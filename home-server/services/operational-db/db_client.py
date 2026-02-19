"""SQLite database client for Sotto operational state."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DatabaseClient:
    """SQLite client for Sotto operational database.

    Manages tasks, heartbeat queue, device state, and processing logs.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to the database and initialize schema."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema()
        logger.info("Database connected: %s", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _initialize_schema(self) -> None:
        """Create tables from schema file."""
        schema = SCHEMA_PATH.read_text()
        self._conn.executescript(schema)
        self._conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    # --- Task Operations ---

    def create_task(
        self,
        description: str,
        source: str = "conversation",
        context: str = "",
        due_at: str | None = None,
        next_remind_at: str | None = None,
        obsidian_path: str | None = None,
        is_private: bool = False,
    ) -> str:
        """Create a new task.

        Returns:
            The generated task ID.
        """
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()

        self.connection.execute(
            """INSERT INTO tasks (id, description, status, created_at, due_at, next_remind_at,
               obsidian_path, source, context, is_private)
               VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, description, now, due_at, next_remind_at, obsidian_path, source, context, is_private),
        )
        self.connection.commit()
        logger.info("Task created: %s - %s", task_id, description[:50])
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get a task by ID."""
        row = self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_pending_tasks(self, include_private: bool = False) -> list[dict[str, Any]]:
        """Get all pending/reminded tasks."""
        if include_private:
            rows = self.connection.execute(
                "SELECT * FROM tasks WHERE status IN ('pending', 'reminded', 'overdue') ORDER BY due_at"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM tasks WHERE status IN ('pending', 'reminded', 'overdue') AND is_private = FALSE ORDER BY due_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tasks_needing_reminder(self, current_time: str | None = None) -> list[dict[str, Any]]:
        """Get tasks whose next_remind_at has passed."""
        if current_time is None:
            current_time = datetime.now(timezone.utc).isoformat()
        rows = self.connection.execute(
            """SELECT * FROM tasks WHERE status IN ('pending', 'reminded')
               AND next_remind_at IS NOT NULL AND next_remind_at <= ?
               AND is_private = FALSE ORDER BY next_remind_at""",
            (current_time,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_task_status(self, task_id: str, status: str) -> None:
        """Update a task's status."""
        self.connection.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        self.connection.commit()

    def update_task_reminder(self, task_id: str, next_remind_at: str, increment_count: bool = True) -> None:
        """Update a task's next reminder time."""
        if increment_count:
            self.connection.execute(
                "UPDATE tasks SET next_remind_at = ?, remind_count = remind_count + 1 WHERE id = ?",
                (next_remind_at, task_id),
            )
        else:
            self.connection.execute(
                "UPDATE tasks SET next_remind_at = ? WHERE id = ?",
                (next_remind_at, task_id),
            )
        self.connection.commit()

    def complete_task(self, task_id: str) -> None:
        """Mark a task as completed."""
        self.update_task_status(task_id, "completed")
        logger.info("Task completed: %s", task_id)

    # --- Heartbeat Queue Operations ---

    def queue_heartbeat(
        self,
        scheduled_at: str,
        content_type: str,
        content: dict[str, Any] | str,
        priority: int = 5,
        is_private: bool = False,
    ) -> int:
        """Add an item to the heartbeat queue.

        Returns:
            The queue item ID.
        """
        if isinstance(content, dict):
            content = json.dumps(content)

        cursor = self.connection.execute(
            """INSERT INTO heartbeat_queue (scheduled_at, content_type, content, priority, is_private)
               VALUES (?, ?, ?, ?, ?)""",
            (scheduled_at, content_type, content, priority, is_private),
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_pending_heartbeats(self, current_time: str | None = None, include_private: bool = False) -> list[dict[str, Any]]:
        """Get heartbeat items ready for delivery."""
        if current_time is None:
            current_time = datetime.now(timezone.utc).isoformat()

        if include_private:
            rows = self.connection.execute(
                """SELECT * FROM heartbeat_queue
                   WHERE delivered_at IS NULL AND scheduled_at <= ?
                   ORDER BY priority, scheduled_at""",
                (current_time,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """SELECT * FROM heartbeat_queue
                   WHERE delivered_at IS NULL AND scheduled_at <= ? AND is_private = FALSE
                   ORDER BY priority, scheduled_at""",
                (current_time,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_heartbeat_delivered(self, heartbeat_id: int) -> None:
        """Mark a heartbeat item as delivered."""
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "UPDATE heartbeat_queue SET delivered_at = ? WHERE id = ?",
            (now, heartbeat_id),
        )
        self.connection.commit()

    # --- Device State Operations ---

    def update_device_state(
        self,
        device_id: str,
        device_type: str = "phone",
        mode: str = "active",
        headphones_connected: bool = False,
        battery_percent: int | None = None,
        audio_quality_avg: float | None = None,
    ) -> None:
        """Update or insert device state."""
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """INSERT OR REPLACE INTO device_state
               (device_id, device_type, last_seen, battery_percent, audio_quality_avg, mode, headphones_connected)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (device_id, device_type, now, battery_percent, audio_quality_avg, mode, headphones_connected),
        )
        self.connection.commit()

    def get_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Get a device's current state."""
        row = self.connection.execute("SELECT * FROM device_state WHERE device_id = ?", (device_id,)).fetchone()
        return dict(row) if row else None

    # --- Processing Log Operations ---

    def log_processing(
        self,
        audio_quality: float | None = None,
        transcription_confidence: float | None = None,
        action_taken: str = "discarded",
        notes: str = "",
    ) -> int:
        """Log a processing event."""
        cursor = self.connection.execute(
            """INSERT INTO processing_log (audio_quality, transcription_confidence, action_taken, notes)
               VALUES (?, ?, ?, ?)""",
            (audio_quality, transcription_confidence, action_taken, notes),
        )
        self.connection.commit()
        return cursor.lastrowid

    # --- Agent Metrics Operations ---

    def update_daily_metrics(
        self,
        date: str | None = None,
        tasks_created: int = 0,
        tasks_completed: int = 0,
        heartbeats_delivered: int = 0,
        transcription_failures: int = 0,
        avg_audio_quality: float | None = None,
    ) -> None:
        """Update or create daily agent metrics."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self.connection.execute(
            """INSERT INTO agent_metrics (date, tasks_created, tasks_completed,
               heartbeats_delivered, transcription_failures, avg_audio_quality)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
               tasks_created = tasks_created + excluded.tasks_created,
               tasks_completed = tasks_completed + excluded.tasks_completed,
               heartbeats_delivered = heartbeats_delivered + excluded.heartbeats_delivered,
               transcription_failures = transcription_failures + excluded.transcription_failures,
               avg_audio_quality = COALESCE(excluded.avg_audio_quality, avg_audio_quality)""",
            (date, tasks_created, tasks_completed, heartbeats_delivered, transcription_failures, avg_audio_quality),
        )
        self.connection.commit()

    def get_daily_metrics(self, date: str) -> dict[str, Any] | None:
        """Get metrics for a specific date."""
        row = self.connection.execute("SELECT * FROM agent_metrics WHERE date = ?", (date,)).fetchone()
        return dict(row) if row else None
