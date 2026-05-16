from __future__ import annotations

import pandas as pd

from src.planning.schema import (
    CRITICAL_ROLE_COLS,
    PLAN_ROLE_COLS,
    SERVICE_DATE_COL,
)
from src.reporting.evaluation_metrics import evaluate_plan


DATE_COL = SERVICE_DATE_COL
ROLE_COLS = list(PLAN_ROLE_COLS)
CRITICAL_ROLES = list(CRITICAL_ROLE_COLS)
DEFAULT_WEIGHTS = {
    "coverage": 0.35,
    "equity": 0.30,
    "rest": 0.20,
    "resilience": 0.15,
}


def coerce_plan_datetime(plan: pd.DataFrame) -> pd.DataFrame:
    normalized = plan.copy()
    if DATE_COL in normalized.columns:
        normalized[DATE_COL] = pd.to_datetime(normalized[DATE_COL])
        normalized = normalized.sort_values(DATE_COL).reset_index(drop=True)
    return normalized


def _coerce_plan_datetimes(plans: dict[int, pd.DataFrame]) -> dict[int, pd.DataFrame]:
    normalized_plans: dict[int, pd.DataFrame] = {}

    for plan_id, df in plans.items():
        plan = coerce_plan_datetime(df)
        normalized_plans[plan_id] = plan

    return normalized_plans


def get_best_plan_id(summary_df: pd.DataFrame) -> int | None:
    if summary_df.empty:
        return None
    return int(summary_df.iloc[0]["plan_id"])


def evaluate_plan_collection(
    plans: dict[int, pd.DataFrame],
    weights: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, dict[int, dict], int | None]:
    weights = weights or DEFAULT_WEIGHTS
    results: dict[int, dict] = {}

    normalized_plans = _coerce_plan_datetimes(plans)

    for plan_id, df_plan in normalized_plans.items():
        results[plan_id] = evaluate_plan(
            df_plan,
            DATE_COL,
            ROLE_COLS,
            CRITICAL_ROLES,
            weights,
        )

    summary_rows = []
    for plan_id, result in results.items():
        summary_rows.append(
            {
                "plan_id": plan_id,
                **result["metrics"]["score_metrics"],
                **result["metrics"]["other_metrics"],
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if summary_df.empty:
        return summary_df, results, None

    summary_df = summary_df.sort_values(
        ["overall_score", "coverage_score", "equity_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    summary_df["rank"] = range(1, len(summary_df) + 1)

    best_plan_id = get_best_plan_id(summary_df)

    return summary_df, results, best_plan_id
