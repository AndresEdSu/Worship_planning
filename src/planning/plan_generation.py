from collections import Counter
from dataclasses import dataclass, field
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

INSTRUMENT_BY_ROLE = {
    GUITARIST_COL: "guitar",
    DRUMMER_COL: "drums",
    BASSIST_COL: "bass",
    KEYBOARDIST_COL: "keyboard",
}
PRIMARY_ONLY_ROLES = {
    BASSIST_COL,
    KEYBOARDIST_COL,
}
INSTRUMENT_ROLE_TIEBREAK = {
    DRUMMER_COL: 0,
    GUITARIST_COL: 1,
    BASSIST_COL: 2,
    KEYBOARDIST_COL: 3,
}


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
    plan_frequency_relaxations: dict[int, dict[str, int]] = field(default_factory=dict)

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

        if self.plan_frequency_relaxations:
            for plan_id, role_counts in sorted(self.plan_frequency_relaxations.items()):
                if not role_counts:
                    continue
                summary = ", ".join(
                    f"{role}={count}"
                    for role, count in sorted(role_counts.items())
                    if count
                )
                if summary:
                    lines.append(
                        f"- Plan {plan_id} required-role frequency fallback(s): {summary}"
                    )

        if not self.plan_relaxation_levels:
            lines.append("- No valid plans were generated.")
        elif self.used_relaxation:
            lines.append(
                "- Planning relaxation was used. Original frequency values were not changed; "
                "frequency fallback was limited to required roles."
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


def _is_role_filled(week_roles, role):
    return pd.notna(week_roles.get(role))


def _get_instrument_role_candidates(band_df, role, week_roles):
    assigned_members = get_assigned_members(week_roles)
    instrument = INSTRUMENT_BY_ROLE[role]

    if role in PRIMARY_ONLY_ROLES:
        instrument_mask = band_df["primary_instrument"] == instrument
    else:
        instrument_mask = band_df[instrument] == 1

    return band_df[instrument_mask & (~band_df["name"].isin(assigned_members))]


def _select_least_recent_instrument_candidate(candidates, instrument):
    primary_available = candidates[candidates["primary_instrument"] == instrument]
    selection_pool = primary_available if not primary_available.empty else candidates
    return selection_pool["last_participation"].idxmin()


def select_instrument_role(band_df, role, week_roles):
    if _is_role_filled(week_roles, role):
        return None

    candidates = _get_instrument_role_candidates(band_df, role, week_roles)
    if candidates.empty:
        return None

    instrument = INSTRUMENT_BY_ROLE[role]
    musician_index = _select_least_recent_instrument_candidate(candidates, instrument)
    week_roles[role] = candidates.loc[musician_index, "name"]
    return musician_index


def select_required_instrument_roles(band_df, week_roles, required_roles):
    selected_indices = {}
    remaining_roles = [
        role
        for role in required_roles
        if role in INSTRUMENT_BY_ROLE and not _is_role_filled(week_roles, role)
    ]

    while remaining_roles:
        role = min(
            remaining_roles,
            key=lambda candidate_role: (
                len(_get_instrument_role_candidates(band_df, candidate_role, week_roles)),
                INSTRUMENT_ROLE_TIEBREAK[candidate_role],
            ),
        )
        musician_index = select_instrument_role(band_df, role, week_roles)
        if musician_index is not None:
            selected_indices[role] = musician_index
        remaining_roles.remove(role)

    return selected_indices


def select_optional_instrument_roles(band_df, week_roles):
    selected_indices = {}
    for role in (GUITARIST_COL, DRUMMER_COL, BASSIST_COL, KEYBOARDIST_COL):
        musician_index = select_instrument_role(band_df, role, week_roles)
        if musician_index is not None:
            selected_indices[role] = musician_index
    return selected_indices


def select_musicians(band_df, week_roles, required_roles=()):
    selected_indices = {}
    selected_indices.update(
        select_required_instrument_roles(band_df, week_roles, required_roles)
    )
    selected_indices.update(select_optional_instrument_roles(band_df, week_roles))
    return selected_indices


def _get_vocalist_candidates(band_df, week_roles):
    assigned_members = get_assigned_members(week_roles)
    return band_df[
        (band_df["primary_instrument"] == "voice")
        & (~band_df["name"].isin(assigned_members))
    ]


def select_vocalist_from_band(band_df, week_roles):
    if _is_role_filled(week_roles, VOCALIST_1_COL):
        return None

    available_vocalists = _get_vocalist_candidates(band_df, week_roles)
    if not available_vocalists.empty:
        vocalist_index = available_vocalists["last_participation"].idxmin()
        vocalist = available_vocalists.loc[vocalist_index, "name"]

        if not pd.isna(week_roles[GUITARIST_COL]):
            week_roles[VOCALIST_1_COL] = vocalist
            week_roles[VOCALIST_2_COL] = week_roles[GUITARIST_COL]
        else:
            week_roles[VOCALIST_1_COL] = vocalist

        return vocalist_index

    return None


def select_vocalists(band_df, week_roles):
    vocalist_index = select_vocalist_from_band(band_df, week_roles)
    if vocalist_index is None and not pd.isna(week_roles[GUITARIST_COL]):
        week_roles[VOCALIST_1_COL] = week_roles[GUITARIST_COL]
    return vocalist_index


def assign_guitarist_as_second_vocalist(week_roles):
    if (
        pd.notna(week_roles[VOCALIST_1_COL])
        and pd.notna(week_roles[GUITARIST_COL])
        and pd.isna(week_roles[VOCALIST_2_COL])
        and week_roles[VOCALIST_1_COL] != week_roles[GUITARIST_COL]
    ):
        week_roles[VOCALIST_2_COL] = week_roles[GUITARIST_COL]


def iter_director_rehearsal_options(available, possible_director_index, available_band):
    if available.loc[possible_director_index, "saturday_am"] == 1:
        yield "Saturday morning", available_band[available_band["saturday_am"] == 1]

    if available.loc[possible_director_index, "saturday_pm"] == 1:
        yield "Saturday afternoon", available_band[available_band["saturday_pm"] == 1]


def filter_band_by_rehearsal_time(band_df, rehearsal_time):
    if rehearsal_time == "Saturday morning":
        return band_df[band_df["saturday_am"] == 1]
    if rehearsal_time == "Saturday afternoon":
        return band_df[band_df["saturday_pm"] == 1]
    return pd.DataFrame()


def _record_relaxed_assignment(
    role,
    musician_index,
    strict_band,
    frequency_relaxations,
):
    if musician_index is not None and musician_index not in strict_band.index:
        frequency_relaxations[role] += 1


def fill_missing_required_roles_with_relaxed_frequency(
    strict_band,
    relaxed_band,
    week_roles,
    required_roles,
    frequency_relaxations,
):
    missing_instrument_roles = [
        role
        for role in required_roles
        if role in INSTRUMENT_BY_ROLE and not _is_role_filled(week_roles, role)
    ]

    while missing_instrument_roles:
        role = min(
            missing_instrument_roles,
            key=lambda candidate_role: (
                len(
                    _get_instrument_role_candidates(
                        relaxed_band,
                        candidate_role,
                        week_roles,
                    )
                ),
                INSTRUMENT_ROLE_TIEBREAK[candidate_role],
            ),
        )
        musician_index = select_instrument_role(relaxed_band, role, week_roles)
        _record_relaxed_assignment(
            role,
            musician_index,
            strict_band,
            frequency_relaxations,
        )
        missing_instrument_roles.remove(role)

    if (
        VOCALIST_1_COL in required_roles
        and not _is_role_filled(week_roles, VOCALIST_1_COL)
    ):
        vocalist_index = select_vocalist_from_band(relaxed_band, week_roles)
        _record_relaxed_assignment(
            VOCALIST_1_COL,
            vocalist_index,
            strict_band,
            frequency_relaxations,
        )
        if vocalist_index is None and not pd.isna(week_roles[GUITARIST_COL]):
            week_roles[VOCALIST_1_COL] = week_roles[GUITARIST_COL]


def score_week_roles(
    week_roles,
    band_size,
    relaxation_policy: RelaxationPolicy,
    frequency_relaxations_used=0,
):
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
        -frequency_relaxations_used,
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
    frequency_relaxation_counts: Counter | None = None,
):
    frequency_policy = frequency_policy or FrequencyPolicy()
    relaxation_policy = relaxation_policy or RelaxationPolicy.from_level(0)
    strict_frequency_policy = FrequencyPolicy(
        relaxation_level=0,
        min_frequency=frequency_policy.min_frequency,
        max_frequency=frequency_policy.max_frequency,
    )
    director_rotation_gap = relaxation_policy.director_rotation_gap(director_count)
    saturday_available = filters.get_weekly_saturday_available_members(
        shuffled_df,
        saturday_date,
    )
    strict_available = filters.filter_by_frequency(
        saturday_available,
        week_index,
        strict_frequency_policy,
    )
    relaxed_available = filters.filter_by_frequency(
        saturday_available,
        week_index,
        frequency_policy,
    )
    strict_directors = filters.get_available_directors(
        strict_available,
        week_index,
        director_rotation_gap,
    )
    available_directors = strict_directors

    if frequency_policy.relaxation_level > 0:
        relaxed_directors = filters.get_available_directors(
            relaxed_available,
            week_index,
            director_rotation_gap,
        )
        relaxed_only_directors = relaxed_directors.drop(
            strict_directors.index,
            errors="ignore",
        )
        available_directors = pd.concat([strict_directors, relaxed_only_directors])

    selected_score = None
    selected_roles = None
    selected_rehearsal_time = np.nan
    selected_frequency_relaxations = Counter()

    for possible_director_index in available_directors.index:
        possible_director = available_directors.loc[possible_director_index, "name_norm"]
        possible_director_name = available_directors.loc[possible_director_index, "name"]
        director_uses_relaxed_frequency = (
            possible_director_index not in strict_directors.index
        )
        strict_available_band = filters.get_available_band(
            strict_available,
            possible_director_index,
            week_index,
            director_rotation_gap,
            strict_frequency_policy,
        )
        relaxed_available_band = filters.get_available_band(
            relaxed_available,
            possible_director_index,
            week_index,
            director_rotation_gap,
            frequency_policy,
        )

        if strict_available_band.empty and relaxed_available_band.empty:
            continue

        validation_band = (
            relaxed_available_band
            if director_uses_relaxed_frequency or strict_available_band.empty
            else strict_available_band
        )
        validation_band_names = validation_band["name_norm"].values

        if not filters.represented_director_validation(
            saturday_available,
            possible_director_index,
            team_members,
            validation_band_names,
        ):
            continue

        strict_available_band_names = strict_available_band["name_norm"].values
        relaxed_available_band_names = relaxed_available_band["name_norm"].values

        strict_available_band = filters.filter_represented_members(
            strict_available_band,
            possible_director,
            team_members,
            strict_available_band_names,
        )
        relaxed_available_band = filters.filter_represented_members(
            relaxed_available_band,
            possible_director,
            team_members,
            relaxed_available_band_names,
        )

        if strict_available_band.empty and relaxed_available_band.empty:
            continue

        for possible_rehearsal_time, _ in iter_director_rehearsal_options(
            saturday_available,
            possible_director_index,
            relaxed_available_band,
        ):
            strict_possible_band = filter_band_by_rehearsal_time(
                strict_available_band,
                possible_rehearsal_time,
            )
            relaxed_possible_band = filter_band_by_rehearsal_time(
                relaxed_available_band,
                possible_rehearsal_time,
            )

            if strict_possible_band.empty and relaxed_possible_band.empty:
                continue

            possible_roles = week_roles.copy()
            possible_frequency_relaxations = Counter()
            possible_roles[DIRECTOR_COL] = possible_director_name

            if director_uses_relaxed_frequency:
                possible_frequency_relaxations[DIRECTOR_COL] += 1

            select_required_instrument_roles(
                strict_possible_band,
                possible_roles,
                relaxation_policy.required_roles,
            )
            select_vocalists(strict_possible_band, possible_roles)
            fill_missing_required_roles_with_relaxed_frequency(
                strict_possible_band,
                relaxed_possible_band,
                possible_roles,
                relaxation_policy.required_roles,
                possible_frequency_relaxations,
            )
            select_optional_instrument_roles(strict_possible_band, possible_roles)
            assign_guitarist_as_second_vocalist(possible_roles)

            possible_score = score_week_roles(
                possible_roles,
                len(strict_possible_band),
                relaxation_policy,
                sum(possible_frequency_relaxations.values()),
            )
            if selected_score is None or possible_score > selected_score:
                selected_score = possible_score
                selected_roles = possible_roles
                selected_rehearsal_time = possible_rehearsal_time
                selected_frequency_relaxations = possible_frequency_relaxations

    if selected_roles is None:
        return

    week_roles.update(selected_roles)
    week_meta[REHEARSAL_TIME_COL] = selected_rehearsal_time
    if frequency_relaxation_counts is not None:
        frequency_relaxation_counts.update(selected_frequency_relaxations)
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
    frequency_relaxation_counts: Counter | None = None,
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

        week_frequency_relaxations = Counter()
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
            week_frequency_relaxations,
        )

        plan_rows.append({**week_meta, **week_roles})
        if (
            frequency_relaxation_counts is not None
            and week_index >= total_weeks - plan_weeks
        ):
            frequency_relaxation_counts.update(week_frequency_relaxations)

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
    plan_frequency_relaxations: dict[int, dict[str, int]] = {}
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
            candidate_frequency_relaxations = Counter()
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
                candidate_frequency_relaxations,
            )

            if is_valid_plan(plan, relaxation_policy):
                plan_id = len(valid_plans) + 1
                valid_plans[plan_id] = plan.copy()
                plan_relaxation_levels[plan_id] = relaxation_level
                plan_frequency_relaxations[plan_id] = dict(
                    sorted(
                        (role, count)
                        for role, count in candidate_frequency_relaxations.items()
                        if count
                    )
                )
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
        plan_frequency_relaxations=plan_frequency_relaxations,
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
