"""Tests for the device state machine."""

import pytest

from state.device_state import AgentMode, DeviceState, QueuedMessage


@pytest.fixture
def state() -> DeviceState:
    """Create a fresh DeviceState for each test."""
    return DeviceState()


@pytest.fixture
def active_state() -> DeviceState:
    """Create a DeviceState with headphones connected."""
    s = DeviceState()
    s.on_headphones_connected()
    return s


def _make_message(content: str = "test", priority: int = 5, content_type: str = "notification") -> QueuedMessage:
    return QueuedMessage(content=content, priority=priority, content_type=content_type)


class TestInitialState:
    def test_starts_fully_active(self, state: DeviceState) -> None:
        assert state.mode == AgentMode.FULLY_ACTIVE

    def test_starts_without_headphones(self, state: DeviceState) -> None:
        assert state.headphones_connected is False

    def test_starts_with_empty_queue(self, state: DeviceState) -> None:
        assert state.output_queue == []


class TestHeadphoneTransitions:
    def test_connect_headphones_in_input_only(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        state.on_headphones_connected()
        assert state.mode == AgentMode.FULLY_ACTIVE
        assert state.headphones_connected is True

    def test_disconnect_headphones_in_fully_active(self, active_state: DeviceState) -> None:
        active_state.on_headphones_disconnected()
        assert active_state.mode == AgentMode.INPUT_ONLY
        assert active_state.headphones_connected is False

    def test_connect_flushes_queue(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        msg = _make_message("queued item")
        state.output_queue.append(msg)
        flushed = state.on_headphones_connected()
        assert len(flushed) == 1
        assert flushed[0].content == "queued item"
        assert state.output_queue == []

    def test_connect_in_quiet_transitions_to_active(self, state: DeviceState) -> None:
        state.go_quiet()
        messages = state.on_headphones_connected()
        assert state.mode == AgentMode.FULLY_ACTIVE
        assert isinstance(messages, list)

    def test_disconnect_in_quiet_stays_quiet(self, state: DeviceState) -> None:
        state.go_quiet()
        state.on_headphones_disconnected()
        assert state.mode == AgentMode.QUIET

    def test_disconnect_in_sleep_stays_sleep(self, state: DeviceState) -> None:
        state.go_to_sleep()
        state.on_headphones_disconnected()
        assert state.mode == AgentMode.SLEEP_MONITOR


class TestQuietMode:
    def test_go_quiet_from_active(self, active_state: DeviceState) -> None:
        active_state.go_quiet()
        assert active_state.mode == AgentMode.QUIET

    def test_go_quiet_from_input_only(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        state.go_quiet()
        assert state.mode == AgentMode.QUIET

    def test_wake_up_with_headphones(self, active_state: DeviceState) -> None:
        active_state.go_quiet()
        messages = active_state.wake_up()
        assert active_state.mode == AgentMode.FULLY_ACTIVE
        assert isinstance(messages, list)

    def test_wake_up_without_headphones(self, state: DeviceState) -> None:
        state.go_quiet()
        messages = state.wake_up()
        assert state.mode == AgentMode.INPUT_ONLY
        assert messages == []


class TestSleepMode:
    def test_go_to_sleep(self, active_state: DeviceState) -> None:
        active_state.go_to_sleep()
        assert active_state.mode == AgentMode.SLEEP_MONITOR

    def test_good_morning_with_headphones(self, active_state: DeviceState) -> None:
        active_state.go_to_sleep()
        messages = active_state.good_morning()
        assert active_state.mode == AgentMode.FULLY_ACTIVE
        assert isinstance(messages, list)

    def test_good_morning_without_headphones(self, state: DeviceState) -> None:
        state.go_to_sleep()
        messages = state.good_morning()
        assert state.mode == AgentMode.INPUT_ONLY
        assert messages == []

    def test_sleep_queued_messages_delivered_on_morning(self, active_state: DeviceState) -> None:
        active_state.go_to_sleep()
        msg = _make_message("morning brief", priority=1)
        active_state.queue_output(msg)
        messages = active_state.good_morning()
        assert len(messages) == 1
        assert messages[0].content == "morning brief"


class TestOutputQueue:
    def test_queue_when_input_only(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        msg = _make_message("test")
        state.queue_output(msg)
        assert len(state.output_queue) == 1

    def test_queue_when_sleep_monitor(self, state: DeviceState) -> None:
        state.mode = AgentMode.SLEEP_MONITOR
        msg = _make_message("alert")
        state.queue_output(msg)
        assert len(state.output_queue) == 1

    def test_no_queue_when_fully_active_with_headphones(self, active_state: DeviceState) -> None:
        msg = _make_message("direct delivery")
        active_state.queue_output(msg)
        assert len(active_state.output_queue) == 0

    def test_flush_sorts_by_priority(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        state.queue_output(_make_message("low", priority=10))
        state.queue_output(_make_message("high", priority=1))
        state.queue_output(_make_message("med", priority=5))
        flushed = state.on_headphones_connected()
        assert [m.content for m in flushed] == ["high", "med", "low"]


class TestAudioProcessingFlags:
    def test_process_audio_when_active(self, active_state: DeviceState) -> None:
        assert active_state.should_process_audio() is True

    def test_process_audio_when_input_only(self, state: DeviceState) -> None:
        state.mode = AgentMode.INPUT_ONLY
        assert state.should_process_audio() is True

    def test_no_process_audio_when_quiet(self, state: DeviceState) -> None:
        state.go_quiet()
        assert state.should_process_audio() is False

    def test_no_process_audio_when_sleeping(self, state: DeviceState) -> None:
        state.go_to_sleep()
        assert state.should_process_audio() is False

    def test_play_output_only_when_active_with_headphones(self, active_state: DeviceState) -> None:
        assert active_state.should_play_output() is True

    def test_no_play_without_headphones(self, state: DeviceState) -> None:
        assert state.should_play_output() is False

    def test_ambient_monitoring_only_in_sleep(self, state: DeviceState) -> None:
        assert state.can_do_ambient_monitoring() is False
        state.go_to_sleep()
        assert state.can_do_ambient_monitoring() is True


class TestSerialization:
    def test_to_dict(self, active_state: DeviceState) -> None:
        result = active_state.to_dict()
        assert result["mode"] == "FULLY_ACTIVE"
        assert result["headphones_connected"] is True
        assert result["queue_size"] == 0
