from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from src.planning.schema import (
    DIRECTOR_COL,
    DRUMMER_COL,
    GUITARIST_COL,
    VOCALIST_1_COL,
)


MAX_RELAXATION_LEVEL = 4


@dataclass(frozen=True)
class RelaxationPolicy:
    """Define what each general planning relaxation level means."""

    level: int
    frequency_relaxation: int
    director_rotation_threshold: float
    required_roles: tuple[str, ...]
    preferred_roles: tuple[str, ...] = ()

    @classmethod
    def from_level(cls, level: int) -> "RelaxationPolicy":
        policies = {
            0: cls(
                level=0,
                frequency_relaxation=0,
                director_rotation_threshold=1.0,
                required_roles=(
                    DIRECTOR_COL,
                    GUITARIST_COL,
                    DRUMMER_COL,
                    VOCALIST_1_COL,
                ),
            ),
            1: cls(
                level=1,
                frequency_relaxation=1,
                director_rotation_threshold=1.0,
                required_roles=(
                    DIRECTOR_COL,
                    GUITARIST_COL,
                    DRUMMER_COL,
                    VOCALIST_1_COL,
                ),
            ),
            2: cls(
                level=2,
                frequency_relaxation=2,
                director_rotation_threshold=0.75,
                required_roles=(
                    DIRECTOR_COL,
                    GUITARIST_COL,
                    DRUMMER_COL,
                    VOCALIST_1_COL,
                ),
            ),
            3: cls(
                level=3,
                frequency_relaxation=3,
                director_rotation_threshold=0.75,
                required_roles=(
                    DIRECTOR_COL,
                    GUITARIST_COL,
                    VOCALIST_1_COL,
                ),
                preferred_roles=(DRUMMER_COL,),
            ),
            4: cls(
                level=4,
                frequency_relaxation=4,
                director_rotation_threshold=0.60,
                required_roles=(
                    DIRECTOR_COL,
                    VOCALIST_1_COL,
                ),
                preferred_roles=(
                    GUITARIST_COL,
                    DRUMMER_COL,
                ),
            ),
        }

        if level not in policies:
            raise ValueError(
                f"relaxation level must be between 0 and {MAX_RELAXATION_LEVEL}."
            )

        return policies[level]

    def director_rotation_gap(self, director_count: int) -> int:
        if director_count < 1:
            return 0
        return max(1, ceil(director_count * self.director_rotation_threshold))

    def role_list(self, roles: tuple[str, ...]) -> str:
        return ", ".join(roles) if roles else "none"

    def summary(self, director_count: int | None = None) -> str:
        director_rotation = f"{self.director_rotation_threshold:.0%}"
        if director_count is not None:
            director_rotation = (
                f"{director_rotation} "
                f"(gap {self.director_rotation_gap(director_count)} week(s))"
            )

        return (
            f"frequency relaxation {self.frequency_relaxation}; "
            f"director rotation {director_rotation}; "
            f"required roles: {self.role_list(self.required_roles)}; "
            f"preferred roles: {self.role_list(self.preferred_roles)}"
        )
