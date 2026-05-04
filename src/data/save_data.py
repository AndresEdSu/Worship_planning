from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.data.load_data import PROJECT_ROOT

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_csv(df: pd.DataFrame, path: str | Path, **kwargs: Any) -> Path:
    """Save a dataframe as CSV and return the output path."""
    path = Path(path)
    ensure_directory(path.parent)
    df.to_csv(path, index=False, **kwargs)
    return path


def save_excel(df: pd.DataFrame, path: str | Path, **kwargs: Any) -> Path:
    """Save a dataframe as Excel and return the output path."""
    path = Path(path)
    ensure_directory(path.parent)
    df.to_excel(path, index=False, **kwargs)
    return path


def save_text(content: str, path: str | Path, encoding: str = "utf-8") -> Path:
    """Save text content and return the output path."""
    path = Path(path)
    ensure_directory(path.parent)
    path.write_text(content, encoding=encoding)
    return path


def replace_processed_plans(
    plans: dict[int, pd.DataFrame],
    processed_dir: str | Path,
) -> list[Path]:
    """Replace generated planning option CSVs in a processed data directory."""
    processed_dir = ensure_directory(processed_dir)

    for old_file in processed_dir.glob("planning_option_*.csv"):
        old_file.unlink()

    saved_paths = []
    for seed, plan in plans.items():
        saved_paths.append(save_csv(plan, processed_dir / f"planning_option_{seed}.csv"))

    return saved_paths
