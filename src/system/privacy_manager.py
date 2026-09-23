"""Privacy Controls, Data Retention, Export & Wipe Manager for DeskSense (Phase 6).
Implements:
1. Data Retention Engine:
   - Configurable retention cycles (7 days, 30 days, 90 days, 365 days, "forever").
   - Prunes records older than the cutoff boundary across all activity tables:
     sessions, posture_events, attention_events, app_usage, phone_sessions, breaks, work_state_intervals.
   - Preserves user settings, calibration profile, and category rules intact.
   - "forever" deletes nothing.
2. Data Export:
   - Single-click export of user activity to structured JSON and CSV formats.
   - Strictly verified: contains 0 camera bytes, image frames, or video recordings.
3. Data Wipe:
   - Wipes all historical activity, sessions, intervals, and summaries upon explicit confirmation.
   - Preserves application settings, calibration, and category rules.
   - Rejects unconfirmed wipe requests safely.
"""

import json
import csv
import io
import datetime
from typing import Dict, Any, List, Optional
from src.storage.db import DatabaseEngine


RETENTION_DAYS_MAP: Dict[str, Optional[int]] = {
    "7_days": 7,
    "30_days": 30,
    "90_days": 90,
    "365_days": 365,
    "forever": None,
}


class PrivacyManager:
    """Handles data retention pruning, structured exports, and data wipe commands."""

    def __init__(self, db: DatabaseEngine):
        self.db = db

    def apply_retention_policy(self, policy: str = "30_days", current_timestamp: Optional[float] = None) -> Dict[str, int]:
        """
        Deletes records older than retention boundary.
        'forever' deletes nothing.
        Settings, calibration, and category_rules are untouched.
        """
        days = RETENTION_DAYS_MAP.get(policy.lower())
        if days is None:
            return {"deleted_records": 0, "policy": "forever"}

        now = current_timestamp if current_timestamp is not None else datetime.datetime.now().timestamp()
        cutoff_epoch = now - (days * 86400.0)
        
        try:
            cutoff_iso = datetime.datetime.fromtimestamp(cutoff_epoch).isoformat()
        except (OSError, OverflowError, ValueError):
            cutoff_iso = "1970-01-01T00:00:00"

        deleted_counts = {}
        with self.db.get_connection() as conn:
            # 1. Posture events (start_time float)
            cur = conn.execute("DELETE FROM posture_events WHERE end_time < ?", (cutoff_epoch,))
            deleted_counts["posture_events"] = cur.rowcount

            # 2. Attention events (start_time float)
            cur = conn.execute("DELETE FROM attention_events WHERE end_time < ?", (cutoff_epoch,))
            deleted_counts["attention_events"] = cur.rowcount

            # 3. App usage (start_time float)
            cur = conn.execute("DELETE FROM app_usage WHERE end_time < ?", (cutoff_epoch,))
            deleted_counts["app_usage"] = cur.rowcount

            # 4. Phone sessions (end_time TEXT ISO or timestamp)
            cur = conn.execute("DELETE FROM phone_sessions WHERE end_time < ?", (cutoff_iso,))
            deleted_counts["phone_sessions"] = cur.rowcount

            # 5. Breaks (end_time TEXT ISO or timestamp)
            cur = conn.execute("DELETE FROM breaks WHERE end_time < ?", (cutoff_iso,))
            deleted_counts["breaks"] = cur.rowcount

            # 6. Work state intervals (end_time TEXT or epoch)
            cur = conn.execute("DELETE FROM work_state_intervals WHERE end_time < ? OR CAST(end_time AS REAL) < ?", (cutoff_iso, cutoff_epoch))
            deleted_counts["work_state_intervals"] = cur.rowcount

            # 7. Sessions (end_time float)
            cur = conn.execute("DELETE FROM sessions WHERE end_time IS NOT NULL AND end_time < ?", (cutoff_epoch,))
            deleted_counts["sessions"] = cur.rowcount

            conn.commit()

        total_deleted = sum(deleted_counts.values())
        return {
            "deleted_records": total_deleted,
            "details": deleted_counts,
            "cutoff_timestamp": cutoff_epoch,
            "policy": policy,
        }

    def wipe_activity_data(self, confirmed: bool = False) -> bool:
        """
        Wipes all user activity, intervals, and session history upon explicit confirmation.
        Settings and category rules remain intact.
        """
        if not confirmed:
            return False

        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM posture_events")
            conn.execute("DELETE FROM attention_events")
            conn.execute("DELETE FROM app_usage")
            conn.execute("DELETE FROM phone_sessions")
            conn.execute("DELETE FROM breaks")
            conn.execute("DELETE FROM work_state_intervals")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM daily_summary")
            conn.commit()

        return True

    def export_data_json(self) -> str:
        """
        Generates full JSON export of activity history.
        Contains structured numerical metrics only; zero image/camera frame bytes.
        """
        with self.db.get_connection() as conn:
            sessions = [dict(r) for r in conn.execute("SELECT * FROM sessions ORDER BY id ASC").fetchall()]
            posture = [dict(r) for r in conn.execute("SELECT * FROM posture_events ORDER BY id ASC").fetchall()]
            attention = [dict(r) for r in conn.execute("SELECT * FROM attention_events ORDER BY id ASC").fetchall()]
            apps = [dict(r) for r in conn.execute("SELECT * FROM app_usage ORDER BY id ASC").fetchall()]
            phone = [dict(r) for r in conn.execute("SELECT * FROM phone_sessions ORDER BY id ASC").fetchall()]
            breaks = [dict(r) for r in conn.execute("SELECT * FROM breaks ORDER BY id ASC").fetchall()]
            work_states = [dict(r) for r in conn.execute("SELECT * FROM work_state_intervals ORDER BY id ASC").fetchall()]

        payload = {
            "exported_at": datetime.datetime.now().isoformat(),
            "sessions": sessions,
            "posture_events": posture,
            "attention_events": attention,
            "app_usage": apps,
            "phone_sessions": phone,
            "breaks": breaks,
            "work_state_intervals": work_states,
            "privacy_statement": "DeskSense operates strictly locally. No camera images, video streams, or raw frames are ever saved or exported.",
        }
        return json.dumps(payload, indent=2)

    def export_data_csv(self) -> str:
        """Generates CSV export of work state intervals."""
        with self.db.get_connection() as conn:
            intervals = [dict(r) for r in conn.execute("SELECT * FROM work_state_intervals ORDER BY id ASC").fetchall()]

        output = io.StringIO()
        fieldnames = ["id", "session_id", "state", "start_time", "end_time", "duration"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in intervals:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        return output.getvalue()
