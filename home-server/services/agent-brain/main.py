"""Agent Brain - Core intelligence service for Sotto."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from classifier import ContentClassifier
from heartbeat import HeartbeatScheduler
from llm_client import OllamaClient
from task_extractor import TaskExtractor

logger = logging.getLogger(__name__)

# Add sibling service paths (for local dev; in Docker these are in /app/ already)
_services_dir = Path(__file__).parent.parent
for _subdir in ("operational-db", "vault-manager"):
    _path = str(_services_dir / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from db_client import DatabaseClient
from vault_client import VaultClient


class AgentBrain:
    """Core agent intelligence service.

    Processes transcriptions, extracts tasks, classifies content,
    manages the heartbeat schedule, and updates the Obsidian vault.
    """

    def __init__(
        self,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
        db_path: str = "/data/sotto.db",
        vault_path: str = "/data/vault",
    ) -> None:
        # MQTT
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="sotto-agent-brain",
        )

        # LLM
        self._llm = OllamaClient(base_url=ollama_url, model=ollama_model)
        self._classifier = ContentClassifier(self._llm)
        self._task_extractor = TaskExtractor(self._llm)

        # Storage
        self._db = DatabaseClient(db_path)
        self._vault = VaultClient(vault_path)

        # Heartbeat
        self._heartbeat = HeartbeatScheduler()

        self._running = False

    def start(self) -> None:
        """Start the agent brain service."""
        logger.info("Starting Agent Brain")

        # Initialize storage
        self._db.connect()
        self._vault.initialize()

        # Create today's daily note
        self._vault.create_daily_note()

        # Setup MQTT
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self._mqtt_host, self._mqtt_port)
        self._client.loop_start()

        self._running = True

        # Main loop for heartbeat checking
        while self._running:
            try:
                self._check_heartbeat()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error("Heartbeat check error: %s", e)
                time.sleep(60)

    def stop(self) -> None:
        """Stop the agent brain service."""
        self._running = False
        self._client.loop_stop()
        self._client.disconnect()
        self._db.close()
        logger.info("Agent Brain stopped")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        logger.info("Agent Brain connected to MQTT")
        self._client.subscribe("sotto/audio/transcription", qos=1)
        self._client.subscribe("sotto/device/state", qos=0)
        self._client.subscribe("sotto/agent/commands", qos=1)

    def _on_message(self, client: Any, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            data = json.loads(message.payload.decode("utf-8"))

            if message.topic == "sotto/audio/transcription":
                self._process_transcription(data)
            elif message.topic == "sotto/device/state":
                self._process_device_state(data)
            elif message.topic == "sotto/agent/commands":
                self._process_command(data)

        except Exception as e:
            logger.error("Error processing message on %s: %s", message.topic, e)

    def _process_transcription(self, data: dict[str, Any]) -> None:
        """Process a transcription from the STT service."""
        payload = data.get("payload", {})
        text = payload.get("text", "").strip()
        confidence = payload.get("confidence", 0)

        if not text:
            return

        logger.info("Processing transcription: %s", text[:100])

        # Classify content
        classification = self._classifier.classify(text)
        is_private = classification.classification == "PRIVATE"

        # Extract tasks
        extraction = self._task_extractor.extract(text)

        # Create tasks in DB and vault
        for task in extraction.tasks:
            task_id = self._db.create_task(
                description=task.description,
                source="conversation",
                context=task.source_quote,
                due_at=task.due_date,
                is_private=is_private,
            )

            # Create vault note
            self._vault.create_task_note(
                task_id=task_id,
                title=task.description,
                context=task.source_quote,
                source="conversation",
                due_date=task.due_date,
                people=task.people,
                is_private=is_private,
            )

            # Create people notes
            for person in task.people:
                self._vault.create_person_note(person)

            logger.info("Task created: %s (private=%s)", task.description[:50], is_private)

        # Update daily note with time block
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_range = f"{now.strftime('%H:%M')}"

        summary = text[:200] if len(text) > 200 else text
        task_mentions = ""
        if extraction.tasks:
            task_mentions = "\n".join(f"- Task: {t.description}" for t in extraction.tasks)

        block_content = f"- {summary}"
        if task_mentions:
            block_content += f"\n{task_mentions}"

        if not is_private:
            self._vault.append_time_block(date_str, time_range, block_content)

        # Log processing
        self._db.log_processing(
            audio_quality=None,
            transcription_confidence=confidence,
            action_taken="task_created" if extraction.tasks else "note_updated",
            notes=f"Classification: {classification.classification}, Tasks: {len(extraction.tasks)}",
        )

        # Update daily metrics
        self._db.update_daily_metrics(
            date=date_str,
            tasks_created=len(extraction.tasks),
        )

    def _process_device_state(self, data: dict[str, Any]) -> None:
        """Process device state update."""
        payload = data.get("payload", data)
        source = data.get("source", "unknown")

        self._db.update_device_state(
            device_id=source,
            mode=payload.get("mode", "active").lower().replace("fully_active", "active"),
            headphones_connected=payload.get("headphones_connected", False),
        )

    def _process_command(self, data: dict[str, Any]) -> None:
        """Process a command from the edge device."""
        payload = data.get("payload", {})
        command = payload.get("command", "")

        if command == "wake_word_activated":
            logger.info("Wake word activated - ready for query")
            # The next transcription will be treated as a direct query
        elif command == "complete_task":
            task_id = payload.get("task_id", "")
            if task_id:
                self._db.complete_task(task_id)
                logger.info("Task completed via command: %s", task_id)

    def _check_heartbeat(self) -> None:
        """Check if a heartbeat should fire."""
        now = datetime.now(timezone.utc)
        heartbeat_type = self._heartbeat.get_heartbeat_type(now)

        if heartbeat_type is None:
            return

        logger.info("Heartbeat firing: %s", heartbeat_type)

        if heartbeat_type == "morning_briefing":
            self._fire_morning_briefing()
        elif heartbeat_type == "evening_summary":
            self._fire_evening_summary()
        elif heartbeat_type == "work_interval":
            self._fire_work_heartbeat()
            self._heartbeat.mark_work_heartbeat_fired()

    def _fire_morning_briefing(self) -> None:
        """Generate and send morning briefing."""
        pending = self._db.get_pending_tasks()
        task_names = [t["description"][:50] for t in pending[:5]]

        text = self._heartbeat.build_morning_briefing(
            calendar_events=[],  # TODO: integrate calendar
            pending_tasks=task_names,
            overnight_alerts=[],  # TODO: integrate alerts
        )

        self._send_tts(text, priority=3)

        # Update daily note
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._vault.update_morning_briefing(
            date_str,
            calendar="No calendar integration yet",
            tasks=", ".join(task_names) if task_names else "None",
        )

    def _fire_evening_summary(self) -> None:
        """Generate and send evening summary."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        metrics = self._db.get_daily_metrics(date_str)
        pending = self._db.get_pending_tasks()

        text = self._heartbeat.build_evening_summary(
            tasks_completed=metrics["tasks_completed"] if metrics else 0,
            tasks_created=metrics["tasks_created"] if metrics else 0,
            incomplete_tasks=[t["description"][:40] for t in pending[:3]],
            tomorrow_events=[],  # TODO: integrate calendar
        )

        self._send_tts(text, priority=3)

    def _fire_work_heartbeat(self) -> None:
        """Generate and send a work-hours heartbeat."""
        reminders = self._db.get_tasks_needing_reminder()
        task_names = [t["description"][:40] for t in reminders[:3]]

        text = self._heartbeat.build_work_heartbeat(
            new_tasks=task_names,
            upcoming_events=[],  # TODO: integrate calendar
            alerts=[],  # TODO: integrate alerts
        )

        if text:
            self._send_tts(text, priority=5)

    def _send_tts(self, text: str, priority: int = 5) -> None:
        """Send text to the TTS service for synthesis."""
        self._client.publish(
            "sotto/audio/tts_text",
            json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "agent-brain",
                "type": "tts_text",
                "payload": {
                    "text": text,
                    "priority": priority,
                },
            }),
            qos=1,
        )

        # Also send as heartbeat notification
        self._client.publish(
            "sotto/agent/heartbeat",
            json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "agent-brain",
                "type": "heartbeat",
                "payload": {
                    "text": text,
                    "priority": priority,
                },
            }),
            qos=1,
        )

        # Update metrics
        self._db.update_daily_metrics(heartbeats_delivered=1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    brain = AgentBrain(
        mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
        ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
        db_path=os.environ.get("DB_PATH", "/data/sotto.db"),
        vault_path=os.environ.get("VAULT_PATH", "/data/vault"),
    )

    def signal_handler(sig: int, frame: Any) -> None:
        brain.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    brain.start()


if __name__ == "__main__":
    main()
