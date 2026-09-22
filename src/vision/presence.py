"""
DeskSense Presence Engine (Phase 1 Module 1)
Handles presence detection, quality validation, and absence hysteresis.
Conforms strictly to P1-01, P1-02, P1-03, P1-04 test specifications.
"""

import time
from typing import Optional, Dict, Any, Tuple

class PresenceEngine:
    def __init__(
        self,
        absence_hysteresis_sec: float = 15.0,
        min_confidence: float = 0.35,
        time_func = None
    ):
        """
        :param absence_hysteresis_sec: Seconds of continuous missing person before switching from PRESENT to AWAY.
        :param min_confidence: Minimum landmark/presence confidence score to treat as detected.
        :param time_func: Callable returning epoch seconds (allows deterministic fake clock for tests).
        """
        self.absence_hysteresis_sec = absence_hysteresis_sec
        self.min_confidence = min_confidence
        self.time_func = time_func or time.time

        self.current_state: str = "UNKNOWN"
        self.last_seen_time: Optional[float] = None
        self.last_evaluated_time: Optional[float] = None
        self.continuous_missing_duration: float = 0.0

    def update(
        self,
        raw_presence_candidate: Optional[str],
        confidence: float = 0.0,
        camera_available: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Update presence state given raw frame observation.
        
        :param raw_presence_candidate: "PRESENT", "AWAY", or None/unreliable
        :param confidence: Landmark detection visibility or model confidence [0.0, 1.0]
        :param camera_available: Whether camera feed is actively providing valid frames
        :return: (filtered_state, diagnostics_dict)
        """
        now = self.time_func()
        self.last_evaluated_time = now

        # P1-04: Camera unavailable, None input, or low-confidence produces UNKNOWN
        if not camera_available or raw_presence_candidate is None:
            self.current_state = "UNKNOWN"
            return "UNKNOWN", {
                "state": "UNKNOWN",
                "reason": "camera_unavailable_or_no_input",
                "missing_sec": self.continuous_missing_duration
            }

        if confidence < self.min_confidence:
            # Unreliable low confidence
            if self.current_state == "UNKNOWN":
                return "UNKNOWN", {
                    "state": "UNKNOWN",
                    "reason": "low_confidence",
                    "confidence": confidence
                }
            # If previously PRESENT, treat low confidence as potential missing candidate to evaluate hysteresis
            raw_presence_candidate = "AWAY"

        # P1-01 & P1-03: Valid face/body produces PRESENT immediately
        if raw_presence_candidate == "PRESENT" and confidence >= self.min_confidence:
            self.current_state = "PRESENT"
            self.last_seen_time = now
            self.continuous_missing_duration = 0.0
            return "PRESENT", {
                "state": "PRESENT",
                "confidence": confidence,
                "missing_sec": 0.0
            }

        # P1-02: Absence hysteresis
        # Person is missing in this frame
        if self.last_seen_time is not None:
            self.continuous_missing_duration = max(0.0, now - self.last_seen_time)
        else:
            self.continuous_missing_duration += 1.0

        if self.current_state == "PRESENT":
            # Only transition to AWAY if continuous missing duration exceeds threshold
            if self.continuous_missing_duration > self.absence_hysteresis_sec:
                self.current_state = "AWAY"
        elif self.current_state == "UNKNOWN":
            # If initial state was UNKNOWN and person is clearly missing with camera available
            if self.continuous_missing_duration > self.absence_hysteresis_sec:
                self.current_state = "AWAY"
            else:
                self.current_state = "UNKNOWN"

        return self.current_state, {
            "state": self.current_state,
            "raw_candidate": raw_presence_candidate,
            "missing_sec": round(self.continuous_missing_duration, 2),
            "hysteresis_sec": self.absence_hysteresis_sec
        }

    def reset(self):
        """Reset internal hysteresis timers."""
        self.current_state = "UNKNOWN"
        self.last_seen_time = None
        self.last_evaluated_time = None
        self.continuous_missing_duration = 0.0
