"""
DeskSense Break Intelligence & Sedentary Reminder System
Detects sustained desk departures, tracks automatic breaks,
and issues sedentary reminders after 60 continuous seated minutes.
"""

import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable


@dataclass
class BreakRecord:
    start_time: str
    end_time: str
    duration: int  # in seconds
    break_type: str = "automatic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "break_type": self.break_type,
        }


class BreakTracker:
    """
    Tracks desk departures and converts sustained absences into breaks.
    Monitors continuous seated duration and requests sedentary reminders.
    """

    def __init__(
        self,
        break_threshold_seconds: float = 120.0,
        qualifying_break_reset_seconds: float = 120.0,
        sedentary_limit_seconds: float = 3600.0,  # 60 minutes
        on_break_completed: Optional[Callable[[BreakRecord], None]] = None,
        on_sedentary_reminder: Optional[Callable[[], None]] = None,
    ):
        self.break_threshold_seconds = break_threshold_seconds
        self.qualifying_break_reset_seconds = qualifying_break_reset_seconds
        self.sedentary_limit_seconds = sedentary_limit_seconds
        self.on_break_completed = on_break_completed
        self.on_sedentary_reminder = on_sedentary_reminder

        # State tracking
        self.is_present: bool = True
        self.absence_start_time: Optional[float] = None
        self.continuous_seated_seconds: float = 0.0
        self.last_update_time: Optional[float] = None
        self.sedentary_alerted: bool = False

        # Active break status
        self.break_active: bool = False
        self.active_break_start: Optional[float] = None

        self.completed_breaks: List[BreakRecord] = []

    def update(self, timestamp: float, present: bool) -> Optional[BreakRecord]:
        """
        Updates presence state at the given timestamp.
        Returns a BreakRecord if a break was just completed upon user return.
        """
        dt = (timestamp - self.last_update_time) if self.last_update_time is not None else 0.0
        if dt < 0:
            dt = 0.0
        self.last_update_time = timestamp

        completed_break: Optional[BreakRecord] = None

        if not present:
            # User is absent
            if self.is_present:
                # Just departed
                self.is_present = False
                self.absence_start_time = timestamp

            absence_duration = timestamp - (self.absence_start_time or timestamp)
            if absence_duration >= self.break_threshold_seconds and not self.break_active:
                # Qualifying break initiated
                self.break_active = True
                self.active_break_start = self.absence_start_time
        else:
            # User is present
            if not self.is_present:
                # Just returned
                return_time = timestamp
                absence_start = self.absence_start_time or timestamp
                absence_duration = return_time - absence_start

                if self.break_active or absence_duration >= self.break_threshold_seconds:
                    # Break completed
                    dur_int = max(1, int(round(absence_duration)))
                    import datetime
                    start_iso = datetime.datetime.fromtimestamp(absence_start).isoformat()
                    end_iso = datetime.datetime.fromtimestamp(return_time).isoformat()

                    completed_break = BreakRecord(
                        start_time=start_iso,
                        end_time=end_iso,
                        duration=dur_int,
                        break_type="automatic",
                    )
                    self.completed_breaks.append(completed_break)
                    if self.on_break_completed:
                        self.on_break_completed(completed_break)

                # If absence was a qualifying break, reset sedentary timer
                if absence_duration >= self.qualifying_break_reset_seconds:
                    self.continuous_seated_seconds = 0.0
                    self.sedentary_alerted = False

                self.is_present = True
                self.absence_start_time = None
                self.break_active = False
                self.active_break_start = None
            else:
                # Continuous presence: accumulate seated duration
                self.continuous_seated_seconds += dt

                # Check sedentary limit (> 60 minutes uninterrupted)
                if self.continuous_seated_seconds >= self.sedentary_limit_seconds and not self.sedentary_alerted:
                    self.sedentary_alerted = True
                    if self.on_sedentary_reminder:
                        self.on_sedentary_reminder()

        return completed_break

    def get_summary(self) -> Dict[str, Any]:
        total_seconds = sum(b.duration for b in self.completed_breaks)
        count = len(self.completed_breaks)
        return {
            "break_count": count,
            "total_break_seconds": total_seconds,
            "continuous_seated_seconds": int(round(self.continuous_seated_seconds)),
        }
