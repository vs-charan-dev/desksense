"""
DeskSense Desktop Application Package (Phase 3)
Provides Desktop Shell host controller, Calibration Wizard state machine,
Dashboard aggregation view models, Live Status Widget state, and Tray/Hotkey management.
"""

from src.app.core import DeskSenseApp, AppState, MonitoringState
from src.app.wizard import CalibrationWizard, WizardState
from src.app.widget import StatusWidgetState
from src.app.dashboard import DashboardService
from src.app.tray import TrayController, TrayCommand
from src.app.hotkey import HotkeyManager

__all__ = [
    "DeskSenseApp",
    "AppState",
    "MonitoringState",
    "CalibrationWizard",
    "WizardState",
    "StatusWidgetState",
    "DashboardService",
    "TrayController",
    "TrayCommand",
    "HotkeyManager",
]
