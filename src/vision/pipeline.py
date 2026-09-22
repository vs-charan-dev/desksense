"""
DeskSense Integrated Vision & Posture Core Pipeline (Phase 1)
Combines:
- VisionDetector (Raw landmark extraction)
- PresenceEngine (Absence hysteresis)
- CalibrationManager (Baseline profile)
- PostureClassifier (Geometric classification)
- AttentionEstimator (Coarse gaze orientation)
- TemporalFilter (Jitter suppression & notification rules)
"""

import time
from typing import Optional, Dict, Any, Tuple
import numpy as np

from src.vision.detector import VisionDetector
from src.vision.presence import PresenceEngine
from src.vision.calibration import CalibrationManager, CalibrationProfile
from src.vision.posture import PostureClassifier
from src.vision.attention import AttentionEstimator
from src.vision.filter import TemporalFilter

class VisionCore:
    def __init__(
        self,
        model_path: str = "models/pose_landmarker_lite.task",
        calibration_path: str = "calibration_profile.json",
        time_func = None
    ):
        self.time_func = time_func or time.time
        self.detector = VisionDetector(model_path=model_path)
        self.calibration_mgr = CalibrationManager(profile_path=calibration_path, time_func=self.time_func)
        self.presence_engine = PresenceEngine(time_func=self.time_func)
        self.posture_classifier = PostureClassifier()
        self.attention_estimator = AttentionEstimator()
        self.temporal_filter = TemporalFilter(time_func=self.time_func)

    def process_frame(
        self,
        frame_rgb: Optional[np.ndarray],
        camera_available: bool = True
    ) -> Dict[str, Any]:
        """
        Processes a single in-memory video frame through the full Phase 1 pipeline.
        Zero persistence: frame is released at end of method.
        """
        now_ts = self.time_func()

        if not camera_available or frame_rgb is None:
            pres, pres_diag = self.presence_engine.update(
                raw_presence_candidate=None,
                confidence=0.0,
                camera_available=False
            )
            post, notify, filter_diag = self.temporal_filter.update("UNKNOWN")
            att, att_diag = self.attention_estimator.estimate(metrics=None, presence_state=pres)
            return {
                "timestamp": now_ts,
                "presence": pres,
                "posture": post,
                "attention": att,
                "should_notify": notify,
                "confidence": 0.0,
                "latency_ms": 0.0,
                "metrics": {},
                "filter_diag": filter_diag,
                "calibration_progress": self.calibration_mgr.progress_pct,
                "is_calibrating": self.calibration_mgr.is_calibrating
            }

        # 1. Raw Landmark Detection
        raw = self.detector.process_frame(frame_rgb, calibration=self.calibration_mgr.profile)
        raw_pres = raw.get("presence", "AWAY")
        conf = raw.get("confidence", 0.0)
        metrics = raw.get("metrics", {})

        # 2. Presence Hysteresis Engine (P1-01, P1-02, P1-03, P1-04)
        pres, pres_diag = self.presence_engine.update(
            raw_presence_candidate=raw_pres,
            confidence=conf,
            camera_available=True
        )

        # 3. Calibration Sample Capture (P1-05, P1-06, P1-07)
        calib_finished = False
        calib_msg = None
        if self.calibration_mgr.is_calibrating and pres == "PRESENT":
            calib_finished, calib_msg = self.calibration_mgr.add_sample(metrics, confidence=conf)

        # 4. Posture Classification (P1-09, P1-10)
        raw_post, post_details = self.posture_classifier.classify(
            metrics=metrics,
            calibration=self.calibration_mgr.profile,
            presence_state=pres
        )

        # 5. Attention Estimation (P1-11)
        att, att_diag = self.attention_estimator.estimate(
            metrics=metrics,
            presence_state=pres,
            confidence=conf
        )

        # 6. Temporal Smoothing & Notification Filter (P1-12, P1-13, P1-14, P1-15, P1-16)
        stable_post, should_notify, filter_diag = self.temporal_filter.update(raw_post)

        return {
            "timestamp": now_ts,
            "presence": pres,
            "posture": stable_post,
            "raw_posture": raw_post,
            "attention": att,
            "should_notify": should_notify,
            "confidence": conf,
            "latency_ms": raw.get("latency_ms", 0.0),
            "metrics": metrics,
            "keypoints": raw.get("keypoints", {}),
            "presence_diag": pres_diag,
            "posture_details": post_details,
            "filter_diag": filter_diag,
            "is_calibrating": self.calibration_mgr.is_calibrating,
            "calibration_progress": self.calibration_mgr.progress_pct,
            "calib_finished": calib_finished,
            "calib_msg": calib_msg
        }

    def start_calibration(self, duration_sec: float = 10.0):
        self.calibration_mgr.start_calibration(duration_sec=duration_sec)

    def reset(self):
        self.presence_engine.reset()
        self.temporal_filter.reset()
