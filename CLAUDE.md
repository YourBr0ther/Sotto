# Sotto - Project Conventions

## Project Overview

Sotto (codename: Project Aegis) is an ambient AI personal assistant system. It captures audio context, processes it into actionable knowledge via a home server pipeline, and communicates with the user through scheduled heartbeats, wake word activation, and notifications.

## Architecture

- **edge-device/**: Python app running on Android (Termux) or Raspberry Pi 5. Handles audio capture, wake word detection, state machine, and MQTT communication.
- **home-server/**: Docker-composed services running on a home server. Handles transcription (Whisper), LLM reasoning, TTS (Piper), Obsidian vault management, and integrations via MCP.
- **vault-template/**: Obsidian vault structure template for the agent's long-term memory.
- **io-controller/**: Phase 4 - Hardware MITM for desk integration (future).

## Tech Stack

- **Language**: Python 3.11+
- **Communication**: MQTT (Mosquitto) over Tailscale VPN
- **STT**: faster-whisper
- **TTS**: Piper
- **LLM**: Ollama (local)
- **Knowledge Store**: Obsidian vault (markdown files)
- **Operational DB**: SQLite
- **Deployment**: Docker Compose / k3s

## Code Conventions

### Python

- Use Python 3.11+ features
- Type hints on all function signatures
- Use `abc.ABC` and `@abstractmethod` for interfaces
- Use `dataclasses` or `pydantic` for data models
- Use `pytest` for testing
- Use `ruff` for linting and formatting
- Follow PEP 8 naming conventions
- Use `logging` module with structured logging (JSON format)

### Testing

- **TDD is mandatory**: Write tests before implementation
- Tests live in `tests/` directories alongside the code they test
- Use `pytest` with `pytest-asyncio` for async tests
- No mock code in production. Mocks are only for test doubles.
- No fallback implementations in production code
- Test file naming: `test_<module_name>.py`
- Minimum test categories: unit tests, integration tests
- Use fixtures for shared test setup

### Project Structure

```
edge-device/           # Runs on phone/Pi 5
  audio/               # Audio I/O abstractions
  comms/               # MQTT client, audio streaming
  state/               # Device state machine
  utils/               # Config loader, logging
  tests/               # All edge device tests

home-server/           # Runs on home server
  services/            # Individual service directories
    transcription/     # Whisper STT
    agent-brain/       # Core LLM agent logic
    tts/               # Piper TTS
    vault-manager/     # Obsidian file operations
    operational-db/    # SQLite schema and client
    mqtt-broker/       # Mosquitto config
    mcp-servers/       # Integration brokers
  config/              # Shared configuration files
```

### MQTT Topics

All MQTT messages use JSON payloads with this envelope:
```json
{
  "timestamp": "ISO-8601",
  "source": "device-id",
  "type": "message_type",
  "payload": {}
}
```

Topic hierarchy: `sotto/` prefix (not `aegis/`)

### Configuration

- YAML files for all configuration
- Environment variables override YAML values
- Secrets via environment variables only, never in config files
- Config files are committed; `.env` files are not

### Docker

- One Dockerfile per service
- Multi-stage builds to minimize image size
- Non-root users in containers
- Health checks on all services
- docker-compose.yml at `home-server/docker-compose.yml`

### Git

- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Feature branches off `main`
- No force pushes to `main`
- README.md updated after critical changes

### Privacy

- Private content goes to `private/` vault section only
- Heartbeat scheduler cannot access private folder path
- Credentials live in MCP server configs, never exposed to LLM
- Raw audio discarded after transcription by default

## Key Files

- `DESIGN_SPEC.md` - Full design specification
- `edge-device/main.py` - Edge device entry point
- `edge-device/config.yaml` - Edge device configuration
- `home-server/docker-compose.yml` - Server deployment
- `home-server/config/agent.yaml` - Agent behavior config
