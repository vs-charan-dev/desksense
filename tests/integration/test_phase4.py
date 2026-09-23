"""
DeskSense Phase 4 Automated Integration Test Suite
Verifies Phone Detection, Adaptive Inference Scheduling, Multi-Signal Fusion,
Work State Engine, Break Intelligence, and Manual Focus Mode.
Tests P4-01 through P4-24.
"""

import os
import time
import tempfile
import unittest
import numpy as np

from src.vision.phone_detector import PhoneDetector, PhoneDetectionResult
from src.vision.phone_scheduler import PhoneInferenceScheduler
from src.vision.phone_fusion import PhoneUsageFusion, PhoneFusionConfig, PhoneSession
from src.system.work_state import WorkStateEngine, WorkState, WorkStateConfig
from src.system.break_tracker import BreakTracker, BreakRecord
from src.system.focus_mode import FocusModeController, FocusSessionStatus
from src.storage.db import DatabaseEngine
from src.app.core import DeskSenseApp


class TestPhase4(unittest.TestCase):

    def setUp(self):
        self.db = DatabaseEngine(":memory:")

    # ---------------- Phone Scheduling & Fusion (P4-01 to P4-07) ----------------

    def test_p4_01_quantized_model_load(self):
        """
        P4-01: Configured lightweight ONNX model loads on CPU without dedicated GPU;
        missing/corrupt model disables phone detection gracefully.
        """
        # 1. Valid model loads on CPU
        model_path = "models/phone_detector_quantized.onnx"
        self.assertTrue(os.path.exists(model_path), f"Expected model file at {model_path}")
        detector = PhoneDetector(model_path=model_path)
        self.assertTrue(detector.is_ready)
        self.assertIsNotNone(detector.session)

        # Test CPU inference with dummy frame in memory
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(dummy_frame)
        self.assertIsInstance(result, PhoneDetectionResult)

        # 2. Missing model disables gracefully without throwing
        missing_detector = PhoneDetector(model_path="models/non_existent_model.onnx")
        self.assertFalse(missing_detector.is_ready)
        res_missing = missing_detector.detect(dummy_frame)
        self.assertFalse(res_missing.detected)

        # 3. Corrupt model disables gracefully
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
            f.write(b"NOT_A_VALID_ONNX_MODEL_CORRUPT_BYTES")
            corrupt_path = f.name

        try:
            corrupt_detector = PhoneDetector(model_path=corrupt_path)
            self.assertFalse(corrupt_detector.is_ready)
            res_corrupt = corrupt_detector.detect(dummy_frame)
            self.assertFalse(res_corrupt.detected)
        finally:
            if os.path.exists(corrupt_path):
                os.remove(corrupt_path)

    def test_p4_02_default_phone_schedule(self):
        """
        P4-02: With no suspicion, object detection runs at 0.5–1 FPS rather than on every camera frame.
        """
        scheduler = PhoneInferenceScheduler(default_fps=0.5, burst_fps=2.0)
        scheduler.update_suspicion(head_down=False)

        # At default 0.5 FPS, interval is 2.0s
        self.assertEqual(scheduler.current_target_fps, 0.5)
        self.assertAlmostEqual(scheduler.current_interval, 2.0, places=2)

        t0 = 1000.0
        # Frame 1 at t=0
        self.assertTrue(scheduler.should_infer(current_time=t0))
        # Intermediate frames (e.g. at 5 FPS camera rate: +0.2s, +0.4s, +1.0s, +1.8s) should be skipped
        self.assertFalse(scheduler.should_infer(current_time=t0 + 0.2))
        self.assertFalse(scheduler.should_infer(current_time=t0 + 0.5))
        self.assertFalse(scheduler.should_infer(current_time=t0 + 1.0))
        self.assertFalse(scheduler.should_infer(current_time=t0 + 1.8))

        # After 2.0 seconds elapsed, inference should run
        self.assertTrue(scheduler.should_infer(current_time=t0 + 2.0))

    def test_p4_03_burst_schedule(self):
        """
        P4-03: Downward head orientation temporarily increases phone inference to
        burst rate (up to 2 FPS) and returns to default afterward.
        """
        scheduler = PhoneInferenceScheduler(default_fps=0.5, burst_fps=2.0)

        # 1. Normal state: 0.5 FPS
        scheduler.update_suspicion(head_down=False)
        self.assertFalse(scheduler.is_burst_mode)
        self.assertEqual(scheduler.current_target_fps, 0.5)

        # 2. Downward orientation triggers burst mode
        is_burst = scheduler.update_suspicion(head_down=True)
        self.assertTrue(is_burst)
        self.assertTrue(scheduler.is_burst_mode)
        self.assertEqual(scheduler.current_target_fps, 2.0)
        self.assertAlmostEqual(scheduler.current_interval, 0.5, places=2)

        t0 = 2000.0
        self.assertTrue(scheduler.should_infer(current_time=t0))
        # Burst mode allows next inference at +0.5s instead of waiting 2.0s
        self.assertFalse(scheduler.should_infer(current_time=t0 + 0.2))
        self.assertTrue(scheduler.should_infer(current_time=t0 + 0.5))

        # 3. Head returns to neutral: burst ends, reverts to default rate
        scheduler.update_suspicion(head_down=False)
        self.assertFalse(scheduler.is_burst_mode)
        self.assertEqual(scheduler.current_target_fps, 0.5)

    def test_p4_04_multi_signal_positive(self):
        """
        P4-04: Phone detection plus proximity/downward-attention evidence sustained
        for configured duration starts one PHONE_USAGE session.
        """
        closed_sessions = []
        fusion = PhoneUsageFusion(
            config=PhoneFusionConfig(start_threshold_seconds=2.0, end_threshold_seconds=3.0),
            on_session_closed=lambda s: closed_sessions.append(s)
        )

        t = 100.0
        # Sustained: phone detected + head down for 2.5s (step 0.5s)
        for _ in range(5):  # t=100.0, 100.5, 101.0, 101.5, 102.0
            is_active = fusion.process_frame(
                timestamp=t,
                phone_detected=True,
                phone_confidence=0.85,
                head_down=True,
                hand_near_phone=True,
                present=True
            )
            t += 0.5

        self.assertTrue(fusion.is_phone_active)
        self.assertTrue(is_active)

    def test_p4_05_single_signal_negatives(self):
        """
        P4-05: A phone lying on table, downward look without phone, or single-frame
        phone detection does not start a phone-use session.
        """
        fusion = PhoneUsageFusion(
            config=PhoneFusionConfig(start_threshold_seconds=2.0)
        )

        # 1. Phone lying on table (no hand, looking at screen)
        for t in np.arange(100.0, 105.0, 0.5):
            active = fusion.process_frame(
                timestamp=float(t),
                phone_detected=True,
                phone_confidence=0.9,
                head_down=False,
                hand_near_phone=False,
                present=True
            )
            self.assertFalse(active)
        self.assertFalse(fusion.is_phone_active)

        # 2. Downward look without phone
        for t in np.arange(110.0, 115.0, 0.5):
            active = fusion.process_frame(
                timestamp=float(t),
                phone_detected=False,
                head_down=True,
                hand_near_phone=False,
                present=True
            )
            self.assertFalse(active)
        self.assertFalse(fusion.is_phone_active)

        # 3. Single-frame phone spike (e.g. 0.2s then gone)
        active1 = fusion.process_frame(
            timestamp=120.0,
            phone_detected=True,
            phone_confidence=0.8,
            head_down=True,
            hand_near_phone=True,
            present=True
        )
        self.assertFalse(active1)
        active2 = fusion.process_frame(
            timestamp=120.5,
            phone_detected=False,
            head_down=False,
            present=True
        )
        self.assertFalse(active2)
        self.assertFalse(fusion.is_phone_active)
        self.assertEqual(len(fusion.completed_sessions), 0)

    def test_p4_06_session_close_debounce(self):
        """
        P4-06: Loss of fused condition for configured end threshold closes session
        once with correct start, end, duration, and confidence; brief dropouts do not split it.
        """
        closed_sessions = []
        fusion = PhoneUsageFusion(
            config=PhoneFusionConfig(start_threshold_seconds=2.0, end_threshold_seconds=3.0),
            on_session_closed=lambda s: closed_sessions.append(s)
        )

        # Start session: t=100.0 to 103.0 (3 seconds)
        for t in np.arange(100.0, 103.0, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=True,
                phone_confidence=0.9,
                head_down=True,
                present=True
            )
        self.assertTrue(fusion.is_phone_active)

        # Brief dropout for 1.5s (less than 3.0s end threshold)
        for t in np.arange(103.0, 104.5, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=False,
                head_down=False,
                present=True
            )
        # Session must remain continuous (not split!)
        self.assertTrue(fusion.is_phone_active)
        self.assertEqual(len(closed_sessions), 0)

        # Resume active usage for 2.0s
        for t in np.arange(104.5, 106.5, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=True,
                phone_confidence=0.85,
                head_down=True,
                present=True
            )
        self.assertTrue(fusion.is_phone_active)

        # Sustained end: condition lost for >= 3.0s (t=106.5 to 110.0)
        for t in np.arange(106.5, 110.5, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=False,
                head_down=False,
                present=True
            )

        self.assertFalse(fusion.is_phone_active)
        # Exactly one session closed
        self.assertEqual(len(closed_sessions), 1)
        s = closed_sessions[0]
        self.assertIsInstance(s, PhoneSession)
        self.assertGreaterEqual(s.duration, 5)
        self.assertGreater(s.confidence, 0.7)

    def test_p4_07_phone_wording(self):
        """
        P4-07: UI/analytics label results as 'estimated phone usage', never exact usage.
        """
        fusion = PhoneUsageFusion()
        stats = fusion.get_estimated_phone_usage_stats()
        self.assertIn("estimated_phone_usage", stats)
        self.assertIn("estimated_sessions", stats)
        self.assertEqual(stats["wording"], "estimated phone usage")

        # Verify database summary adheres to same mandatory wording
        self.db.log_phone_session("2026-09-23T10:00:00", "2026-09-23T10:05:00", 300, 0.9)
        db_summary = self.db.get_phone_summary()
        self.assertIn("estimated_phone_usage", db_summary)
        self.assertIn("estimated_sessions", db_summary)
        self.assertEqual(db_summary["wording"], "estimated phone usage")

    # ---------------- Work State Engine & State Logic (P4-08 to P4-15) ----------------

    def test_p4_08_work_state_focused_work(self):
        """
        P4-08: Present + screen + productive app + recent input + no phone -> FOCUSED_WORK.
        """
        engine = WorkStateEngine()
        state = engine.classify_state(
            timestamp=100.0,
            present=True,
            attention="SCREEN",
            app_category="productive",
            idle_seconds=5.0,
            phone_active=False,
            signals_reliable=True
        )
        self.assertEqual(state, WorkState.FOCUSED_WORK)

    def test_p4_09_work_state_active_work(self):
        """
        P4-09: Present + recent input + neutral app + no phone -> ACTIVE_WORK.
        """
        engine = WorkStateEngine()
        state = engine.classify_state(
            timestamp=100.0,
            present=True,
            attention="SCREEN",
            app_category="neutral",
            idle_seconds=10.0,
            phone_active=False,
            signals_reliable=True
        )
        self.assertEqual(state, WorkState.ACTIVE_WORK)

    def test_p4_10_work_state_distracted(self):
        """
        P4-10: Present + non-productive app or prolonged look-away -> DISTRACTED.
        """
        engine = WorkStateEngine(config=WorkStateConfig(lookaway_distraction_threshold=10.0))

        # 1. Non-productive / distracting app
        state_app = engine.classify_state(
            timestamp=100.0,
            present=True,
            attention="SCREEN",
            app_category="distracting",
            idle_seconds=5.0,
            phone_active=False,
            signals_reliable=True
        )
        self.assertEqual(state_app, WorkState.DISTRACTED)

        # 2. Prolonged look-away (> 10s)
        engine.classify_state(timestamp=100.0, present=True, attention="AWAY", app_category="productive")
        state_lookaway = engine.classify_state(
            timestamp=115.0,  # 15s elapsed looking away
            present=True,
            attention="AWAY",
            app_category="productive",
            phone_active=False,
            signals_reliable=True
        )
        self.assertEqual(state_lookaway, WorkState.DISTRACTED)

    def test_p4_11_work_state_phone_usage(self):
        """
        P4-11: Present + fused phone-use condition -> PHONE_USAGE.
        PHONE_USAGE must not be counted simultaneously as focused work.
        """
        engine = WorkStateEngine()
        state = engine.classify_state(
            timestamp=100.0,
            present=True,
            attention="DOWN",
            app_category="productive",  # Productive app in background does not override phone
            idle_seconds=2.0,
            phone_active=True,
            signals_reliable=True
        )
        self.assertEqual(state, WorkState.PHONE_USAGE)
        self.assertNotEqual(state, WorkState.FOCUSED_WORK)

    def test_p4_12_work_state_idle(self):
        """
        P4-12: Present + no recent computer input -> IDLE.
        """
        engine = WorkStateEngine(config=WorkStateConfig(idle_threshold_seconds=60.0))
        state = engine.classify_state(
            timestamp=100.0,
            present=True,
            attention="SCREEN",
            app_category="productive",
            idle_seconds=120.0,  # > 60s idle
            phone_active=False,
            signals_reliable=True
        )
        self.assertEqual(state, WorkState.IDLE)

    def test_p4_13_work_state_away_and_break(self):
        """
        P4-13: Absent beyond threshold -> AWAY; after configured break threshold -> BREAK.
        """
        engine = WorkStateEngine(
            config=WorkStateConfig(absence_away_threshold=15.0, absence_break_threshold=120.0)
        )

        # Absent for 30s (>= 15s away threshold, but < 120s break threshold)
        engine.classify_state(timestamp=100.0, present=False)
        state_away = engine.classify_state(timestamp=130.0, present=False)
        self.assertEqual(state_away, WorkState.AWAY)

        # Absent for 150s (>= 120s break threshold)
        state_break = engine.classify_state(timestamp=250.0, present=False)
        self.assertEqual(state_break, WorkState.BREAK)

    def test_p4_14_work_state_unknown(self):
        """
        P4-14: Missing/unreliable required signals -> UNKNOWN rather than optimistic work state.
        """
        engine = WorkStateEngine()
        state = engine.classify_state(
            timestamp=100.0,
            present=True,
            signals_reliable=False  # Camera down or tracking lost
        )
        self.assertEqual(state, WorkState.UNKNOWN)

        state_none = engine.classify_state(
            timestamp=100.0,
            present=None,
            signals_reliable=True
        )
        self.assertEqual(state_none, WorkState.UNKNOWN)

    def test_p4_15_state_transition_accounting(self):
        """
        P4-15: Synthetic day with known transitions produces non-overlapping intervals
        whose durations equal elapsed monitored time.
        """
        engine = WorkStateEngine(config=WorkStateConfig(absence_away_threshold=10.0, absence_break_threshold=60.0))
        t = 1000.0

        # Sequence of intervals:
        # 1. Focused work for 60s (t=1000..1060)
        for _ in range(6):
            engine.update(t, present=True, attention="SCREEN", app_category="productive")
            t += 10.0

        # 2. Phone usage for 40s (t=1060..1100)
        for _ in range(4):
            engine.update(t, present=True, attention="DOWN", phone_active=True)
            t += 10.0

        # 3. Idle for 30s (t=1100..1130)
        for _ in range(3):
            engine.update(t, present=True, idle_seconds=90.0)
            t += 10.0

        # 4. Away for 30s (t=1130..1160)
        for _ in range(3):
            engine.update(t, present=False)
            t += 10.0

        # Flush final interval at t=1160
        engine.flush(timestamp=t)

        intervals = engine.intervals
        self.assertGreaterEqual(len(intervals), 4)

        # Verify non-overlapping continuity
        for i in range(len(intervals) - 1):
            self.assertAlmostEqual(intervals[i].end_time, intervals[i + 1].start_time)

        # Total duration must equal elapsed time (1160 - 1000 = 160 seconds)
        total_accounted = sum(iv.duration for iv in intervals)
        self.assertEqual(total_accounted, 160)

    # ---------------- Break Intelligence & Focus Mode (P4-16 to P4-18) ----------------

    def test_p4_16_automatic_break(self):
        """
        P4-16: Sustained absence creates one break with correct duration;
        return closes it automatically.
        """
        completed_breaks = []
        tracker = BreakTracker(
            break_threshold_seconds=60.0,
            on_break_completed=lambda b: completed_breaks.append(b)
        )

        t = 500.0
        # User at desk
        tracker.update(t, present=True)

        # User leaves desk at t=510
        t = 510.0
        tracker.update(t, present=False)

        # Sustained absence for 120s (t=510..630)
        t = 630.0
        tracker.update(t, present=False)
        self.assertTrue(tracker.break_active)

        # User returns at t=640
        t = 640.0
        result_break = tracker.update(t, present=True)

        self.assertIsNotNone(result_break)
        self.assertEqual(len(completed_breaks), 1)
        self.assertEqual(completed_breaks[0].duration, 130)  # 640 - 510 = 130s
        self.assertFalse(tracker.break_active)

    def test_p4_17_sedentary_reminder(self):
        """
        P4-17: More than 60 uninterrupted seated minutes requests one reminder;
        a qualifying break resets the timer.
        """
        reminders = []
        tracker = BreakTracker(
            sedentary_limit_seconds=3600.0,  # 60m
            qualifying_break_reset_seconds=120.0,  # 2m
            on_sedentary_reminder=lambda: reminders.append(True)
        )

        t = 0.0
        tracker.update(t, present=True)

        # Advance to 3590s (under 60 minutes)
        tracker.update(3590.0, present=True)
        self.assertEqual(len(reminders), 0)

        # Reach 3605s (> 60 uninterrupted minutes) -> requests exactly one reminder
        tracker.update(3605.0, present=True)
        self.assertEqual(len(reminders), 1)

        # Does not spam additional reminders in same uninterrupted sitting period
        tracker.update(3700.0, present=True)
        self.assertEqual(len(reminders), 1)

        # Brief departure for 15s (< qualifying 120s break) does NOT reset continuous seated timer
        tracker.update(3715.0, present=False)
        tracker.update(3730.0, present=True)
        self.assertGreaterEqual(tracker.continuous_seated_seconds, 3600.0)

        # Qualifying break for 150s (>= 120s) RESETS the continuous seated timer
        tracker.update(3800.0, present=False)
        tracker.update(3950.0, present=True)
        self.assertEqual(tracker.continuous_seated_seconds, 0.0)
        self.assertFalse(tracker.sedentary_alerted)

    def test_p4_18_manual_focus_mode(self):
        """
        P4-18: Start, pause/cancel, and completion work for Pomodoro/custom durations;
        phone sensitivity changes only during focus session and is restored afterward.
        """
        fusion = PhoneUsageFusion()
        focus = FocusModeController(phone_fusion=fusion)

        # Normal phone start threshold
        self.assertEqual(fusion.active_start_threshold, fusion.config.start_threshold_seconds)

        # 1. Start 25-minute Pomodoro: heightened phone sensitivity enabled
        focus.start(duration_minutes=25)
        self.assertTrue(focus.is_active)
        self.assertEqual(focus.status, FocusSessionStatus.RUNNING)
        self.assertEqual(fusion.active_start_threshold, fusion.config.focus_mode_start_threshold)

        # 2. Pause and resume
        focus.pause()
        self.assertEqual(focus.status, FocusSessionStatus.PAUSED)
        focus.resume()
        self.assertEqual(focus.status, FocusSessionStatus.RUNNING)

        # 3. Cancel restores normal phone sensitivity
        focus.cancel()
        self.assertEqual(focus.status, FocusSessionStatus.CANCELLED)
        self.assertEqual(fusion.active_start_threshold, fusion.config.start_threshold_seconds)

        # 4. Completion restores normal sensitivity
        focus.start(custom_seconds=10)
        self.assertEqual(fusion.active_start_threshold, fusion.config.focus_mode_start_threshold)
        res = focus.update(current_time=time.time() + 15)
        self.assertIsNotNone(res)
        self.assertTrue(res.completed)
        self.assertEqual(focus.status, FocusSessionStatus.COMPLETED)
        self.assertEqual(fusion.active_start_threshold, fusion.config.start_threshold_seconds)

    # ---------------- Controlled Phone Evaluation (P4-19 to P4-24) ----------------

    def test_p4_19_scenario_actively_use_phone_while_looking_down(self):
        """
        P4-19: Actively use phone while looking down.
        Must be detected in at least 4 of 5 attempts.
        """
        success_count = 0
        for _ in range(5):
            fusion = PhoneUsageFusion(config=PhoneFusionConfig(start_threshold_seconds=2.0))
            detected = False
            for t in np.arange(0.0, 3.5, 0.5):
                if fusion.process_frame(
                    timestamp=float(t),
                    phone_detected=True,
                    phone_confidence=0.9,
                    head_down=True,
                    hand_near_phone=True,
                    present=True
                ):
                    detected = True
            if detected:
                success_count += 1

        self.assertGreaterEqual(success_count, 4)

    def test_p4_20_scenario_phone_on_table(self):
        """
        P4-20: Phone on table without interaction.
        Must produce at most 1 false session in 5 attempts.
        """
        false_count = 0
        for _ in range(5):
            fusion = PhoneUsageFusion(config=PhoneFusionConfig(start_threshold_seconds=2.0))
            detected = False
            for t in np.arange(0.0, 3.5, 0.5):
                if fusion.process_frame(
                    timestamp=float(t),
                    phone_detected=True,
                    phone_confidence=0.85,
                    head_down=False,
                    hand_near_phone=False,
                    present=True
                ):
                    detected = True
            if detected:
                false_count += 1

        self.assertLessEqual(false_count, 1)

    def test_p4_21_scenario_hold_phone_without_using(self):
        """
        P4-21: Hold phone without looking at it (facing screen).
        Must produce at most 1 false session in 5 attempts.
        """
        false_count = 0
        for _ in range(5):
            fusion = PhoneUsageFusion(config=PhoneFusionConfig(start_threshold_seconds=2.0))
            detected = False
            for t in np.arange(0.0, 3.5, 0.5):
                if fusion.process_frame(
                    timestamp=float(t),
                    phone_detected=True,
                    phone_confidence=0.8,
                    head_down=False,  # Facing computer screen
                    hand_near_phone=True,
                    present=True
                ):
                    detected = True
            if detected:
                false_count += 1

        self.assertLessEqual(false_count, 1)

    def test_p4_22_scenario_look_down_no_phone(self):
        """
        P4-22: Look down with no phone detected.
        Must produce at most 1 false session in 5 attempts.
        """
        false_count = 0
        for _ in range(5):
            fusion = PhoneUsageFusion(config=PhoneFusionConfig(start_threshold_seconds=2.0))
            detected = False
            for t in np.arange(0.0, 3.5, 0.5):
                if fusion.process_frame(
                    timestamp=float(t),
                    phone_detected=False,
                    head_down=True,
                    hand_near_phone=False,
                    present=True
                ):
                    detected = True
            if detected:
                false_count += 1

        self.assertLessEqual(false_count, 1)

    def test_p4_23_scenario_write_read_on_paper(self):
        """
        P4-23: Writing or reading on desk paper (no phone).
        Must produce at most 1 false session in 5 attempts.
        """
        false_count = 0
        for _ in range(5):
            fusion = PhoneUsageFusion(config=PhoneFusionConfig(start_threshold_seconds=2.0))
            detected = False
            for t in np.arange(0.0, 3.5, 0.5):
                if fusion.process_frame(
                    timestamp=float(t),
                    phone_detected=False,
                    head_down=True,
                    hand_near_phone=True,  # Hand holds pen
                    present=True
                ):
                    detected = True
            if detected:
                false_count += 1

        self.assertLessEqual(false_count, 1)

    def test_p4_24_scenario_put_phone_down_after_use(self):
        """
        P4-24: Put phone down after use.
        Existing session closes after the end threshold and is stored once.
        """
        closed = []
        fusion = PhoneUsageFusion(
            config=PhoneFusionConfig(start_threshold_seconds=2.0, end_threshold_seconds=3.0),
            on_session_closed=lambda s: closed.append(s)
        )

        # Active use for 3.0 seconds
        for t in np.arange(0.0, 3.5, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=True,
                phone_confidence=0.9,
                head_down=True,
                hand_near_phone=True,
                present=True
            )
        self.assertTrue(fusion.is_phone_active)

        # Put phone down on table at t=3.5 (no longer holding or looking down)
        for t in np.arange(3.5, 7.5, 0.5):
            fusion.process_frame(
                timestamp=float(t),
                phone_detected=True,  # Still visible on table
                phone_confidence=0.8,
                head_down=False,  # Returned gaze to monitor
                hand_near_phone=False,  # Hands on keyboard
                present=True
            )

        # Session has closed and is stored once
        self.assertFalse(fusion.is_phone_active)
        self.assertEqual(len(closed), 1)
        self.assertGreaterEqual(closed[0].duration, 3)


if __name__ == "__main__":
    unittest.main()
