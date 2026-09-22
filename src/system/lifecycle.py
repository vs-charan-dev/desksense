"""DeskSense System Lifecycle Event Listener & Session Manager.
Handles Windows session lock, unlock, sleep, resume, and camera failover/recovery.
Ensures work sessions are cleanly closed during sleep/lock without joining inactive time.
"""

import sys
import os
import time
import uuid
from typing import Optional, Dict, Any, Callable, List


class LifecycleEventType:
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"
    SLEEP = "SLEEP"
    RESUME = "RESUME"
    CAMERA_DISCONNECTED = "CAMERA_DISCONNECTED"
    CAMERA_RECONNECTED = "CAMERA_RECONNECTED"


class SessionManager:
    """Manages active work session state across machine lifecycles."""

    def __init__(
        self,
        clock_func: Optional[Callable[[], float]] = None,
        on_session_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_session_end: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.clock_func = clock_func or time.time
        self.on_session_start = on_session_start
        self.on_session_end = on_session_end

        self.current_session: Optional[Dict[str, Any]] = None
        self.is_locked: bool = False
        self.is_sleeping: bool = False
        self.camera_available: bool = True
        self.completed_sessions: List[Dict[str, Any]] = []

    def start_session(self, session_type: str = "WORK") -> Dict[str, Any]:
        """Starts a new active session."""
        now = self.clock_func()
        if self.current_session is not None:
            self.end_session()

        session = {
            "id": str(uuid.uuid4()),
            "start_time": now,
            "end_time": None,
            "session_type": session_type,
            "duration": 0.0,
            "status": "ACTIVE",
        }
        self.current_session = session
        if self.on_session_start:
            self.on_session_start(session)
        return session

    def end_session(self) -> Optional[Dict[str, Any]]:
        """Ends current active session, recording exact duration."""
        if self.current_session is None:
            return None

        now = self.clock_func()
        start = self.current_session["start_time"]
        duration = max(0.0, now - start)

        self.current_session["end_time"] = now
        self.current_session["duration"] = duration
        self.current_session["status"] = "COMPLETED"

        closed_session = dict(self.current_session)
        self.completed_sessions.append(closed_session)
        self.current_session = None

        if self.on_session_end:
            self.on_session_end(closed_session)

        return closed_session

    def handle_event(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Handles lifecycle state changes (lock, unlock, sleep, resume)."""
        now = self.clock_func()

        if event_type in {LifecycleEventType.LOCK, LifecycleEventType.SLEEP}:
            # Close active session once with valid end time and duration
            closed = None
            if self.current_session is not None:
                closed = self.end_session()

            if event_type == LifecycleEventType.LOCK:
                self.is_locked = True
            elif event_type == LifecycleEventType.SLEEP:
                self.is_sleeping = True

            return closed

        elif event_type in {LifecycleEventType.UNLOCK, LifecycleEventType.RESUME}:
            if event_type == LifecycleEventType.UNLOCK:
                self.is_locked = False
            elif event_type == LifecycleEventType.RESUME:
                self.is_sleeping = False

            # Resume starts one fresh session without joining sleep/lock time
            if not self.is_locked and not self.is_sleeping:
                return self.start_session()

        elif event_type == LifecycleEventType.CAMERA_DISCONNECTED:
            self.camera_available = False
        elif event_type == LifecycleEventType.CAMERA_RECONNECTED:
            self.camera_available = True

        return None
