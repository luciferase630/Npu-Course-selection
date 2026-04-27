from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bidflow.config.defaults import default_config_path


def load_yaml(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"config must be a mapping: {source}")
    return payload


def load_global_config(path: str | Path | None = None) -> dict[str, Any]:
    return load_yaml(path or default_config_path())


def deep_merge(*configs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for config in configs:
        result = _merge_two(result, config)
    return result


def _merge_two(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_two(merged[key], value)
        else:
            merged[key] = value
    return merged


def population_string_from_yaml(path: str | Path) -> str:
    payload = load_yaml(path)
    if "population" in payload and isinstance(payload["population"], str):
        return payload["population"]
    assignments = payload.get("assignments", [])
    if not isinstance(assignments, list):
        raise ValueError("population assignments must be a list")
    parts = []
    for row in assignments:
        if not isinstance(row, dict):
            raise ValueError("population assignment rows must be mappings")
        selector = str(row.get("selector", "")).strip()
        agent = str(row.get("agent", "")).strip()
        if selector and agent:
            parts.append(f"{selector}={agent}")
    if not parts:
        raise ValueError(f"population file has no assignments: {path}")
    return ",".join(parts)
