from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path

from bidflow.agents import AgentContext, BaseAgent, BidDecision, build_agent, list_agents
from bidflow.agents.context import CourseInfo
from bidflow.agents.registry import load_external_agent
from bidflow.core.population import Population
from src.analysis.cass_policy_sensitivity import POLICY_SWEEP, oat_sensitivity_cases
from src.analysis.crowding_boundary_fit import collect_boundary_observations, evaluate_models


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
        upgraded = build_agent("cass", policy="cass_v2").decide(context)
        self.assertEqual(upgraded.metadata["cass_policy_metrics"]["cass_policy"], "cass_v2")

    def test_cli_help_and_agent_list(self) -> None:
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("gui", help_result.stdout)
        list_result = self.run_cli("agent", "list")
        self.assertEqual(list_result.returncode, 0, list_result.stderr)
        self.assertIn("cass", list_result.stdout)
        sensitivity_help = self.run_cli("analyze", "cass-sensitivity", "--help")
        self.assertEqual(sensitivity_help.returncode, 0, sensitivity_help.stderr)
        self.assertIn("--quick", sensitivity_help.stdout)
        boundary_help = self.run_cli("analyze", "crowding-boundary", "--help")
        self.assertEqual(boundary_help.returncode, 0, boundary_help.stderr)
        self.assertIn("--summary-table", boundary_help.stdout)
        market_create_help = self.run_cli("market", "create", "--help")
        self.assertEqual(market_create_help.returncode, 0, market_create_help.stderr)
        self.assertIn("--students", market_create_help.stdout)
        self.assertIn("--classes", market_create_help.stdout)
        self.assertIn("--majors", market_create_help.stdout)
        self.assertIn("--codes", market_create_help.stdout)
        self.assertIn("--dry-run", market_create_help.stdout)
        self.assertIn("--audit", market_create_help.stdout)

    def test_market_create_generates_complete_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_dir = Path(tmp) / "easy_market"
            create = self.run_cli(
                "market",
                "create",
                "--output",
                str(market_dir),
                "--students",
                "12",
                "--classes",
                "30",
                "--majors",
                "3",
                "--seed",
                "123",
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            for filename in (
                "profiles.csv",
                "profile_requirements.csv",
                "students.csv",
                "courses.csv",
                "student_course_code_requirements.csv",
                "student_course_utility_edges.csv",
                "generation_metadata.json",
                "bidflow_metadata.json",
            ):
                self.assertTrue((market_dir / filename).exists(), filename)
            validate = self.run_cli("market", "validate", str(market_dir))
            self.assertEqual(validate.returncode, 0, validate.stderr)
            metadata = json.loads((market_dir / "bidflow_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["command"], "market create")
            self.assertEqual(metadata["effective_parameters"]["students"], 12)
            self.assertEqual(metadata["effective_parameters"]["sections"], 30)
            edge_rows = (market_dir / "student_course_utility_edges.csv").read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(len(edge_rows) - 1, 12 * 30)

    def test_market_create_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_dir = Path(tmp) / "dry_market"
            result = self.run_cli(
                "market",
                "create",
                "--output",
                str(market_dir),
                "--students",
                "12",
                "--classes",
                "30",
                "--majors",
                "3",
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("dry-run", result.stdout)
            self.assertIn('"students": 12', result.stdout)
            self.assertFalse(market_dir.exists())

    def test_market_create_infers_profiles_from_largest_scale_signal(self) -> None:
        many_students = self.run_cli("market", "create", "--students", "800", "--classes", "30", "--dry-run")
        self.assertEqual(many_students.returncode, 0, many_students.stderr)
        self.assertIn('"profiles": 6', many_students.stdout)

        many_classes = self.run_cli("market", "create", "--students", "50", "--classes", "500", "--dry-run")
        self.assertEqual(many_classes.returncode, 0, many_classes.stderr)
        self.assertIn('"profiles": 6', many_classes.stdout)

        tiny_market = self.run_cli("market", "create", "--students", "12", "--classes", "30", "--dry-run")
        self.assertEqual(tiny_market.returncode, 0, tiny_market.stderr)
        self.assertIn('"profiles": 3', tiny_market.stdout)

    def test_market_create_accepts_custom_course_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_dir = Path(tmp) / "custom_codes_market"
            result = self.run_cli(
                "market",
                "create",
                "--output",
                str(market_dir),
                "--students",
                "12",
                "--classes",
                "30",
                "--majors",
                "3",
                "--codes",
                "20",
                "--seed",
                "123",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads((market_dir / "bidflow_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["effective_parameters"]["course_codes"], 20)

    def test_market_create_rejects_non_positive_course_codes(self) -> None:
        result = self.run_cli(
            "market",
            "create",
            "--students",
            "12",
            "--classes",
            "30",
            "--majors",
            "3",
            "--codes",
            "0",
            "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("课程代码数量必须大于 0", result.stderr + result.stdout)

    def test_market_create_audit_succeeds_for_small_market(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_dir = Path(tmp) / "audit_market"
            result = self.run_cli(
                "market",
                "create",
                "--output",
                str(market_dir),
                "--students",
                "12",
                "--classes",
                "30",
                "--majors",
                "3",
                "--seed",
                "123",
                "--audit",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_market_create_seed_is_reproducible_for_generated_files(self) -> None:
        stable_files = (
            "profiles.csv",
            "profile_requirements.csv",
            "students.csv",
            "courses.csv",
            "student_course_code_requirements.csv",
            "student_course_utility_edges.csv",
            "generation_metadata.json",
        )
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "seed_a"
            second = Path(tmp) / "seed_b"
            for market_dir in (first, second):
                result = self.run_cli(
                    "market",
                    "create",
                    "--output",
                    str(market_dir),
                    "--students",
                    "12",
                    "--classes",
                    "30",
                    "--majors",
                    "3",
                    "--seed",
                    "123",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            for filename in stable_files:
                self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes(), filename)

    def test_market_create_rejects_invalid_manual_shape(self) -> None:
        result = self.run_cli("market", "create", "--classes", "10", "--majors", "6", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("调大 --classes", result.stderr + result.stdout)

    def test_market_create_size_preset_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_dir = Path(tmp) / "tiny_market"
            result = self.run_cli("market", "create", "tiny_market", "--size", "tiny", "--output", str(market_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((market_dir / "students.csv").exists())
            self.assertTrue((market_dir / "student_course_utility_edges.csv").exists())

    def test_sensitivity_grid_has_distinct_policy_families(self) -> None:
        self.assertGreaterEqual(len(POLICY_SWEEP), 6)
        self.assertIn("cass_logit", POLICY_SWEEP)
        self.assertGreaterEqual(len(oat_sensitivity_cases()), 10)

    def test_crowding_boundary_fit_uses_m_n_and_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run_a"
            run_dir.mkdir()
            (run_dir / "decisions.csv").write_text(
                "\n".join(
                    [
                        "run_id,experiment_group,student_id,course_id,agent_type,script_policy_name,selected,bid,observed_capacity,observed_waitlist_count_final",
                        "run_a,E,S1,C1,behavioral,,true,5,2,3",
                        "run_a,E,S2,C1,behavioral,,true,3,2,3",
                        "run_a,E,S3,C1,behavioral,,true,1,2,3",
                        "run_a,E,S1,C2,behavioral,,true,1,3,1",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "allocations.csv").write_text(
                "\n".join(
                    [
                        "run_id,experiment_group,course_id,student_id,bid,admitted,cutoff_bid,tie_break_used",
                        "run_a,E,C1,S1,5,true,3,false",
                        "run_a,E,C1,S2,3,true,3,false",
                        "run_a,E,C1,S3,1,false,3,false",
                        "run_a,E,C2,S1,1,true,0,false",
                    ]
                ),
                encoding="utf-8",
            )
            observations = collect_boundary_observations([run_dir])
        by_course = {row.course_id: row for row in observations}
        self.assertEqual(by_course["C1"].m, 3)
        self.assertEqual(by_course["C1"].n, 2)
        self.assertEqual(by_course["C1"].cutoff_bid, 3.0)
        self.assertEqual(by_course["C2"].cutoff_bid, 0.0)
        summary = evaluate_models(observations, observations)
        self.assertTrue(summary)
        self.assertIn("test_mae", summary[0])

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
                "--policy",
                "cass_logit",
                "--data-dir",
                str(market_dir),
                "--output",
                str(replay_dir),
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertTrue((replay_dir / "cass_focal_backtest_metrics.json").exists())
            self.assertTrue((replay_dir / "bidflow_metadata.json").exists())
            metrics = json.loads((replay_dir / "cass_focal_backtest_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["policy"], "cass_logit")
