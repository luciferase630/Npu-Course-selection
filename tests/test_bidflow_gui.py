from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bidflow.gui.server import create_server


class BidFlowGuiTests(unittest.TestCase):
    def test_gui_help_is_available(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "bidflow", "gui", "--help"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--host", result.stdout)
        self.assertIn("--port", result.stdout)
        self.assertIn("--no-browser", result.stdout)

    def test_static_home_and_health_endpoint(self) -> None:
        with running_server() as base_url:
            html = get_text(base_url + "/")
            self.assertIn("BidFlow 沙盒", html)
            health = get_json(base_url + "/api/health")
            self.assertTrue(health["ok"])
            self.assertIn("cwd", health)
            agents = get_json(base_url + "/api/agents")
            self.assertTrue(agents["ok"])
            self.assertIn("cass", {agent["name"] for agent in agents["agents"]})

    def test_market_create_dry_run_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, running_server() as base_url:
            market_dir = Path(tmp) / "dry_market"
            created = post_json(
                base_url + "/api/markets/create",
                {
                    "output": str(market_dir),
                    "students": 12,
                    "classes": 30,
                    "majors": 3,
                    "dry_run": True,
                },
            )
            self.assertTrue(created["ok"])
            job = wait_for_job(base_url, created["job_id"])
            self.assertEqual(job["status"], "succeeded", job)
            self.assertIn("dry-run", job["stdout"])
            self.assertFalse(market_dir.exists())

    def test_file_preview_rejects_secret_like_paths(self) -> None:
        with running_server() as base_url:
            with self.assertRaises(HTTPError) as raised:
                post_json(base_url + "/api/files/preview", {"path": ".env.local"})
            self.assertEqual(raised.exception.code, 400)

    def test_gui_api_runs_minimal_market_session_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, running_server() as base_url:
            root = Path(tmp)
            market_dir = root / "market"
            run_dir = root / "run"
            replay_dir = root / "replay"
            run_id = "gui_unit_behavioral"
            legacy_dir = Path("outputs/runs") / run_id
            try:
                create = post_json(
                    base_url + "/api/markets/create",
                    {
                        "output": str(market_dir),
                        "students": 12,
                        "classes": 30,
                        "majors": 3,
                        "seed": 123,
                    },
                )
                self.assertEqual(wait_for_job(base_url, create["job_id"])["status"], "succeeded")
                self.assertTrue((market_dir / "students.csv").exists())

                validate = post_json(base_url + "/api/markets/validate", {"market": str(market_dir)})
                self.assertTrue(validate["ok"], validate)
                self.assertEqual(validate["json"]["student_count"], 12)

                session = post_json(
                    base_url + "/api/sessions/run",
                    {
                        "market": str(market_dir),
                        "population": "background=behavioral",
                        "output": str(run_dir),
                        "run_id": run_id,
                        "time_points": 3,
                        "seed": 123,
                    },
                )
                self.assertEqual(wait_for_job(base_url, session["job_id"])["status"], "succeeded")
                self.assertTrue((run_dir / "metrics.json").exists())

                replay = post_json(
                    base_url + "/api/replays/run",
                    {
                        "baseline": str(run_dir),
                        "focal": "S001",
                        "agent": "cass",
                        "policy": "cass_v2",
                        "data_dir": str(market_dir),
                        "output": str(replay_dir),
                    },
                )
                self.assertEqual(wait_for_job(base_url, replay["job_id"])["status"], "succeeded")
                self.assertTrue((replay_dir / "cass_focal_backtest_metrics.json").exists())
            finally:
                if legacy_dir.exists():
                    import shutil

                    shutil.rmtree(legacy_dir)


class running_server:
    def __enter__(self) -> str:
        self.server = create_server(port=0)
        host, port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def get_text(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def get_json(url: str) -> dict:
    return json.loads(get_text(url))


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_job(base_url: str, job_id: str) -> dict:
    for _attempt in range(60):
        job = get_json(base_url + f"/api/jobs/{job_id}")["job"]
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.25)
    raise AssertionError(f"job did not finish: {job_id}")
