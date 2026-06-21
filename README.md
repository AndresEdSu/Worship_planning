# Worship Planning

Data pipeline and Streamlit dashboard for planning worship band schedules.

## Overview

Planning a worship band manually can become difficult as the team grows. It is easy to overuse the same musicians, miss availability constraints, lose visibility into participation history, and spend too much time comparing schedule options.

This project turns worship availability spreadsheets into cleaned data, generated planning options, plan evaluation metrics, and dashboard views that make the scheduling process easier to review.

## App Preview

### Plan Comparison

![Worship planning dashboard comparison view](docs/images/worship_planning_dashboard_comparison.png)

### Monthly Plan View

![Worship planning dashboard monthly plan view](docs/images/worship_planning_dashboard_plan_view.png)

### Availability Profile

![Worship planning dashboard availability profile](docs/images/worship_planning_dashboard_availability.png)

## Current Features

- Loads worship availability from Excel.
- Cleans and standardizes names, roles, instruments, schedules, frequencies, and availability fields.
- Supports English and Spanish source-column aliases.
- Applies representative-attendance constraints only when explicitly required per member.
- Generates multiple planning options across progressive relaxation levels.
- Supports planning by week count or by an inclusive Sunday date range.
- Scores plans using coverage, equity, rest, and resilience metrics.
- Writes a generation report describing attempts and relaxation policies used.
- Exports a lightweight monthly HTML plan view.
- Provides a Streamlit dashboard to compare generated plans, inspect plan details, preview the monthly plan view, and review availability.

## Tech Stack

- Python
- pandas
- NumPy
- Altair
- OpenPyXL
- Streamlit

## Project Structure

```text
Worship_planning/
|-- app/
|   `-- streamlit_app.py
|-- data/
|   |-- raw/
|   |   `-- worship_availability_demo_en.xlsx
|   |-- interim/
|   `-- processed/
|-- docs/
|   `-- images/
|-- outputs/
|-- src/
|   |-- data/
|   |   |-- clean_data.py
|   |   |-- load_data.py
|   |   `-- save_data.py
|   |-- pipeline/
|   |   `-- run_pipeline.py
|   |-- planning/
|   |   |-- frequency_policy.py
|   |   |-- filters.py
|   |   |-- plan_generation.py
|   |   |-- relaxation_policy.py
|   |   `-- schema.py
|   `-- reporting/
|       |-- availability_profile.py
|       |-- dashboard_view.py
|       |-- evaluation_metrics.py
|       |-- export_infographic.py
|       `-- plan_evaluation.py
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Data Policy

The repository is organized around lowercase directory names.

- `data/raw/worship_availability_demo_en.xlsx` is the default demo input file.
- `data/raw/worship_availability.xlsx` is treated as local/private data and ignored by Git.
- `data/interim/`, `data/processed/`, and `outputs/` contain generated artifacts that can be refreshed by the pipeline.
- `notebooks/` is currently treated as local exploratory work and ignored by Git.

## Setup

Create and activate a virtual environment, then install the project dependencies:

```bash
pip install -r requirements.txt
```

## Run the Pipeline

Generate cleaned data, planning options, evaluation scores, and the HTML infographic:

```bash
python -m src.pipeline.run_pipeline --raw-path data/raw/worship_availability_demo_en.xlsx --start-date 2026-07-05 --end-date 2026-08-30 --relax-after-seconds 120
```

If `--start-date` is omitted, the pipeline uses its default Sunday start date.
All service dates must be Sundays.

### Planning Range

Use `--end-date` to generate an inclusive Sunday-to-Sunday range:

```bash
python -m src.pipeline.run_pipeline --start-date 2026-07-05 --end-date 2026-08-30
```

Both dates must be Sundays. `--end-date` and `--plan-weeks` cannot be used together.

Alternatively, provide a number of service weeks:

```bash
python -m src.pipeline.run_pipeline --start-date 2026-07-05 --plan-weeks 9
```

If neither option is provided, the plan defaults to `director_count * 2` weeks.

### Relaxation Levels

The generator starts at level 0 and moves upward only when it cannot find enough valid plans. `--max-relaxation` defaults to 4.

| Level | Frequency | Director rotation | Required roles | Preferred roles |
|---|---|---|---|---|
| 0 | Strict | 100% rotation gap | Director, Guitarist, Drummer, Vocalist_1 | None |
| 1 | Slightly relaxed | 100% rotation gap | Director, Guitarist, Drummer, Vocalist_1 | None |
| 2 | More relaxed | 75% rotation gap | Director, Guitarist, Drummer, Vocalist_1 | None |
| 3 | Strongly relaxed | 75% rotation gap | Director, Guitarist, Vocalist_1 | Drummer |
| 4 | Maximum configured relaxation | 60% rotation gap | Director, Vocalist_1 | Guitarist, Drummer |

The source frequency values are never modified. Relaxation only changes the effective constraints used during generation.

### Generation Controls

- `--n-iter`: maximum attempts per relaxation level; defaults to `10000`.
- `--relax-after-seconds`: time limit per relaxation level; defaults to `300`. Use `0` to rely only on `--n-iter`.
- `--warmup-weeks`: simulated pre-planning history; defaults to `0`.
- `--max-relaxation`: highest allowed planning relaxation level, from `0` to `4`.

Run `python -m src.pipeline.run_pipeline --help` for the complete CLI reference.

## Representative Attendance

The optional representative-presence field is supported in both languages:

```text
requires_representative_present
Requiere representante presente
```

Accepted true values include `yes`, `y`, `true`, `si`, `s`, and `1`. Empty and false values do not require the representative to attend.

When presence is required, the represented member and representative must share the same Saturday availability and rehearsal time. The planner also requires the representative to be present in that week's team.

## Generated Files

The pipeline reads from:

```text
data/raw/worship_availability_demo_en.xlsx
```

and writes generated outputs under:

```text
data/interim/availability_clean.csv
data/processed/planning_option_*.csv
outputs/plan_generation_report.txt
outputs/worship_planning_<start>_<end>.xlsx
outputs/worship_planning_<start>_<end>.html
```

## Run the Dashboard

After running the pipeline, launch the dashboard:

```bash
python -m streamlit run app/streamlit_app.py
```

The dashboard lets you compare generated plans, inspect the winning plan, review weekly assignments, preview and download the monthly HTML plan view, and understand the score breakdown.

## Notes

The reusable project logic lives under `src/`. New scheduling, scoring, or reporting behavior should generally be added there first, then used from the pipeline or the Streamlit app.
