import pandas as pd
import re
from collections import Counter
import unicodedata
from functools import partial

from src.reporting.export_infographic import DATE_REHEARSAL_COL

COLUMN_RENAME_MAP = {
    "marca_temporal": "timestamp",
    "direccion_de_correo_electronico": "correo",
    "nombre_y_apellido": "nombre",
    "director_voz_principal": "director",
    "horario_de_ensayo": "horario_ensayo",
}

def normalize_column_name(col):
    col = str(col).strip().lower()
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("utf-8")
    col = re.sub(r"[\s\-\/]+", "_", col)
    col = re.sub(r"[^a-z0-9_]", "", col)
    col = re.sub(r"_+", "_", col)
    return col.strip("_")


def normalize_text(text, mod=None, accents=True):
    """
    Normaliza texto:
    - convierte a string
    - limpia espacios al inicio/final
    - opcionalmente elimina acentos
    - aplica transformación de mayúsculas/minúsculas
    - colapsa espacios múltiples

    Parámetros
    ----------
    text : any
        Valor a normalizar.
    mod : str | None, default=None
        Transformación de texto:
        - 'upper'
        - 'lower'
        - 'capitalize'
        - 'title'
         Si None, no se aplica transformación de mayúsculas/minúsculas.
        - None
    accents : bool, default=True
        Si False, elimina acentos.

    Retorna
    -------
    str | NaN
        Texto normalizado o NaN si la entrada era nula.
    """         
    
    if pd.isna(text):
        return text

    valid_mods = {None, 'upper', 'lower', 'capitalize', 'title'}
    if mod not in valid_mods:
        raise ValueError(f"mod debe ser uno de {valid_mods}")

    text = str(text).strip()
    if text == "":
        return pd.NA

    if not accents:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(
            c for c in text
            if not unicodedata.combining(c)
        )

    if mod == 'upper':
        text = text.upper()
    elif mod == 'lower':
        text = text.lower()
    elif mod == 'capitalize':
        text = text.capitalize()
    elif mod == 'title':
        text = text.title()

    text = re.sub(r"\s+", " ", text)

    return text

#Normalizamos el texto con funciones parciales para facilitar su uso en diferentes contextos
neutral_normalizer_text = partial(normalize_text, mod=None, accents=True)
title_normalizer_text = partial(normalize_text, mod='title', accents=True)
capitalize_normalizer_text = partial(normalize_text, mod='capitalize', accents=True)
lower_normalizer_text = partial(normalize_text, mod='lower', accents=False)
upper_normalizer_text = partial(normalize_text, mod='upper', accents=False)




def count_strings(df,col,patron_extraer,n_common):
    values = df[col].astype("string").str.lower()
    matches = values.str.findall(patron_extraer).dropna()
    todos_strings = [item for sublist in matches for item in sublist]
    # Count the occurrences
    common = Counter(todos_strings)
    # Get the top n most common capitalized words/sequences
    return common.most_common(n_common)

def normalize_text_columns(df, cols, mod_normalizer):
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(mod_normalizer)
    return df

def create_instrument_flags(df):
    df = df.copy()
    instruments_col = ["voz", "guitarra", "bajo", "bateria", "teclado"]

    for instrumento in instruments_col:
        df[instrumento] = (
            df["instrumento"]
            .astype("string")
            .str.contains(instrumento, na=False, regex=False)
        ).astype(int)

    return df

def create_schedule_flags(df):
    df = df.copy()
    horarios_cols = {"sabado_am" : "sabado en la manana",
                      "sabado_pm" : "sabado en la tarde"}

    for h_col, h_str in horarios_cols.items():
        df[h_col] = (
            df["horario_ensayo"]
            .astype("string")
            .str.contains(h_str, na=False, regex=False)
        ).astype(int)

    return df

def create_saturday_flags(df):
    df = df.copy()

    sabados_cols = {"primer sabado":"sabado_1",
                    "segundo sabado":"sabado_2",
                    "tercer sabado":"sabado_3",
                    "cuarto sabado":"sabado_4",
                    "quinto sabado":"sabado_5"}
    
    df[list(sabados_cols.keys())] = 1
    for sabado in sabados_cols:
        df[sabado] = (
            ~df['dias_ocupados'].astype("string").str.contains(sabado, na=False, regex=False)
        ).astype(int)
    
    df = df.rename(columns = sabados_cols)
    return df

def map_frecuencia(df):
    df = df.copy()
    frecuencia_map = {
        "cada dos semanas": 2,
        "cada tres semanas": 3,
        "cada cuatro semanas": 4,
    }
    frecuencia_original = df["frecuencia"]
    frecuencia_mapeada = frecuencia_original.map(frecuencia_map)
    invalid_mask = frecuencia_original.notna() & frecuencia_mapeada.isna()

    if invalid_mask.any():
        invalid_values = sorted(frecuencia_original.loc[invalid_mask].astype(str).unique())
        raise ValueError(
            "Unexpected frecuencia values found: "
            f"{invalid_values}. Expected one of {sorted(frecuencia_map)}."
        )

    df["frecuencia"] = frecuencia_mapeada
    return df

def adjust_represented_availability(df):
    df = df.copy()
    availability_cols = df.loc[:, 'sabado_am':'sabado_5'].columns

    for idx in df.index:
        representante = df.loc[idx, 'representante']

        if pd.isna(representante):
            continue

        match = df.index[df['nombre_norm'].eq(representante)]

        # Si el representante no pertenece a la banda, no alteramos la disponibilidad
        if len(match) == 0:
            continue

        representante_index = match[0]

        df.loc[idx, availability_cols] = (
            df.loc[idx, availability_cols].astype(int)
            & df.loc[representante_index, availability_cols].astype(int)
        )
    return df


def clean_availability_data (df):

    df=df.copy()

    #Normalize and rename columns names:
    column_map = {c: normalize_column_name(c) for c in df.columns}
    df = df.rename(columns = column_map)
    df = df.rename(columns = COLUMN_RENAME_MAP)

    #Normalize text columns
    df['nombre_norm'] = df['nombre'].apply(lower_normalizer_text)
    df['nombre'] = df['nombre'].apply(neutral_normalizer_text)

    cols_to_low_normalize = ["representante", 
                         "horario_ensayo", 
                         "instrumento",
                         "director", 
                         "instrumento_principal",
                         "dias_ocupados",
                         "frecuencia"]
    
    df = normalize_text_columns(df, cols_to_low_normalize, lower_normalizer_text)
    
    #Director flag
    df['director'] = (df['director'] == 'si').astype(int)
    
    #Desglozando columna Instrumentos
    df = create_instrument_flags(df)
    
    #Desglozamos la columna horario de ensayo
    df = create_schedule_flags(df)
    
    #Desglozamos la columna días ocupados
    df = create_saturday_flags(df)
    #Cambiando a int columna Frecuencia
    df = map_frecuencia(df)
    
    # Disponibilidad de los representados:
    # si su representante está en la banda y no está disponible, ellos tampoco.
    df = adjust_represented_availability(df)

    #Borrar columnas innecesarias
    required_columns = ['correo',
                        'nombre',
                        'nombre_norm',
                        'representante', 
                        'director',
                        'instrumento_principal', 
                        'voz',
                        'guitarra',
                        'bajo', 
                        'bateria', 
                        'teclado',  
                        'sabado_am',
                        'sabado_pm',
                        'sabado_1', 
                        'sabado_2',
                        'sabado_3', 
                        'sabado_4', 
                        'sabado_5',
                        'frecuencia']
    optional_columns = ['sugerencias']

    missing_required_columns = [column for column in required_columns if column not in df.columns]
    if missing_required_columns:
        raise KeyError(f"Missing expected columns after cleaning: {missing_required_columns}")

    selected_columns = required_columns + [column for column in optional_columns if column in df.columns]
    df = df[selected_columns]

    return df


def clean_generated_plan_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    date_columns = ["Fecha Ensayo (Sábado)", "Fecha Presentación (Domingo)"]
    role_columns = [
        "Director",
        "Guitarrista",
        "Baterista",
        "Bajista",
        "Tecladista",
        "Corista_1",
        "Corista_2",
    ]
    text_columns = ["Horario Tentativo de Ensayo", *role_columns]
    ordered_columns = [*date_columns, "Horario Tentativo de Ensayo", *role_columns]

    for column in date_columns:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    
    df = df.sort_values(date_columns).reset_index(drop=True)

    df = normalize_text_columns(df, text_columns, neutral_normalizer_text)

    available_columns = [column for column in ordered_columns if column in df.columns]
    remaining_columns = [column for column in df.columns if column not in available_columns]

    return df[available_columns + remaining_columns]
