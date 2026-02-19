"""Tests for the SQLite operational database client."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from db_client import DatabaseClient


@pytest.fixture
def db() -> DatabaseClient:
    """Create an in-memory database for testing."""
    client = DatabaseClient(":memory:")
    client.connect()
    yield client
    client.close()


class TestConnection:
    def test_connect_creates_tables(self, db: DatabaseClient) -> None:
        tables = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "tasks" in table_names
        assert "heartbeat_queue" in table_names
        assert "device_state" in table_names
        assert "processing_log" in table_names
        assert "agent_metrics" in table_names

    def test_connection_property_raises_when_not_connected(self) -> None:
        client = DatabaseClient(":memory:")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.connection


class TestTasks:
    def test_create_task(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Schedule haircut", source="conversation", context="Wife asked")
        assert task_id is not None
        assert len(task_id) == 8

    def test_get_task(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Test task", source="manual")
        task = db.get_task(task_id)
        assert task is not None
        assert task["description"] == "Test task"
        assert task["status"] == "pending"
        assert task["source"] == "manual"

    def test_get_nonexistent_task(self, db: DatabaseClient) -> None:
        task = db.get_task("nonexistent")
        assert task is None

    def test_get_pending_tasks(self, db: DatabaseClient) -> None:
        db.create_task("Task 1", source="manual")
        db.create_task("Task 2", source="manual")
        task_id = db.create_task("Task 3", source="manual")
        db.complete_task(task_id)

        pending = db.get_pending_tasks()
        assert len(pending) == 2

    def test_get_pending_tasks_excludes_private(self, db: DatabaseClient) -> None:
        db.create_task("Public task", source="manual")
        db.create_task("Private task", source="manual", is_private=True)

        public = db.get_pending_tasks(include_private=False)
        assert len(public) == 1
        assert public[0]["description"] == "Public task"

        all_tasks = db.get_pending_tasks(include_private=True)
        assert len(all_tasks) == 2

    def test_update_task_status(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Status test", source="manual")
        db.update_task_status(task_id, "reminded")
        task = db.get_task(task_id)
        assert task["status"] == "reminded"

    def test_complete_task(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Complete me", source="manual")
        db.complete_task(task_id)
        task = db.get_task(task_id)
        assert task["status"] == "completed"

    def test_update_task_reminder(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Remind me", source="manual", next_remind_at="2026-02-19T12:00:00Z")
        db.update_task_reminder(task_id, "2026-02-20T12:00:00Z")
        task = db.get_task(task_id)
        assert task["next_remind_at"] == "2026-02-20T12:00:00Z"
        assert task["remind_count"] == 1

    def test_get_tasks_needing_reminder(self, db: DatabaseClient) -> None:
        db.create_task("Past reminder", source="manual", next_remind_at="2026-02-19T10:00:00Z")
        db.create_task("Future reminder", source="manual", next_remind_at="2026-12-31T23:59:59Z")

        tasks = db.get_tasks_needing_reminder("2026-02-19T12:00:00Z")
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Past reminder"

    def test_create_task_with_due_date(self, db: DatabaseClient) -> None:
        task_id = db.create_task("Due task", source="calendar", due_at="2026-02-22T00:00:00Z")
        task = db.get_task(task_id)
        assert task["due_at"] == "2026-02-22T00:00:00Z"


class TestHeartbeatQueue:
    def test_queue_heartbeat(self, db: DatabaseClient) -> None:
        hb_id = db.queue_heartbeat(
            scheduled_at="2026-02-19T07:00:00Z",
            content_type="briefing",
            content={"items": ["weather", "calendar"]},
            priority=3,
        )
        assert hb_id is not None

    def test_get_pending_heartbeats(self, db: DatabaseClient) -> None:
        db.queue_heartbeat("2026-02-19T07:00:00Z", "briefing", "Morning brief", priority=3)
        db.queue_heartbeat("2026-02-19T12:00:00Z", "task_reminder", "Task reminder", priority=5)
        db.queue_heartbeat("2026-12-31T23:59:59Z", "briefing", "Future brief", priority=3)

        pending = db.get_pending_heartbeats("2026-02-19T13:00:00Z")
        assert len(pending) == 2

    def test_pending_heartbeats_sorted_by_priority(self, db: DatabaseClient) -> None:
        db.queue_heartbeat("2026-02-19T07:00:00Z", "briefing", "Low priority", priority=8)
        db.queue_heartbeat("2026-02-19T07:00:00Z", "alert", "High priority", priority=1)

        pending = db.get_pending_heartbeats("2026-02-19T08:00:00Z")
        assert pending[0]["content"] == "High priority"
        assert pending[1]["content"] == "Low priority"

    def test_mark_heartbeat_delivered(self, db: DatabaseClient) -> None:
        hb_id = db.queue_heartbeat("2026-02-19T07:00:00Z", "briefing", "Test")
        db.mark_heartbeat_delivered(hb_id)

        pending = db.get_pending_heartbeats("2026-02-19T08:00:00Z")
        assert len(pending) == 0

    def test_heartbeats_exclude_private(self, db: DatabaseClient) -> None:
        db.queue_heartbeat("2026-02-19T07:00:00Z", "briefing", "Public", is_private=False)
        db.queue_heartbeat("2026-02-19T07:00:00Z", "briefing", "Private", is_private=True)

        public = db.get_pending_heartbeats("2026-02-19T08:00:00Z", include_private=False)
        assert len(public) == 1
        assert public[0]["content"] == "Public"


class TestDeviceState:
    def test_update_device_state(self, db: DatabaseClient) -> None:
        db.update_device_state("sotto-phone", device_type="phone", mode="active")
        state = db.get_device_state("sotto-phone")
        assert state is not None
        assert state["device_type"] == "phone"
        assert state["mode"] == "active"

    def test_update_overwrites_existing(self, db: DatabaseClient) -> None:
        db.update_device_state("sotto-phone", mode="active")
        db.update_device_state("sotto-phone", mode="quiet")
        state = db.get_device_state("sotto-phone")
        assert state["mode"] == "quiet"

    def test_get_nonexistent_device(self, db: DatabaseClient) -> None:
        state = db.get_device_state("nonexistent")
        assert state is None


class TestProcessingLog:
    def test_log_processing(self, db: DatabaseClient) -> None:
        log_id = db.log_processing(
            audio_quality=0.85,
            transcription_confidence=0.92,
            action_taken="task_created",
            notes="Created haircut task",
        )
        assert log_id is not None

    def test_log_with_minimal_data(self, db: DatabaseClient) -> None:
        log_id = db.log_processing(action_taken="discarded")
        assert log_id is not None


class TestAgentMetrics:
    def test_update_daily_metrics(self, db: DatabaseClient) -> None:
        db.update_daily_metrics(
            date="2026-02-19",
            tasks_created=3,
            tasks_completed=1,
            heartbeats_delivered=5,
        )
        metrics = db.get_daily_metrics("2026-02-19")
        assert metrics is not None
        assert metrics["tasks_created"] == 3
        assert metrics["tasks_completed"] == 1
        assert metrics["heartbeats_delivered"] == 5

    def test_metrics_accumulate(self, db: DatabaseClient) -> None:
        db.update_daily_metrics(date="2026-02-19", tasks_created=2)
        db.update_daily_metrics(date="2026-02-19", tasks_created=3)
        metrics = db.get_daily_metrics("2026-02-19")
        assert metrics["tasks_created"] == 5

    def test_get_nonexistent_date(self, db: DatabaseClient) -> None:
        metrics = db.get_daily_metrics("2099-01-01")
        assert metrics is None
