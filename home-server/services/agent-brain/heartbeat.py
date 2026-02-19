"""Heartbeat scheduler for proactive agent communication."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class HeartbeatScheduler:
    """Manages scheduled heartbeat notifications.

    Checks for pending heartbeat items and delivers them at the right time.
    """

    def __init__(
        self,
        morning_briefing: str = "07:00",
        work_interval_minutes: int = 30,
        evening_summary: str = "18:00",
        work_start: str = "08:00",
        work_end: str = "17:00",
    ) -> None:
        self._morning_briefing = morning_briefing
        self._work_interval_minutes = work_interval_minutes
        self._evening_summary = evening_summary
        self._work_start = work_start
        self._work_end = work_end
        self._last_work_heartbeat: float = 0

    def should_fire_morning_briefing(self, current_time: datetime | None = None) -> bool:
        """Check if it's time for the morning briefing."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        time_str = current_time.strftime("%H:%M")
        return time_str == self._morning_briefing

    def should_fire_evening_summary(self, current_time: datetime | None = None) -> bool:
        """Check if it's time for the evening summary."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        time_str = current_time.strftime("%H:%M")
        return time_str == self._evening_summary

    def should_fire_work_heartbeat(self, current_time: datetime | None = None) -> bool:
        """Check if it's time for a work-hours heartbeat."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        time_str = current_time.strftime("%H:%M")

        # Check if within work hours
        if not (self._work_start <= time_str <= self._work_end):
            return False

        # Check if enough time has passed since last heartbeat
        now_ts = current_time.timestamp()
        elapsed_minutes = (now_ts - self._last_work_heartbeat) / 60

        if elapsed_minutes >= self._work_interval_minutes:
            return True

        return False

    def mark_work_heartbeat_fired(self) -> None:
        """Record that a work heartbeat was just delivered."""
        self._last_work_heartbeat = time.time()

    def get_heartbeat_type(self, current_time: datetime | None = None) -> str | None:
        """Determine which heartbeat type should fire now.

        Returns:
            Heartbeat type string, or None if no heartbeat should fire.
        """
        if self.should_fire_morning_briefing(current_time):
            return "morning_briefing"
        if self.should_fire_evening_summary(current_time):
            return "evening_summary"
        if self.should_fire_work_heartbeat(current_time):
            return "work_interval"
        return None

    def build_morning_briefing(
        self,
        calendar_events: list[str],
        pending_tasks: list[str],
        overnight_alerts: list[str],
    ) -> str:
        """Build the morning briefing text."""
        parts = ["Good morning. Here's your day:"]

        if calendar_events:
            parts.append("Calendar: " + ", ".join(calendar_events) + ".")
        else:
            parts.append("No meetings on your calendar today.")

        if pending_tasks:
            if len(pending_tasks) == 1:
                parts.append(f"You have one pending task: {pending_tasks[0]}.")
            else:
                parts.append(f"You have {len(pending_tasks)} pending tasks: {', '.join(pending_tasks)}.")
        else:
            parts.append("No pending tasks.")

        if overnight_alerts:
            parts.append("Alerts: " + ". ".join(overnight_alerts) + ".")

        return " ".join(parts)

    def build_work_heartbeat(
        self,
        new_tasks: list[str],
        upcoming_events: list[str],
        alerts: list[str],
    ) -> str | None:
        """Build a work-hours heartbeat. Returns None if nothing to report."""
        parts = []

        if alerts:
            parts.append("Alert: " + ". ".join(alerts) + ".")

        if upcoming_events:
            parts.append("Coming up: " + ", ".join(upcoming_events) + ".")

        if new_tasks:
            parts.append("New tasks: " + ", ".join(new_tasks) + ".")

        if not parts:
            return None

        return " ".join(parts)

    def build_evening_summary(
        self,
        tasks_completed: int,
        tasks_created: int,
        incomplete_tasks: list[str],
        tomorrow_events: list[str],
    ) -> str:
        """Build the evening summary text."""
        parts = ["Here's your evening summary."]

        parts.append(f"Tasks: {tasks_completed} completed, {tasks_created} created today.")

        if incomplete_tasks:
            parts.append(f"Still pending: {', '.join(incomplete_tasks)}.")

        if tomorrow_events:
            parts.append(f"Tomorrow: {', '.join(tomorrow_events)}.")
        else:
            parts.append("Nothing on your calendar tomorrow.")

        return " ".join(parts)
