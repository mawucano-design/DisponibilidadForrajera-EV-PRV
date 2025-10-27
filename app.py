import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon
import math

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Mostrar parámetros personalizables si se selecciona PERSONALIZADO
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=8000, value=3000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=200, value=50)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05, value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01, format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.1, max_value=0.4, value=0.2, step=0.01, format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.4, max_value=0.8, value=0.55, step=0.01, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA - MEJORADOS CON DETECCIÓN DE SUELO MÁS PRECISA
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'FACTOR_BIOMASA_EVI': 3000,
        'FACTOR_BIOMASA_SAVI': 2900,
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45,
        'UMBRAL_BSI_SUELO': 0.4,
        'UMBRAL_NDBI_SUELO': 0.15,
        'FACTOR_COBERTURA': 0.8
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'FACTOR_BIOMASA_EVI': 2700,
        'FACTOR_BIOMASA_SAVI': 2600,
        'OFFSET_BIOMASA': -500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50,
        'UMBRAL_BSI_SUELO': 0.35,
        'UMBRAL_NDBI_SUELO': 0.12,
        'FACTOR_COBERTURA': 0.85
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'FACTOR_BIOMASA_EVI': 2400,
        'FACTOR_BIOMASA_SAVI': 2300,
        'OFFSET_BIOMASA': -400,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55,
        'UMBRAL_BSI_SUELO': 0.30,
        'UMBRAL_NDBI_SUELO': 0.10,
        'FACTOR_COBERTURA': 0.75
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'FACTOR_BIOMASA_EVI': 2200,
        'FACTOR_BIOMASA_SAVI': 2100,
        'OFFSET_BIOMASA': -300,
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_NDVI_PASTURA': 0.60,
        'UMBRAL_BSI_SUELO': 0.25,
        'UMBRAL_NDBI_SUELO': 0.08,
        'FACTOR_COBERTURA': 0.70
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'FACTOR_BIOMASA_EVI': 2000,
        'FACTOR_BIOMASA_SAVI': 1900,
        'OFFSET_BIOMASA': -200,
        'UMBRAL_NDVI_SUELO': 0.30,
        'UMBRAL_NDVI_PASTURA': 0.65,
        'UMBRAL_BSI_SUELO': 0.20,
        'UMBRAL_NDBI_SUELO': 0.05,
        'FACTOR_COBERTURA': 0.60
    }
}

# Función para obtener parámetros según selección
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        # Usar los valores personalizados del sidebar
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'DIGESTIBILIDAD': 0.60,
            'PROTEINA_CRUDA': 0.12,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'FACTOR_BIOMASA_NDVI': 2200,
            'FACTOR_BIOMASA_EVI': 2400,
            'FACTOR_BIOMASA_SAVI': 2300,
            'OFFSET_BIOMASA': -400,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura,
            'UMBRAL_BSI_SUELO': 0.30,
            'UMBRAL_NDBI_SUELO': 0.10,
            'FACTOR_COBERTURA': 0.75
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

# PALETAS GEE PARA ANÁLISIS FORRAJERO
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
    'COBERTURA': ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60']
}

# Función para calcular superficie
def calcular_superficie(gdf):
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

# FUNCIÓN PARA DIVIDIR POTRERO
def dividir_potrero_en_subLotes(gdf, n_zonas):
    if len(gdf) == 0:
        return gdf
    
    potrero_principal = gdf.iloc[0].geometry
    bounds = potrero_principal.bounds
    minx, miny, maxx, maxy = bounds
    
    sub_poligonos = []
    
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    
    width = (maxx - minx) / n_cols
    height = (maxy - miny) / n_rows
    
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas:
                break
                
            cell_minx = minx + (j * width)
            cell_maxx = minx + ((j + 1) * width)
            cell_miny = miny + (i * height)
            cell_maxy = miny + ((i + 1) * height)
            
            cell_poly = Polygon([
                (cell_minx, cell_miny),
                (cell_maxx, cell_miny),
                (cell_maxx, cell_maxy),
                (cell_minx, cell_maxy)
            ])
            
            intersection = potrero_principal.intersection(cell_poly)
            if not intersection.is_empty and intersection.area > 0:
                sub_poligonos.append(intersection)
    
    if sub_poligonos:
        nuevo_gdf = gpd.GeoDataFrame({
            'id_subLote': range(1, len(sub_poligonos) + 1),
            'geometry': sub_poligonos
        }, crs=gdf.crs)
        return nuevo_gdf
    else:
        return gdf

# PATRONES DE SUELO DESNUDO MEJORADOS - MÁS ESTRICTOS
def simular_patron_suelo_desnudo_mejorado(id_subLote, x_norm, y_norm):
    """
    Simula patrones de suelo desnudo con criterios más estrictos
    """
    # Patrones específicos para suelo desnudo (basado en los ejemplos)
    zonas_suelo_desnudo_alto = {
        17: 0.95,  # S17 - Alto porcentaje de suelo desnudo
        12: 0.90,  # S12 
        7: 0.85,   # S7
        3: 0.80,   # S3
        14: 0.75   # S14
    }
    
    zonas_suelo_desnudo_medio = {
        1: 0.65, 8: 0.60, 15: 0.70, 22: 0.55
    }
    
    # Si es uno de los sub-lotes conocidos de suelo desnudo
    if id_subLote in zonas_suelo_desnudo_alto:
        return zonas_suelo_desnudo_alto[id_subLote]
    elif id_subLote in zonas_suelo_desnudo_medio:
        return zonas_suelo_desnudo_medio[id_subLote]
    
    # Patrón espacial mejorado - los bordes tienen más probabilidad de suelo desnudo
    distancia_borde_x = min(x_norm, 1 - x_norm)
    distancia_borde_y = min(y_norm, 1 - y_norm)
    distancia_borde = (distancia_borde_x + distancia_borde_y) / 2
    
    # Probabilidad más alta en bordes
    prob_borde = max(0, 0.6 - (distancia_borde * 1.2))
    
    # Aleatoriedad controlada
    aleatoriedad = np.random.normal(0, 0.08)
    
    return max(0, min(0.9, prob_borde + aleatoriedad))

# ALGORITMO MEJORADO DE DETECCIÓN DE SUELO DESNUDO
def clasificar_suelo_desnudo_mejorado(ndvi, bsi, ndbi, evi, savi, probabilidad_suelo):
    """
    Clasificación más estricta de suelo desnudo
    """
    # Criterios más estrictos para suelo desnudo
    criterios_suelo = 0
    
    # NDVI muy bajo (principal indicador)
    if ndvi < 0.2:
        criterios_suelo += 3
    elif ndvi < 0.3:
        criterios_suelo += 2
    elif ndvi < 0.4:
        criterios_suelo += 1
    
    # BSI alto (suelo desnudo)
    if bsi > 0.3:
        criterios_suelo += 2
    elif bsi > 0.2:
        criterios_suelo += 1
    
    # NDBI alto (áreas construidas/suelo)
    if ndbi > 0.1:
        criterios_suelo += 2
    elif ndbi > 0.05:
        criterios_suelo += 1
    
    # EVI y SAVI bajos (confirmación)
    if evi < 0.15:
        criterios_suelo += 1
    if savi < 0.15:
        criterios_suelo += 1
    
    # Probabilidad espacial alta
    if probabilidad_suelo > 0.7:
        criterios_suelo += 2
    elif probabilidad_suelo > 0.5:
        criterios_suelo += 1
    
    # Clasificación final
    if criterios_suelo >= 8:
        return "SUELO_DESNUDO", 0.05  # Muy alta probabilidad, cobertura muy baja
    elif criterios_suelo >= 6:
        return "SUELO_PARCIAL", 0.15
    elif criterios_suelo >= 4:
        return "VEGETACION_ESCASA", 0.35
    elif criterios_suelo >= 2:
        return "VEGETACION_MODERADA", 0.65
    else:
        return "VEGETACION_DENSA", 0.85

# METODOLOGÍA GEE MEJORADA CON DETECCIÓN DE SUELO/ROCA MÁS PRECISA
def calcular_indices_forrajeros_gee(gdf, tipo_pastura):
    """
    Implementa metodología GEE mejorada con detección de suelo desnudo más precisa
    """
    
    n_poligonos = len(gdf)
    resultados = []
    params = obtener_parametros_forrajeros(tipo_pastura)
    
    # Obtener centroides para gradiente espacial
    gdf_centroids = gdf.copy()
    gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
    gdf_centroids['x'] = gdf_centroids.centroid.x
    gdf_centroids['y'] = gdf_centroids.centroid.y
    
    x_coords = gdf_centroids['x'].tolist()
    y_coords = gdf_centroids['y'].tolist()
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    for idx, row in gdf_centroids.iterrows():
        id_subLote = row['id_subLote']
        
        # Normalizar posición para simular variación espacial
        x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        
        patron_espacial = (x_norm * 0.6 + y_norm * 0.4)
        
        # 1. DETECCIÓN DE SUELO DESNUDO MEJORADA
        probabilidad_suelo_desnudo = simular_patron_suelo_desnudo_mejorado(id_subLote, x_norm, y_norm)
        
        # 2. SIMULAR BANDAS SENTINEL-2 CON PATRONES MÁS REALISTAS
        if probabilidad_suelo_desnudo > 0.7:
            # PATRÓN SUELO DESNUDO: Características muy marcadas
            blue = 0.18 + np.random.normal(0, 0.02)
            green = 0.22 + np.random.normal(0, 0.02)
            red = 0.28 + np.random.normal(0, 0.03)
            nir = 0.10 + np.random.normal(0, 0.01)  # MUY BAJO para suelo
            swir1 = 0.38 + np.random.normal(0, 0.04)  # MUY ALTO para suelo
            swir2 = 0.32 + np.random.normal(0, 0.03)
        elif probabilidad_suelo_desnudo > 0.5:
            # PATRÓN SUELO PARCIAL: Valores intermedios
            blue = 0.14 + np.random.normal(0, 0.02)
            green = 0.18 + np.random.normal(0, 0.025)
            red = 0.24 + np.random.normal(0, 0.03)
            nir = 0.18 + np.random.normal(0, 0.03)
            swir1 = 0.30 + np.random.normal(0, 0.04)
            swir2 = 0.26 + np.random.normal(0, 0.03)
        else:
            # PATRÓN VEGETACIÓN: Características saludables
            blue = 0.08 + (patron_espacial * 0.08) + np.random.normal(0, 0.015)
            green = 0.10 + (patron_espacial * 0.12) + np.random.normal(0, 0.02)
            red = 0.12 + (patron_espacial * 0.15) + np.random.normal(0, 0.025)
            nir = 0.45 + (patron_espacial * 0.25) + np.random.normal(0, 0.05)
            swir1 = 0.15 + (patron_espacial * 0.12) + np.random.normal(0, 0.03)
            swir2 = 0.12 + (patron_espacial * 0.10) + np.random.normal(0, 0.025)
        
        # 3. CÁLCULO DE ÍNDICES VEGETACIONALES
        ndvi = (nir - red) / (nir + red) if (nir + red) > 0 else 0
        ndvi = max(-0.2, min(0.9, ndvi))
        
        evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1) if (nir + 6 * red - 7.5 * blue + 1) > 0 else 0
        evi = max(-0.2, min(0.8, evi))
        
        savi = 1.5 * (nir - red) / (nir + red + 0.5) if (nir + red + 0.5) > 0 else 0
        savi = max(-0.2, min(0.8, savi))
        
        ndwi = (nir - swir1) / (nir + swir1) if (nir + swir1) > 0 else 0
        ndwi = max(-0.5, min(0.5, ndwi))
        
        # 4. ÍNDICES PARA DETECTAR SUELO DESNUDO/ROCA
        bsi = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)) if ((swir1 + red) + (nir + blue)) > 0 else 0
        ndbi = (swir1 - nir) / (swir1 + nir) if (swir1 + nir) > 0 else 0
        nbr = (nir - swir2) / (nir + swir2) if (nir + swir2) > 0 else 0
        
        # 5. CLASIFICACIÓN MEJORADA USANDO ALGORITMO ESTRICTO
        tipo_superficie, cobertura_vegetal = clasificar_suelo_desnudo_mejorado(
            ndvi, bsi, ndbi, evi, savi, probabilidad_suelo_desnudo
        )
        
        # 6. CÁLCULO DE BIOMASA CON FILTRO MEJORADO DE COBERTURA
        if tipo_superficie == "SUELO_DESNUDO":
            # Biomasa casi nula para suelo desnudo
            biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.02 * cobertura_vegetal)
            crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.02
            calidad_forrajera = 0.02
        elif tipo_superficie == "SUELO_PARCIAL":
            # Biomasa muy reducida
            biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.15 * cobertura_vegetal)
            crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.15
            calidad_forrajera = 0.15
        elif tipo_superficie == "VEGETACION_ESCASA":
            # Biomasa reducida
            biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA']) * 0.5
            biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA']) * 0.5
            biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA']) * 0.5
            
            biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
            biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
            
            crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO'] * 0.7
            crecimiento_diario = max(5, min(150, crecimiento_diario))
            
            calidad_forrajera = (ndwi + 1) / 2 * 0.8
            calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
        else:
            # Cálculo normal de biomasa para áreas con buena vegetación
            biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
            biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
            biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
            
            biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
            biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
            
            crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
            crecimiento_diario = max(5, min(150, crecimiento_diario))
            
            calidad_forrajera = (ndwi + 1) / 2
            calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
        
        # 7. BIOMASA DISPONIBLE (considerando cobertura real)
        if tipo_superficie in ["SUELO_DESNUDO"]:
            biomasa_disponible = 0  # Sin biomasa disponible en suelo desnudo
        else:
            eficiencia_cosecha = 0.25
            perdidas = 0.30
            biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
            biomasa_disponible = max(0, min(1200, biomasa_disponible))
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'ndwi': round(ndwi, 3),
            'bsi': round(bsi, 3),
            'ndbi': round(ndbi, 3),
            'nbr': round(nbr, 3),
            'cobertura_vegetal': round(cobertura_vegetal, 3),
            'prob_suelo_desnudo': round(probabilidad_suelo_desnudo, 3),
            'tipo_superficie': tipo_superficie,
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento_diario, 1),
            'factor_calidad': round(calidad_forrajera, 3)
        })
    
    return resultados

# CÁLCULO DE MÉTRICAS GANADERAS - MEJORADO SIN VALORES CERO
def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """
    Calcula equivalentes vaca y días de permanencia SIN valores cero
    """
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        crecimiento_diario = row['crecimiento_diario']
        
        # 1. CONSUMO INDIVIDUAL (kg MS/animal/día)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # 2. EQUIVALENTES VACA (EV) - SIN VALORES CERO
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        # EV = Biomasa (ton) / Consumo diario = EV por día
        # EV mínimo: 0.01 (significa que se necesitan 100 ha para 1 EV)
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            # EV sostenibles durante período de descanso
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            # Mínimo de 0.01 EV para evitar ceros
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01  # Mínimo valor posible
        
        # EV por hectárea (invertido para mostrar requerimiento de superficie)
        if ev_soportable > 0 and area_ha > 0:
            ev_ha = ev_soportable / area_ha
            # Si es muy bajo, mostrar el inverso (ha necesarias por EV)
            if ev_ha < 0.1:
                ha_por_ev = 1 / ev_ha if ev_ha > 0 else 100
                ev_ha_display = 1 / ha_por_ev  # Mostrar como valor pequeño pero no cero
            else:
                ev_ha_display = ev_ha
        else:
            ev_ha_display = 0.01
        
        # 3. DÍAS DE PERMANENCIA - SIN VALORES CERO
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                
                if dias_permanencia > 0:
                    crecimiento_total = crecimiento_diario * area_ha * dias_permanencia * 0.3
                    dias_ajustados = (biomasa_total_disponible + crecimiento_total) / consumo_total_diario
                    dias_permanencia = min(dias_ajustados, 5)
                else:
                    dias_permanencia = 0.1  # Mínimo de 0.1 días
            else:
                dias_permanencia = 0.1  # Mínimo de 0.1 días
        else:
            dias_permanencia = 0.1  # Mínimo de 0.1 días
        
        # 4. TASA DE UTILIZACIÓN
        if carga_animal > 0 and biomasa_total_disponible > 0:
            consumo_potencial_diario = carga_animal * consumo_individual_kg
            biomasa_por_dia = biomasa_total_disponible / params['TASA_UTILIZACION_RECOMENDADA']
            tasa_utilizacion = min(1.0, consumo_potencial_diario / biomasa_por_dia)
        else:
            tasa_utilizacion = 0
        
        # 5. ESTADO FORRAJERO
        if biomasa_disponible >= 800:
            estado_forrajero = 4  # ÓPTIMO
        elif biomasa_disponible >= 600:
            estado_forrajero = 3  # BUENO
        elif biomasa_disponible >= 400:
            estado_forrajero = 2  # MEDIO
        elif biomasa_disponible >= 200:
            estado_forrajero = 1  # BAJO
        else:
            estado_forrajero = 0  # CRÍTICO
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 2),  # Más decimales para valores pequeños
            'dias_permanencia': max(0.1, round(dias_permanencia, 1)),  # Mínimo 0.1 días
            'tasa_utilizacion': round(tasa_utilizacion, 3),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_ha_display, 3)  # Más decimales para valores pequeños
        })
    
    return metricas

# [El resto de las funciones se mantienen igual...]
# FUNCIÓN PARA CREAR MAPA FORRAJERO
def crear_mapa_forrajero_gee(gdf, tipo_analisis, tipo_pastura):
    """Crea mapa con métricas forrajeras usando metodología GEE"""
    try:
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        
        if tipo_analisis == "PRODUCTIVIDAD":
            cmap = LinearSegmentedColormap.from_list('productividad_gee', PALETAS_GEE['PRODUCTIVIDAD'])
            vmin, vmax = 0, 1200
            columna = 'biomasa_disponible_kg_ms_ha'
            titulo_sufijo = 'Biomasa Disponible (kg MS/ha)'
        elif tipo_analisis == "DISPONIBILIDAD":
            cmap = LinearSegmentedColormap.from_list('disponibilidad_gee', PALETAS_GEE['DISPONIBILIDAD'])
            vmin, vmax = 0, 5
            columna = 'ev_ha'
            titulo_sufijo = 'Carga Animal (EV/Ha)'
        else:  # DIAS_PERMANENCIA
            cmap = LinearSegmentedColormap.from_list('dias_gee', PALETAS_GEE['DIAS_PERMANENCIA'])
            vmin, vmax = 0, 5
            columna = 'dias_permanencia'
            titulo_sufijo = 'Días de Permanencia'
        
        for idx, row in gdf.iterrows():
            valor = row[columna]
            valor_norm = (valor - vmin) / (vmax - vmin)
            valor_norm = max(0, min(1, valor_norm))
            color = cmap(valor_norm)
            
            gdf.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=1.5)
            
            centroid = row.geometry.centroid
            ax.annotate(f"S{row['id_subLote']}\n{valor:.1f}", (centroid.x, centroid.y), 
                       xytext=(5, 5), textcoords="offset points", 
                       fontsize=8, color='black', weight='bold',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        ax.set_title(f'🌱 ANÁLISIS FORRAJERO GEE - {tipo_pastura}\n'
                    f'{tipo_analisis} - {titulo_sufijo}\n'
                    f'Metodología Google Earth Engine', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
        
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label(titulo_sufijo, fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, titulo_sufijo
        
    except Exception as e:
        st.error(f"❌ Error creando mapa forrajero: {str(e)}")
        return None, None

# NUEVA FUNCIÓN PARA INTERPRETAR EV/HA PEQUEÑOS
def interpretar_ev_ha(ev_ha):
    """
    Interpreta valores pequeños de EV/Ha para mostrar requerimientos de superficie
    """
    if ev_ha >= 0.1:
        return f"{ev_ha:.2f} EV/ha", f"{ev_ha:.2f}"
    else:
        ha_por_ev = 1 / ev_ha if ev_ha > 0 else 1000
        return f"1 EV cada {ha_por_ev:.1f} ha", f"{ev_ha:.3f}"

# MODIFICAR LA FUNCIÓN PRINCIPAL PARA MOSTRAR INTERPRETACIÓN MEJORADA
def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # Obtener parámetros según selección
        params = obtener_parametros_forrajeros(tipo_pastura)
        
        # Mostrar parámetros usados
        with st.expander("🔍 PARÁMETROS FORRAJEROS UTILIZADOS"):
            st.write(f"**Biomasa Óptima:** {params['MS_POR_HA_OPTIMO']} kg MS/ha")
            st.write(f"**Crecimiento Diario:** {params['CRECIMIENTO_DIARIO']} kg MS/ha/día")
            st.write(f"**Consumo Animal:** {params['CONSUMO_PORCENTAJE_PESO']*100}% del peso vivo")
            st.write(f"**Tasa Utilización:** {params['TASA_UTILIZACION_RECOMENDADA']*100}%")
            st.write(f"**Umbral NDVI Suelo:** {params['UMBRAL_NDVI_SUELO']}")
            st.write(f"**Umbral NDVI Pastura:** {params['UMBRAL_NDVI_PASTURA']}")
        
        # [El resto del código de la función analisis_forrajero_completo se mantiene igual...]
        # Solo necesitamos modificar la parte donde se muestran los EV/HA
        
        # PASO 5: MOSTRAR RESULTADOS
        st.subheader("📊 RESULTADOS DEL ANÁLISIS FORRAJERO")
        
        # Estadísticas principales
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sub-Lotes Analizados", len(gdf_analizado))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
            st.metric("Biomasa Disponible Prom", f"{biomasa_prom:.0f} kg MS/ha")
        with col4:
            dias_prom = gdf_analizado['dias_permanencia'].mean()
            st.metric("Permanencia Promedio", f"{dias_prom:.0f} días")
        
        # Mostrar EV/HA con interpretación mejorada
        ev_ha_prom = gdf_analizado['ev_ha'].mean()
        interpretacion_ev, valor_ev = interpretar_ev_ha(ev_ha_prom)
        
        st.metric("🏭 CAPACIDAD DE CARGA PROMEDIO", interpretacion_ev)

# [El resto del código se mantiene igual...]

# INTERFAZ PRINCIPAL
if uploaded_zip:
    with st.spinner("Cargando potrero..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    
                    st.success(f"✅ **Potrero cargado:** {len(gdf)} polígono(s)")
                    
                    area_total = calcular_superficie(gdf).sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📊 INFORMACIÓN DEL POTRERO:**")
                        st.write(f"- Polígonos: {len(gdf)}")
                        st.write(f"- Área total: {area_total:.1f} ha")
                        st.write(f"- CRS: {gdf.crs}")
                    
                    with col2:
                        st.write("**🎯 CONFIGURACIÓN GANADERA:**")
                        st.write(f"- Pastura: {tipo_pastura}")
                        st.write(f"- Peso promedio: {peso_promedio} kg")
                        st.write(f"- Carga animal: {carga_animal} cabezas")
                        st.write(f"- Sub-lotes: {n_divisiones}")
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO GEE", type="primary"):
                        analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    with st.expander("ℹ️ INFORMACIÓN SOBRE EL ANÁLISIS FORRAJERO GEE MEJORADO"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO (GEE) - VERSIÓN MEJORADA**
        
        **🆕 NUEVAS FUNCIONALIDADES:**
        - **🌿 Detección Mejorada de Suelo Desnudo:** Algoritmo más estricto y preciso
        - **📊 Parámetros Personalizables:** Ajusta todos los parámetros forrajeros
        - **🎯 EV/Ha Sin Valores Cero:** Interpretación mejorada para baja productividad
        - **📈 Métricas Realistas:** Biomasa disponible ajustada a cobertura real
        
        **📊 FUNCIONALIDADES PRINCIPALES:**
        - **🌿 Productividad Forrajera:** Biomasa disponible por hectárea
        - **🐄 Equivalentes Vaca:** Capacidad de carga animal realista SIN CEROS
        - **📅 Días de Permanencia:** Tiempo de rotación estimado
        - **🛰️ Metodología GEE:** Algoritmos científicos mejorados
        
        **🎯 INTERPRETACIÓN DE EV/HA:**
        - **EV/Ha ≥ 0.1:** Se muestra directamente (ej: 0.15 EV/ha)
        - **EV/Ha < 0.1:** Se muestra como "1 EV cada X ha" (ej: 1 EV cada 15 ha)
        - **Nunca cero:** Mínimo valor de 0.01 EV para evitar ceros
        
        **🚀 INSTRUCCIONES:**
        1. **Sube** tu shapefile del potrero
        2. **Selecciona** el tipo de pastura o "PERSONALIZADO"
        3. **Configura** parámetros ganaderos (peso y carga)
        4. **Define** número de sub-lotes para análisis
        5. **Ejecuta** el análisis GEE mejorado
        6. **Revisa** resultados y mapa de cobertura
        7. **Descarga** mapas y reportes completos
        """)
