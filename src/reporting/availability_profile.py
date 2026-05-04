from __future__ import annotations

import pandas as pd


INSTRUMENT_FLAG_LABELS = {
    "voz": "Voice",
    "guitarra": "Guitar",
    "bajo": "Bass",
    "bateria": "Drums",
    "teclado": "Keyboard",
}
SCHEDULE_LABELS = {
    "sabado_am": "Saturday AM",
    "sabado_pm": "Saturday PM",
}
SATURDAY_LABELS = {
    "sabado_1": "First Saturday",
    "sabado_2": "Second Saturday",
    "sabado_3": "Third Saturday",
    "sabado_4": "Fourth Saturday",
    "sabado_5": "Fifth Saturday",
}
FREQUENCY_LABELS = {
    2: "Every 2 weeks",
    3: "Every 3 weeks",
    4: "Every 4 weeks",
}


def _sum_binary_column(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    return int(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _build_binary_count_df(
    df: pd.DataFrame,
    labels: dict[str, str],
    category_column: str,
) -> pd.DataFrame:
    rows = [
        {
            category_column: label,
            "Available Members": _sum_binary_column(df, column),
        }
        for column, label in labels.items()
        if column in df.columns
    ]
    return pd.DataFrame(rows)


def build_instrument_profile_df(df: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "Instrument": label,
            "Available Members": _sum_binary_column(df, column),
        }
        for column, label in INSTRUMENT_FLAG_LABELS.items()
        if column in df.columns
    ]
    return pd.DataFrame(rows)


def build_main_instrument_df(df: pd.DataFrame) -> pd.DataFrame:
    if "instrumento_principal" not in df.columns:
        return pd.DataFrame(columns=["Main Instrument", "Members"])

    counts = (
        df["instrumento_principal"]
        .fillna("missing")
        .value_counts()
        .rename_axis("Main Instrument")
        .reset_index(name="Members")
    )
    counts["Main Instrument"] = counts["Main Instrument"].str.title()
    return counts


def build_frequency_df(df: pd.DataFrame) -> pd.DataFrame:
    if "frecuencia" not in df.columns:
        return pd.DataFrame(columns=["Frequency", "Members"])

    frequency = pd.to_numeric(df["frecuencia"], errors="coerce")
    counts = frequency.value_counts(dropna=False).sort_index().rename_axis("Frequency").reset_index(name="Members")
    counts["Frequency"] = counts["Frequency"].map(FREQUENCY_LABELS).fillna(counts["Frequency"].astype(str))
    return counts


def build_limited_availability_df(df: pd.DataFrame) -> pd.DataFrame:
    saturday_cols = [column for column in SATURDAY_LABELS if column in df.columns]
    schedule_cols = [column for column in SCHEDULE_LABELS if column in df.columns]

    availability = df.copy()
    availability["saturday_options"] = availability[saturday_cols].sum(axis=1) if saturday_cols else 0
    availability["schedule_options"] = availability[schedule_cols].sum(axis=1) if schedule_cols else 0

    limited = availability.loc[
        (availability["saturday_options"] <= 1) | (availability["schedule_options"] == 0)
    ].copy()

    display_columns = [
        "nombre",
        "instrumento_principal",
        "frecuencia",
        "saturday_options",
        "schedule_options",
    ]
    available_columns = [column for column in display_columns if column in limited.columns]
    limited = limited[available_columns].rename(
        columns={
            "nombre": "Name",
            "instrumento_principal": "Main Instrument",
            "frecuencia": "Frequency",
            "saturday_options": "Saturday Options",
            "schedule_options": "Rehearsal Time Options",
        }
    )

    if "Main Instrument" in limited.columns:
        limited["Main Instrument"] = limited["Main Instrument"].fillna("missing").str.title()

    return limited.sort_values(["Saturday Options", "Rehearsal Time Options", "Name"]).reset_index(drop=True)


def build_availability_alerts(
    df: pd.DataFrame,
    limited_df: pd.DataFrame,
) -> list[str]:
    alerts = []
    director_count = _sum_binary_column(df, "director")

    if director_count < 2:
        alerts.append(f"Only {director_count} director(s) are available.")

    for column, label in {"guitarra": "guitarists", "bateria": "drummers"}.items():
        count = _sum_binary_column(df, column)
        if count < 2:
            alerts.append(f"Only {count} {label} are available.")

    for column, label in SCHEDULE_LABELS.items():
        if column in df.columns and _sum_binary_column(df, column) == 0:
            alerts.append(f"No members are available for {label}.")

    for column, label in SATURDAY_LABELS.items():
        if column in df.columns and _sum_binary_column(df, column) == 0:
            alerts.append(f"No members are available on the {label.lower()}.")

    if not limited_df.empty:
        alerts.append(f"{len(limited_df)} member(s) have limited availability.")

    return alerts


def build_availability_profile(df: pd.DataFrame) -> dict:
    limited_df = build_limited_availability_df(df)
    represented_count = int(df["representante"].notna().sum()) if "representante" in df.columns else 0

    return {
        "availability_summary": {
            "total_members": len(df),
            "directors": _sum_binary_column(df, "director"),
            "represented_members": represented_count,
            "limited_members": len(limited_df),
        },
        "instrument_df": build_instrument_profile_df(df),
        "main_instrument_df": build_main_instrument_df(df),
        "schedule_df": _build_binary_count_df(df, SCHEDULE_LABELS, "Rehearsal Time"),
        "saturday_df": _build_binary_count_df(df, SATURDAY_LABELS, "Saturday"),
        "frequency_df": build_frequency_df(df),
        "limited_df": limited_df,
        "alerts": build_availability_alerts(df, limited_df),
    }
