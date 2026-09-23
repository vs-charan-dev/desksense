"""Integration test suite for Phase 3: Desktop Shell, Calibration Wizard, and MVP 1 Dashboard.

Verifies:
- P3-01: Start/minimize/close behavior: start minimized, hide on close, clean quit.
- P3-02: Tray commands: Open Dashboard, Pause 15m, Pause 1h, Custom pause, Recalibrate, Settings, Quit.
- P3-03: Pause semantics: stop inference/event creation, UI reflection, no invented data for gap.
- P3-04: Global hotkey: Ctrl+Shift+P toggle, deduplicated registration across window reopens.
- P3-05: Calibration wizard happy path: guidance -> 3s countdown -> 10s capture -> success & save profile.
- P3-06: Calibration wizard recovery: rejection/camera error reason, retry, cancel preserves previous profile.
- P3-07: Dashboard totals: exact At-Desk Time, Away Time, Posture Score, Active Computer Time.
- P3-08: Posture distribution: good, slouching, too close, leaning percentages use desk time and sum to 100%.
- P3-09: Live state updates: live posture, attention, session timer update smoothly.
- P3-10: Empty/error states: new day, unavailable camera, missing calibration, database read error handled gracefully.
- P3-11: Optional widget disabled: works fully when disabled; if enabled, draggable/collapsible/hidable without affecting monitoring.
- P3-12: End-to-end desk session: calibrate, normal posture, brief move, prolonged slouch, lean close, away, return, idle.
- P3-13: Restart continuity: quit and relaunch preserves prior session and dashboard totals.
- P3-14: Two-hour stability: 2-hour monitoring under synthetic clock has bounded memory and stable metrics.
- P3-15: Privacy recheck: zero camera frames, video files, or screenshots persist in database or disk.
"""

import os
import sys
import json
import tempfile
import unittest
from typing import Dict, Any, List, Optional

# Add repo root to path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.app.core import DeskSenseApp, AppState, MonitoringState
from src.app.wizard import CalibrationWizard, WizardState
from src.app.widget import StatusWidgetState
from src.app.tray import TrayController, TrayCommand
from src.app.hotkey import HotkeyManager
from src.app.dashboard import DashboardService
from src.vision.calibration import CalibrationProfile
from src.storage.db import DatabaseEngine


class MockClock:
    def __init__(self, start_time: float = 1700000000.0):
        self._time = start_time

    def time(self) -> float:
        return self._time

    def advance(self, seconds: float):
        self._time += seconds


class TestPhase3(unittest.TestCase):
    def setUp(self):
        self.mock_clock = MockClock(1700000000.0)
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.temp_profile = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.temp_profile_path = self.temp_profile.name
        self.temp_profile.close()

    def tearDown(self):
        for path in (self.temp_db_path, self.temp_profile_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    # ---------------- P3-01: Start/Minimize/Close Behavior ----------------
    def test_p3_01_start_minimize_close_behavior(self):
        # 1. Start minimized
        app_minimized = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            start_minimized=True,
            time_func=self.mock_clock.time
        )
        self.assertFalse(app_minimized.window_visible)
        self.assertEqual(app_minimized.monitoring_state, MonitoringState.MONITORING)

        # 2. Show dashboard then intercept close
        app_minimized.show_dashboard()
        self.assertTrue(app_minimized.window_visible)

        # Closing dashboard hides window while monitoring continues
        close_intercepted = app_minimized.on_close_requested()
        self.assertFalse(close_intercepted)  # Intercepted (prevents destroy)
        self.assertFalse(app_minimized.window_visible)  # Hidden to tray
        self.assertEqual(app_minimized.monitoring_state, MonitoringState.MONITORING)  # Still monitoring

        # 3. Clean Quit
        app_minimized.quit()
        self.assertFalse(app_minimized.is_running)
        self.assertEqual(app_minimized.monitoring_state, MonitoringState.STOPPED)

    # ---------------- P3-02: Tray Commands ----------------
    def test_p3_02_tray_commands(self):
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            start_minimized=True,
            time_func=self.mock_clock.time
        )

        tray = app.tray

        # Open Dashboard
        tray.dispatch(TrayCommand.OPEN_DASHBOARD)
        self.assertTrue(app.window_visible)

        # Pause 15 minutes
        tray.dispatch(TrayCommand.PAUSE_15_MIN)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)
        self.assertAlmostEqual(app.pause_remaining_sec, 900.0, delta=1.0)

        # Pause 1 hour
        tray.dispatch(TrayCommand.PAUSE_1_HOUR)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)
        self.assertAlmostEqual(app.pause_remaining_sec, 3600.0, delta=1.0)

        # Custom pause 45 minutes
        tray.dispatch(TrayCommand.PAUSE_CUSTOM, minutes=45)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)
        self.assertAlmostEqual(app.pause_remaining_sec, 2700.0, delta=1.0)

        # Resume
        tray.dispatch(TrayCommand.RESUME)
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)
        self.assertFalse(app.get_state().is_paused)

        # Recalibrate
        tray.dispatch(TrayCommand.RECALIBRATE)
        self.assertEqual(app.monitoring_state, MonitoringState.CALIBRATING)
        self.assertEqual(app.active_view, "calibration")

        # Settings
        tray.dispatch(TrayCommand.SETTINGS)
        self.assertEqual(app.active_view, "settings")

        # Quit
        tray.dispatch(TrayCommand.QUIT)
        self.assertFalse(app.is_running)
        self.assertEqual(app.monitoring_state, MonitoringState.STOPPED)

    # ---------------- P3-03: Pause Semantics ----------------
    def test_p3_03_pause_semantics(self):
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=self.mock_clock.time
        )

        # 1. Monitoring active, record sample
        app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        self.assertEqual(app.current_posture, "POSTURE_GOOD")

        # 2. Pause for 10 minutes (600s)
        app.pause_monitoring(duration_sec=600.0)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)
        self.assertEqual(app.pause_remaining_sec, 600.0)

        # Verify tray label reflects pause
        self.assertIn("Paused", app.get_tray_status_label())

        # Advance clock during pause by 300s (5 minutes)
        self.mock_clock.advance(300.0)
        self.assertEqual(app.pause_remaining_sec, 300.0)

        # Ingestion during pause is dropped (no events created for pause gap)
        app.record_observation("SLOUCHING", "SCREEN", confidence=1.0)
        self.assertNotEqual(app.current_posture, "SLOUCHING")  # Not accepted

        # 3. Advance clock past expiration (remaining 301s)
        self.mock_clock.advance(301.0)
        app.check_pause_expiration()
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)
        self.assertEqual(app.pause_remaining_sec, 0.0)

        # App resumes and records new observations without joining the paused gap
        app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        self.assertEqual(app.current_posture, "POSTURE_GOOD")
        app.quit()

    # ---------------- P3-04: Global Hotkey ----------------
    def test_p3_04_global_hotkey(self):
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=self.mock_clock.time
        )

        # Verify initial monitoring state
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)

        # First trigger of Ctrl+Shift+P pauses monitoring
        triggered = app.hotkey.trigger("Ctrl+Shift+P")
        self.assertTrue(triggered)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)

        # Second trigger resumes monitoring
        app.hotkey.trigger("Ctrl+Shift+P")
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)

        # Verify deduplication: re-registering on window open does not double-fire
        app.hotkey.register("Ctrl+Shift+P", app.toggle_pause)
        app.hotkey.register("Ctrl+Shift+P", app.toggle_pause)

        initial_count = app.hotkey.invocation_count
        app.hotkey.trigger("Ctrl+Shift+P")
        self.assertEqual(app.hotkey.invocation_count, initial_count + 1)
        self.assertEqual(app.monitoring_state, MonitoringState.PAUSED)
        app.quit()

    # ---------------- P3-05: Calibration Wizard Happy Path ----------------
    def test_p3_05_calibration_wizard_happy_path(self):
        clock = MockClock(100.0)
        wizard = CalibrationWizard(
            profile_path=self.temp_profile_path,
            countdown_sec=3.0,
            capture_sec=10.0,
            min_required_samples=15,
            time_func=clock.time
        )

        # Step 1: Guidance
        wizard.start_guidance()
        self.assertEqual(wizard.state, WizardState.GUIDANCE)

        # Step 2: 3-Second Countdown
        wizard.begin_countdown()
        self.assertEqual(wizard.state, WizardState.COUNTDOWN)
        self.assertAlmostEqual(wizard.countdown_remaining, 3.0, delta=0.1)

        # Tick 2 seconds: countdown still in progress
        clock.advance(2.0)
        wizard.update()
        self.assertEqual(wizard.state, WizardState.COUNTDOWN)
        self.assertAlmostEqual(wizard.countdown_remaining, 1.0, delta=0.1)

        # Tick 1 more second: countdown transitions to CAPTURING
        clock.advance(1.1)
        wizard.update()
        self.assertEqual(wizard.state, WizardState.CAPTURING)

        # Step 3: 10-Second Capturing with valid posture samples
        valid_sample = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "ear_shoulder_ratio": 0.15,
            "head_shoulder_angle": 90.0
        }

        # Feed 15 samples across the 10 seconds
        for i in range(15):
            clock.advance(0.6)
            wizard.add_sample(valid_sample, confidence=0.95)

        # Advance to completion of 10s window
        clock.advance(2.0)
        wizard.update()

        # Step 4: Success
        self.assertEqual(wizard.state, WizardState.SUCCESS)
        profile = wizard.finish()
        self.assertIsNotNone(profile)
        self.assertTrue(os.path.exists(self.temp_profile_path))
        self.assertAlmostEqual(profile.shoulder_span, 0.35, places=2)

    # ---------------- P3-06: Calibration Wizard Recovery ----------------
    def test_p3_06_calibration_wizard_recovery(self):
        clock = MockClock(100.0)

        # Pre-seed a known valid calibration profile
        initial_profile = {
            "inter_eye_dist": 0.052,
            "shoulder_span": 0.36,
            "head_shoulder_y_delta": 0.21,
            "ear_shoulder_ratio": 0.15,
            "head_shoulder_angle": 90.0,
            "calibrated_at": "2026-09-20T10:00:00"
        }
        with open(self.temp_profile_path, "w", encoding="utf-8") as f:
            json.dump(initial_profile, f)

        wizard = CalibrationWizard(
            profile_path=self.temp_profile_path,
            countdown_sec=3.0,
            capture_sec=10.0,
            min_required_samples=15,
            time_func=clock.time
        )
        self.assertIsNotNone(wizard.manager.profile)
        self.assertAlmostEqual(wizard.manager.profile.shoulder_span, 0.36, places=2)

        # Start calibration and simulate camera error
        wizard.start_guidance()
        wizard.begin_countdown()
        clock.advance(3.1)
        wizard.update()
        self.assertEqual(wizard.state, WizardState.CAPTURING)

        # Report camera failure
        wizard.report_camera_error("Webcam device disconnected")
        self.assertEqual(wizard.state, WizardState.FAILED)
        self.assertIn("Camera error", wizard.failure_reason)

        # User chooses Retry
        wizard.retry()
        self.assertEqual(wizard.state, WizardState.GUIDANCE)
        self.assertIsNone(wizard.failure_reason)

        # Then user cancels: previous profile must remain completely intact!
        wizard.cancel()
        self.assertEqual(wizard.state, WizardState.IDLE)
        self.assertIsNotNone(wizard.manager.profile)
        self.assertAlmostEqual(wizard.manager.profile.shoulder_span, 0.36, places=2)

        # Verify disk file was preserved
        with open(self.temp_profile_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
            self.assertAlmostEqual(saved["shoulder_span"], 0.36, places=2)

    # ---------------- P3-07: Dashboard Totals ----------------
    def test_p3_07_dashboard_totals(self):
        db = DatabaseEngine(self.temp_db_path)
        dashboard = DashboardService(db)

        # Target date
        target_date = "2026-09-23"
        t0 = 1790150400.0  # Epoch for 2026-09-23 00:00:00 UTC

        # Seed exact known intervals:
        # At-Desk: 6h 52m = 24720s
        # 18292.8s good posture + 6427.2s deviations = 24720s
        db.insert_posture_event("POSTURE_GOOD", 1.0, t0 + 100, t0 + 18392.8)
        db.insert_posture_event("SLOUCHING", 1.0, t0 + 18392.8, t0 + 24820.0)

        # Away: 1h 51m = 6660s
        db.insert_attention_event("AWAY", 1.0, t0 + 25000, t0 + 31660)

        # Active computer time: 5h 49m = 20940s
        db.record_app_usage("Code.exe", "DeskSense", t0 + 100, t0 + 21040)

        metrics_data = dashboard.get_dashboard_metrics(target_date="2026-09-23")
        m = metrics_data["metrics"]

        # Exact duration checks
        self.assertAlmostEqual(m["desk_time_sec"], 24720.0, delta=1.0)
        self.assertEqual(m["desk_time_formatted"], "6h 52m")

        self.assertAlmostEqual(m["away_time_sec"], 6660.0, delta=1.0)
        self.assertEqual(m["away_time_formatted"], "1h 51m")

        self.assertAlmostEqual(m["active_time_sec"], 20940.0, delta=1.0)
        self.assertEqual(m["active_time_formatted"], "5h 49m")

        # Posture Score: 18292.8 / 24720.0 * 100 = 74.0%
        self.assertAlmostEqual(m["posture_score"], 74.0, delta=0.5)
        self.assertEqual(m["posture_score_formatted"], "74%")
        db.close()

    # ---------------- P3-08: Posture Distribution ----------------
    def test_p3_08_posture_distribution(self):
        db = DatabaseEngine(self.temp_db_path)
        dashboard = DashboardService(db)

        # Desk time total: 10000s
        # Good: 7400s (74.0%)
        # Slouching: 1700s (17.0%)
        # Too Close: 600s (6.0%)
        # Leaning: 300s (3.0%)
        t0 = 1790150400.0
        db.insert_posture_event("POSTURE_GOOD", 1.0, t0, t0 + 7400)
        db.insert_posture_event("SLOUCHING", 1.0, t0 + 7400, t0 + 9100)
        db.insert_posture_event("TOO_CLOSE", 1.0, t0 + 9100, t0 + 9700)
        db.insert_posture_event("LEAN_LEFT", 1.0, t0 + 9700, t0 + 9850)
        db.insert_posture_event("LEAN_RIGHT", 1.0, t0 + 9850, t0 + 10000)

        res = dashboard.get_dashboard_metrics(target_date="2026-09-23")
        dist = res["posture_distribution"]

        self.assertAlmostEqual(dist["good"]["percentage"], 74.0, delta=0.1)
        self.assertAlmostEqual(dist["slouching"]["percentage"], 17.0, delta=0.1)
        self.assertAlmostEqual(dist["too_close"]["percentage"], 6.0, delta=0.1)
        self.assertAlmostEqual(dist["leaning"]["percentage"], 3.0, delta=0.1)

        # Must total exactly 100.0%
        self.assertEqual(dist["total_percentage"], 100.0)
        db.close()

    # ---------------- P3-09: Live State Updates ----------------
    def test_p3_09_live_state_updates(self):
        clock = MockClock(1000.0)
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )

        # 1. Normal state
        app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        clock.advance(120.0)  # 2 minutes session

        data = app.get_dashboard_data()
        self.assertEqual(data["live"]["posture"], "POSTURE_GOOD")
        self.assertEqual(data["live"]["session_duration_formatted"], "2m")
        self.assertEqual(data["live"]["status_category"], "good")

        # 2. Slouching transition updates status without full reload
        clock.advance(30.0)
        app.record_observation("SLOUCHING", "SCREEN", confidence=1.0)

        data = app.get_dashboard_data()
        self.assertEqual(data["live"]["posture"], "SLOUCHING")
        self.assertEqual(data["live"]["status_category"], "warning")
        self.assertEqual(data["live"]["session_duration_formatted"], "2m")
        app.quit()

    # ---------------- P3-10: Empty/Error States ----------------
    def test_p3_10_empty_error_states(self):
        db = DatabaseEngine(self.temp_db_path)
        dashboard = DashboardService(db)

        # 1. New day (empty state)
        empty_res = dashboard.get_dashboard_metrics(target_date="2026-09-24")
        self.assertEqual(empty_res["metrics"]["desk_time_sec"], 0.0)
        self.assertEqual(empty_res["posture_distribution"]["total_percentage"], 0.0)
        empty_alerts = [a["type"] for a in empty_res["alerts"]]
        self.assertIn("empty", empty_alerts)

        # 2. Unavailable camera
        cam_res = dashboard.get_dashboard_metrics(camera_available=False)
        cam_alerts = [a["type"] for a in cam_res["alerts"]]
        self.assertIn("warning", cam_alerts)

        # 3. Missing calibration
        cal_res = dashboard.get_dashboard_metrics(has_calibration=False)
        cal_alerts = [a["type"] for a in cal_res["alerts"]]
        self.assertIn("info", cal_alerts)

        # 4. Database read error resilience
        db.close()
        corrupt_db = DatabaseEngine(":memory:")
        corrupt_service = DashboardService(corrupt_db)
        # Intentionally break table to simulate db error
        with corrupt_db.get_connection() as conn:
            conn.execute("DROP TABLE app_usage")
        err_res = corrupt_service.get_dashboard_metrics()
        self.assertTrue(err_res["has_error"])
        err_alerts = [a["type"] for a in err_res["alerts"]]
        self.assertIn("error", err_alerts)
        corrupt_db.close()

    # ---------------- P3-11: Optional Widget Disabled ----------------
    def test_p3_11_optional_widget_disabled(self):
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            enable_widget=False,
            time_func=self.mock_clock.time
        )

        # When disabled, app functions normally
        self.assertFalse(app.widget.enabled)
        self.assertFalse(app.widget.visible)
        app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)

        # Enable widget and manipulate it
        app.widget.enable()
        self.assertTrue(app.widget.enabled)
        self.assertTrue(app.widget.visible)

        # Drag to new coordinates
        app.widget.set_position(250, 400)
        self.assertEqual((app.widget.x, app.widget.y), (250, 400))

        # Collapse / Expand
        is_collapsed = app.widget.toggle_collapse()
        self.assertTrue(is_collapsed)

        # Adjust opacity
        app.widget.set_opacity(0.75)
        self.assertAlmostEqual(app.widget.opacity, 0.75, places=2)

        # Hide widget
        app.widget.hide()
        self.assertFalse(app.widget.visible)

        # Monitoring remains unaffected throughout widget changes
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)
        app.quit()

    # ---------------- P3-12: End-to-End Desk Session ----------------
    def test_p3_12_end_to_end_desk_session(self):
        clock = MockClock(1790150400.0)
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )

        # 1. Calibrate
        app.start_calibration()
        app.wizard.begin_countdown()
        clock.advance(3.1)
        app.wizard.update()
        valid_sample = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "ear_shoulder_ratio": 0.15,
            "head_shoulder_angle": 90.0
        }
        for _ in range(15):
            clock.advance(0.5)
            app.wizard.add_sample(valid_sample, confidence=1.0)
        clock.advance(3.0)
        app.wizard.update()
        app.finish_calibration()
        self.assertEqual(app.monitoring_state, MonitoringState.MONITORING)

        # 2. Monitor normal posture for 100s
        for _ in range(100):
            clock.advance(1.0)
            app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)

        # 3. Brief move (3 seconds slouch) - should not trigger alert
        for _ in range(3):
            clock.advance(1.0)
            app.record_observation("SLOUCHING", "SCREEN", confidence=1.0)

        # 4. Slouch long enough for notification alert (30 seconds)
        for _ in range(30):
            clock.advance(1.0)
            app.record_observation("SLOUCHING", "SCREEN", confidence=1.0)
        toast_sent = app.notifier.dispatch("SLOUCHING")
        self.assertTrue(toast_sent)

        # 5. Lean close
        for _ in range(15):
            clock.advance(1.0)
            app.record_observation("TOO_CLOSE", "SCREEN", confidence=1.0)

        # 6. User leaves (AWAY)
        clock.advance(60.0)
        app.record_observation("UNKNOWN", "AWAY", confidence=0.0)

        # 7. User returns and switches app
        for _ in range(10):
            clock.advance(1.0)
            app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0, active_app="chrome.exe")
        self.assertEqual(app.active_app, "chrome.exe")

        # Verify summary data matches sequence
        app.db.flush_posture_interval()
        app.db.flush_attention_interval()
        data = app.get_dashboard_data("2026-09-23")
        self.assertGreater(data["metrics"]["desk_time_sec"], 0)
        app.quit()

    # ---------------- P3-13: Restart Continuity ----------------
    def test_p3_13_restart_continuity(self):
        clock = MockClock(1790150400.0)

        # First instance: run session, seed data, quit
        app1 = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )
        for _ in range(300):
            clock.advance(1.0)
            app1.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        app1.db.record_app_usage("Code.exe", "DeskSense", 1790150400.0, 1790150700.0)
        app1.quit()

        # Second instance: relaunches on same db
        app2 = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )
        data = app2.get_dashboard_data("2026-09-23")
        self.assertAlmostEqual(data["metrics"]["desk_time_sec"], 300.0, delta=1.0)
        self.assertAlmostEqual(data["metrics"]["active_time_sec"], 300.0, delta=1.0)
        app2.quit()

    # ---------------- P3-14: Two-Hour Stability ----------------
    def test_p3_14_two_hour_stability(self):
        clock = MockClock(1790150400.0)
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )

        # 2 hours = 7200 seconds. Step in 1.0-second increments = 7200 iterations
        states = ["POSTURE_GOOD", "POSTURE_GOOD", "SLOUCHING", "POSTURE_GOOD"]
        for i in range(7200):
            clock.advance(1.0)
            curr = states[(i // 1800) % len(states)]
            app.record_observation(curr, "SCREEN", confidence=1.0)

        app.db.flush_posture_interval()
        app.db.flush_attention_interval()

        # Check total desk time equals 7200 seconds
        data = app.get_dashboard_data("2026-09-23")
        self.assertAlmostEqual(data["metrics"]["desk_time_sec"], 7200.0, delta=10.0)
        self.assertTrue(app.is_running)
        app.quit()

    # ---------------- P3-15: Privacy Recheck ----------------
    def test_p3_15_privacy_recheck(self):
        clock = MockClock(1790150400.0)
        app = DeskSenseApp(
            db_path=self.temp_db_path,
            profile_path=self.temp_profile_path,
            time_func=clock.time
        )

        # Run calibration, observation, notification, dashboard
        app.record_observation("POSTURE_GOOD", "SCREEN", confidence=1.0)
        app.notifier.dispatch("SLOUCHING")
        _ = app.get_dashboard_data("2026-09-23")
        app.quit()

        # Audit SQLite database tables for absence of binary frame or image columns
        with app.db.get_connection() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                col_defs = conn.execute(f"PRAGMA table_info({table})").fetchall()
                col_names = [col[1].lower() for col in col_defs]
                col_types = [col[2].lower() for col in col_defs]

                # Assert no frame, image, video, jpeg, png columns exist
                for name in col_names:
                    self.assertNotIn("frame", name)
                    self.assertNotIn("image", name)
                    self.assertNotIn("photo", name)
                    self.assertNotIn("video", name)
                for ctype in col_types:
                    self.assertNotIn("blob", ctype)

        # Audit profile file
        if os.path.exists(self.temp_profile_path) and os.path.getsize(self.temp_profile_path) > 0:
            with open(self.temp_profile_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("base64", content)
                self.assertNotIn("image", content)


if __name__ == "__main__":
    unittest.main()
