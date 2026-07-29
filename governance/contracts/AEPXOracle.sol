// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title AEPXOracle
/// @notice Reference contract for RFC-0008 — the chain→AI direction of the
/// AEP-X bridge. An on-chain caller (another contract or an EOA) requests an
/// AI decision; the AEP-X `oracle-bridge` off-chain service
/// (services/oracle-bridge) watches for the request event, runs a *governed*
/// AI call (through the Connector Bus: trust + policy + audit) and an
/// evidence/verification scoring pass, then writes the answer back on-chain.
///
/// Request/fulfil is the same shape Chainlink-style oracles use, kept
/// deliberately minimal to match AEPXAnchor.sol / AEPXPolicyRegistry.sol:
/// append-only request ids, one authorized fulfiller, no upgrade logic. The
/// off-chain bridge remains the always-on source of truth for the *decision*
/// (it works with zero chain configured); this contract is the on-chain
/// rendezvous point when a deployment opts into it.
contract AEPXOracle {
    struct Decision {
        address requester;
        string prompt;
        string answer;
        uint8 confidence;   // 0-100, from the Verification Engine's truth score
        string band;        // "GREEN" | "AMBER" | "RED" | "GREY" (Verification bands)
        bool fulfilled;
        uint256 requestedAt;
        uint256 fulfilledAt;
    }

    address public owner;
    /// @notice The only address allowed to call fulfillDecision — the
    /// oracle-bridge's signing account (ORACLE_PRIVATE_KEY). Keeping fulfil
    /// permissioned is what stops anyone from writing a forged AI answer.
    address public oracle;

    uint256 public nextRequestId;
    mapping(uint256 => Decision) private _decisions;

    event DecisionRequested(uint256 indexed requestId, address indexed requester, string prompt);
    event DecisionFulfilled(uint256 indexed requestId, string answer, uint8 confidence, string band);
    event OracleChanged(address previous, address current);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier onlyOracle() {
        require(msg.sender == oracle, "not oracle");
        _;
    }

    constructor(address oracleAddress) {
        owner = msg.sender;
        oracle = oracleAddress;
        emit OracleChanged(address(0), oracleAddress);
    }

    /// @notice Point the contract at a new off-chain fulfiller.
    function setOracle(address oracleAddress) external onlyOwner {
        emit OracleChanged(oracle, oracleAddress);
        oracle = oracleAddress;
    }

    /// @notice Request an AI decision. Returns the request id the caller
    /// (or the off-chain bridge) uses to look the result up later.
    function requestDecision(string calldata prompt) external returns (uint256 requestId) {
        requestId = nextRequestId++;
        _decisions[requestId] = Decision({
            requester: msg.sender,
            prompt: prompt,
            answer: "",
            confidence: 0,
            band: "",
            fulfilled: false,
            requestedAt: block.timestamp,
            fulfilledAt: 0
        });
        emit DecisionRequested(requestId, msg.sender, prompt);
    }

    /// @notice Write the AI answer back on-chain. Restricted to the
    /// authorized oracle; a request can only be fulfilled once.
    function fulfillDecision(
        uint256 requestId,
        string calldata answer,
        uint8 confidence,
        string calldata band
    ) external onlyOracle {
        Decision storage d = _decisions[requestId];
        require(d.requestedAt != 0, "unknown request");
        require(!d.fulfilled, "already fulfilled");
        require(confidence <= 100, "confidence out of range");
        d.answer = answer;
        d.confidence = confidence;
        d.band = band;
        d.fulfilled = true;
        d.fulfilledAt = block.timestamp;
        emit DecisionFulfilled(requestId, answer, confidence, band);
    }

    function getDecision(uint256 requestId) external view returns (Decision memory) {
        require(_decisions[requestId].requestedAt != 0, "unknown request");
        return _decisions[requestId];
    }

    function isFulfilled(uint256 requestId) external view returns (bool) {
        return _decisions[requestId].fulfilled;
    }
}
