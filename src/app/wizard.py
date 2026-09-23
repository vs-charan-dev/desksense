"""
DeskSense Calibration Wizard State Machine (Phase 3 Module 2)
Guides user through camera placement, 3-second countdown, 10-second posture baseline capture,
quality checks, profile persistence, and failure recovery.
Conforms strictly to P3-05 and P3-06 test specifications:
- Placement guidance -> 3s countdown -> 10s capture -> success saves profile and enters monitoring
- Poor quality / camera failure shows reason and allows retry or cancel without losing previous valid calibration
- Pluggable clock for deterministic automated testing
"""

import time
import copy
from enum import Enum
from typing import Optional, Dict, Any, Tuple
from src.vision.calibration import CalibrationManager, CalibrationProfile


class WizardState(str, Enum):
    IDLE = "IDLE"
    GUIDANCE = "GUIDANCE"
    COUNTDOWN = "COUNTDOWN"
    CAPTURING = "CAPTURING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class CalibrationWizard:
    def __init__(
        self,
        calibration_manager: Optional[CalibrationManager] = None,
        profile_path: str = "calibration_profile.json",
        countdown_sec: float = 3.0,
        capture_sec: float = 10.0,
        min_required_samples: int = 15,
        time_func = None
    ):
        self.time_func = time_func or time.time
        self.countdown_sec = countdown_sec
        self.capture_sec = capture_sec
        self.profile_path = profile_path

        if calibration_manager is not None:
            self.manager = calibration_manager
        else:
            self.manager = CalibrationManager(
                profile_path=profile_path,
                calibration_duration_sec=capture_sec,
                min_required_samples=min_required_samples,
                time_func=self.time_func
            )

        self.state: WizardState = WizardState.IDLE
        self.countdown_start_time: Optional[float] = None
        self.failure_reason: Optional[str] = None
        # Preserve backup of previously active valid profile for recovery/cancel
        self.previous_valid_profile: Optional[CalibrationProfile] = (
            copy.deepcopy(self.manager.profile) if self.manager.profile else None
        )

    def start_guidance(self) -> None:
        """Transitions from IDLE or FAILED into placement guidance step."""
        # Refresh backup of current profile
        if self.manager.profile:
            self.previous_valid_profile = copy.deepcopy(self.manager.profile)
        self.state = WizardState.GUIDANCE
        self.failure_reason = None

    def begin_countdown(self) -> None:
        """User confirms placement; starts 3-second countdown."""
        self.state = WizardState.COUNTDOWN
        self.countdown_start_time = self.time_func()
        self.failure_reason = None

    @property
    def countdown_remaining(self) -> float:
        """Returns seconds remaining in countdown (clamped to 0.0)."""
        if self.state != WizardState.COUNTDOWN or self.countdown_start_time is None:
            return 0.0
        elapsed = self.time_func() - self.countdown_start_time
        return max(0.0, self.countdown_sec - elapsed)

    def update(self) -> WizardState:
        """
        Clock tick update.
        Transitions COUNTDOWN -> CAPTURING once 3 seconds elapse.
        """
        now = self.time_func()
        if self.state == WizardState.COUNTDOWN:
            if self.countdown_start_time is not None:
                elapsed = now - self.countdown_start_time
                if elapsed >= self.countdown_sec:
                    # Transition to CAPTURING
                    self.state = WizardState.CAPTURING
                    self.manager.start_calibration(duration_sec=self.capture_sec)

        elif self.state == WizardState.CAPTURING:
            # If time exceeded calibration window, finalize
            if self.manager.is_calibrating and self.manager.start_time:
                elapsed = now - self.manager.start_time
                if elapsed >= self.manager.calibration_duration_sec:
                    success, msg = self.manager._finalize_calibration()
                    if success:
                        self.state = WizardState.SUCCESS
                        self.previous_valid_profile = copy.deepcopy(self.manager.profile)
                    else:
                        self.state = WizardState.FAILED
                        self.failure_reason = msg or "Calibration failed quality checks"

        return self.state

    def add_sample(
        self,
        metrics: Optional[Dict[str, float]],
        confidence: float = 1.0
    ) -> Tuple[bool, Optional[str]]:
        """Feeds sample from camera during CAPTURING."""
        if self.state == WizardState.COUNTDOWN:
            # Auto-tick in case update wasn't called explicitly
            self.update()

        if self.state != WizardState.CAPTURING:
            return False, f"Wizard not in capturing state (current: {self.state.value})"

        finished, reason = self.manager.add_sample(metrics, confidence)
        if finished:
            if self.manager.profile is not None:
                self.state = WizardState.SUCCESS
                self.previous_valid_profile = copy.deepcopy(self.manager.profile)
                return True, "Calibration successful"
            else:
                self.state = WizardState.FAILED
                self.failure_reason = reason or "Quality criteria not met"
                return False, self.failure_reason
        return False, None

    def report_camera_error(self, error_message: str) -> None:
        """Handles camera error or disconnect during wizard."""
        self.state = WizardState.FAILED
        self.failure_reason = f"Camera error: {error_message}"
        self.manager.is_calibrating = False

    def retry(self) -> None:
        """Allows user to retry calibration after failure without losing previous valid profile."""
        self.failure_reason = None
        self.state = WizardState.GUIDANCE

    def cancel(self) -> None:
        """
        User cancels calibration wizard.
        Restores previous valid calibration profile if one existed, ensuring zero data loss.
        """
        if self.previous_valid_profile is not None:
            self.manager.profile = copy.deepcopy(self.previous_valid_profile)
            self.manager.save_profile()
        self.manager.is_calibrating = False
        self.failure_reason = None
        self.state = WizardState.IDLE

    def finish(self) -> Optional[CalibrationProfile]:
        """Finalizes wizard on SUCCESS and returns saved profile."""
        if self.state == WizardState.SUCCESS:
            self.state = WizardState.IDLE
            return self.manager.profile
        return None

    def get_status(self) -> Dict[str, Any]:
        """Status payload for UI presentation."""
        return {
            "state": self.state.value,
            "countdown_sec": round(self.countdown_remaining, 1),
            "capture_progress_pct": round(self.manager.progress_pct, 1),
            "sample_count": len(self.manager.samples),
            "min_required_samples": self.manager.min_required_samples,
            "failure_reason": self.failure_reason,
            "has_profile": self.manager.profile is not None,
            "profile": self.manager.profile.to_dict() if self.manager.profile else None
        }

    def tick(self, dt: float = 0.0) -> WizardState:
        """Alias for update() to support tick-based caller loops."""
        return self.update()
