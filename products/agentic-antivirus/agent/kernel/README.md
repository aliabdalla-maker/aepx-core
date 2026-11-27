# Kernel-level real-time protection (B-01, B-04)

| OS | Mechanism | Source | Agent side | Fail mode |
|---|---|---|---|---|
| Linux | fanotify permission events (FAN_OPEN_PERM, FAN_OPEN_EXEC_PERM) | — (kernel API) | `aav_agent/realtime_linux.py` | allow if the agent stops |
| Windows | File-system minifilter, IRP_MJ_CREATE pre-operation | `windows/AavFilter.c` | `aav_agent/realtime_windows.py` (filter port) | allow after 3 s or without agent |
| macOS | Endpoint Security AUTH_OPEN / AUTH_EXEC | `macos/main.swift` | `aav_agent/realtime.py` VerdictSocketServer | allow before deadline or without agent |

All three ask one decision service (`aav_agent/realtime.py`), which scans the file with the signed detection
bundle, caches verdicts, never blocks the agent itself and quarantines blocked files through the normal response
path. Linux works today (the agent service runs as root). Windows and macOS build in CI (`kernel` jobs in
`.github/workflows/agentic-antivirus.yml`) but can only be loaded on customer machines after:

- Windows: a production altitude from Microsoft and attestation signing in Partner Center (EV certificate).
  Development: `bcdedit /set testsigning on`, test-sign, `pnputil /add-driver AavFilter.inf /install`, `fltmc load AavFilter`.
- macOS: Apple's `com.apple.developer.endpoint-security.client` entitlement, Developer ID signing, notarisation and
  Full Disk Access (MDM). Development: a test Mac with SIP disabled, ad-hoc signed binary run as root.
