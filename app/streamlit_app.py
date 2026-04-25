from __future__ import annotations

from pathlib import Path
import streamlit as st

from src.data.load_data import PROCESSED_DIR, load_processed_plans_data
from src.reporting.dashboard_view import build_dashboard_view
from src.reporting.plan_evaluation import DEFAULT_WEIGHTS, evaluate_plan_collection


st.set_page_config(
    page_title="Worship Planning Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)


SUMMARY_TABLE_FORMAT = {
    "#": "{:.0f}",
    "Plan": "{:.0f}",
    "Overall Score": "{:.1f}",
    "Coverage": "{:.1f}",
    "Equity": "{:.1f}",
    "Rest": "{:.1f}",
    "Resilience": "{:.1f}",
    "Missing": "{:.0f}",
    "Avg. Max Consecutive Weeks": "{:.2f}",
}
PARTICIPANTS_TABLE_FORMAT = {
    "Participations": "{:.0f}",
    "Role Diversity": "{:.0f}",
    "Max Consecutive Weeks": "{:.0f}",
}
MISSING_TABLE_FORMAT = {"Missing Core Roles": "{:.0f}"}


@st.cache_data(show_spinner=False)
def load_dashboard_data(
    processed_dir: str,
) -> dict:
    plans = load_processed_plans_data(Path(processed_dir))
    summary_df, results, best_plan_id = evaluate_plan_collection(plans, DEFAULT_WEIGHTS)
    dashboard_view = build_dashboard_view(summary_df, results, plans, best_plan_id)
    return dashboard_view


def render_component_scorecard(label: str, score: float, weight: float) -> None:
    st.markdown(f"**{label}**")
    st.progress(min(max(score / 100, 0.0), 1.0), text=f"{score:.1f}/100")
    st.caption(f"Weight: {weight:.0%}")


def render_empty_state() -> None:
    st.info(
        "No plans were found in `data/processed`. "
        "Run `python -m src.pipeline.run_pipeline` first to generate the 5 options."
    )


def render_sidebar_controls(best_plan_id: int | None, available_plan_ids: list[int]) -> int:
    with st.sidebar:
        selected_plan_id = st.selectbox(
            "Plan to Explore",
            available_plan_ids,
            index=available_plan_ids.index(best_plan_id) if best_plan_id in available_plan_ids else 0,
            format_func=lambda plan_id: f"Plan {plan_id}",
        )
        st.markdown("**Score Weights**")
        for name, value in DEFAULT_WEIGHTS.items():
            st.caption(f"{name.title()}: {value:.0%}")

    return selected_plan_id


def render_top_metrics(best_plan_view: dict) -> None:
    top_metrics = st.columns(4)
    top_metrics[0].metric("Best Plan", best_plan_view["plan_label"])
    top_metrics[1].metric("Overall Score", best_plan_view['score_metrics']['overall_score']['score_display'])
    top_metrics[2].metric("Dates Covered", best_plan_view["other_metrics"]["dates_covered"])
    top_metrics[3].metric("Total Vacancies", best_plan_view["other_metrics"]["total_vacancies"])


def build_component_metrics(plan_view: dict) -> list[dict[str, str | float]]:
    return [
        metric
        for score_key, metric in plan_view["score_metrics"].items()
        if score_key != "overall_score"
    ]


def style_dataframe(dataframe, format_map: dict[str, str]):
    available_formats = {
        column: format_spec
        for column, format_spec in format_map.items()
        if column in dataframe.columns
    }
    return dataframe.style.format(available_formats, na_rep="-")


def render_plan_tables(plan_view: dict) -> None:
    st.subheader("Calendar")
    st.dataframe(plan_view["calendar_df"], width="stretch", hide_index=True)

    st.subheader("Team Participation")
    st.dataframe(
        style_dataframe(plan_view["participants_df"], PARTICIPANTS_TABLE_FORMAT),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Dates with Vacancies")
    st.dataframe(
        style_dataframe(plan_view["missing_df"], MISSING_TABLE_FORMAT),
        width="stretch",
        hide_index=True,
    )


def render_comparison_tab(dashboard_view: dict, best_plan_id: int, best_plan_view: dict) -> None:
    st.subheader("Options Ranking")
    st.dataframe(
        style_dataframe(dashboard_view["summary_display_df"], SUMMARY_TABLE_FORMAT),
        width="stretch",
        hide_index=True,
    )

    st.bar_chart(dashboard_view["chart_df"], width="stretch")

    st.subheader("Quick Read")
    st.write(
        f"Plan `{best_plan_id}` ranked first with {best_plan_view['score_metrics']['overall_score']['score_display']}. "
        f"Its strongest area is coverage ({best_plan_view['score_metrics']['coverage_score']['score_display']}) "
        f"and it maintains an average streak of {best_plan_view['other_metrics']['average_streak']} consecutive weeks."
        )

def render_best_plan_tab(best_plan_id: int, best_plan_view: dict) -> None:
    st.subheader(f"Winning Plan: {best_plan_id}")

    component_metrics = build_component_metrics(best_plan_view)
    score_cols = st.columns(len(component_metrics))
    for column, score_metric in zip(score_cols, component_metrics):
        column.metric(score_metric["label"], score_metric["score_display"])

    progress_cols = st.columns(len(component_metrics))
    for column, score_metric in zip(progress_cols, component_metrics):
        with column:
            render_component_scorecard(score_metric["label"], score_metric["score_value"], score_metric["weight"])

    render_plan_tables(best_plan_view)


def render_selected_plan_tab(
    selected_plan_id: int,
    selected_plan_view: dict,
    delta: float,
) -> None:
    st.subheader(f"Plan {selected_plan_id} Details")
    selected_score_metrics = list(selected_plan_view["score_metrics"].values())
    selected_score_cols = st.columns(len(selected_score_metrics))
    for column, score_metric in zip(selected_score_cols, selected_score_metrics):
        column.metric(score_metric["label"], score_metric["score_display"])

    st.write(
        f"Difference vs. the winning plan: `{delta:+.2f}` points. "
        f"Coefficient of variation: `{selected_plan_view['other_metrics']['coefficient_variation']}`. "
        f"Average top share in critical roles: `{selected_plan_view['other_metrics']['critical_top_share']}`."
    )
    render_plan_tables(selected_plan_view)


def main() -> None:
    st.title("Worship Planning Dashboard")
    st.caption("Compare the generated options and understand why one plan scored better than the others.")

    with st.sidebar:
        st.header("Controls")
        if st.button("Reload Data", width="stretch"):
            load_dashboard_data.clear()
        processed_dir = st.text_input("Plans Folder", str(PROCESSED_DIR))

    dashboard_view = load_dashboard_data(processed_dir)

    if not dashboard_view["plan_views"]:
        render_empty_state()
        return

    best_plan_id = dashboard_view["best_plan_id"]
    available_plan_ids = dashboard_view["available_plan_ids"]

    selected_plan_id = render_sidebar_controls(best_plan_id, available_plan_ids)

    best_plan_view = dashboard_view["plan_views"][best_plan_id]
    selected_plan_view = dashboard_view["plan_views"][selected_plan_id]

    delta = (
        selected_plan_view["score_metrics"]["overall_score"]["score_value"]
        - best_plan_view["score_metrics"]["overall_score"]["score_value"]
    )

    render_top_metrics(best_plan_view)

    comparison_tab, best_plan_tab, selected_plan_tab = st.tabs(
        ["Comparison", "Winning Plan", f"Plan {selected_plan_id}"]
    )

    with comparison_tab:
        render_comparison_tab(dashboard_view, best_plan_id, best_plan_view)

    with best_plan_tab:
        render_best_plan_tab(best_plan_id, best_plan_view)

    with selected_plan_tab:
        render_selected_plan_tab(selected_plan_id, selected_plan_view, delta)


if __name__ == "__main__":
    main()
