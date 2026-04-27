from __future__ import annotations

from pathlib import Path


def default_config_dir() -> Path:
    return Path.home() / ".bidflow"


def default_config_path() -> Path:
    return default_config_dir() / "config.yaml"


def default_registry_path() -> Path:
    return default_config_dir() / "agents.yaml"
