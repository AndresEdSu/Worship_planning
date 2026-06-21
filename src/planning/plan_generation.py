from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

import numpy as np
import pandas as pd

import src.planning.filters as filters
from src.planning.frequency_policy import FrequencyPolicy
from src.planning.relaxation_policy import MAX_RELAXATION_LEVEL, RelaxationPolicy
from src.planning.schema import (
    BASSIST_COL,
    DIRECTOR_COL,
    DRUMMER_COL,
    GUITARIST_COL,
    KEYBOARDIST_COL,
    REHEARSAL_DATE_COL,
    REHEARSAL_TIME_COL,
    SERVICE_DATE_COL,
    VOCALIST_1_COL,
    VOCALIST_2_COL,
)


MAX_AUTO_WARMUP_WEEKS = 16


@dataclass(frozen=True)
class PlanGenerationAttempt:
    relaxation_level: int
    iterations: int
    plans_found: int
    elapsed_seconds: float
    stopped_by_time_limit: bool


@dataclass(frozen=True)
class PlanGenerationReport:
    max_options: int
    n_iter: int
    max_relaxation: int
    relax_after_seconds: float | None
    plan_weeks: int
    warmup_weeks: int
    director_count: int
    frequency_max: int
    total_elapsed_seconds: float
    attempts: tuple[PlanGenerationAttempt, ...]
    plan_relaxation_levels: dict[int, int]

    @property
    def used_relaxation(self) -> bool:
        return any(level > 0 for level in self.plan_relaxation_levels.values())

    @property
    def highest_relaxation_level(self) -> int | None:
        if not self.plan_relaxation_levels:
            return None
        return max(self.plan_relaxation_levels.values())

    def to_lines(self) -> list[str]:
        relax_after = (
            f"{self.relax_after_seconds:.1f}s"
            if self.relax_after_seconds is not None
            else "iteration limit only"
        )
        lines = [
            "Plan generation report:",
            f"- Requested options: {self.max_options}",
            f"- Iterations per relaxation level: {self.n_iter}",
            f"- Max relaxation level: {self.max_relaxation}",
            f"- Relax after: {relax_after}",
            f"- Plan weeks: {self.plan_weeks}",
            f"- Warmup weeks: {self.warmup_weeks}",
            f"- Director count: {self.director_count}",
            f"- Frequency max: {self.frequency_max}",
            f"- Total elapsed: {self.total_elapsed_seconds:.1f}s",
        ]

        for attempt in self.attempts:
            reason = "time limit" if attempt.stopped_by_time_limit else "iteration/options limit"
            policy = RelaxationPolicy.from_level(attempt.relaxation_level)
            lines.append(
                "- Level "
                f"{attempt.relaxation_level}: {attempt.plans_found} plan(s), "
                f"{attempt.iterations} iteration(s), {attempt.elapsed_seconds:.1f}s, "
                f"stopped by {reason}"
            )
            lines.append(f"  Policy: {policy.summary(self.director_count)}")

        if self.plan_relaxation_levels:
            plan_levels = ", ".join(
                f"Plan {plan_id}=level {level}"
                for plan_id, level in sorted(self.plan_relaxation_levels.items())
            )
            lines.append(f"- Plan relaxation levels: {plan_levels}")
        else:
            lines.append("- Plan relaxation levels: none")

        if not self.plan_relaxation_levels:
            lines.append("- No valid plans were generated.")
        elif self.used_relaxation:
            lines.append(
                "- Planning relaxation was used. Original frequency values were not changed."
            )
        else:
            lines.append("- Planning relaxation was not needed.")

        return lines

    def to_text(self) -> str:
        return "\n".join(self.to_lines())


@dataclass(frozen=True)
class PlanGenerationResult:
    plans: dict[int, pd.DataFrame]
    report: PlanGenerationReport


def calculate_plan_weeks_from_dates(start_date, end_date) -> int:
    if start_date.weekday() != 6:
        raise ValueError("start_date must be a Sunday service date.")
    if end_date.weekday() != 6:
        raise ValueError("end_date must be a Sunday service date.")
    if end_date < start_date:
        raise ValueError("end_date must be greater than or equal to start_date.")

    return ((end_date - start_date).days // 7) + 1


def calculate_warmup_weeks(
    director_count: int,
    plan_weeks: int,
    max_frequency: int,
    max_auto_warmup_weeks: int = MAX_AUTO_WARMUP_WEEKS,
) -> int:
    planning_frequency_warmup = min(
        max_auto_warmup_weeks,
        max(plan_weeks * 2, max_frequency * 2),
    )
    return max(director_count, planning_frequency_warmup)


def generate_planning_dates(
    start_date,
    director_count,
    plan_weeks=None,
    warmup_weeks=0,
    max_frequency=None,
):
    if start_date.weekday() != 6:
        raise ValueError("start_date must be a Sunday service date.")
    if plan_weeks is not None and plan_weeks < 1:
        raise ValueError("plan_weeks must be greater than or equal to 1.")
    if warmup_weeks is not None and warmup_weeks < 0:
        raise ValueError("warmup_weeks must be greater than or equal to 0.")

    plan_weeks = plan_weeks or director_count * 2
    max_frequency = max_frequency or FrequencyPolicy().max_frequency
    warmup_weeks = (
        warmup_weeks
        if warmup_weeks is not None
        else calculate_warmup_weeks(director_count, plan_weeks, max_frequency)
    )
    total_weeks = warmup_weeks + plan_weeks

    sunday_dates = [
        start_date - timedelta(weeks=warmup_weeks) + timedelta(weeks=index)
        for index in range(total_weeks)
    ]
    saturday_dates = [date - timedelta(days=1) for date in sunday_dates]

    return saturday_dates, sunday_dates, plan_weeks, total_weeks


def get_assigned_members(week_roles):
    return list(
        {
            member
            for member in week_roles.values()
            if pd.notna(member) and member not in {"Guest", "Invitado"}
        }
    )


def update_participation_tracking(shuffled_df, week_roles, week_index):
    assigned_members = get_assigned_members(week_roles)
    for member in assigned_members:
        shuffled_df.loc[shuffled_df["name"] == member, "last_participation"] = week_index
    if pd.notna(week_roles[DIRECTOR_COL]):
        shuffled_df.loc[
            shuffled_df["name"] == week_roles[DIRECTOR_COL],
            "last_direction",
        ] = week_index


def select_musicians(band_df, week_roles):
    priority_instruments = {
        "guitar": GUITARIST_COL,
        "drums": DRUMMER_COL,
    }

    for instrument, role in priority_instruments.items():
        assigned_members = get_assigned_members(week_roles)
        available_for_instrument = band_df[
            (band_df[instrument] == 1) & (~band_df["name"].isin(assigned_members))
        ]
        primary_available = available_for_instrument[
            available_for_instrument["primary_instrument"] == instrument
        ]

        if available_for_instrument.empty:
            continue

        if not primary_available.empty:
            musician = primary_available.loc[
                primary_available["last_participation"].idxmin(),
                "name",
            ]
        else:
            musician = available_for_instrument.loc[
                available_for_instrument["last_participation"].idxmin(),
                "name",
            ]

        week_roles[role] = musician

    secondary_instruments = {
        "bass": BASSIST_COL,
        "keyboard": KEYBOARDIST_COL,
    }

    for instrument, role in secondary_instruments.items():
        assigned_members = get_assigned_members(week_roles)
        primary_available = band_df[
            (band_df["primary_instrument"] == instrument)
            & (~band_df["name"].isin(assigned_members))
        ]

        if primary_available.empty:
            continue

        musician = primary_available.loc[
            primary_available["last_participation"].idxmin(),
            "name",
        ]
        week_roles[role] = musician


def select_vocalists(band_df, week_roles):
    assigned_members = get_assigned_members(week_roles)

    available_vocalists = band_df[
        (band_df["primary_instrument"] == "voice")
        & (~band_df["name"].isin(assigned_members))
    ]

    if not available_vocalists.empty:
        vocalist = available_vocalists.loc[
            available_vocalists["last_participation"].idxmin(),
            "name",
        ]

        if not pd.isna(week_roles[GUITARIST_COL]):
            week_roles[VOCALIST_1_COL] = vocalist
            week_roles[VOCALIST_2_COL] = week_roles[GUITARIST_COL]
        else:
            week_roles[VOCALIST_1_COL] = vocalist
    elif not pd.isna(week_roles[GUITARIST_COL]):
        week_roles[VOCALIST_1_COL] = week_roles[GUITARIST_COL]


def iter_director_rehearsal_options(available, possible_director_index, available_band):
    if available.loc[possible_director_index, "saturday_am"] == 1:
        yield "Saturday morning", available_band[available_band["saturday_am"] == 1]

    if available.loc[possible_director_index, "saturday_pm"] == 1:
        yield "Saturday afternoon", available_band[available_band["saturday_pm"] == 1]


def score_week_roles(week_roles, band_size, relaxation_policy: RelaxationPolicy):
    required_roles_filled = sum(
        pd.notna(week_roles[role])
        for role in relaxation_policy.required_roles
    )
    preferred_roles_filled = sum(
        pd.notna(week_roles[role])
        for role in relaxation_policy.preferred_roles
    )
    total_roles_filled = sum(pd.notna(member) for member in week_roles.values())
    assigned_members = len(get_assigned_members(week_roles))

    return (
        required_roles_filled,
        preferred_roles_filled,
        total_roles_filled,
        assigned_members,
        band_size,
    )


def select_best_band_for_week(
    shuffled_df,
    team_members,
    director_count,
    saturday_date,
    week_roles,
    week_meta,
    week_index,
    frequency_policy: FrequencyPolicy | None = None,
    relaxation_policy: RelaxationPolicy | None = None,
):
    frequency_policy = frequency_policy or FrequencyPolicy()
    relaxation_policy = relaxation_policy or RelaxationPolicy.from_level(0)
    director_rotation_gap = relaxation_policy.director_rotation_gap(director_count)
    available = filters.get_weekly_available_members(
        shuffled_df,
        saturday_date,
        week_index,
        frequency_policy,
    )
    available_directors = filters.get_available_directors(
        available,
        week_index,
        director_rotation_gap,
    )

    selected_score = None
    selected_roles = None
    selected_rehearsal_time = np.nan

    for possible_director_index in available_directors.index:
        possible_director = available_directors.loc[possible_director_index, "name_norm"]
        possible_director_name = available_directors.loc[possible_director_index, "name"]
        available_band = filters.get_available_band(
            available,
            possible_director_index,
            week_index,
            director_rotation_gap,
            frequency_policy,
        )

        if available_band.empty:
            continue

        available_band_names = available_band["name_norm"].values

        if not filters.represented_director_validation(
            available,
            possible_director_index,
            team_members,
            available_band_names,
        ):
            continue

        available_band = filters.filter_represented_members(
            available_band,
            possible_director,
            team_members,
            available_band_names,
        )

        if available_band.empty:
            continue

        for possible_rehearsal_time, possible_band in iter_director_rehearsal_options(
            available,
            possible_director_index,
            available_band,
        ):
            if possible_band.empty:
                continue

            possible_roles = week_roles.copy()
            possible_roles[DIRECTOR_COL] = possible_director_name
            select_musicians(possible_band, possible_roles)
            select_vocalists(possible_band, possible_roles)

            possible_score = score_week_roles(
                possible_roles,
                len(possible_band),
                relaxation_policy,
            )
            if selected_score is None or possible_score > selected_score:
                selected_score = possible_score
                selected_roles = possible_roles
                selected_rehearsal_time = possible_rehearsal_time

    if selected_roles is None:
        return

    week_roles.update(selected_roles)
    week_meta[REHEARSAL_TIME_COL] = selected_rehearsal_time
    update_participation_tracking(shuffled_df, week_roles, week_index)


def build_candidate_plan(
    df,
    team_members,
    director_count,
    saturday_dates,
    sunday_dates,
    plan_weeks,
    total_weeks,
    frequency_policy: FrequencyPolicy,
    relaxation_policy: RelaxationPolicy,
):
    working_df = df.copy()
    working_df["last_participation"] = -99
    working_df["last_direction"] = -99

    seed = np.random.randint(0, 1_000_000)
    shuffled_df = working_df.sample(frac=1, random_state=seed).copy()

    plan_rows = []

    for week_index in range(total_weeks):
        sunday_date = sunday_dates[week_index]
        saturday_date = saturday_dates[week_index]

        week_meta = {
            REHEARSAL_DATE_COL: saturday_date.date(),
            REHEARSAL_TIME_COL: np.nan,
            SERVICE_DATE_COL: sunday_date.date(),
        }

        week_roles = {
            DIRECTOR_COL: np.nan,
            GUITARIST_COL: np.nan,
            DRUMMER_COL: np.nan,
            BASSIST_COL: np.nan,
            KEYBOARDIST_COL: np.nan,
            VOCALIST_1_COL: np.nan,
            VOCALIST_2_COL: np.nan,
        }

        select_best_band_for_week(
            shuffled_df,
            team_members,
            director_count,
            saturday_date,
            week_roles,
            week_meta,
            week_index,
            frequency_policy,
            relaxation_policy,
        )

        plan_rows.append({**week_meta, **week_roles})

    return pd.DataFrame(plan_rows[-plan_weeks:])


def is_valid_plan(plan: pd.DataFrame, relaxation_policy: RelaxationPolicy) -> bool:
    return not plan[list(relaxation_policy.required_roles)].isna().any().any()


def normalize_relax_after_seconds(relax_after_seconds: float | None) -> float | None:
    if relax_after_seconds is None or relax_after_seconds <= 0:
        return None
    return relax_after_seconds


def generate_plans_with_report(
    df,
    start_date,
    max_options=5,
    n_iter=10_000,
    max_relaxation=MAX_RELAXATION_LEVEL,
    relax_after_seconds=300.0,
    plan_weeks=None,
    warmup_weeks=0,
) -> PlanGenerationResult:
    if max_options < 1:
        raise ValueError("max_options must be greater than or equal to 1.")
    if n_iter < 1:
        raise ValueError("n_iter must be greater than or equal to 1.")
    if max_relaxation < 0:
        raise ValueError("max_relaxation must be greater than or equal to 0.")
    if max_relaxation > MAX_RELAXATION_LEVEL:
        raise ValueError(
            f"max_relaxation must be less than or equal to {MAX_RELAXATION_LEVEL}."
        )
    if plan_weeks is not None and plan_weeks < 1:
        raise ValueError("plan_weeks must be greater than or equal to 1.")
    if warmup_weeks is not None and warmup_weeks < 0:
        raise ValueError("warmup_weeks must be greater than or equal to 0.")

    df = df.copy()

    team_members = df["name_norm"].unique().tolist()
    directors = df[df["director"] == 1]["name_norm"].unique().tolist()
    director_count = len(directors)
    frequency_values = pd.to_numeric(df["frequency"], errors="coerce").dropna()
    frequency_max = (
        int(frequency_values.max())
        if not frequency_values.empty
        else FrequencyPolicy().max_frequency
    )
    relax_after_seconds = normalize_relax_after_seconds(relax_after_seconds)
    resolved_plan_weeks = plan_weeks or director_count * 2
    resolved_warmup_weeks = (
        warmup_weeks
        if warmup_weeks is not None
        else calculate_warmup_weeks(
            director_count,
            resolved_plan_weeks,
            frequency_max,
        )
    )

    if director_count == 0:
        report = PlanGenerationReport(
            max_options=max_options,
            n_iter=n_iter,
            max_relaxation=max_relaxation,
            relax_after_seconds=relax_after_seconds,
            plan_weeks=0,
            warmup_weeks=0,
            director_count=0,
            frequency_max=frequency_max,
            total_elapsed_seconds=0.0,
            attempts=(),
            plan_relaxation_levels={},
        )
        return PlanGenerationResult({}, report)

    saturday_dates, sunday_dates, plan_weeks, total_weeks = generate_planning_dates(
        start_date,
        director_count,
        plan_weeks=resolved_plan_weeks,
        warmup_weeks=resolved_warmup_weeks,
        max_frequency=frequency_max,
    )

    valid_plans: dict[int, pd.DataFrame] = {}
    plan_relaxation_levels: dict[int, int] = {}
    attempts: list[PlanGenerationAttempt] = []
    generation_start = monotonic()

    for relaxation_level in range(max_relaxation + 1):
        relaxation_policy = RelaxationPolicy.from_level(relaxation_level)
        frequency_policy = FrequencyPolicy(
            relaxation_level=relaxation_policy.frequency_relaxation,
            max_frequency=frequency_max,
        )
        attempt_start = monotonic()
        iterations = 0
        plans_before_attempt = len(valid_plans)
        stopped_by_time_limit = False

        for _ in range(n_iter):
            if (
                relax_after_seconds is not None
                and monotonic() - attempt_start >= relax_after_seconds
            ):
                stopped_by_time_limit = True
                break

            iterations += 1
            plan = build_candidate_plan(
                df,
                team_members,
                director_count,
                saturday_dates,
                sunday_dates,
                plan_weeks,
                total_weeks,
                frequency_policy,
                relaxation_policy,
            )

            if is_valid_plan(plan, relaxation_policy):
                plan_id = len(valid_plans) + 1
                valid_plans[plan_id] = plan.copy()
                plan_relaxation_levels[plan_id] = relaxation_level
                if len(valid_plans) == max_options:
                    break

        attempts.append(
            PlanGenerationAttempt(
                relaxation_level=relaxation_level,
                iterations=iterations,
                plans_found=len(valid_plans) - plans_before_attempt,
                elapsed_seconds=monotonic() - attempt_start,
                stopped_by_time_limit=stopped_by_time_limit,
            )
        )

        if len(valid_plans) == max_options:
            break

    report = PlanGenerationReport(
        max_options=max_options,
        n_iter=n_iter,
        max_relaxation=max_relaxation,
        relax_after_seconds=relax_after_seconds,
        plan_weeks=plan_weeks,
        warmup_weeks=resolved_warmup_weeks,
        director_count=director_count,
        frequency_max=frequency_max,
        total_elapsed_seconds=monotonic() - generation_start,
        attempts=tuple(attempts),
        plan_relaxation_levels=plan_relaxation_levels,
    )

    print(f"{len(valid_plans)} plans generated.")
    print(report.to_text())
    return PlanGenerationResult(valid_plans, report)


def generate_plans(
    df,
    start_date,
    max_options=5,
    n_iter=10_000,
    max_relaxation=MAX_RELAXATION_LEVEL,
    relax_after_seconds=300.0,
    plan_weeks=None,
    warmup_weeks=0,
):
    result = generate_plans_with_report(
        df,
        start_date,
        max_options=max_options,
        n_iter=n_iter,
        max_relaxation=max_relaxation,
        relax_after_seconds=relax_after_seconds,
        plan_weeks=plan_weeks,
        warmup_weeks=warmup_weeks,
    )
    return result.plans


plans_generator = generate_plans
