from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from bidflow.agents.base import BaseAgent


T = TypeVar("T", bound=type[BaseAgent])


@dataclass(frozen=True)
class AgentRegistration:
    name: str
    agent_class: type[BaseAgent]
    kind: str = "external"
    description: str = ""
    source: str = ""


_REGISTRY: dict[str, AgentRegistration] = {}


def register(
    agent: T | str | None = None,
    *,
    name: str | None = None,
    kind: str = "external",
    description: str | None = None,
    source: str = "",
) -> T | Callable[[T], T]:
    """Register a BaseAgent subclass.

    Supports all common forms:
    - @register
    - @register("my_agent")
    - @register(name="my_agent", kind="builtin")
    """

    def decorator(cls: T) -> T:
        if not issubclass(cls, BaseAgent):
            raise TypeError("registered agent must inherit BaseAgent")
        registration_name = name or (agent if isinstance(agent, str) else None) or getattr(cls, "name", cls.__name__)
        registration_name = str(registration_name)
        _REGISTRY[registration_name] = AgentRegistration(
            name=registration_name,
            agent_class=cls,
            kind=kind,
            description=description if description is not None else getattr(cls, "description", ""),
            source=source,
        )
        return cls

    if isinstance(agent, type):
        return decorator(agent)
    return decorator


def list_agents() -> list[AgentRegistration]:
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def get_agent_class(name: str) -> type[BaseAgent]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown agent: {name}")
    return _REGISTRY[name].agent_class


def build_agent(name: str, **config: object) -> BaseAgent:
    return get_agent_class(name)(**config)


def load_external_agent(target: str) -> list[AgentRegistration]:
    before = set(_REGISTRY)
    path = Path(target)
    if path.exists():
        module_path = path / "agent.py" if path.is_dir() else path
        if module_path.suffix != ".py":
            raise ValueError(f"External agent path must be a .py file or directory containing agent.py: {target}")
        module_name = f"bidflow_external_{abs(hash(module_path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load external agent from {target}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        importlib.import_module(target)
    added = sorted(set(_REGISTRY) - before)
    return [_REGISTRY[name] for name in added]


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()
