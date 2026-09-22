"""
DeskSense Coarse Screen Attention Estimator (Phase 1 Module 4)
Estimates coarse user gaze and head pose direction without claiming invasive precise eye tracking:
- SCREEN
- LEFT
- RIGHT
- DOWN
- AWAY
- UNKNOWN

Conforms strictly to P1-11 and P1-21 test specifications.
"""

from typing import Optional, Dict, Any, Tuple

class AttentionEstimator:
    def __init__(
        self,
        yaw_threshold: float = 0.45,
        pitch_down_threshold: float = 0.12,
        pitch_up_away_threshold: float = -0.15
    ):
        """
        :param yaw_threshold: Normalized yaw offset (nose relative to mid-eye / inter-eye distance).
        :param pitch_down_threshold: Normalized pitch offset (nose relative to mid-eye) for looking DOWN.
        :param pitch_up_away_threshold: Pitch offset looking excessively UP/AWAY.
        """
        self.yaw_threshold = yaw_threshold
        self.pitch_down_threshold = pitch_down_threshold
        self.pitch_up_away_threshold = pitch_up_away_threshold

    def estimate(
        self,
        metrics: Optional[Dict[str, float]],
        presence_state: str = "PRESENT",
        confidence: float = 1.0
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Estimate coarse attention orientation.
        Returns: (attention_class, details_dict)
        """
        if presence_state == "AWAY":
            return "AWAY", {"reason": "user_away"}

        if presence_state != "PRESENT" or not metrics or confidence < 0.35:
            return "UNKNOWN", {"reason": "unreliable_input"}

        yaw_offset = metrics.get("yaw_offset", 0.0)
        pitch_offset = metrics.get("pitch_offset", 0.0)

        details = {
            "yaw_offset": round(yaw_offset, 3),
            "pitch_offset": round(pitch_offset, 3),
            "confidence": confidence
        }

        # Coarse direction evaluation
        if yaw_offset > self.yaw_threshold:
            details["direction"] = "RIGHT"
            return "RIGHT", details
        elif yaw_offset < -self.yaw_threshold:
            details["direction"] = "LEFT"
            return "LEFT", details
        elif pitch_offset > self.pitch_down_threshold:
            details["direction"] = "DOWN"
            return "DOWN", details
        elif pitch_offset < self.pitch_up_away_threshold:
            details["direction"] = "AWAY"
            return "AWAY", details
        else:
            details["direction"] = "SCREEN"
            return "SCREEN", details
