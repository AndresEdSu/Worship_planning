from __future__ import annotations

import pandas as pd

from src.reporting.evaluation_metrics import evaluate_plan
from src.reporting.export_infographic import (
    COLUMN_ALIASES,
    DATE_PRESENTATION_COL,
)


DATE_COL = DATE_PRESENTATION_COL
ROLE_COLS = [
    "Director",
    "Guitarist",
    "Drummer",
    "Bassist",
    "Keyboardist",
    "Vocalist_1",
    "Vocalist_2",
]
CRITICAL_ROLES = ["Director", "Guitarist", "Drummer", "Bassist", "Keyboardist"]
DEFAULT_WEIGHTS = {
    "coverage": 0.35,
    "equity": 0.30,
    "rest": 0.20,
    "resilience": 0.15,
}


def coerce_plan_datetime(plan: pd.DataFrame) -> pd.DataFrame:
    normalized = plan.rename(columns=COLUMN_ALIASES).copy()
    if DATE_COL in normalized.columns:
        normalized[DATE_COL] = pd.to_datetime(normalized[DATE_COL])
        normalized = normalized.sort_values(DATE_COL).reset_index(drop=True)
    return normalized


def _coerce_plan_columns(plans: dict[int, pd.DataFrame]) -> dict[int, pd.DataFrame]:
    normalized_plans: dict[int, pd.DataFrame] = {}

    for seed, df in plans.items():
        plan = coerce_plan_datetime(df)
        normalized_plans[seed] = plan

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

    normalized_plans = _coerce_plan_columns(plans)

    for seed, df_plan in normalized_plans.items():
        results[seed] = evaluate_plan(
            df_plan,
            DATE_COL,
            ROLE_COLS,
            CRITICAL_ROLES,
            weights,
        )

    summary_rows = []
    for seed, result in results.items():
        summary_rows.append(
            {
                "plan_id": seed,
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
