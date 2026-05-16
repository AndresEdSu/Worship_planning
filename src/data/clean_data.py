from collections import Counter
from functools import partial
import re
import unicodedata

import pandas as pd

from src.planning.schema import PLAN_DATE_COLS, PLAN_ROLE_COLS, REHEARSAL_TIME_COL


COLUMN_RENAME_MAP = {
    "marca_temporal": "timestamp",
    "direccion_de_correo_electronico": "email",
    "nombre_y_apellido": "name",
    "first_and_last_name": "name",
    "nombre": "name",
    "representante": "representative",
    "instrumento": "instrument",
    "instrumento_principal": "primary_instrument",
    "director_voz_principal": "director",
    "director_lead_vocals": "director",
    "horario_de_ensayo": "rehearsal_schedule",
    "frecuencia": "frequency",
    "dias_ocupados": "unavailable_days",
    "sugerencias": "suggestions",
}

INSTRUMENT_ALIASES = {
    "voice": ("voice", "vocals", "vocal", "voz"),
    "guitar": ("guitar", "guitarra"),
    "bass": ("bass", "bajo"),
    "drums": ("drums", "drum", "bateria"),
    "keyboard": ("keyboard", "keys", "teclado"),
}

SCHEDULE_ALIASES = {
    "saturday_am": ("saturday morning", "sabado en la manana"),
    "saturday_pm": (
        "saturday afternoon",
        "saturday at noon",
        "saturday noon",
        "sabado en la tarde",
        "sabado al mediodia",
    ),
}

SATURDAY_UNAVAILABLE_ALIASES = {
    "saturday_1": ("first saturday", "primer sabado"),
    "saturday_2": ("second saturday", "segundo sabado"),
    "saturday_3": ("third saturday", "tercer sabado"),
    "saturday_4": ("fourth saturday", "cuarto sabado"),
    "saturday_5": ("fifth saturday", "quinto sabado"),
}

FREQUENCY_MAP = {
    "every two weeks": 2,
    "every 2 weeks": 2,
    "cada dos semanas": 2,
    "every three weeks": 3,
    "every 3 weeks": 3,
    "cada tres semanas": 3,
    "every four weeks": 4,
    "every 4 weeks": 4,
    "cada cuatro semanas": 4,
}

TRUE_VALUES = {"yes", "y", "true", "si", "s", "1"}

def normalize_column_name(col):
    col = str(col).strip().lower()
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("utf-8")
    col = re.sub(r"[\s\-\/]+", "_", col)
    col = re.sub(r"[^a-z0-9_]", "", col)
    col = re.sub(r"_+", "_", col)
    return col.strip("_")


def normalize_text(text, mod=None, accents=True):
    """
    Normalize a text value by trimming whitespace, optionally removing accents,
    optionally changing case, and collapsing repeated spaces.
    """
    if pd.isna(text):
        return text

    valid_mods = {None, "upper", "lower", "capitalize", "title"}
    if mod not in valid_mods:
        raise ValueError(f"mod must be one of {valid_mods}")

    text = str(text).strip()
    if text == "":
        return pd.NA

    if not accents:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))

    if mod == "upper":
        text = text.upper()
    elif mod == "lower":
        text = text.lower()
    elif mod == "capitalize":
        text = text.capitalize()
    elif mod == "title":
        text = text.title()

    return re.sub(r"\s+", " ", text)


neutral_normalizer_text = partial(normalize_text, mod=None, accents=True)
title_normalizer_text = partial(normalize_text, mod="title", accents=True)
capitalize_normalizer_text = partial(normalize_text, mod="capitalize", accents=True)
lower_normalizer_text = partial(normalize_text, mod="lower", accents=False)
upper_normalizer_text = partial(normalize_text, mod="upper", accents=False)


def count_strings(df, col, extract_pattern, n_common):
    values = df[col].astype("string").str.lower()
    matches = values.str.findall(extract_pattern).dropna()
    strings = [item for sublist in matches for item in sublist]
    return Counter(strings).most_common(n_common)


def normalize_text_columns(df, cols, mod_normalizer):
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(mod_normalizer)
    return df


def _contains_any(series: pd.Series, aliases: tuple[str, ...]) -> pd.Series:
    text = series.astype("string").fillna("")
    mask = pd.Series(False, index=series.index)
    for alias in aliases:
        mask = mask | text.str.contains(alias, na=False, regex=False)
    return mask


def _canonicalize_primary_instrument(value):
    if pd.isna(value):
        return pd.NA

    text = str(value)
    for instrument, aliases in INSTRUMENT_ALIASES.items():
        if any(alias in text for alias in aliases):
            return instrument
    return text


def create_instrument_flags(df):
    df = df.copy()

    for instrument, aliases in INSTRUMENT_ALIASES.items():
        df[instrument] = _contains_any(df["instrument"], aliases).astype(int)

    df["primary_instrument"] = df["primary_instrument"].apply(_canonicalize_primary_instrument)
    return df


def create_schedule_flags(df):
    df = df.copy()

    for schedule_col, aliases in SCHEDULE_ALIASES.items():
        df[schedule_col] = _contains_any(df["rehearsal_schedule"], aliases).astype(int)

    return df


def create_saturday_flags(df):
    df = df.copy()

    for saturday_col, aliases in SATURDAY_UNAVAILABLE_ALIASES.items():
        df[saturday_col] = (~_contains_any(df["unavailable_days"], aliases)).astype(int)

    return df


def map_frequency(df):
    df = df.copy()
    original_frequency = df["frequency"]
    mapped_frequency = original_frequency.map(FREQUENCY_MAP)
    invalid_mask = original_frequency.notna() & mapped_frequency.isna()

    if invalid_mask.any():
        invalid_values = sorted(original_frequency.loc[invalid_mask].astype(str).unique())
        raise ValueError(
            "Unexpected frequency values found: "
            f"{invalid_values}. Expected one of {sorted(FREQUENCY_MAP)}."
        )

    df["frequency"] = mapped_frequency
    return df


def adjust_represented_availability(df):
    df = df.copy()
    availability_cols = [
        "saturday_am",
        "saturday_pm",
        "saturday_1",
        "saturday_2",
        "saturday_3",
        "saturday_4",
        "saturday_5",
    ]

    for idx in df.index:
        representative = df.loc[idx, "representative"]

        if pd.isna(representative):
            continue

        match = df.index[df["name_norm"].eq(representative)]

        if len(match) == 0:
            continue

        representative_index = match[0]
        df.loc[idx, availability_cols] = (
            df.loc[idx, availability_cols].astype(int)
            & df.loc[representative_index, availability_cols].astype(int)
        )

    return df


def clean_availability_data(df):
    df = df.copy()

    column_map = {column: normalize_column_name(column) for column in df.columns}
    df = df.rename(columns=column_map)
    df = df.rename(columns=COLUMN_RENAME_MAP)

    required_raw_columns = {
        "email",
        "name",
        "representative",
        "instrument",
        "primary_instrument",
        "director",
        "rehearsal_schedule",
        "frequency",
        "unavailable_days",
    }
    missing_raw_columns = sorted(required_raw_columns - set(df.columns))
    if missing_raw_columns:
        raise KeyError(f"Missing expected columns in raw availability data: {missing_raw_columns}")

    df["name_norm"] = df["name"].apply(lower_normalizer_text)
    df["name"] = df["name"].apply(neutral_normalizer_text)

    cols_to_lower_normalize = [
        "representative",
        "rehearsal_schedule",
        "instrument",
        "director",
        "primary_instrument",
        "unavailable_days",
        "frequency",
    ]
    df = normalize_text_columns(df, cols_to_lower_normalize, lower_normalizer_text)

    df["director"] = df["director"].isin(TRUE_VALUES).astype(int)

    df = create_instrument_flags(df)
    df = create_schedule_flags(df)
    df = create_saturday_flags(df)
    df = map_frequency(df)
    df = adjust_represented_availability(df)

    required_columns = [
        "email",
        "name",
        "name_norm",
        "representative",
        "director",
        "primary_instrument",
        "voice",
        "guitar",
        "bass",
        "drums",
        "keyboard",
        "saturday_am",
        "saturday_pm",
        "saturday_1",
        "saturday_2",
        "saturday_3",
        "saturday_4",
        "saturday_5",
        "frequency",
    ]
    optional_columns = ["suggestions"]

    missing_required_columns = [column for column in required_columns if column not in df.columns]
    if missing_required_columns:
        raise KeyError(f"Missing expected columns after cleaning: {missing_required_columns}")

    selected_columns = required_columns + [column for column in optional_columns if column in df.columns]
    return df[selected_columns]


def clean_generated_plan_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    date_columns = list(PLAN_DATE_COLS)
    role_columns = list(PLAN_ROLE_COLS)
    text_columns = [REHEARSAL_TIME_COL, *role_columns]
    ordered_columns = [*date_columns, REHEARSAL_TIME_COL, *role_columns]

    for column in date_columns:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")

    available_date_columns = [column for column in date_columns if column in df.columns]
    if available_date_columns:
        df = df.sort_values(available_date_columns).reset_index(drop=True)

    df = normalize_text_columns(df, text_columns, neutral_normalizer_text)

    available_columns = [column for column in ordered_columns if column in df.columns]
    remaining_columns = [column for column in df.columns if column not in available_columns]

    return df[available_columns + remaining_columns]
