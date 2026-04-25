from __future__ import annotations

import pandas as pd

from src.reporting.plan_evaluation import DATE_COL, DEFAULT_WEIGHTS


SUMMARY_COLUMN_LABELS = {
    "rank": "#",
    "plan_id": "Plan",
    "overall_score": "Overall Score",
    "coverage_score": "Coverage",
    "equity_score": "Equity",
    "rest_score": "Rest",
    "resilience_score": "Resilience",
    "missing_total": "Missing",
    "avg_max_consecutive_weeks": "Avg. Max Consecutive Weeks",
}
SCORE_LABELS = {
    "overall_score": "Overall Score",
    "coverage_score": "Coverage",
    "equity_score": "Equity",
    "rest_score": "Rest",
    "resilience_score": "Resilience",
}


def format_score(value: float) -> str:
    return f"{value:.1f}/100"


def format_decimal(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def format_integer(value: float | int) -> str:
    return str(int(value))


def build_calendar_df(plan_df: pd.DataFrame) -> pd.DataFrame:
    calendar_df = plan_df.copy()
    calendar_df[DATE_COL] = pd.to_datetime(calendar_df[DATE_COL]).dt.strftime("%Y-%m-%d")
    return calendar_df


def build_participants_df(participants_df: pd.DataFrame) -> pd.DataFrame:
    return participants_df.reset_index().rename(
        columns={
            "index": "Person",
            "participations": "Participations",
            "role_diversity": "Role Diversity",
            "roles": "Roles",
            "max_consecutive_weeks": "Max Consecutive Weeks",
        }
    )


def build_missing_df(missing_df: pd.DataFrame) -> pd.DataFrame:
    formatted_missing_df = missing_df.copy()
    formatted_missing_df["date"] = pd.to_datetime(formatted_missing_df["date"]).dt.strftime("%Y-%m-%d")
    return formatted_missing_df.rename(
        columns={"date": "Date", "missing_core_roles": "Missing Core Roles"}
    )


def build_summary_display_df(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df.copy()

    return summary_df[
        [
            "rank",
            "plan_id",
            "overall_score",
            "coverage_score",
            "equity_score",
            "rest_score",
            "resilience_score",
            "missing_total",
            "avg_max_consecutive_weeks",
        ]
    ].rename(columns=SUMMARY_COLUMN_LABELS)


def build_chart_df(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df.copy()

    chart_df = summary_df.set_index(summary_df["plan_id"].astype(str))[
        ["overall_score", "coverage_score", "equity_score", "rest_score", "resilience_score"]
    ].copy()
    chart_df.columns = [SCORE_LABELS[column] for column in chart_df.columns]
    return chart_df


def build_score_metrics(
    score_values: dict[str, float],
    weights: dict[str, float],
) -> dict[str, dict[str, str | float]]:
    for score_key, _ in SCORE_LABELS.items():
        if score_key not in score_values:
            raise ValueError(f"Missing expected score key: {score_key}")

    return {
        score_key: {
            "label": label,
            "score_value": score_values[score_key],
            "score_display": format_score(score_values[score_key]),
            "weight": weights.get(label.lower(), 1),
        }
        for score_key, label in SCORE_LABELS.items()
    }


def build_other_metrics(
    other_values: dict[str, float | int],
) -> dict[str, str]:
    return {
        "dates_covered": format_integer(other_values["num_dates"]),
        "total_vacancies": format_integer(other_values["missing_total"]),
        "coefficient_variation": format_decimal(other_values["participation_cv"], 3),
        "critical_top_share": format_decimal(other_values["avg_critical_top_share"], 3),
        "average_streak": format_decimal(other_values["avg_max_consecutive_weeks"], 2),
    }


def build_plan_view(
    plan_id: int,
    result: dict,
    plan_df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    metrics = result["metrics"]
    dfs = result["dfs"]
    score_values = metrics["score_metrics"]
    other_values = metrics["other_metrics"]

    return {
        "plan_id": plan_id,
        "plan_label": f"Plan {plan_id}",
        "score_metrics": build_score_metrics(score_values, weights),
        "other_metrics": build_other_metrics(other_values),
        "calendar_df": build_calendar_df(plan_df),
        "participants_df": build_participants_df(dfs["participants"]),
        "missing_df": build_missing_df(dfs["missing_by_date"]),
    }


def build_dashboard_view(
    summary_df: pd.DataFrame,
    results: dict[int, dict],
    plans: dict[int, pd.DataFrame],
    best_plan_id: int | None,
    weights: dict[str, float] | None = None,
) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    plan_views = {
        plan_id: build_plan_view(plan_id, results[plan_id], plans[plan_id], weights)
        for plan_id in results
    }

    return {
        "best_plan_id": best_plan_id,
        "available_plan_ids": summary_df["plan_id"].astype(int).tolist(),
        "summary_display_df": build_summary_display_df(summary_df),
        "chart_df": build_chart_df(summary_df),
        "plan_views": plan_views,
    }
