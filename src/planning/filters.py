from datetime import timedelta
import calendar

import pandas as pd

from src.planning.frequency_policy import FrequencyPolicy


TRUE_VALUES = {"yes", "y", "true", "si", "s", "1"}


def get_saturday_ordinal_column(date):
    """Return the first-through-fourth availability column for the Saturday."""
    if date.weekday() != calendar.SATURDAY:
        return None

    first_day = date.replace(day=1)
    first_saturday = first_day + timedelta(
        days=(calendar.SATURDAY - first_day.weekday() + 7) % 7
    )
    weeks = (date - first_saturday).days // 7

    ordinals = [
        "saturday_1",
        "saturday_2",
        "saturday_3",
        "saturday_4",
    ]

    return ordinals[weeks] if 0 <= weeks < 4 else None


def is_last_saturday_of_month(date):
    if date.weekday() != calendar.SATURDAY:
        return False
    return (date + timedelta(days=7)).month != date.month


def get_saturday_availability_columns(date):
    if date.weekday() != calendar.SATURDAY:
        return []

    columns = []
    ordinal_column = get_saturday_ordinal_column(date)
    if ordinal_column is not None:
        columns.append(ordinal_column)

    if is_last_saturday_of_month(date):
        columns.append("last_saturday")

    return columns


def is_available_on_saturday(row, saturday_date):
    saturday_columns = get_saturday_availability_columns(saturday_date)
    if not saturday_columns:
        return False
    return all(row.get(saturday_column, 0) == 1 for saturday_column in saturday_columns)


def respects_frequency(row, week_index, frequency_policy: FrequencyPolicy | None = None):
    frequency_policy = frequency_policy or FrequencyPolicy()
    return frequency_policy.respects_frequency(row, week_index)


def is_available_to_direct(row, week_index, director_rotation_gap):
    director = row["director"]
    last_direction = row["last_direction"]
    return bool(director) and (week_index - last_direction) >= director_rotation_gap


def is_available_to_play(
    row,
    week_index,
    director_rotation_gap,
    frequency_policy: FrequencyPolicy | None = None,
):
    frequency_policy = frequency_policy or FrequencyPolicy()
    last_direction = int(row["last_direction"])
    overlap_window = frequency_policy.overlap_window(row)
    if overlap_window is None:
        return False

    next_direction_week = director_rotation_gap + last_direction
    blocked_start = next_direction_week - overlap_window

    return not (blocked_start < week_index < next_direction_week)


def get_weekly_available_members(
    df,
    saturday_date,
    week_index,
    frequency_policy: FrequencyPolicy | None = None,
):
    frequency_policy = frequency_policy or FrequencyPolicy()
    available = df.copy()
    available = available[
        available.apply(lambda row: is_available_on_saturday(row, saturday_date), axis=1)
    ]
    available = available[
        available.apply(
            lambda row: respects_frequency(row, week_index, frequency_policy),
            axis=1,
        )
    ]

    return available


def get_available_directors(available, week_index, director_rotation_gap):
    return available[
        available.apply(
            lambda row: is_available_to_direct(row, week_index, director_rotation_gap),
            axis=1,
        )
    ]


def get_available_band(
    available,
    possible_director_index,
    week_index,
    director_rotation_gap,
    frequency_policy: FrequencyPolicy | None = None,
):
    frequency_policy = frequency_policy or FrequencyPolicy()
    available_band = available.drop(possible_director_index)
    available_band = available_band[
        available_band.apply(
            lambda row: is_available_to_play(
                row,
                week_index,
                director_rotation_gap,
                frequency_policy,
            ),
            axis=1,
        )
    ]

    return available_band


def requires_representative_presence(row):
    value = row.get("requires_representative_present", 0)
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return bool(value)


def represented_director_validation(
    available,
    possible_director_index,
    team_members,
    available_band_names,
):
    possible_director = available.loc[possible_director_index]
    if not requires_representative_presence(possible_director):
        return True

    representative = available.loc[possible_director_index, "representative"]
    if not pd.isna(representative) and representative in team_members:
        if representative not in available_band_names:
            return False
    return True


def filter_represented_members(
    available_band,
    director,
    team_members,
    available_band_names,
):
    present_names = set(available_band_names) | {director}
    representative = available_band["representative"]
    requires_presence = available_band.apply(requires_representative_presence, axis=1)

    mask = (
        ~requires_presence
        | representative.isna()
        | ~representative.isin(team_members)
        | representative.isin(present_names)
    )

    return available_band.loc[mask].copy()


def select_rehearsal_time(available, possible_director_index, available_band):
    if available.loc[possible_director_index, "saturday_am"] == 1:
        morning_band = available_band[available_band["saturday_am"] == 1]
    else:
        morning_band = pd.DataFrame()

    if available.loc[possible_director_index, "saturday_pm"] == 1:
        afternoon_band = available_band[available_band["saturday_pm"] == 1]
    else:
        afternoon_band = pd.DataFrame()

    if len(morning_band) >= len(afternoon_band):
        selected_band = morning_band
        rehearsal_time = "Saturday morning"
    else:
        selected_band = afternoon_band
        rehearsal_time = "Saturday afternoon"

    return selected_band, rehearsal_time
