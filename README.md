# Worship Planning

Data pipeline and Streamlit dashboard for planning worship band schedules.

## Overview

Planning a worship band manually can become difficult as the team grows. It is easy to overuse the same musicians, miss availability constraints, lose visibility into participation history, and spend too much time comparing schedule options.

This project turns worship availability spreadsheets into cleaned data, generated planning options, plan evaluation metrics, and dashboard views that make the scheduling process easier to review.

## Current Features

- Loads worship availability from Excel.
- Cleans and standardizes names, roles, dates, instruments, and availability fields.
- Generates multiple planning options.
- Scores plans using coverage, equity, rest, and resilience metrics.
- Exports a lightweight HTML infographic for the selected plan.
- Provides a Streamlit dashboard to compare generated plans.

## Tech Stack

- Python
- pandas
- NumPy
- Altair
- OpenPyXL
- Pillow
- Streamlit

## Project Structure

```text
Worship_planning/
|-- app/
|   `-- streamlit_app.py
|-- data/
|   |-- raw/
|   |   `-- worship_availability_demo.xlsx
|   |-- interim/
|   `-- processed/
|-- outputs/
|-- src/
|   |-- data/
|   |   |-- clean_data.py
|   |   |-- load_data.py
|   |   `-- save_data.py
|   |-- pipeline/
|   |   `-- run_pipeline.py
|   |-- planning/
|   |   |-- filters.py
|   |   `-- plan_generation.py
|   `-- reporting/
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

- `data/raw/worship_availability_demo.xlsx` is the demo input file.
- `data/raw/worship_availability.xlsx` is treated as local/private data and ignored by Git.
- `data/interim/`, `data/processed/`, and `outputs/` contain generated artifacts and are ignored by Git.
- `notebooks/` is currently treated as local exploratory work and ignored by Git.

## Setup

Create and activate a virtual environment, then install the project dependencies:

```bash
pip install -r requirements.txt
```

## Run the Pipeline

Generate cleaned data, planning options, evaluation scores, and the HTML infographic:

```bash
python -m src.pipeline.run_pipeline --fecha-inicio 2026-01-04
```

If `--fecha-inicio` is omitted, the pipeline uses its default Sunday start date.
The start date must be a Sunday presentation date.

The pipeline reads from:

```text
data/raw/worship_availability_demo.xlsx
```

and writes generated outputs under:

```text
data/interim/
data/processed/
outputs/
```

## Run the Dashboard

After running the pipeline, launch the dashboard:

```bash
python -m streamlit run app/streamlit_app.py
```

The dashboard lets you compare generated plans, inspect the winning plan, review weekly assignments, and understand the score breakdown.

## Notes

The reusable project logic lives under `src/`. New scheduling, scoring, or reporting behavior should generally be added there first, then used from the pipeline or the Streamlit app.
