from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

DEFAULT_RAW_FILE = RAW_DIR / "worship_availability_demo_en.xlsx"
DEFAULT_INTERIM_FILE = INTERIM_DIR / "availability_clean.csv"
PLAN_FILE_PATTERN = re.compile(r"planning_option_(\d+)\.csv$")


def validate_path(path: str | Path) -> Path:
    """Return a normalized existing path or raise a helpful error."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path


def validate_directory(path: str | Path) -> Path:
    """Return a normalized directory path or raise if it is missing/invalid."""
    path = validate_path(path)
    if not path.is_dir():
        raise NotADirectoryError(f"Expected a directory, got: {path}")
    return path


def load_excel(path: str | Path, sheet_name: int | str = 0, **kwargs: Any) -> pd.DataFrame:
    """Load an Excel sheet from disk."""
    path = validate_path(path)
    return pd.read_excel(path, sheet_name=sheet_name, **kwargs)


def load_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Load a CSV file from disk."""
    path = validate_path(path)
    return pd.read_csv(path, **kwargs)


def load_raw_availability_data(
    path: str | Path | None = None,
    sheet_name: int | str = 0,
    **kwargs: Any,
) -> pd.DataFrame:
    """Load the raw worship availability workbook."""
    path = path or DEFAULT_RAW_FILE
    return load_excel(path, sheet_name=sheet_name, **kwargs)


def load_interim_availability_data(path: str | Path | None = None, **kwargs: Any) -> pd.DataFrame:
    """Load the cleaned interim availability data."""
    path = path or DEFAULT_INTERIM_FILE
    return load_csv(path, **kwargs)


def load_processed_plans_data(processed_dir: str | Path | None = None) -> dict[int, pd.DataFrame]:
    """Load every generated planning option keyed by its plan id."""
    processed_dir = Path(processed_dir) if processed_dir is not None else PROCESSED_DIR
    plans: dict[int, pd.DataFrame] = {}

    if not processed_dir.exists():
        return plans
    processed_dir = validate_directory(processed_dir)

    for path in sorted(processed_dir.glob("planning_option_*.csv")):
        match = PLAN_FILE_PATTERN.match(path.name)
        if match is None:
            continue
        plan_id = int(match.group(1))
        plans[plan_id] = load_csv(path)

    return plans
