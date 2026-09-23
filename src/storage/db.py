"""DeskSense SQLite Local Storage Engine.
Implements WAL mode, foreign keys, structured event schema, migrations,
downsampled interval storage, transaction rollbacks, and aggregation queries.
Operates 100% locally with zero cloud dependencies.
"""

import os
import json
import sqlite3
import datetime
from typing import Optional, Dict, Any, List, Tuple


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    start_time REAL NOT NULL,
    end_time REAL,
    session_type TEXT NOT NULL,
    duration REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posture_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    posture_state TEXT NOT NULL,
    confidence REAL NOT NULL,
    sample_count INTEGER DEFAULT 1,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS attention_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    attention_state TEXT NOT NULL,
    confidence REAL NOT NULL,
    sample_count INTEGER DEFAULT 1,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS app_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    application TEXT NOT NULL,
    window_title TEXT,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    duration REAL NOT NULL,
    category TEXT DEFAULT 'Uncategorized',
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT PRIMARY KEY,
    desk_time REAL DEFAULT 0.0,
    active_time REAL DEFAULT 0.0,
    away_time REAL DEFAULT 0.0,
    phone_time REAL DEFAULT 0.0,
    posture_score REAL DEFAULT 0.0,
    break_count INTEGER DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS phone_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration INTEGER NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration INTEGER NOT NULL,
    break_type TEXT DEFAULT 'automatic',
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS work_state_intervals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    state TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    category TEXT NOT NULL,
    is_user_override INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    UNIQUE(pattern, rule_type)
);

CREATE INDEX IF NOT EXISTS idx_category_rules_pattern ON category_rules(pattern, rule_type);
CREATE INDEX IF NOT EXISTS idx_phone_sessions_time ON phone_sessions(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_breaks_time ON breaks(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_work_state_time ON work_state_intervals(start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_posture_time ON posture_events(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_attention_time ON attention_events(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_app_usage_time ON app_usage(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_sessions_time ON sessions(start_time, end_time);
"""


class DatabaseEngine:
    """Embedded SQLite storage engine for DeskSense."""

    def __init__(self, db_path: str = "desksense.db"):
        self.db_path = db_path
        self._shared_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA foreign_keys = ON;")
        else:
            # Ensure parent directory exists if path includes a directory
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

        self._active_posture_interval: Optional[Dict[str, Any]] = None
        self._active_attention_interval: Optional[Dict[str, Any]] = None
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Returns SQLite connection with row factory enabled."""
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_schema(self) -> None:
        """Initializes tables and indices idempotently."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    # ---------------- Settings ----------------
    def set_setting(self, key: str, value: Any, timestamp: Optional[float] = None) -> None:
        ts = timestamp or datetime.datetime.now().timestamp()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, val_str, ts),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            val_str = row["value"]
            try:
                return json.loads(val_str)
            except Exception:
                return val_str

    # ---------------- Sessions ----------------
    def record_session(self, session: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, start_time, end_time, session_type, duration, status) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET end_time=excluded.end_time, duration=excluded.duration, status=excluded.status",
                (
                    session["id"],
                    session["start_time"],
                    session.get("end_time"),
                    session.get("session_type", "WORK"),
                    session.get("duration", 0.0),
                    session.get("status", "COMPLETED"),
                ),
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None

    # ---------------- Posture Events & Downsampling ----------------
    def record_posture_sample(
        self,
        posture_state: str,
        confidence: float,
        timestamp: float,
        session_id: Optional[str] = None,
    ) -> None:
        """Downsamples continuous camera frame predictions into compact intervals."""
        if self._active_posture_interval is None:
            self._active_posture_interval = {
                "session_id": session_id,
                "start_time": timestamp,
                "end_time": timestamp,
                "posture_state": posture_state,
                "confidence_sum": confidence,
                "count": 1,
            }
            return

        curr = self._active_posture_interval
        # If the state is the same and consecutive within 2 seconds, extend interval
        if curr["posture_state"] == posture_state and (timestamp - curr["end_time"]) <= 2.0:
            curr["end_time"] = timestamp
            curr["confidence_sum"] += confidence
            curr["count"] += 1
        else:
            # Commit finished interval and start new
            self.flush_posture_interval()
            self._active_posture_interval = {
                "session_id": session_id,
                "start_time": timestamp,
                "end_time": timestamp,
                "posture_state": posture_state,
                "confidence_sum": confidence,
                "count": 1,
            }

    def flush_posture_interval(self) -> None:
        if not self._active_posture_interval:
            return
        curr = self._active_posture_interval
        avg_conf = curr["confidence_sum"] / max(1, curr["count"])
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO posture_events (session_id, start_time, end_time, posture_state, confidence, sample_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    curr["session_id"],
                    curr["start_time"],
                    curr["end_time"],
                    curr["posture_state"],
                    avg_conf,
                    curr["count"],
                ),
            )
        self._active_posture_interval = None

    def insert_posture_event(
        self,
        posture_state: str,
        confidence: float,
        start_time: float,
        end_time: float,
        session_id: Optional[str] = None,
        sample_count: int = 1,
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO posture_events (session_id, start_time, end_time, posture_state, confidence, sample_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, start_time, end_time, posture_state, confidence, sample_count),
            )

    # ---------------- Attention Events & Downsampling ----------------
    def record_attention_sample(
        self,
        attention_state: str,
        confidence: float,
        timestamp: float,
        session_id: Optional[str] = None,
    ) -> None:
        if self._active_attention_interval is None:
            self._active_attention_interval = {
                "session_id": session_id,
                "start_time": timestamp,
                "end_time": timestamp,
                "attention_state": attention_state,
                "confidence_sum": confidence,
                "count": 1,
            }
            return

        curr = self._active_attention_interval
        if curr["attention_state"] == attention_state and (timestamp - curr["end_time"]) <= 2.0:
            curr["end_time"] = timestamp
            curr["confidence_sum"] += confidence
            curr["count"] += 1
        else:
            self.flush_attention_interval()
            self._active_attention_interval = {
                "session_id": session_id,
                "start_time": timestamp,
                "end_time": timestamp,
                "attention_state": attention_state,
                "confidence_sum": confidence,
                "count": 1,
            }

    def flush_attention_interval(self) -> None:
        if not self._active_attention_interval:
            return
        curr = self._active_attention_interval
        avg_conf = curr["confidence_sum"] / max(1, curr["count"])
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO attention_events (session_id, start_time, end_time, attention_state, confidence, sample_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    curr["session_id"],
                    curr["start_time"],
                    curr["end_time"],
                    curr["attention_state"],
                    avg_conf,
                    curr["count"],
                ),
            )
        self._active_attention_interval = None

    def insert_attention_event(
        self,
        attention_state: str,
        confidence: float,
        start_time: float,
        end_time: float,
        session_id: Optional[str] = None,
        sample_count: int = 1,
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO attention_events (session_id, start_time, end_time, attention_state, confidence, sample_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, start_time, end_time, attention_state, confidence, sample_count),
            )

    # ---------------- App Usage ----------------
    def record_app_usage(
        self,
        application: str,
        window_title: str,
        start_time: float,
        end_time: float,
        category: str = "Uncategorized",
        session_id: Optional[str] = None,
    ) -> None:
        duration = max(0.0, end_time - start_time)
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO app_usage (session_id, application, window_title, start_time, end_time, duration, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, application, window_title, start_time, end_time, duration, category),
            )

    # ---------------- Transactions & Rollback ----------------
    def execute_batch_transaction(self, operations: List[Tuple[str, Tuple]]) -> None:
        """Executes a list of (sql, params) in a single atomic transaction.
        Rolls back completely if any statement fails.
        """
        conn = self.get_connection()
        try:
            with conn:
                for sql, params in operations:
                    conn.execute(sql, params)
        finally:
            conn.close()

    # ---------------- Aggregation & Metrics ----------------
    def calculate_daily_metrics(self, start_timestamp: float, end_timestamp: float) -> Dict[str, Any]:
        """Calculates desk time, away time, active computer time, and posture score."""
        with self.get_connection() as conn:
            # Active computer time from app_usage
            row_active = conn.execute(
                "SELECT SUM(duration) as total_active FROM app_usage "
                "WHERE start_time >= ? AND end_time <= ?",
                (start_timestamp, end_timestamp),
            ).fetchone()
            active_time = float(row_active["total_active"] or 0.0)

            # Posture breakdown
            rows_posture = conn.execute(
                "SELECT posture_state, SUM(end_time - start_time) as total_dur FROM posture_events "
                "WHERE start_time >= ? AND end_time <= ? GROUP BY posture_state",
                (start_timestamp, end_timestamp),
            ).fetchall()

            posture_durations: Dict[str, float] = {}
            for r in rows_posture:
                posture_durations[r["posture_state"]] = float(r["total_dur"])

            # Attention breakdown
            rows_attn = conn.execute(
                "SELECT attention_state, SUM(end_time - start_time) as total_dur FROM attention_events "
                "WHERE start_time >= ? AND end_time <= ? GROUP BY attention_state",
                (start_timestamp, end_timestamp),
            ).fetchall()

            attn_durations: Dict[str, float] = {}
            for r in rows_attn:
                attn_durations[r["attention_state"]] = float(r["total_dur"])

            away_time = attn_durations.get("AWAY", 0.0)

            # Total desk time = sum of all posture intervals where user was detected at desk
            desk_posture_keys = {"POSTURE_GOOD", "SLOUCHING", "TOO_CLOSE", "LEAN_LEFT", "LEAN_RIGHT", "HEAD_TILT"}
            desk_time = sum(dur for state, dur in posture_durations.items() if state in desk_posture_keys)

            good_time = posture_durations.get("POSTURE_GOOD", 0.0)
            posture_score = (good_time / desk_time * 100.0) if desk_time > 0 else 100.0

            return {
                "desk_time": round(desk_time, 2),
                "away_time": round(away_time, 2),
                "active_time": round(active_time, 2),
                "posture_score": round(posture_score, 1),
                "posture_breakdown": posture_durations,
                "attention_breakdown": attn_durations,
            }

    def log_phone_session(
        self,
        start_time: str,
        end_time: str,
        duration: int,
        confidence: float,
        session_id: Optional[str] = None,
    ) -> int:
        """Stores one estimated phone usage session."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO phone_sessions (session_id, start_time, end_time, duration, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, start_time, end_time, duration, confidence),
            )
            conn.commit()
            return cur.lastrowid

    def get_phone_sessions(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches stored phone sessions."""
        with self.get_connection() as conn:
            if session_id:
                cur = conn.execute("SELECT * FROM phone_sessions WHERE session_id = ? ORDER BY id ASC", (session_id,))
            else:
                cur = conn.execute("SELECT * FROM phone_sessions ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    def get_phone_summary(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Aggregates phone sessions.
        Strictly labeled as 'estimated phone usage' per requirements.
        """
        sessions = self.get_phone_sessions(session_id)
        total_seconds = sum(s["duration"] for s in sessions)
        count = len(sessions)
        longest = max((s["duration"] for s in sessions), default=0)
        avg = int(round(total_seconds / count)) if count > 0 else 0

        return {
            "estimated_phone_usage": total_seconds,
            "estimated_sessions": count,
            "longest_session": longest,
            "average_session": avg,
            "wording": "estimated phone usage",
        }

    def log_break(
        self,
        start_time: str,
        end_time: str,
        duration: int,
        break_type: str = "automatic",
        session_id: Optional[str] = None,
    ) -> int:
        """Stores one break interval."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO breaks (session_id, start_time, end_time, duration, break_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, start_time, end_time, duration, break_type),
            )
            conn.commit()
            return cur.lastrowid

    def get_breaks(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches stored breaks."""
        with self.get_connection() as conn:
            if session_id:
                cur = conn.execute("SELECT * FROM breaks WHERE session_id = ? ORDER BY id ASC", (session_id,))
            else:
                cur = conn.execute("SELECT * FROM breaks ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    def log_work_state_interval(
        self,
        state: str,
        start_time: str,
        end_time: str,
        duration: int,
        session_id: Optional[str] = None,
    ) -> int:
        """Stores one non-overlapping work state interval."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO work_state_intervals (session_id, state, start_time, end_time, duration) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, state, start_time, end_time, duration),
            )
            conn.commit()
            return cur.lastrowid

    def get_work_state_intervals(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches stored work state intervals."""
        with self.get_connection() as conn:
            if session_id:
                cur = conn.execute("SELECT * FROM work_state_intervals WHERE session_id = ? ORDER BY id ASC", (session_id,))
            else:
                cur = conn.execute("SELECT * FROM work_state_intervals ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    def insert_category_rule(
        self,
        pattern: str,
        rule_type: str,
        category: str,
        is_user_override: bool = True,
    ) -> int:
        """Inserts or replaces an app category rule."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT OR REPLACE INTO category_rules (pattern, rule_type, category, is_user_override, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pattern.lower().strip(), rule_type.lower().strip(), category.lower().strip(), 1 if is_user_override else 0, datetime.datetime.now().timestamp()),
            )
            conn.commit()
            return cur.lastrowid

    def get_category_rules(self) -> List[Dict[str, Any]]:
        """Fetches all stored app category rules."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM category_rules ORDER BY is_user_override DESC, id ASC")
            return [dict(r) for r in cur.fetchall()]

    def delete_category_rule(self, rule_id: int) -> bool:
        """Deletes a category rule by ID."""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_category_rules(self) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM category_rules")
            conn.commit()

    def close(self) -> None:
        self.flush_posture_interval()
        self.flush_attention_interval()
