"""Automatic Focus Session Tracker for DeskSense (Phase 5).
Tracks deep-focus sessions automatically from work state transitions,
app activity, and user presence.
Handles focus boundaries: productive work starts/extends a session;
phone, away, idle, or qualifying distraction closes it at the exact timestamp.
Computes focus totals: deep-focus time, session count, longest session, average session, and distraction count.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import datetime
from src.system.work_state import WorkState
from src.storage.db import DatabaseEngine


@dataclass
class FocusSession:
    start_time: float
    end_time: float
    duration: int
    distraction_count: int = 0
    interrupted_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "distraction_count": self.distraction_count,
            "interrupted_by": self.interrupted_by,
        }


class FocusTracker:
    """
    Monitors work state and active tasks to delineate continuous focus blocks.
    Minimum threshold for a qualifying focus session can be configured (e.g., >= 60 seconds).
    """

    def __init__(self, db: Optional[DatabaseEngine] = None, min_qualifying_seconds: int = 0):
        self.db = db
        self.min_qualifying_seconds = min_qualifying_seconds
        self.active_session_start: Optional[float] = None
        self.completed_sessions: List[FocusSession] = []
        self.total_distraction_count: int = 0
        self.session_distraction_count: int = 0

    @property
    def in_focus(self) -> bool:
        return self.active_session_start is not None

    def update(self, timestamp: float, work_state: WorkState) -> Optional[FocusSession]:
        """
        Updates the tracker with the current work state at `timestamp`.
        Returns a closed FocusSession if a session just ended.
        """
        is_focus_state = (work_state == WorkState.FOCUSED_WORK)

        if is_focus_state:
            if self.active_session_start is None:
                # Start new focus session
                self.active_session_start = timestamp
                self.session_distraction_count = 0
            return None
        else:
            # Non-focus state: if we had an active session, close it now
            if self.active_session_start is not None:
                dur = max(0, int(round(timestamp - self.active_session_start)))
                interrupted_by = work_state.value
                
                # Count distraction if interrupted by phone or distraction
                if work_state in (WorkState.PHONE_USAGE, WorkState.DISTRACTED):
                    self.total_distraction_count += 1
                    self.session_distraction_count += 1

                session = FocusSession(
                    start_time=self.active_session_start,
                    end_time=timestamp,
                    duration=dur,
                    distraction_count=self.session_distraction_count,
                    interrupted_by=interrupted_by,
                )
                self.active_session_start = None
                self.session_distraction_count = 0

                if dur >= self.min_qualifying_seconds:
                    self.completed_sessions.append(session)
                    return session
            elif work_state in (WorkState.PHONE_USAGE, WorkState.DISTRACTED):
                # Count distraction even outside an active focus session if qualifying
                self.total_distraction_count += 1

            return None

    def close_active(self, timestamp: float, reason: str = "END_OF_DAY") -> Optional[FocusSession]:
        """Forces closure of any currently active focus session."""
        if self.active_session_start is not None:
            dur = max(0, int(round(timestamp - self.active_session_start)))
            session = FocusSession(
                start_time=self.active_session_start,
                end_time=timestamp,
                duration=dur,
                distraction_count=self.session_distraction_count,
                interrupted_by=reason,
            )
            self.active_session_start = None
            self.session_distraction_count = 0
            if dur >= self.min_qualifying_seconds:
                self.completed_sessions.append(session)
                return session
        return None

    def get_focus_totals(self) -> Dict[str, Any]:
        """
        Returns exact focus totals:
        - total_focus_time (seconds)
        - session_count
        - longest_session (seconds)
        - average_session (seconds)
        - distraction_count
        """
        sessions = self.completed_sessions
        count = len(sessions)
        total_time = sum(s.duration for s in sessions)
        longest = max((s.duration for s in sessions), default=0)
        avg = int(round(total_time / count)) if count > 0 else 0

        return {
            "total_focus_time": total_time,
            "session_count": count,
            "longest_session": longest,
            "average_session": avg,
            "distraction_count": self.total_distraction_count,
            "sessions": [s.to_dict() for s in sessions],
        }

    @staticmethod
    def calculate_totals_from_intervals(
        intervals: List[Dict[str, Any]],
        phone_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Utility to calculate focus totals from raw or stored work state intervals.
        Considers FOCUSED_WORK intervals as focus sessions.
        """
        focus_intervals = [i for i in intervals if i.get("state") == WorkState.FOCUSED_WORK.value or i.get("state") == "FOCUSED_WORK"]
        distraction_intervals = [i for i in intervals if i.get("state") in (WorkState.DISTRACTED.value, "DISTRACTED", WorkState.PHONE_USAGE.value, "PHONE_USAGE")]
        
        total_time = sum(int(i.get("duration", 0)) for i in focus_intervals)
        count = len(focus_intervals)
        longest = max((int(i.get("duration", 0)) for i in focus_intervals), default=0)
        avg = int(round(total_time / count)) if count > 0 else 0
        distractions = max(len(distraction_intervals), phone_count)

        return {
            "total_focus_time": total_time,
            "session_count": count,
            "longest_session": longest,
            "average_session": avg,
            "distraction_count": distractions,
        }
