import pandas as pd
import calendar
from datetime import timedelta



def number_saturday(date):
    """
    Returns which Saturday of the month a given date is (first, second, etc.)
    in Spanish, or None if the date is not a Saturday or not within the first 5 Saturdays.
    """
    if date.weekday() != calendar.SATURDAY:
        return None

    first_day = date.replace(day=1)
    first_saturday = first_day + timedelta(days=(calendar.SATURDAY - first_day.weekday() + 7) % 7)

    weeks = (date - first_saturday).days // 7

    ordinals = [
        "sabado_1",
        "sabado_2",
        "sabado_3",
        "sabado_4",
        "sabado_5"
    ]

    return ordinals[weeks] if 0 <= weeks < 5 else None


def disponibilidad_sabado (fila, fecha_sabado):
    # Verifica si la persona está disponible ese sábado

    n_sabado = number_saturday(fecha_sabado) #sábado del mes n°?

    # Check if the person is available on the given Saturday
    disponibilidad = any(col for col in fila.index if n_sabado in col.lower() and fila[col] == 1)
    if not disponibilidad:
        return False
        
    return True

def disponibilidad_frecuencia (fila, semana_idx):
    # Verifica disponibilidad según frecuencia
    frecuencia = fila["frecuencia"]
    last_=fila["ultima_participacion"]
    
    if (semana_idx - last_ ) < frecuencia:
        return False

    return True

def disponibilidad_para_dirigir (fila, semana_idx, n_directores):
    # Verifica disponibilidad para dirigir
    director =  fila['director'] 
    last_dir= fila["ultima_direccion"]

    if not director or (semana_idx - last_dir) < n_directores:
        return False
    
    return True


def disponibilidad_para_tocar(fila, semana_idx, n_directores):
    last_dir = int(fila["ultima_direccion"])
    ventana = int(fila["frecuencia"])  #ventana anti-solapamiento

    semana_prox_dir = n_directores + last_dir
    inicio_bloqueo = semana_prox_dir - ventana  # desde aquí empieza la “zona roja”

    # Bloquear semanas en [inicio_bloqueo+1, semana_prox_dir-1]
    return not (inicio_bloqueo < semana_idx < semana_prox_dir)



def get_weekly_available_members(df, fecha_sabado, semana_idx):
    #Generamos una copia de df
    df_disponibles = df.copy()
    
    #Disponibilidad sábado
    df_disponibles = df_disponibles[df_disponibles.apply(lambda fila: disponibilidad_sabado(fila, fecha_sabado), axis=1)]
    
    #Disponibilidad frecuencia
    df_disponibles = df_disponibles[df_disponibles.apply(lambda fila: disponibilidad_frecuencia(fila, semana_idx), axis=1)] 

    return df_disponibles

def get_available_directors(df_disponibles, semana_idx, n_directores):  
    #Disponibilidad para dirigir
    return  df_disponibles[df_disponibles.apply(lambda fila: disponibilidad_para_dirigir (fila, semana_idx, n_directores), axis=1)]

def get_available_band(df_disponibles, posible_director_index, semana_idx, n_directores): 
            """
            Genera banda disponible (músicos y coristas) excepto el director.
            Excluye a quienes le corresponde dirigir pronto.
            """
            df_banda_disponible = df_disponibles.drop(posible_director_index)   #Quitamos al director, solo dejamos los músicos y coristas.
            
            df_banda_disponible = df_banda_disponible[df_banda_disponible.apply(lambda fila: disponibilidad_para_tocar (fila, semana_idx, n_directores), axis=1)]  #Quitamos a los que les toca dirigir pronto.

            return df_banda_disponible

def represented_director_validation(df_disponibles, 
                                    posible_director_index,
                                    integrantes,
                                    banda_disponible_nombres):    
        """
        Validar director si es representado. Devuelve False si su representante 
        pertenece al equipo, pero no está disponible en la banda para esta fecha.
        Devuelve True si no tiene representante, su representante no pertence al equipo o
        sí tiene representante y está disponible.
        """
        representante = df_disponibles.loc[posible_director_index, 'representante']
        if not pd.isna(representante) and representante in integrantes:
            if not representante in banda_disponible_nombres:
                return False
        return True


def filter_represented_members(df_banda_disponible, 
                                    director,
                                    integrantes,
                                    banda_disponible_nombres):           
        """
        Elimina representados solo si su representante pertenece al equipo
        pero no está disponible ni es el director.
        """
        nombres_set = set(banda_disponible_nombres) | {director}
        rep = df_banda_disponible["representante"]
        
        mask = (
            rep.isna()                       # no tiene representante
            | ~rep.isin(integrantes)         # su representante no pertenece al equipo
            | rep.isin(nombres_set)          # su representante sí pertenece y está disponible o es el director
        )
        
        return df_banda_disponible.loc[mask].copy()

def select_rehearsal_time(df_disponibles, posible_director_index, df_banda_disponible):
            """
            Disponibilidad según horario de ensayo.
            """       
            if df_disponibles.loc[posible_director_index, 'sabado_am'] == 1:
                df_banda_disponible_mañana = df_banda_disponible[df_banda_disponible['sabado_am'] == 1]
            else: 
                df_banda_disponible_mañana = pd.DataFrame()
                
            if df_disponibles.loc[posible_director_index, 'sabado_pm'] == 1:
                df_banda_disponible_tarde = df_banda_disponible[df_banda_disponible['sabado_pm'] == 1]
            else: 
                df_banda_disponible_tarde = pd.DataFrame()
    
            if len(df_banda_disponible_mañana) >= len(df_banda_disponible_tarde):
                df_posible_banda = df_banda_disponible_mañana
                horario = 'Sábado en la mañana'
            else:
                df_posible_banda = df_banda_disponible_tarde
                horario = 'Sábado en la tarde'

            return df_posible_banda, horario
        