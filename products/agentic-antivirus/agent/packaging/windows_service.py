"""Windows service wrapper (built with PyInstaller + pywin32 on windows-latest).
Install: aav-agent-service.exe --startup auto install ; start: sc start AgenticAntivirus"""
import os
import sys
import threading

import servicemanager  # type: ignore
import win32event  # type: ignore
import win32service  # type: ignore
import win32serviceutil  # type: ignore

from aav_agent.agent import Agent

STATE = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "AgenticAntivirus")


class AgenticAntivirusService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AgenticAntivirus"
    _svc_display_name_ = "Agentic Antivirus endpoint agent"
    _svc_description_ = "Scans files, monitors behaviour and applies signed policies from the control plane."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        agent = Agent(STATE)
        t = threading.Thread(target=agent.run_forever, daemon=True)
        t.start()
        servicemanager.LogInfoMsg("Agentic Antivirus agent started")
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AgenticAntivirusService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(AgenticAntivirusService)
