from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from src.analysis.cass_focal_backtest import run_backtest


@dataclass(frozen=True)
class BackgroundSpec:
    name: str
    baseline: str
    data_dir: str


DEFAULT_BACKGROUNDS = (
    BackgroundSpec("high_ba", "outputs/runs/research_large_800x240x3_behavioral", "data/synthetic/research_large"),
    BackgroundSpec("high_mix30", "outputs/runs/research_large_s048_mix30_ba_market", "data/synthetic/research_large"),
    BackgroundSpec(
        "medium_ba",
        "outputs/runs/research_large_medium_competition_behavioral",
        "data/synthetic/research_large_medium_competition",
    ),
    BackgroundSpec(
        "sparse_ba",
        "outputs/runs/research_large_sparse_hotspots_behavioral",
        "data/synthetic/research_large_sparse_hotspots",
    ),
)
DEFAULT_FOCALS = ("S048", "S092", "S043", "S005")
POLICY_SWEEP = ("cass_v1", "cass_smooth", "cass_value", "cass_v2", "cass_frontier", "cass_logit")
SENSITIVITY_BASE_POLICY = "cass_v2"


def oat_sensitivity_cases() -> list[dict[str, object]]:
    """One-at-a-time perturbations around the CASS-v2 baseline.

    Values are intentionally symmetric and coarse. The goal is not fine tuning;
    it is to check whether the selected policy survives plausible parameter
    perturbations in the modeling-paper sense.
    """
    return [
        {"case": "base", "param": "base", "value": "", "params": {}},
        {"case": "pressure_denominator_low", "param": "pressure_denominator", "value": 0.8, "params": {"pressure_denominator": 0.8}},
        {"case": "pressure_denominator_high", "param": "pressure_denominator", "value": 1.8, "params": {"pressure_denominator": 1.8}},
        {"case": "price_penalty_low", "param": "price_penalty_balanced", "value": 1.2, "params": {"price_penalty_balanced": 1.2}},
        {"case": "price_penalty_high", "param": "price_penalty_balanced", "value": 2.4, "params": {"price_penalty_balanced": 2.4}},
        {
            "case": "optional_hot_penalty_low",
            "param": "optional_hot_penalty_balanced",
            "value": 3.0,
            "params": {"optional_hot_penalty_balanced": 3.0},
        },
        {
            "case": "optional_hot_penalty_high",
            "param": "optional_hot_penalty_balanced",
            "value": 9.0,
            "params": {"optional_hot_penalty_balanced": 9.0},
        },
        {"case": "max_single_low", "param": "max_single_bid_share", "value": 0.15, "params": {"max_single_bid_share": 0.15}},
        {"case": "max_single_high", "param": "max_single_bid_share", "value": 0.25, "params": {"max_single_bid_share": 0.25}},
        {
            "case": "required_base_low",
            "param": "required_selection_base",
            "value": 120.0,
            "params": {"required_selection_base": 120.0},
        },
        {
            "case": "required_base_high",
            "param": "required_selection_base",
            "value": 170.0,
            "params": {"required_selection_base": 170.0},
        },
    ]


def run_policy_sensitivity(
    *,
    output_dir: str | Path = "outputs/runs/cass_sensitivity",
    detail_table: str | Path = "outputs/tables/cass_sensitivity_detail.csv",
    policy_summary_table: str | Path = "outputs/tables/cass_sensitivity_policy_summary.csv",
    oat_summary_table: str | Path = "outputs/tables/cass_sensitivity_oat_summary.csv",
    config_path: str | Path = "configs/simple_model.yaml",
    backgrounds: tuple[BackgroundSpec, ...] = DEFAULT_BACKGROUNDS,
    focals: tuple[str, ...] = DEFAULT_FOCALS,
    quick: bool = False,
) -> dict[str, object]:
    if quick:
        backgrounds = backgrounds[:1]
        focals = focals[:1]
    output_root = Path(output_dir)
    rows: list[dict[str, object]] = []

    for policy in POLICY_SWEEP:
        for background in backgrounds:
            for focal in focals:
                metrics = _run_one(
                    output_root,
                    config_path,
                    background,
                    focal,
                    policy,
                    case_group="policy",
                    case_name=policy,
                    params={},
                )
                rows.append(_row_from_metrics(metrics, background, focal, "policy", policy, "policy", "", {}))

    for case in oat_sensitivity_cases():
        case_name = str(case["case"])
        params = dict(case["params"])  # type: ignore[arg-type]
        for background in backgrounds:
            for focal in focals:
                metrics = _run_one(
                    output_root,
                    config_path,
                    background,
                    focal,
                    SENSITIVITY_BASE_POLICY,
                    case_group="oat",
                    case_name=case_name,
                    params=params,
                )
                rows.append(
                    _row_from_metrics(
                        metrics,
                        background,
                        focal,
                        "oat",
                        case_name,
                        str(case["param"]),
                        case["value"],
                        params,
                    )
                )

    write_csv(Path(detail_table), rows)
    policy_summary = summarize(rows, group_field="case_name", filter_group="policy")
    oat_summary = summarize(rows, group_field="case_name", filter_group="oat")
    write_csv(Path(policy_summary_table), policy_summary)
    write_csv(Path(oat_summary_table), oat_summary)
    return {
        "detail_table": str(detail_table),
        "policy_summary_table": str(policy_summary_table),
        "oat_summary_table": str(oat_summary_table),
        "row_count": len(rows),
        "policy_summary": policy_summary,
        "oat_summary": oat_summary,
    }


def _run_one(
    output_root: Path,
    config_path: str | Path,
    background: BackgroundSpec,
    focal: str,
    policy: str,
    *,
    case_group: str,
    case_name: str,
    params: dict[str, float],
) -> dict[str, object]:
    run_output = output_root / case_group / case_name / background.name / focal
    return run_backtest(
        config_path=config_path,
        baseline_dir=background.baseline,
        focal_student_id=focal,
        output_dir=run_output,
        data_dir=background.data_dir,
        cass_policy=policy,
        cass_params=params,
        results_table=output_root / "cass_sensitivity_backtest_results.csv",
        bean_table=output_root / "cass_sensitivity_bean_diagnostics.csv",
    )


def _row_from_metrics(
    metrics: dict[str, object],
    background: BackgroundSpec,
    focal: str,
    case_group: str,
    case_name: str,
    param: str,
    value: object,
    params: dict[str, float],
) -> dict[str, object]:
    return {
        "case_group": case_group,
        "case_name": case_name,
        "param": param,
        "value": value,
        "params_json": json.dumps(params, sort_keys=True),
        "background": background.name,
        "focal_student_id": focal,
        "policy": metrics.get("policy"),
        "baseline_course_outcome_utility": metrics.get("baseline_course_outcome_utility"),
        "cass_course_outcome_utility": metrics.get("cass_course_outcome_utility"),
        "delta_course_outcome_utility": metrics.get("delta_course_outcome_utility"),
        "cass_selected_course_count": metrics.get("cass_selected_course_count"),
        "cass_admitted_course_count": metrics.get("cass_admitted_course_count"),
        "cass_beans_paid": metrics.get("cass_beans_paid"),
        "cass_rejected_wasted_beans": metrics.get("cass_rejected_wasted_beans"),
        "cass_admitted_excess_bid_total": metrics.get("cass_admitted_excess_bid_total"),
        "cass_posthoc_non_marginal_beans": metrics.get("cass_posthoc_non_marginal_beans"),
        "cass_bid_concentration_hhi": metrics.get("cass_bid_concentration_hhi"),
        "utility_win": metrics.get("utility_win"),
    }


def summarize(rows: list[dict[str, object]], *, group_field: str, filter_group: str) -> list[dict[str, object]]:
    groups = sorted({str(row[group_field]) for row in rows if row["case_group"] == filter_group})
    summary = []
    for group in groups:
        items = [row for row in rows if row["case_group"] == filter_group and str(row[group_field]) == group]
        utilities = [_float(row["cass_course_outcome_utility"]) for row in items]
        deltas = [_float(row["delta_course_outcome_utility"]) for row in items]
        beans = [_float(row["cass_beans_paid"]) for row in items]
        waste = [_float(row["cass_rejected_wasted_beans"]) for row in items]
        non_marginal = [_float(row["cass_posthoc_non_marginal_beans"]) for row in items]
        hhi = [_float(row["cass_bid_concentration_hhi"]) for row in items]
        robust_score = mean(deltas) - 0.25 * pstdev(deltas) - 2.0 * mean(waste) - 0.5 * mean(non_marginal)
        summary.append(
            {
                group_field: group,
                "n": len(items),
                "avg_utility": round(mean(utilities), 6),
                "std_utility": round(pstdev(utilities), 6),
                "min_utility": round(min(utilities), 6),
                "max_utility": round(max(utilities), 6),
                "utility_range_pct": round((max(utilities) - min(utilities)) / max(1.0, abs(mean(utilities))), 6),
                "avg_delta_utility": round(mean(deltas), 6),
                "std_delta_utility": round(pstdev(deltas), 6),
                "avg_beans_paid": round(mean(beans), 6),
                "avg_rejected_wasted_beans": round(mean(waste), 6),
                "avg_posthoc_non_marginal_beans": round(mean(non_marginal), 6),
                "avg_bid_concentration_hhi": round(mean(hhi), 8),
                "robust_score": round(robust_score, 6),
            }
        )
    return sorted(summary, key=lambda row: float(row["robust_score"]), reverse=True)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _float(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan
    if math.isnan(number):
        return 0.0
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CASS policy and hyperparameter sensitivity analysis.")
    parser.add_argument("--output-dir", default="outputs/runs/cass_sensitivity")
    parser.add_argument("--detail-table", default="outputs/tables/cass_sensitivity_detail.csv")
    parser.add_argument("--policy-summary-table", default="outputs/tables/cass_sensitivity_policy_summary.csv")
    parser.add_argument("--oat-summary-table", default="outputs/tables/cass_sensitivity_oat_summary.csv")
    parser.add_argument("--config", default="configs/simple_model.yaml")
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_policy_sensitivity(
        output_dir=args.output_dir,
        detail_table=args.detail_table,
        policy_summary_table=args.policy_summary_table,
        oat_summary_table=args.oat_summary_table,
        config_path=args.config,
        quick=args.quick,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
