// Wire protocol between the AavFilter minifilter and the user-mode agent (aav_agent/realtime_windows.py).
// Keep the layout in step with the ctypes structures there; tests/test_realtime.py checks the constants.
#pragma once

#define AAV_PORT_NAME L"\\AavFilterPort"
#define AAV_MAX_PATH_CHARS 520
#define AAV_OP_OPEN 1
#define AAV_OP_EXEC 2

typedef struct _AAV_REQUEST {
    ULONG ProcessId;
    ULONG Operation;                       // AAV_OP_OPEN or AAV_OP_EXEC
    WCHAR Path[AAV_MAX_PATH_CHARS];        // normalized DOS path when available, NUL-terminated
} AAV_REQUEST, *PAAV_REQUEST;

typedef struct _AAV_REPLY {
    ULONG Allow;                           // 1 = allow, 0 = deny
} AAV_REPLY, *PAAV_REPLY;
