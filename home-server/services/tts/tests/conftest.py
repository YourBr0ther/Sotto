"""Conftest for TTS tests - ensures correct module imports."""

import sys
from pathlib import Path

# Clear any cached 'main' module from other services to avoid collision
for mod_name in list(sys.modules):
    if mod_name == "main":
        del sys.modules[mod_name]

service_dir = str(Path(__file__).parent.parent)
if service_dir in sys.path:
    sys.path.remove(service_dir)
sys.path.insert(0, service_dir)
