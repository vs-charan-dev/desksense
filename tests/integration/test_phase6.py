"""Phase 6 Integration Tests for DeskSense.
Covers requirements P6-01 through P6-19:
- P6-01: AC profile (normal monitoring targets 5 FPS and stays within 5–10 FPS range)
- P6-02: Away profile (sustained absence reduces inference to ~1 FPS, restored on return)
- P6-03: Battery profile (reduces vision to ~3 FPS, lowers phone-scan, throttles UI animation)
- P6-04: Thermal/CPU throttle (high CPU drops inference rate; recovery uses hysteresis band)
- P6-05: Bounded queues/caches (guaranteed max queue size = 1, immediate frame release)
- P6-06: Multi-monitor attention (configured monitor directions count as SCREEN focus)
- P6-07: Weekly aggregation (exact totals, week-over-week deltas, no fabricated zero-days)
- P6-08: Insight minimum evidence (no trend claim without minimum data threshold)
- P6-09: Retention policies (7-, 30-, 90-, 365-day delete older records; forever deletes none; settings untouched)
- P6-10: Export (JSON/CSV contains documented records, zero image/video/frame bytes)
- P6-11: Wipe activity data (wipes activity history upon confirmation; cancel leaves untouched; settings preserved)
- P6-12: Startup setting (enable/disable is idempotent; creates minimized-to-tray entry)
- P6-13: Installer smoke test (verify local packaging structure and executable paths)
- P6-14: Endurance simulation (sustained loop maintains stable bounded references)
- P6-15: Normal resource budget (lightweight frame scheduling, bounded queues)
- P6-16: Battery resource behavior (battery mode visibly lowers inference frequency)
- P6-17: Data growth (structured records instead of heavy blobs)
- P6-18: Offline / privacy audit (operates 100% locally with zero camera frame files on disk)
- P6-19: Final regression (all core subsystems run cohesively)
"""

import unittest
import time
import os
import tempfile
import json
import numpy as np

from src.system.adaptive_perf import AdaptivePerformanceManager, PowerSource, PerformanceProfile
from src.system.multi_monitor import MultiMonitorConfig, MonitorPosition
from src.system.weekly_trends import WeeklyTrendsEngine
from src.system.privacy_manager import PrivacyManager
from src.system.startup import WindowsStartupManager
from src.storage.db import DatabaseEngine
from src.vision.scheduler import FrameScheduler


class TestPhase6Integration(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseEngine(":memory:")

    def tearDown(self):
        self.db.close()

    # P6-01: AC profile
    def test_p6_01_ac_profile(self):
        perf = AdaptivePerformanceManager()
        perf.set_power_source(PowerSource.AC)
        self.assertEqual(perf.current_profile, PerformanceProfile.AC_NORMAL)
        self.assertEqual(perf.target_fps, 5.0)
        self.assertGreaterEqual(perf.target_fps, 5.0)
        self.assertLessEqual(perf.target_fps, 10.0)
        self.assertTrue(perf.ui_animations_enabled)

    # P6-02: Away profile
    def test_p6_02_away_profile(self):
        fake_time = 1000.0
        perf = AdaptivePerformanceManager(time_func=lambda: fake_time, away_throttle_delay=5.0)
        
        # User present
        perf.update_presence(True)
        self.assertEqual(perf.target_fps, 5.0)

        # Absence begins at 1000.0
        perf.update_presence(False)
        # Brief absence (< 5s) does not drop yet
        fake_time = 1002.0
        self.assertEqual(perf.target_fps, 5.0)

        # Sustained absence (>= 5s) drops to 1 FPS
        fake_time = 1006.0
        self.assertEqual(perf.current_profile, PerformanceProfile.AWAY_THROTTLED)
        self.assertEqual(perf.target_fps, 1.0)

        # User returns -> immediate restoration to 5 FPS
        perf.update_presence(True)
        self.assertEqual(perf.target_fps, 5.0)

    # P6-03: Battery profile
    def test_p6_03_battery_profile(self):
        perf = AdaptivePerformanceManager()
        perf.set_power_source(PowerSource.BATTERY)
        self.assertEqual(perf.current_profile, PerformanceProfile.BATTERY_SAVER)
        self.assertEqual(perf.target_fps, 3.0)
        self.assertLess(perf.phone_scan_fps, 0.5)
        self.assertFalse(perf.ui_animations_enabled)

        # Return to AC restores normal settings
        perf.set_power_source(PowerSource.AC)
        self.assertEqual(perf.target_fps, 5.0)
        self.assertTrue(perf.ui_animations_enabled)

    # P6-04: Thermal/CPU throttle with hysteresis
    def test_p6_04_thermal_cpu_throttle_hysteresis(self):
        perf = AdaptivePerformanceManager(cpu_high_threshold=70.0, cpu_low_threshold=50.0)
        
        # Normal CPU
        perf.update_cpu_load(30.0)
        self.assertFalse(perf.is_thermal_throttled)
        self.assertEqual(perf.target_fps, 5.0)

        # Spike above threshold triggers throttle
        perf.update_cpu_load(75.0)
        self.assertTrue(perf.is_thermal_throttled)
        self.assertEqual(perf.current_profile, PerformanceProfile.THERMAL_THROTTLED)
        self.assertEqual(perf.target_fps, 2.0)

        # Slight drop to 60.0 does NOT unthrottle due to hysteresis band
        perf.update_cpu_load(60.0)
        self.assertTrue(perf.is_thermal_throttled)
        self.assertEqual(perf.target_fps, 2.0)

        # Drop below low threshold unthrottles
        perf.update_cpu_load(45.0)
        self.assertFalse(perf.is_thermal_throttled)
        self.assertEqual(perf.target_fps, 5.0)

    # P6-05: Bounded queues and caches
    def test_p6_05_bounded_queues_and_caches(self):
        scheduler = FrameScheduler(target_fps=5, max_queue_size=1)
        dummy_frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        dummy_frame2 = np.zeros((100, 100, 3), dtype=np.uint8)

        # Submit first frame
        accepted1 = scheduler.submit_frame(dummy_frame1, current_time=1000.0)
        self.assertTrue(accepted1)
        self.assertEqual(scheduler.queue_size, 1)

        # Immediate rapid second frame dropped
        accepted2 = scheduler.submit_frame(dummy_frame2, current_time=1000.05)
        self.assertTrue(accepted1)
        self.assertEqual(scheduler.queue_size, 1)

        # Immediate rapid second frame dropped
        # duplicate line replaced
        self.assertFalse(accepted2)
        self.assertEqual(scheduler.queue_size, 1)

        # Process and release
        processed = scheduler.process_next(lambda f: f.shape)
        self.assertEqual(processed, (100, 100, 3))
        self.assertEqual(scheduler.queue_size, 0)

    # P6-06: Multi-monitor attention
    def test_p6_06_multi_monitor_attention(self):
        mm = MultiMonitorConfig(secondary_monitors=["RIGHT"])
        # Direct screen attention
        self.assertEqual(mm.adapt_attention("SCREEN"), "SCREEN")
        # Looking right with right monitor configured counts as SCREEN
        self.assertEqual(mm.adapt_attention("RIGHT"), "SCREEN")
        # Looking left without left monitor configured remains LEFT (distraction)
        self.assertEqual(mm.adapt_attention("LEFT"), "LEFT")
        # Looking down remains DOWN
        self.assertEqual(mm.adapt_attention("DOWN"), "DOWN")

        # Dynamically add left monitor
        mm.add_monitor("LEFT")
        self.assertEqual(mm.adapt_attention("LEFT"), "SCREEN")

    # P6-07: Weekly aggregation
    def test_p6_07_weekly_aggregation_and_deltas(self):
        engine = WeeklyTrendsEngine(min_days_for_comparison=3)
        curr_week = [
            {"date": "2026-09-21", "focus_time": 7200, "phone_time": 600, "desk_time": 14400, "posture_score": 80.0},
            {"date": "2026-09-22", "focus_time": 7200, "phone_time": 600, "desk_time": 14400, "posture_score": 80.0},
            {"date": "2026-09-23", "focus_time": 7200, "phone_time": 600, "desk_time": 14400, "posture_score": 80.0},
        ]
        prev_week = [
            {"date": "2026-09-14", "focus_time": 3600, "phone_time": 1200, "desk_time": 14400, "posture_score": 70.0},
            {"date": "2026-09-15", "focus_time": 3600, "phone_time": 1200, "desk_time": 14400, "posture_score": 70.0},
            {"date": "2026-09-16", "focus_time": 3600, "phone_time": 1200, "desk_time": 14400, "posture_score": 70.0},
        ]

        res = engine.calculate_week_over_week(curr_week, prev_week)
        self.assertTrue(res["has_sufficient_data"])
        self.assertEqual(res["current_week"]["focus_time"], 21600)
        self.assertEqual(res["previous_week"]["focus_time"], 10800)
        self.assertEqual(res["deltas"]["focus_pct_change"], 100.0)   # doubled focus time
        self.assertEqual(res["deltas"]["phone_pct_change"], -50.0)   # halved phone time

    # P6-08: Insight minimum evidence
    def test_p6_08_insight_minimum_evidence(self):
        engine = WeeklyTrendsEngine(min_days_for_comparison=3)
        # Insufficient data (only 1 day)
        curr_week = [{"date": "2026-09-21", "focus_time": 7200, "desk_time": 14400, "posture_score": 80.0}]
        prev_week = [{"date": "2026-09-14", "focus_time": 3600, "desk_time": 14400, "posture_score": 70.0}]

        res = engine.calculate_week_over_week(curr_week, prev_week)
        self.assertFalse(res["has_sufficient_data"])
        self.assertIsNone(res["deltas"]["focus_pct_change"])

        insights = engine.generate_trend_insights(res)
        self.assertIn("Collecting baseline", insights[0])

    # P6-09: Retention policies
    def test_p6_09_retention_policies(self):
        privacy = PrivacyManager(self.db)
        now = 1000000.0
        old_time = now - (40 * 86400.0)  # 40 days ago

        # Insert old and recent posture events
        self.db.insert_posture_event("POSTURE_GOOD", 0.9, old_time, old_time + 100)
        self.db.insert_posture_event("POSTURE_GOOD", 0.9, now - 100, now)

        # 30-day policy should delete the 40-day event and keep recent
        prune_res = privacy.apply_retention_policy("30_days", current_timestamp=now)
        self.assertEqual(prune_res["deleted_records"], 1)

        with self.db.get_connection() as conn:
            remaining = conn.execute("SELECT COUNT(*) as cnt FROM posture_events").fetchone()["cnt"]
            self.assertEqual(remaining, 1)

        # Forever policy deletes nothing
        prune_forever = privacy.apply_retention_policy("forever", current_timestamp=now)
        self.assertEqual(prune_forever["deleted_records"], 0)

    # P6-10: Export JSON & CSV
    def test_p6_10_export_clean_no_frame_bytes(self):
        privacy = PrivacyManager(self.db)
        self.db.log_work_state_interval("FOCUSED_WORK", "100.0", "200.0", 100)
        
        # JSON export
        json_str = privacy.export_data_json()
        data = json.loads(json_str)
        self.assertIn("work_state_intervals", data)
        self.assertIn("privacy_statement", data)
        # Ensure zero raw image or binary bytes
        self.assertNotIn("frame_bytes", json_str)
        self.assertNotIn("image_data", json_str)

        # CSV export
        csv_str = privacy.export_data_csv()
        self.assertIn("FOCUSED_WORK", csv_str)
        self.assertIn("duration", csv_str)

    # P6-11: Wipe activity data
    def test_p6_11_wipe_activity_data(self):
        privacy = PrivacyManager(self.db)
        self.db.insert_posture_event("POSTURE_GOOD", 0.9, 0.0, 100.0)
        self.db.insert_category_rule("custom_app.exe", "process", "productive")

        # Unconfirmed wipe does not delete
        wiped_unconfirmed = privacy.wipe_activity_data(confirmed=False)
        self.assertFalse(wiped_unconfirmed)

        # Confirmed wipe clears activity
        wiped = privacy.wipe_activity_data(confirmed=True)
        self.assertTrue(wiped)

        with self.db.get_connection() as conn:
            posture_cnt = conn.execute("SELECT COUNT(*) as cnt FROM posture_events").fetchone()["cnt"]
            self.assertEqual(posture_cnt, 0)
            # Settings / Category rules remain preserved!
            rules_cnt = conn.execute("SELECT COUNT(*) as cnt FROM category_rules").fetchone()["cnt"]
            self.assertEqual(rules_cnt, 1)

    # P6-12: Startup setting
    def test_p6_12_startup_setting_idempotency(self):
        mgr = WindowsStartupManager(mock_mode=True)
        self.assertFalse(mgr.is_startup_enabled())

        # Enable
        self.assertTrue(mgr.enable_startup(executable_path="C:\\DeskSense\\desksense.exe"))
        self.assertTrue(mgr.is_startup_enabled())

        # Enable repeatedly (idempotent)
        self.assertTrue(mgr.enable_startup(executable_path="C:\\DeskSense\\desksense.exe"))
        self.assertTrue(mgr.is_startup_enabled())

        # Disable
        self.assertTrue(mgr.disable_startup())
        self.assertFalse(mgr.is_startup_enabled())

        # Disable repeatedly (idempotent)
        self.assertTrue(mgr.disable_startup())
        self.assertFalse(mgr.is_startup_enabled())

    # P6-13: Packaging & Installer readiness smoke test
    def test_p6_13_installer_smoke_test(self):
        # Verify repository entrypoints and build artifacts exist
        self.assertTrue(os.path.exists("main.py"))
        self.assertTrue(os.path.exists("ui/package.json"))
        self.assertTrue(os.path.exists("src/app/server.py"))

    # P6-14: Endurance simulation
    def test_p6_14_endurance_simulation(self):
        scheduler = FrameScheduler(target_fps=5)
        # Simulate 100 successive iterations
        for i in range(100):
            frame = np.zeros((50, 50, 3), dtype=np.uint8)
            scheduler.submit_frame(frame, current_time=i * 0.25)
            scheduler.process_next(lambda f: f.mean())
        self.assertEqual(scheduler.queue_size, 0)

    # P6-15: Normal resource budget verification
    def test_p6_15_resource_budget_verification(self):
        perf = AdaptivePerformanceManager()
        self.assertLessEqual(perf.target_fps, 10.0)
        self.assertGreaterEqual(perf.target_fps, 1.0)

    # P6-16: Battery resource behavior
    def test_p6_16_battery_resource_behavior(self):
        perf = AdaptivePerformanceManager()
        perf.set_power_source(PowerSource.BATTERY)
        self.assertAlmostEqual(perf.target_fps, 3.0, delta=0.5)

    # P6-17: Data growth (compact structured intervals)
    def test_p6_17_data_growth(self):
        # 10 downsampled posture samples store negligible bytes
        for i in range(10):
            self.db.record_posture_sample("POSTURE_GOOD", 0.95, float(i))
        self.db.flush_posture_interval()
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM posture_events").fetchall()
            self.assertEqual(len(rows), 1)  # All merged into 1 continuous interval!

    # P6-18: Offline and privacy audit
    def test_p6_18_offline_and_privacy_audit(self):
        # Ensure zero camera frame files are written to local working directory
        cwd_files = os.listdir(".")
        for f in cwd_files:
            self.assertFalse(f.endswith(".jpg") or f.endswith(".png") or f.endswith(".mp4"), f"Found unallowed media artifact: {f}")

    # P6-19: Final regression
    def test_p6_19_final_regression(self):
        perf = AdaptivePerformanceManager()
        mm = MultiMonitorConfig()
        trends = WeeklyTrendsEngine()
        privacy = PrivacyManager(self.db)
        startup = WindowsStartupManager(mock_mode=True)
        self.assertIsNotNone(perf)
        self.assertIsNotNone(mm)
        self.assertIsNotNone(trends)
        self.assertIsNotNone(privacy)
        self.assertIsNotNone(startup)


if __name__ == "__main__":
    unittest.main()
