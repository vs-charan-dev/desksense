"""
DeskSense Temporal Smoothing & Notification Filter (Phase 1 Module 5)
Handles:
- Jitter suppression via rolling window majority voting (P1-12)
- Deviation persistence tracking (P1-13, P1-14)
- Persistence reset on return to good posture (P1-15)
- Notification cooldown enforcement (P1-16)

Provides deterministic testing via mockable time function.
"""

import time
from collections import deque, Counter
from typing import Optional, Dict, Any, List, Tuple

class TemporalFilter:
    def __init__(
        self,
        window_size: int = 7,
        persistence_threshold_sec: float = 20.0,
        cooldown_sec: float = 300.0,  # 5 minutes
        time_func = None
    ):
        """
        :param window_size: Number of frames in rolling buffer for majority voting jitter suppression.
        :param persistence_threshold_sec: Continuous deviation duration required before alerting.
        :param cooldown_sec: Minimum cooldown duration between repeated alerts of same type.
        :param time_func: Callable returning epoch seconds.
        """
        self.window_size = window_size
        self.persistence_threshold_sec = persistence_threshold_sec
        self.cooldown_sec = cooldown_sec
        self.time_func = time_func or time.time

        self.history: deque = deque(maxlen=window_size)
        self.stable_state: str = "UNKNOWN"

        # Deviation tracking
        self.current_deviation_state: Optional[str] = None
        self.deviation_start_time: Optional[float] = None
        self.continuous_deviation_duration: float = 0.0

        # Alert tracking
        self.last_alert_time: Dict[str, float] = {}

    def update(self, raw_posture: str) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Update rolling filter with raw posture frame.
        
        Returns:
            (stable_posture, should_notify, diagnostics)
        """
        now = self.time_func()
        self.history.append(raw_posture)

        # 1. Majority voting jitter suppression (P1-12)
        counts = Counter(self.history)
        # Select most common candidate
        most_common, freq = counts.most_common(1)[0]

        # Require majority (> half window size) or full agreement if window small
        if freq > (len(self.history) / 2):
            self.stable_state = most_common
        # Else retain current stable_state to suppress flapping

        stable = self.stable_state

        # 2. Persistence Tracking (P1-13, P1-14, P1-15)
        should_notify = False
        alert_reason = None

        if stable in {"POSTURE_GOOD", "UNKNOWN"}:
            # P1-15: Reset persistence timer on return to good posture or unknown
            self.current_deviation_state = None
            self.deviation_start_time = None
            self.continuous_deviation_duration = 0.0
        else:
            # Bad posture detected
            if self.current_deviation_state != stable:
                # Started a new deviation condition
                self.current_deviation_state = stable
                self.deviation_start_time = now
                self.continuous_deviation_duration = 0.0
            else:
                # Continuing current deviation condition
                if self.deviation_start_time is not None:
                    self.continuous_deviation_duration = max(0.0, now - self.deviation_start_time)

            # P1-14: Has it reached the continuous persistence threshold?
            if self.continuous_deviation_duration >= self.persistence_threshold_sec:
                # Check cooldown (P1-16)
                last_alert = self.last_alert_time.get(stable, 0.0)
                if (now - last_alert) >= self.cooldown_sec:
                    should_notify = True
                    alert_reason = f"Persistent {stable} for {round(self.continuous_deviation_duration, 1)}s"
                    self.last_alert_time[stable] = now

        diagnostics = {
            "stable_posture": stable,
            "raw_posture": raw_posture,
            "window_counts": dict(counts),
            "deviation_condition": self.current_deviation_state,
            "deviation_duration_sec": round(self.continuous_deviation_duration, 2),
            "persistence_threshold_sec": self.persistence_threshold_sec,
            "should_notify": should_notify,
            "alert_reason": alert_reason
        }

        return stable, should_notify, diagnostics

    def reset(self):
        """Reset temporal smoothing state."""
        self.history.clear()
        self.stable_state = "UNKNOWN"
        self.current_deviation_state = None
        self.deviation_start_time = None
        self.continuous_deviation_duration = 0.0
        self.last_alert_time.clear()
