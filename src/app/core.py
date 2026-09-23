from src.system.adaptive_perf import AdaptivePerformanceManager, PowerSource
from src.system.multi_monitor import MultiMonitorConfig
from src.system.weekly_trends import WeeklyTrendsEngine
from src.system.privacy_manager import PrivacyManager
from src.system.startup import WindowsStartupManager
from src.system.app_classifier import AppClassifier
from src.system.focus_tracker import FocusTracker
from src.system.timeline import TimelineBuilder
from src.system.summary_engine import DailySummaryEngine
"""
DeskSense Main Application Core & Host Controller (Phase 3)
Coordinates Desktop Shell lifecycle, Tray operations, Global Hotkey,
Pause semantics, Calibration Wizard, Dashboard aggregation, Live Status Widget,
and Vision/System background pipelines.
Conforms strictly to P3-01 through P3-15 test specifications.
"""

import time
import datetime
from enum import Enum
from typing import Optional, Dict, Any, Callable

from src.storage.db import DatabaseEngine
from src.system.activity import ActivityTracker
from src.system.lifecycle import SessionManager, LifecycleEventType
from src.system.notifier import NotificationDispatcher
from src.app.wizard import CalibrationWizard, WizardState
from src.app.widget import StatusWidgetState
from src.app.tray import TrayController, TrayCommand
from src.app.hotkey import HotkeyManager
from src.app.dashboard import DashboardService
from src.vision.phone_fusion import PhoneUsageFusion, PhoneSession
from src.vision.phone_scheduler import PhoneInferenceScheduler
from src.system.work_state import WorkStateEngine, WorkState
from src.system.break_tracker import BreakTracker, BreakRecord
from src.system.focus_mode import FocusModeController


class MonitoringState(str, Enum):
    MONITORING = "MONITORING"
    PAUSED = "PAUSED"
    CALIBRATING = "CALIBRATING"
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"
    STOPPED = "STOPPED"


class AppState:
    """Snapshot of current application state."""
    def __init__(
        self,
        monitoring_state: MonitoringState = MonitoringState.MONITORING,
        window_visible: bool = True,
        is_paused: bool = False,
        pause_remaining_sec: float = 0.0,
        current_posture: str = "POSTURE_GOOD",
        current_attention: str = "SCREEN",
        current_activity: str = "ACTIVE_WORK",
        active_app: str = "Desktop",
        session_duration_sec: float = 0.0,
        camera_available: bool = True,
        has_calibration: bool = False
    ):
        self.monitoring_state = monitoring_state
        self.window_visible = window_visible
        self.is_paused = is_paused
        self.pause_remaining_sec = pause_remaining_sec
        self.current_posture = current_posture
        self.current_attention = current_attention
        self.current_activity = current_activity
        self.active_app = active_app
        self.session_duration_sec = session_duration_sec
        self.camera_available = camera_available
        self.has_calibration = has_calibration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitoring_state": self.monitoring_state.value,
            "window_visible": self.window_visible,
            "is_paused": self.is_paused,
            "pause_remaining_sec": round(self.pause_remaining_sec, 1),
            "current_posture": self.current_posture,
            "current_attention": self.current_attention,
            "current_activity": self.current_activity,
            "active_app": self.active_app,
            "session_duration_sec": round(self.session_duration_sec, 1),
            "camera_available": self.camera_available,
            "has_calibration": self.has_calibration
        }


class DeskSenseApp:
    def __init__(
        self,
        db_path: str = ":memory:",
        profile_path: str = "calibration_profile.json",
        start_minimized: bool = False,
        time_func: Optional[Callable[[], float]] = None,
        enable_widget: bool = False
    ):
        self.time_func = time_func or time.time
        self.start_minimized = start_minimized

        # Storage & System modules
        self.db = DatabaseEngine(db_path=db_path)
        self.activity_tracker = ActivityTracker(clock_func=self.time_func)
        self.session_manager = SessionManager(
            clock_func=self.time_func,
            on_session_start=lambda s: self.db.record_session(s),
            on_session_end=lambda s: self.db.record_session(s)
        )
        self.notifier = NotificationDispatcher(cooldown_seconds=300.0, clock_func=self.time_func, dispatch_func=lambda t, m: True)

        # Desktop UI & Shell modules
        self.dashboard_service = DashboardService(self.db)
        self.wizard = CalibrationWizard(
            profile_path=profile_path,
            countdown_sec=3.0,
            capture_sec=10.0,
            time_func=self.time_func
        )
        self.widget = StatusWidgetState(enabled=enable_widget)
        self.tray = TrayController(app_controller=self)
        self.hotkey = HotkeyManager(toggle_callback=self.toggle_pause)

        # Application state
        self.window_visible = not start_minimized
        self.is_running = True
        self.monitoring_state = MonitoringState.MONITORING
        self.camera_available = True
        self.current_posture = "POSTURE_GOOD"
        self.current_attention = "SCREEN"
        self.current_activity = "ACTIVE_WORK"
        self.active_app = "Desktop"

        # Pause tracking
        self.pause_end_time: Optional[float] = None
        self.pause_duration_sec: float = 0.0

        # Session tracking
        self.session_start_time = self.time_func()
        self.session_manager.start_session(session_type="DESKTOP_WORK")

        # Active settings view toggle
        self.active_view = "dashboard"

        # Phase 4 Signal Fusion, Phone & Break Trackers
        self.phone_fusion = PhoneUsageFusion(
            on_session_closed=self._on_phone_session_closed
        )
        self.phone_scheduler = PhoneInferenceScheduler()
        self.work_state_engine = WorkStateEngine()
        self.break_tracker = BreakTracker(
            on_break_completed=self._on_break_completed,
            on_sedentary_reminder=self._on_sedentary_reminder
        )
        self.focus_mode = FocusModeController(phone_fusion=self.phone_fusion)
        self.current_work_state = WorkState.UNKNOWN

        # Phase 5: App Classifier, Focus Tracker, Timeline & Daily Summary
        self.app_classifier = AppClassifier(db=self.db)
        self.focus_tracker = FocusTracker(db=self.db)
        self.daily_summary_engine = DailySummaryEngine()

        # Phase 6: Adaptive Performance, Multi-Monitor, Trends, Privacy & Startup
        self.adaptive_perf = AdaptivePerformanceManager(time_func=self.time_func)
        self.multi_monitor = MultiMonitorConfig()
        self.weekly_trends_engine = WeeklyTrendsEngine()
        self.privacy_manager = PrivacyManager(db=self.db)
        self.startup_manager = WindowsStartupManager()


    # ---------------- Window & Lifecycle Management (P3-01) ----------------

    def _on_phone_session_closed(self, session: PhoneSession) -> None:
        session_id = self.session_manager.current_session['id'] if self.session_manager.current_session else None
        self.db.log_phone_session(
            start_time=session.start_time,
            end_time=session.end_time,
            duration=session.duration,
            confidence=session.confidence,
            session_id=session_id
        )
        if self.focus_mode.is_active:
            self.focus_mode.record_phone_interruption()

    def _on_break_completed(self, brk: BreakRecord) -> None:
        session_id = self.session_manager.current_session['id'] if self.session_manager.current_session else None
        self.db.log_break(
            start_time=brk.start_time,
            end_time=brk.end_time,
            duration=brk.duration,
            break_type=brk.break_type,
            session_id=session_id
        )

    def _on_sedentary_reminder(self) -> None:
        self.notifier.dispatch("SEDENTARY_ALERT")

    def show_dashboard(self) -> None:
        """Brings dashboard to foreground / makes window visible."""
        self.window_visible = True
        self.active_view = "dashboard"

    def hide_dashboard(self) -> None:
        """Hides window while monitoring continues."""
        self.window_visible = False

    def on_close_requested(self) -> bool:
        """
        P3-01: Intercept window close request.
        Hides window to tray instead of quitting; monitoring continues.
        Returns False to prevent window destruction.
        """
        self.window_visible = False
        return False

    def open_settings(self) -> None:
        """Opens Settings page."""
        self.window_visible = True
        self.active_view = "settings"

    def quit(self) -> None:
        """
        P3-01: Cleanly shuts down host, flushes database, stops monitoring.
        """
        self.is_running = False
        self.monitoring_state = MonitoringState.STOPPED
        self.window_visible = False

        # Close session
        self.session_manager.end_session()
        self.phone_fusion.flush(self.time_func())
        self.work_state_engine.flush(self.time_func())

        # Flush database
        self.db.close()

    # ---------------- Pause Semantics (P3-03, P3-04) ----------------

    def pause_monitoring(self, duration_sec: float = 900.0) -> None:
        """
        P3-03: Pauses monitoring for specified duration.
        Inference and event creation halt. No synthetic data recorded for pause gap.
        """
        if self.monitoring_state == MonitoringState.STOPPED:
            return

        self.monitoring_state = MonitoringState.PAUSED
        self.pause_duration_sec = duration_sec
        self.pause_end_time = self.time_func() + duration_sec

        # Close or pause active work session so gap is not joined to work
        self.session_manager.end_session()

    def resume_monitoring(self) -> None:
        """P3-03: Resumes monitoring without inventing data for pause duration."""
        if self.monitoring_state == MonitoringState.STOPPED:
            return

        self.monitoring_state = MonitoringState.MONITORING
        self.pause_end_time = None
        self.pause_duration_sec = 0.0

        # Start a fresh work session
        self.session_start_time = self.time_func()
        self.session_manager.start_session(session_type="DESKTOP_WORK")

    def toggle_pause(self) -> None:
        """P3-04: Toggled by Ctrl+Shift+P hotkey."""
        if self.monitoring_state == MonitoringState.PAUSED:
            self.resume_monitoring()
        else:
            self.pause_monitoring(duration_sec=900.0)

    @property
    def pause_remaining_sec(self) -> float:
        if self.monitoring_state != MonitoringState.PAUSED or self.pause_end_time is None:
            return 0.0
        remaining = self.pause_end_time - self.time_func()
        return max(0.0, remaining)

    def check_pause_expiration(self) -> None:
        """Auto-resumes if pause duration elapsed."""
        if self.monitoring_state == MonitoringState.PAUSED and self.pause_end_time is not None:
            if self.time_func() >= self.pause_end_time:
                self.resume_monitoring()

    # ---------------- Calibration Wizard (P3-05, P3-06) ----------------

    def start_calibration(self) -> None:
        """P3-05: Begins calibration wizard flow."""
        self.monitoring_state = MonitoringState.CALIBRATING
        self.wizard.start_guidance()
        self.show_dashboard()
        self.active_view = "calibration"

    def cancel_calibration(self) -> None:
        """P3-06: Cancels wizard, preserves previous calibration profile."""
        self.wizard.cancel()
        self.monitoring_state = MonitoringState.MONITORING
        self.active_view = "dashboard"

    def finish_calibration(self) -> bool:
        """Finalizes calibration on success, saves profile, enters monitoring."""
        profile = self.wizard.finish()
        if profile is not None:
            self.monitoring_state = MonitoringState.MONITORING
            self.active_view = "dashboard"
            return True
        return False

    # ---------------- Telemetry & Event Ingestion ----------------

    def record_observation(
        self,
        posture_state: str,
        attention_state: str,
        confidence: float = 1.0,
        active_app: Optional[str] = None
    ) -> None:
        """
        Ingests frame inference observation.
        If PAUSED or STOPPED or CALIBRATING, drops observation to obey pause semantics.
        """
        # Auto-check pause expiration first
        self.check_pause_expiration()

        if self.monitoring_state != MonitoringState.MONITORING:
            return

        now = self.time_func()
        self.current_posture = posture_state
        self.current_attention = attention_state
        if active_app:
            self.active_app = active_app

        session_id = self.session_manager.current_session["id"] if self.session_manager.current_session else None

        # Record downsampled intervals in database
        self.db.record_posture_sample(
            posture_state=posture_state,
            confidence=confidence,
            timestamp=now,
            session_id=session_id
        )
        self.db.record_attention_sample(
            attention_state=attention_state,
            confidence=confidence,
            timestamp=now,
            session_id=session_id
        )

        # Update Phase 4 state engines
        is_head_down = (attention_state.upper() == "DOWN")
        self.phone_scheduler.update_suspicion(head_down=is_head_down)
        phone_active = self.phone_fusion.process_frame(
            timestamp=now,
            phone_detected=False,
            phone_confidence=0.0,
            head_down=is_head_down,
            present=(attention_state.upper() != "AWAY")
        )
        self.break_tracker.update(timestamp=now, present=(attention_state.upper() != "AWAY"))
        self.current_work_state = self.work_state_engine.update(
            timestamp=now,
            present=(attention_state.upper() != "AWAY"),
            attention=attention_state,
            app_category="neutral",
            idle_seconds=0.0,
            phone_active=phone_active,
            signals_reliable=self.camera_available
        )
        self.current_activity = self.current_work_state.value
        if self.focus_mode.is_active:
            self.focus_mode.update(now)

    def record_observation_extended(
        self,
        posture_state: str,
        attention_state: str,
        confidence: float = 1.0,
        active_app: Optional[str] = None,
        phone_detected: bool = False,
        phone_confidence: float = 0.0,
        head_down: bool = False,
        hand_near_phone: bool = False,
        present: bool = True,
        idle_seconds: float = 0.0,
        app_category: str = "neutral"
    ) -> None:
        """Extended observation ingestion handling vision, phone fusion, and work states."""
        self.check_pause_expiration()

        if self.monitoring_state != MonitoringState.MONITORING:
            return

        now = self.time_func()
        self.current_posture = posture_state
        self.current_attention = attention_state
        if active_app:
            self.active_app = active_app

        session_id = self.session_manager.current_session["id"] if self.session_manager.current_session else None

        self.db.record_posture_sample(
            posture_state=posture_state,
            confidence=confidence,
            timestamp=now,
            session_id=session_id
        )
        self.db.record_attention_sample(
            attention_state=attention_state,
            confidence=confidence,
            timestamp=now,
            session_id=session_id
        )

        is_head_down = head_down or (attention_state.upper() == "DOWN")
        self.phone_scheduler.update_suspicion(head_down=is_head_down)
        phone_active = self.phone_fusion.process_frame(
            timestamp=now,
            phone_detected=phone_detected,
            phone_confidence=phone_confidence,
            head_down=is_head_down,
            hand_near_phone=hand_near_phone,
            present=present
        )
        self.break_tracker.update(timestamp=now, present=present)
        self.current_work_state = self.work_state_engine.update(
            timestamp=now,
            present=present,
            attention=attention_state,
            app_category=app_category,
            idle_seconds=idle_seconds,
            phone_active=phone_active,
            signals_reliable=self.camera_available
        )
        self.current_activity = self.current_work_state.value
        if self.focus_mode.is_active:
            self.focus_mode.update(now)

    def set_camera_availability(self, available: bool) -> None:
        """Updates camera hardware availability status."""
        self.camera_available = available
        if not available:
            if self.monitoring_state == MonitoringState.MONITORING:
                self.monitoring_state = MonitoringState.CAMERA_UNAVAILABLE
        else:
            if self.monitoring_state == MonitoringState.CAMERA_UNAVAILABLE:
                self.monitoring_state = MonitoringState.MONITORING

    # ---------------- State & Presentation ----------------

    def get_session_duration(self) -> float:
        """Returns elapsed seconds in active session."""
        if self.monitoring_state == MonitoringState.PAUSED:
            return 0.0
        return max(0.0, self.time_func() - self.session_start_time)

    def get_state(self) -> AppState:
        self.check_pause_expiration()
        return AppState(
            monitoring_state=self.monitoring_state,
            window_visible=self.window_visible,
            is_paused=(self.monitoring_state == MonitoringState.PAUSED),
            pause_remaining_sec=self.pause_remaining_sec,
            current_posture=self.current_posture,
            current_attention=self.current_attention,
            current_activity=self.current_activity,
            active_app=self.active_app,
            session_duration_sec=self.get_session_duration(),
            camera_available=self.camera_available,
            has_calibration=(self.wizard.manager.profile is not None)
        )

    def get_tray_status_label(self) -> str:
        """Tray badge text based on live state."""
        if self.monitoring_state == MonitoringState.PAUSED:
            mins = int(self.pause_remaining_sec // 60) + 1
            return f"⏸ Paused ({mins}m)"
        elif self.monitoring_state == MonitoringState.CALIBRATING:
            return "⚙ Calibrating"
        elif self.monitoring_state == MonitoringState.CAMERA_UNAVAILABLE:
            return "⚠ Camera Disconnected"
        elif self.monitoring_state == MonitoringState.MONITORING:
            return "● Monitoring"
        return "DeskSense (Inactive)"

    def get_dashboard_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """Provides full view model for dashboard UI."""
        metrics_data = self.dashboard_service.get_dashboard_metrics(
            target_date=target_date,
            camera_available=self.camera_available,
            has_calibration=(self.wizard.manager.profile is not None)
        )
        live_state = self.dashboard_service.get_live_state(
            current_posture=self.current_posture,
            current_attention=self.current_attention,
            current_activity=self.current_activity,
            session_duration_sec=self.get_session_duration(),
            is_paused=(self.monitoring_state == MonitoringState.PAUSED),
            pause_remaining_sec=self.pause_remaining_sec,
            phone_active=self.phone_fusion.is_phone_active,
            work_state=self.current_work_state.value
        )
        # Phase 5 Aggregations: Timeline & Focus Totals
        intervals = self.db.get_work_state_intervals()
        t_start, t_end = self.dashboard_service.get_day_boundaries(target_date)
        timeline_builder = TimelineBuilder(day_start=t_start, day_end=t_end)
        timeline_segments = timeline_builder.build_timeline(intervals)

        focus_totals = self.focus_tracker.get_focus_totals()
        if not focus_totals["sessions"] and intervals:
            focus_totals = FocusTracker.calculate_totals_from_intervals(intervals)

        # Phone summary
        phone_summary = self.db.get_phone_summary()
        breaks = self.db.get_breaks()

        # Daily summary & score
        today_str = target_date or datetime.datetime.now().strftime("%Y-%m-%d")
        summary_payload = self.daily_summary_engine.generate_daily_summary(
            date_str=today_str,
            focus_seconds=focus_totals.get("total_focus_time", 0),
            desk_seconds=metrics_data["metrics"].get("desk_time_sec", 0.0),
            away_seconds=metrics_data["metrics"].get("away_time_sec", 0.0),
            phone_seconds=phone_summary.get("estimated_phone_usage", 0),
            posture_score=metrics_data["metrics"].get("posture_score", 100.0),
            break_count=len(breaks),
            longest_focus_seconds=focus_totals.get("longest_session", 0),
        )

        # Category rules
        category_rules = self.db.get_category_rules()

        return {
            **metrics_data,
            "live": live_state,
            "timeline": [s.to_dict() for s in timeline_segments],
            "focus": focus_totals,
            "phone_dashboard": phone_summary,
            "presence_dashboard": {
                "desk_time_sec": metrics_data["metrics"].get("desk_time_sec", 0.0),
                "away_time_sec": metrics_data["metrics"].get("away_time_sec", 0.0),
                "breaks": breaks,
            },
            "summary": summary_payload,
            "category_rules": category_rules,
            "performance": self.adaptive_perf.to_dict(),
            "multi_monitor": self.multi_monitor.to_dict(),
            "startup_enabled": self.startup_manager.is_startup_enabled(),
            "window_visible": self.window_visible,
            "active_view": self.active_view,
            "widget": self.widget.to_dict(),
            "tray": self.tray.get_tray_menu_definition()
        }
