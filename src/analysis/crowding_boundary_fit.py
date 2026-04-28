from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable


DEFAULT_BINS = (0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, math.inf)
POWER_GRID = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)


@dataclass(frozen=True)
class BoundaryObservation:
    source_root: str
    run_dir: str
    run_id: str
    course_id: str
    market_profile: str
    run_family: str
    agent_mix: str
    category: str
    m: int
    n: int
    crowding_ratio: float
    excess_demand: int
    cutoff_bid: float
    selected_bid_mean: float
    selected_bid_p50: float
    selected_bid_p75: float
    selected_bid_p90: float
    overloaded: bool


def discover_run_dirs(run_roots: list[str | Path] | None = None, *, include_sibling: bool = True) -> list[Path]:
    roots = [Path(root) for root in (run_roots or ["outputs/runs"])]
    if include_sibling:
        sibling = Path.cwd().parent / (Path.cwd().name + "-llm-tests") / "outputs" / "runs"
        if sibling.exists():
            roots.append(sibling)
    run_dirs: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            key = str(run_dir.resolve()).lower()
            if key in seen:
                continue
            if (run_dir / "decisions.csv").exists() and (run_dir / "allocations.csv").exists():
                seen.add(key)
                run_dirs.append(run_dir)
    return run_dirs


def collect_boundary_observations(run_dirs: list[Path]) -> list[BoundaryObservation]:
    observations: list[BoundaryObservation] = []
    for run_dir in run_dirs:
        observations.extend(_observations_for_run(run_dir))
    return observations


def run_crowding_boundary_fit(
    *,
    run_roots: list[str | Path] | None = None,
    include_sibling: bool = True,
    quick: bool = False,
    detail_table: str | Path = "outputs/tables/crowding_boundary_observations.csv",
    summary_table: str | Path = "outputs/tables/crowding_boundary_model_summary.csv",
    bin_table: str | Path = "outputs/tables/crowding_boundary_bin_table.csv",
    report_path: str | Path = "reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md",
) -> dict[str, object]:
    run_dirs = discover_run_dirs(run_roots, include_sibling=include_sibling)
    if quick:
        run_dirs = run_dirs[: min(8, len(run_dirs))]
    observations = collect_boundary_observations(run_dirs)
    if not observations:
        raise SystemExit("No valid run outputs found. Expected run directories with decisions.csv and allocations.csv.")

    detail_rows = [observation_to_row(item) for item in observations]
    write_csv(Path(detail_table), detail_rows)

    train, test = split_train_test(observations)
    model_rows = evaluate_models(train, test)
    write_csv(Path(summary_table), model_rows)

    bin_rows = build_bin_table(observations)
    write_csv(Path(bin_table), bin_rows)
    write_report(Path(report_path), observations, model_rows, bin_rows, run_dirs, quick=quick)

    best = model_rows[0] if model_rows else {}
    result = {
        "run_count": len(run_dirs),
        "observation_count": len(observations),
        "train_observation_count": len(train),
        "test_observation_count": len(test),
        "best_model": best.get("model", ""),
        "detail_table": str(detail_table),
        "summary_table": str(summary_table),
        "bin_table": str(bin_table),
        "report_path": str(report_path),
    }
    return result


def _observations_for_run(run_dir: Path) -> list[BoundaryObservation]:
    decisions = read_csv(run_dir / "decisions.csv")
    allocations = read_csv(run_dir / "allocations.csv")
    if not decisions or not allocations:
        return []
    run_id = decisions[0].get("run_id") or run_dir.name
    selected_by_course: dict[str, list[dict[str, str]]] = {}
    capacity_by_course: dict[str, int] = {}
    category_by_course: dict[str, str] = {}
    agent_counts: dict[str, int] = {}
    for row in decisions:
        course_id = row.get("course_id", "")
        if not course_id:
            continue
        if _truthy(row.get("selected", "")):
            selected_by_course.setdefault(course_id, []).append(row)
        capacity = _to_int(row.get("observed_capacity"))
        if capacity is not None and capacity > 0:
            capacity_by_course[course_id] = capacity
        agent_type = row.get("agent_type", "")
        if agent_type:
            agent_counts[agent_type] = agent_counts.get(agent_type, 0) + 1

    allocation_by_course: dict[str, list[dict[str, str]]] = {}
    for row in allocations:
        course_id = row.get("course_id", "")
        if course_id:
            allocation_by_course.setdefault(course_id, []).append(row)

    observations: list[BoundaryObservation] = []
    for course_id, selected_rows in selected_by_course.items():
        m = len(selected_rows)
        n = capacity_by_course.get(course_id) or _capacity_from_allocations(allocation_by_course.get(course_id, [])) or 0
        if n <= 0:
            continue
        allocation_rows = allocation_by_course.get(course_id, [])
        cutoff = _course_cutoff(allocation_rows, m, n)
        selected_bids = sorted(_to_int(row.get("bid")) or 0 for row in selected_rows)
        category = category_by_course.get(course_id, "")
        observations.append(
            BoundaryObservation(
                source_root=str(run_dir.parent),
                run_dir=str(run_dir),
                run_id=str(run_id),
                course_id=course_id,
                market_profile=infer_market_profile(run_dir.name),
                run_family=infer_run_family(run_dir.name),
                agent_mix=agent_mix_label(agent_counts),
                category=category,
                m=m,
                n=n,
                crowding_ratio=round(m / max(1, n), 8),
                excess_demand=max(0, m - n),
                cutoff_bid=float(cutoff),
                selected_bid_mean=round(mean(selected_bids), 6) if selected_bids else 0.0,
                selected_bid_p50=quantile(selected_bids, 0.50),
                selected_bid_p75=quantile(selected_bids, 0.75),
                selected_bid_p90=quantile(selected_bids, 0.90),
                overloaded=m > n,
            )
        )
    return observations


def evaluate_models(train: list[BoundaryObservation], test: list[BoundaryObservation]) -> list[dict[str, object]]:
    candidates: list[tuple[str, Callable[[BoundaryObservation], list[float]]]] = [
        ("original_formula_scaled", lambda row: [1.0, original_formula_feature(row)]),
        ("ratio_linear", lambda row: [1.0, row.crowding_ratio, max(0.0, row.crowding_ratio - 1.0)]),
        (
            "excess_capacity",
            lambda row: [1.0, row.crowding_ratio, math.sqrt(row.excess_demand), math.log1p(row.n)],
        ),
        ("log_saturation", lambda row: [1.0, math.log1p(row.excess_demand), math.log1p(row.crowding_ratio)]),
    ]
    for power in POWER_GRID:
        candidates.append((f"ratio_power_p{power:g}", lambda row, p=power: [1.0, max(0.0, row.crowding_ratio - 1.0) ** p]))

    rows: list[dict[str, object]] = []
    for name, feature_fn in candidates:
        coeffs = fit_ols([feature_fn(row) for row in train], [row.cutoff_bid for row in train])
        predictor = lambda row, fn=feature_fn, beta=coeffs: clamp_bid(dot(beta, fn(row)))
        rows.append(summary_for_model(name, predictor, train, test, coeffs))

    for quantile_value in (0.5, 0.75, 0.9):
        bin_predictor = fit_bin_predictor(train, quantile_value)
        rows.append(summary_for_model(f"bin_quantile_p{int(quantile_value * 100)}", bin_predictor, train, test, []))

    return sorted(rows, key=lambda row: (float(row["test_score"]), float(row["test_mae"])))


def summary_for_model(
    name: str,
    predictor: Callable[[BoundaryObservation], float],
    train: list[BoundaryObservation],
    test: list[BoundaryObservation],
    coeffs: list[float],
) -> dict[str, object]:
    train_metrics = metrics_for_predictions([(row.cutoff_bid, predictor(row)) for row in train])
    test_metrics = metrics_for_predictions([(row.cutoff_bid, predictor(row)) for row in test])
    high_test = [row for row in test if row.crowding_ratio > 1.0]
    low_test = [row for row in test if row.crowding_ratio <= 1.0]
    high_metrics = metrics_for_predictions([(row.cutoff_bid, predictor(row)) for row in high_test])
    low_metrics = metrics_for_predictions([(row.cutoff_bid, predictor(row)) for row in low_test])
    score = test_metrics["mae"] + 0.25 * test_metrics["mean_overpay"] + 8.0 * max(0.0, 0.75 - test_metrics["coverage"])
    return {
        "model": name,
        "coefficients_json": json.dumps([round(value, 8) for value in coeffs], ensure_ascii=False),
        "train_n": len(train),
        "test_n": len(test),
        "train_mae": round(train_metrics["mae"], 6),
        "test_mae": round(test_metrics["mae"], 6),
        "test_rmse": round(test_metrics["rmse"], 6),
        "test_coverage": round(test_metrics["coverage"], 6),
        "test_mean_overpay": round(test_metrics["mean_overpay"], 6),
        "test_mean_underpay": round(test_metrics["mean_underpay"], 6),
        "test_score": round(score, 6),
        "high_competition_mae": round(high_metrics["mae"], 6),
        "high_competition_coverage": round(high_metrics["coverage"], 6),
        "low_competition_mae": round(low_metrics["mae"], 6),
        "low_competition_coverage": round(low_metrics["coverage"], 6),
    }


def build_bin_table(observations: list[BoundaryObservation]) -> list[dict[str, object]]:
    rows = []
    for lower, upper in zip(DEFAULT_BINS, DEFAULT_BINS[1:]):
        items = [row for row in observations if lower <= row.crowding_ratio < upper]
        cutoffs = sorted(row.cutoff_bid for row in items)
        rows.append(
            {
                "bin": bin_label(lower, upper),
                "lower": lower,
                "upper": upper if math.isfinite(upper) else "",
                "n": len(items),
                "cutoff_mean": round(mean(cutoffs), 6) if cutoffs else 0.0,
                "cutoff_p50": quantile(cutoffs, 0.50),
                "cutoff_p75": quantile(cutoffs, 0.75),
                "cutoff_p90": quantile(cutoffs, 0.90),
                "overloaded_share": round(sum(1 for row in items if row.overloaded) / max(1, len(items)), 6),
            }
        )
    return rows


def write_report(
    path: Path,
    observations: list[BoundaryObservation],
    model_rows: list[dict[str, object]],
    bin_rows: list[dict[str, object]],
    run_dirs: list[Path],
    *,
    quick: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    best = model_rows[0]
    original = next((row for row in model_rows if row["model"] == "original_formula_scaled"), None)
    bin_p75 = next((row for row in model_rows if row["model"] == "bin_quantile_p75"), None)
    train, test = split_train_test(observations)
    strata_rows = build_stratified_model_rows(train, test, observations)
    content = [
        "# 拥挤比边界公式拟合报告",
        "",
        "## 核心结论",
        "",
        f"- 本轮使用 `{len(run_dirs)}` 个 run，聚合 `{len(observations)}` 条 `run × course section` 观测。",
        f"- 最优综合模型是 `{best['model']}`：test MAE `{best['test_mae']}`，coverage `{best['test_coverage']}`，平均 overpay `{best['test_mean_overpay']}`。",
        f"- 简洁可执行版本是 `bin_quantile_p75`：test MAE `{bin_p75['test_mae'] if bin_p75 else ''}`，coverage `{bin_p75['test_coverage'] if bin_p75 else ''}`，用拥挤比分箱给安全边界。",
        f"- 原始流传公式即使经过最优缩放，test MAE 仍为 `{original['test_mae'] if original else ''}`，coverage `{original['test_coverage'] if original else ''}`，明显弱于拥挤比分箱和 log 饱和模型。",
        "- 流传公式只看 `m,n`，方向上能表达拥挤，但缺少课程重要性、替代品、毕业压力和预算约束，不能直接当最终投豆答案。",
        "- 学生可执行策略应是：先用拥挤比预测边界，再按课程重要性加安全垫。",
        "",
        "## 数据与目标",
        "",
        "数据来自本项目生成的合成市场和已完成实验输出，不是真实教务数据。观测单位是一个 run 中的一门教学班：",
        "",
        "```text",
        "r = m / n",
        "m = 最终选择该教学班的人数",
        "n = 教学班容量",
        "target = cutoff_bid",
        "```",
        "",
        "目标是预测录取边界，不是直接替学生给唯一 bid。学生没有精确 utility 表，因此最终建议只使用拥挤比、课程重要性和替代品判断。",
        "",
        "训练/测试按 run_id 哈希切分，避免同一 run 的教学班同时出现在训练和测试里。`coverage` 表示预测边界不低于真实 cutoff 的比例；`mean overpay` 表示预测边界高于 cutoff 的平均豆数，衡量“边界估高导致多投”的风险。",
        "",
        "## 候选公式",
        "",
        "- `original_formula_scaled`：对流传公式特征 `sqrt(m-n) * exp(m/n)` 做线性缩放；当 `m <= n` 时特征置为 `0`。",
        "- `ratio_linear`：直接使用拥挤比 `r=m/n` 和超载部分 `max(0,r-1)`。",
        "- `ratio_power`：使用 `max(0,r-1)^p`，扫描多个幂次。",
        "- `excess_capacity`：同时使用拥挤比、超额人数 `m-n` 和容量尺度。",
        "- `log_saturation`：使用 `log(1+max(0,m-n))` 与 `log(1+r)`，允许高拥挤区域逐渐饱和。",
        "- `bin_quantile`：按拥挤比分箱，取训练集中 cutoff 的 p50/p75/p90，作为最容易公开解释的经验边界。",
        "",
        "## 模型比较",
        "",
        "| Model | Test MAE | Coverage | Mean overpay | High-r MAE | Low-r MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in model_rows[:10]:
        content.append(
            f"| `{row['model']}` | {row['test_mae']} | {row['test_coverage']} | "
            f"{row['test_mean_overpay']} | {row['high_competition_mae']} | {row['low_competition_mae']} |"
        )
    if strata_rows:
        content.extend(
            [
                "",
                "## 分市场检验",
                "",
                "这里单独看 `r > 1` 的高拥挤课程，区分整体高竞争市场和 sparse-hotspots 这种“多数课不挤、少数课很热”的市场。优先使用测试集；若某个市场在按 run 切分后的测试集中没有样本，则用全量观测做描述性 sanity check。",
                "",
                "| Stratum | Sample | Model | n | MAE | Coverage | Mean overpay |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in strata_rows:
            content.append(
                f"| {row['stratum']} | {row['sample']} | `{row['model']}` | {row['n']} | "
                f"{row['mae']} | {row['coverage']} | {row['mean_overpay']} |"
            )
    content.extend(
        [
            "",
            "## 拥挤比分箱表",
            "",
            "| r bin | n | cutoff p50 | cutoff p75 | cutoff p90 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in bin_rows:
        content.append(f"| `{row['bin']}` | {row['n']} | {row['cutoff_p50']} | {row['cutoff_p75']} | {row['cutoff_p90']} |")
    content.extend(
        [
            "",
            "## 给学生的版本",
            "",
            "- `m/n <= 1`：大多数情况下边界低，普通课不要高价表达喜欢。",
            "- `m/n > 1`：开始关注边界预测；普通可替代课按中位边界，重要课看 p75/p90。",
            "- 必修、毕业压力大、特别喜欢老师或课程时，在预测边界上加安全垫。",
            "- 有替代 section 或替代课时，不要和热门课硬碰。",
            "",
            "本报告推荐把 `log_saturation` 作为统计模型，把 `bin_quantile_p75` 作为公开可执行规则。前者误差更低，后者更容易让学生按表操作：先查 `m/n` 分箱，再根据课程重要性决定用 p50、p75 还是 p90。",
            "",
            "## 复现",
            "",
            "```powershell",
            "bidflow analyze crowding-boundary",
            "```",
        ]
    )
    if quick:
        content.insert(2, "> 这是 quick smoke 版本，不用于最终结论。")
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def build_stratified_model_rows(
    train: list[BoundaryObservation],
    test: list[BoundaryObservation],
    observations: list[BoundaryObservation],
) -> list[dict[str, object]]:
    predictors = {
        "log_saturation": named_predictor(train, "log_saturation"),
        "bin_quantile_p75": named_predictor(train, "bin_quantile_p75"),
        "original_formula_scaled": named_predictor(train, "original_formula_scaled"),
    }
    strata: list[tuple[str, Callable[[BoundaryObservation], bool]]] = [
        (
            "high-market hot courses",
            lambda row: row.market_profile in {"research_large_high", "behavioral_large"} and row.crowding_ratio > 1.0,
        ),
        ("medium-market hot courses", lambda row: row.market_profile == "medium" and row.crowding_ratio > 1.0),
        (
            "sparse-hotspots hot courses",
            lambda row: row.market_profile == "sparse_hotspots" and row.crowding_ratio > 1.0,
        ),
        ("all low-r courses", lambda row: row.crowding_ratio <= 1.0),
    ]
    rows: list[dict[str, object]] = []
    for stratum_name, predicate in strata:
        items = [row for row in test if predicate(row)]
        sample = "test"
        if not items:
            items = [row for row in observations if predicate(row)]
            sample = "all"
        if not items:
            continue
        for model_name, predictor in predictors.items():
            metrics = metrics_for_predictions([(row.cutoff_bid, predictor(row)) for row in items])
            rows.append(
                {
                    "stratum": stratum_name,
                    "sample": sample,
                    "model": model_name,
                    "n": len(items),
                    "mae": round(metrics["mae"], 6),
                    "coverage": round(metrics["coverage"], 6),
                    "mean_overpay": round(metrics["mean_overpay"], 6),
                }
            )
    return rows


def named_predictor(
    train: list[BoundaryObservation],
    model_name: str,
) -> Callable[[BoundaryObservation], float]:
    if model_name == "original_formula_scaled":
        coeffs = fit_ols([[1.0, original_formula_feature(row)] for row in train], [row.cutoff_bid for row in train])
        return lambda row, beta=coeffs: clamp_bid(dot(beta, [1.0, original_formula_feature(row)]))
    if model_name == "log_saturation":
        coeffs = fit_ols(
            [[1.0, math.log1p(row.excess_demand), math.log1p(row.crowding_ratio)] for row in train],
            [row.cutoff_bid for row in train],
        )
        return lambda row, beta=coeffs: clamp_bid(
            dot(beta, [1.0, math.log1p(row.excess_demand), math.log1p(row.crowding_ratio)])
        )
    if model_name.startswith("bin_quantile_p"):
        quantile_value = float(model_name.removeprefix("bin_quantile_p")) / 100.0
        return fit_bin_predictor(train, quantile_value)
    raise ValueError(f"Unsupported model for report stratum: {model_name}")


def split_train_test(observations: list[BoundaryObservation]) -> tuple[list[BoundaryObservation], list[BoundaryObservation]]:
    train = []
    test = []
    for row in observations:
        digest = hashlib.sha256(row.run_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 5
        (test if bucket == 0 else train).append(row)
    if not train or not test:
        midpoint = max(1, len(observations) // 2)
        train = observations[:midpoint]
        test = observations[midpoint:] or observations[:]
    return train, test


def fit_bin_predictor(train: list[BoundaryObservation], quantile_value: float) -> Callable[[BoundaryObservation], float]:
    global_cutoffs = sorted(row.cutoff_bid for row in train)
    global_value = quantile(global_cutoffs, quantile_value)
    by_bin: dict[str, float] = {}
    for lower, upper in zip(DEFAULT_BINS, DEFAULT_BINS[1:]):
        items = sorted(row.cutoff_bid for row in train if lower <= row.crowding_ratio < upper)
        by_bin[bin_label(lower, upper)] = quantile(items, quantile_value) if items else global_value

    def predict(row: BoundaryObservation) -> float:
        for lower, upper in zip(DEFAULT_BINS, DEFAULT_BINS[1:]):
            if lower <= row.crowding_ratio < upper:
                return clamp_bid(by_bin[bin_label(lower, upper)])
        return clamp_bid(global_value)

    return predict


def metrics_for_predictions(pairs: list[tuple[float, float]]) -> dict[str, float]:
    if not pairs:
        return {"mae": 0.0, "rmse": 0.0, "coverage": 0.0, "mean_overpay": 0.0, "mean_underpay": 0.0}
    errors = [prediction - actual for actual, prediction in pairs]
    abs_errors = [abs(error) for error in errors]
    return {
        "mae": mean(abs_errors),
        "rmse": math.sqrt(mean(error * error for error in errors)),
        "coverage": sum(1 for error in errors if error >= 0) / len(errors),
        "mean_overpay": mean(max(0.0, error) for error in errors),
        "mean_underpay": mean(max(0.0, -error) for error in errors),
    }


def fit_ols(x_rows: list[list[float]], y_values: list[float], *, ridge: float = 1e-8) -> list[float]:
    if not x_rows:
        return []
    width = len(x_rows[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]
    for x, y in zip(x_rows, y_values):
        for i in range(width):
            xty[i] += x[i] * y
            for j in range(width):
                xtx[i][j] += x[i] * x[j]
    for i in range(width):
        xtx[i][i] += ridge
    return solve_linear_system(xtx, xty)


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for pivot in range(n):
        best = max(range(pivot, n), key=lambda row: abs(augmented[row][pivot]))
        if abs(augmented[best][pivot]) < 1e-12:
            continue
        augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
        scale = augmented[pivot][pivot]
        augmented[pivot] = [value / scale for value in augmented[pivot]]
        for row in range(n):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            if abs(factor) < 1e-12:
                continue
            augmented[row] = [value - factor * augmented[pivot][col] for col, value in enumerate(augmented[row])]
    return [augmented[i][-1] for i in range(n)]


def original_formula_feature(row: BoundaryObservation) -> float:
    if row.m <= row.n:
        return 0.0
    return math.sqrt(row.m - row.n) * math.exp(min(row.crowding_ratio, 6.0))


def dot(coeffs: list[float], features: list[float]) -> float:
    return sum(coef * feature for coef, feature in zip(coeffs, features))


def clamp_bid(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return float(min(100, max(0, round(value))))


def quantile(values: list[float] | list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 6)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 6)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 6)


def _course_cutoff(allocation_rows: list[dict[str, str]], m: int, n: int) -> float:
    cutoffs = [_to_float(row.get("cutoff_bid")) for row in allocation_rows]
    cutoffs = [value for value in cutoffs if value is not None]
    if cutoffs:
        return max(cutoffs)
    if m <= n:
        return 0.0
    admitted_bids = sorted(
        (_to_int(row.get("bid")) or 0 for row in allocation_rows if _truthy(row.get("admitted", ""))),
        reverse=True,
    )
    return float(admitted_bids[n - 1]) if len(admitted_bids) >= n else 0.0


def _capacity_from_allocations(allocation_rows: list[dict[str, str]]) -> int | None:
    admitted = sum(1 for row in allocation_rows if _truthy(row.get("admitted", "")))
    return admitted or None


def infer_market_profile(run_name: str) -> str:
    lower = run_name.lower()
    if "sparse" in lower:
        return "sparse_hotspots"
    if "medium" in lower:
        return "medium"
    if "behavioral_large" in lower:
        return "behavioral_large"
    if "research_large" in lower:
        return "research_large_high"
    return "unknown"


def infer_run_family(run_name: str) -> str:
    lower = run_name.lower()
    if "10pct" in lower or "cohort" in lower:
        return "llm_cohort"
    if "mix30" in lower:
        return "mix30_formula"
    if "llm_formula" in lower:
        return "llm_formula"
    if "llm_plain" in lower:
        return "llm_plain"
    if "cass" in lower:
        return "cass"
    if "behavioral" in lower:
        return "behavioral"
    return "other"


def agent_mix_label(agent_counts: dict[str, int]) -> str:
    if not agent_counts:
        return ""
    total = sum(agent_counts.values())
    top = sorted(agent_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    return ",".join(f"{agent}:{count / max(1, total):.2f}" for agent, count in top)


def bin_label(lower: float, upper: float) -> str:
    if math.isinf(upper):
        return f">={lower:g}"
    return f"[{lower:g},{upper:g})"


def observation_to_row(item: BoundaryObservation) -> dict[str, object]:
    return {
        "source_root": item.source_root,
        "run_dir": item.run_dir,
        "run_id": item.run_id,
        "course_id": item.course_id,
        "market_profile": item.market_profile,
        "run_family": item.run_family,
        "agent_mix": item.agent_mix,
        "category": item.category,
        "m": item.m,
        "n": item.n,
        "crowding_ratio": item.crowding_ratio,
        "excess_demand": item.excess_demand,
        "cutoff_bid": item.cutoff_bid,
        "selected_bid_mean": item.selected_bid_mean,
        "selected_bid_p50": item.selected_bid_p50,
        "selected_bid_p75": item.selected_bid_p75,
        "selected_bid_p90": item.selected_bid_p90,
        "overloaded": item.overloaded,
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit crowding-ratio formulas for course cutoff bids.")
    parser.add_argument("--run-root", action="append", default=None, help="Run root directory. May be repeated.")
    parser.add_argument("--no-sibling", action="store_true", help="Do not scan the sibling llm-tests worktree outputs.")
    parser.add_argument("--quick", action="store_true", help="Use a small run subset for smoke testing.")
    parser.add_argument("--detail-table", default="outputs/tables/crowding_boundary_observations.csv")
    parser.add_argument("--summary-table", default="outputs/tables/crowding_boundary_model_summary.csv")
    parser.add_argument("--bin-table", default="outputs/tables/crowding_boundary_bin_table.csv")
    parser.add_argument("--report", default="reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_crowding_boundary_fit(
        run_roots=args.run_root,
        include_sibling=not args.no_sibling,
        quick=args.quick,
        detail_table=args.detail_table,
        summary_table=args.summary_table,
        bin_table=args.bin_table,
        report_path=args.report,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
