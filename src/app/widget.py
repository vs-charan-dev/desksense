"""
DeskSense Live Status Widget State (Phase 3 Module 4)
Manages floating overlay pill state: position, opacity, collapse, and visibility.
Conforms strictly to P3-11 test specification:
- Application works fully when optional overlay is disabled
- If enabled, widget can be dragged, collapsed, and hidden without affecting monitoring
"""

from typing import Dict, Any


class StatusWidgetState:
    def __init__(
        self,
        enabled: bool = False,
        visible: bool = False,
        x: int = 100,
        y: int = 100,
        opacity: float = 0.9,
        collapsed: bool = False,
        always_on_top: bool = True
    ):
        self.enabled = enabled
        self.visible = visible
        self.x = x
        self.y = y
        self.opacity = max(0.1, min(1.0, opacity))
        self.collapsed = collapsed
        self.always_on_top = always_on_top

    def set_position(self, x: int, y: int) -> None:
        """Drag update."""
        self.x = int(x)
        self.y = int(y)

    def set_opacity(self, opacity: float) -> None:
        """Opacity update clamped 0.1 to 1.0."""
        self.opacity = max(0.1, min(1.0, float(opacity)))

    def toggle_collapse(self) -> bool:
        """Toggles collapsed/pill mode."""
        self.collapsed = not self.collapsed
        return self.collapsed

    def show(self) -> None:
        if self.enabled:
            self.visible = True

    def hide(self) -> None:
        self.visible = False

    def enable(self) -> None:
        self.enabled = True
        self.visible = True

    def disable(self) -> None:
        self.enabled = False
        self.visible = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "visible": self.visible,
            "x": self.x,
            "y": self.y,
            "opacity": round(self.opacity, 2),
            "collapsed": self.collapsed,
            "always_on_top": self.always_on_top
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatusWidgetState":
        return cls(
            enabled=data.get("enabled", False),
            visible=data.get("visible", False),
            x=data.get("x", 100),
            y=data.get("y", 100),
            opacity=data.get("opacity", 0.9),
            collapsed=data.get("collapsed", False),
            always_on_top=data.get("always_on_top", True)
        )
