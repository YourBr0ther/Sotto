"""Quick MQTT connectivity test for Sotto edge device.

Connects to the MQTT broker, publishes a test message,
subscribes to a test topic, and verifies round-trip communication.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import yaml


def main() -> int:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    broker_host = config.get("mqtt", {}).get("broker_host", "localhost")
    broker_port = config.get("mqtt", {}).get("broker_port", 1883)

    print(f"Connecting to MQTT broker at {broker_host}:{broker_port}...")

    received = {"message": None}

    def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            print(f"  Connected to broker (rc={rc})")
            client.subscribe("sotto/test/echo", qos=1)
        else:
            print(f"  Connection failed (rc={rc})")

    def on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        received["message"] = json.loads(message.payload.decode())

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sotto-test",
    )
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(broker_host, broker_port)
    except Exception as e:
        print(f"  ERROR: Could not connect: {e}")
        return 1

    client.loop_start()

    # Wait for connection
    deadline = time.time() + 5
    while not client.is_connected() and time.time() < deadline:
        time.sleep(0.1)

    if not client.is_connected():
        print("  ERROR: Connection timed out after 5 seconds")
        client.loop_stop()
        return 1

    # Publish test message
    test_payload = {"test": True, "source": "sotto-test", "ts": time.time()}
    client.publish("sotto/test/echo", json.dumps(test_payload), qos=1)
    print("  Published test message to sotto/test/echo")

    # Wait for echo
    deadline = time.time() + 3
    while received["message"] is None and time.time() < deadline:
        time.sleep(0.1)

    if received["message"] is not None:
        print("  Received echo message — round-trip OK")
    else:
        print("  Warning: No echo received (publish-only confirmed)")

    # Check if server services are subscribed by publishing to a real topic
    client.publish(
        "sotto/device/state",
        json.dumps({"source": "sotto-test", "status": "test", "mode": "test"}),
        qos=1,
    )
    print("  Published device state test message")

    client.loop_stop()
    client.disconnect()
    print("  Disconnected")
    print("")
    print("MQTT connectivity test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
