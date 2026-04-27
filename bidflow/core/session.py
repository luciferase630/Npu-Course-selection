from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_legacy_session(args: list[str], cwd: str | Path | None = None) -> int:
    command = [sys.executable, "-m", "src.experiments.run_single_round_mvp", *args]
    return subprocess.run(command, cwd=cwd, check=False).returncode
