from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FrequencyPolicy:
    """Translate stored frequency into the effective planning constraint."""

    relaxation_level: int = 0
    min_frequency: int = 1
    max_frequency: int = 4

    def __post_init__(self) -> None:
        if self.relaxation_level < 0:
            raise ValueError("relaxation_level must be greater than or equal to 0.")
        if self.min_frequency < 1:
            raise ValueError("min_frequency must be greater than or equal to 1.")
        if self.max_frequency < self.min_frequency:
            raise ValueError("max_frequency must be greater than or equal to min_frequency.")

    def effective_frequency(self, frequency) -> int | None:
        if pd.isna(frequency):
            return None

        try:
            original_frequency = int(frequency)
        except (TypeError, ValueError):
            return None

        target_ceiling = max(self.min_frequency, self.max_frequency - self.relaxation_level)
        return max(self.min_frequency, min(original_frequency, target_ceiling))

    def respects_frequency(self, row, week_index: int) -> bool:
        effective_frequency = self.effective_frequency(row["frequency"])
        if effective_frequency is None or pd.isna(row["last_participation"]):
            return False

        return (week_index - int(row["last_participation"])) >= effective_frequency

    def overlap_window(self, row) -> int | None:
        return self.effective_frequency(row["frequency"])
