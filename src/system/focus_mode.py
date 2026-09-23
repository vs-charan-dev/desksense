"""
DeskSense Manual Focus Mode
Provides timed focus sessions (e.g., 25-minute Pomodoro or custom),
heightens phone detection sensitivity during the session, and restores it on completion.
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
from src.vision.phone_fusion import PhoneUsageFusion


class FocusSessionStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class FocusSessionResult:
    target_seconds: int
    elapsed_seconds: int
    completed: bool
    interrupted_by_phone: bool = False


class FocusModeController:
    """
    Coordinates manual focus sessions with phone sensitivity management.
    """

    def __init__(
        self,
        phone_fusion: Optional[PhoneUsageFusion] = None,
        on_session_complete: Optional[Callable[[FocusSessionResult], None]] = None,
    ):
        self.phone_fusion = phone_fusion
        self.on_session_complete = on_session_complete

        self.status: FocusSessionStatus = FocusSessionStatus.IDLE
        self.target_seconds: int = 25 * 60
        self.elapsed_seconds: float = 0.0
        self.last_update_time: Optional[float] = None
        self.phone_interrupt_count: int = 0

    @property
    def is_active(self) -> bool:
        return self.status == FocusSessionStatus.RUNNING

    def start(self, duration_minutes: int = 25, custom_seconds: Optional[int] = None) -> None:
        """Starts a focus session and increases phone detection sensitivity."""
        self.target_seconds = custom_seconds if custom_seconds is not None else (duration_minutes * 60)
        self.elapsed_seconds = 0.0
        self.last_update_time = time.time()
        self.status = FocusSessionStatus.RUNNING
        self.phone_interrupt_count = 0

        if self.phone_fusion:
            self.phone_fusion.set_focus_mode_sensitivity(True)

    def pause(self) -> None:
        """Pauses the focus timer."""
        if self.status == FocusSessionStatus.RUNNING:
            self.status = FocusSessionStatus.PAUSED
            self.last_update_time = None

    def resume(self) -> None:
        """Resumes the focus timer."""
        if self.status == FocusSessionStatus.PAUSED:
            self.status = FocusSessionStatus.RUNNING
            self.last_update_time = time.time()

    def cancel(self) -> FocusSessionResult:
        """Cancels the active focus session and restores phone sensitivity."""
        result = FocusSessionResult(
            target_seconds=self.target_seconds,
            elapsed_seconds=int(round(self.elapsed_seconds)),
            completed=False,
            interrupted_by_phone=(self.phone_interrupt_count > 0),
        )
        self.status = FocusSessionStatus.CANCELLED
        self.last_update_time = None

        if self.phone_fusion:
            self.phone_fusion.set_focus_mode_sensitivity(False)

        return result

    def update(self, current_time: Optional[float] = None) -> Optional[FocusSessionResult]:
        """
        Advances focus timer. Completes session if target reached.
        """
        if self.status != FocusSessionStatus.RUNNING:
            return None

        now = time.time() if current_time is None else current_time
        if self.last_update_time is not None:
            dt = now - self.last_update_time
            if dt > 0:
                self.elapsed_seconds += dt
        self.last_update_time = now

        if self.elapsed_seconds >= self.target_seconds:
            return self._complete()

        return None

    def record_phone_interruption(self) -> None:
        """Increments phone distraction count during focus session."""
        if self.status == FocusSessionStatus.RUNNING:
            self.phone_interrupt_count += 1

    def _complete(self) -> FocusSessionResult:
        """Completes the session successfully and restores phone sensitivity."""
        result = FocusSessionResult(
            target_seconds=self.target_seconds,
            elapsed_seconds=int(round(self.elapsed_seconds)),
            completed=True,
            interrupted_by_phone=(self.phone_interrupt_count > 0),
        )
        self.status = FocusSessionStatus.COMPLETED
        self.last_update_time = None

        if self.phone_fusion:
            self.phone_fusion.set_focus_mode_sensitivity(False)

        if self.on_session_complete:
            self.on_session_complete(result)

        return result

    def get_state(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "target_seconds": self.target_seconds,
            "elapsed_seconds": int(round(self.elapsed_seconds)),
            "remaining_seconds": max(0, int(round(self.target_seconds - self.elapsed_seconds))),
            "phone_interrupt_count": self.phone_interrupt_count,
        }
