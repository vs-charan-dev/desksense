"""
DeskSense Pose & Presence Detector
Wraps MediaPipe PoseLandmarker to extract 33 skeletal landmarks and determine:
- Presence (PRESENT, AWAY)
- Posture state (POSTURE_GOOD, SLOUCHING, TOO_CLOSE, LEAN_LEFT, LEAN_RIGHT)
- Coarse Attention (SCREEN, LEFT, RIGHT, DOWN, AWAY)
Adheres strictly to the privacy mandate: zero frame storage, in-memory processing only.
"""

import math
import time
from typing import Optional, Tuple, Dict, Any
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

from src.vision.calibration import CalibrationProfile, CalibrationManager


class VisionDetector:
    # Landmark indices according to MediaPipe Pose 33-point topology
    NOSE = 0
    LEFT_EYE = 2
    RIGHT_EYE = 5
    LEFT_EAR = 7
    RIGHT_EAR = 8
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12

    def __init__(self, model_path: str = "models/pose_landmarker_lite.task"):
        self.model_path = model_path
        self.detector = None
        self._init_detector()

    def _init_detector(self):
        if not MEDIAPIPE_AVAILABLE:
            print("[VisionDetector] MediaPipe tasks not available.")
            return

        try:
            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                output_segmentation_masks=False,
                running_mode=vision.RunningMode.IMAGE
            )
            self.detector = vision.PoseLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[VisionDetector] Failed to load model at {self.model_path}: {e}")
            self.detector = None

    def process_frame(
        self,
        frame_rgb: np.ndarray,
        calibration: Optional[CalibrationProfile] = None
    ) -> Dict[str, Any]:
        """
        Process a single in-memory RGB frame.
        Returns extracted metrics, presence, posture, and attention.
        The frame is never written to disk.
        """
        t0 = time.perf_counter()

        if self.detector is None:
            return self._empty_result(latency_ms=0.0, error="Model not loaded")

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        detection_result = self.detector.detect(mp_image)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if not detection_result.pose_landmarks:
            return self._empty_result(latency_ms=latency_ms)

        landmarks = detection_result.pose_landmarks[0]
        
        # Check presence confidence
        nose = landmarks[self.NOSE]
        left_sh = landmarks[self.LEFT_SHOULDER]
        right_sh = landmarks[self.RIGHT_SHOULDER]
        left_eye = landmarks[self.LEFT_EYE]
        right_eye = landmarks[self.RIGHT_EYE]
        left_ear = landmarks[self.LEFT_EAR]
        right_ear = landmarks[self.RIGHT_EAR]

        presence_score = (
            getattr(nose, 'visibility', 0.8) +
            getattr(left_sh, 'visibility', 0.8) +
            getattr(right_sh, 'visibility', 0.8)
        ) / 3.0

        if presence_score < 0.35:
            return self._empty_result(latency_ms=latency_ms)

        # Compute geometric feature metrics
        inter_eye_dist = math.sqrt(
            (right_eye.x - left_eye.x) ** 2 +
            (right_eye.y - left_eye.y) ** 2
        )
        shoulder_span = math.sqrt(
            (right_sh.x - left_sh.x) ** 2 +
            (right_sh.y - left_sh.y) ** 2
        )

        mid_shoulder_x = (left_sh.x + right_sh.x) / 2.0
        mid_shoulder_y = (left_sh.y + right_sh.y) / 2.0
        head_shoulder_y_delta = mid_shoulder_y - nose.y
        shoulder_tilt = right_sh.y - left_sh.y

        mid_eye_x = (left_eye.x + right_eye.x) / 2.0
        mid_eye_y = (left_eye.y + right_eye.y) / 2.0

        ear_shoulder_ratio = 0.15
        if left_ear and right_ear:
            mid_ear_y = (left_ear.y + right_ear.y) / 2.0
            ear_shoulder_ratio = max(0.01, mid_shoulder_y - mid_ear_y)

        # Coarse attention / head orientation
        yaw_offset = (nose.x - mid_eye_x) / (inter_eye_dist + 1e-6)
        pitch_offset = nose.y - mid_eye_y

        if yaw_offset > 0.45:
            attention = "RIGHT"
        elif yaw_offset < -0.45:
            attention = "LEFT"
        elif pitch_offset > 0.12:
            attention = "DOWN"
        else:
            attention = "SCREEN"

        # Posture evaluation against baseline
        posture = "POSTURE_GOOD"
        distance_ratio = 1.0

        if calibration:
            base_eye = calibration.inter_eye_dist
            base_span = calibration.shoulder_span
            base_y = calibration.head_shoulder_y_delta

            if base_eye > 0:
                distance_ratio = inter_eye_dist / base_eye
            elif base_span > 0:
                distance_ratio = shoulder_span / base_span

            y_ratio = head_shoulder_y_delta / max(base_y, 0.05)

            if distance_ratio > 1.35:
                posture = "TOO_CLOSE"
            elif y_ratio < 0.78:
                posture = "SLOUCHING"
            elif shoulder_tilt > 0.08:
                posture = "LEAN_RIGHT"
            elif shoulder_tilt < -0.08:
                posture = "LEAN_LEFT"
            else:
                posture = "POSTURE_GOOD"

        raw_metrics = {
            "inter_eye_dist": inter_eye_dist,
            "shoulder_span": shoulder_span,
            "head_shoulder_y_delta": head_shoulder_y_delta,
            "shoulder_tilt": shoulder_tilt,
            "ear_shoulder_ratio": ear_shoulder_ratio,
            "distance_ratio": distance_ratio,
        }

        keypoints_summary = {
            "nose": (round(nose.x, 3), round(nose.y, 3)),
            "left_shoulder": (round(left_sh.x, 3), round(left_sh.y, 3)),
            "right_shoulder": (round(right_sh.x, 3), round(right_sh.y, 3)),
        }

        return {
            "presence": "PRESENT",
            "posture": posture,
            "attention": attention,
            "metrics": raw_metrics,
            "keypoints": keypoints_summary,
            "latency_ms": round(latency_ms, 1),
            "confidence": round(presence_score, 2)
        }

    def _empty_result(self, latency_ms: float = 0.0, error: str = "") -> Dict[str, Any]:
        return {
            "presence": "AWAY",
            "posture": "UNKNOWN",
            "attention": "AWAY",
            "metrics": {},
            "keypoints": {},
            "latency_ms": round(latency_ms, 1),
            "confidence": 0.0,
            "error": error
        }
