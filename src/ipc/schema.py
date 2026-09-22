"""
DeskSense IPC Schema Validation
Defines structured data contracts for IPC between host shell and vision sidecar.
Handles serialization, parsing, enum constraints, and schema version checking.
"""

import json
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, asdict

SUPPORTED_SCHEMA_VERSIONS: Set[str] = {"1.0"}

VALID_PRESENCE = {"PRESENT", "AWAY", "UNKNOWN", True, False}
VALID_POSTURE = {"POSTURE_GOOD", "SLOUCHING", "TOO_CLOSE", "LEAN_LEFT", "LEAN_RIGHT", "HEAD_TILT", "UNKNOWN"}
VALID_ATTENTION = {"SCREEN", "LEFT", "RIGHT", "DOWN", "AWAY", "UNKNOWN"}
VALID_ACTIVITIES = {
    "FOCUSED_WORK", "ACTIVE_WORK", "DISTRACTED", "PHONE_USAGE",
    "IDLE", "AWAY", "BREAK", "UNKNOWN", "focused_work"
}

class IPCValidationError(ValueError):
    """Raised when an IPC message fails structural validation."""
    pass

class UnsupportedSchemaVersionError(IPCValidationError):
    """Raised when the schema version is not supported."""
    pass

class MalformedJsonError(IPCValidationError):
    """Raised when JSON payload is unparseable."""
    pass


@dataclass
class Observation:
    timestamp: str
    presence: str
    posture: str
    attention: str
    phone_usage: bool
    active_app: str
    activity: str
    schema_version: str = "1.0"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        # Check schema version if supplied
        version = str(data.get("schema_version", "1.0"))
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaVersionError(
                f"Unsupported schema version '{version}'. Supported: {SUPPORTED_SCHEMA_VERSIONS}"
            )

        # Required fields check
        required_fields = [
            "timestamp", "presence", "posture", "attention",
            "phone_usage", "active_app", "activity"
        ]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise IPCValidationError(f"Missing required observation fields: {missing}")

        # Normalization & Enum validation
        pres = data["presence"]
        if isinstance(pres, bool):
            pres_str = "PRESENT" if pres else "AWAY"
        elif isinstance(pres, str) and pres.upper() in {"PRESENT", "AWAY", "UNKNOWN"}:
            pres_str = pres.upper()
        else:
            raise IPCValidationError(f"Invalid presence value '{pres}'")

        post = str(data["posture"]).upper()
        if post == "GOOD":
            post = "POSTURE_GOOD"
        if post not in VALID_POSTURE:
            raise IPCValidationError(f"Invalid posture value '{post}'")

        att = str(data["attention"]).upper()
        if att not in VALID_ATTENTION:
            raise IPCValidationError(f"Invalid attention value '{att}'")

        phone = data["phone_usage"]
        if not isinstance(phone, bool):
            raise IPCValidationError(f"phone_usage must be a boolean, got {type(phone).__name__}")

        act_app = data["active_app"]
        if not isinstance(act_app, str):
            raise IPCValidationError("active_app must be a string")

        act = str(data["activity"]).upper()
        if act not in {a.upper() for a in VALID_ACTIVITIES}:
            raise IPCValidationError(f"Invalid activity value '{act}'")

        return cls(
            timestamp=str(data["timestamp"]),
            presence=pres_str,
            posture=post,
            attention=att,
            phone_usage=phone,
            active_app=act_app,
            activity=act,
            schema_version=version,
            confidence=float(data.get("confidence", 1.0))
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Observation":
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise MalformedJsonError(f"Malformed JSON: {e}")
        
        if not isinstance(data, dict):
            raise IPCValidationError("Observation payload must be a JSON object")
        return cls.from_dict(data)
