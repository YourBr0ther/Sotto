# Project Aegis — Ambient AI Personal Assistant

## Design Specification v1.0

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Philosophy](#2-architecture-philosophy)
3. [System Architecture](#3-system-architecture)
4. [Phase 1: Android App Prototype](#4-phase-1-android-app-prototype)
5. [Phase 2: Raspberry Pi 5 Belt Device](#5-phase-2-raspberry-pi-5-belt-device)
6. [Phase 3: Smart Glasses + Undershirt](#6-phase-3-smart-glasses--undershirt)
7. [Phase 4: IO Controller](#7-phase-4-io-controller)
8. [Home Server Stack](#8-home-server-stack)
9. [MQTT Communication Layer](#9-mqtt-communication-layer)
10. [Obsidian Knowledge Vault](#10-obsidian-knowledge-vault)
11. [Privacy Architecture](#11-privacy-architecture)
12. [Agent Behavior Model](#12-agent-behavior-model)
13. [Software Module Design](#13-software-module-design)
14. [Daily Workflow Reference](#14-daily-workflow-reference)
15. [Hardware BOM (Prototype)](#15-hardware-bom-prototype)
16. [Open Source Considerations](#16-open-source-considerations)

---

## 1. Project Overview

### Vision

An always-on, ambient AI personal assistant that acts as a second memory and proactive life manager. The system continuously captures audio context, processes it into actionable knowledge, and communicates with the user through scheduled heartbeat intervals, wake word activation, and standard notifications (calendar, email, text).

### Core Metaphor: The Peristaltic Pump

The system interfaces with the user's digital and physical world without ever directly touching sensitive credentials, authentication tokens, or private systems. Like a peristaltic pump that moves fluid by deforming the tube around it — never contacting the fluid itself — this system actuates through proxy layers, broker patterns, and hardware passthrough. The AI reasons and decides; separate, sandboxed services execute.

### Design Principles

- **Intelligence at the center, simplicity at the edge**: All heavy reasoning happens on the home server. Edge devices (phone, belt device, glasses) are sensors, relays, and output devices only.
- **Privacy by architecture, not by policy**: Sensitive data stays on user-owned hardware. Private content is compartmentalized by design, not by promise. Physical disconnects are preferred over software toggles.
- **Graceful degradation**: Every component can fail or disconnect without breaking the system. No connectivity? Buffer locally. Headphones off? Queue output. Server down? Store and forward.
- **No subscriptions, no cloud dependency, no IT approval**: The system runs on user-owned hardware, communicates over user-controlled networks, and never requires third-party accounts for core functionality. Cloud APIs are optional enhancements.
- **Quiet yet carries a big stick**: The agent is restrained by default. It speaks only when spoken to, on scheduled intervals, or for notifications the user has opted into. But when engaged, it has deep context and broad capability.

---

## 2. Architecture Philosophy

### The Peristaltic Pump Pattern — Applied

Every integration follows this pattern:

```
[AI Brain] → [Broker/Proxy Layer] → [Target System]
                    ↑
         Credentials live HERE only.
         AI never sees them.
```

**Home Assistant**: AI sends intent via MCP → MCP server holds HA token → HA executes action.

**k3s/Docker Monitoring**: AI queries via MCP → MCP server holds kubeconfig → Returns sanitized cluster health data.

**Discord**: AI sends message via MCP → MCP server holds bot token → Bot posts to channel.

**Email/Calendar**: Home server pulls via IMAP/CalDAV with stored credentials → Presents data to AI as structured context.

**IO Controller (Phase 4)**: AI sends keystrokes/mouse events → IO controller injects as USB HID → Target computer has no idea an AI is involved. No software installation, no authentication, no credentials.

### Distributed Body-Area System

Unlike single-device wearables that compromise on battery, compute, or comfort, this system distributes responsibilities across purpose-built components:

| Component | Responsibility | Intelligence |
|-----------|---------------|-------------|
| Smart Glasses | Sensing (mic, camera), Output (bone conduction, LED) | None — completely passive |
| Undershirt | Signal/power routing | None — a wiring harness |
| Belt Device (Pi 5) | Wake word, noise filtering, TTS, buffering, relay | Edge compute only |
| Home Server | Transcription, LLM reasoning, integrations, storage | Full intelligence |
| IO Controller | Screen capture, HID injection, BLE proximity | Peripheral awareness |

---

## 3. System Architecture

### High-Level Data Flow

```
                        ┌─────────────────────────────────────────┐
                        │            HOME SERVER (Brain)           │
                        │                                         │
                        │  ┌─────────┐  ┌─────────┐  ┌────────┐  │
                        │  │ Whisper  │  │  Local   │  │  MCP   │  │
                        │  │  (STT)   │  │   LLM    │  │Servers │  │
                        │  └────┬─────┘  └────┬─────┘  └───┬────┘  │
                        │       │             │            │       │
                        │  ┌────┴─────────────┴────────────┴────┐  │
                        │  │         Processing Pipeline         │  │
                        │  └────┬─────────────┬────────────┬────┘  │
                        │       │             │            │       │
                        │  ┌────┴────┐  ┌─────┴─────┐ ┌───┴────┐  │
                        │  │Obsidian │  │  SQLite    │ │ Piper  │  │
                        │  │ Vault   │  │ (OpState)  │ │ (TTS)  │  │
                        │  └─────────┘  └───────────┘ └────────┘  │
                        │                                         │
                        │  ┌─────────────────────────────────────┐ │
                        │  │          MQTT Broker (Mosquitto)     │ │
                        │  └──────────────┬──────────────────────┘ │
                        └─────────────────┼───────────────────────┘
                                          │ (Tailscale VPN)
                    ┌─────────────────────┼──────────────────────┐
                    │                     │                      │
           ┌────────┴────────┐  ┌─────────┴─────────┐  ┌────────┴────────┐
           │  BELT DEVICE    │  │   IO CONTROLLER    │  │  INTEGRATIONS   │
           │  (Pi 5)         │  │   (Desk Unit)      │  │                 │
           │                 │  │                     │  │  Home Assistant │
           │  Wake Word      │  │  HDMI Capture       │  │  k3s/Docker    │
           │  Noise Filter   │  │  USB HID Inject     │  │  Discord       │
           │  TTS Playback   │  │  BLE Proximity      │  │  Email/IMAP    │
           │  Audio Buffer   │  │                     │  │  Calendar      │
           │  MQTT Client    │  │  MQTT Client        │  │                │
           └────────┬────────┘  └─────────────────────┘  └────────────────┘
                    │
         ┌──────────┴──────────┐
         │   SMART GLASSES     │
         │                     │
         │   MEMS Mic          │
         │   Bone Conduction   │
         │   Status LED        │
         │   Magnetic Pogo     │
         └─────────────────────┘
         (Connected via undershirt
          wiring to belt device)
```

### Network Topology

```
[Home LAN]
  ├── Home Server (static IP or hostname)
  │     ├── Mosquitto MQTT Broker
  │     ├── Whisper / faster-whisper
  │     ├── Local LLM (Ollama / vLLM / llama.cpp)
  │     ├── Piper TTS
  │     ├── MCP Server(s)
  │     ├── Obsidian Vault (filesystem)
  │     └── SQLite operational database
  │
  ├── IO Controller (when at desk)
  │     └── BLE + WiFi
  │
  └── Tailscale mesh VPN
        └── Belt Device / Phone (anywhere)
              └── Connects to MQTT broker via Tailscale IP
```

---

## 4. Phase 1: Android App Prototype

### Purpose

Validate the entire interaction model — heartbeat notifications, wake word, task extraction, daily summaries, and privacy compartmentalization — before building any custom hardware. The phone acts as a stand-in for the belt device + glasses combo.

### What Phase 1 Validates

- Is the heartbeat interaction cadence useful or annoying?
- Does the home server pipeline (Whisper → LLM → Obsidian) work end-to-end?
- Are task extractions from natural conversation accurate enough?
- Is the notification queue (calendar, email, text) valuable?
- What kinds of information are worth pushing vs. noise?
- Does the privacy compartmentalization (public vs. private) work in practice?

### What Phase 1 Cannot Validate

- Always-on recording battery life (phone will drain)
- Bone conduction private audio experience
- Hands-free, invisible form factor
- IO controller desk integration
- The physical experience of wearing the system

### Technical Stack

**Device**: Android phone running Termux (or a lightweight native app)

**Language**: Python (runs in Termux, portable to Pi 5 later)

**Audio**: Bluetooth bone conduction headphones (e.g., Shokz OpenRun) for output. Phone mic for input.

**Connectivity**: WiFi when home, cellular when out. Tailscale VPN to reach home server MQTT broker from anywhere.

### App Architecture

```
phone_app/
├── main.py                  # Entry point, state machine, lifecycle
├── config.yaml              # Device-specific settings
├── audio/
│   ├── __init__.py
│   ├── input.py             # AudioInput abstraction (mic capture)
│   ├── output.py            # AudioOutput abstraction (TTS playback)
│   ├── noise_filter.py      # Basic noise reduction
│   └── wake_word.py         # OpenWakeWord listener
├── comms/
│   ├── __init__.py
│   ├── mqtt_client.py       # MQTT connection, publish/subscribe
│   └── audio_streamer.py    # Chunked audio streaming to server
├── state/
│   ├── __init__.py
│   ├── device_state.py      # Agent operating mode state machine
│   └── headphone_monitor.py # Bluetooth headphone connection detection
└── utils/
    ├── __init__.py
    ├── logger.py             # Structured logging
    └── config_loader.py      # YAML config parser
```

### Audio Abstraction Layer

This is critical for Phase 1 → Phase 2 transition. All audio I/O goes through abstract interfaces that can be swapped without touching core logic.

```python
# audio/input.py
from abc import ABC, abstractmethod

class AudioInput(ABC):
    """Abstract audio input — swap implementations for different hardware."""

    @abstractmethod
    def start_capture(self) -> None:
        """Begin continuous audio capture."""
        pass

    @abstractmethod
    def read_chunk(self, duration_ms: int = 500) -> bytes:
        """Read a chunk of audio data."""
        pass

    @abstractmethod
    def stop_capture(self) -> None:
        """Stop audio capture."""
        pass

    @abstractmethod
    def get_sample_rate(self) -> int:
        """Return the sample rate of the audio stream."""
        pass


class PhoneMicInput(AudioInput):
    """Phone microphone implementation using sounddevice/PyAudio."""

    def __init__(self, device_index: int = None, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.device_index = device_index
        # ... setup

    def start_capture(self) -> None:
        # Start PyAudio/sounddevice stream
        pass

    def read_chunk(self, duration_ms: int = 500) -> bytes:
        # Read from stream buffer
        pass

    def stop_capture(self) -> None:
        # Stop stream
        pass

    def get_sample_rate(self) -> int:
        return self.sample_rate


# Future: Pi5MicInput, GlassesMicInput — same interface, different hardware
```

```python
# audio/output.py
from abc import ABC, abstractmethod

class AudioOutput(ABC):
    """Abstract audio output — swap implementations for different hardware."""

    @abstractmethod
    def play_audio(self, audio_data: bytes, sample_rate: int) -> None:
        """Play audio through the output device."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if output device is connected and available."""
        pass


class BluetoothHeadphoneOutput(AudioOutput):
    """Bluetooth headphone output (bone conduction or standard)."""

    def play_audio(self, audio_data: bytes, sample_rate: int) -> None:
        # Play via default audio output (routed to BT headphones by OS)
        pass

    def is_available(self) -> bool:
        # Check if BT headphones are paired and connected
        pass


# Future: BoneConductionWiredOutput — same interface, driven through
#         shirt cable to glasses transducers
```

### Agent State Machine

The agent operates in distinct modes based on hardware state and user commands.

```python
# state/device_state.py
from enum import Enum, auto

class AgentMode(Enum):
    FULLY_ACTIVE = auto()     # Headphones on, listening, can speak
    INPUT_ONLY = auto()       # Headphones off, listening, queuing output
    QUIET = auto()            # Manual trigger, discarding audio, no processing
    SLEEP_MONITOR = auto()    # Minimal processing, ambient health only (snoring)


class DeviceState:
    """
    Manages the agent's operating mode.

    Transitions:
      FULLY_ACTIVE → INPUT_ONLY:    Headphones disconnect
      INPUT_ONLY → FULLY_ACTIVE:    Headphones reconnect (deliver queued items)
      ANY → QUIET:                  Voice command "agent, go quiet"
      QUIET → FULLY_ACTIVE:         Voice command "agent, wake up" or headphone reconnect
      ANY → SLEEP_MONITOR:          Scheduled time or voice command "agent, goodnight"
      SLEEP_MONITOR → FULLY_ACTIVE: Morning alarm time or voice command "agent, good morning"
    """

    def __init__(self):
        self.mode = AgentMode.FULLY_ACTIVE
        self.output_queue = []  # Queued messages for when output becomes available
        self.headphones_connected = False

    def on_headphones_connected(self):
        self.headphones_connected = True
        if self.mode == AgentMode.INPUT_ONLY:
            self.mode = AgentMode.FULLY_ACTIVE
            return self._flush_queue()
        return []

    def on_headphones_disconnected(self):
        self.headphones_connected = False
        if self.mode == AgentMode.FULLY_ACTIVE:
            self.mode = AgentMode.INPUT_ONLY

    def queue_output(self, message: dict):
        """Queue a message for later delivery if output isn't available."""
        if self.mode in (AgentMode.INPUT_ONLY, AgentMode.SLEEP_MONITOR):
            self.output_queue.append(message)
        return message

    def _flush_queue(self) -> list:
        """Return and clear all queued messages."""
        messages = self.output_queue.copy()
        self.output_queue.clear()
        return messages

    def should_process_audio(self) -> bool:
        """Whether the agent should process incoming audio."""
        return self.mode in (AgentMode.FULLY_ACTIVE, AgentMode.INPUT_ONLY)

    def should_play_output(self) -> bool:
        """Whether the agent can play audio to the user."""
        return self.mode == AgentMode.FULLY_ACTIVE and self.headphones_connected

    def can_do_ambient_monitoring(self) -> bool:
        """Whether to run lightweight ambient analysis (snoring, etc.)."""
        return self.mode == AgentMode.SLEEP_MONITOR
```

### Config File

```yaml
# config.yaml — Phase 1 Android prototype

device:
  name: "phone-prototype"
  type: "android"

audio:
  input_device: null          # null = system default (phone mic)
  output_device: null          # null = system default (BT headphones)
  sample_rate: 16000
  chunk_duration_ms: 500
  noise_filter_enabled: true

wake_word:
  engine: "openwakeword"
  model: "hey_jarvis"          # or custom wake word model
  threshold: 0.7
  acknowledgment_sound: true   # play a short tone on detection

mqtt:
  broker_host: "100.x.x.x"    # Tailscale IP of home server
  broker_port: 1883
  client_id: "aegis-phone"
  topics:
    audio_stream: "aegis/audio/raw"
    transcription: "aegis/audio/transcription"
    commands: "aegis/agent/commands"
    heartbeat: "aegis/agent/heartbeat"
    notifications: "aegis/agent/notifications"
    tts_audio: "aegis/audio/tts"
    device_state: "aegis/device/state"
    io_controller: "aegis/io/status"

heartbeat:
  schedule:
    morning_briefing: "07:00"
    work_intervals_minutes: 30
    evening_summary: "18:00"
  work_hours:
    start: "08:00"
    end: "17:00"

agent:
  quiet_command: "agent go quiet"
  wake_command: "agent wake up"
  goodnight_command: "agent goodnight"
  morning_command: "agent good morning"

connectivity:
  retry_interval_seconds: 10
  offline_buffer_max_mb: 500
  sync_on_reconnect: true
```

### Phase 1 → Phase 2 Transition

When moving from Android to Raspberry Pi 5:

1. Copy the project directory to the Pi 5
2. Update `config.yaml`:
   - Change `device.type` to `"pi5"`
   - Change `audio.input_device` to the USB mic device ID
   - Change `audio.output_device` to the USB DAC or audio HAT device ID
3. Install the same Python dependencies
4. Run `main.py`

The MQTT broker doesn't change. The home server doesn't change. The Obsidian vault doesn't change. The audio abstraction layer handles the hardware difference. Everything else is identical.

---

## 5. Phase 2: Raspberry Pi 5 Belt Device

### Purpose

Move from phone prototype to dedicated always-on hardware. Eliminates battery drain issues, enables continuous recording, and proves the wearable form factor.

### Hardware

| Component | Specification | Purpose |
|-----------|--------------|---------|
| Compute | Raspberry Pi 5 (4GB or 8GB) | Wake word, noise filtering, TTS, MQTT relay |
| Battery | USB-C power bank, 10000-20000mAh | All-day power, hot-swappable |
| Mic | USB MEMS lavalier mic (clip-on) | Audio capture (interim before glasses) |
| Audio Out | 3.5mm or USB to bone conduction headphones | TTS playback |
| Enclosure | Belt-clip case, ventilated | Protection, passive cooling |
| Storage | MicroSD 32GB+ or USB SSD | OS, rolling audio buffer |

### Hot-Swap Battery Design

Two battery packs with a switchover circuit. The Pi 5 draws from both through a diode OR or active switchover. Remove one, the other keeps the system alive. Slot in a fresh one. No reboot, no interruption.

For prototype: simply use a USB-C power bank. When it gets low, plug in a second one and remove the first. The Pi 5 handles brief power transitions on USB-C gracefully.

### Software Additions (Beyond Phase 1)

- **Local TTS via Piper**: Pre-generate common responses, stream longer ones
- **Enhanced noise filtering**: RNNoise or similar running on-device
- **Offline Whisper fallback**: When home server is unreachable, run `whisper.cpp` locally on the Pi 5 for basic transcription. Queue full processing for when connectivity returns.
- **Audio quality scoring**: Rate each captured chunk and log quality metrics. Inform the user via heartbeat if placement is consistently poor.

### Thermal Considerations

The Pi 5 running audio processing (not visual) will generate moderate heat. Passive cooling is sufficient.

- Use an aluminum heatsink case (e.g., Pimoroni or Argon passive cases)
- Ensure the belt pouch has ventilation slots
- Monitor CPU temp and throttle TTS quality if needed (fallback to lower sample rate)
- The SoC is doing audio-only work — expect 2-4W power draw, manageable heat

---

## 6. Phase 3: Smart Glasses + Undershirt

### Smart Glasses

#### Components

| Component | Specification | Purpose |
|-----------|--------------|---------|
| Frames | Standard eyeglass frames with modified temple arms | Housing for electronics |
| Mic | MEMS microphone (e.g., Knowles SPH0645) | Audio capture, near-mouth placement |
| Bone Conduction | 2x transducers (e.g., Sonion or Knowles) | Private audio output |
| LED | Small soft-glow LED near mic | Recording indicator, always on when active |
| Connector | 5-6 pin magnetic pogo connector, behind ear | Power + data to/from shirt cable |

#### Magnetic Pogo Pin Assignment

| Pin | Function | Notes |
|-----|----------|-------|
| 1 | GND | Outer position (safety) |
| 2 | VCC (3.3V or 5V) | Power from belt battery |
| 3 | MIC_SIGNAL | Analog mic audio, down to belt |
| 4 | BONE_LEFT | Audio signal, up to left transducer |
| 5 | BONE_RIGHT | Audio signal, up to right transducer |
| 6 | GND | Outer position (safety) |

Ground pins on outer edges so partial misalignment doesn't short signal to power.

#### Design Notes

- Glasses contain NO battery, NO compute, NO radio
- All power and signals come through the shirt cable via magnetic connector
- Frames can be swapped independently — any frames with the same connector work
- LED should be a soft, slow-breathing white or amber. Steady when active. Off when in QUIET mode.
- Target weight addition over standard frames: < 15 grams
- Bone conduction requires firm temple arm contact with temporal bone for good audio. Frames need adequate spring tension. Multiple size options or adjustable temple tips recommended.

### Undershirt Wiring Harness

#### Design

A thin compression-fit tank top with an integrated cable channel running from a waist connector to a collar connector.

#### Cable Routing Path

```
[Belt Device] →→ [Waist Connector (magnetic)]
                        │
                        │  (cable runs inside sewn channel
                        │   along left side seam, midaxillary line)
                        │
                        ↓
               [Collar area, behind left ear]
                        │
                        ↓
              [Glasses Connector (magnetic pogo)]
```

The route follows the side of the torso where skin movement is minimal. Avoids joints, front of body, and areas where clothing bunches.

#### Cable Specification

- Flat flex cable or thin silicone-encapsulated multi-conductor wire
- 6 conductors matching the pogo pin assignment
- Encapsulated in medical-grade silicone for skin safety and electrical insulation
- Cannot short out — no exposed conductors anywhere
- Strain relief at both connector junctions

#### Washability

Two options:

1. **Removable cable**: Snap-in cable that pops out of the channel before washing. Shirt is a standard tank top when cable is removed.
2. **Integrated washable cable**: Fully encapsulated silicone wire that survives gentle wash cycles. Proven in heated clothing and medical garments.

Option 1 recommended for prototype. Simpler, lower risk.

#### Connectors

- **Waist**: Magnetic connector, similar to glasses pogo pin but possibly larger. Mates with a matching connector on the belt device enclosure.
- **Collar**: Terminates near behind the left ear. The glasses' magnetic pogo connector attaches here. Short visible cable segment from collar to behind ear — can be skin-colored or hidden under collar.

---

## 7. Phase 4: IO Controller

### Purpose

Give the AI eyes and hands on the user's digital workspace without installing software, authenticating, or requiring IT approval. The purest expression of the peristaltic pump principle.

### How It Works

The IO controller sits inline between the user's computer and their peripherals. From the computer's perspective, it IS the monitor and keyboard. It's a hardware man-in-the-middle.

```
[Computer] ──HDMI──→ [IO Controller] ──HDMI──→ [Monitor(s)]
[Computer] ←──USB──→ [IO Controller] ←──USB──→ [Keyboard/Mouse]
```

The IO controller:
- **Sees** everything on screen via HDMI capture/passthrough
- **Sees** all keyboard and mouse input via USB passthrough
- **Can inject** keystrokes and mouse events as a USB HID device
- **Never installs** anything on the host computer
- **Never authenticates** with anything
- The host computer has no idea an AI is involved

### Hardware

| Component | Specification | Purpose |
|-----------|--------------|---------|
| Compute | Pi 5 or similar SoC with USB3 | Processing, BLE, WiFi |
| HDMI Capture | HDMI input per monitor (passthrough + capture) | Screen observation |
| HDMI Output | HDMI output per monitor (passthrough) | Clean video to displays |
| USB Hub | USB passthrough for keyboard + mouse | Input observation |
| USB HID | USB HID gadget mode | Keystroke/mouse injection |
| BLE | Built-in on Pi 5 | Proximity detection for belt device |
| WiFi | Built-in on Pi 5 | MQTT communication with home server |
| Enclosure | Small puck or box, desk-mountable | Sits behind monitors |

### Multi-Monitor Support

The IO controller supports passthrough for multiple monitors. Each monitor gets an HDMI-in and HDMI-out pair. The controller captures frames from each display.

### Attention Allocation

The IO controller does NOT process every frame from every monitor. It uses intelligent attention:

1. **Cursor tracking**: Whichever screen has the mouse cursor gets primary attention (cursor position known from USB passthrough)
2. **Change detection**: Lightweight pixel-diff on each display. Only run heavier OCR/vision on screens with active changes.
3. **Periodic snapshots**: Every few seconds on active screens. Much less on static screens.
4. **Keyboard context**: Correlate typed text with active window for richer context.

Screen capture data is sent to the home server for vision processing. The IO controller itself does minimal vision work.

### BLE Proximity Auto-Connect

```
Belt device advertises BLE beacon
IO controller scans for belt device

RSSI > threshold for 30 seconds → CONNECT → switch to desk mode
RSSI < threshold for 60 seconds → DISCONNECT → switch to mobile mode

Hysteresis prevents rapid toggling when walking past desk.
```

When connected, the home server AI gains:
- Screen context (what the user is looking at)
- Keyboard/mouse context (what the user is typing)
- The ability to inject keystrokes and mouse actions

When disconnected, these capabilities disappear. The AI continues with audio-only context from the belt device.

### MQTT Topics for IO Controller

```
aegis/io/status          # online/offline, connected monitors
aegis/io/screen/capture  # screen snapshot data (sent to server)
aegis/io/keyboard/events # keyboard activity metadata (not raw keystrokes for security)
aegis/io/hid/inject      # commands FROM server TO inject keystrokes/mouse
```

---

## 8. Home Server Stack

### Overview

The home server is the brain of the entire system. It runs all intelligence, all integrations, all storage. Every other component is a sensor or actuator that feeds into or receives commands from the home server.

### Required Services

| Service | Purpose | Implementation |
|---------|---------|---------------|
| MQTT Broker | Communication backbone | Mosquitto |
| Speech-to-Text | Audio transcription | faster-whisper or whisper.cpp |
| Local LLM | Reasoning, task extraction, summarization | Ollama, vLLM, or llama.cpp |
| Text-to-Speech | Generate audio responses | Piper TTS |
| MCP Runtime | Tool/integration broker | MCP server framework |
| Obsidian Vault | Knowledge storage | Filesystem (markdown) |
| SQLite | Operational state | Single file database |
| Tailscale | VPN mesh for remote access | Tailscale daemon |

### MCP Servers

Each integration gets its own MCP server. The AI interacts with tools through MCP. Credentials live in the MCP server config, never exposed to the LLM.

| MCP Server | Integrates With | Capabilities |
|------------|----------------|-------------|
| home-assistant | Home Assistant API | Device control, sensor reading, automation triggers |
| k8s-monitor | k3s clusters via kubeconfig | Pod health, node status, deployment state, alerts |
| docker-monitor | Docker API | Container health, logs, restart |
| discord | Discord Bot API | Send/read messages, channel management |
| email | IMAP server | Read inbox, search, flag |
| calendar | CalDAV / Google Calendar API | Read events, create events, check availability |
| obsidian | Local filesystem | Read/write/search Obsidian vault notes |

### Processing Pipeline

```
1. Audio arrives via MQTT from belt device
         │
2. faster-whisper transcribes audio to text
         │
3. LLM processes transcript with context:
   ├── Current agent mode
   ├── Recent conversation history
   ├── Pending tasks from SQLite
   ├── Today's calendar events
   └── Current Obsidian daily note
         │
4. LLM decides what to do:
   ├── Extract tasks → Create task in Obsidian + SQLite
   ├── Classify content → Route to public or private vault section
   ├── Answer query → Generate response → Piper TTS → MQTT to belt
   ├── Trigger integration → MCP call → Result → Maybe notify user
   ├── Update daily note → Write to Obsidian
   └── Nothing → Discard, continue listening
         │
5. Heartbeat scheduler checks pending items on interval:
   ├── Pending task reminders
   ├── Calendar events approaching
   ├── New emails/texts
   ├── Infrastructure alerts
   └── Custom scheduled briefings
         │
6. Notifications delivered via MQTT → Belt device → TTS → Headphones
```

### Heartbeat Scheduler

The heartbeat system delivers information at user-defined intervals. It is the primary proactive communication channel.

```python
# Heartbeat schedule definition
heartbeat_schedule = {
    "morning_briefing": {
        "time": "07:00",
        "includes": [
            "today_calendar_summary",
            "pending_tasks_reminder",
            "overnight_alerts",
            "weather"
        ]
    },
    "work_intervals": {
        "every_minutes": 30,
        "active_hours": ("08:00", "17:00"),
        "includes": [
            "new_task_reminders",
            "upcoming_calendar_events",
            "infrastructure_alerts",
            "unread_important_emails"
        ]
    },
    "evening_summary": {
        "time": "18:00",
        "includes": [
            "daily_summary",
            "incomplete_tasks",
            "tomorrow_preview"
        ]
    }
}
```

Heartbeat delivery rules:
- **Only fires when headphones are connected** (agent mode is FULLY_ACTIVE)
- **Queues if headphones are off** and delivers on reconnection
- **Never includes private-classified content**
- **Keeps each heartbeat under 60 seconds of spoken audio** — brevity is critical
- **Prioritizes by urgency**: infrastructure alerts > calendar in 15 min > task reminders > general info

---

## 9. MQTT Communication Layer

### Broker

Mosquitto running on the home server. Accessible via Tailscale IP from anywhere.

### Topic Hierarchy

```
aegis/
├── audio/
│   ├── raw                # Raw audio chunks from belt device → server
│   ├── transcription      # Transcribed text from server → belt device (for logging)
│   └── tts                # TTS audio from server → belt device for playback
│
├── agent/
│   ├── commands           # Commands from belt to server (wake word triggered queries)
│   ├── heartbeat          # Heartbeat notifications from server → belt device
│   ├── notifications      # Push notifications (calendar, email, text) → belt device
│   ├── mode               # Agent mode changes (quiet, sleep, active)
│   └── tasks              # Task state changes
│
├── device/
│   ├── state              # Belt device state (battery, connectivity, audio quality)
│   ├── headphones         # Headphone connection status
│   └── health             # Device health metrics
│
├── io/
│   ├── status             # IO controller online/offline
│   ├── screen/capture     # Screen snapshots → server
│   ├── keyboard/events    # Keyboard activity metadata → server
│   └── hid/inject         # HID injection commands server → IO controller
│
└── integrations/
    ├── home-assistant     # HA events and commands
    ├── k8s/alerts         # Kubernetes cluster alerts
    ├── docker/alerts      # Docker container alerts
    ├── email/new          # New email notifications
    ├── calendar/upcoming  # Upcoming calendar events
    └── discord/messages   # Discord message notifications
```

### Message Format

All MQTT messages use JSON payloads:

```json
{
  "timestamp": "2026-02-19T14:30:00Z",
  "source": "belt-device",
  "type": "audio_chunk",
  "payload": {
    "audio_b64": "...",
    "sample_rate": 16000,
    "duration_ms": 500,
    "quality_score": 0.85
  }
}
```

### QoS Levels

| Topic Pattern | QoS | Rationale |
|---------------|-----|-----------|
| aegis/audio/raw | 0 | Best effort, losing a chunk is acceptable |
| aegis/agent/heartbeat | 1 | At least once, don't lose notifications |
| aegis/agent/commands | 1 | At least once, user queries must arrive |
| aegis/io/hid/inject | 2 | Exactly once, don't double-inject keystrokes |
| aegis/device/state | 0 | Best effort, frequent updates |

### Offline Behavior

When the belt device loses MQTT connectivity:

1. Wake word still works locally (acknowledgment tone plays)
2. Audio chunks are buffered to local storage (up to configurable max, default 500MB)
3. User is informed via TTS: "I've lost connection to the server. I'm buffering locally and will sync when connection returns."
4. On reconnection, buffered audio is streamed to server for processing
5. Any queued heartbeats/notifications from the server are delivered

---

## 10. Obsidian Knowledge Vault

### Overview

The Obsidian vault is the agent's long-term memory. It is a folder of markdown files on the home server filesystem. The LLM has full read/write access through the MCP obsidian server. Obsidian (the app) is used by the human to browse, search, and review the knowledge visually. The agent doesn't need Obsidian running — it works directly with the files.

### Vault Structure

```
aegis-vault/
│
├── daily/
│   ├── 2026-02-19.md              # Daily note with time-block summaries
│   ├── 2026-02-20.md
│   └── ...
│
├── tasks/
│   ├── haircut-daughter-2026-02.md
│   ├── school-event-date.md
│   └── ...
│
├── people/
│   ├── wife.md
│   ├── daughter.md
│   ├── daughter-teacher.md
│   ├── coworker-jane.md
│   └── ...
│
├── projects/
│   ├── beach-trip.md
│   ├── ai-wearable/
│   │   ├── overview.md
│   │   ├── hardware-notes.md
│   │   └── software-notes.md
│   └── ...
│
├── health/
│   ├── sleep/
│   │   ├── 2026-02-19.md          # Snoring data, sleep quality
│   │   └── ...
│   ├── nutrition/
│   │   ├── 2026-02-19.md          # Meals logged
│   │   └── ...
│   └── ...
│
├── private/                        # PASSWORD PROTECTED
│   ├── notes/
│   │   └── ...                     # Private interest notes
│   └── suggestions/
│       └── ...                     # Agent's private recommendations
│
├── agent/
│   ├── self-assessment.md          # Agent's notes on its own performance
│   ├── skill-suggestions.md        # Skills/improvements the agent recommends
│   ├── patterns.md                 # Behavioral patterns the agent has noticed
│   └── processing-log.md          # What the agent couldn't parse, quality issues
│
└── templates/
    ├── daily-note.md
    ├── task.md
    ├── person.md
    └── project.md
```

### Daily Note Template

```markdown
---
date: {{date}}
summary: ""
mood: ""
---

# {{date}} — Daily Log

## Morning Briefing
- Calendar: ...
- Pending tasks: ...

## Time Blocks

### 07:00–07:30
- Conversation with [[wife]] about weekend plans
- Task created: [[haircut-daughter-2026-02]]

### 07:30–08:00
- Commute, no notable conversations

### 08:00–08:30
- Work standup meeting
- Discussed: ...
- Action items: ...

(continues in 30-minute blocks)

## Evening Summary
- Tasks completed: ...
- Tasks created: ...
- Notable moments: ...
- Agent notes: ...

## Links
- Tasks created today: [[task1]], [[task2]]
- People mentioned: [[wife]], [[daughter]]
- Projects discussed: [[beach-trip]]
```

### Task Note Template

```markdown
---
status: pending          # pending, reminded, snoozed, completed
created: 2026-02-19T07:15:00
source: conversation     # conversation, calendar, email, manual
due: 2026-02-22
remind_at: 2026-02-19T12:00:00
remind_count: 0
context: "Wife asked to schedule daughter's haircut for the weekend"
---

# Schedule Daughter's Haircut

## Details
- What: Haircut appointment for [[daughter]]
- When: This weekend (Feb 22-23)
- Requested by: [[wife]]
- Original context: Morning conversation on [[2026-02-19]]

## Agent Notes
- No preferred salon found in memory. Ask user if they have a preference.
- Weekend availability may be limited. Suggest booking today.

## History
- 2026-02-19 07:15 — Task created from conversation
- 2026-02-19 12:00 — Reminder delivered (heartbeat)
```

### Person Note Template

```markdown
---
name: ""
relationship: ""
last_seen: ""
---

# {{name}}

## Key Information
- Relationship: ...
- Context: ...

## Conversation Log
- [[2026-02-19]]: Discussed weekend plans, asked about haircut scheduling
- [[2026-02-18]]: ...

## Things to Remember
- ...
```

### Private Section

The `private/` folder contains content the agent classifies as private. Behavior rules:

- **Agent writes here normally** — same markdown format, same linking
- **Agent NEVER references this content in heartbeats**
- **Agent NEVER surfaces this content proactively**
- **Agent NEVER speaks about this content unless the user specifically asks**
- **User initiates all conversations about private content** — the agent responds but never starts
- **Suggestions are written as notes only** — the user reads them manually in Obsidian at their own discretion
- **Password protection**: Use Obsidian community plugin "Protected Note" or filesystem-level encryption (gocryptfs) for the private folder
- **For Phase 1 prototype**: Folder on the home server behind Tailscale is sufficient. Encryption can be added later.

### Content Classification

The LLM classifies every processed piece of content as part of its summarization step:

```
CLASSIFICATION PROMPT (part of the processing pipeline system prompt):

When processing transcribed audio, classify each distinct topic or event
into one of these categories:

- PUBLIC: Work conversations, family logistics, tasks, appointments,
  meals, travel planning, general interests, media discussions (movies,
  games, books), health/fitness, home management, shopping, errands.
  → Written to daily notes, tasks, projects as appropriate.
  → Can be referenced in heartbeats and proactive notifications.

- PRIVATE: Adult content, intimate conversations, personal preferences
  the user would not want spoken aloud, anything the user has explicitly
  asked to keep private.
  → Written ONLY to the private/ section of the vault.
  → NEVER referenced in heartbeats or proactive output.
  → ONLY discussed when the user explicitly asks.

When in doubt, classify as PRIVATE. User privacy is always the priority.
```

---

## 11. Privacy Architecture

### Principles

1. **All data stays on user-owned hardware**: Home server, belt device, phone. No cloud storage for audio, transcripts, or personal data.
2. **Short-lived edge data**: The belt device (or phone) holds a rolling buffer of recent audio. Once transmitted to the home server and acknowledged, local copies are discarded.
3. **Encryption at rest**: Home server vault is on encrypted storage. Private folder has additional encryption layer.
4. **Device theft mitigation**: If a belt device is lost/stolen, the home server revokes its MQTT credentials. The device has no stored credentials of value — it only knows the MQTT broker address and its own client certificate, which can be revoked server-side.
5. **Private content compartmentalization**: Architectural separation, not just prompting. Private content lives in a separate folder with separate access rules. The heartbeat scheduler physically cannot access the private folder path.
6. **Recording indicator**: The glasses LED is always on when the mic is active. This is a hard-wired connection, not software-controlled. If the mic has power, the LED has power.

### Two-Party Consent Handling

The system records continuously. In two-party consent jurisdictions, this has legal implications.

For the personal prototype:
- Wear a visible indicator (shirt, badge, or the glasses LED) that signals you are recording
- This is a social experiment and personal tool — act in good faith
- Be prepared to pause recording in situations where it would be inappropriate
- The QUIET mode voice command immediately stops all audio processing

This is NOT a solved legal problem for a product. For personal use, transparency and the ability to quickly disable are the minimum requirements.

### Data Lifecycle

```
Audio captured (glasses mic / phone mic)
    │
    ├── Belt device: noise filter, buffer (rolling 5-minute window)
    │
    ├── Stream to home server via MQTT
    │
    ├── Home server: transcribe (Whisper), process (LLM)
    │     ├── Classify content (public / private)
    │     ├── Extract tasks, events, notes
    │     ├── Write to Obsidian vault
    │     └── Discard raw audio after processing (configurable retention)
    │
    └── Belt device: discard audio after server acknowledges receipt
```

Raw audio retention on the home server is configurable. Default: discard after successful transcription. Option to retain for X days for debugging/improvement, then auto-delete.

---

## 12. Agent Behavior Model

### Communication Rules

The agent communicates with the user in exactly three ways:

1. **Heartbeat intervals**: Scheduled briefings at user-defined times and intervals. Contains calendar events, task reminders, infrastructure alerts, email/text summaries. NEVER contains private content.

2. **Wake word response**: User says the wake word, agent acknowledges with a tone, listens for the query, processes, responds. Can discuss ANY content including private when asked.

3. **Notifications**: Calendar events approaching, new important emails/texts, infrastructure alerts that need attention. Mirrors phone notification behavior. NEVER contains private content.

The agent NEVER initiates casual conversation. It NEVER offers unsolicited opinions. It NEVER makes small talk. It is a tool — responsive, capable, and quiet.

### Task Management Behavior

When the agent detects a task in conversation:

1. Create task note in Obsidian with full context
2. Add to SQLite active task queue with reminder schedule
3. At next heartbeat: mention the new task briefly
4. If task has a deadline and isn't completed:
   - Remind at the configured interval
   - Escalate reminder urgency as deadline approaches
   - After deadline: flag as overdue in next heartbeat
5. If task has no deadline:
   - Remind once at next heartbeat
   - If user says "later" or snoozes: remind again tomorrow
   - If task sits idle for 3 days: ask if it's still relevant
6. User can complete tasks via voice: "agent, the haircut is scheduled"

### Incomplete Information Handling

When the agent detects information that is missing key details (like the school event without a date):

1. Note the incomplete information in the task/daily note
2. Flag it with a "needs_info" status
3. At a natural heartbeat (not immediately, let it breathe):
   - "Hey, the teacher at pickup mentioned an event coming up but didn't give a date. Have you found out when that is? I can put it on the calendar whenever you're ready."
4. If user provides the info: complete the note, create calendar event
5. If user says they don't know yet: snooze and ask again tomorrow

### Context-Aware Behavior

The agent adapts based on what it knows:

- **At desk (IO controller connected)**: Can reference what's on screen. Can take actions via HID injection. Richer work context.
- **Mobile (IO controller disconnected)**: Audio-only context. Focus on conversation capture, task extraction, navigation help.
- **Headphones off**: Queue everything, deliver on reconnect. Keep processing for the daily log.
- **Quiet mode**: Stop all processing. Respect the boundary.
- **Sleep mode**: Minimal ambient monitoring (snoring). No notifications until morning.

### Daily Note Generation

The agent builds the daily note continuously throughout the day:

- Every 30 minutes (matching the heartbeat interval), the agent writes a time block summary
- Each time block includes: conversations summarized, tasks identified, notable events, mood/energy observations if detectable
- The evening summary aggregates the day: tasks completed, tasks created, key conversations, notable moments
- The daily note links to all other notes created or referenced that day

---

## 13. Software Module Design

### Home Server Services

```
home-server/
├── docker-compose.yml          # Or k3s manifests if preferred
│
├── services/
│   ├── mqtt-broker/
│   │   └── mosquitto.conf
│   │
│   ├── transcription/
│   │   ├── main.py             # MQTT subscriber, processes audio
│   │   ├── whisper_engine.py   # faster-whisper wrapper
│   │   └── requirements.txt
│   │
│   ├── agent-brain/
│   │   ├── main.py             # Core agent logic
│   │   ├── llm_client.py       # Ollama/vLLM client
│   │   ├── classifier.py       # Public/private content classification
│   │   ├── task_extractor.py   # Task identification from transcripts
│   │   ├── heartbeat.py        # Heartbeat scheduler
│   │   ├── notification.py     # Notification queue manager
│   │   ├── context.py          # Context assembly for LLM prompts
│   │   └── requirements.txt
│   │
│   ├── tts/
│   │   ├── main.py             # MQTT subscriber, generates TTS audio
│   │   ├── piper_engine.py     # Piper TTS wrapper
│   │   └── requirements.txt
│   │
│   ├── vault-manager/
│   │   ├── main.py             # Obsidian vault file operations
│   │   ├── daily_notes.py      # Daily note creation and updates
│   │   ├── task_notes.py       # Task note CRUD
│   │   ├── people_notes.py     # People note management
│   │   ├── private_notes.py    # Private section management
│   │   └── requirements.txt
│   │
│   ├── mcp-servers/
│   │   ├── home-assistant/
│   │   ├── k8s-monitor/
│   │   ├── docker-monitor/
│   │   ├── discord/
│   │   ├── email/
│   │   └── calendar/
│   │
│   └── operational-db/
│       ├── schema.sql          # SQLite schema
│       └── db_client.py        # Database access layer
│
└── config/
    ├── agent.yaml              # Agent behavior configuration
    ├── heartbeat.yaml          # Heartbeat schedule
    ├── integrations.yaml       # MCP server configs
    └── privacy.yaml            # Classification rules, retention policies
```

### SQLite Operational Schema

```sql
-- Active task queue
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, reminded, snoozed, completed, overdue
    created_at TIMESTAMP NOT NULL,
    due_at TIMESTAMP,
    next_remind_at TIMESTAMP,
    remind_count INTEGER DEFAULT 0,
    obsidian_path TEXT,             -- Path to corresponding Obsidian note
    source TEXT,                    -- conversation, calendar, email, manual
    context TEXT,                   -- Brief context for reminder delivery
    is_private BOOLEAN DEFAULT FALSE
);

-- Heartbeat notification queue
CREATE TABLE heartbeat_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP,
    content_type TEXT,              -- task_reminder, calendar, email, alert, briefing
    content TEXT NOT NULL,          -- JSON payload
    priority INTEGER DEFAULT 5,    -- 1 = highest (infrastructure alert), 10 = lowest
    is_private BOOLEAN DEFAULT FALSE
);

-- Device state tracking
CREATE TABLE device_state (
    device_id TEXT PRIMARY KEY,
    device_type TEXT,               -- phone, pi5, io-controller
    last_seen TIMESTAMP,
    battery_percent INTEGER,
    audio_quality_avg FLOAT,
    mode TEXT,                      -- active, input_only, quiet, sleep
    headphones_connected BOOLEAN
);

-- Processing log (debugging and quality improvement)
CREATE TABLE processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    audio_quality FLOAT,
    transcription_confidence FLOAT,
    action_taken TEXT,              -- task_created, note_updated, classified_private, discarded
    notes TEXT
);

-- Agent self-assessment
CREATE TABLE agent_metrics (
    date TEXT PRIMARY KEY,
    tasks_created INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    heartbeats_delivered INTEGER DEFAULT 0,
    transcription_failures INTEGER DEFAULT 0,
    avg_audio_quality FLOAT,
    notes TEXT
);
```

### TTS Decision Location

TTS generation happens on the **belt device (Pi 5)** using Piper TTS, not on the home server. This minimizes latency for spoken responses.

Flow:
1. Home server generates text response
2. Text sent via MQTT to belt device
3. Belt device runs Piper TTS locally
4. Audio plays through bone conduction headphones (or BT headphones in Phase 1)

For Phase 1 (phone app): TTS runs on the phone via Piper's Android-compatible build or a lightweight TTS library.

---

## 14. Daily Workflow Reference

This section describes a complete day using the system, documenting expected agent behavior and technical requirements at each moment.

### 07:00 — Wake Up

**User action**: Puts on Bluetooth bone conduction headphones.

**System behavior**:
- Phone detects BT headphone connection
- Agent transitions from SLEEP_MONITOR → FULLY_ACTIVE
- Agent delivers queued morning heartbeat:
  - "Good morning. Here's your day: you have a standup at 9, a 1-on-1 with Sarah at 2, and nothing on the calendar this evening. You have two pending tasks: follow up on the Q3 report, and schedule your daughter's haircut. Your k3s cluster is healthy, no alerts overnight."
- Duration: ~30 seconds of spoken audio
- Daily note for today is created with morning briefing section

### 07:15 — Conversation with Wife

**User action**: Has natural conversation. Wife asks to schedule daughter's haircut this weekend.

**System behavior**:
- Audio captured by phone mic
- Streamed to home server via MQTT
- Whisper transcribes the conversation
- LLM identifies: task (schedule haircut), people (wife, daughter), timeframe (this weekend)
- Task note created in Obsidian: `tasks/haircut-daughter-2026-02.md`
- Task added to SQLite queue with reminder at next heartbeat
- Daily note updated with time block summary
- People notes for wife and daughter updated with conversation reference

### 07:30 — Heartbeat (Work Interval)

This heartbeat only fires if configured to start at 07:30. Otherwise, the task waits for the first work-hours heartbeat.

**Agent says**: "Quick note — I captured that you need to schedule a haircut for your daughter this weekend. I'll remind you later if you haven't gotten to it."

### 08:00–12:00 — Work at Desk

**System behavior (Phase 1, no IO controller)**:
- Phone on desk, mic captures room audio
- All meetings taken through computer speakers are picked up
- 30-minute time block summaries written to daily note
- Tasks extracted from meeting conversations
- Work heartbeats every 30 minutes cover: new tasks, upcoming calendar, infrastructure alerts, important emails

**System behavior (with IO controller, Phase 4)**:
- IO controller detects belt device BLE proximity → connects
- Agent gains screen context and keyboard context
- Can correlate what user is working on (visible on screen) with what they're saying
- Can take actions on the computer via HID injection when requested

### 12:00 — Lunch at Taco Bell

**System behavior**:
- Phone mic captures ordering interaction
- LLM extracts meal information from transcript
- Nutrition note updated: `health/nutrition/2026-02-19.md`
- Ambient audio (TikTok, restaurant noise) is noted at low detail in daily log
- No heartbeat fires unless there's something urgent

### 12:30–17:00 — Afternoon Work

Same as morning work block. Continued 30-minute summaries. Task reminders at heartbeat intervals.

### 17:15 — Daughter Pickup, Teacher Conversation

**System behavior**:
- Audio captured, teacher mentions upcoming event without a date
- LLM identifies: incomplete information (event exists, date unknown)
- Creates task with `needs_info` status: `tasks/school-event-date.md`
- Does NOT ask about it immediately (user is at school, wrangling kid)
- Queues follow-up for evening heartbeat or next morning

### 18:00 — Evening Heartbeat

**Agent says**: "Here's your evening summary. You had 3 meetings today, created 2 new tasks. The Q3 report follow-up is still pending. Also, the teacher at pickup mentioned an event coming up for your daughter but no date was given. Have you found out when that is? I can put it on the calendar whenever you're ready."

If the haircut still hasn't been scheduled: "And a reminder — the haircut for your daughter this weekend still needs to be booked."

### Late Evening — Private Content

**System behavior**:
- Audio continues to be processed
- LLM classifies content as PRIVATE
- Notes written to `private/notes/` ONLY
- No heartbeat, no proactive mention, no spoken reference
- If user asks about something in this context, agent responds normally through headphones
- Agent NEVER initiates conversation about private content

### 21:00 — Conversation About Beach Trip

**System behavior**:
- Audio captured, LLM identifies planning conversation
- Project note created or updated: `projects/beach-trip.md`
- Key details extracted: locations discussed, activities mentioned, preferences noted
- May appear in tomorrow's morning briefing if there are actionable items
- Daily note updated

### 21:30 — Shower, Headphones Off

**System behavior**:
- BT headphones disconnect → agent transitions to INPUT_ONLY mode
- Phone mic still captures ambient room audio (from wherever the phone is)
- Processing continues, daily note continues to be updated
- Any heartbeats or notifications are queued
- When headphones reconnect: "While you were away — no new alerts. Your k3s cluster is still healthy."

### 22:00 — Sleep

**User action**: Says "agent, goodnight" or agent detects sleep schedule time.

**System behavior**:
- Agent transitions to SLEEP_MONITOR mode
- Full audio processing stops
- Lightweight ambient monitoring begins (snoring detection)
- Sleep data logged to `health/sleep/2026-02-19.md`
- No notifications until morning trigger
- Daily note finalized with evening summary

---

## 15. Hardware BOM (Prototype)

### Phase 1: Android App

| Item | Est. Cost | Notes |
|------|-----------|-------|
| Android phone | Already owned | Running Termux + Python app |
| Bone conduction headphones (Shokz OpenRun) | $80-130 | BT output device |
| Tailscale | Free tier | VPN mesh to home server |
| Home server with GPU | Already owned | Running all server-side services |

**Total additional cost: $80-130**

### Phase 2: Belt Device

| Item | Est. Cost | Notes |
|------|-----------|-------|
| Raspberry Pi 5 (4GB) | $60 | Belt compute module |
| Pi 5 passive heatsink case | $15 | Thermal management |
| MicroSD card (64GB) | $12 | OS + rolling buffer |
| USB-C power bank (10000mAh) x2 | $40 | Hot-swap battery |
| USB lavalier mic | $15 | Interim mic before glasses |
| Belt pouch/clip case | $15 | Wearable enclosure |
| USB audio DAC (for headphone output) | $10 | If Pi 5 audio out isn't sufficient |

**Total additional cost: ~$170**

### Phase 3: Smart Glasses + Undershirt

| Item | Est. Cost | Notes |
|------|-----------|-------|
| Eyeglass frames (plain or prescription) | $20-50 | Base frames to modify |
| MEMS microphone (Knowles SPH0645 or similar) | $5 | Glasses mic |
| Bone conduction transducers x2 | $15-30 | Glasses audio output |
| Magnetic pogo pin connectors x2 sets | $10-20 | Glasses + collar connection |
| LED (small, soft-glow) | $2 | Recording indicator |
| Thin flex cable / silicone wire (6-conductor) | $10-15 | Shirt cable |
| Compression tank top | $15 | Base garment |
| Miscellaneous (solder, connectors, adhesive) | $20 | Assembly supplies |

**Total additional cost: ~$120-170**

### Phase 4: IO Controller

| Item | Est. Cost | Notes |
|------|-----------|-------|
| Raspberry Pi 5 (4GB) or similar SBC | $60 | Controller compute |
| HDMI capture card(s) (USB or HAT-based) | $30-60 | Screen capture, per monitor |
| HDMI splitter/passthrough | $15-30 | Per monitor |
| USB hub with passthrough | $15 | Keyboard/mouse observation |
| Enclosure | $15 | Desk-mountable case |

**Total additional cost: ~$135-180**

### Total Prototype Budget

All phases: approximately **$500-650** plus the home server and phone you already own.

---

## 16. Open Source Considerations

### License

Recommend: MIT or Apache 2.0 for maximum community adoption and contribution.

### Repository Structure

```
project-aegis/
├── README.md
├── LICENSE
├── DESIGN_SPEC.md              # This document
├── CHANGELOG.md
├── BUILD_LOG.md                # Ongoing build diary
│
├── edge-device/                # Runs on phone (Termux) or Pi 5
│   ├── main.py
│   ├── config.yaml
│   ├── audio/
│   ├── comms/
│   ├── state/
│   └── utils/
│
├── home-server/
│   ├── docker-compose.yml
│   ├── services/
│   │   ├── transcription/
│   │   ├── agent-brain/
│   │   ├── tts/
│   │   ├── vault-manager/
│   │   ├── mcp-servers/
│   │   └── operational-db/
│   └── config/
│
├── io-controller/              # Phase 4
│   ├── main.py
│   ├── hdmi_capture.py
│   ├── hid_injector.py
│   ├── ble_proximity.py
│   └── config.yaml
│
├── hardware/
│   ├── glasses/
│   │   ├── schematic.pdf
│   │   ├── bom.csv
│   │   └── assembly-guide.md
│   ├── undershirt/
│   │   ├── routing-diagram.pdf
│   │   └── assembly-guide.md
│   ├── belt-device/
│   │   └── assembly-guide.md
│   └── io-controller/
│       ├── schematic.pdf
│       └── assembly-guide.md
│
├── vault-template/             # Starter Obsidian vault
│   ├── daily/
│   ├── tasks/
│   ├── people/
│   ├── projects/
│   ├── health/
│   ├── private/
│   ├── agent/
│   └── templates/
│
└── docs/
    ├── setup-guide.md
    ├── configuration.md
    ├── privacy-model.md
    ├── contributing.md
    └── faq.md
```

### Documentation from Day One

- Every build session gets a log entry in BUILD_LOG.md
- Hardware assembly is photographed and documented
- Software decisions are explained in commit messages and docs
- BOM lists are kept current with sources and prices
- Wiring diagrams and schematics are version-controlled

### Community Contribution Areas

- Alternative wake word models
- Additional MCP server integrations
- Improved noise filtering algorithms
- Alternative form factors (different glasses styles, different shirt designs)
- Snore detection and sleep analysis models
- Mobile app (native Android replacement for Termux prototype)
- Web dashboard for reviewing Obsidian vault and agent metrics
- Alternative LLM backends and prompt tuning

---

## Appendix A: Key Technology References

| Technology | Use | Documentation |
|-----------|-----|--------------|
| OpenWakeWord | Wake word detection | github.com/dscripka/openWakeWord |
| faster-whisper | Speech-to-text | github.com/SYSTRAN/faster-whisper |
| Piper TTS | Text-to-speech | github.com/rhasspy/piper |
| Mosquitto | MQTT broker | mosquitto.org |
| Ollama | Local LLM runtime | ollama.ai |
| Tailscale | Mesh VPN | tailscale.com |
| MCP | Model Context Protocol | modelcontextprotocol.io |
| Home Assistant | Home automation | home-assistant.io |
| Obsidian | Knowledge management | obsidian.md |
| RNNoise | Noise suppression | github.com/xiph/rnnoise |
| Porcupine | Alt wake word engine | picovoice.ai/platform/porcupine |

## Appendix B: Key Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary language | Python | Runs on Android (Termux), Pi 5, and server. Portable across all phases. |
| Communication layer | MQTT over Tailscale | Lightweight, handles intermittent connectivity, topic-based routing. Tailscale provides secure remote access. |
| Knowledge store | Obsidian vault (markdown) | Human-readable, browseable, LLM-friendly file operations. No database complexity. |
| Operational state | SQLite | Fast structured queries for active tasks, heartbeat queue, device state. Complements Obsidian. |
| TTS location | Belt device (Pi 5) | Minimizes latency for spoken responses. Server generates text, belt generates audio. |
| Wake word location | Belt device (Pi 5) / Phone | Must be local for responsiveness. Acknowledgment tone plays immediately, query forwarded to server. |
| Transcription location | Home server | GPU-accelerated Whisper. Belt device has optional fallback for offline use. |
| LLM location | Home server | GPU required for reasonable inference speed. |
| Private content handling | Same vault, separate folder, reactive-only behavior | User's complete self. Never excluded, never surfaced proactively. User initiates. |
| Recording indicator | Hardwired LED on glasses | LED has power whenever mic has power. Not software-controllable. Trust in physics. |
| Form factor | Distributed body-area system | Solves battery, comfort, and compute tradeoffs that kill single-device wearables. |
| IO controller pattern | Hardware MITM (HDMI + USB passthrough) | Peristaltic pump principle. No software install, no auth, no IT approval. |

---

*This is a living document. Update as the project evolves.*
