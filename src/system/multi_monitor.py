"""Multi-Monitor Workspace Configuration and Attention Adapter for DeskSense (Phase 6).
Allows users to configure multi-monitor setups (e.g., Center Laptop, Right External Monitor, Left External Monitor).
Adapts coarse attention states so looking towards configured monitor orientations
counts as screen focus ("SCREEN") rather than distraction/away.
Unconfigured orientations retain their natural attention classification (e.g. LEFT, RIGHT, AWAY).
"""

from typing import Set, Dict, List, Any, Optional
from enum import Enum


class MonitorPosition(str, Enum):
    CENTER = "CENTER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"


class MultiMonitorConfig:
    """Manages workspace monitor layout and attention direction mapping."""

    def __init__(self, secondary_monitors: Optional[List[str]] = None):
        # Center is always the primary display containing the camera
        self.monitors: Set[str] = {MonitorPosition.CENTER.value}
        if secondary_monitors:
            for m in secondary_monitors:
                norm = m.strip().upper()
                if norm in MonitorPosition.__members__:
                    self.monitors.add(norm)

    def add_monitor(self, position: str) -> bool:
        norm = position.strip().upper()
        if norm in MonitorPosition.__members__:
            self.monitors.add(norm)
            return True
        return False

    def remove_monitor(self, position: str) -> bool:
        norm = position.strip().upper()
        if norm == MonitorPosition.CENTER.value:
            return False  # Center cannot be removed
        if norm in self.monitors:
            self.monitors.remove(norm)
            return True
        return False

    def is_monitor_configured(self, position: str) -> bool:
        return position.strip().upper() in self.monitors

    def adapt_attention(self, raw_attention: str) -> str:
        """
        Translates raw attention (SCREEN, LEFT, RIGHT, DOWN, AWAY, UNKNOWN) into effective attention.
        If user looks LEFT and a LEFT monitor is configured, translates to 'SCREEN'.
        If user looks RIGHT and a RIGHT monitor is configured, translates to 'SCREEN'.
        Unconfigured directions (or DOWN/AWAY) remain untouched.
        """
        att = (raw_attention or "").strip().upper()
        if att in ("SCREEN", "UNKNOWN", "DOWN", "AWAY"):
            return att

        if att in self.monitors:
            return "SCREEN"

        return att

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitors": sorted(list(self.monitors)),
            "has_left": MonitorPosition.LEFT.value in self.monitors,
            "has_right": MonitorPosition.RIGHT.value in self.monitors,
            "has_up": MonitorPosition.UP.value in self.monitors,
        }
