"""
DeskSense Structured Test Fixtures
Deterministic mock fixtures for observations and landmark metrics.
No private recordings or camera frame images.
"""

VALID_OBSERVATION_FIXTURE = {
    "timestamp": "2026-09-22T10:15:22",
    "presence": "PRESENT",
    "posture": "POSTURE_GOOD",
    "attention": "SCREEN",
    "phone_usage": False,
    "active_app": "Code.exe",
    "activity": "FOCUSED_WORK",
    "schema_version": "1.0",
    "confidence": 0.95
}

SLOUCH_OBSERVATION_FIXTURE = {
    "timestamp": "2026-09-22T10:16:00",
    "presence": "PRESENT",
    "posture": "SLOUCHING",
    "attention": "SCREEN",
    "phone_usage": False,
    "active_app": "Code.exe",
    "activity": "ACTIVE_WORK",
    "schema_version": "1.0",
    "confidence": 0.90
}

AWAY_OBSERVATION_FIXTURE = {
    "timestamp": "2026-09-22T10:20:00",
    "presence": "AWAY",
    "posture": "UNKNOWN",
    "attention": "AWAY",
    "phone_usage": False,
    "active_app": "Code.exe",
    "activity": "AWAY",
    "schema_version": "1.0",
    "confidence": 0.0
}
