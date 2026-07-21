// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/// @title AEPXAnchor
/// @notice Reference contract for RFC-0006 — anchors the Governance
/// Engine's audit-trail Merkle roots (services/governance/app/ledger.py's
/// EVMAnchorClient) so their tamper-evidence extends onto a real chain.
/// Deliberately minimal: append-only, one event per anchor, no upgrade
/// logic — the local hash chain (LocalHashChainAnchor) is the always-on
/// source of truth this merely reinforces.
contract AEPXAnchor {
    event Anchored(uint256 indexed index, bytes32 root, uint256 timestamp);

    bytes32[] private _roots;

    function anchor(bytes32 root) external {
        _roots.push(root);
        emit Anchored(_roots.length - 1, root, block.timestamp);
    }

    function latestRoot() external view returns (bytes32) {
        require(_roots.length > 0, "no anchors yet");
        return _roots[_roots.length - 1];
    }

    function anchorCount() external view returns (uint256) {
        return _roots.length;
    }
}
