# Release manifest — aav-v0.1.1 (DLV-15)

- Tag: `aav-v0.1.1` (GitHub release, aliabdalla-maker/aepx-core), built by `.github/workflows/agentic-antivirus.yml`
- Source commit: `4e5c8ea9ed78ed5574a99cc2c30745f54c77e86c` (merge of PR #430)
- Production control plane: same commit, api.softwareequality.com/apps/agentic-antivirus (verified 19 Nov 2026 via /api/ready)
- Containers: ghcr.io images `:latest` and `:edge` (public)
- SBOM: `aav-sbom.spdx.json` (SPDX), SHA-256 `0e8a925e90ff7af33e3b32adfc5c98e162bee4652a19989487e020a7c4379de5`
- Checksums file: `SHA256SUMS.txt`, SHA-256 `306233dab27a170da4946000baf2dbe39946cc94618824329c55e5890e58e3d9`
- Signing: Windows unsigned; macOS ad-hoc signed only (register B-02, proposed deferral to Release 2)

| Asset | Size | SHA-256 |
|---|---|---|
| agentic-antivirus-0.1.1-beta-win-x64.exe | 106 MB | 2820ebd5dec92f1a65d921650efd868aae7f3ffeb39ec7d1c2c7966cbc1f9b32 |
| agentic-antivirus-0.1.1-beta-win-arm64.exe | 102 MB | cb1889bf1bbaa4e7e8fde36023d50b2365632486ca28fbca6c6c084225f0532c |
| agentic-antivirus-0.1.1-beta-win.exe | 207 MB | 76d9a62c48f25b338fb6b6d0bc7bac467ed203da199ce3cd27d9ca7f76d542d2 |
| agentic-antivirus-0.1.1-beta-mac-arm64.dmg | 115 MB | afff7727e1ccceea4f6b87bb4ad1f009de687dc8ebc16469c552562415e467ce |
| agentic-antivirus-0.1.1-beta-mac-x64.dmg | 119 MB | 3880b5bdc9ba3e2a8a2b38b6d1622f426ae14da9ca2cb144e011e673b92acedd |
| agentic-antivirus-0.1.1-beta-linux-x86_64.AppImage | 121 MB | b7361c65d1a5a8661a0b72688d70216e87ff425088fa2b151e0ccbbdd86cdd62 |
| agentic-antivirus-0.1.1-beta-linux-arm64.AppImage | 123 MB | fb56de0fde1c7f88a1d72e588de9d942b9afc81d583d4715c3d21e2d0109e5fb |
| agentic-antivirus-0.1.1-beta-linux-amd64.deb | 94.9 MB | 32d2faa3566b1393616bf705500410ffe839896474394be2165aecc125db3cdc |
| agentic-antivirus-0.1.1-beta-linux-arm64.deb | 90.3 MB | 57e8918f925d9e29e93fe4c8a150af140209fd8c8044eb814d3b02a323436d49 |
| aav-agent-windows-x64.exe | 16.8 MB | e51fcea0cda295598fc9705b91fb47298bc5b95e8897147b724cb39cfb4496f5 |
| aav-agent-service-windows-x64.exe | 17.2 MB | 7fff518219ba689c9b8ad9797ee05048b35d81e979a24de81abaf1999d608cb7 |
| aav-agent-macos-arm64 | 15.4 MB | 7d0869e60562f2d2f572bb112ee2a4b4086db586552e54da4a5fdd7d075da497 |
| aav-agent-linux-x64 | 31.3 MB | ac7ea52347be32e978c99ac41b7e14e9fdd563b041984e49f0837d211fcf833e |
| aav-agent-linux-arm64 | 29.1 MB | 1a56bf8ed378d2fbfb1c79555aecda56214e3041bbbf5efdc792ab8cfe21e924 |

Known issues fixed in the next release (PR #431): console menu clicks, desktop window not opening after install,
in-app scan, baseline detection bundle not published on fresh deployments.
