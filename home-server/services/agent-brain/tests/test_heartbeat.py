"""Tests for the heartbeat scheduler."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from heartbeat import HeartbeatScheduler


class TestHeartbeatSchedulerInit:
    def test_defaults(self) -> None:
        hs = HeartbeatScheduler()
        assert hs._morning_briefing == "07:00"
        assert hs._evening_summary == "18:00"
        assert hs._work_interval_minutes == 30
        assert hs._work_start == "08:00"
        assert hs._work_end == "17:00"

    def test_custom_params(self) -> None:
        hs = HeartbeatScheduler(
            morning_briefing="06:30",
            work_interval_minutes=15,
            evening_summary="19:00",
            work_start="09:00",
            work_end="18:00",
        )
        assert hs._morning_briefing == "06:30"
        assert hs._work_interval_minutes == 15


class TestMorningBriefing:
    def test_fires_at_correct_time(self) -> None:
        hs = HeartbeatScheduler(morning_briefing="07:00")
        t = datetime(2025, 1, 15, 7, 0, tzinfo=timezone.utc)
        assert hs.should_fire_morning_briefing(t) is True

    def test_does_not_fire_at_wrong_time(self) -> None:
        hs = HeartbeatScheduler(morning_briefing="07:00")
        t = datetime(2025, 1, 15, 7, 1, tzinfo=timezone.utc)
        assert hs.should_fire_morning_briefing(t) is False


class TestEveningSummary:
    def test_fires_at_correct_time(self) -> None:
        hs = HeartbeatScheduler(evening_summary="18:00")
        t = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
        assert hs.should_fire_evening_summary(t) is True

    def test_does_not_fire_at_wrong_time(self) -> None:
        hs = HeartbeatScheduler(evening_summary="18:00")
        t = datetime(2025, 1, 15, 17, 59, tzinfo=timezone.utc)
        assert hs.should_fire_evening_summary(t) is False


class TestWorkHeartbeat:
    def test_fires_during_work_hours(self) -> None:
        hs = HeartbeatScheduler(work_start="08:00", work_end="17:00", work_interval_minutes=30)
        # Force last heartbeat to be long ago
        hs._last_work_heartbeat = 0
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert hs.should_fire_work_heartbeat(t) is True

    def test_does_not_fire_before_work(self) -> None:
        hs = HeartbeatScheduler(work_start="08:00", work_end="17:00")
        hs._last_work_heartbeat = 0
        t = datetime(2025, 1, 15, 7, 0, tzinfo=timezone.utc)
        assert hs.should_fire_work_heartbeat(t) is False

    def test_does_not_fire_after_work(self) -> None:
        hs = HeartbeatScheduler(work_start="08:00", work_end="17:00")
        hs._last_work_heartbeat = 0
        t = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
        assert hs.should_fire_work_heartbeat(t) is False

    def test_respects_interval(self) -> None:
        hs = HeartbeatScheduler(work_start="08:00", work_end="17:00", work_interval_minutes=30)
        # Set last heartbeat to recent
        hs._last_work_heartbeat = time.time()
        t = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert hs.should_fire_work_heartbeat(t) is False

    def test_mark_work_heartbeat_fired(self) -> None:
        hs = HeartbeatScheduler()
        assert hs._last_work_heartbeat == 0
        hs.mark_work_heartbeat_fired()
        assert hs._last_work_heartbeat > 0


class TestGetHeartbeatType:
    def test_morning_briefing(self) -> None:
        hs = HeartbeatScheduler(morning_briefing="07:00")
        t = datetime(2025, 1, 15, 7, 0, tzinfo=timezone.utc)
        assert hs.get_heartbeat_type(t) == "morning_briefing"

    def test_evening_summary(self) -> None:
        hs = HeartbeatScheduler(evening_summary="18:00")
        t = datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc)
        assert hs.get_heartbeat_type(t) == "evening_summary"

    def test_work_interval(self) -> None:
        hs = HeartbeatScheduler(work_start="08:00", work_end="17:00")
        hs._last_work_heartbeat = 0
        t = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert hs.get_heartbeat_type(t) == "work_interval"

    def test_no_heartbeat(self) -> None:
        hs = HeartbeatScheduler()
        hs._last_work_heartbeat = time.time()
        t = datetime(2025, 1, 15, 12, 30, tzinfo=timezone.utc)
        assert hs.get_heartbeat_type(t) is None

    def test_morning_takes_priority(self) -> None:
        hs = HeartbeatScheduler(morning_briefing="08:00", work_start="08:00", work_end="17:00")
        hs._last_work_heartbeat = 0
        t = datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc)
        # Morning briefing should take priority
        assert hs.get_heartbeat_type(t) == "morning_briefing"


class TestBuildMorningBriefing:
    def test_full_briefing(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_morning_briefing(
            calendar_events=["Team standup at 9am", "Lunch with Bob at 12"],
            pending_tasks=["Review PR", "Update docs"],
            overnight_alerts=["Server disk usage at 90%"],
        )
        assert "Good morning" in text
        assert "Team standup" in text
        assert "2 pending tasks" in text
        assert "Server disk usage" in text

    def test_empty_briefing(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_morning_briefing(
            calendar_events=[],
            pending_tasks=[],
            overnight_alerts=[],
        )
        assert "Good morning" in text
        assert "No meetings" in text
        assert "No pending tasks" in text

    def test_single_task(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_morning_briefing(
            calendar_events=[],
            pending_tasks=["Only task"],
            overnight_alerts=[],
        )
        assert "one pending task" in text
        assert "Only task" in text


class TestBuildWorkHeartbeat:
    def test_with_content(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_work_heartbeat(
            new_tasks=["Buy groceries"],
            upcoming_events=["Meeting at 3pm"],
            alerts=["Battery low"],
        )
        assert text is not None
        assert "Buy groceries" in text
        assert "Meeting at 3pm" in text
        assert "Battery low" in text

    def test_nothing_to_report(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_work_heartbeat(
            new_tasks=[],
            upcoming_events=[],
            alerts=[],
        )
        assert text is None

    def test_only_alerts(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_work_heartbeat(
            new_tasks=[],
            upcoming_events=[],
            alerts=["Important alert"],
        )
        assert text is not None
        assert "Important alert" in text


class TestBuildEveningSummary:
    def test_full_summary(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_evening_summary(
            tasks_completed=5,
            tasks_created=3,
            incomplete_tasks=["Finish report", "Call dentist"],
            tomorrow_events=["Doctor appointment at 10am"],
        )
        assert "evening summary" in text
        assert "5 completed" in text
        assert "3 created" in text
        assert "Finish report" in text
        assert "Doctor appointment" in text

    def test_no_incomplete_no_tomorrow(self) -> None:
        hs = HeartbeatScheduler()
        text = hs.build_evening_summary(
            tasks_completed=0,
            tasks_created=0,
            incomplete_tasks=[],
            tomorrow_events=[],
        )
        assert "evening summary" in text
        assert "Nothing on your calendar" in text
