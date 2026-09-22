"""
DeskSense Frame Scheduler & Rate Limiter
Enforces target FPS (5-10 FPS) from higher-frequency camera input (e.g. 30 FPS),
provides adaptive throttle hooks, and guarantees bounded queue size and immediate frame disposal.
"""

import time
from typing import Callable, Optional, Any
import numpy as np

class FrameScheduler:
    def __init__(self, target_fps: int = 5, max_queue_size: int = 1):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / max(1, target_fps)
        self.max_queue_size = max_queue_size
        self.last_dispatched_time = 0.0
        
        # Bounded single-item or zero-item slot (no accumulating queue)
        self._current_frame: Optional[np.ndarray] = None
        self.dispatched_count = 0
        self.skipped_count = 0

    def set_target_fps(self, new_fps: int):
        """Adaptive throttle hook to adjust frame rate without restarting."""
        self.target_fps = max(1, min(30, new_fps))
        self.frame_interval = 1.0 / self.target_fps

    def submit_frame(self, frame: np.ndarray, current_time: Optional[float] = None) -> bool:
        """
        Accept incoming camera frame.
        If frame_interval has elapsed, accepts frame for dispatch.
        Otherwise skips/drops frame to avoid queue buildup and excessive CPU work.
        """
        now = current_time if current_time is not None else time.time()
        
        # Check if interval has elapsed since last dispatched frame
        if (now - self.last_dispatched_time) >= self.frame_interval:
            # Dispose of any lingering frame
            if self._current_frame is not None:
                del self._current_frame
            self._current_frame = frame
            self.last_dispatched_time = now
            self.dispatched_count += 1
            return True
        else:
            # Drop frame immediately
            self.skipped_count += 1
            del frame
            return False

    def process_next(self, processor_fn: Callable[[np.ndarray], Any]) -> Optional[Any]:
        """Processes and immediately releases the current frame."""
        if self._current_frame is None:
            return None

        frame = self._current_frame
        self._current_frame = None  # Remove reference before execution
        try:
            result = processor_fn(frame)
            return result
        finally:
            del frame  # Strict zero retention

    @property
    def queue_size(self) -> int:
        return 1 if self._current_frame is not None else 0
