from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import webbrowser
import csv
import ipaddress
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from bidflow.agents.registry import list_agents
from bidflow.cli.agent import _load_persisted_agents
from bidflow.cli.market import SCENARIOS, SIZE_PRESETS
from src.data_generation.scenarios import load_generation_scenario


STATIC_ROOT = Path(__file__).with_name("static")
REPO_ROOT = Path.cwd().resolve()
MAX_PREVIEW_BYTES = 256_000
LLM_ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL")


@dataclass
class Job:
    job_id: str
    command: list[str]
    cwd: str
    status: str = "queued"
    started_at: float | None = None
    ended_at: float | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    process: subprocess.Popen[str] | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "returncode": self.returncode,
            "stdout": self.stdout[-20_000:],
            "stderr": self.stderr[-20_000:],
            "error": self.error,
        }


class JobManager:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, command: list[str]) -> Job:
        job = Job(job_id="job_" + uuid4().hex[:12], command=command, cwd=str(self.cwd))
        with self._lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [job.public() for job in sorted(jobs, key=lambda item: item.job_id, reverse=True)]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.process and job.status == "running":
            job.process.terminate()
            job.status = "cancelled"
            job.ended_at = time.time()
            return True
        if job.status == "queued":
            job.status = "cancelled"
            job.ended_at = time.time()
            return True
        return False

    def _run(self, job: Job) -> None:
        if job.status == "cancelled":
            return
        job.status = "running"
        job.started_at = time.time()
        try:
            process = subprocess.Popen(
                job.command,
                cwd=self.cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
            )
            job.process = process
            stdout, stderr = process.communicate()
            job.stdout = stdout or ""
            job.stderr = stderr or ""
            job.returncode = process.returncode
            if job.status != "cancelled":
                job.status = "succeeded" if process.returncode == 0 else "failed"
        except Exception as exc:  # pragma: no cover - defensive job guard
            job.error = str(exc)
            job.status = "failed"
        finally:
            job.ended_at = time.time()
            job.process = None


class GuiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], cwd: Path) -> None:
        super().__init__(server_address, GuiRequestHandler)
        self.cwd = cwd.resolve()
        self.jobs = JobManager(self.cwd)


class GuiRequestHandler(BaseHTTPRequestHandler):
    server: GuiServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/health":
            self._json(
                {
                    "ok": True,
                    "bidflow_version": "0.1.0",
                    "cwd": str(self.server.cwd),
                    "python": sys.version.split()[0],
                    "llm_env": _llm_env_status(self.server.cwd),
                }
            )
            return
        if path == "/api/llm/config":
            if not _is_loopback_host(str(self.client_address[0])):
                self._json_error("LLM configuration is only available from localhost", status=403)
                return
            self._json(_llm_config(self.server.cwd))
            return
        if path == "/api/agents":
            _load_persisted_agents()
            self._json({"ok": True, "agents": [_agent_row(row) for row in list_agents()]})
            return
        if path == "/api/markets/scenarios":
            scenarios = []
            for name, scenario_path in SCENARIOS.items():
                scenario = load_generation_scenario(scenario_path)
                scenarios.append(
                    {
                        "name": name,
                        "path": str(scenario_path),
                        "students": scenario.n_students,
                        "sections": scenario.n_course_sections,
                        "profiles": scenario.n_profiles,
                        "course_codes": scenario.n_course_codes,
                        "competition_profile": scenario.competition_profile,
                    }
                )
            self._json({"ok": True, "scenarios": scenarios, "sizes": SIZE_PRESETS})
            return
        if path == "/api/jobs":
            self._json({"ok": True, "jobs": self.server.jobs.list()})
            return
        if path.startswith("/api/jobs/"):
            if path.endswith("/cancel"):
                self._json_error("use POST /api/jobs/<job_id>/cancel to cancel jobs", status=405)
                return
            job_id = path.rsplit("/", 1)[-1]
            job = self.server.jobs.get(job_id)
            if job is None:
                self._json_error(f"unknown job: {job_id}", status=404)
            else:
                self._json({"ok": True, "job": job.public()})
            return
        self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._body()
            if path == "/api/agents/init":
                self._start(["agent", "init", str(payload.get("name", "")).strip(), "--template", str(payload.get("template", "minimal"))])
                return
            if path == "/api/agents/register":
                self._start(["agent", "register", str(payload.get("target", "")).strip()])
                return
            if path == "/api/agents/info":
                self._run_sync(["agent", "info", str(payload.get("name", "")).strip()])
                return
            if path == "/api/markets/create":
                self._start(_market_create_args(payload))
                return
            if path == "/api/markets/generate":
                self._start(_market_generate_args(payload))
                return
            if path == "/api/markets/validate":
                self._run_sync(["market", "validate", str(payload.get("market", "")).strip()])
                return
            if path == "/api/markets/info":
                self._run_sync(["market", "info", str(payload.get("market", "")).strip()])
                return
            if path == "/api/markets/course":
                self._run_sync(["market", "course", str(payload.get("market", "")).strip(), "--course-id", str(payload.get("course_id", "")).strip()])
                return
            if path == "/api/sessions/run":
                self._start(_session_args(payload))
                return
            if path == "/api/replays/run":
                self._start(_replay_args(payload))
                return
            if path == "/api/analysis/summary":
                self._run_sync(["analyze", "summary", "--runs", *_list(payload.get("runs"))])
                return
            if path == "/api/analysis/beans":
                self._run_sync(["analyze", "beans", "--runs", *_list(payload.get("runs"))])
                return
            if path == "/api/analysis/compare":
                self._run_sync(["analyze", "compare", "--runs", *_list(payload.get("runs"))])
                return
            if path == "/api/analysis/focal":
                self._run_sync(["analyze", "focal", "--run", str(payload.get("run", "")).strip(), "--student-id", str(payload.get("student_id", "")).strip()])
                return
            if path == "/api/analysis/cass-sensitivity":
                self._start(_cass_sensitivity_args(payload))
                return
            if path == "/api/analysis/crowding-boundary":
                self._start(_crowding_boundary_args(payload))
                return
            if path == "/api/analysis/strategy-visual":
                self._json({"ok": True, "visual": _strategy_visual(payload)})
                return
            if path == "/api/jobs/cancel":
                job_id = str(payload.get("job_id", "")).strip()
                self._json({"ok": self.server.jobs.cancel(job_id)})
                return
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = path.split("/")[-2]
                self._json({"ok": self.server.jobs.cancel(job_id)})
                return
            if path == "/api/files/preview":
                self._json(_preview_file(payload, self.server.cwd))
                return
            if path == "/api/llm/config":
                if not _is_loopback_host(str(self.client_address[0])):
                    self._json_error("LLM configuration is only available from localhost", status=403)
                    return
                self._json(_save_llm_config(payload, self.server.cwd))
                return
            self._json_error(f"unknown endpoint: {path}", status=404)
        except ValueError as exc:
            self._json_error(str(exc), status=400)
        except Exception as exc:  # pragma: no cover - HTTP safety net
            self._json_error(str(exc), status=500)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _start(self, args: list[str]) -> None:
        command = [sys.executable, "-m", "bidflow", *[item for item in args if item != ""]]
        job = self.server.jobs.start(command)
        self._json({"ok": True, "job_id": job.job_id, "status": job.status})

    def _run_sync(self, args: list[str]) -> None:
        command = [sys.executable, "-m", "bidflow", *[item for item in args if item != ""]]
        result = subprocess.run(
            command,
            cwd=self.server.cwd,
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        self._json(
            {
                "ok": result.returncode == 0,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "json": _try_json(result.stdout),
            },
            status=200 if result.returncode == 0 else 400,
        )

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_error(self, message: str, status: int = 400, details: dict[str, Any] | None = None) -> None:
        self._json({"ok": False, "error": message, "details": details or {}}, status=status)

    def _static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        relative = unquote(path).lstrip("/")
        target = (STATIC_ROOT / relative).resolve()
        if not _is_relative_to(target, STATIC_ROOT.resolve()) or not target.exists() or target.is_dir():
            self.send_error(404)
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = GuiServer((host, port), REPO_ROOT)
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}"
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("Warning: BidFlow GUI is bound outside localhost. Do not expose secrets or private outputs.")
    print(f"BidFlow GUI running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping BidFlow GUI")
    finally:
        server.server_close()


def create_server(host: str = "127.0.0.1", port: int = 0, cwd: Path | None = None) -> GuiServer:
    return GuiServer((host, port), cwd or REPO_ROOT)


def _agent_row(row: Any) -> dict[str, str]:
    return {
        "name": str(row.name),
        "kind": str(row.kind),
        "description": str(row.description),
        "source": str(row.source),
    }


def _market_create_args(payload: dict[str, Any]) -> list[str]:
    args = ["market", "create"]
    if payload.get("name"):
        args.append(str(payload["name"]))
    _append_value(args, "--output", payload.get("output"))
    _append_value(args, "--size", payload.get("size"))
    _append_value(args, "--students", payload.get("students"))
    _append_value(args, "--classes", payload.get("classes") or payload.get("sections"))
    _append_value(args, "--majors", payload.get("majors") or payload.get("profiles"))
    _append_value(args, "--codes", payload.get("codes") or payload.get("course_codes"))
    _append_value(args, "--competition-profile", payload.get("competition_profile"))
    _append_value(args, "--seed", payload.get("seed"))
    _append_value(args, "--config", payload.get("config"))
    _append_bool(args, "--dry-run", payload.get("dry_run"))
    _append_bool(args, "--audit", payload.get("audit"))
    return args


def _market_generate_args(payload: dict[str, Any]) -> list[str]:
    args = ["market", "generate", "--scenario", str(payload.get("scenario", "")).strip()]
    _append_value(args, "--output", payload.get("output"))
    _append_value(args, "--seed", payload.get("seed"))
    _append_value(args, "--n-students", payload.get("n_students"))
    _append_value(args, "--n-course-sections", payload.get("n_course_sections"))
    _append_value(args, "--n-profiles", payload.get("n_profiles"))
    _append_value(args, "--n-course-codes", payload.get("n_course_codes"))
    _append_value(args, "--competition-profile", payload.get("competition_profile"))
    _append_value(args, "--config", payload.get("config"))
    return args


def _session_args(payload: dict[str, Any]) -> list[str]:
    args = ["session", "run", "--market", str(payload.get("market", "")).strip()]
    _append_value(args, "--population", payload.get("population"))
    _append_value(args, "--population-file", payload.get("population_file"))
    _append_value(args, "--output", payload.get("output"))
    _append_value(args, "--run-id", payload.get("run_id"))
    _append_value(args, "--time-points", payload.get("time_points"))
    _append_value(args, "--seed", payload.get("seed"))
    _append_value(args, "--config", payload.get("config"))
    _append_value(args, "--experiment-config", payload.get("experiment_config"))
    _append_value(args, "--experiment-group", payload.get("experiment_group"))
    _append_value(args, "--interaction-mode", payload.get("interaction_mode"))
    _append_value(args, "--focal-agent", payload.get("focal_agent"))
    _append_value(args, "--focal-student-id", payload.get("focal_student_id"))
    _append_value(args, "--focal-student-ids", payload.get("focal_student_ids"))
    _append_value(args, "--focal-student-share", payload.get("focal_student_share"))
    _append_value(args, "--focal-student-count", payload.get("focal_student_count"))
    _append_bool(args, "--formula-prompt", payload.get("formula_prompt"))
    _append_value(args, "--background-formula-share", payload.get("background_formula_share"))
    _append_value(args, "--cass-policy", payload.get("cass_policy"))
    return args


def _replay_args(payload: dict[str, Any]) -> list[str]:
    args = [
        "replay",
        "run",
        "--baseline",
        str(payload.get("baseline", "")).strip(),
        "--focal",
        str(payload.get("focal", "")).strip(),
        "--output",
        str(payload.get("output", "")).strip(),
    ]
    _append_value(args, "--agent", payload.get("agent"))
    _append_value(args, "--agents", payload.get("agents"))
    _append_value(args, "--data-dir", payload.get("data_dir"))
    _append_value(args, "--config", payload.get("config"))
    _append_bool(args, "--formula-prompt", payload.get("formula_prompt"))
    _append_value(args, "--formula-policy", payload.get("formula_policy"))
    _append_value(args, "--formula-prompt-policy", payload.get("formula_prompt_policy"))
    _append_value(args, "--policy", payload.get("policy"))
    for param in _list(payload.get("params")):
        args.extend(["--param", param])
    return args


def _cass_sensitivity_args(payload: dict[str, Any]) -> list[str]:
    args = ["analyze", "cass-sensitivity"]
    _append_value(args, "--output-dir", payload.get("output_dir"))
    _append_value(args, "--detail-table", payload.get("detail_table"))
    _append_value(args, "--policy-summary-table", payload.get("policy_summary_table"))
    _append_value(args, "--oat-summary-table", payload.get("oat_summary_table"))
    _append_value(args, "--config", payload.get("config"))
    _append_bool(args, "--quick", payload.get("quick"))
    return args


def _crowding_boundary_args(payload: dict[str, Any]) -> list[str]:
    args = ["analyze", "crowding-boundary"]
    for root in _list(payload.get("run_root")):
        args.extend(["--run-root", root])
    _append_bool(args, "--no-sibling", payload.get("no_sibling"))
    _append_bool(args, "--quick", payload.get("quick"))
    _append_value(args, "--detail-table", payload.get("detail_table"))
    _append_value(args, "--summary-table", payload.get("summary_table"))
    _append_value(args, "--bin-table", payload.get("bin_table"))
    _append_value(args, "--report", payload.get("report"))
    _append_value(args, "--formula-config", payload.get("formula_config"))
    return args


def _preview_file(payload: dict[str, Any], cwd: Path) -> dict[str, Any]:
    raw_path = str(payload.get("path", "")).strip()
    if not raw_path:
        raise ValueError("path is required")
    path = Path(raw_path)
    if not path.is_absolute():
        path = cwd / path
    path = path.resolve()
    _guard_preview_path(path, cwd)
    if not path.exists() or not path.is_file():
        raise ValueError(f"file not found: {path}")
    data = path.read_bytes()[:MAX_PREVIEW_BYTES]
    text = data.decode("utf-8-sig", errors="replace")
    return {"ok": True, "path": str(path), "truncated": path.stat().st_size > MAX_PREVIEW_BYTES, "text": text}


def _llm_config(cwd: Path) -> dict[str, Any]:
    status = _llm_env_status(cwd)
    return {
        "ok": True,
        "env_path": str(_llm_env_path(cwd)),
        "api_key_present": status["OPENAI_API_KEY"],
        "model_present": status["OPENAI_MODEL"],
        "base_url_present": status["OPENAI_BASE_URL"],
        "model": os.environ.get("OPENAI_MODEL", ""),
        "base_url": os.environ.get("OPENAI_BASE_URL", ""),
    }


def _save_llm_config(payload: dict[str, Any], cwd: Path) -> dict[str, Any]:
    api_key = _clean_env_value(payload.get("api_key", ""))
    model = _clean_env_value(payload.get("model", ""))
    base_url = _clean_env_value(payload.get("base_url", ""))
    clear_key = _truthy(payload.get("clear_key"))
    if not model:
        raise ValueError("OPENAI_MODEL is required")
    updates = {"OPENAI_MODEL": model}
    deletions = {"OPENAI_BASE_URL"}
    if base_url:
        updates["OPENAI_BASE_URL"] = base_url
        deletions.discard("OPENAI_BASE_URL")
    if clear_key:
        deletions.add("OPENAI_API_KEY")
    elif api_key:
        updates["OPENAI_API_KEY"] = api_key
        deletions.discard("OPENAI_API_KEY")
    path = _llm_env_path(cwd)
    _write_env_file(path, updates, deletions)
    for key, value in updates.items():
        os.environ[key] = value
    for key in deletions:
        os.environ.pop(key, None)
    return _llm_config(cwd) | {"message": ".env.local updated"}


def _llm_env_status(cwd: Path) -> dict[str, bool]:
    _load_env_file(_llm_env_path(cwd))
    return {key: bool(os.environ.get(key)) for key in LLM_ENV_KEYS}


def _llm_env_path(cwd: Path) -> Path:
    return cwd.resolve() / ".env.local"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for key, value in _read_env_values(path).items():
        if key not in os.environ:
            os.environ[key] = value


def _read_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _write_env_file(path: Path, updates: dict[str, str], deletions: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    written: set[str] = set()
    output: list[str] = []
    for raw_line in lines:
        key = _env_line_key(raw_line)
        if key in deletions:
            continue
        if key in updates:
            output.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            output.append(raw_line)
    for key in LLM_ENV_KEYS:
        if key in updates and key not in written:
            output.append(f"{key}={updates[key]}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _env_line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key or None


def _clean_env_value(value: Any) -> str:
    cleaned = str(value or "").strip()
    if "\n" in cleaned or "\r" in cleaned:
        raise ValueError("LLM configuration values must be single-line strings")
    return cleaned


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"1", "true", "yes", "on"}


def _strategy_visual(payload: dict[str, Any]) -> dict[str, Any]:
    raw_run = str(payload.get("run", "")).strip()
    if not raw_run:
        raise ValueError("run is required")
    run = Path(raw_run)
    if not run.is_absolute():
        run = REPO_ROOT / run
    run = run.resolve()
    decisions_path = run / "decisions.csv"
    if not decisions_path.exists():
        raise ValueError(f"missing decisions.csv under {run}")
    decisions = _read_csv_rows(decisions_path)
    allocations = _read_csv_rows(run / "allocations.csv") if (run / "allocations.csv").exists() else []
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8")) if (run / "metrics.json").exists() else {}
    student_id = str(payload.get("student_id", "")).strip()

    student_agent: dict[str, str] = {}
    selected_by_agent: Counter[str] = Counter()
    bid_bins: Counter[str] = Counter()
    course_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in decisions:
        agent = str(row.get("agent_type", ""))
        sid = str(row.get("student_id", ""))
        if sid and agent:
            student_agent[sid] = agent
        if str(row.get("selected", "")).lower() != "true":
            continue
        bid = _to_int(row.get("bid"))
        selected_by_agent[agent] += 1
        bid_bins[_bid_bin(bid)] += 1
        course_rows[str(row.get("course_id", ""))].append(row)

    admitted_by_key = {
        (str(row.get("student_id", "")), str(row.get("course_id", ""))): str(row.get("admitted", "")).lower() == "true"
        for row in allocations
    }
    top_courses = []
    for course_id, rows in course_rows.items():
        bids = [_to_int(row.get("bid")) for row in rows]
        sample = rows[0]
        capacity = _to_int(sample.get("observed_capacity"))
        waitlist = _to_int(sample.get("observed_waitlist_count_final"))
        top_courses.append(
            {
                "course_id": course_id,
                "selected_count": len(rows),
                "capacity": capacity,
                "waitlist": waitlist,
                "crowding_ratio": round(waitlist / max(1, capacity), 4),
                "average_bid": round(sum(bids) / max(1, len(bids)), 3),
                "max_bid": max(bids) if bids else 0,
            }
        )
    top_courses.sort(key=lambda item: (item["crowding_ratio"], item["waitlist"], item["average_bid"]), reverse=True)

    focal_rows = []
    if student_id:
        for row in decisions:
            if str(row.get("student_id", "")) != student_id or str(row.get("selected", "")).lower() != "true":
                continue
            focal_rows.append(
                {
                    "course_id": row.get("course_id", ""),
                    "bid": _to_int(row.get("bid")),
                    "capacity": _to_int(row.get("observed_capacity")),
                    "waitlist": _to_int(row.get("observed_waitlist_count_final")),
                    "admitted": admitted_by_key.get((student_id, str(row.get("course_id", ""))), None),
                }
            )
        focal_rows.sort(key=lambda item: int(item["bid"]), reverse=True)

    return {
        "run": str(run),
        "agent_type_counts": dict(sorted(Counter(student_agent.values()).items())),
        "selected_course_count_by_agent": dict(sorted(selected_by_agent.items())),
        "bid_histogram": {label: bid_bins.get(label, 0) for label in ["1", "2-5", "6-10", "11-20", "21-40", "41+"]},
        "top_crowded_courses": top_courses[:12],
        "focal_student_id": student_id,
        "focal_selected_courses": focal_rows,
        "metrics": {
            key: metrics.get(key, "")
            for key in [
                "admission_rate",
                "average_selected_courses",
                "average_course_outcome_utility",
                "average_rejected_wasted_beans",
                "average_admitted_excess_bid_total",
                "focal_student_count",
                "agent_type_counts",
            ]
        },
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _bid_bin(bid: int) -> str:
    if bid <= 1:
        return "1"
    if bid <= 5:
        return "2-5"
    if bid <= 10:
        return "6-10"
    if bid <= 20:
        return "11-20"
    if bid <= 40:
        return "21-40"
    return "41+"


def _guard_preview_path(path: Path, cwd: Path) -> None:
    lowered = {part.lower() for part in path.parts}
    forbidden = {".git", ".ssh"}
    if lowered & forbidden:
        raise ValueError("refusing to preview private repository or SSH files")
    name = path.name.lower()
    default_private_key_name = "id_" + "ed25519"
    if name.startswith(".env") or default_private_key_name in name or "private_key" in name:
        raise ValueError("refusing to preview secret-like files")
    allowed_roots = [cwd.resolve(), Path(os.environ.get("TEMP", "")).resolve(), Path(os.environ.get("TMP", "")).resolve()]
    if not any(_is_relative_to(path, root) for root in allowed_roots if str(root) != "."):
        raise ValueError("path is outside allowed BidFlow preview roots")


def _append_value(args: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    args.extend([flag, str(value)])


def _append_bool(args: list[str], flag: str, value: Any) -> None:
    if value is True or str(value).lower() in {"1", "true", "yes", "on"}:
        args.append(flag)


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).replace("\n", ",").split(",") if item.strip()]


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"
