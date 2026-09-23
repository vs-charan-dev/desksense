"""Windows Startup Manager for DeskSense (Phase 6).
Manages automatic launch at Windows login minimized to the system tray.
Uses Windows Registry (HKCU\Software\Microsoft\Windows\CurrentVersion\Run) or portable mock registry.
Actions are strictly idempotent: enabling twice does not duplicate; disabling when absent is a clean no-op.
"""

import sys
import os
from typing import Optional

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DeskSense"


class WindowsStartupManager:
    """Manages Windows startup registry entries idempotently."""

    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode or (not HAS_WINREG)
        self._mock_registry: dict = {}

    def is_startup_enabled(self) -> bool:
        """Checks if startup key exists."""
        if self.mock_mode:
            return APP_NAME in self._mock_registry

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except (FileNotFoundError, OSError):
            return False

    def enable_startup(self, executable_path: Optional[str] = None, start_minimized: bool = True) -> bool:
        """
        Enables launch at Windows login with minimized-to-tray argument.
        Idempotent: safe to invoke repeatedly.
        """
        exe = executable_path or sys.executable
        cmd = f'"{exe}" --minimized' if start_minimized else f'"{exe}"'

        if self.mock_mode:
            self._mock_registry[APP_NAME] = cmd
            return True

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                return True
        except OSError:
            return False

    def disable_startup(self) -> bool:
        """
        Removes launch at Windows login.
        Idempotent: safe to invoke even if key does not exist.
        """
        if self.mock_mode:
            self._mock_registry.pop(APP_NAME, None)
            return True

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass  # already removed
                return True
        except OSError:
            return False
