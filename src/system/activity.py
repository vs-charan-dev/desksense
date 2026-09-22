"""DeskSense System Activity Monitor.
Uses Win32 native APIs via ctypes to track active foreground window, process name,
and keyboard/mouse idle duration via GetLastInputInfo.
Includes interval aggregation to prevent database bloat on repeated polls.
"""

import sys
import os
import time
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, Any, Tuple, Callable


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class ActivityTracker:
    """Tracks Windows foreground window, active process name, and user idle duration."""

    def __init__(
        self,
        idle_threshold_seconds: float = 60.0,
        clock_func: Optional[Callable[[], float]] = None,
        tick_func: Optional[Callable[[], int]] = None,
        last_input_func: Optional[Callable[[], Optional[int]]] = None,
    ):
        """Initialize activity tracker with dependency injection for testability."""
        self.idle_threshold_seconds = idle_threshold_seconds
        self.clock_func = clock_func or time.time
        self.tick_func = tick_func or self._native_get_tick_count
        self.last_input_func = last_input_func or self._native_get_last_input_tick

        self.current_window_title: str = ""
        self.current_process_name: str = ""
        self.current_exe_path: str = ""
        self.interval_start_time: float = self.clock_func()
        self.last_poll_time: float = self.interval_start_time
        self.active_intervals: list = []

    def _native_get_tick_count(self) -> int:
        if sys.platform == "win32":
            return ctypes.windll.kernel32.GetTickCount()
        return int(time.monotonic() * 1000)

    def _native_get_last_input_tick(self) -> Optional[int]:
        if sys.platform != "win32":
            return self.tick_func()
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                return lii.dwTime
        except Exception:
            pass
        return None

    def get_idle_duration(self) -> float:
        """Returns idle duration in seconds, handling 32-bit tick wrap safely."""
        last_input = self.last_input_func()
        if last_input is None:
            return 0.0

        current_tick = self.tick_func()
        # Handle 32-bit unsigned rollover correctly: (current_tick - last_input) & 0xFFFFFFFF
        diff_ms = (current_tick - last_input) & 0xFFFFFFFF
        return max(0.0, float(diff_ms) / 1000.0)

    def is_idle(self) -> bool:
        """True if user has been inactive for longer than idle_threshold_seconds."""
        return self.get_idle_duration() >= self.idle_threshold_seconds

    def get_foreground_info(self) -> Tuple[str, str, str]:
        """Queries Win32 API for (process_name, window_title, exe_path)."""
        if sys.platform != "win32":
            return ("test_app.exe", "Test Application Window", "C:\\test\\test_app.exe")

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ("Unknown", "", "")

        # Window title
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
        else:
            title = ""

        # Process ID and Name
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = "Unknown"
        exe_path = ""

        if pid.value > 0:
            try:
                import psutil
                proc = psutil.Process(pid.value)
                process_name = proc.name()
                try:
                    exe_path = proc.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    exe_path = ""
            except Exception:
                pass

        return (process_name, title, exe_path)

    def poll(
        self,
        override_foreground: Optional[Tuple[str, str, str]] = None
    ) -> Dict[str, Any]:
        """Polls current activity and manages interval aggregation.
        
        If foreground app & window title match current interval, extends the interval
        rather than emitting a new record on every poll (deduplication).
        """
        now = self.clock_func()
        idle_sec = self.get_idle_duration()
        is_idle_now = idle_sec >= self.idle_threshold_seconds

        if override_foreground is not None:
            proc_name, win_title, exe_path = override_foreground
        else:
            proc_name, win_title, exe_path = self.get_foreground_info()

        # Check if the active window has changed
        window_changed = (proc_name != self.current_process_name) or (win_title != self.current_window_title)

        closed_interval = None
        if window_changed:
            # Close previous interval if valid
            if self.current_process_name and now > self.interval_start_time:
                closed_interval = {
                    "application": self.current_process_name,
                    "window_title": self.current_window_title,
                    "exe_path": self.current_exe_path,
                    "start_time": self.interval_start_time,
                    "end_time": now,
                    "duration": max(0.0, now - self.interval_start_time),
                }

            # Start new interval
            self.current_process_name = proc_name
            self.current_window_title = win_title
            self.current_exe_path = exe_path
            self.interval_start_time = now

        self.last_poll_time = now

        current_active_interval = {
            "application": self.current_process_name,
            "window_title": self.current_window_title,
            "exe_path": self.current_exe_path,
            "start_time": self.interval_start_time,
            "end_time": now,
            "duration": max(0.0, now - self.interval_start_time),
        }

        return {
            "application": self.current_process_name,
            "window_title": self.current_window_title,
            "exe_path": self.current_exe_path,
            "idle_duration_seconds": idle_sec,
            "is_idle": is_idle_now,
            "window_changed": window_changed,
            "closed_interval": closed_interval,
            "current_interval": current_active_interval,
        }

    def close_current_interval(self) -> Optional[Dict[str, Any]]:
        """Closes and returns the active interval (e.g. on session end or sleep)."""
        now = self.clock_func()
        if self.current_process_name and now > self.interval_start_time:
            interval = {
                "application": self.current_process_name,
                "window_title": self.current_window_title,
                "exe_path": self.current_exe_path,
                "start_time": self.interval_start_time,
                "end_time": now,
                "duration": max(0.0, now - self.interval_start_time),
            }
            self.interval_start_time = now
            return interval
        return None
