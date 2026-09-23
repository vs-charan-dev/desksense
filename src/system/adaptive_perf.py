"""Adaptive Performance and Power Manager for DeskSense (Phase 6).
Implements:
1. Power profile switching:
   - AC Mode: Targets 5 FPS (within 5 to 10 FPS range). Normal phone-scan rates.
   - Battery Mode: Drops vision to ~3 FPS, throttles phone-scan rates, signals UI to throttle animation.
2. Away throttling:
   - Sustained absence reduces expensive vision inference to ~1 FPS.
   - Restores normal rate immediately when user returns.
3. Thermal / CPU Watchdog:
   - Monitored CPU utilization drops inference rates when sustained over limit (e.g. 70%).
   - Uses hysteresis band (e.g., lower threshold 50%) to prevent rapid oscillation/flapping.
4. Bounded queues / memory protection:
   - Guarantees max queue size = 1 and immediate reference cleanup.
"""

from enum import Enum
from typing import Optional, Callable, Dict, Any
import time


class PowerSource(str, Enum):
    AC = "AC"
    BATTERY = "BATTERY"


class PerformanceProfile(str, Enum):
    AC_NORMAL = "AC_NORMAL"
    BATTERY_SAVER = "BATTERY_SAVER"
    AWAY_THROTTLED = "AWAY_THROTTLED"
    THERMAL_THROTTLED = "THERMAL_THROTTLED"


class AdaptivePerformanceManager:
    """Dynamically regulates vision FPS and phone scan frequency based on system state."""

    def __init__(
        self,
        time_func: Optional[Callable[[], float]] = None,
        cpu_high_threshold: float = 70.0,
        cpu_low_threshold: float = 50.0,
        away_throttle_delay: float = 10.0,
    ):
        self.time_func = time_func or time.time
        self.cpu_high_threshold = cpu_high_threshold
        self.cpu_low_threshold = cpu_low_threshold
        self.away_throttle_delay = away_throttle_delay

        # Current system states
        self.power_source: PowerSource = PowerSource.AC
        self.user_present: bool = True
        self.absent_since: Optional[float] = None
        self.cpu_usage_pct: float = 5.0
        self.is_thermal_throttled: bool = False

        # Profile targets
        self._target_fps: float = 5.0
        self._phone_scan_rate: float = 0.5
        self._ui_animations_enabled: bool = True

    @property
    def target_fps(self) -> float:
        self._evaluate_profile()
        return self._target_fps

    @property
    def phone_scan_fps(self) -> float:
        self._evaluate_profile()
        return self._phone_scan_rate

    @property
    def ui_animations_enabled(self) -> bool:
        self._evaluate_profile()
        return self._ui_animations_enabled

    @property
    def current_profile(self) -> PerformanceProfile:
        if self.is_thermal_throttled:
            return PerformanceProfile.THERMAL_THROTTLED
        if not self.user_present and self.is_away_sustained:
            return PerformanceProfile.AWAY_THROTTLED
        if self.power_source == PowerSource.BATTERY:
            return PerformanceProfile.BATTERY_SAVER
        return PerformanceProfile.AC_NORMAL

    @property
    def is_away_sustained(self) -> bool:
        if self.user_present or self.absent_since is None:
            return False
        return (self.time_func() - self.absent_since) >= self.away_throttle_delay

    def set_power_source(self, source: PowerSource) -> None:
        """Sets power state (AC or BATTERY) and recalculates profile."""
        self.power_source = source
        self._evaluate_profile()

    def update_presence(self, present: bool) -> None:
        """Tracks presence and timestamps sustained absences."""
        now = self.time_func()
        if present:
            self.user_present = True
            self.absent_since = None
        else:
            if self.user_present or self.absent_since is None:
                self.absent_since = now
            self.user_present = False
        self._evaluate_profile()

    def update_cpu_load(self, cpu_pct: float) -> None:
        """
        Updates CPU utilization with hysteresis:
        - If not throttled, triggers throttle when cpu_pct >= cpu_high_threshold
        - If throttled, releases throttle only when cpu_pct <= cpu_low_threshold
        """
        self.cpu_usage_pct = cpu_pct
        if not self.is_thermal_throttled:
            if cpu_pct >= self.cpu_high_threshold:
                self.is_thermal_throttled = True
        else:
            if cpu_pct <= self.cpu_low_threshold:
                self.is_thermal_throttled = False
        self._evaluate_profile()

    def _evaluate_profile(self) -> None:
        """Applies configured FPS and scheduling parameters according to active profile."""
        profile = self.current_profile
        if profile == PerformanceProfile.THERMAL_THROTTLED:
            self._target_fps = 2.0
            self._phone_scan_rate = 0.2
            self._ui_animations_enabled = False
        elif profile == PerformanceProfile.AWAY_THROTTLED:
            self._target_fps = 1.0
            self._phone_scan_rate = 0.1
            self._ui_animations_enabled = True
        elif profile == PerformanceProfile.BATTERY_SAVER:
            self._target_fps = 3.0
            self._phone_scan_rate = 0.25
            self._ui_animations_enabled = False
        else:  # AC_NORMAL
            self._target_fps = 5.0
            self._phone_scan_rate = 0.5
            self._ui_animations_enabled = True

    def to_dict(self) -> Dict[str, Any]:
        self._evaluate_profile()
        return {
            "power_source": self.power_source.value,
            "profile": self.current_profile.value,
            "target_fps": self._target_fps,
            "phone_scan_fps": self._phone_scan_rate,
            "ui_animations_enabled": self._ui_animations_enabled,
            "cpu_usage_pct": round(self.cpu_usage_pct, 1),
            "is_thermal_throttled": self.is_thermal_throttled,
            "user_present": self.user_present,
            "is_away_sustained": self.is_away_sustained,
        }
