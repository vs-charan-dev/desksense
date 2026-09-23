"""
DeskSense Adaptive Phone Inference Scheduler
Regulates object detection frequency to prevent unnecessary CPU load.
Default: 0.5–1 FPS.
Burst: 2 FPS triggered by downward head orientation / pitch.
"""

import time
from typing import Optional


class PhoneInferenceScheduler:
    """
    Schedules phone inference based on head pose suspicion.
    """

    def __init__(
        self,
        default_fps: float = 0.5,
        burst_fps: float = 2.0,
    ):
        self.default_fps = max(0.1, min(default_fps, 5.0))
        self.burst_fps = max(self.default_fps, min(burst_fps, 5.0))
        self.last_inference_time: float = -1.0
        self.is_burst_mode: bool = False

    @property
    def current_target_fps(self) -> float:
        return self.burst_fps if self.is_burst_mode else self.default_fps

    @property
    def current_interval(self) -> float:
        return 1.0 / self.current_target_fps

    def update_suspicion(
        self,
        attention: Optional[str] = None,
        head_down: bool = False,
        pitch: Optional[float] = None,
        downward_threshold: float = -10.0,
    ) -> bool:
        """
        Updates suspicion state based on downward orientation evidence.
        Returns whether burst mode is active.
        """
        is_down = False
        if head_down:
            is_down = True
        elif attention is not None:
            if isinstance(attention, str) and attention.strip().upper() == "DOWN":
                is_down = True
        elif pitch is not None and pitch < downward_threshold:
            is_down = True

        self.is_burst_mode = is_down
        return self.is_burst_mode

    def should_infer(self, current_time: Optional[float] = None) -> bool:
        """
        Determines whether phone inference should run on the current frame.
        If True is returned, advances the internal last_inference_time.
        """
        now = time.time() if current_time is None else current_time
        if self.last_inference_time < 0.0:
            self.last_inference_time = now
            return True

        interval = self.current_interval
        # Allow small floating epsilon (1e-4) for exact tick boundaries
        if (now - self.last_inference_time) >= (interval - 1e-4):
            self.last_inference_time = now
            return True

        return False

    def reset(self) -> None:
        self.last_inference_time = -1.0
        self.is_burst_mode = False
