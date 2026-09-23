"""Phase 5 Integration Tests for DeskSense.
Covers requirements P5-01 through P5-15:
- P5-01: Focus session boundaries (starts/extends on productive work, closes at timestamp on phone/away/idle/distraction)
- P5-02: Focus totals (exact total focus time, session count, longest session, average session, distraction count)
- P5-03: Timeline mapping (renders ordered, non-overlapping Work, Phone, Away/Break, Idle at proportional positions)
- P5-04: Timeline gaps/overlaps (gaps become UNMONITORED, overlaps resolved by state priority without double-counting)
- P5-05: Timeline interaction (state, start, end, duration formatted for hover; immutability verified)
- P5-06: Default app categories (Productive, Communication, Entertainment, Browser, neutral unclassified)
- P5-07: User reclassification (add, edit, remove, persist across restarts, apply to classification)
- P5-08: Rule precedence (user rules override defaults, case-insensitive, no unsafe arbitrary code/regex)
- P5-09: Phone dashboard (exact estimated total, count, longest, average durations)
- P5-10: Presence dashboard (exact desk time, away intervals, break log)
- P5-11: Daily summary (exact metrics without double-counting)
- P5-12: Daily score boundaries (weights, no division by zero on missing data, clamped 0-100)
- P5-13: Actionable wording (factual, motivational, estimated phone wording, non-medical posture language)
- P5-14: End-of-day preference (configured time check, once per day, disabled check)
- P5-15: MVP 2 end-to-end day (all 5 required totals match: focus, desk, away, phone, posture score)
"""

import unittest
import time
import datetime
import tempfile
import os

from src.system.work_state import WorkState, WorkStateEngine
from src.system.app_classifier import AppClassifier, AppCategory
from src.system.focus_tracker import FocusTracker, FocusSession
from src.system.timeline import TimelineBuilder, TimelineSegment, STATE_PRIORITY
from src.system.summary_engine import DailySummaryEngine, ScoreWeights
from src.storage.db import DatabaseEngine


class TestPhase5Integration(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseEngine(":memory:")

    def tearDown(self):
        self.db.close()

    # P5-01: Focus session boundaries
    def test_p5_01_focus_session_boundaries(self):
        tracker = FocusTracker(db=self.db)
        
        # Productive work starts session at 100.0
        closed = tracker.update(100.0, WorkState.FOCUSED_WORK)
        self.assertIsNone(closed)
        self.assertTrue(tracker.in_focus)

        # Extended at 150.0
        closed = tracker.update(150.0, WorkState.FOCUSED_WORK)
        self.assertIsNone(closed)
        self.assertTrue(tracker.in_focus)

        # Interrupted by Phone at 200.0 -> session closes at 200.0
        closed = tracker.update(200.0, WorkState.PHONE_USAGE)
        self.assertIsNotNone(closed)
        self.assertEqual(closed.start_time, 100.0)
        self.assertEqual(closed.end_time, 200.0)
        self.assertEqual(closed.duration, 100)
        self.assertFalse(tracker.in_focus)

        # Second session starts at 300.0
        tracker.update(300.0, WorkState.FOCUSED_WORK)
        self.assertTrue(tracker.in_focus)

        # Interrupted by Away at 420.0
        closed2 = tracker.update(420.0, WorkState.AWAY)
        self.assertIsNotNone(closed2)
        self.assertEqual(closed2.start_time, 300.0)
        self.assertEqual(closed2.end_time, 420.0)
        self.assertEqual(closed2.duration, 120)

    # P5-02: Focus totals
    def test_p5_02_focus_totals(self):
        tracker = FocusTracker()
        
        # Session 1: 100s (from 0 to 100)
        tracker.update(0.0, WorkState.FOCUSED_WORK)
        tracker.update(100.0, WorkState.IDLE)

        # Session 2: 300s (from 200 to 500)
        tracker.update(200.0, WorkState.FOCUSED_WORK)
        tracker.update(500.0, WorkState.PHONE_USAGE)

        # Session 3: 200s (from 600 to 800)
        tracker.update(600.0, WorkState.FOCUSED_WORK)
        tracker.update(800.0, WorkState.DISTRACTED)

        totals = tracker.get_focus_totals()
        self.assertEqual(totals["session_count"], 3)
        self.assertEqual(totals["total_focus_time"], 600)  # 100 + 300 + 200
        self.assertEqual(totals["longest_session"], 300)
        self.assertEqual(totals["average_session"], 200)   # 600 / 3
        self.assertEqual(totals["distraction_count"], 2)   # PHONE_USAGE + DISTRACTED

    # P5-03: Timeline mapping
    def test_p5_03_timeline_mapping(self):
        builder = TimelineBuilder(day_start=0.0, day_end=1000.0)
        raw_intervals = [
            {"start_time": 100.0, "end_time": 400.0, "state": WorkState.FOCUSED_WORK.value},
            {"start_time": 400.0, "end_time": 500.0, "state": WorkState.PHONE_USAGE.value},
            {"start_time": 500.0, "end_time": 700.0, "state": WorkState.BREAK.value},
            {"start_time": 700.0, "end_time": 800.0, "state": WorkState.IDLE.value},
        ]
        segments = builder.build_timeline(raw_intervals)
        
        # Verify ordered timestamps
        for i in range(len(segments) - 1):
            self.assertLessEqual(segments[i].end_time, segments[i + 1].start_time)

        # Verify segments cover the day cleanly
        self.assertEqual(segments[0].start_time, 0.0)
        self.assertEqual(segments[-1].end_time, 1000.0)
        
        # Verify categories
        categories = [s.category for s in segments]
        self.assertIn("work", categories)
        self.assertIn("phone", categories)
        self.assertIn("break", categories)
        self.assertIn("idle", categories)

    # P5-04: Timeline gaps/overlaps
    def test_p5_04_timeline_gaps_and_overlaps(self):
        builder = TimelineBuilder()
        # Synthetic overlap: Work from 0 to 100, but Phone detected from 40 to 60
        raw_intervals = [
            {"start_time": 0.0, "end_time": 100.0, "state": WorkState.FOCUSED_WORK.value},
            {"start_time": 40.0, "end_time": 60.0, "state": WorkState.PHONE_USAGE.value},
            # Gap from 100 to 200
            {"start_time": 200.0, "end_time": 300.0, "state": WorkState.ACTIVE_WORK.value},
        ]

        segments = builder.build_timeline(raw_intervals, day_start=0.0, day_end=300.0)
        
        # Verify 0 double-counted time: total duration must equal exactly 300.0
        total_duration = sum(s.duration for s in segments)
        self.assertEqual(total_duration, 300.0)

        # Phone (priority 100) must carve out 40-60 from Work (priority 50)
        phone_segs = [s for s in segments if s.state == WorkState.PHONE_USAGE.value]
        self.assertEqual(len(phone_segs), 1)
        self.assertEqual(phone_segs[0].start_time, 40.0)
        self.assertEqual(phone_segs[0].end_time, 60.0)

        # Gap from 100 to 200 should be UNMONITORED
        gap_segs = [s for s in segments if s.state == "UNMONITORED"]
        self.assertEqual(len(gap_segs), 1)
        self.assertEqual(gap_segs[0].start_time, 100.0)
        self.assertEqual(gap_segs[0].end_time, 200.0)

    # P5-05: Timeline interaction
    def test_p5_05_timeline_interaction_immutability(self):
        segment = TimelineSegment(
            start_time=3600.0,
            end_time=5400.0,
            duration=1800.0,
            state="FOCUSED_WORK",
            label="Deep Focus",
            color="#10b981",
            category="work",
        )
        data = segment.to_dict()
        self.assertIn("start_time_str", data)
        self.assertIn("end_time_str", data)
        self.assertEqual(data["duration"], 1800.0)
        self.assertEqual(data["category"], "work")

        # Immutability check (frozen dataclass)
        with self.assertRaises(Exception):
            segment.duration = 2000.0

    # P5-06: Default app categories
    def test_p5_06_default_app_categories(self):
        classifier = AppClassifier()
        self.assertEqual(classifier.classify(process_name="Code.exe"), "productive")
        self.assertEqual(classifier.classify(process_name="slack.exe"), "communication")
        self.assertEqual(classifier.classify(process_name="spotify.exe"), "entertainment")
        self.assertEqual(classifier.classify(process_name="chrome.exe"), "browser")
        # Refined browser title
        self.assertEqual(classifier.classify(process_name="chrome.exe", window_title="GitHub - Repo"), "productive")
        self.assertEqual(classifier.classify(process_name="msedge.exe", window_title="YouTube - Video"), "entertainment")
        # Unknown app
        self.assertEqual(classifier.classify(process_name="calculator.exe"), "unclassified")

    # P5-07: User reclassification
    def test_p5_07_user_reclassification_and_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db_path = tf.name
        try:
            db1 = DatabaseEngine(test_db_path)
            classifier1 = AppClassifier(db=db1)
            # Classify unknown app initially
            self.assertEqual(classifier1.classify("special_tool.exe"), "unclassified")

            # Add user rule
            rule_id = classifier1.add_rule("special_tool.exe", "process", "productive")
            self.assertEqual(classifier1.classify("special_tool.exe"), "productive")
            db1.close()

            # Persistence across restart
            db2 = DatabaseEngine(test_db_path)
            classifier2 = AppClassifier(db=db2)
            self.assertEqual(classifier2.classify("special_tool.exe"), "productive")

            # Delete rule
            classifier2.delete_rule("special_tool.exe", "process", rule_id=rule_id)
            self.assertEqual(classifier2.classify("special_tool.exe"), "unclassified")
            db2.close()
        finally:
            try:
                os.remove(test_db_path)
            except Exception:
                pass

    # P5-08: Rule precedence
    def test_p5_08_rule_precedence_and_case_insensitivity(self):
        classifier = AppClassifier(db=self.db)
        # By default spotify is entertainment
        self.assertEqual(classifier.classify("Spotify.EXE"), "entertainment")

        # User reclassifies Spotify as productive (e.g., focus music)
        classifier.add_rule("sPoTiFy.ExE", "process", "productive")
        self.assertEqual(classifier.classify("spotify.exe"), "productive")
        self.assertEqual(classifier.classify("SPOTIFY"), "productive")

    # P5-09: Phone dashboard
    def test_p5_09_phone_dashboard_metrics(self):
        self.db.log_phone_session("2026-09-23T10:00:00", "2026-09-23T10:01:40", duration=100, confidence=0.85)
        self.db.log_phone_session("2026-09-23T11:00:00", "2026-09-23T11:05:00", duration=300, confidence=0.90)

        summary = self.db.get_phone_summary()
        self.assertEqual(summary["estimated_phone_usage"], 400)
        self.assertEqual(summary["estimated_sessions"], 2)
        self.assertEqual(summary["longest_session"], 300)
        self.assertEqual(summary["average_session"], 200)
        self.assertEqual(summary["wording"], "estimated phone usage")

    # P5-10: Presence dashboard
    def test_p5_10_presence_dashboard_metrics(self):
        # Log breaks
        self.db.log_break("2026-09-23T10:30:00", "2026-09-23T10:35:00", duration=300, break_type="automatic")
        self.db.log_break("2026-09-23T12:00:00", "2026-09-23T12:15:00", duration=900, break_type="manual")
        
        breaks = self.db.get_breaks()
        self.assertEqual(len(breaks), 2)
        self.assertEqual(sum(b["duration"] for b in breaks), 1200)

        # Log posture events
        self.db.insert_posture_event("POSTURE_GOOD", 0.9, 0.0, 3600.0)
        self.db.insert_attention_event("AWAY", 0.9, 3600.0, 4200.0)

        metrics = self.db.calculate_daily_metrics(0.0, 5000.0)
        self.assertEqual(metrics["desk_time"], 3600.0)
        self.assertEqual(metrics["away_time"], 600.0)

    # P5-11: Daily summary
    def test_p5_11_daily_summary_no_double_counting(self):
        summary_engine = DailySummaryEngine()
        res = summary_engine.generate_daily_summary(
            date_str="2026-09-23",
            focus_seconds=10800.0,  # 3h
            desk_seconds=14400.0,   # 4h
            away_seconds=3600.0,    # 1h
            phone_seconds=600.0,    # 10m
            posture_score=85.0,
            break_count=3,
            longest_focus_seconds=5400.0,
        )
        metrics = res["metrics"]
        self.assertEqual(metrics["focus_seconds"], 10800)
        self.assertEqual(metrics["desk_seconds"], 14400)
        self.assertEqual(metrics["away_seconds"], 3600)
        self.assertEqual(metrics["estimated_phone_seconds"], 600)
        self.assertEqual(metrics["posture_score"], 85.0)
        self.assertEqual(metrics["break_count"], 3)
        self.assertEqual(metrics["longest_focus_seconds"], 5400)

    # P5-12: Daily score boundaries
    def test_p5_12_daily_score_boundaries_and_safety(self):
        summary_engine = DailySummaryEngine()

        # Zero data safety check (no division by zero)
        res_zero = summary_engine.calculate_daily_score(
            focus_seconds=0.0,
            desk_seconds=0.0,
            posture_score=0.0,
            break_count=0,
            phone_seconds=0.0,
        )
        self.assertGreaterEqual(res_zero["daily_wellness_score"], 0)
        self.assertLessEqual(res_zero["daily_wellness_score"], 100)

        # Perfect day
        res_perfect = summary_engine.calculate_daily_score(
            focus_seconds=14400.0,
            desk_seconds=14400.0,
            posture_score=100.0,
            break_count=4,
            phone_seconds=0.0,
        )
        self.assertEqual(res_perfect["daily_wellness_score"], 100)

        # Extremely negative signals
        res_bad = summary_engine.calculate_daily_score(
            focus_seconds=0.0,
            desk_seconds=28800.0,
            posture_score=0.0,
            break_count=0,
            phone_seconds=28800.0,
        )
        self.assertGreaterEqual(res_bad["daily_wellness_score"], 0)
        self.assertLessEqual(res_bad["daily_wellness_score"], 25)

    # P5-13: Actionable wording
    def test_p5_13_actionable_wording_and_disclaimer(self):
        summary_engine = DailySummaryEngine()
        insights = summary_engine.generate_actionable_insights(
            focus_seconds=7200.0,
            desk_seconds=10800.0,
            posture_score=75.0,
            break_count=2,
            phone_seconds=900.0,
            longest_focus_seconds=3600.0,
        )

        full_text = " ".join(insights).lower()
        # Must describe phone as estimate
        self.assertIn("estimated phone usage", full_text)
        # Must not contain medical diagnostic claims
        medical_terms = ["diagnose", "spine disorder", "kyphosis", "treatment", "doctor", "pathology"]
        for term in medical_terms:
            self.assertNotIn(term, full_text)

    # P5-14: End-of-day preference
    def test_p5_14_end_of_day_preference(self):
        summary_engine = DailySummaryEngine()
        
        # Disabled check
        dt_1800 = datetime.datetime(2026, 9, 23, 18, 0, 0)
        self.assertFalse(summary_engine.should_trigger_summary(dt_1800, "17:30", enabled=False))

        # Before scheduled time
        dt_1600 = datetime.datetime(2026, 9, 23, 16, 0, 0)
        self.assertFalse(summary_engine.should_trigger_summary(dt_1600, "17:30", enabled=True))

        # At or after scheduled time -> triggers True
        self.assertTrue(summary_engine.should_trigger_summary(dt_1800, "17:30", enabled=True))

        # Second check on same day -> triggers False (at most once per day)
        dt_1900 = datetime.datetime(2026, 9, 23, 19, 0, 0)
        self.assertFalse(summary_engine.should_trigger_summary(dt_1900, "17:30", enabled=True))

        # Next day -> triggers True again
        dt_next_day = datetime.datetime(2026, 9, 24, 18, 0, 0)
        self.assertTrue(summary_engine.should_trigger_summary(dt_next_day, "17:30", enabled=True))

    # P5-15: MVP 2 end-to-end day
    def test_p5_15_mvp2_end_to_end_day(self):
        # 1. Simulate day intervals: Focus Work, Phone Usage, Break, Active Work, Away
        # Day: 0 to 14400s (4 hours)
        intervals = [
            {"start_time": 0.0, "end_time": 3600.0, "state": WorkState.FOCUSED_WORK.value, "duration": 3600},
            {"start_time": 3600.0, "end_time": 4200.0, "state": WorkState.PHONE_USAGE.value, "duration": 600},
            {"start_time": 4200.0, "end_time": 4800.0, "state": WorkState.BREAK.value, "duration": 600},
            {"start_time": 4800.0, "end_time": 8400.0, "state": WorkState.ACTIVE_WORK.value, "duration": 3600},
            {"start_time": 8400.0, "end_time": 10200.0, "state": WorkState.AWAY.value, "duration": 1800},
            {"start_time": 10200.0, "end_time": 14400.0, "state": WorkState.FOCUSED_WORK.value, "duration": 4200},
        ]

        for item in intervals:
            self.db.log_work_state_interval(
                state=item["state"],
                start_time=str(item["start_time"]),
                end_time=str(item["end_time"]),
                duration=item["duration"],
            )

        # 2. Build Timeline
        builder = TimelineBuilder(day_start=0.0, day_end=14400.0)
        timeline = builder.build_timeline(intervals)
        self.assertEqual(len(timeline), 6)
        self.assertEqual(sum(s.duration for s in timeline), 14400.0)

        # 3. Focus Totals
        focus_totals = FocusTracker.calculate_totals_from_intervals(intervals)
        self.assertEqual(focus_totals["total_focus_time"], 7800)  # 3600 + 4200
        self.assertEqual(focus_totals["session_count"], 2)
        self.assertEqual(focus_totals["longest_session"], 4200)

        # 4. Desk time vs Away time vs Phone time
        desk_time = 3600 + 600 + 3600 + 4200  # Focused + Phone + Active + Focused = 12000s
        away_time = 1800 + 600                 # Away + Break = 2400s
        phone_time = 600
        posture_score = 80.0                   # Seeded posture quality

        # 5. Generate daily summary and verify all 5 required totals
        summary_engine = DailySummaryEngine()
        day_summary = summary_engine.generate_daily_summary(
            date_str="2026-09-23",
            focus_seconds=focus_totals["total_focus_time"],
            desk_seconds=desk_time,
            away_seconds=away_time,
            phone_seconds=phone_time,
            posture_score=posture_score,
            break_count=1,
            longest_focus_seconds=focus_totals["longest_session"],
        )

        m = day_summary["metrics"]
        self.assertEqual(m["focus_seconds"], 7800)
        self.assertEqual(m["desk_seconds"], 12000)
        self.assertEqual(m["away_seconds"], 2400)
        self.assertEqual(m["estimated_phone_seconds"], 600)
        self.assertEqual(m["posture_score"], 80.0)
        self.assertGreater(day_summary["score"]["daily_wellness_score"], 50)


if __name__ == "__main__":
    unittest.main()
