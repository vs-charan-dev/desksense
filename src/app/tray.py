"""
DeskSense System Tray Controller (Phase 3 Module 1)
Defines tray menu actions, pause duration options, and status indicator.
Conforms strictly to P3-02 test specification:
- Open Dashboard, Pause 15m, Pause 1h, Custom pause, Recalibrate, Settings, and Quit invoke correct action once.
- Tray status reflects live monitoring, pause countdown, or calibration state.
"""

from enum import Enum
from typing import Callable, Optional, Dict, Any


class TrayCommand(str, Enum):
    OPEN_DASHBOARD = "open_dashboard"
    PAUSE_15_MIN = "pause_15_min"
    PAUSE_1_HOUR = "pause_1_hour"
    PAUSE_CUSTOM = "pause_custom"
    RESUME = "resume"
    RECALIBRATE = "recalibrate"
    SETTINGS = "settings"
    QUIT = "quit"


class TrayController:
    def __init__(self, app_controller=None):
        self.app = app_controller
        self.action_history = []
        self._handlers: Dict[TrayCommand, Callable] = {}
        self._init_default_handlers()

    def _init_default_handlers(self):
        self._handlers = {
            TrayCommand.OPEN_DASHBOARD: self._handle_open_dashboard,
            TrayCommand.PAUSE_15_MIN: lambda: self._handle_pause(900.0),
            TrayCommand.PAUSE_1_HOUR: lambda: self._handle_pause(3600.0),
            TrayCommand.PAUSE_CUSTOM: lambda minutes=30.0: self._handle_pause(float(minutes) * 60.0),
            TrayCommand.RESUME: self._handle_resume,
            TrayCommand.RECALIBRATE: self._handle_recalibrate,
            TrayCommand.SETTINGS: self._handle_settings,
            TrayCommand.QUIT: self._handle_quit,
        }

    def set_handler(self, cmd: TrayCommand, handler: Callable) -> None:
        """Register custom or mocked handler."""
        self._handlers[cmd] = handler

    def dispatch(self, cmd: TrayCommand, *args, **kwargs) -> Any:
        """Executes a tray menu command once."""
        self.action_history.append((cmd.value, args, kwargs))
        handler = self._handlers.get(cmd)
        if handler:
            return handler(*args, **kwargs)
        return None

    def _handle_open_dashboard(self):
        if self.app:
            return self.app.show_dashboard()
        return True

    def _handle_pause(self, duration_sec: float):
        if self.app:
            return self.app.pause_monitoring(duration_sec)
        return True

    def _handle_resume(self):
        if self.app:
            return self.app.resume_monitoring()
        return True

    def _handle_recalibrate(self):
        if self.app:
            return self.app.start_calibration()
        return True

    def _handle_settings(self):
        if self.app:
            return self.app.open_settings()
        return True

    def _handle_quit(self):
        if self.app:
            return self.app.quit()
        return True

    def get_tray_menu_definition(self) -> Dict[str, Any]:
        """Returns structured tray menu for host integration."""
        status_label = "● Monitoring"
        if self.app:
            status_label = self.app.get_tray_status_label()

        return {
            "title": "DeskSense",
            "status_label": status_label,
            "items": [
                {"id": TrayCommand.OPEN_DASHBOARD.value, "label": "Open Dashboard", "enabled": True},
                {"type": "separator"},
                {"id": TrayCommand.PAUSE_15_MIN.value, "label": "Pause 15 minutes", "enabled": True},
                {"id": TrayCommand.PAUSE_1_HOUR.value, "label": "Pause 1 hour", "enabled": True},
                {"id": TrayCommand.PAUSE_CUSTOM.value, "label": "Pause (Custom)...", "enabled": True},
                {"id": TrayCommand.RESUME.value, "label": "Resume Monitoring", "enabled": True},
                {"type": "separator"},
                {"id": TrayCommand.RECALIBRATE.value, "label": "Recalibrate Posture", "enabled": True},
                {"id": TrayCommand.SETTINGS.value, "label": "Settings", "enabled": True},
                {"type": "separator"},
                {"id": TrayCommand.QUIT.value, "label": "Quit DeskSense", "enabled": True},
            ]
        }
