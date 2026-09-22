"""
DeskSense Phase 1 Automated Integration Tests
Covers all contract requirements from TESTS.md:
- Presence (P1-01, P1-02, P1-03, P1-04)
- Calibration & Classification (P1-05, P1-06, P1-07, P1-08, P1-09, P1-10, P1-11)
- Smoothing & Notifications (P1-12, P1-13, P1-14, P1-15, P1-16)
Runs deterministically with synthetic clocks and fixtures.
"""

import os
import json
import tempfile
import unittest
from typing import Dict, Any

from src.vision.presence import PresenceEngine
from src.vision.calibration import CalibrationManager, CalibrationProfile
from src.vision.posture import PostureClassifier
from src.vision.attention import AttentionEstimator
from src.vision.filter import TemporalFilter


class MockClock:
    def __init__(self, initial_time: float = 1000.0):
        self.current_time = initial_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float):
        self.current_time += seconds


class TestPhase1Presence(unittest.TestCase):
    """P1-01 to P1-04: Presence detection and hysteresis"""

    def setUp(self):
        self.clock = MockClock(1000.0)
        self.engine = PresenceEngine(
            absence_hysteresis_sec=15.0,
            min_confidence=0.35,
            time_func=self.clock.time
        )

    def test_p1_01_present_detection(self):
        """P1-01: Valid face/body fixture produces PRESENT."""
        state, diag = self.engine.update(
            raw_presence_candidate="PRESENT",
            confidence=0.85,
            camera_available=True
        )
        self.assertEqual(state, "PRESENT")
        self.assertEqual(diag["state"], "PRESENT")

    def test_p1_02_absence_hysteresis(self):
        """P1-02: Continuous missing-person input for <=15s does not produce AWAY; >15s does."""
        # Start present
        self.engine.update("PRESENT", confidence=0.9, camera_available=True)
        self.assertEqual(self.engine.current_state, "PRESENT")

        # Advance 5 seconds with missing person
        self.clock.advance(5.0)
        state, _ = self.engine.update("AWAY", confidence=0.0, camera_available=True)
        self.assertEqual(state, "PRESENT", "Should remain PRESENT due to <15s hysteresis")

        # Advance to 14.9 seconds total absence
        self.clock.advance(9.9)
        state, _ = self.engine.update("AWAY", confidence=0.0, camera_available=True)
        self.assertEqual(state, "PRESENT", "Still within 15s hysteresis window")

        # Advance beyond 15.0 seconds
        self.clock.advance(0.5)  # 15.4s total missing
        state, diag = self.engine.update("AWAY", confidence=0.0, camera_available=True)
        self.assertEqual(state, "AWAY", "Exceeded 15s absence hysteresis threshold -> AWAY")
        self.assertGreater(diag["missing_sec"], 15.0)

    def test_p1_03_automatic_return(self):
        """P1-03: Valid person observation after AWAY returns state to PRESENT automatically."""
        # Establish AWAY state
        self.engine.update("PRESENT", confidence=0.9, camera_available=True)
        self.clock.advance(20.0)
        self.engine.update("AWAY", confidence=0.0, camera_available=True)
        self.assertEqual(self.engine.current_state, "AWAY")

        # Person returns
        self.clock.advance(1.0)
        state, diag = self.engine.update("PRESENT", confidence=0.88, camera_available=True)
        self.assertEqual(state, "PRESENT", "Must immediately return to PRESENT")
        self.assertEqual(diag["missing_sec"], 0.0)

    def test_p1_04_unknown_input(self):
        """P1-04: Low-confidence, invalid, or unavailable camera produces UNKNOWN."""
        # Camera unavailable
        state, _ = self.engine.update("PRESENT", confidence=0.9, camera_available=False)
        self.assertEqual(state, "UNKNOWN")

        # None candidate
        state, _ = self.engine.update(None, confidence=0.9, camera_available=True)
        self.assertEqual(state, "UNKNOWN")

        # Low confidence (<0.35) on clean slate
        fresh_engine = PresenceEngine(time_func=self.clock.time)
        state, _ = fresh_engine.update("PRESENT", confidence=0.20, camera_available=True)
        self.assertEqual(state, "UNKNOWN")


class TestPhase1CalibrationAndClassification(unittest.TestCase):
    """P1-05 to P1-11: Calibration engine and posture/attention classifiers"""

    def setUp(self):
        self.clock = MockClock(1000.0)
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_path = self.temp_file.name
        self.temp_file.close()

        self.calib_mgr = CalibrationManager(
            profile_path=self.temp_path,
            calibration_duration_sec=10.0,
            min_required_samples=15,
            time_func=self.clock.time
        )
        self.classifier = PostureClassifier()
        self.attention = AttentionEstimator()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except Exception:
                pass

    def test_p1_05_calibration_duration_and_window(self):
        """P1-05: Collects configured 10s of samples and ignores frames outside window."""
        self.calib_mgr.start_calibration(duration_sec=10.0)
        sample = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "ear_shoulder_ratio": 0.15,
            "head_shoulder_angle": 90.0
        }

        # Submit 16 samples across 8 seconds
        for i in range(16):
            self.clock.advance(0.5)
            done, _ = self.calib_mgr.add_sample(sample, confidence=0.9)
            self.assertFalse(done)

        # Advance beyond 10s
        self.clock.advance(3.0)  # total elapsed: 11.0s
        done, msg = self.calib_mgr.add_sample(sample, confidence=0.9)
        self.assertTrue(done)
        self.assertEqual(msg, "Calibration successful")
        self.assertIsNotNone(self.calib_mgr.profile)

    def test_p1_06_calibration_quality_rejection(self):
        """P1-06: Inadequate samples or missing landmarks does not overwrite profile."""
        # Establish valid existing profile
        self.calib_mgr.profile = CalibrationProfile(0.05, 0.35, 0.20)
        self.calib_mgr.save_profile()

        # Start new calibration
        self.calib_mgr.start_calibration(duration_sec=10.0)

        # Feed invalid/missing shoulder frames
        bad_sample = {"inter_eye_dist": 0.005, "shoulder_span": 0.01, "head_shoulder_y_delta": 0.01}
        for _ in range(20):
            self.clock.advance(0.5)
            self.calib_mgr.add_sample(bad_sample, confidence=0.9)

        self.clock.advance(2.0)
        done, reason = self.calib_mgr.add_sample(bad_sample, confidence=0.9)
        self.assertTrue(done)
        self.assertIn("rejected", reason.lower())

        # Verify old valid profile was NOT overwritten
        self.assertEqual(self.calib_mgr.profile.inter_eye_dist, 0.05)

    def test_p1_07_normalized_calibration_profile(self):
        """P1-07: Good sample set stores normalized metrics."""
        self.calib_mgr.start_calibration(duration_sec=5.0)
        for i in range(20):
            self.clock.advance(0.25)
            self.calib_mgr.add_sample({
                "inter_eye_dist": 0.06,
                "shoulder_span": 0.36,
                "head_shoulder_y_delta": 0.22,
                "ear_shoulder_ratio": 0.16,
                "head_shoulder_angle": 90.0
            }, confidence=0.95)

        self.clock.advance(0.5)
        self.calib_mgr.add_sample({"inter_eye_dist": 0.06, "shoulder_span": 0.36, "head_shoulder_y_delta": 0.22}, confidence=0.95)

        prof = self.calib_mgr.profile
        self.assertIsNotNone(prof)
        self.assertAlmostEqual(prof.inter_eye_dist, 0.06, places=3)
        self.assertAlmostEqual(prof.shoulder_span, 0.36, places=3)
        self.assertAlmostEqual(prof.head_shoulder_y_delta, 0.22, places=3)

    def test_p1_08_calibration_persistence(self):
        """P1-08: Saved profile reloads safely; corrupt profile handled safely."""
        self.calib_mgr.profile = CalibrationProfile(0.055, 0.37, 0.21, 0.14, 91.0)
        self.calib_mgr.save_profile()

        # Reload in new manager instance
        mgr2 = CalibrationManager(profile_path=self.temp_path)
        self.assertIsNotNone(mgr2.profile)
        self.assertAlmostEqual(mgr2.profile.inter_eye_dist, 0.055, places=3)

        # Corrupt file test
        with open(self.temp_path, "w") as f:
            f.write("{invalid_json: true")
        mgr3 = CalibrationManager(profile_path=self.temp_path)
        self.assertIsNone(mgr3.profile, "Corrupt profile should be safely set to None without crash")

    def test_p1_09_posture_classes(self):
        """P1-09: Controlled landmark fixtures independently produce required classes."""
        baseline = CalibrationProfile(
            inter_eye_dist=0.05,
            shoulder_span=0.35,
            head_shoulder_y_delta=0.20
        )

        # Good posture fixture
        good_metrics = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "shoulder_tilt": 0.0,
            "head_tilt": 0.0
        }
        res, _ = self.classifier.classify(good_metrics, baseline)
        self.assertEqual(res, "POSTURE_GOOD")

        # Slouching fixture (head dropped relative to shoulder)
        slouch_metrics = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.14,  # ratio 0.14/0.20 = 0.70 (< 0.80)
            "shoulder_tilt": 0.0,
            "head_tilt": 0.0
        }
        res, _ = self.classifier.classify(slouch_metrics, baseline)
        self.assertEqual(res, "SLOUCHING")

        # Lean Left fixture (left shoulder dropped)
        lean_left_metrics = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "shoulder_tilt": -0.06,  # angle < -7 deg
            "head_tilt": 0.0
        }
        res, _ = self.classifier.classify(lean_left_metrics, baseline)
        self.assertEqual(res, "LEAN_LEFT")

        # Lean Right fixture (right shoulder dropped)
        lean_right_metrics = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "shoulder_tilt": 0.06,  # angle > 7 deg
            "head_tilt": 0.0
        }
        res, _ = self.classifier.classify(lean_right_metrics, baseline)
        self.assertEqual(res, "LEAN_RIGHT")

        # Head Tilt fixture
        tilt_metrics = {
            "inter_eye_dist": 0.05,
            "shoulder_span": 0.35,
            "head_shoulder_y_delta": 0.20,
            "shoulder_tilt": 0.0,
            "head_tilt": 0.015  # angle > 10 deg
        }
        res, _ = self.classifier.classify(tilt_metrics, baseline)
        self.assertEqual(res, "HEAD_TILT")

    def test_p1_10_relative_distance(self):
        """P1-10: Face size / inter-eye distance above threshold produces TOO_CLOSE."""
        baseline = CalibrationProfile(inter_eye_dist=0.05, shoulder_span=0.35, head_shoulder_y_delta=0.20)

        # Normal slight forward shift (within threshold)
        normal_metrics = {"inter_eye_dist": 0.055, "shoulder_span": 0.35, "head_shoulder_y_delta": 0.20}
        res, _ = self.classifier.classify(normal_metrics, baseline)
        self.assertEqual(res, "POSTURE_GOOD")

        # Excessive close up (distance_ratio = 0.075 / 0.05 = 1.50 > 1.30)
        close_metrics = {"inter_eye_dist": 0.075, "shoulder_span": 0.45, "head_shoulder_y_delta": 0.20}
        res, details = self.classifier.classify(close_metrics, baseline)
        self.assertEqual(res, "TOO_CLOSE")
        self.assertGreaterEqual(details["distance_ratio"], 1.30)

    def test_p1_11_attention_classes(self):
        """P1-11: Head pose fixtures produce SCREEN, LEFT, RIGHT, DOWN, AWAY, UNKNOWN."""
        # Screen
        res, _ = self.attention.estimate({"yaw_offset": 0.05, "pitch_offset": 0.02}, presence_state="PRESENT")
        self.assertEqual(res, "SCREEN")

        # Right
        res, _ = self.attention.estimate({"yaw_offset": 0.60, "pitch_offset": 0.02}, presence_state="PRESENT")
        self.assertEqual(res, "RIGHT")

        # Left
        res, _ = self.attention.estimate({"yaw_offset": -0.60, "pitch_offset": 0.02}, presence_state="PRESENT")
        self.assertEqual(res, "LEFT")

        # Down
        res, _ = self.attention.estimate({"yaw_offset": 0.0, "pitch_offset": 0.20}, presence_state="PRESENT")
        self.assertEqual(res, "DOWN")

        # User AWAY
        res, _ = self.attention.estimate(None, presence_state="AWAY")
        self.assertEqual(res, "AWAY")

        # Low confidence produces UNKNOWN
        res, _ = self.attention.estimate({"yaw_offset": 0.0, "pitch_offset": 0.0}, presence_state="PRESENT", confidence=0.2)
        self.assertEqual(res, "UNKNOWN")


class TestPhase1SmoothingAndNotifications(unittest.TestCase):
    """P1-12 to P1-16: Jitter suppression, persistence window, and alert cooldowns"""

    def setUp(self):
        self.clock = MockClock(1000.0)
        self.filter = TemporalFilter(
            window_size=5,
            persistence_threshold_sec=20.0,
            cooldown_sec=300.0,
            time_func=self.clock.time
        )

    def test_p1_12_jitter_suppression(self):
        """P1-12: Alternating good/bad frames do not cause rapid flapping."""
        # Establish initial stable good state
        for _ in range(5):
            self.clock.advance(0.2)
            self.filter.update("POSTURE_GOOD")
        self.assertEqual(self.filter.stable_state, "POSTURE_GOOD")

        # Single frame glitch to SLOUCHING
        self.clock.advance(0.2)
        stable, _, _ = self.filter.update("SLOUCHING")
        self.assertEqual(stable, "POSTURE_GOOD", "Single frame anomaly must be suppressed by majority voting")

        # Consecutive good frames keep it steady
        self.clock.advance(0.2)
        stable, _, _ = self.filter.update("POSTURE_GOOD")
        self.assertEqual(stable, "POSTURE_GOOD")

    def test_p1_13_brief_movement_ignored(self):
        """P1-13: Posture deviation shorter than 20 seconds never triggers notification."""
        # Stabilize
        for _ in range(5):
            self.filter.update("POSTURE_GOOD")

        # Continuous slouch for 12 seconds
        for _ in range(12):
            self.clock.advance(1.0)
            stable, notify, _ = self.filter.update("SLOUCHING")
            self.assertFalse(notify, "Deviation < 20s must not notify")

        # Return to good posture
        for _ in range(5):
            self.clock.advance(0.2)
            stable, notify, _ = self.filter.update("POSTURE_GOOD")
            self.assertFalse(notify)

    def test_p1_14_persistent_posture_alert(self):
        """P1-14: Continuous deviation reaching 20s threshold requests exactly one alert."""
        for _ in range(5):
            self.filter.update("POSTURE_GOOD")

        alert_count = 0
        # Slouch continuously for 25 seconds
        for sec in range(25):
            self.clock.advance(1.0)
            _, notify, _ = self.filter.update("SLOUCHING")
            if notify:
                alert_count += 1

        self.assertEqual(alert_count, 1, "Must trigger exactly one alert when reaching persistence threshold")

    def test_p1_15_persistence_reset(self):
        """P1-15: Returning to good posture clears timer; later deviation requires full threshold again."""
        for _ in range(5):
            self.filter.update("POSTURE_GOOD")

        # Slouch for 18 seconds (almost at 20s)
        for _ in range(18):
            self.clock.advance(1.0)
            _, notify, _ = self.filter.update("SLOUCHING")
            self.assertFalse(notify)

        # Sit up straight (reset)
        for _ in range(5):
            self.clock.advance(0.2)
            self.filter.update("POSTURE_GOOD")
        self.assertEqual(self.filter.continuous_deviation_duration, 0.0)

        # Slouch again for 10 seconds - total time is high, but continuous is only 10s
        for _ in range(10):
            self.clock.advance(1.0)
            _, notify, diag = self.filter.update("SLOUCHING")
            self.assertFalse(notify, "Timer must have been reset; 10s continuous is below 20s threshold")
            self.assertLess(diag["deviation_duration_sec"], 15.0)

    def test_p1_16_notification_cooldown(self):
        """P1-16: After an alert, the same condition cannot alert again during 5-minute cooldown."""
        for _ in range(5):
            self.filter.update("POSTURE_GOOD")

        # Reach 20s and get alert
        first_alert = False
        for _ in range(25):
            self.clock.advance(1.0)
            _, notify, diag = self.filter.update("SLOUCHING")
            if notify:
                first_alert = True
        self.assertTrue(first_alert)

        # Continue slouching for another 3 minutes (180s < 300s cooldown)
        for _ in range(180):
            self.clock.advance(1.0)
            _, notify, _ = self.filter.update("SLOUCHING")
            self.assertFalse(notify, "Must not alert during cooldown period")

        # Advance past 5 minutes (300s) cooldown (advance 125s more)
        subsequent_alert = False
        for _ in range(125):
            self.clock.advance(1.0)
            _, notify, _ = self.filter.update("SLOUCHING")
            if notify:
                subsequent_alert = True

        self.assertTrue(subsequent_alert, "Must alert again once cooldown has elapsed if deviation continues")


if __name__ == "__main__":
    unittest.main()
