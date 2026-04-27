from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bidflow.agents import AgentContext, BaseAgent, BidDecision, build_agent, list_agents
from bidflow.agents.context import CourseInfo
from bidflow.agents.registry import load_external_agent
from bidflow.core.population import Population


class BidFlowCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "bidflow", *args],
            check=False,
            text=True,
            capture_output=True,
        )

    def test_builtin_agents_are_registered(self) -> None:
        names = {registration.name for registration in list_agents()}
        self.assertIn("behavioral", names)
        self.assertIn("cass", names)
        self.assertIn("llm", names)
        self.assertEqual(type(build_agent("cass")).__name__, "CASSAgent")

    def test_population_string_parses_focal_and_background(self) -> None:
        population = Population.parse("focal:S001=cass,background=behavioral")
        self.assertEqual(population.background_agent, "behavioral")
        self.assertEqual(population.focal_assignments, {"S001": "cass"})

    def test_external_agent_loader_registers_strategy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent_path = Path(tmp) / "my_agent.py"
            agent_path.write_text(
                """
from bidflow.agents import AgentContext, BaseAgent, BidDecision, register

@register("unit_external_agent")
class UnitExternalAgent(BaseAgent):
    def decide(self, context: AgentContext) -> BidDecision:
        return BidDecision({})
""",
                encoding="utf-8",
            )
            registrations = load_external_agent(str(agent_path))
        self.assertEqual([registration.name for registration in registrations], ["unit_external_agent"])

    def test_cass_agent_decides_from_public_context(self) -> None:
        context = AgentContext(
            student_id="S001",
            budget_initial=100,
            budget_available=100,
            credit_cap=20,
            time_point=1,
            time_points_total=3,
            courses=(
                CourseInfo(course_id="FND001-A", course_code="FND001", capacity=20, utility=90, credit=2),
                CourseInfo(course_id="MCO001-A", course_code="MCO001", capacity=20, utility=85, credit=2),
            ),
        )
        decision = build_agent("cass").decide(context)
        decision.validate(context)
        self.assertTrue(decision.bids)
        self.assertLessEqual(sum(decision.bids.values()), 100)

    def test_cli_help_and_agent_list(self) -> None:
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        list_result = self.run_cli("agent", "list")
        self.assertEqual(list_result.returncode, 0, list_result.stderr)
        self.assertIn("cass", list_result.stdout)

    def test_market_generate_validate_session_and_replay_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            market_dir = root / "market"
            run_dir = root / "run"
            replay_dir = root / "replay"
            generate = self.run_cli("market", "generate", "--scenario", "medium", "--output", str(market_dir))
            self.assertEqual(generate.returncode, 0, generate.stderr)
            validate = self.run_cli("market", "validate", str(market_dir))
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertTrue((market_dir / "bidflow_metadata.json").exists())

            session = self.run_cli(
                "session",
                "run",
                "--market",
                str(market_dir),
                "--population",
                "background=behavioral",
                "--run-id",
                "bidflow_unittest_smoke",
                "--output",
                str(run_dir),
                "--time-points",
                "1",
            )
            self.assertEqual(session.returncode, 0, session.stderr)
            self.assertTrue((run_dir / "metrics.json").exists())
            self.assertTrue((run_dir / "bidflow_metadata.json").exists())

            replay = self.run_cli(
                "replay",
                "run",
                "--baseline",
                str(run_dir),
                "--focal",
                "S001",
                "--agent",
                "cass",
                "--data-dir",
                str(market_dir),
                "--output",
                str(replay_dir),
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertTrue((replay_dir / "cass_focal_backtest_metrics.json").exists())
            self.assertTrue((replay_dir / "bidflow_metadata.json").exists())
