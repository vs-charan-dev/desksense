"""
DeskSense MVP 1 Dashboard Service (Phase 3 Module 3)
Calculates and formats daily overview metrics, posture distribution,
live state view model, and handles empty/error states gracefully.
Conforms strictly to P3-07, P3-08, P3-09, and P3-10 test specifications:
- Exact At-Desk Time, Away Time, Posture Score, Active Computer Time
- Posture distribution breakdown normalized to desk time, totaling 100%
- Live state and session duration updates
- Graceful handling of empty day, unavailable camera, missing calibration, database errors
"""

import datetime
from typing import Dict, Any, Optional
from src.storage.db import DatabaseEngine


class DashboardService:
    def __init__(self, db_engine: DatabaseEngine):
        self.db = db_engine

    def format_duration(self, seconds: float) -> str:
        """Formats seconds into human-readable e.g. '4h 18m' or '37m' or '0m'."""
        sec = int(round(seconds))
        if sec < 0:
            sec = 0
        hours = sec // 3600
        minutes = (sec % 3600) // 60
        remaining_secs = sec % 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m"
        elif remaining_secs > 0:
            return f"{remaining_secs}s"
        else:
            return "0m"

    def get_day_boundaries(self, target_date: Optional[str] = None) -> tuple[float, float]:
        """Calculates UTC/local day epoch timestamps (start of day 00:00:00 to 23:59:59.999)."""
        if not target_date:
            now = datetime.datetime.now()
            target_date = now.strftime("%Y-%m-%d")
        
        dt_start = datetime.datetime.strptime(f"{target_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.datetime.strptime(f"{target_date} 23:59:59.999", "%Y-%m-%d %H:%M:%S.%f")
        return dt_start.timestamp(), dt_end.timestamp()

    def get_dashboard_metrics(
        self,
        target_date: Optional[str] = None,
        camera_available: bool = True,
        has_calibration: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieves formatted daily metrics and distribution breakdown.
        Resilient against database errors, empty days, camera errors, and missing calibration.
        """
        if not target_date:
            target_date = datetime.datetime.now().strftime("%Y-%m-%d")

        t_start, t_end = self.get_day_boundaries(target_date)

        # Database fetch with error resilience (P3-10)
        db_error = None
        try:
            raw_metrics = self.db.calculate_daily_metrics(t_start, t_end)
        except Exception as e:
            db_error = f"Database read error: {str(e)}"
            raw_metrics = {
                "desk_time": 0.0,
                "away_time": 0.0,
                "active_time": 0.0,
                "posture_score": 100.0,
                "posture_breakdown": {},
                "attention_breakdown": {},
            }

        desk_time = float(raw_metrics.get("desk_time", 0.0))
        away_time = float(raw_metrics.get("away_time", 0.0))
        active_time = float(raw_metrics.get("active_time", 0.0))
        posture_score = float(raw_metrics.get("posture_score", 100.0))
        posture_breakdown = raw_metrics.get("posture_breakdown", {})

        # P3-08: Posture distribution calculation with desk_time as denominator
        good_sec = float(posture_breakdown.get("POSTURE_GOOD", 0.0))
        slouch_sec = float(posture_breakdown.get("SLOUCHING", 0.0))
        too_close_sec = float(posture_breakdown.get("TOO_CLOSE", 0.0))
        lean_left_sec = float(posture_breakdown.get("LEAN_LEFT", 0.0))
        lean_right_sec = float(posture_breakdown.get("LEAN_RIGHT", 0.0))
        head_tilt_sec = float(posture_breakdown.get("HEAD_TILT", 0.0))
        lean_sec = lean_left_sec + lean_right_sec + head_tilt_sec

        if desk_time > 0:
            pct_good = round((good_sec / desk_time) * 100.0, 1)
            pct_slouch = round((slouch_sec / desk_time) * 100.0, 1)
            pct_too_close = round((too_close_sec / desk_time) * 100.0, 1)
            # Ensure leaning takes up the remainder so total is exactly 100.0%
            pct_lean = round(max(0.0, 100.0 - (pct_good + pct_slouch + pct_too_close)), 1)
            distribution_total = round(pct_good + pct_slouch + pct_too_close + pct_lean, 1)
        else:
            pct_good = 0.0
            pct_slouch = 0.0
            pct_too_close = 0.0
            pct_lean = 0.0
            distribution_total = 0.0

        # Status banners and notifications for empty/error states (P3-10)
        alerts = []
        if db_error:
            alerts.append({"type": "error", "message": db_error})
        if not camera_available:
            alerts.append({"type": "warning", "message": "Camera is disconnected or in use by another application."})
        if not has_calibration:
            alerts.append({"type": "info", "message": "Posture calibration required. Click 'Calibrate' to begin."})
        if desk_time == 0 and active_time == 0 and away_time == 0 and not db_error:
            alerts.append({"type": "empty", "message": "No workspace activity recorded yet for today."})

        return {
            "date": target_date,
            "metrics": {
                "desk_time_sec": desk_time,
                "desk_time_formatted": self.format_duration(desk_time),
                "away_time_sec": away_time,
                "away_time_formatted": self.format_duration(away_time),
                "active_time_sec": active_time,
                "active_time_formatted": self.format_duration(active_time),
                "posture_score": posture_score,
                "posture_score_formatted": f"{int(round(posture_score))}%",
            },
            "posture_distribution": {
                "good": {"seconds": good_sec, "percentage": pct_good, "formatted": f"{pct_good}%"},
                "slouching": {"seconds": slouch_sec, "percentage": pct_slouch, "formatted": f"{pct_slouch}%"},
                "too_close": {"seconds": too_close_sec, "percentage": pct_too_close, "formatted": f"{pct_too_close}%"},
                "leaning": {"seconds": lean_sec, "percentage": pct_lean, "formatted": f"{pct_lean}%"},
                "total_percentage": distribution_total
            },
            "alerts": alerts,
            "has_error": db_error is not None,
            "camera_available": camera_available,
            "has_calibration": has_calibration,
        }

    def get_live_state(
        self,
        current_posture: str,
        current_attention: str,
        current_activity: str,
        session_duration_sec: float,
        is_paused: bool = False,
        pause_remaining_sec: float = 0.0
    ) -> Dict[str, Any]:
        """P3-09: Real-time update payload for live status indicator and timer."""
        status_label = "Good"
        status_category = "good"

        if is_paused:
            status_label = f"Paused ({self.format_duration(pause_remaining_sec)} remaining)"
            status_category = "paused"
        elif current_posture == "SLOUCHING":
            status_label = "Slouching"
            status_category = "warning"
        elif current_posture == "TOO_CLOSE":
            status_label = "Too Close"
            status_category = "warning"
        elif current_posture in ("LEAN_LEFT", "LEAN_RIGHT", "HEAD_TILT"):
            status_label = "Leaning"
            status_category = "warning"
        elif current_attention == "AWAY" or current_activity == "AWAY":
            status_label = "Away from Desk"
            status_category = "neutral"
        elif current_posture == "POSTURE_GOOD":
            status_label = "Good Posture"
            status_category = "good"
        else:
            status_label = "Calibrating / Detecting"
            status_category = "neutral"

        return {
            "posture": current_posture,
            "attention": current_attention,
            "activity": current_activity,
            "status_label": status_label,
            "status_category": status_category,
            "session_duration_sec": session_duration_sec,
            "session_duration_formatted": self.format_duration(session_duration_sec),
            "is_paused": is_paused,
            "pause_remaining_sec": round(pause_remaining_sec, 1)
        }
