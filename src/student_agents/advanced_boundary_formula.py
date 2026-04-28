from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


LEGACY_FORMULA_POLICY = "legacy_formula_v1"
ADVANCED_FORMULA_POLICY = "advanced_boundary_v1"
FORMULA_POLICY_ALIASES = {
    "bid_allocation_v1": LEGACY_FORMULA_POLICY,
    LEGACY_FORMULA_POLICY: LEGACY_FORMULA_POLICY,
    ADVANCED_FORMULA_POLICY: ADVANCED_FORMULA_POLICY,
}
FORMULA_POLICIES = tuple(FORMULA_POLICY_ALIASES)
DEFAULT_ADVANCED_FORMULA_CONFIG_PATH = Path("configs/formulas/advanced_boundary_v1.yaml")


@dataclass(frozen=True)
class AdvancedBoundaryConfig:
    policy: str = ADVANCED_FORMULA_POLICY
    budget_reference: int = 100
    beta0: float = -0.0029413192284291428
    beta_log_excess: float = 0.03823510855613368
    beta_log_ratio: float = 0.00977980294108818
    tau_share: float = 0.01
    target_coverage: float = 0.90
    default_single_course_cap_share: float = 0.35
    required_single_course_cap_share: float = 0.45
    min_bid: int = 1
    replaceable_multiplier: float = 0.85
    standard_multiplier: float = 1.00
    strong_multiplier: float = 1.15
    required_multiplier: float = 1.30


@dataclass(frozen=True)
class AdvancedBoundaryResult:
    policy: str
    m: int
    n: int
    crowding_ratio: float
    excess_demand: int
    raw_boundary_share: float
    boundary_share: float
    boundary_bid_reference: int
    importance_label: str
    importance_multiplier: float
    single_course_cap_share: float
    single_course_cap_bid: int
    suggested_bid_before_cap: int
    suggested_bid: int
    m_le_n_guard: bool
    clipped_by_course_cap: bool
    clipped_by_remaining_budget: bool


def resolve_formula_policy(policy: str | None) -> str:
    key = str(policy or LEGACY_FORMULA_POLICY).strip()
    if key not in FORMULA_POLICY_ALIASES:
        raise ValueError(f"Unsupported formula policy: {policy}")
    return FORMULA_POLICY_ALIASES[key]


def load_advanced_boundary_config(path: str | Path | None = None) -> AdvancedBoundaryConfig:
    config_path = Path(path or DEFAULT_ADVANCED_FORMULA_CONFIG_PATH)
    if not config_path.exists():
        return AdvancedBoundaryConfig()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    coefficients = payload.get("coefficients", {}) or {}
    calibration = payload.get("coverage_calibration", {}) or {}
    caps = payload.get("single_course_cap", {}) or {}
    multipliers = payload.get("importance_multipliers", {}) or {}
    return AdvancedBoundaryConfig(
        policy=str(payload.get("policy", ADVANCED_FORMULA_POLICY)),
        budget_reference=int(payload.get("budget_reference", 100)),
        beta0=float(coefficients.get("beta0", AdvancedBoundaryConfig.beta0)),
        beta_log_excess=float(coefficients.get("beta_log_excess", AdvancedBoundaryConfig.beta_log_excess)),
        beta_log_ratio=float(coefficients.get("beta_log_ratio", AdvancedBoundaryConfig.beta_log_ratio)),
        tau_share=float(calibration.get("tau_share", AdvancedBoundaryConfig.tau_share)),
        target_coverage=float(calibration.get("target_coverage", AdvancedBoundaryConfig.target_coverage)),
        default_single_course_cap_share=float(
            caps.get("default_share", AdvancedBoundaryConfig.default_single_course_cap_share)
        ),
        required_single_course_cap_share=float(
            caps.get("required_share", AdvancedBoundaryConfig.required_single_course_cap_share)
        ),
        min_bid=int(payload.get("min_bid", AdvancedBoundaryConfig.min_bid)),
        replaceable_multiplier=float(multipliers.get("replaceable", AdvancedBoundaryConfig.replaceable_multiplier)),
        standard_multiplier=float(multipliers.get("standard", AdvancedBoundaryConfig.standard_multiplier)),
        strong_multiplier=float(multipliers.get("strong", AdvancedBoundaryConfig.strong_multiplier)),
        required_multiplier=float(multipliers.get("required", AdvancedBoundaryConfig.required_multiplier)),
    )


def advanced_boundary_reference(
    *,
    m: int,
    n: int,
    budget: int,
    remaining_budget: int | None = None,
    importance_label: str = "standard",
    config: AdvancedBoundaryConfig | None = None,
) -> AdvancedBoundaryResult:
    cfg = config or load_advanced_boundary_config()
    budget = max(0, int(budget))
    remaining = budget if remaining_budget is None else max(0, int(remaining_budget))
    n_safe = max(1, int(n))
    m_value = max(0, int(m))
    ratio = m_value / n_safe
    excess = max(0, m_value - n_safe)
    m_le_n_guard = m_value <= n_safe
    importance = normalize_importance_label(importance_label)
    multiplier = importance_multiplier(importance, cfg)
    cap_share = cfg.required_single_course_cap_share if importance == "required" else cfg.default_single_course_cap_share
    cap_bid = max(0, int(math.floor(budget * cap_share)))

    if m_le_n_guard or budget <= 0:
        raw_share = 0.0
        boundary_share = 0.0
    else:
        raw_share = (
            cfg.beta0
            + cfg.beta_log_excess * math.log1p(excess)
            + cfg.beta_log_ratio * math.log1p(ratio)
            + cfg.tau_share
        )
        boundary_share = min(max(0.0, raw_share), cap_share)

    boundary_bid = int(math.ceil(budget * boundary_share)) if boundary_share > 0 else 0
    before_cap = int(math.ceil(boundary_bid * multiplier)) if boundary_bid > 0 else cfg.min_bid
    capped = min(before_cap, cap_bid if cap_bid > 0 else before_cap)
    suggested = min(capped, remaining)
    if budget > 0 and remaining > 0:
        suggested = max(min(cfg.min_bid, remaining), suggested)

    return AdvancedBoundaryResult(
        policy=cfg.policy,
        m=m_value,
        n=n_safe,
        crowding_ratio=round(ratio, 8),
        excess_demand=excess,
        raw_boundary_share=round(raw_share, 10),
        boundary_share=round(boundary_share, 10),
        boundary_bid_reference=boundary_bid,
        importance_label=importance,
        importance_multiplier=round(multiplier, 6),
        single_course_cap_share=round(cap_share, 6),
        single_course_cap_bid=cap_bid,
        suggested_bid_before_cap=before_cap,
        suggested_bid=suggested,
        m_le_n_guard=m_le_n_guard,
        clipped_by_course_cap=before_cap > capped,
        clipped_by_remaining_budget=capped > remaining,
    )


def normalize_importance_label(label: str | None) -> str:
    value = str(label or "standard").strip().lower()
    if value in {"required", "graduation", "graduate", "must"}:
        return "required"
    if value in {"strong", "core", "favorite", "important", "strong_elective"}:
        return "strong"
    if value in {"replaceable", "optional", "low"}:
        return "replaceable"
    return "standard"


def importance_multiplier(label: str, config: AdvancedBoundaryConfig) -> float:
    normalized = normalize_importance_label(label)
    return {
        "replaceable": config.replaceable_multiplier,
        "standard": config.standard_multiplier,
        "strong": config.strong_multiplier,
        "required": config.required_multiplier,
    }[normalized]


def config_to_yaml_dict(config: AdvancedBoundaryConfig, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "policy": config.policy,
        "budget_reference": config.budget_reference,
        "coefficients": {
            "beta0": config.beta0,
            "beta_log_excess": config.beta_log_excess,
            "beta_log_ratio": config.beta_log_ratio,
        },
        "coverage_calibration": {
            "target_coverage": config.target_coverage,
            "tau_share": config.tau_share,
        },
        "single_course_cap": {
            "default_share": config.default_single_course_cap_share,
            "required_share": config.required_single_course_cap_share,
        },
        "importance_multipliers": {
            "replaceable": config.replaceable_multiplier,
            "standard": config.standard_multiplier,
            "strong": config.strong_multiplier,
            "required": config.required_multiplier,
        },
        "min_bid": config.min_bid,
        "metadata": metadata or {},
    }


def write_advanced_boundary_config(
    path: str | Path,
    config: AdvancedBoundaryConfig,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(config_to_yaml_dict(config, metadata=metadata), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def result_to_dict(result: AdvancedBoundaryResult) -> dict[str, Any]:
    return asdict(result)
