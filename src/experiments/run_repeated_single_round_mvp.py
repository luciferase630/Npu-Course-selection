from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from src.data_generation.io import load_config, write_csv_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated single-round all-pay MVP experiments.")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--agent", default="behavioral", choices=["behavioral", "mock", "openai"])
    parser.add_argument("--experiment-group", default="E0_llm_natural_baseline")
    parser.add_argument("--script-policy", default="utility_weighted")
    parser.add_argument("--n-repetitions", type=int, default=None)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    n_repetitions = args.n_repetitions or int(config.get("repeated_experiments", {}).get("n_repetitions", 1))
    output_root = Path(config.get("outputs", {}).get("run_root", "outputs/runs"))
    summary_rows = []

    for repetition_index in range(n_repetitions):
        run_id = f"{args.run_prefix}_{repetition_index + 1:03d}"
        command = [
            sys.executable,
            "-m",
            "src.experiments.run_single_round_mvp",
            "--config",
            args.config,
            "--run-id",
            run_id,
            "--agent",
            args.agent,
            "--experiment-group",
            args.experiment_group,
            "--script-policy",
            args.script_policy,
            "--seed-offset",
            str(repetition_index),
        ]
        if args.data_dir:
            command.extend(["--data-dir", args.data_dir])
        subprocess.run(command, check=True)
        metrics_path = output_root / run_id / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        summary_rows.append({"repetition_id": repetition_index + 1, **metrics})

    summary_path = output_root / f"{args.run_prefix}_summary.csv"
    fieldnames = sorted({key for row in summary_rows for key in row})
    write_csv_rows(summary_path, fieldnames, summary_rows)
    print(f"Repeated run summary: {summary_path.resolve()}")


if __name__ == "__main__":
    main()
