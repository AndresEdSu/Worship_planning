from datetime import datetime

from src.data.load_data import (
    PROCESSED_DIR,
    INTERIM_DIR,
    load_raw_availability_data
    )
from src.data.clean_data import clean_availability_data, clean_generated_plan_data
from src.planning.plan_generation import plans_generator
from src.reporting.plan_evaluation import (
    DEFAULT_WEIGHTS,
    evaluate_plan_collection
)
from src.reporting.export_infographic import build_plan_infographic_html


EXPORTS_DIR = PROCESSED_DIR.parent / "exports"


def _print_plan_summary(row, prefix: str = "Plan") -> None:
    print(
        f"{prefix} {row.plan_id} details: {int(row.num_dates)} dates, "
        f"{row.participation_cv:.3f} CV, "
        f"{row.avg_critical_top_share:.3f} avg top share, "
        f"{row.avg_max_consecutive_weeks:.2f} avg max consecutive"
    )


def main():

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df_raw = load_raw_availability_data()
    df_clean = clean_availability_data(df_raw)

    clean_output_path = INTERIM_DIR / "availability_clean.csv"
    df_clean.to_csv(clean_output_path, index=False)

    print(f"Clean data saved to: {clean_output_path}")
    print(df_clean.shape)

    fecha_inicio = datetime(2026, 2, 1)
    valid_plans = plans_generator(df_clean, fecha_inicio, max_options=5, n_iter=10_000)
    cleaned_plans = {
        seed: clean_generated_plan_data(plan)
        for seed, plan in valid_plans.items()
    }

    if cleaned_plans:
        for old_file in PROCESSED_DIR.glob("planning_option_*.csv"):
            old_file.unlink()

        for seed, plan in cleaned_plans.items():
            plan_output_path = PROCESSED_DIR / f"planning_option_{seed}.csv"
            plan.to_csv(plan_output_path, index=False)

        print(f"{len(cleaned_plans)} plan options saved to: {PROCESSED_DIR}")

        summary_df, plan_results, best_plan_id = evaluate_plan_collection(cleaned_plans, DEFAULT_WEIGHTS)

        if not summary_df.empty:
            print("\nPlan Evaluation Results in descending order of overall score:")
            for row in summary_df.itertuples(index=False):
                print(f"\nPlan {row.plan_id}:")
                print(f"  Overall Score: {row.overall_score:.2f}")
                print(f"  --> Coverage: {row.coverage_score:.2f}")
                print(f"  --> Equity: {row.equity_score:.2f}")
                print(f"  --> Rest: {row.rest_score:.2f}")
                print(f"  --> Resilience: {row.resilience_score:.2f}")

            max_value = summary_df["overall_score"].max()
            best_rows = summary_df.loc[summary_df["overall_score"] == max_value].copy()
            best_seeds = best_rows["plan_id"].tolist()

            if len(best_seeds) > 1:
                print(f"\nMultiple best plans with overall score {max_value:.2f}: {best_seeds}")
                for row in best_rows.itertuples(index=False):
                    _print_plan_summary(row)
            else:
                best_row = next(best_rows.itertuples(index=False))
                print(f"\nBest plan: {best_row.plan_id} with overall score {max_value:.2f}")
                _print_plan_summary(best_row, prefix="Best plan")

            if best_plan_id is not None:
                infographic_html = build_plan_infographic_html(
                    cleaned_plans[best_plan_id],
                )
                infographic_path = EXPORTS_DIR / f"planning_option_{best_plan_id}.html"
                infographic_path.write_text(infographic_html, encoding="utf-8")
                print("\nHTML infographic exported:")
                print(f"  {infographic_path}")
    else:
        print("No valid plans were generated. Previous results were kept.")


if __name__ == "__main__":
    main()
