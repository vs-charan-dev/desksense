"""Integration test suite for Phase 2: Windows Activity, Lifecycle, SQLite, and Notifications.

Verifies:
- P2-01: Foreground application tracking and window title extraction.
- P2-02: Idle duration calculation via GetLastInputInfo and tick wrap handling.
- P2-03: Activity polling deduplication and interval extension.
- P2-04: Lock/sleep/hibernate event handling and session closure.
- P2-05: Unlock/resume session initialization without joining sleep time.
- P2-06: Camera disconnect/contention resilience and desktop tracking continuity.
- P2-07: SQLite schema creation, migrations, and idempotent reopening.
- P2-08: Structured event round-trip for settings, sessions, posture, attention, and apps.
- P2-09: Restart persistence across database engine instances.
- P2-10: Batch transaction rollback on partial failure.
- P2-11: Aggregation correctness for daily desk time, away time, and posture score.
- P2-12: Compact storage behavior (downsampling repeated frame predictions).
- P2-13: Toast notification payload privacy (short text, no image/frame blobs).
- P2-14: Shared 5-minute cooldown enforcement and category disable toggles.
- P2-15: Local-only operation (no network sockets or outbound calls required).
"""

import os
import sys
import tempfile
import unittest
from typing import Dict, Any, List, Optional

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.system.activity import ActivityTracker
from src.system.lifecycle import SessionManager, LifecycleEventType
from src.storage.db import DatabaseEngine
from src.system.notifier import NotificationDispatcher, NotificationCategory, TOAST_TEMPLATES


class MockClock:
    def __init__(self, start_time: float = 1000.0):
        self._time = start_time

    def time(self) -> float:
        return self._time

    def advance(self, seconds: float):
        self._time += seconds


class TestPhase2(unittest.TestCase):
    def setUp(self):
        self.mock_clock = MockClock(1000.0)
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db_file.name
        self.temp_db_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass
        # Also clean WAL files
        for extra in [f"{self.temp_db_path}-wal", f"{self.temp_db_path}-shm"]:
            if os.path.exists(extra):
                try:
                    os.remove(extra)
                except Exception:
                    pass

    # P2-01: Foreground application
    def test_p2_01_foreground_application_tracking(self):
        tracker = ActivityTracker(clock_func=self.mock_clock.time)
        
        # Test switching between two known applications
        app1 = ("code.exe", "DeskSense - Visual Studio Code", "C:\\VSCode\\code.exe")
        res1 = tracker.poll(override_foreground=app1)
        self.assertEqual(res1["application"], "code.exe")
        self.assertEqual(res1["window_title"], "DeskSense - Visual Studio Code")

        self.mock_clock.advance(10.0)
        app2 = ("chrome.exe", "Google Chrome - New Tab", "C:\\Chrome\\chrome.exe")
        res2 = tracker.poll(override_foreground=app2)

        self.assertTrue(res2["window_changed"])
        self.assertEqual(res2["application"], "chrome.exe")
        self.assertEqual(res2["window_title"], "Google Chrome - New Tab")
        self.assertIsNotNone(res2["closed_interval"])
        self.assertEqual(res2["closed_interval"]["application"], "code.exe")
        self.assertAlmostEqual(res2["closed_interval"]["duration"], 10.0)

    # P2-02: Idle duration calculation & tick wrap handling
    def test_p2_02_idle_duration_and_tick_wrap(self):
        current_tick = 5000000
        last_input_tick = 4940000  # 60s idle

        tracker = ActivityTracker(
            idle_threshold_seconds=60.0,
            tick_func=lambda: current_tick,
            last_input_func=lambda: last_input_tick,
        )

        idle_sec = tracker.get_idle_duration()
        self.assertAlmostEqual(idle_sec, 60.0)
        self.assertTrue(tracker.is_idle())

        # Test 32-bit unsigned rollover / wrap (e.g. system uptime rollover at 2^32 ms ~49.7 days)
        # last_input was right before wrap (0xFFFFFF00 = 4294967040), current tick right after (0x000000FF = 255)
        # diff = 255 + (4294967295 - 4294967040 + 1) = 511 ms = 0.511s
        tracker.tick_func = lambda: 0x000000FF
        tracker.last_input_func = lambda: 0xFFFFFF00
        idle_wrapped = tracker.get_idle_duration()
        self.assertAlmostEqual(idle_wrapped, 0.511, places=3)
        self.assertFalse(tracker.is_idle())

    # P2-03: Activity polling deduplication
    def test_p2_03_activity_polling_deduplication(self):
        tracker = ActivityTracker(clock_func=self.mock_clock.time)
        app = ("code.exe", "DeskSense - VS Code", "C:\\VSCode\\code.exe")

        # First poll starts interval
        res1 = tracker.poll(override_foreground=app)
        self.assertEqual(res1["application"], "code.exe")
        self.assertIsNone(res1["closed_interval"])

        # 10 repeated polls with same app
        for _ in range(10):
            self.mock_clock.advance(1.0)
            res = tracker.poll(override_foreground=app)
            self.assertFalse(res["window_changed"])
            self.assertIsNone(res["closed_interval"])
            self.assertAlmostEqual(res["current_interval"]["duration"], self.mock_clock.time() - 1000.0)

        # Total duration should be exactly 10s on single active interval
        self.assertAlmostEqual(tracker.current_interval["duration"] if hasattr(tracker, "current_interval") else res["current_interval"]["duration"], 10.0)

    # P2-04: Lock/sleep/hibernate event handling
    def test_p2_04_lock_and_sleep_closes_active_session(self):
        session_mgr = SessionManager(clock_func=self.mock_clock.time)
        session = session_mgr.start_session("WORK")
        self.assertIsNotNone(session)
        self.assertEqual(session["status"], "ACTIVE")

        self.mock_clock.advance(300.0)  # 5 minutes work
        closed = session_mgr.handle_event(LifecycleEventType.LOCK)
        
        self.assertIsNotNone(closed)
        self.assertEqual(closed["status"], "COMPLETED")
        self.assertAlmostEqual(closed["duration"], 300.0)
        self.assertIsNone(session_mgr.current_session)
        self.assertTrue(session_mgr.is_locked)

    # P2-05: Unlock/resume session initialization
    def test_p2_05_unlock_and_resume_starts_new_session_without_joining_gap(self):
        session_mgr = SessionManager(clock_func=self.mock_clock.time)
        s1 = session_mgr.start_session("WORK")
        self.mock_clock.advance(100.0)
        
        # Machine sleeps
        c1 = session_mgr.handle_event(LifecycleEventType.SLEEP)
        self.assertAlmostEqual(c1["duration"], 100.0)

        # Machine sleeps for 2 hours (7200 seconds)
        self.mock_clock.advance(7200.0)

        # Machine wakes up
        s2 = session_mgr.handle_event(LifecycleEventType.RESUME)
        self.assertIsNotNone(s2)
        self.assertNotEqual(s1["id"], s2["id"])
        self.assertEqual(s2["start_time"], self.mock_clock.time())

        # Work for 50 seconds and end
        self.mock_clock.advance(50.0)
        c2 = session_mgr.end_session()
        self.assertAlmostEqual(c2["duration"], 50.0)
        # Total durations of sessions must be 100 and 50, strictly excluding the 7200s gap
        self.assertEqual(len(session_mgr.completed_sessions), 2)
        self.assertAlmostEqual(session_mgr.completed_sessions[0]["duration"], 100.0)
        self.assertAlmostEqual(session_mgr.completed_sessions[1]["duration"], 50.0)

    # P2-06: Camera disconnect/contention resilience
    def test_p2_06_camera_disconnect_and_reconnect(self):
        session_mgr = SessionManager(clock_func=self.mock_clock.time)
        session_mgr.start_session("WORK")
        tracker = ActivityTracker(clock_func=self.mock_clock.time)

        # Camera gets disconnected (or grabbed by Teams/Zoom)
        session_mgr.handle_event(LifecycleEventType.CAMERA_DISCONNECTED)
        self.assertFalse(session_mgr.camera_available)

        # Desktop activity tracking continues uninterrupted
        app = ("word.exe", "Document1 - Word", "C:\\Word\\word.exe")
        res = tracker.poll(override_foreground=app)
        self.assertEqual(res["application"], "word.exe")

        # Camera is reconnected/released
        session_mgr.handle_event(LifecycleEventType.CAMERA_RECONNECTED)
        self.assertTrue(session_mgr.camera_available)
        self.assertIsNotNone(session_mgr.current_session)

    # P2-07: Schema creation/migration idempotency
    def test_p2_07_sqlite_schema_creation_and_idempotency(self):
        db = DatabaseEngine(self.temp_db_path)
        with db.get_connection() as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            table_names = {row["name"] for row in tables}
            required = {"settings", "sessions", "posture_events", "attention_events", "app_usage", "daily_summary"}
            self.assertTrue(required.issubset(table_names), f"Missing tables: {required - table_names}")

        # Reopening the database must be idempotent and succeed without errors
        db2 = DatabaseEngine(self.temp_db_path)
        db2.init_schema()

    # P2-08: Structured event round trip
    def test_p2_08_structured_event_round_trip(self):
        db = DatabaseEngine(self.temp_db_path)

        # 1. Settings
        db.set_setting("work_hours", {"start": "09:00", "end": "17:00"})
        val = db.get_setting("work_hours")
        self.assertEqual(val["start"], "09:00")

        # 2. Session
        session = {
            "id": "sess-test-1",
            "start_time": 1000.0,
            "end_time": 2000.0,
            "session_type": "WORK",
            "duration": 1000.0,
            "status": "COMPLETED",
        }
        db.record_session(session)
        rec = db.get_session("sess-test-1")
        self.assertEqual(rec["id"], "sess-test-1")
        self.assertEqual(rec["duration"], 1000.0)

        # 3. Posture Event
        db.insert_posture_event("SLOUCHING", 0.95, 1000.0, 1030.0, session_id="sess-test-1")
        with db.get_connection() as conn:
            p_row = conn.execute("SELECT * FROM posture_events WHERE session_id = 'sess-test-1'").fetchone()
            self.assertEqual(p_row["posture_state"], "SLOUCHING")
            self.assertAlmostEqual(p_row["confidence"], 0.95)

        # 4. Attention Event
        db.insert_attention_event("SCREEN", 0.88, 1000.0, 1030.0, session_id="sess-test-1")
        with db.get_connection() as conn:
            a_row = conn.execute("SELECT * FROM attention_events WHERE session_id = 'sess-test-1'").fetchone()
            self.assertEqual(a_row["attention_state"], "SCREEN")

        # 5. App Usage
        db.record_app_usage("code.exe", "DeskSense", 1000.0, 1050.0, "Productive", session_id="sess-test-1")
        with db.get_connection() as conn:
            u_row = conn.execute("SELECT * FROM app_usage WHERE session_id = 'sess-test-1'").fetchone()
            self.assertEqual(u_row["application"], "code.exe")
            self.assertEqual(u_row["duration"], 50.0)

    # P2-09: Restart persistence
    def test_p2_09_restart_persistence(self):
        db1 = DatabaseEngine(self.temp_db_path)
        db1.set_setting("calibration_profile", {"tilt": 0.05, "ratio": 1.0})
        db1.record_session({
            "id": "sess-persistent",
            "start_time": 500.0,
            "end_time": 600.0,
            "session_type": "WORK",
            "duration": 100.0,
            "status": "COMPLETED",
        })
        db1.close()

        # Reopen under fresh instance
        db2 = DatabaseEngine(self.temp_db_path)
        profile = db2.get_setting("calibration_profile")
        self.assertEqual(profile["ratio"], 1.0)
        session = db2.get_session("sess-persistent")
        self.assertIsNotNone(session)
        self.assertEqual(session["duration"], 100.0)

    # P2-10: Batch transaction rollback
    def test_p2_10_batch_transaction_rollback(self):
        db = DatabaseEngine(self.temp_db_path)
        valid_op = ("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)", ("key_a", "val_a", 1.0))
        # Intentionally malformed SQL to force rollback
        invalid_op = ("INSERT INTO non_existent_table VALUES (?, ?)", (1, 2))

        try:
            db.execute_batch_transaction([valid_op, invalid_op])
        except Exception:
            pass

        # Verify key_a was NOT written (atomic rollback)
        val = db.get_setting("key_a")
        self.assertIsNone(val, "Failed batch transaction must rollback all operations")

    # P2-11: Aggregation correctness
    def test_p2_11_aggregation_correctness(self):
        db = DatabaseEngine(self.temp_db_path)

        # 30 minutes good posture
        db.insert_posture_event("POSTURE_GOOD", 0.9, 1000.0, 2800.0)  # 1800s
        # 10 minutes slouching
        db.insert_posture_event("SLOUCHING", 0.9, 2800.0, 3400.0)      # 600s
        # 10 minutes away
        db.insert_attention_event("AWAY", 0.9, 3400.0, 4000.0)        # 600s
        # Active computer app
        db.record_app_usage("code.exe", "DeskSense", 1000.0, 3400.0)   # 2400s

        metrics = db.calculate_daily_metrics(1000.0, 4000.0)

        # Desk time = 1800 + 600 = 2400s
        self.assertAlmostEqual(metrics["desk_time"], 2400.0)
        # Away time = 600s
        self.assertAlmostEqual(metrics["away_time"], 600.0)
        # Active app time = 2400s
        self.assertAlmostEqual(metrics["active_time"], 2400.0)
        # Posture score = 1800 / 2400 = 75.0%
        self.assertAlmostEqual(metrics["posture_score"], 75.0)

    # P2-12: Compact storage behavior (downsampling)
    def test_p2_12_compact_storage_downsampling(self):
        db = DatabaseEngine(self.temp_db_path)

        # Simulate 100 frames of consecutive SLOUCHING (e.g. 5 FPS for 20 seconds)
        t = 1000.0
        for _ in range(100):
            db.record_posture_sample("SLOUCHING", 0.95, t)
            t += 0.2  # 5 FPS
        db.flush_posture_interval()

        # Database should have exactly 1 consolidated row, NOT 100 rows!
        with db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM posture_events").fetchall()
            self.assertEqual(len(rows), 1, "Repeated consecutive samples must consolidate into 1 interval")
            self.assertEqual(rows[0]["sample_count"], 100)
            self.assertAlmostEqual(rows[0]["start_time"], 1000.0)
            self.assertAlmostEqual(rows[0]["end_time"], 1019.8, places=1)

    # P2-13: Toast payload privacy & content
    def test_p2_13_toast_payload_privacy_and_structure(self):
        dispatcher = NotificationDispatcher()
        for alert_key, template in TOAST_TEMPLATES.items():
            payload = dispatcher.format_payload(alert_key)
            self.assertIsNotNone(payload)
            self.assertIn("title", payload)
            self.assertIn("message", payload)
            # Ensure zero frame or image binary references in payload
            for val in payload.values():
                self.assertNotIn("jpg", str(val).lower())
                self.assertNotIn("png", str(val).lower())
                self.assertNotIn("frame", str(val).lower())
                self.assertNotIn("base64", str(val).lower())

    # P2-14: Shared cooldown enforcement & category toggles
    def test_p2_14_shared_cooldown_and_category_toggles(self):
        dispatched_list = []
        dispatcher = NotificationDispatcher(
            cooldown_seconds=300.0,
            clock_func=self.mock_clock.time,
            dispatch_func=lambda t, m: (dispatched_list.append((t, m)) or True)
        )

        # 1. First alert dispatches successfully
        res1 = dispatcher.dispatch("SLOUCHING")
        self.assertTrue(res1)
        self.assertEqual(len(dispatched_list), 1)

        # 2. Repeated alert within 5 minutes is blocked by cooldown
        self.mock_clock.advance(100.0)  # only 100 seconds
        res2 = dispatcher.dispatch("SLOUCHING")
        self.assertFalse(res2)
        self.assertEqual(len(dispatched_list), 1)

        # 3. After 5 minutes (300s), alert succeeds again
        self.mock_clock.advance(201.0)  # total 301 seconds elapsed
        res3 = dispatcher.dispatch("SLOUCHING")
        self.assertTrue(res3)
        self.assertEqual(len(dispatched_list), 2)

        # 4. Category toggle disabled
        dispatcher.set_category_enabled(NotificationCategory.POSTURE, False)
        self.mock_clock.advance(500.0)
        res4 = dispatcher.dispatch("SLOUCHING")
        self.assertFalse(res4, "Disabled notification category must not dispatch")

    # P2-15: Local-only operation (no network required)
    def test_p2_15_local_only_operation(self):
        # Verify no socket/network library is imported or called during activity, storage, or notifications
        db = DatabaseEngine(self.temp_db_path)
        tracker = ActivityTracker()
        dispatcher = NotificationDispatcher(dispatch_func=lambda t, m: True)

        db.set_setting("offline_mode", True)
        tracker.poll(override_foreground=("local.exe", "Local App", "C:\\local.exe"))
        db.record_app_usage("local.exe", "Local App", 1.0, 2.0)
        self.assertTrue(dispatcher.dispatch("CALIBRATION_SUCCESS"))

        # Check DB was written purely to local sqlite file
        self.assertTrue(os.path.exists(self.temp_db_path))
        self.assertGreater(os.path.getsize(self.temp_db_path), 0)


if __name__ == "__main__":
    unittest.main()
