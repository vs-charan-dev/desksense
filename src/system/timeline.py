"""Interactive Day Timeline Generator for DeskSense (Phase 5).
Maps raw and downsampled events into ordered, non-overlapping visual segments
representing Work, Phone, Away, Break, and Idle.
Resolves overlapping raw events according to state priority without double-counting.
Converts unexplained gaps into neutral 'UNMONITORED' time.
Provides immutable scrubbing and tooltip inspection metadata.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import datetime
from src.system.work_state import WorkState


STATE_PRIORITY: Dict[str, int] = {
    # Higher number = higher precedence during overlap resolution
    WorkState.PHONE_USAGE.value: 100,
    WorkState.BREAK.value: 90,
    WorkState.AWAY.value: 80,
    WorkState.DISTRACTED.value: 70,
    WorkState.IDLE.value: 60,
    WorkState.FOCUSED_WORK.value: 50,
    WorkState.ACTIVE_WORK.value: 40,
    WorkState.UNKNOWN.value: 10,
    "UNMONITORED": 0,
}

STATE_DISPLAY_INFO: Dict[str, Dict[str, str]] = {
    WorkState.FOCUSED_WORK.value: {"label": "Deep Focus", "color": "#10b981", "category": "work"},
    WorkState.ACTIVE_WORK.value: {"label": "Active Work", "color": "#3b82f6", "category": "work"},
    WorkState.PHONE_USAGE.value: {"label": "Phone (Estimated)", "color": "#f59e0b", "category": "phone"},
    WorkState.BREAK.value: {"label": "Break", "color": "#8b5cf6", "category": "break"},
    WorkState.AWAY.value: {"label": "Away", "color": "#64748b", "category": "away"},
    WorkState.IDLE.value: {"label": "Idle", "color": "#94a3b8", "category": "idle"},
    WorkState.DISTRACTED.value: {"label": "Distracted", "color": "#ef4444", "category": "distraction"},
    WorkState.UNKNOWN.value: {"label": "Unknown", "color": "#475569", "category": "unknown"},
    "UNMONITORED": {"label": "Unmonitored", "color": "#334155", "category": "unmonitored"},
}


@dataclass(frozen=True)
class TimelineSegment:
    """An immutable timeline segment representing a discrete period in time."""
    start_time: float
    end_time: float
    duration: float
    state: str
    label: str
    color: str
    category: str

    def to_dict(self) -> Dict[str, Any]:
        st_iso = datetime.datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S")
        et_iso = datetime.datetime.fromtimestamp(self.end_time).strftime("%H:%M:%S")
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_time_str": st_iso,
            "end_time_str": et_iso,
            "duration": self.duration,
            "state": self.state,
            "label": self.label,
            "color": self.color,
            "category": self.category,
        }


class TimelineBuilder:
    """Constructs a seamless, non-overlapping day timeline from event intervals."""

    def __init__(self, day_start: Optional[float] = None, day_end: Optional[float] = None):
        self.day_start = day_start
        self.day_end = day_end

    @staticmethod
    def resolve_overlaps(raw_intervals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes raw intervals that might overlap, slices them at boundary points,
        and assigns each non-overlapping slice to the highest-priority state.
        Guarantees zero double-counting.
        """
        if not raw_intervals:
            return []

        # Find all boundary time points
        points = set()
        for item in raw_intervals:
            st = float(item["start_time"])
            et = float(item["end_time"])
            if et > st:
                points.add(st)
                points.add(et)

        sorted_points = sorted(points)
        if len(sorted_points) < 2:
            return []

        resolved_slices = []
        for i in range(len(sorted_points) - 1):
            t0 = sorted_points[i]
            t1 = sorted_points[i + 1]
            if t1 <= t0:
                continue

            # Find all intervals active during [t0, t1]
            matching = [
                item for item in raw_intervals
                if float(item["start_time"]) <= t0 and float(item["end_time"]) >= t1
            ]

            if not matching:
                continue

            # Pick the state with the highest priority
            winner = max(matching, key=lambda m: STATE_PRIORITY.get(m["state"], 0))
            resolved_slices.append({
                "start_time": t0,
                "end_time": t1,
                "state": winner["state"],
            })

        # Merge adjacent slices with identical states
        merged: List[Dict[str, Any]] = []
        for s in resolved_slices:
            if not merged:
                merged.append(dict(s))
            else:
                last = merged[-1]
                if last["state"] == s["state"] and abs(last["end_time"] - s["start_time"]) < 1e-4:
                    last["end_time"] = s["end_time"]
                else:
                    merged.append(dict(s))

        return merged

    @staticmethod
    def fill_gaps(
        resolved_intervals: List[Dict[str, Any]],
        overall_start: Optional[float] = None,
        overall_end: Optional[float] = None,
        gap_state: str = "UNMONITORED",
    ) -> List[Dict[str, Any]]:
        """Fills gaps between monitored intervals with `gap_state`."""
        if not resolved_intervals:
            if overall_start is not None and overall_end is not None and overall_end > overall_start:
                return [{
                    "start_time": overall_start,
                    "end_time": overall_end,
                    "state": gap_state,
                }]
            return []

        result: List[Dict[str, Any]] = []
        first_start = resolved_intervals[0]["start_time"]

        # Leading gap
        if overall_start is not None and first_start > overall_start:
            result.append({
                "start_time": overall_start,
                "end_time": first_start,
                "state": gap_state,
            })

        # Intermediate gaps
        for i in range(len(resolved_intervals)):
            current = resolved_intervals[i]
            if result:
                last_end = result[-1]["end_time"]
                if current["start_time"] > last_end + 1e-4:
                    result.append({
                        "start_time": last_end,
                        "end_time": current["start_time"],
                        "state": gap_state,
                    })
            result.append(dict(current))

        # Trailing gap
        last_end = result[-1]["end_time"]
        if overall_end is not None and overall_end > last_end:
            result.append({
                "start_time": last_end,
                "end_time": overall_end,
                "state": gap_state,
            })

        return result

    def build_timeline(
        self,
        raw_intervals: List[Dict[str, Any]],
        day_start: Optional[float] = None,
        day_end: Optional[float] = None,
    ) -> List[TimelineSegment]:
        """
        Creates full list of formatted immutable TimelineSegments.
        """
        t_start = day_start or self.day_start
        t_end = day_end or self.day_end

        # Resolve overlaps first
        resolved = self.resolve_overlaps(raw_intervals)

        # Fill gaps
        full_seq = self.fill_gaps(resolved, overall_start=t_start, overall_end=t_end)

        # Convert to immutable TimelineSegment
        segments: List[TimelineSegment] = []
        for item in full_seq:
            st = float(item["start_time"])
            et = float(item["end_time"])
            dur = max(0.0, et - st)
            st_name = item["state"]
            info = STATE_DISPLAY_INFO.get(st_name, {
                "label": st_name,
                "color": "#64748b",
                "category": "unknown",
            })

            segments.append(
                TimelineSegment(
                    start_time=st,
                    end_time=et,
                    duration=dur,
                    state=st_name,
                    label=info["label"],
                    color=info["color"],
                    category=info["category"],
                )
            )

        return segments
