"""
DeskSense Multi-Signal Phone Usage Fusion Engine
Fuses phone object detection, hand proximity, and downward head pose
to prevent false positives and produce high-confidence estimated phone sessions.
Mandate: Results are always labeled as 'estimated phone usage', never exact.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable


@dataclass
class PhoneSession:
    start_time: str
    end_time: str
    duration: int  # in seconds
    confidence: float
    session_type: str = "estimated_phone_usage"
    label: str = "estimated phone usage"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "confidence": round(self.confidence, 3),
            "session_type": self.session_type,
            "label": self.label,
        }


@dataclass
class PhoneFusionConfig:
    start_threshold_seconds: float = 2.5
    end_threshold_seconds: float = 3.0
    min_detection_confidence: float = 0.5
    focus_mode_start_threshold: float = 1.0


class PhoneUsageFusion:
    """
    Multi-signal fusion engine for phone usage detection.
    Requires phone detection + secondary evidence (downward head pose and/or hand interaction)
    sustained over a temporal window to start an estimated phone session.
    """

    def __init__(
        self,
        config: Optional[PhoneFusionConfig] = None,
        on_session_closed: Optional[Callable[[PhoneSession], None]] = None,
    ):
        self.config = config or PhoneFusionConfig()
        self.on_session_closed = on_session_closed

        self._normal_start_threshold = self.config.start_threshold_seconds
        self._active_start_threshold = self._normal_start_threshold

        # Internal tracking state
        self.is_phone_active: bool = False
        self.candidate_start_time: Optional[float] = None
        self.current_session_start_time: Optional[float] = None
        self.last_candidate_true_time: Optional[float] = None
        self.candidate_confidences: List[float] = []

        # Completed sessions
        self.completed_sessions: List[PhoneSession] = []

    def set_focus_mode_sensitivity(self, enabled: bool) -> None:
        """Increases phone detection sensitivity during manual focus mode."""
        if enabled:
            self._active_start_threshold = self.config.focus_mode_start_threshold
        else:
            self._active_start_threshold = self._normal_start_threshold

    @property
    def active_start_threshold(self) -> float:
        return self._active_start_threshold

    def process_frame(
        self,
        timestamp: float,
        phone_detected: bool,
        phone_confidence: float = 0.0,
        head_down: bool = False,
        hand_near_phone: bool = False,
        present: bool = True,
    ) -> bool:
        """
        Ingests a frame's signals and updates phone session state.
        Returns True if phone usage is currently active (sustained), False otherwise.
        """
        # Determine whether this instant satisfies fused candidate criteria
        is_candidate = False
        if present and phone_detected and phone_confidence >= self.config.min_detection_confidence:
            # Secondary evidence required: downward head orientation or active hand manipulation
            # Holding phone on table with no hand or looking straight ahead does not count
            if head_down or (hand_near_phone and head_down):
                is_candidate = True
            elif hand_near_phone and head_down:
                is_candidate = True
            elif hand_near_phone and not head_down:
                # Holding phone while looking at screen does not count as active phone use
                is_candidate = False

        if is_candidate:
            self.candidate_confidences.append(phone_confidence)
            self.last_candidate_true_time = timestamp

            if self.candidate_start_time is None:
                self.candidate_start_time = timestamp

            # Check if candidate condition has persisted long enough to start session
            if not self.is_phone_active:
                elapsed = timestamp - self.candidate_start_time
                if elapsed >= self._active_start_threshold:
                    self.is_phone_active = True
                    self.current_session_start_time = self.candidate_start_time
        else:
            # Candidate condition is false for this frame
            if self.is_phone_active:
                # We are in an active session. Check debounce threshold
                time_since_last_true = timestamp - (self.last_candidate_true_time or timestamp)
                if time_since_last_true >= self.config.end_threshold_seconds:
                    # Session ended
                    self._close_session(timestamp)
            else:
                # Not active; reset candidate window if lost
                self.candidate_start_time = None
                self.candidate_confidences.clear()

        return self.is_phone_active

    def _close_session(self, current_time: float) -> Optional[PhoneSession]:
        """Closes the current active session and creates a PhoneSession record."""
        if not self.is_phone_active or self.current_session_start_time is None:
            return None

        end_time_ts = self.last_candidate_true_time or current_time
        start_time_ts = self.current_session_start_time
        duration = max(1, int(round(end_time_ts - start_time_ts)))

        avg_confidence = (
            float(sum(self.candidate_confidences) / len(self.candidate_confidences))
            if self.candidate_confidences
            else 0.8
        )

        import datetime
        start_iso = datetime.datetime.fromtimestamp(start_time_ts).isoformat()
        end_iso = datetime.datetime.fromtimestamp(end_time_ts).isoformat()

        session = PhoneSession(
            start_time=start_iso,
            end_time=end_iso,
            duration=duration,
            confidence=avg_confidence,
            session_type="estimated_phone_usage",
            label="estimated phone usage",
        )

        self.completed_sessions.append(session)
        if self.on_session_closed:
            self.on_session_closed(session)

        # Reset active state
        self.is_phone_active = False
        self.candidate_start_time = None
        self.current_session_start_time = None
        self.last_candidate_true_time = None
        self.candidate_confidences.clear()

        return session

    def flush(self, current_time: float) -> Optional[PhoneSession]:
        """Forces closure of any active session (e.g. at shutdown or day close)."""
        if self.is_phone_active:
            return self._close_session(current_time)
        return None

    def get_estimated_phone_usage_stats(self) -> Dict[str, Any]:
        """Returns aggregate phone statistics with explicit estimated wording."""
        total_seconds = sum(s.duration for s in self.completed_sessions)
        count = len(self.completed_sessions)
        longest = max((s.duration for s in self.completed_sessions), default=0)
        avg = int(round(total_seconds / count)) if count > 0 else 0

        return {
            "estimated_phone_usage": total_seconds,
            "estimated_sessions": count,
            "longest_session": longest,
            "average_session": avg,
            "wording": "estimated phone usage",
        }
