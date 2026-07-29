// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title AEPXPolicyRegistry
/// @notice Reference contract for RFC-0006 — an optional on-chain source
/// of truth for the Governance Engine's risk-level ceiling
/// (services/governance/app/main.py's `_POLICIES["max_risk_level"]` seed
/// policy). Levels follow the same 0-4 ordinal scale as AIA-R/Safety S
/// classes: 0=S0 ... 4=S4 (see SOA-Architecture.md §1.1).
contract AEPXPolicyRegistry {
    address public owner;
    uint8 public maxRiskLevel;

    event MaxRiskLevelChanged(uint8 previous, uint8 current);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(uint8 initialMaxRiskLevel) {
        require(initialMaxRiskLevel <= 4, "level out of range");
        owner = msg.sender;
        maxRiskLevel = initialMaxRiskLevel;
    }

    function setMaxRiskLevel(uint8 level) external onlyOwner {
        require(level <= 4, "level out of range");
        emit MaxRiskLevelChanged(maxRiskLevel, level);
        maxRiskLevel = level;
    }
}
