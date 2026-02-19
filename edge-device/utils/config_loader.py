"""YAML configuration loader for Sotto edge device."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeviceConfig:
    name: str = "sotto-phone"
    type: str = "android"


@dataclass
class AudioConfig:
    input_device: int | None = None
    output_device: int | None = None
    sample_rate: int = 16000
    chunk_duration_ms: int = 500
    noise_filter_enabled: bool = True


@dataclass
class WakeWordConfig:
    engine: str = "openwakeword"
    model: str = "hey_jarvis"
    threshold: float = 0.7
    acknowledgment_sound: bool = True


@dataclass
class MqttTopics:
    audio_stream: str = "sotto/audio/raw"
    transcription: str = "sotto/audio/transcription"
    commands: str = "sotto/agent/commands"
    heartbeat: str = "sotto/agent/heartbeat"
    notifications: str = "sotto/agent/notifications"
    tts_audio: str = "sotto/audio/tts"
    tts_text: str = "sotto/audio/tts_text"
    device_state: str = "sotto/device/state"
    agent_mode: str = "sotto/agent/mode"


@dataclass
class MqttConfig:
    broker_host: str = "localhost"
    broker_port: int = 1883
    client_id: str = "sotto-phone"
    username: str = ""
    password: str = ""
    topics: MqttTopics = field(default_factory=MqttTopics)


@dataclass
class HeartbeatSchedule:
    morning_briefing: str = "07:00"
    work_intervals_minutes: int = 30
    evening_summary: str = "18:00"


@dataclass
class WorkHours:
    start: str = "08:00"
    end: str = "17:00"


@dataclass
class HeartbeatConfig:
    schedule: HeartbeatSchedule = field(default_factory=HeartbeatSchedule)
    work_hours: WorkHours = field(default_factory=WorkHours)


@dataclass
class AgentConfig:
    quiet_command: str = "agent go quiet"
    wake_command: str = "agent wake up"
    goodnight_command: str = "agent goodnight"
    morning_command: str = "agent good morning"


@dataclass
class ConnectivityConfig:
    retry_interval_seconds: int = 10
    offline_buffer_max_mb: int = 500
    sync_on_reconnect: bool = True


@dataclass
class SottoConfig:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    connectivity: ConnectivityConfig = field(default_factory=ConnectivityConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides. Format: SOTTO_SECTION_KEY=value."""
    env_prefix = "SOTTO_"
    for key, value in os.environ.items():
        if not key.startswith(env_prefix):
            continue
        parts = key[len(env_prefix):].lower().split("_", 1)
        if len(parts) == 2:
            section, setting = parts
            if section in data:
                if isinstance(data[section], dict):
                    data[section][setting] = _coerce_type(value)
    return data


def _coerce_type(value: str) -> Any:
    """Coerce string environment variable to appropriate Python type."""
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _dict_to_config(data: dict[str, Any]) -> SottoConfig:
    """Convert a nested dict to a SottoConfig dataclass."""
    device_data = data.get("device", {})
    audio_data = data.get("audio", {})
    wake_word_data = data.get("wake_word", {})
    mqtt_data = data.get("mqtt", {})
    heartbeat_data = data.get("heartbeat", {})
    agent_data = data.get("agent", {})
    connectivity_data = data.get("connectivity", {})

    # Build nested MQTT topics
    mqtt_topics_data = mqtt_data.pop("topics", {})
    mqtt_topics = MqttTopics(**{k: v for k, v in mqtt_topics_data.items() if k in MqttTopics.__dataclass_fields__})

    # Build nested heartbeat
    schedule_data = heartbeat_data.pop("schedule", {})
    work_hours_data = heartbeat_data.pop("work_hours", {})

    return SottoConfig(
        device=DeviceConfig(**{k: v for k, v in device_data.items() if k in DeviceConfig.__dataclass_fields__}),
        audio=AudioConfig(**{k: v for k, v in audio_data.items() if k in AudioConfig.__dataclass_fields__}),
        wake_word=WakeWordConfig(**{k: v for k, v in wake_word_data.items() if k in WakeWordConfig.__dataclass_fields__}),
        mqtt=MqttConfig(
            **{k: v for k, v in mqtt_data.items() if k in MqttConfig.__dataclass_fields__ and k != "topics"},
            topics=mqtt_topics,
        ),
        heartbeat=HeartbeatConfig(
            schedule=HeartbeatSchedule(**{k: v for k, v in schedule_data.items() if k in HeartbeatSchedule.__dataclass_fields__}),
            work_hours=WorkHours(**{k: v for k, v in work_hours_data.items() if k in WorkHours.__dataclass_fields__}),
        ),
        agent=AgentConfig(**{k: v for k, v in agent_data.items() if k in AgentConfig.__dataclass_fields__}),
        connectivity=ConnectivityConfig(**{k: v for k, v in connectivity_data.items() if k in ConnectivityConfig.__dataclass_fields__}),
    )


def load_config(config_path: str | Path) -> SottoConfig:
    """Load configuration from a YAML file with environment variable overrides.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        SottoConfig with all settings loaded.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    data = _apply_env_overrides(data)
    return _dict_to_config(data)
