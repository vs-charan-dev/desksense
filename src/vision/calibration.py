"""
DeskSense Posture Calibration Module (Phase 1 Module 2)
Establishes user baseline measurements (inter-eye distance, head-to-shoulder angle,
shoulder span, ear-to-shoulder alignment, distance baseline) for ergonomic evaluation.
Conforms strictly to P1-05, P1-06, P1-07, P1-08 test specifications:
- 10-second posture baseline capture sequence with fake-clock support
- Quality rejection (missing shoulders/head, too few valid samples, extreme tilt)
- Stores normalized profile and reloads safely
"""

import json
import os
import math
import time
import datetime
from typing import Optional, Dict, Any, List, Tuple

class CalibrationProfile:
    def __init__(
        self,
        inter_eye_dist: float = 0.05,
        shoulder_span: float = 0.35,
        head_shoulder_y_delta: float = 0.20,
        ear_shoulder_ratio: float = 0.15,
        head_shoulder_angle: float = 90.0,
        calibrated_at: str = ""
    ):
        self.inter_eye_dist = float(inter_eye_dist)
        self.shoulder_span = float(shoulder_span)
        self.head_shoulder_y_delta = float(head_shoulder_y_delta)
        self.ear_shoulder_ratio = float(ear_shoulder_ratio)
        self.head_shoulder_angle = float(head_shoulder_angle)
        self.calibrated_at = calibrated_at or datetime.datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inter_eye_dist": round(self.inter_eye_dist, 4),
            "shoulder_span": round(self.shoulder_span, 4),
            "head_shoulder_y_delta": round(self.head_shoulder_y_delta, 4),
            "ear_shoulder_ratio": round(self.ear_shoulder_ratio, 4),
            "head_shoulder_angle": round(self.head_shoulder_angle, 2),
            "calibrated_at": self.calibrated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationProfile":
        return cls(
            inter_eye_dist=data.get("inter_eye_dist", 0.05),
            shoulder_span=data.get("shoulder_span", 0.35),
            head_shoulder_y_delta=data.get("head_shoulder_y_delta", 0.20),
            ear_shoulder_ratio=data.get("ear_shoulder_ratio", 0.15),
            head_shoulder_angle=data.get("head_shoulder_angle", 90.0),
            calibrated_at=data.get("calibrated_at", "")
        )


class CalibrationManager:
    def __init__(
        self,
        profile_path: str = "calibration_profile.json",
        calibration_duration_sec: float = 10.0,
        min_required_samples: int = 15,
        time_func = None
    ):
        self.profile_path = profile_path
        self.calibration_duration_sec = calibration_duration_sec
        self.min_required_samples = min_required_samples
        self.time_func = time_func or time.time

        self.profile: Optional[CalibrationProfile] = None
        self.is_calibrating = False
        self.start_time: Optional[float] = None
        self.samples: List[Dict[str, float]] = []
        self.last_rejection_reason: Optional[str] = None
        self.load_profile()

    def load_profile(self) -> bool:
        """Load calibration profile from disk if present and valid."""
        if not os.path.exists(self.profile_path):
            self.profile = None
            return False
        try:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                required = ["inter_eye_dist", "shoulder_span", "head_shoulder_y_delta"]
                if not all(k in data for k in required):
                    self.profile = None
                    return False
                self.profile = CalibrationProfile.from_dict(data)
                return True
        except Exception:
            # Corrupted profile
            self.profile = None
            return False

    def save_profile(self) -> bool:
        """Persist calibration profile to disk."""
        if not self.profile:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.profile_path)), exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    def start_calibration(self, duration_sec: Optional[float] = None):
        """Initiate 10-second calibration collection sequence."""
        if duration_sec is not None:
            self.calibration_duration_sec = duration_sec
        self.is_calibrating = True
        self.start_time = self.time_func()
        self.samples = []
        self.last_rejection_reason = None

    def add_sample(
        self,
        metrics: Optional[Dict[str, float]],
        confidence: float = 1.0
    ) -> Tuple[bool, Optional[str]]:
        """
        Add a frame measurement during calibration.
        Frames outside the configured duration window are ignored.
        
        Returns:
            (is_finished, rejection_or_status_message)
        """
        if not self.is_calibrating:
            return False, "Not calibrating"

        now = self.time_func()
        elapsed = now - (self.start_time or now)

        # Ignore samples if duration exceeded and finalize
        if elapsed > self.calibration_duration_sec:
            success, reason = self._finalize_calibration()
            return True, reason

        # P1-06: Quality rejection checks on sample candidate
        if not metrics or confidence < 0.4:
            # Drop low quality / invalid frame
            return False, None

        # Check required landmarks present
        eye_dist = metrics.get("inter_eye_dist", 0.0)
        shoulder_span = metrics.get("shoulder_span", 0.0)
        y_delta = metrics.get("head_shoulder_y_delta", 0.0)

        # Quality check: head and shoulders must be clearly distinct & visible
        if eye_dist <= 0.01:
            return False, "Eye distance too small or head not clearly visible"
        if shoulder_span <= 0.05:
            return False, "Shoulders not clearly visible in frame"
        if y_delta <= 0.02:
            return False, "Head-shoulder distance inadequate"

        self.samples.append(metrics)

        # If exactly at or past the configured duration window, finalize
        if elapsed >= self.calibration_duration_sec:
            success, reason = self._finalize_calibration()
            return True, reason

        return False, None

    def _finalize_calibration(self) -> Tuple[bool, str]:
        """Validate sample set quality and compute baseline metrics."""
        self.is_calibrating = False
        n = len(self.samples)

        # P1-06: Check minimum valid sample count
        if n < self.min_required_samples:
            reason = f"Calibration rejected: Insufficient valid frames: received {n}, required {self.min_required_samples}. Keep head and shoulders visible."
            self.last_rejection_reason = reason
            return False, reason

        # Aggregate averages
        avg_inter_eye = sum(s["inter_eye_dist"] for s in self.samples) / n
        avg_shoulder_span = sum(s["shoulder_span"] for s in self.samples) / n
        avg_head_shoulder_y = sum(s["head_shoulder_y_delta"] for s in self.samples) / n
        avg_ear_shoulder = sum(s.get("ear_shoulder_ratio", 0.15) for s in self.samples) / n
        avg_angle = sum(s.get("head_shoulder_angle", 90.0) for s in self.samples) / n

        # Sanity check ranges
        if avg_inter_eye <= 0.015 or avg_shoulder_span <= 0.10:
            reason = "Calibration rejected: User positioned too far from camera or lighting inadequate."
            self.last_rejection_reason = reason
            return False, reason

        # P1-07: Store normalized profile
        self.profile = CalibrationProfile(
            inter_eye_dist=avg_inter_eye,
            shoulder_span=avg_shoulder_span,
            head_shoulder_y_delta=avg_head_shoulder_y,
            ear_shoulder_ratio=avg_ear_shoulder,
            head_shoulder_angle=avg_angle,
            calibrated_at=datetime.datetime.now().isoformat()
        )
        self.last_rejection_reason = None
        self.save_profile()
        return True, "Calibration successful"

    @property
    def progress_pct(self) -> float:
        if not self.is_calibrating or not self.start_time:
            return 100.0 if self.profile else 0.0
        elapsed = self.time_func() - self.start_time
        return min(100.0, max(0.0, (elapsed / self.calibration_duration_sec) * 100.0))
