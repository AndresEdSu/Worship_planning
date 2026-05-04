from argparse import ArgumentParser
from datetime import datetime

from src.data.load_data import (
    PROCESSED_DIR,
    INTERIM_DIR,
    load_raw_availability_data
    )
from src.data.clean_data import clean_availability_data, clean_generated_plan_data
from src.data.save_data import (
    OUTPUTS_DIR,
    replace_processed_plans, 
    save_csv, 
    save_excel, 
    save_text
)
from src.planning.plan_generation import plans_generator
from src.reporting.plan_evaluation import (
    DATE_COL,
    DEFAULT_WEIGHTS,
    evaluate_plan_collection
)
from src.reporting.export_infographic import build_plan_infographic_html


def parse_args():
    parser = ArgumentParser(description="Generate worship planning options.")
    parser.add_argument(
        "--fecha-inicio",
        default="2026-01-04",
        help="Presentation start date in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def _print_plan_summary(row, prefix: str = "Plan") -> None:
    print(
        f"{prefix} {row.plan_id} details: {int(row.num_dates)} dates, "
        f"{row.participation_cv:.3f} CV, "
        f"{row.avg_critical_top_share:.3f} avg top share, "
        f"{row.avg_max_consecutive_weeks:.2f} avg max consecutive"
    )


def main(fecha_inicio: datetime):
    df_raw = load_raw_availability_data()
    df_clean = clean_availability_data(df_raw)

    clean_output_path = INTERIM_DIR / "availability_clean.csv"
    save_csv(df_clean, clean_output_path)

    print(f"Clean data saved to: {clean_output_path}")
    print(df_clean.shape)

    valid_plans = plans_generator(df_clean, fecha_inicio, max_options=5, n_iter=10_000)
    cleaned_plans = {
        seed: clean_generated_plan_data(plan)
        for seed, plan in valid_plans.items()
    }

    if cleaned_plans:

        summary_df, _, best_plan_id = evaluate_plan_collection(cleaned_plans, DEFAULT_WEIGHTS)

        if not summary_df.empty and best_plan_id is not None:
            # Plan Ranking
            print("\nPlan Evaluation Results in descending order of overall score:")
            for row in summary_df.itertuples(index=False):
                print(f"\nPlan {row.plan_id}:")
                print(f"  Overall Score: {row.overall_score:.2f}")
                print(f"  --> Coverage: {row.coverage_score:.2f}")
                print(f"  --> Equity: {row.equity_score:.2f}")
                print(f"  --> Rest: {row.rest_score:.2f}")
                print(f"  --> Resilience: {row.resilience_score:.2f}")

            # Best Plan Details
            best_row = next(
                summary_df.loc[summary_df["plan_id"] == best_plan_id].itertuples(index=False)
            )
            print(f"\nBest plan: {best_row.plan_id} with overall score {best_row.overall_score:.2f}")
            _print_plan_summary(best_row, prefix="Best plan")

            # Save Worship planning data (best plan data)
            best_plan = cleaned_plans[best_plan_id]
            start = best_plan[DATE_COL].min().strftime("%Y-%m-%d")
            end = best_plan[DATE_COL].max().strftime("%Y-%m-%d")

            best_plan_output_path = OUTPUTS_DIR / f"worship_planning_{start}_{end}.xlsx"
            save_excel(best_plan, best_plan_output_path)
            print(f"\nWorship planning data saved to: {best_plan_output_path}")

            # Generate and save worship planning infographic (best plan infographic)
            infographic_html = build_plan_infographic_html(
                best_plan,
            )
            infographic_path = OUTPUTS_DIR / f"worship_planning_{start}_{end}.html"
            save_text(infographic_html, infographic_path)
            print(f"\nWorship planning HTML infographic exported to: {infographic_path}")

            # Save all plans
            replace_processed_plans(cleaned_plans, PROCESSED_DIR)
            print(f"\n{len(cleaned_plans)} plan options saved to: {PROCESSED_DIR}")

        else:
            print("Plans were generated but evaluation failed to produce valid results. Previous results were kept.")

    else:
        print("No valid plans were generated. Previous results were kept.")


if __name__ == "__main__":
    args = parse_args()
    fecha_inicio = datetime.strptime(args.fecha_inicio, "%Y-%m-%d")
    main(fecha_inicio)
