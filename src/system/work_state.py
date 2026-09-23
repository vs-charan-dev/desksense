"""
DeskSense Work State Engine
Synthesizes vision, input, and app context into unified behavioral states:
FOCUSED_WORK, ACTIVE_WORK, DISTRACTED, PHONE_USAGE, IDLE, AWAY, BREAK, UNKNOWN.
Maintains non-overlapping state intervals with rigorous accounting.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable


class WorkState(str, Enum):
    FOCUSED_WORK = "FOCUSED_WORK"
    ACTIVE_WORK = "ACTIVE_WORK"
    DISTRACTED = "DISTRACTED"
    PHONE_USAGE = "PHONE_USAGE"
    IDLE = "IDLE"
    AWAY = "AWAY"
    BREAK = "BREAK"
    UNKNOWN = "UNKNOWN"


@dataclass
class WorkStateInterval:
    state: WorkState
    start_time: float
    end_time: float
    duration: int  # in seconds

    def to_dict(self) -> Dict[str, Any]:
        import datetime
        return {
            "state": self.state.value,
            "start_time": datetime.datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.datetime.fromtimestamp(self.end_time).isoformat(),
            "duration": self.duration,
        }


@dataclass
class WorkStateConfig:
    idle_threshold_seconds: float = 60.0
    absence_away_threshold: float = 15.0
    absence_break_threshold: float = 120.0
    lookaway_distraction_threshold: float = 15.0


class WorkStateEngine:
    """
    Prioritized state engine mapping multi-modal inputs to mutually exclusive work states.
    Guarantees non-overlapping intervals and exact duration conservation.
    """

    def __init__(
        self,
        config: Optional[WorkStateConfig] = None,
        on_state_change: Optional[Callable[[WorkState, WorkState, float], None]] = None,
    ):
        self.config = config or WorkStateConfig()
        self.on_state_change = on_state_change

        self.current_state: WorkState = WorkState.UNKNOWN
        self.current_interval_start: Optional[float] = None
        self.last_update_time: Optional[float] = None

        # Sub-trackers for persistence conditions
        self.absent_since: Optional[float] = None
        self.lookaway_since: Optional[float] = None

        self.intervals: List[WorkStateInterval] = []

    def classify_state(
        self,
        timestamp: float,
        present: Optional[bool] = None,
        attention: Optional[str] = None,
        app_category: Optional[str] = "neutral",
        idle_seconds: Optional[float] = 0.0,
        phone_active: bool = False,
        signals_reliable: bool = True,
    ) -> WorkState:
        """
        Pure state classification based on instantaneous and tracking signals.
        """
        if not signals_reliable or present is None:
            return WorkState.UNKNOWN

        # Handle Absence
        if not present:
            if self.absent_since is None:
                self.absent_since = timestamp
            absent_duration = timestamp - self.absent_since
            if absent_duration >= self.config.absence_break_threshold:
                return WorkState.BREAK
            elif absent_duration >= self.config.absence_away_threshold:
                return WorkState.AWAY
            else:
                # Grace period before declaring away
                return WorkState.AWAY
        else:
            self.absent_since = None

        # User is present. Check Phone Usage first (phone overrides computer work)
        if phone_active:
            return WorkState.PHONE_USAGE

        # Check Idle (present but no computer input)
        if idle_seconds is not None and idle_seconds >= self.config.idle_threshold_seconds:
            return WorkState.IDLE

        # Check Attention for prolonged look-away
        att_norm = (attention or "").strip().upper()
        if att_norm and att_norm not in ("SCREEN", "UNKNOWN"):
            if self.lookaway_since is None:
                self.lookaway_since = timestamp
            if (timestamp - self.lookaway_since) >= self.config.lookaway_distraction_threshold:
                return WorkState.DISTRACTED
        else:
            self.lookaway_since = None

        # Check Application Category
        cat = (app_category or "").strip().lower()
        if cat in ("distracting", "entertainment", "non_productive", "social_media"):
            return WorkState.DISTRACTED

        # Check Focused Work vs Active Work
        if (att_norm == "SCREEN" or not att_norm) and cat == "productive":
            return WorkState.FOCUSED_WORK

        return WorkState.ACTIVE_WORK

    def update(
        self,
        timestamp: float,
        present: Optional[bool] = None,
        attention: Optional[str] = None,
        app_category: Optional[str] = "neutral",
        idle_seconds: Optional[float] = 0.0,
        phone_active: bool = False,
        signals_reliable: bool = True,
    ) -> WorkState:
        """
        Updates the engine with current signals, transitions state if needed,
        and maintains seamless interval records.
        """
        new_state = self.classify_state(
            timestamp=timestamp,
            present=present,
            attention=attention,
            app_category=app_category,
            idle_seconds=idle_seconds,
            phone_active=phone_active,
            signals_reliable=signals_reliable,
        )

        self.last_update_time = timestamp

        if self.current_interval_start is None:
            # First evaluation
            self.current_state = new_state
            self.current_interval_start = timestamp
            return self.current_state

        if new_state != self.current_state:
            # State transition: close previous interval at this exact timestamp
            prev_state = self.current_state
            duration = max(0, int(round(timestamp - self.current_interval_start)))
            if duration > 0:
                self.intervals.append(
                    WorkStateInterval(
                        state=prev_state,
                        start_time=self.current_interval_start,
                        end_time=timestamp,
                        duration=duration,
                    )
                )
            if self.on_state_change:
                self.on_state_change(prev_state, new_state, timestamp)

            self.current_state = new_state
            self.current_interval_start = timestamp

        return self.current_state

    def flush(self, timestamp: Optional[float] = None) -> Optional[WorkStateInterval]:
        """Closes the active interval at the given timestamp."""
        if self.current_interval_start is None:
            return None
        end_ts = timestamp or self.last_update_time or self.current_interval_start
        duration = max(0, int(round(end_ts - self.current_interval_start)))
        closed = None
        if duration > 0:
            closed = WorkStateInterval(
                state=self.current_state,
                start_time=self.current_interval_start,
                end_time=end_ts,
                duration=duration,
            )
            self.intervals.append(closed)

        self.current_interval_start = None
        return closed

    def get_summary(self) -> Dict[str, int]:
        """Returns total seconds spent in each work state."""
        summary = {s.value: 0 for s in WorkState}
        for interval in self.intervals:
            summary[interval.state.value] += interval.duration
        return summary
