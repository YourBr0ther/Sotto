"""Device state machine for Sotto edge device."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class AgentMode(Enum):
    """Operating modes for the Sotto agent."""

    FULLY_ACTIVE = auto()    # Headphones on, listening, can speak
    INPUT_ONLY = auto()      # Headphones off, listening, queuing output
    QUIET = auto()           # Manual trigger only, discarding audio, no processing
    SLEEP_MONITOR = auto()   # Minimal processing, ambient health only


@dataclass
class QueuedMessage:
    """A message queued for delivery when output becomes available."""

    content: str
    priority: int  # 1 = highest, 10 = lowest
    content_type: str  # heartbeat, notification, task_reminder, alert
    timestamp: str = ""


@dataclass
class DeviceState:
    """Manages the agent's operating mode and output queue.

    State transitions:
      FULLY_ACTIVE -> INPUT_ONLY:    Headphones disconnect
      INPUT_ONLY -> FULLY_ACTIVE:    Headphones reconnect (deliver queued items)
      ANY -> QUIET:                  Voice command "agent go quiet"
      QUIET -> FULLY_ACTIVE:         Voice command "agent wake up" or headphone reconnect
      ANY -> SLEEP_MONITOR:          Scheduled time or voice command "agent goodnight"
      SLEEP_MONITOR -> FULLY_ACTIVE: Morning alarm or voice command "agent good morning"
    """

    mode: AgentMode = AgentMode.FULLY_ACTIVE
    headphones_connected: bool = False
    output_queue: list[QueuedMessage] = field(default_factory=list)

    def on_headphones_connected(self) -> list[QueuedMessage]:
        """Handle headphone connection event.

        Returns:
            List of queued messages to deliver now, sorted by priority.
        """
        self.headphones_connected = True
        if self.mode == AgentMode.INPUT_ONLY:
            self.mode = AgentMode.FULLY_ACTIVE
            logger.info("Headphones connected: INPUT_ONLY -> FULLY_ACTIVE")
            return self._flush_queue()
        if self.mode == AgentMode.QUIET:
            self.mode = AgentMode.FULLY_ACTIVE
            logger.info("Headphones connected: QUIET -> FULLY_ACTIVE")
            return self._flush_queue()
        logger.info("Headphones connected (mode unchanged: %s)", self.mode.name)
        return []

    def on_headphones_disconnected(self) -> None:
        """Handle headphone disconnection event."""
        self.headphones_connected = False
        if self.mode == AgentMode.FULLY_ACTIVE:
            self.mode = AgentMode.INPUT_ONLY
            logger.info("Headphones disconnected: FULLY_ACTIVE -> INPUT_ONLY")

    def go_quiet(self) -> None:
        """Transition to QUIET mode. Stops all audio processing."""
        previous = self.mode
        self.mode = AgentMode.QUIET
        logger.info("Going quiet: %s -> QUIET", previous.name)

    def wake_up(self) -> list[QueuedMessage]:
        """Transition from QUIET back to active.

        Returns:
            List of queued messages if headphones are connected.
        """
        if self.headphones_connected:
            self.mode = AgentMode.FULLY_ACTIVE
            logger.info("Waking up: -> FULLY_ACTIVE (headphones connected)")
            return self._flush_queue()
        self.mode = AgentMode.INPUT_ONLY
        logger.info("Waking up: -> INPUT_ONLY (headphones not connected)")
        return []

    def go_to_sleep(self) -> None:
        """Transition to SLEEP_MONITOR mode."""
        previous = self.mode
        self.mode = AgentMode.SLEEP_MONITOR
        logger.info("Going to sleep: %s -> SLEEP_MONITOR", previous.name)

    def good_morning(self) -> list[QueuedMessage]:
        """Transition from sleep to active.

        Returns:
            List of queued messages if headphones are connected.
        """
        if self.headphones_connected:
            self.mode = AgentMode.FULLY_ACTIVE
            logger.info("Good morning: -> FULLY_ACTIVE (headphones connected)")
            return self._flush_queue()
        self.mode = AgentMode.INPUT_ONLY
        logger.info("Good morning: -> INPUT_ONLY (headphones not connected)")
        return []

    def queue_output(self, message: QueuedMessage) -> None:
        """Queue a message for later delivery.

        Messages are only queued when the agent can't currently play output.
        If the agent can play output, the caller should deliver directly.
        """
        if not self.should_play_output():
            self.output_queue.append(message)
            logger.debug(
                "Queued message (type=%s, priority=%d, queue_size=%d)",
                message.content_type,
                message.priority,
                len(self.output_queue),
            )

    def should_process_audio(self) -> bool:
        """Whether the agent should process incoming audio."""
        return self.mode in (AgentMode.FULLY_ACTIVE, AgentMode.INPUT_ONLY)

    def should_play_output(self) -> bool:
        """Whether the agent can play audio to the user."""
        return self.mode == AgentMode.FULLY_ACTIVE and self.headphones_connected

    def can_do_ambient_monitoring(self) -> bool:
        """Whether to run lightweight ambient analysis (snoring, etc.)."""
        return self.mode == AgentMode.SLEEP_MONITOR

    def _flush_queue(self) -> list[QueuedMessage]:
        """Return queued messages sorted by priority (lowest number = highest priority)."""
        messages = sorted(self.output_queue, key=lambda m: m.priority)
        self.output_queue.clear()
        logger.info("Flushed %d queued messages", len(messages))
        return messages

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for MQTT publishing."""
        return {
            "mode": self.mode.name,
            "headphones_connected": self.headphones_connected,
            "queue_size": len(self.output_queue),
        }
