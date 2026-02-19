# Sotto

**An ambient AI personal assistant that acts as a second memory and proactive life manager.**

Sotto continuously captures audio context, processes it into actionable knowledge, and communicates through scheduled heartbeats, wake word activation, and smart notifications. All processing happens on your own hardware - no cloud dependencies, no subscriptions.

---

## Features

- **Always-On Audio Capture** - Continuous ambient listening with intelligent noise filtering
- **Wake Word Activation** - Hands-free interaction via configurable wake word
- **Heartbeat System** - Scheduled briefings (morning, work intervals, evening summary)
- **Task Extraction** - Automatically identifies tasks from natural conversation
- **Daily Notes** - Auto-generated daily logs with 30-minute time block summaries
- **Privacy by Architecture** - All data stays on your hardware; private content is compartmentalized
- **Obsidian Integration** - Knowledge stored as markdown files, browseable in Obsidian
- **Smart Notifications** - Calendar events, email summaries, infrastructure alerts
- **Graceful Degradation** - Works offline with local buffering and sync-on-reconnect

## Architecture

```
Edge Device (Phone/Pi 5)          Home Server (Brain)
┌─────────────────────┐          ┌──────────────────────────┐
│  Audio Capture       │          │  Whisper STT             │
│  Wake Word Detection │◄──MQTT──►│  Local LLM (Ollama)      │
│  State Machine       │          │  Piper TTS               │
│  TTS Playback        │          │  Obsidian Vault Manager  │
│  Offline Buffer      │          │  Heartbeat Scheduler     │
└─────────────────────┘          │  SQLite Operational DB   │
                                  │  MCP Integration Servers │
                                  └──────────────────────────┘
```

Communication flows over MQTT (Mosquitto) through a Tailscale VPN mesh, enabling secure access from anywhere.

## Quick Start

### Prerequisites

- **Home Server**: Linux machine with Docker and Docker Compose
- **Edge Device**: Android phone with Termux (Phase 1) or Raspberry Pi 5 (Phase 2)
- **Network**: Tailscale VPN configured on both devices
- **Optional**: Ollama installed with a model pulled (e.g., `llama3.1:8b`)

### Server Setup

```bash
# Clone the repository
git clone https://github.com/YourBr0ther/Sotto.git
cd Sotto/home-server

# Configure environment
cp .env.example .env
# Edit .env with your settings (MQTT credentials, Tailscale IP, etc.)

# Start all services
docker compose up -d
```

### Edge Device Setup (Android/Termux)

```bash
# Install Termux from F-Droid (recommended over Play Store)
# In Termux:
pkg install python git
pip install -r requirements.txt

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your MQTT broker address

# Run
python main.py
```

### Edge Device Setup (Raspberry Pi 5)

```bash
# Clone on the Pi
git clone https://github.com/YourBr0ther/Sotto.git
cd Sotto/edge-device

pip install -r requirements.txt
cp config.yaml.example config.yaml
# Edit config.yaml - change device.type to "pi5"

python main.py
```

## Project Structure

```
Sotto/
├── edge-device/              # Runs on phone (Termux) or Pi 5
│   ├── main.py               # Entry point
│   ├── config.yaml           # Device configuration
│   ├── audio/                # Audio I/O abstractions
│   ├── comms/                # MQTT client, audio streaming
│   ├── state/                # Device state machine
│   ├── utils/                # Config loader, logging
│   └── tests/                # Edge device tests
│
├── home-server/              # Runs on home server (Docker)
│   ├── docker-compose.yml    # Full server stack
│   ├── services/
│   │   ├── transcription/    # Whisper STT service
│   │   ├── agent-brain/      # Core LLM agent logic
│   │   ├── tts/              # Piper TTS service
│   │   ├── vault-manager/    # Obsidian vault operations
│   │   ├── operational-db/   # SQLite schema and client
│   │   └── mqtt-broker/      # Mosquitto configuration
│   └── config/               # Shared configuration
│
├── vault-template/           # Starter Obsidian vault
│   ├── daily/                # Daily notes
│   ├── tasks/                # Task notes
│   ├── people/               # People notes
│   ├── projects/             # Project notes
│   ├── health/               # Health tracking
│   ├── private/              # Private content (encrypted)
│   ├── agent/                # Agent self-assessment
│   └── templates/            # Note templates
│
├── io-controller/            # Phase 4 - Desk integration
├── hardware/                 # Hardware designs and BOMs
├── docs/                     # Documentation
├── DESIGN_SPEC.md            # Full design specification
└── CLAUDE.md                 # Development conventions
```

## Configuration

### Edge Device (`edge-device/config.yaml`)

| Setting | Description | Default |
|---------|-------------|---------|
| `device.name` | Device identifier | `sotto-phone` |
| `device.type` | `android` or `pi5` | `android` |
| `audio.sample_rate` | Audio sample rate (Hz) | `16000` |
| `mqtt.broker_host` | MQTT broker Tailscale IP | Required |
| `wake_word.model` | Wake word model name | `hey_jarvis` |
| `heartbeat.schedule` | Briefing schedule | See config |

### Server (`home-server/config/agent.yaml`)

| Setting | Description | Default |
|---------|-------------|---------|
| `llm.model` | Ollama model name | `llama3.1:8b` |
| `llm.base_url` | Ollama API endpoint | `http://ollama:11434` |
| `whisper.model` | Whisper model size | `base` |
| `vault.path` | Obsidian vault path | `/data/vault` |

## Development

### Requirements

- Python 3.11+
- Docker and Docker Compose
- pytest for testing

### Running Tests

```bash
# Edge device tests
cd edge-device
pip install -r requirements-dev.txt
pytest tests/ -v

# Home server service tests
cd home-server/services/agent-brain
pip install -r requirements-dev.txt
pytest tests/ -v
```

### Code Style

This project uses `ruff` for linting and formatting:

```bash
ruff check .
ruff format .
```

## Deployment

### Docker Compose (Recommended)

```bash
cd home-server
docker compose up -d

# View logs
docker compose logs -f

# Check service health
docker compose ps
```

### k3s / Kubernetes

k3s manifests are provided in `home-server/k3s/`:

```bash
kubectl apply -f home-server/k3s/
```

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Android app prototype | **In Progress** |
| Phase 2 | Raspberry Pi 5 belt device | Planned |
| Phase 3 | Smart glasses + undershirt | Planned |
| Phase 4 | IO controller (desk integration) | Planned |

## Privacy

Sotto is designed with privacy as an architectural constraint, not a policy:

- **All data stays on your hardware** - No cloud storage for audio, transcripts, or personal data
- **Private content compartmentalization** - Separate folder with separate access rules
- **Short-lived edge data** - Audio buffers are discarded after server acknowledgment
- **No credential exposure** - AI never sees authentication tokens (peristaltic pump pattern)
- **Physical recording indicator** - Hardwired LED on glasses (Phase 3)

## License

MIT License - See [LICENSE](LICENSE) for details.

## Acknowledgments

Built with:
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - Speech-to-text
- [Piper](https://github.com/rhasspy/piper) - Text-to-speech
- [OpenWakeWord](https://github.com/dscripka/openWakeWord) - Wake word detection
- [Mosquitto](https://mosquitto.org/) - MQTT broker
- [Ollama](https://ollama.ai/) - Local LLM runtime
- [Obsidian](https://obsidian.md/) - Knowledge management
