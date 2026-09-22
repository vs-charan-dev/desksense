"""
DeskSense Posture Classification Engine (Phase 1 Module 3)
Evaluates skeletal landmark metrics against the user's calibrated baseline to determine:
- POSTURE_GOOD
- SLOUCHING
- TOO_CLOSE
- LEAN_LEFT
- LEAN_RIGHT
- HEAD_TILT
- UNKNOWN

Conforms strictly to P1-09, P1-10, P1-17, P1-18, P1-19, P1-20 test specifications.
"""

import math
from typing import Optional, Dict, Any, Tuple
from src.vision.calibration import CalibrationProfile

class PostureClassifier:
    def __init__(
        self,
        too_close_ratio_threshold: float = 1.30,
        slouch_y_ratio_threshold: float = 0.80,
        lean_angle_threshold_deg: float = 7.0,
        head_tilt_angle_threshold_deg: float = 10.0
    ):
        """
        :param too_close_ratio_threshold: Distance ratio (current / baseline) above which is TOO_CLOSE.
        :param slouch_y_ratio_threshold: Head-shoulder Y delta ratio below which is SLOUCHING.
        :param lean_angle_threshold_deg: Shoulder tilt angle from horizontal above which is LEAN_LEFT/RIGHT.
        :param head_tilt_angle_threshold_deg: Eye tilt angle from horizontal above which is HEAD_TILT.
        """
        self.too_close_ratio_threshold = too_close_ratio_threshold
        self.slouch_y_ratio_threshold = slouch_y_ratio_threshold
        self.lean_angle_threshold_deg = lean_angle_threshold_deg
        self.head_tilt_angle_threshold_deg = head_tilt_angle_threshold_deg

    def classify(
        self,
        metrics: Optional[Dict[str, float]],
        calibration: Optional[CalibrationProfile],
        presence_state: str = "PRESENT"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Classifies frame posture.
        Returns: (posture_class, evaluation_details)
        """
        if presence_state != "PRESENT" or not metrics:
            return "UNKNOWN", {"reason": "user_not_present_or_no_metrics"}

        # If no calibration profile is established yet, use safe fallback defaults
        base_eye = calibration.inter_eye_dist if calibration else 0.05
        base_y = calibration.head_shoulder_y_delta if calibration else 0.20

        cur_eye = metrics.get("inter_eye_dist", 0.0)
        cur_y = metrics.get("head_shoulder_y_delta", 0.0)
        shoulder_span = metrics.get("shoulder_span", 0.35)
        shoulder_tilt = metrics.get("shoulder_tilt", 0.0)  # right_sh.y - left_sh.y
        head_tilt = metrics.get("head_tilt", 0.0)          # right_eye.y - left_eye.y

        # Compute relative distance ratio (P1-10)
        distance_ratio = cur_eye / max(base_eye, 0.01) if base_eye > 0 else 1.0
        y_ratio = cur_y / max(base_y, 0.05) if base_y > 0 else 1.0

        # Calculate shoulder tilt angle in degrees
        # span is normalized, tilt is normalized delta y
        # angle = atan2(delta_y, delta_x)
        shoulder_angle_deg = math.degrees(math.atan2(shoulder_tilt, max(shoulder_span, 0.01)))
        # Eye span angle
        eye_span = max(cur_eye, 0.01)
        head_tilt_angle_deg = math.degrees(math.atan2(head_tilt, eye_span))

        eval_details = {
            "distance_ratio": round(distance_ratio, 3),
            "head_y_ratio": round(y_ratio, 3),
            "shoulder_angle_deg": round(shoulder_angle_deg, 1),
            "head_tilt_angle_deg": round(head_tilt_angle_deg, 1),
        }

        # Hierarchy of classification rules
        # 1. TOO_CLOSE: User is leaning excessively forward toward the screen / camera
        if distance_ratio >= self.too_close_ratio_threshold:
            eval_details["detected_class"] = "TOO_CLOSE"
            return "TOO_CLOSE", eval_details

        # 2. SLOUCHING: Head has dropped significantly relative to shoulders
        if y_ratio <= self.slouch_y_ratio_threshold:
            eval_details["detected_class"] = "SLOUCHING"
            return "SLOUCHING", eval_details

        # 3. LEAN_LEFT / LEAN_RIGHT: Shoulder line tilted
        # In image coordinates, y increases downward.
        # If right_sh.y > left_sh.y, right shoulder is lower -> leaning right
        if shoulder_angle_deg >= self.lean_angle_threshold_deg:
            eval_details["detected_class"] = "LEAN_RIGHT"
            return "LEAN_RIGHT", eval_details
        elif shoulder_angle_deg <= -self.lean_angle_threshold_deg:
            eval_details["detected_class"] = "LEAN_LEFT"
            return "LEAN_LEFT", eval_details

        # 4. HEAD_TILT: Head tilted sideways while shoulders remain relatively level
        if abs(head_tilt_angle_deg) >= self.head_tilt_angle_threshold_deg:
            eval_details["detected_class"] = "HEAD_TILT"
            return "HEAD_TILT", eval_details

        # 5. Ergonomically sound posture
        eval_details["detected_class"] = "POSTURE_GOOD"
        return "POSTURE_GOOD", eval_details
