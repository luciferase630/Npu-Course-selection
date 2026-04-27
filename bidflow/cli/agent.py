from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from bidflow.agents.registry import load_external_agent, list_agents
from bidflow.config.defaults import default_registry_path


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("agent", help="Manage bidding agents.")
    agent_subparsers = parser.add_subparsers(dest="agent_command", required=True)

    agent_subparsers.add_parser("list", help="List registered agents.")

    init_parser = agent_subparsers.add_parser("init", help="Create an agent template.")
    init_parser.add_argument("name")
    init_parser.add_argument("--template", choices=["minimal", "advanced"], default="minimal")

    register_parser = agent_subparsers.add_parser("register", help="Register an external agent.")
    register_parser.add_argument("target")

    info_parser = agent_subparsers.add_parser("info", help="Show agent details.")
    info_parser.add_argument("name")


def run(args: argparse.Namespace) -> int:
    if args.agent_command == "list":
        _load_persisted_agents()
        rows = list_agents()
        print(f"{'NAME':<16} {'TYPE':<10} DESCRIPTION")
        for row in rows:
            print(f"{row.name:<16} {row.kind:<10} {row.description}")
        return 0
    if args.agent_command == "init":
        return _init_agent(args.name, args.template)
    if args.agent_command == "register":
        registrations = load_external_agent(args.target)
        _persist_agent_target(args.target)
        if registrations:
            for registration in registrations:
                print(f"registered {registration.name} from {args.target}")
        else:
            print(f"loaded {args.target}; no new @register agent was found")
        return 0
    if args.agent_command == "info":
        _load_persisted_agents()
        for row in list_agents():
            if row.name == args.name:
                print(f"name: {row.name}")
                print(f"type: {row.kind}")
                print(f"description: {row.description}")
                print(f"source: {row.source}")
                return 0
        raise SystemExit(f"unknown agent: {args.name}")
    raise SystemExit(f"unknown agent command: {args.agent_command}")


def _init_agent(name: str, template: str) -> int:
    target = Path(name)
    target.mkdir(parents=True, exist_ok=False)
    class_name = "".join(part.capitalize() for part in target.name.replace("-", "_").split("_")) + "Agent"
    (target / "__init__.py").write_text("", encoding="utf-8")
    (target / "agent.py").write_text(
        f"""from __future__ import annotations

from bidflow.agents import AgentContext, BaseAgent, BidDecision, register


@register("{target.name}")
class {class_name}(BaseAgent):
    description = "User strategy scaffold."

    def decide(self, context: AgentContext) -> BidDecision:
        # Minimal example: bid 1 bean on the highest-utility visible courses.
        ordered = sorted(context.courses, key=lambda course: course.utility, reverse=True)
        bids = {{}}
        for course in ordered[:5]:
            if sum(bids.values()) + 1 <= context.budget_initial:
                bids[course.course_id] = 1
        return BidDecision(bids=bids, explanation="Minimal scaffold strategy.")
""",
        encoding="utf-8",
    )
    (target / "config.yaml").write_text("name: " + target.name + "\n", encoding="utf-8")
    (target / "README.md").write_text(f"# {target.name}\n\nEdit `agent.py` and run `bidflow agent register ./{target.name}`.\n", encoding="utf-8")
    print(f"created {target}")
    return 0


def _persist_agent_target(target: str) -> None:
    registry_path = default_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agents": []}
    if registry_path.exists():
        payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or payload
    agents = list(payload.get("agents", []))
    if target not in agents:
        agents.append(target)
    payload["agents"] = agents
    registry_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _load_persisted_agents() -> None:
    registry_path = default_registry_path()
    if not registry_path.exists():
        return
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    for target in payload.get("agents", []):
        try:
            load_external_agent(str(target))
        except Exception as exc:  # pragma: no cover - defensive CLI warning
            print(f"warning: failed to load registered agent {target}: {exc}")
