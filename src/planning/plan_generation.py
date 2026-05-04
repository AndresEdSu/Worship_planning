import pandas as pd
import numpy as np
from datetime import timedelta
import src.planning.filters as filters


# =========================
# Helpers de fechas
# =========================

def generate_planning_dates(fecha_inicio, n_directores):
    if fecha_inicio.weekday() != 6:
        raise ValueError("fecha_inicio must be a Sunday presentation date.")

    numero_semanas_pre_corrida = n_directores * 4
    numero_semanas_plan = n_directores * 2
    numero_semanas_total = numero_semanas_pre_corrida + numero_semanas_plan

    fechas_domingo = [
        fecha_inicio - timedelta(weeks=numero_semanas_pre_corrida) + timedelta(weeks=i) 
        for i in range(numero_semanas_total)]
    
    fechas_sabado = [f - timedelta(days=1) for f in fechas_domingo]

    return fechas_sabado, fechas_domingo, numero_semanas_plan, numero_semanas_total


# =========================
# Selección de músicos y coristas
# =========================

def get_assigned_members(week_roles):
    return list({member for member in week_roles.values() if pd.notna(member) and member != "Invitado"})


def update_participation_tracking(df_shuffled, week_roles, semana_idx):
    asignados = get_assigned_members(week_roles)
    for member in asignados:
        df_shuffled.loc[df_shuffled["nombre"] == member, "ultima_participacion"] = semana_idx
    if pd.notna(week_roles['Director']):
        df_shuffled.loc[df_shuffled["nombre"] == week_roles['Director'], "ultima_direccion"] = semana_idx


def select_musicians(df_banda, week_roles):

    # Seleccionamos Músicos

    #Seleccionamos Instrumentos Prioritarios
    instrumentos_prioritarios = {
        "guitarra": "Guitarrista",
        "bateria": "Baterista",
    }

    for instrumento, rol in instrumentos_prioritarios.items():

        asignados = get_assigned_members(week_roles) 

        disponibles_inst = df_banda[(df_banda[instrumento] == 1)&
                                    (~df_banda["nombre"].isin(asignados))]
        
        disponibles_inst_principal = disponibles_inst[disponibles_inst["instrumento_principal"] == instrumento]
        
        if not disponibles_inst.empty:
            if not disponibles_inst_principal.empty:
                musico = disponibles_inst_principal.loc[disponibles_inst_principal['ultima_participacion'].idxmin(),"nombre"]
            else:
                musico = disponibles_inst.loc[disponibles_inst['ultima_participacion'].idxmin(),"nombre"]
            
            week_roles[rol] = musico

    # Seleccionamos Instrumentos Secundarios
    instrumentos_secundarios = {
        "bajo": "Bajista",
        "teclado": "Tecladista",
    }

    for instrumento, rol in instrumentos_secundarios.items():
        asignados = get_assigned_members(week_roles)
        disponibles_inst_principal = df_banda[(df_banda["instrumento_principal"] == instrumento) &
                                              (~df_banda["nombre"].isin(asignados))]
        
        if not disponibles_inst_principal.empty:
            musico = disponibles_inst_principal.loc[disponibles_inst_principal['ultima_participacion'].idxmin(),"nombre"]
            
            week_roles[rol] = musico


def select_choir(df_banda, week_roles):

    asignados = get_assigned_members(week_roles) 

    # Seleccionamos vocalistas disponibles
    vocalistas_disponibles = df_banda[(df_banda["instrumento_principal"] == 'voz') & 
                                      (~df_banda["nombre"].isin(asignados))] #En principio seleccionamos solo aquellos cuyo instrumento principal sea la voz y no estén asignados
    
    if not vocalistas_disponibles.empty:
        
        corista_1 = vocalistas_disponibles.loc[vocalistas_disponibles['ultima_participacion'].idxmin(),"nombre"]
        
        if not pd.isna(week_roles['Guitarrista']):
            week_roles["Corista_1"] = corista_1  
            week_roles["Corista_2"] = week_roles["Guitarrista"] #El guitarrista será uno de los coristas siempre que esté disponible.
        else:
            week_roles["Corista_1"] = corista_1


    else:
        if not pd.isna(week_roles['Guitarrista']):
            week_roles["Corista_1"] = week_roles["Guitarrista"]  



    

# =========================
# Planificación semanal
# =========================

def select_best_band_for_week(df_shuffled, integrantes, n_directores, fecha_sabado, week_roles, week_meta, semana_idx):

    #Filtro de disponibilidad según día y frecuencia de participación
    df_disponibles = filters.get_weekly_available_members(df_shuffled, fecha_sabado, semana_idx)

    #Disponibilidad para dirigir
    df_directores_disponibles = filters.get_available_directors(df_disponibles, semana_idx, n_directores)

    #Seleccionamos el director y la banda más apropiados para esta semana.
    df_banda = pd.DataFrame()
    director_index = np.nan
    
    for posible_director_index in df_directores_disponibles.index:

        posible_director = df_directores_disponibles.loc[posible_director_index,'nombre_norm']

        #Disponibilidad para tocar
        df_banda_disponible = filters.get_available_band(df_disponibles, posible_director_index, semana_idx, n_directores)

        if df_banda_disponible.empty:
            continue
        
        # Disponibilidad de representados
        # Saltar director si es representado y su representante pertenece al equipo,
        # pero no está disponible en la banda para esta fecha.
        banda_disponible_nombres = df_banda_disponible['nombre_norm'].values
        
        if not filters.represented_director_validation(df_disponibles, 
                                    posible_director_index,
                                    integrantes,
                                    banda_disponible_nombres):
            continue

        # Eliminar representados solo si su representante pertenece al equipo
        # y no está disponible ni es el director.
        df_banda_disponible = filters.filter_represented_members(df_banda_disponible, 
                                    posible_director,
                                    integrantes,
                                    banda_disponible_nombres)

        if df_banda_disponible.empty:
            continue

        df_posible_banda, horario = filters.select_rehearsal_time(df_disponibles, posible_director_index, df_banda_disponible)

        #Selección de la banda más grande    
        if len(df_posible_banda) > len(df_banda):
            df_banda = df_posible_banda
            director_index = posible_director_index
            horario_ensayo = horario
    
    if not df_banda.empty and not np.isnan(director_index):

        week_roles['Director'] = df_directores_disponibles.loc[director_index, 'nombre']
        week_meta["Horario Tentativo de Ensayo"] = horario_ensayo

        select_musicians(df_banda, week_roles)

        select_choir(df_banda, week_roles)

        update_participation_tracking(df_shuffled, week_roles, semana_idx)
    
    

# =========================
# Planificación global
# =========================

def plans_generator(df, fecha_inicio, max_options=5, n_iter=10_000):

    df = df.copy()

    # === CONFIGURACIÓN GENERAL ===

    # === Integrantes ===
    integrantes = df["nombre_norm"].unique().tolist()

    # === DIRECTORES (voz principal) ===
    directores = df[df["director"] == 1]["nombre_norm"].unique().tolist()
    n_directores = len(directores)

    if n_directores == 0:
        return {}
    
    # === GENERAR FECHAS ===

    fechas_sabado, fechas_domingo, numero_semanas_plan, numero_semanas_total = generate_planning_dates(fecha_inicio, n_directores)

    # === PLANIFICACIÓN ===

    #Planificamos

    valid_plans = {}

    for _ in range(n_iter):
        # Inicializar columnas de control
        df["ultima_participacion"] = -99
        df["ultima_direccion"] = -99

        #Generamos un orden al azar para cada iteración
        seed = np.random.randint(0, 1_000_000)
        df_shuffled = df.sample(frac=1, random_state=seed)
        
        planificacion_list = []
        
        #Planificamos cada semana en un bucle
        for semana_idx in range(numero_semanas_total):
            fecha_domingo = fechas_domingo[semana_idx]
            fecha_sabado = fechas_sabado[semana_idx]
            #print(fecha_sabado)

            #Diccionario que almacenará la planificación semanal

            week_meta = {
                "Fecha Ensayo (Sábado)": fecha_sabado.date(),
                "Horario Tentativo de Ensayo": np.nan,
                "Fecha Presentación (Domingo)": fecha_domingo.date(),
            }

            week_roles = {
                "Director": np.nan,
                "Guitarrista": np.nan,
                "Baterista": np.nan,
                "Bajista": np.nan,
                "Tecladista": np.nan,
                "Corista_1": np.nan,
                "Corista_2": np.nan
            }

            select_best_band_for_week(df_shuffled, integrantes, n_directores, fecha_sabado, week_roles, week_meta, semana_idx)

            week_band_dict = {**week_meta, **week_roles}

            #Agregamos la semana a la lista de planificación    
            planificacion_list.append(week_band_dict)

        #Generamos un df de la planificación
        planificacion = pd.DataFrame(planificacion_list[-numero_semanas_plan:])

        #Guardamos un máximo de 5 planificaciones 
        #que tengan'Director','Guitarrista', 'Baterista', 'Corista_1' en cada fecha. 
        columns = ['Director','Guitarrista', 'Baterista', 'Corista_1']
        if not planificacion[columns].isna().any().any():
            valid_plans[seed] = planificacion.copy()
            if len(valid_plans) == max_options:
                break
    print(f'{len(valid_plans)} plans already generated.')
    return valid_plans
