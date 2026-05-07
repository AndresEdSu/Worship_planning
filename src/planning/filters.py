from datetime import timedelta
import calendar

import pandas as pd


def get_saturday_ordinal_column(date):
    """Return the availability column for the given Saturday of the month."""
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
        "saturday_5",
    ]

    return ordinals[weeks] if 0 <= weeks < 5 else None


def is_available_on_saturday(row, saturday_date):
    saturday_column = get_saturday_ordinal_column(saturday_date)
    if saturday_column is None:
        return False
    return row.get(saturday_column, 0) == 1


def respects_frequency(row, week_index):
    frequency = row["frequency"]
    last_participation = row["last_participation"]
    return (week_index - last_participation) >= frequency


def is_available_to_direct(row, week_index, director_count):
    director = row["director"]
    last_direction = row["last_direction"]
    return bool(director) and (week_index - last_direction) >= director_count


def is_available_to_play(row, week_index, director_count):
    last_direction = int(row["last_direction"])
    overlap_window = int(row["frequency"])

    next_direction_week = director_count + last_direction
    blocked_start = next_direction_week - overlap_window

    return not (blocked_start < week_index < next_direction_week)


def get_weekly_available_members(df, saturday_date, week_index):
    available = df.copy()
    available = available[
        available.apply(lambda row: is_available_on_saturday(row, saturday_date), axis=1)
    ]
    available = available[
        available.apply(lambda row: respects_frequency(row, week_index), axis=1)
    ]

    return available


def get_available_directors(available, week_index, director_count):
    return available[
        available.apply(lambda row: is_available_to_direct(row, week_index, director_count), axis=1)
    ]


def get_available_band(available, possible_director_index, week_index, director_count):
    available_band = available.drop(possible_director_index)
    available_band = available_band[
        available_band.apply(
            lambda row: is_available_to_play(row, week_index, director_count),
            axis=1,
        )
    ]

    return available_band


def represented_director_validation(
    available,
    possible_director_index,
    team_members,
    available_band_names,
):
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

    mask = (
        representative.isna()
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
