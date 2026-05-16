from datetime import timedelta

import numpy as np
import pandas as pd

import src.planning.filters as filters
from src.planning.schema import (
    BASSIST_COL,
    DIRECTOR_COL,
    DRUMMER_COL,
    GUITARIST_COL,
    KEYBOARDIST_COL,
    REHEARSAL_DATE_COL,
    REHEARSAL_TIME_COL,
    REQUIRED_PLAN_ROLE_COLS,
    SERVICE_DATE_COL,
    VOCALIST_1_COL,
    VOCALIST_2_COL,
)


def generate_planning_dates(start_date, director_count):
    if start_date.weekday() != 6:
        raise ValueError("start_date must be a Sunday service date.")

    warmup_weeks = director_count * 4
    plan_weeks = director_count * 2
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


def select_best_band_for_week(
    shuffled_df,
    team_members,
    director_count,
    saturday_date,
    week_roles,
    week_meta,
    week_index,
):
    available = filters.get_weekly_available_members(shuffled_df, saturday_date, week_index)
    available_directors = filters.get_available_directors(available, week_index, director_count)

    selected_band = pd.DataFrame()
    director_index = np.nan
    rehearsal_time = np.nan

    for possible_director_index in available_directors.index:
        possible_director = available_directors.loc[possible_director_index, "name_norm"]
        available_band = filters.get_available_band(
            available,
            possible_director_index,
            week_index,
            director_count,
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

        possible_band, possible_rehearsal_time = filters.select_rehearsal_time(
            available,
            possible_director_index,
            available_band,
        )

        if len(possible_band) > len(selected_band):
            selected_band = possible_band
            director_index = possible_director_index
            rehearsal_time = possible_rehearsal_time

    if selected_band.empty or np.isnan(director_index):
        return

    week_roles[DIRECTOR_COL] = available_directors.loc[director_index, "name"]
    week_meta[REHEARSAL_TIME_COL] = rehearsal_time

    select_musicians(selected_band, week_roles)
    select_vocalists(selected_band, week_roles)
    update_participation_tracking(shuffled_df, week_roles, week_index)


def generate_plans(df, start_date, max_options=5, n_iter=10_000):
    df = df.copy()

    team_members = df["name_norm"].unique().tolist()
    directors = df[df["director"] == 1]["name_norm"].unique().tolist()
    director_count = len(directors)

    if director_count == 0:
        return {}

    saturday_dates, sunday_dates, plan_weeks, total_weeks = generate_planning_dates(
        start_date,
        director_count,
    )

    valid_plans = {}

    for _ in range(n_iter):
        df["last_participation"] = -99
        df["last_direction"] = -99

        seed = np.random.randint(0, 1_000_000)
        shuffled_df = df.sample(frac=1, random_state=seed)

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
            )

            plan_rows.append({**week_meta, **week_roles})

        plan = pd.DataFrame(plan_rows[-plan_weeks:])

        if not plan[list(REQUIRED_PLAN_ROLE_COLS)].isna().any().any():
            plan_id = len(valid_plans) + 1
            valid_plans[plan_id] = plan.copy()
            if len(valid_plans) == max_options:
                break

    print(f"{len(valid_plans)} plans generated.")
    return valid_plans


plans_generator = generate_plans
