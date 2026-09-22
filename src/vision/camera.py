"""
DeskSense Camera Manager
Manages webcam capture constrained to 640x480 resolution at 5-10 FPS.
Supports mock/synthetic frame generation for headless profiling and testing.
Strictly adheres to in-memory processing with immediate frame disposal.
"""

import time
import subprocess
import json
from typing import Tuple, Optional, List, Dict
import numpy as np
import cv2

def find_preferred_camera_index(
    preferred_keywords: Tuple[str, ...] = ("integrated", "internal", "built-in", "facetime"),
    exclude_keywords: Tuple[str, ...] = ("smart connect", "virtual", "droidcam", "obs", "iriun")
) -> int:
    """
    Auto-discovers and returns the index of the laptop's built-in webcam on Windows.
    Specifically skips virtual or external phone cameras (e.g. Smart Connect, DroidCam).
    """
    try:
        ps_cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_PnPEntity | Where-Object PNPClass -eq Camera | Select-Object Name, DeviceID | ConvertTo-Json"
        ]
        res = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            devices = json.loads(res.stdout)
            if isinstance(devices, dict):
                devices = [devices]

            # 1. Match preferred physical laptop webcam keywords
            for idx, dev in enumerate(devices):
                name = dev.get("Name", "").lower()
                if any(kw in name for kw in preferred_keywords):
                    print(f"[CameraManager] Found preferred laptop camera: '{dev.get('Name')}' at index {idx}")
                    return idx

            # 2. Pick first non-excluded camera device
            for idx, dev in enumerate(devices):
                name = dev.get("Name", "").lower()
                if not any(ex in name for ex in exclude_keywords):
                    print(f"[CameraManager] Selected camera: '{dev.get('Name')}' at index {idx}")
                    return idx
    except Exception as e:
        print(f"[CameraManager] Device enumeration notice: {e}")

    return 0


class CameraManager:
    def __init__(
        self,
        camera_index: Optional[int] = None,
        target_fps: int = 5,
        width: int = 640,
        height: int = 480,
        mock_mode: bool = False
    ):
        if camera_index is None or camera_index < 0:
            self.camera_index = find_preferred_camera_index()
        else:
            self.camera_index = camera_index
        self.target_fps = target_fps
        self.frame_interval = 1.0 / max(1, target_fps)
        self.width = width
        self.height = height
        self.mock_mode = mock_mode
        self.cap: Optional[cv2.VideoCapture] = None
        self.last_frame_time = 0.0

        if not self.mock_mode:
            self._init_camera()

    def _init_camera(self):
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            else:
                print(f"[CameraManager] Warning: Camera {self.camera_index} could not be opened. Falling back to mock frames.")
                self.mock_mode = True
        except Exception as e:
            print(f"[CameraManager] Error initializing camera: {e}")
            self.mock_mode = True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Throttle to target FPS and return in-memory RGB frame.
        Guarantees that frames are never written to disk or preserved beyond callers scope.
        """
        now = time.time()
        sleep_needed = self.frame_interval - (now - self.last_frame_time)
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        self.last_frame_time = time.time()

        if self.mock_mode or self.cap is None or not self.cap.isOpened():
            # Return synthetic test frame (640x480 blank with neutral tone)
            frame_rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            return True, frame_rgb

        ret, frame_bgr = self.cap.read()
        if not ret or frame_bgr is None:
            return False, None

        if frame_bgr.shape[1] != self.width or frame_bgr.shape[0] != self.height:
            frame_bgr = cv2.resize(frame_bgr, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        # Release frame_bgr memory
        del frame_bgr
        return True, frame_rgb

    def release(self):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None
