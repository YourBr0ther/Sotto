"""Tests for the TTS MQTT service."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the TTS main module with a unique name to avoid collision
# with other services' main.py files
_service_dir = str(Path(__file__).parent.parent)
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

_spec = importlib.util.spec_from_file_location(
    "tts_main",
    str(Path(__file__).parent.parent / "main.py"),
)
tts_main = importlib.util.module_from_spec(_spec)
sys.modules["tts_main"] = tts_main
_spec.loader.exec_module(tts_main)

TTSService = tts_main.TTSService


class TestTTSServiceInit:
    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_init_defaults(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()
        assert svc._mqtt_host == "localhost"
        assert svc._mqtt_port == 1883

    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_init_custom(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService(
            mqtt_host="broker",
            mqtt_port=1884,
            piper_model="/models/test.onnx",
        )
        assert svc._mqtt_host == "broker"
        assert svc._mqtt_port == 1884


class TestTTSServiceOnConnect:
    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_subscribes_to_tts_text(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()
        svc._on_connect(None, None, None, 0)
        svc._client.subscribe.assert_called_once_with("sotto/audio/tts_text", qos=1)


class TestTTSServiceOnMessage:
    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_synthesizes_and_publishes(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()
        fake_audio = b"\x00\x01" * 500
        svc._engine.synthesize.return_value = fake_audio

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "agent-brain",
            "type": "tts_text",
            "payload": {"text": "Good morning. Here's your day.", "priority": 3},
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        svc._engine.synthesize.assert_called_once_with("Good morning. Here's your day.")
        svc._client.publish.assert_called_once()

        call_args = svc._client.publish.call_args
        assert call_args[0][0] == "sotto/audio/tts"

        published = json.loads(call_args[0][1])
        assert published["type"] == "tts_audio"
        assert published["source"] == "tts-service"
        assert published["payload"]["sample_rate"] == 22050
        assert published["payload"]["encoding"] == "pcm_s16le"
        assert published["payload"]["text"] == "Good morning. Here's your day."

        decoded_audio = base64.b64decode(published["payload"]["audio_b64"])
        assert decoded_audio == fake_audio

    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_empty_text_ignored(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "agent-brain",
            "payload": {"text": "", "priority": 5},
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        svc._engine.synthesize.assert_not_called()
        svc._client.publish.assert_not_called()

    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_whitespace_text_ignored(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "test",
            "payload": {"text": "   \n  "},
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        svc._engine.synthesize.assert_not_called()

    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_empty_audio_not_published(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()
        svc._engine.synthesize.return_value = b""

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "test",
            "payload": {"text": "Hello"},
        }).encode("utf-8")

        svc._on_message(None, None, msg)

        svc._engine.synthesize.assert_called_once()
        svc._client.publish.assert_not_called()

    @patch("tts_main.PiperEngine")
    @patch("tts_main.mqtt.Client")
    def test_synthesis_error_handled(self, mock_mqtt: MagicMock, mock_piper: MagicMock) -> None:
        svc = TTSService()
        svc._engine.synthesize.side_effect = RuntimeError("synthesis failed")

        msg = MagicMock()
        msg.payload = json.dumps({
            "source": "test",
            "payload": {"text": "Hello"},
        }).encode("utf-8")

        # Should not raise
        svc._on_message(None, None, msg)
        svc._client.publish.assert_not_called()
