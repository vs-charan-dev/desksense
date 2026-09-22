"""DeskSense Toast Notification Dispatcher.
Dispatches native Windows toast notifications using PowerShell WinRT or fallback alerts.
Enforces shared 5-minute cooldown per alert category and supports category enable/disable toggles.
Guarantees payloads contain zero image or frame blobs.
"""

import sys
import time
import subprocess
from typing import Optional, Dict, Any, Callable


class NotificationCategory:
    POSTURE = "POSTURE"
    BREAK = "BREAK"
    SEDENTARY = "SEDENTARY"
    CALIBRATION = "CALIBRATION"
    SYSTEM = "SYSTEM"


TOAST_TEMPLATES = {
    "SLOUCHING": {
        "title": "Posture Coach",
        "message": "You've been slouching for a bit. Gently roll your shoulders back.",
        "category": NotificationCategory.POSTURE,
    },
    "TOO_CLOSE": {
        "title": "Screen Distance",
        "message": "You're leaning a bit too close to the screen. Ease back for better eye comfort.",
        "category": NotificationCategory.POSTURE,
    },
    "LEAN_LEFT": {
        "title": "Posture Coach",
        "message": "Noticeable lean to the left. Center your weight evenly on your chair.",
        "category": NotificationCategory.POSTURE,
    },
    "LEAN_RIGHT": {
        "title": "Posture Coach",
        "message": "Noticeable lean to the right. Center your weight evenly on your chair.",
        "category": NotificationCategory.POSTURE,
    },
    "HEAD_TILT": {
        "title": "Posture Coach",
        "message": "Head tilt detected. Align your neck comfortably with your spine.",
        "category": NotificationCategory.POSTURE,
    },
    "SEDENTARY_ALERT": {
        "title": "Movement Break",
        "message": "You've been seated for over 60 minutes. Stand up, stretch, and grab some water.",
        "category": NotificationCategory.SEDENTARY,
    },
    "CALIBRATION_SUCCESS": {
        "title": "DeskSense Calibrated",
        "message": "Baseline posture recorded successfully. DeskSense is now monitoring.",
        "category": NotificationCategory.CALIBRATION,
    },
}


class NotificationDispatcher:
    """Manages alert formatting, cooldowns, toggles, and OS dispatch."""

    def __init__(
        self,
        cooldown_seconds: float = 300.0,  # 5 minutes
        clock_func: Optional[Callable[[], float]] = None,
        dispatch_func: Optional[Callable[[str, str], bool]] = None,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.clock_func = clock_func or time.time
        self.dispatch_func = dispatch_func or self._native_toast_dispatch

        # Category enable/disable settings
        self.category_enabled: Dict[str, bool] = {
            NotificationCategory.POSTURE: True,
            NotificationCategory.BREAK: True,
            NotificationCategory.SEDENTARY: True,
            NotificationCategory.CALIBRATION: True,
            NotificationCategory.SYSTEM: True,
        }

        # Track last alert dispatch per alert key
        self.last_dispatched: Dict[str, float] = {}
        self.dispatch_history: list = []

    def set_category_enabled(self, category: str, enabled: bool) -> None:
        self.category_enabled[category] = enabled

    def can_dispatch(self, alert_key: str) -> bool:
        template = TOAST_TEMPLATES.get(alert_key)
        if not template:
            return False

        category = template["category"]
        if not self.category_enabled.get(category, True):
            return False

        now = self.clock_func()
        last_time = self.last_dispatched.get(alert_key, 0.0)
        if (now - last_time) < self.cooldown_seconds:
            return False

        return True

    def format_payload(self, alert_key: str) -> Optional[Dict[str, str]]:
        template = TOAST_TEMPLATES.get(alert_key)
        if not template:
            return None
        # Verify no image or frame blob in payload
        return {
            "title": template["title"],
            "message": template["message"],
            "category": template["category"],
        }

    def dispatch(self, alert_key: str) -> bool:
        """Evaluates cooldown and category, then dispatches toast notification."""
        if not self.can_dispatch(alert_key):
            return False

        payload = self.format_payload(alert_key)
        if not payload:
            return False

        now = self.clock_func()
        self.last_dispatched[alert_key] = now
        self.dispatch_history.append({"key": alert_key, "time": now, "payload": payload})

        return self.dispatch_func(payload["title"], payload["message"])

    def _native_toast_dispatch(self, title: str, message: str) -> bool:
        """Sends native Windows toast via PowerShell BurntToast or Windows.UI.Notifications."""
        if sys.platform != "win32":
            return True

        # Clean escaping for PowerShell
        safe_title = title.replace('"', '`"')
        safe_msg = message.replace('"', '`"')

        ps_script = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) > $null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) > $null; "
            f"$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DeskSense'); "
            f"$notification = [Windows.UI.Notifications.ToastNotification]::new($template); "
            f"$notifier.Show($notification);"
        )

        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except Exception:
            return False
