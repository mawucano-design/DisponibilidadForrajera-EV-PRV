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
import json
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - PARÁMETROS PERSONALIZABLES")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selección de tipo de pastura con opción personalizada
    opciones_pastura = ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    tipo_pastura = st.selectbox("Tipo de Pastura:", opciones_pastura)
    
    # MOSTRAR PARÁMETROS PERSONALIZABLES SI SE SELECCIONA "PERSONALIZADO"
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("🎯 Parámetros Forrajeros Personalizados")
        
        col1, col2 = st.columns(2)
        with col1:
            ms_optimo = st.number_input("MS Óptimo (kg MS/ha):", min_value=500, max_value=10000, value=3000, step=100)
            crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=5, max_value=200, value=50, step=5)
            consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.1, value=0.025, step=0.001, format="%.3f")
        
        with col2:
            digestibilidad = st.number_input("Digestibilidad (%):", min_value=0.1, max_value=0.9, value=0.6, step=0.01, format="%.2f")
            proteina_cruda = st.number_input("Proteína Cruda (%):", min_value=0.01, max_value=0.3, value=0.12, step=0.01, format="%.2f")
            tasa_utilizacion = st.number_input("Tasa Utilización (%):", min_value=0.1, max_value=0.9, value=0.55, step=0.01, format="%.2f")
        
        # Parámetros avanzados en expander
        with st.expander("⚙️ Parámetros Avanzados"):
            col1, col2 = st.columns(2)
            with col1:
                factor_ndvi = st.number_input("Factor Biomasa NDVI:", min_value=500, max_value=5000, value=2000, step=100)
                factor_evi = st.number_input("Factor Biomasa EVI:", min_value=500, max_value=5000, value=2200, step=100)
                offset_biomasa = st.number_input("Offset Biomasa:", min_value=-2000, max_value=0, value=-300, step=50)
            
            with col2:
                umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.0, max_value=0.5, value=0.20, step=0.01, format="%.2f")
                umbral_bsi_suelo = st.number_input("Umbral BSI Suelo:", min_value=0.0, max_value=0.5, value=0.18, step=0.01, format="%.2f")
                penalizacion_suelo = st.number_input("Penalización Suelo:", min_value=0.0, max_value=1.0, value=0.75, step=0.05, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=72, value=48)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

    # NUEVO: GUARDAR/CARGAR CONFIGURACIÓN
    st.subheader("💾 Guardar/Cargar Configuración")
    
    if tipo_pastura == "PERSONALIZADO":
        # Guardar configuración actual
        config_data = {
            'ms_optimo': ms_optimo,
            'crecimiento_diario': crecimiento_diario,
            'consumo_porcentaje': consumo_porcentaje,
            'digestibilidad': digestibilidad,
            'proteina_cruda': proteina_cruda,
            'tasa_utilizacion': tasa_utilizacion,
            'factor_ndvi': factor_ndvi,
            'factor_evi': factor_evi,
            'offset_biomasa': offset_biomasa,
            'umbral_ndvi_suelo': umbral_ndvi_suelo,
            'umbral_bsi_suelo': umbral_bsi_suelo,
            'penalizacion_suelo': penalizacion_suelo
        }
        
        config_json = json.dumps(config_data, indent=2)
        st.download_button(
            "💾 Guardar Configuración",
            config_json,
            file_name="configuracion_pastura.json",
            mime="application/json",
            help="Descarga la configuración actual para usarla después"
        )
    
    # Cargar configuración
    uploaded_config = st.file_uploader("Cargar configuración (.json)", type=['json'], key="config_uploader")
    
    if uploaded_config is not None:
        try:
            config_cargada = json.load(uploaded_config)
            st.success("✅ Configuración cargada correctamente")
            st.info(f"MS Óptimo: {config_cargada.get('ms_optimo', 'N/A')} kg/ha")
        except Exception as e:
            st.error(f"❌ Error cargando configuración: {e}")

# PARÁMETROS FORRAJEROS BASE
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
        'UMBRAL_NDVI_SUELO': 0.12,
        'UMBRAL_BSI_SUELO': 0.20,
        'UMBRAL_NDBI_SUELO': 0.08,
        'UMBRAL_NDVI_VEGETACION': 0.40,
        'FACTOR_COBERTURA_MAX': 0.98,
        'FACTOR_COBERTURA_MIN': 0.02,
        'PENALIZACION_SUELO': 0.90,
        'FACTOR_MSAVI2': 2600,
        'FACTOR_VARI': 800,
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
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_BSI_SUELO': 0.18,
        'UMBRAL_NDBI_SUELO': 0.07,
        'UMBRAL_NDVI_VEGETACION': 0.45,
        'FACTOR_COBERTURA_MAX': 0.95,
        'FACTOR_COBERTURA_MIN': 0.03,
        'PENALIZACION_SUELO': 0.85,
        'FACTOR_MSAVI2': 2400,
        'FACTOR_VARI': 750,
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
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_BSI_SUELO': 0.16,
        'UMBRAL_NDBI_SUELO': 0.06,
        'UMBRAL_NDVI_VEGETACION': 0.50,
        'FACTOR_COBERTURA_MAX': 0.92,
        'FACTOR_COBERTURA_MIN': 0.05,
        'PENALIZACION_SUELO': 0.80,
        'FACTOR_MSAVI2': 2200,
        'FACTOR_VARI': 700,
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
        'UMBRAL_NDVI_SUELO': 0.22,
        'UMBRAL_BSI_SUELO': 0.14,
        'UMBRAL_NDBI_SUELO': 0.05,
        'UMBRAL_NDVI_VEGETACION': 0.55,
        'FACTOR_COBERTURA_MAX': 0.88,
        'FACTOR_COBERTURA_MIN': 0.08,
        'PENALIZACION_SUELO': 0.75,
        'FACTOR_MSAVI2': 2000,
        'FACTOR_VARI': 650,
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
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_BSI_SUELO': 0.12,
        'UMBRAL_NDBI_SUELO': 0.04,
        'UMBRAL_NDVI_VEGETACION': 0.60,
        'FACTOR_COBERTURA_MAX': 0.85,
        'FACTOR_COBERTURA_MIN': 0.10,
        'PENALIZACION_SUELO': 0.65,
        'FACTOR_MSAVI2': 1800,
        'FACTOR_VARI': 600,
    }
}

# FUNCIÓN PARA OBTENER PARÁMETROS (BASE O PERSONALIZADOS)
def obtener_parametros_pastura(tipo_pastura, config_personalizada=None):
    """
    Retorna los parámetros según la selección (base o personalizados)
    """
    if tipo_pastura != "PERSONALIZADO":
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]
    else:
        # Usar parámetros personalizados
        if config_personalizada:
            # Si se cargó una configuración, usarla
            return {
                'MS_POR_HA_OPTIMO': config_personalizada.get('ms_optimo', 3000),
                'CRECIMIENTO_DIARIO': config_personalizada.get('crecimiento_diario', 50),
                'CONSUMO_PORCENTAJE_PESO': config_personalizada.get('consumo_porcentaje', 0.025),
                'DIGESTIBILIDAD': config_personalizada.get('digestibilidad', 0.6),
                'PROTEINA_CRUDA': config_personalizada.get('proteina_cruda', 0.12),
                'TASA_UTILIZACION_RECOMENDADA': config_personalizada.get('tasa_utilizacion', 0.55),
                'FACTOR_BIOMASA_NDVI': config_personalizada.get('factor_ndvi', 2000),
                'FACTOR_BIOMASA_EVI': config_personalizada.get('factor_evi', 2200),
                'FACTOR_BIOMASA_SAVI': config_personalizada.get('factor_ndvi', 2000) * 1.05,  # Derivado de NDVI
                'OFFSET_BIOMASA': config_personalizada.get('offset_biomasa', -300),
                'UMBRAL_NDVI_SUELO': config_personalizada.get('umbral_ndvi_suelo', 0.20),
                'UMBRAL_BSI_SUELO': config_personalizada.get('umbral_bsi_suelo', 0.18),
                'UMBRAL_NDBI_SUELO': 0.05,  # Valor por defecto
                'UMBRAL_NDVI_VEGETACION': 0.55,  # Valor por defecto
                'FACTOR_COBERTURA_MAX': 0.90,
                'FACTOR_COBERTURA_MIN': 0.05,
                'PENALIZACION_SUELO': config_personalizada.get('penalizacion_suelo', 0.75),
                'FACTOR_MSAVI2': config_personalizada.get('factor_ndvi', 2000) * 0.9,  # Derivado de NDVI
                'FACTOR_VARI': 700,  # Valor por defecto
            }
        else:
            # Usar valores por defecto para personalizado
            return {
                'MS_POR_HA_OPTIMO': 3000,
                'CRECIMIENTO_DIARIO': 50,
                'CONSUMO_PORCENTAJE_PESO': 0.025,
                'DIGESTIBILIDAD': 0.60,
                'PROTEINA_CRUDA': 0.12,
                'TASA_UTILIZACION_RECOMENDADA': 0.55,
                'FACTOR_BIOMASA_NDVI': 2000,
                'FACTOR_BIOMASA_EVI': 2200,
                'FACTOR_BIOMASA_SAVI': 2100,
                'OFFSET_BIOMASA': -300,
                'UMBRAL_NDVI_SUELO': 0.20,
                'UMBRAL_BSI_SUELO': 0.18,
                'UMBRAL_NDBI_SUELO': 0.05,
                'UMBRAL_NDVI_VEGETACION': 0.55,
                'FACTOR_COBERTURA_MAX': 0.90,
                'FACTOR_COBERTURA_MIN': 0.05,
                'PENALIZACION_SUELO': 0.75,
                'FACTOR_MSAVI2': 2000,
                'FACTOR_VARI': 700,
            }

# PALETAS GEE PARA ANÁLISIS FORRAJERO
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
    'COBERTURA': ['#8c510a', '#bf812d', '#dfc27d', '#80cdc1', '#01665e']
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

# NUEVO: CÁLCULO DE ÍNDICES ADICIONALES
def calcular_indices_avanzados(blue, green, red, nir, swir1, swir2):
    """
    Calcula índices avanzados para mejor detección
    """
    epsilon = 1e-10
    
    # Índices básicos
    ndvi = (nir - red) / (nir + red + epsilon)
    evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1 + epsilon)
    savi = 1.5 * (nir - red) / (nir + red + 0.5 + epsilon)
    
    # Índices de suelo
    bsi = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue) + epsilon)
    ndbi = (swir1 - nir) / (swir1 + nir + epsilon)
    ndsi = (green - swir1) / (green + swir1 + epsilon)
    
    # Índices avanzados
    msavi2 = (2 * nir + 1 - np.sqrt((2 * nir + 1)**2 - 8 * (nir - red))) / 2
    ui = (swir2 - nir) / (swir2 + nir + epsilon)  # Urban Index
    
    # Índice de Vegetación Ajustado para Suelo (VARI)
    vari = (green - red) / (green + red - blue + epsilon)
    
    return {
        'ndvi': max(-1, min(1, ndvi)),
        'evi': max(-1, min(1, evi)),
        'savi': max(-1, min(1, savi)),
        'bsi': max(-1, min(1, bsi)),
        'ndbi': max(-1, min(1, ndbi)),
        'ndsi': max(-1, min(1, ndsi)),
        'msavi2': max(-1, min(1, msavi2)),
        'ui': max(-1, min(1, ui)),
        'vari': max(-1, min(1, vari))
    }

# NUEVO: ALGORITMO AVANZADO DE CLASIFICACIÓN
def clasificacion_avanzada_suelo_vegetacion(ndvi, bsi, ndbi, evi, savi, msavi2, ui, params):
    """
    Clasificación avanzada usando múltiples índices y lógica fuzzy
    """
    # 1. CALCULAR PUNTUACIONES INDIVIDUALES
    puntuacion_suelo = 0
    puntuacion_vegetacion = 0
    
    # Puntuación por NDVI (vegetación)
    if ndvi < params['UMBRAL_NDVI_SUELO']:
        puntuacion_suelo += 3
    elif ndvi < params['UMBRAL_NDVI_SUELO'] * 1.5:
        puntuacion_suelo += 2
    elif ndvi > params['UMBRAL_NDVI_VEGETACION']:
        puntuacion_vegetacion += 3
    elif ndvi > params['UMBRAL_NDVI_VEGETACION'] * 0.7:
        puntuacion_vegetacion += 2
    
    # Puntuación por BSI (suelo desnudo)
    if bsi > params['UMBRAL_BSI_SUELO']:
        puntuacion_suelo += 3
    elif bsi > params['UMBRAL_BSI_SUELO'] * 0.7:
        puntuacion_suelo += 2
    
    # Puntuación por NDBI (áreas construidas/suelo)
    if ndbi > params['UMBRAL_NDBI_SUELO']:
        puntuacion_suelo += 2
    
    # Puntuación por EVI (vegetación saludable)
    if evi > 0.4:
        puntuacion_vegetacion += 2
    elif evi > 0.2:
        puntuacion_vegetacion += 1
    
    # Puntuación por SAVI (vegetación ajustada por suelo)
    if savi > 0.3:
        puntuacion_vegetacion += 2
    elif savi > 0.15:
        puntuacion_vegetacion += 1
    
    # 2. DETERMINAR TIPO DE SUPERFICIE
    diferencia = puntuacion_vegetacion - puntuacion_suelo
    
    if diferencia <= -4:
        return "SUELO_DESNUDO", 0.05, 0.1
    elif diferencia <= -2:
        return "SUELO_PARCIAL", 0.15, 0.3
    elif diferencia <= 0:
        return "VEGETACION_ESCASA", 0.35, 0.5
    elif diferencia <= 2:
        return "VEGETACION_MODERADA", 0.65, 0.8
    else:
        return "VEGETACION_DENSA", 0.85, 1.0

# NUEVO: FUNCIÓN DE SIMULACIÓN DE BANDAS MÁS REALISTA
def simular_bandas_sentinel_realista(patron_espacial, tipo_pastura):
    """
    Simula bandas Sentinel-2 de forma más realista para mejor detección
    """
    # Valores base según tipo de pastura
    if tipo_pastura == "PASTIZAL_NATURAL":
        # Para pastizales naturales, más variabilidad y suelo
        base_ndvi = 0.25 + (patron_espacial * 0.3)
        base_bsi = 0.15 + ((1 - patron_espacial) * 0.2)
    else:
        # Para pasturas cultivadas, más homogéneo
        base_ndvi = 0.35 + (patron_espacial * 0.25)
        base_bsi = 0.08 + ((1 - patron_espacial) * 0.15)
    
    # Simular bandas basadas en NDVI esperado
    if base_ndvi < 0.15:  # Suelo desnudo
        blue = 0.15 + np.random.normal(0, 0.03)
        green = 0.18 + np.random.normal(0, 0.04)
        red = 0.22 + np.random.normal(0, 0.05)
        nir = 0.25 + np.random.normal(0, 0.06)
        swir1 = 0.30 + np.random.normal(0, 0.07)
        swir2 = 0.28 + np.random.normal(0, 0.06)
    elif base_ndvi < 0.3:  # Vegetación escasa
        blue = 0.12 + np.random.normal(0, 0.02)
        green = 0.16 + np.random.normal(0, 0.03)
        red = 0.20 + np.random.normal(0, 0.04)
        nir = 0.35 + np.random.normal(0, 0.08)
        swir1 = 0.25 + np.random.normal(0, 0.05)
        swir2 = 0.22 + np.random.normal(0, 0.04)
    elif base_ndvi < 0.5:  # Vegetación moderada
        blue = 0.10 + np.random.normal(0, 0.02)
        green = 0.14 + np.random.normal(0, 0.03)
        red = 0.18 + np.random.normal(0, 0.04)
        nir = 0.45 + np.random.normal(0, 0.10)
        swir1 = 0.22 + np.random.normal(0, 0.04)
        swir2 = 0.20 + np.random.normal(0, 0.03)
    else:  # Vegetación densa
        blue = 0.08 + np.random.normal(0, 0.01)
        green = 0.12 + np.random.normal(0, 0.02)
        red = 0.15 + np.random.normal(0, 0.03)
        nir = 0.55 + np.random.normal(0, 0.12)
        swir1 = 0.18 + np.random.normal(0, 0.03)
        swir2 = 0.16 + np.random.normal(0, 0.02)
    
    return blue, green, red, nir, swir1, swir2

# NUEVO: DETECCIÓN AVANZADA DE SUELO vs VEGETACIÓN
def detectar_suelo_vegetacion_avanzado(blue, green, red, nir, swir1, swir2, params):
    """
    Detección MUY MEJORADA de suelo vs vegetación con múltiples índices
    """
    # Calcular todos los índices
    indices = calcular_indices_avanzados(blue, green, red, nir, swir1, swir2)
    
    # Clasificación avanzada
    tipo_superficie, cobertura_base, factor_base = clasificacion_avanzada_suelo_vegetacion(
        indices['ndvi'], indices['bsi'], indices['ndbi'], indices['evi'], 
        indices['savi'], indices['msavi2'], indices['ui'], params
    )
    
    # 3. AJUSTE FINO DE COBERTURA BASADO EN MÚLTIPLES ÍNDICES
    cobertura_ajustada = cobertura_base
    
    # Ajustar por NDVI
    if indices['ndvi'] > 0:
        cobertura_ajustada += indices['ndvi'] * 0.2
    
    # Ajustar por EVI (mejor para vegetación densa)
    if indices['evi'] > 0.2:
        cobertura_ajustada += indices['evi'] * 0.15
    
    # Penalizar por BSI (suelo desnudo)
    if indices['bsi'] > 0.1:
        cobertura_ajustada -= indices['bsi'] * 0.3
    
    # Ajustar por MSAVI2 (mejor para suelos)
    if indices['msavi2'] > 0.1:
        cobertura_ajustada += indices['msavi2'] * 0.1
    
    # 4. FACTOR DE PENALIZACIÓN MÁS PRECISO
    if tipo_superficie == "SUELO_DESNUDO":
        factor_penalizacion = 0.05  # Solo 5% de biomasa
        cobertura_final = max(0.02, min(0.1, cobertura_ajustada))
    elif tipo_superficie == "SUELO_PARCIAL":
        factor_penalizacion = 0.25
        cobertura_final = max(0.1, min(0.3, cobertura_ajustada))
    elif tipo_superficie == "VEGETACION_ESCASA":
        factor_penalizacion = 0.45
        cobertura_final = max(0.25, min(0.5, cobertura_ajustada))
    elif tipo_superficie == "VEGETACION_MODERADA":
        factor_penalizacion = 0.75
        cobertura_final = max(0.5, min(0.8, cobertura_ajustada))
    else:  # VEGETACION_DENSA
        factor_penalizacion = 1.0
        cobertura_final = max(0.8, min(0.98, cobertura_ajustada))
    
    # 5. VALIDACIÓN FINAL CON ÍNDICE DE VARI
    # VARI es bueno para distinguir vegetación de suelo en áreas mixtas
    if indices['vari'] < -0.1 and tipo_superficie.startswith("VEGETACION"):
        # Posible corrección: podría ser suelo
        cobertura_final *= 0.7
        factor_penalizacion *= 0.8
        if cobertura_final < 0.3:
            tipo_superficie = "SUELO_PARCIAL"
    
    return tipo_superficie, cobertura_final, factor_penalizacion, indices

# METODOLOGÍA GEE MEJORADA CON DETECCIÓN AVANZADA DE SUELO
def calcular_indices_forrajeros_gee(gdf, tipo_pastura, params):
    """
    Implementa metodología GEE MEJORADA con detección avanzada de suelo desnudo
    """
    
    n_poligonos = len(gdf)
    resultados = []
    
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
        # Normalizar posición para simular variación espacial
        x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        
        patron_espacial = (x_norm * 0.6 + y_norm * 0.4)
        
        # 1. SIMULAR BANDAS SENTINEL-2 MEJORADO
        blue, green, red, nir, swir1, swir2 = simular_bandas_sentinel_realista(patron_espacial, tipo_pastura)
        
        # 2. DETECCIÓN AVANZADA DE SUELO vs VEGETACIÓN
        tipo_superficie, cobertura_vegetal, factor_penalizacion, indices_avanzados = detectar_suelo_vegetacion_avanzado(
            blue, green, red, nir, swir1, swir2, params
        )
        
        # 3. USAR LOS ÍNDICES CALCULADOS EN LA DETECCIÓN
        ndvi = indices_avanzados['ndvi']
        evi = indices_avanzados['evi']
        savi = indices_avanzados['savi']
        bsi = indices_avanzados['bsi']
        ndbi = indices_avanzados['ndbi']
        msavi2 = indices_avanzados['msavi2']
        vari = indices_avanzados['vari']
        
        # 4. CÁLCULO DE BIOMASA CON PENALIZACIÓN POR SUELO
        if tipo_superficie in ["SUELO_DESNUDO", "SUELO_PARCIAL"]:
            # Biomasa muy reducida en áreas con suelo
            biomasa_base = params['MS_POR_HA_OPTIMO'] * 0.1 * cobertura_vegetal
            crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.1
            calidad_forrajera = 0.1
            
        else:
            # Biomasa normal para áreas con vegetación
            biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
            biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
            biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
            biomasa_msavi2 = (msavi2 * params['FACTOR_MSAVI2'] + params['OFFSET_BIOMASA'] * 0.8)
            
            biomasa_ms_ha = (biomasa_ndvi * 0.3 + biomasa_evi * 0.3 + biomasa_savi * 0.2 + biomasa_msavi2 * 0.2)
            
            # APLICAR PENALIZACIÓN POR TIPO DE SUPERFICIE
            biomasa_ms_ha = biomasa_ms_ha * factor_penalizacion
            biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
            
            crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
            crecimiento_diario = max(5, min(150, crecimiento_diario))
            
            # Calidad forrajera basada en índices
            calidad_forrajera = (ndvi * 0.4 + evi * 0.3 + savi * 0.2 + vari * 0.1)
            calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
        
        # 5. BIOMASA DISPONIBLE REAL (considerando cobertura y tipo de superficie)
        eficiencia_cosecha = 0.25
        perdidas = 0.30
        biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
        biomasa_disponible = max(0, min(1200, biomasa_disponible))
        
        # 6. PROBABILIDAD DE SUELO DESNUDO (para análisis)
        prob_suelo_desnudo = 0.0
        if tipo_superficie == "SUELO_DESNUDO":
            prob_suelo_desnudo = 0.95
        elif tipo_superficie == "SUELO_PARCIAL":
            prob_suelo_desnudo = 0.65
        elif tipo_superficie == "VEGETACION_ESCASA":
            prob_suelo_desnudo = 0.25
        else:
            prob_suelo_desnudo = 0.05
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'bsi': round(bsi, 3),
            'ndbi': round(ndbi, 3),
            'msavi2': round(msavi2, 3),
            'vari': round(vari, 3),
            'cobertura_vegetal': round(cobertura_vegetal, 3),
            'prob_suelo_desnudo': round(prob_suelo_desnudo, 3),
            'tipo_superficie': tipo_superficie,
            'factor_penalizacion': round(factor_penalizacion, 3),
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento_diario, 1),
            'factor_calidad': round(calidad_forrajera, 3)
        })
    
    return resultados

# CÁLCULO DE MÉTRICAS GANADERAS - ACTUALIZADO
def calcular_metricas_ganaderas(gdf_analizado, params, peso_promedio, carga_animal):
    """
    Calcula equivalentes vaca y días de permanencia usando metodología GEE
    """
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        crecimiento_diario = row['crecimiento_diario']
        
        # 1. CONSUMO INDIVIDUAL (kg MS/animal/día) - Método GEE
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # 2. EQUIVALENTES VACA (EV) - Fórmula GEE corregida
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        # EV = Biomasa (ton) / Consumo diario = EV por día
        ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
        
        # EV sostenibles durante período de descanso
        ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
        
        # 3. DÍAS DE PERMANENCIA - Fórmula GEE
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            
            if consumo_total_diario > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                
                if dias_permanencia > 0:
                    crecimiento_total = crecimiento_diario * area_ha * dias_permanencia * 0.3
                    dias_ajustados = (biomasa_total_disponible + crecimiento_total) / consumo_total_diario
                    dias_permanencia = min(dias_ajustados, 5)
            else:
                dias_permanencia = 0
        else:
            dias_permanencia = 0
        
        # 4. TASA DE UTILIZACIÓN
        if carga_animal > 0 and biomasa_total_disponible > 0:
            consumo_potencial_diario = carga_animal * consumo_individual_kg
            biomasa_por_dia = biomasa_total_disponible / params['TASA_UTILIZACION_RECOMENDADA']
            tasa_utilizacion = min(1.0, consumo_potencial_diario / biomasa_por_dia)
        else:
            tasa_utilizacion = 0
        
        # 5. ESTADO FORRAJERO (como en GEE)
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
            'ev_soportable': round(ev_soportable, 1),
            'dias_permanencia': max(0, round(dias_permanencia, 1)),
            'tasa_utilizacion': round(tasa_utilizacion, 3),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_soportable / area_ha, 2) if area_ha > 0 else 0
        })
    
    return metricas

# FUNCIÓN MEJORADA PARA CREAR MAPA FORRAJERO
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
            ax.annotate(f"S{row['id_subLote']}\n{valor:.0f}", (centroid.x, centroid.y), 
                       xytext=(5, 5), textcoords="offset points", 
                       fontsize=8, color='black', weight='bold',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        ax.set_title(f'🌱 ANÁLISIS FORRAJERO - {tipo_pastura}\n'
                    f'{tipo_analisis} - {titulo_sufijo}', 
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

# FUNCIÓN MEJORADA PARA MAPA DE COBERTURA
def crear_mapa_cobertura(gdf, tipo_pastura):
    """Crea mapa MEJORADO de cobertura vegetal y tipos de superficie"""
    try:
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        
        # COLORES MEJORADOS PARA DIFERENCIAR SUELO vs VEGETACIÓN
        colores_superficie = {
            'SUELO_DESNUDO': '#8c510a',    # Marrón oscuro - suelo desnudo
            'SUELO_PARCIAL': '#bf812d',     # Marrón medio - suelo con algo de vegetación
            'VEGETACION_ESCASA': '#dfc27d', # Beige - vegetación muy escasa
            'VEGETACION_MODERADA': '#80cdc1', # Verde azulado - vegetación media
            'VEGETACION_DENSA': '#01665e',   # Verde oscuro - vegetación densa
            'INDETERMINADO': '#cccccc'      # Gris - áreas indeterminadas
        }
        
        for idx, row in gdf.iterrows():
            tipo_superficie = row['tipo_superficie']
            color = colores_superficie.get(tipo_superficie, '#cccccc')
            
            gdf.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=1.5)
            
            centroid = row.geometry.centroid
            # Mostrar ID y cobertura
            ax.annotate(f"S{row['id_subLote']}\n{row['cobertura_vegetal']:.1f}", 
                       (centroid.x, centroid.y), 
                       xytext=(5, 5), textcoords="offset points", 
                       fontsize=8, color='black', weight='bold',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        ax.set_title(f'🌱 MAPA DE COBERTURA VEGETAL - {tipo_pastura}\n'
                    f'Detección Avanzada de Suelo Desnudo vs Biomasa Forrajera', 
                    fontsize=14, fontweight='bold', pad=20)
        
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
        
        # LEYENDA MEJORADA
        leyenda_elementos = []
        for tipo, color in colores_superficie.items():
            if tipo != 'INDETERMINADO':  # No mostrar indeterminado en leyenda
                count = len(gdf[gdf['tipo_superficie'] == tipo])
                area = gdf[gdf['tipo_superficie'] == tipo]['area_ha'].sum()
                label = f"{tipo} ({count} lotes, {area:.1f} ha)"
                leyenda_elementos.append(mpatches.Patch(color=color, label=label))
        
        ax.legend(handles=leyenda_elementos, loc='upper right', fontsize=9)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        st.error(f"❌ Error creando mapa de cobertura: {str(e)}")
        return None

# =============================================================================
# FUNCIONES SIMPLIFICADAS DE VISUALIZACIÓN (sin dependencias externas)
# =============================================================================

def crear_analisis_correlacion_simple(gdf_analizado):
    """Crea análisis de correlación simple usando solo matplotlib y numpy"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. Correlación NDVI vs Biomasa
        ndvi = gdf_analizado['ndvi'].values
        biomasa = gdf_analizado['biomasa_disponible_kg_ms_ha'].values
        correlacion_ndvi = np.corrcoef(ndvi, biomasa)[0, 1]
        
        axes[0,0].scatter(ndvi, biomasa, alpha=0.6, color='green')
        axes[0,0].set_xlabel('NDVI')
        axes[0,0].set_ylabel('Biomasa Disponible (kg MS/ha)')
        axes[0,0].set_title(f'NDVI vs Biomasa\nCorrelación: {correlacion_ndvi:.3f}')
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Correlación Cobertura vs Días Permanencia
        cobertura = gdf_analizado['cobertura_vegetal'].values
        dias = gdf_analizado['dias_permanencia'].values
        correlacion_cob = np.corrcoef(cobertura, dias)[0, 1]
        
        axes[0,1].scatter(cobertura, dias, alpha=0.6, color='blue')
        axes[0,1].set_xlabel('Cobertura Vegetal')
        axes[0,1].set_ylabel('Días de Permanencia')
        axes[0,1].set_title(f'Cobertura vs Días Permanencia\nCorrelación: {correlacion_cob:.3f}')
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Matriz de correlación simple
        variables = ['ndvi', 'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha']
        variables_existentes = [v for v in variables if v in gdf_analizado.columns]
        
        if len(variables_existentes) > 1:
            data_corr = gdf_analizado[variables_existentes]
            corr_matrix = data_corr.corr()
            
            # Crear heatmap manualmente
            im = axes[1,0].imshow(corr_matrix.values, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)
            axes[1,0].set_xticks(range(len(corr_matrix.columns)))
            axes[1,0].set_yticks(range(len(corr_matrix.columns)))
            axes[1,0].set_xticklabels(corr_matrix.columns, rotation=45)
            axes[1,0].set_yticklabels(corr_matrix.columns)
            axes[1,0].set_title('Matriz de Correlación')
            
            # Añadir valores de correlación
            for i in range(len(corr_matrix.columns)):
                for j in range(len(corr_matrix.columns)):
                    axes[1,0].text(j, i, f'{corr_matrix.iloc[i, j]:.2f}', 
                                  ha='center', va='center', 
                                  color='white' if abs(corr_matrix.iloc[i, j]) > 0.5 else 'black')
        
        # 4. Distribución de biomasa por tipo de superficie
        if 'tipo_superficie' in gdf_analizado.columns:
            tipos = gdf_analizado['tipo_superficie'].unique()
            data_boxplot = [gdf_analizado[gdf_analizado['tipo_superficie'] == tipo]['biomasa_disponible_kg_ms_ha'] for tipo in tipos]
            
            axes[1,1].boxplot(data_boxplot, labels=tipos)
            axes[1,1].set_ylabel('Biomasa Disponible (kg MS/ha)')
            axes[1,1].set_title('Biomasa por Tipo de Superficie')
            axes[1,1].tick_params(axis='x', rotation=45)
            axes[1,1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, corr_matrix if 'corr_matrix' in locals() else None
        
    except Exception as e:
        st.error(f"Error en análisis de correlación: {str(e)}")
        return None, None

def crear_tabla_resultados_detallada(gdf_analizado):
    """Crea tabla detallada de resultados con estadísticas"""
    try:
        # Seleccionar columnas clave para el resumen
        columnas_resumen = [
            'id_subLote', 'area_ha', 'ndvi', 'cobertura_vegetal', 
            'tipo_superficie', 'biomasa_disponible_kg_ms_ha',
            'ev_ha', 'dias_permanencia', 'estado_forrajero'
        ]
        
        # Filtrar columnas existentes
        columnas_existentes = [col for col in columnas_resumen if col in gdf_analizado.columns]
        df_resumen = gdf_analizado[columnas_existentes].copy()
        
        # Calcular estadísticas por tipo de superficie
        if 'tipo_superficie' in df_resumen.columns:
            stats_por_tipo = df_resumen.groupby('tipo_superficie').agg({
                'area_ha': ['count', 'sum', 'mean'],
                'biomasa_disponible_kg_ms_ha': ['mean', 'std', 'min', 'max'],
                'dias_permanencia': ['mean', 'std']
            }).round(2)
            
            # Aplanar columnas multiindex
            stats_por_tipo.columns = ['_'.join(col).strip() for col in stats_por_tipo.columns.values]
            stats_por_tipo = stats_por_tipo.reset_index()
        
        # Estadísticas generales
        stats_generales = pd.DataFrame({
            'Métrica': [
                'Total Sub-Lotes', 'Área Total (ha)', 
                'Biomasa Promedio (kg MS/ha)', 'Días Permanencia Promedio',
                'EV/Ha Promedio', 'Cobertura Vegetal Promedio (%)'
            ],
            'Valor': [
                len(gdf_analizado),
                round(gdf_analizado['area_ha'].sum(), 1),
                round(gdf_analizado['biomasa_disponible_kg_ms_ha'].mean(), 1),
                round(gdf_analizado['dias_permanencia'].mean(), 1),
                round(gdf_analizado['ev_ha'].mean(), 2),
                round(gdf_analizado['cobertura_vegetal'].mean() * 100, 1)
            ]
        })
        
        return df_resumen, stats_por_tipo, stats_generales
        
    except Exception as e:
        st.error(f"Error creando tabla de resultados: {str(e)}")
        return None, None, None

def crear_dashboard_metricas(gdf_analizado):
    """Crea dashboard visual con las métricas principales"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. Distribución de biomasa
        axes[0,0].hist(gdf_analizado['biomasa_disponible_kg_ms_ha'], bins=15, alpha=0.7, color='green', edgecolor='black')
        axes[0,0].axvline(gdf_analizado['biomasa_disponible_kg_ms_ha'].mean(), color='red', linestyle='--', linewidth=2, label='Promedio')
        axes[0,0].set_xlabel('Biomasa Disponible (kg MS/ha)')
        axes[0,0].set_ylabel('Frecuencia')
        axes[0,0].set_title('Distribución de Biomasa Disponible')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Distribución de días de permanencia
        axes[0,1].hist(gdf_analizado['dias_permanencia'], bins=15, alpha=0.7, color='blue', edgecolor='black')
        axes[0,1].axvline(gdf_analizado['dias_permanencia'].mean(), color='red', linestyle='--', linewidth=2, label='Promedio')
        axes[0,1].set_xlabel('Días de Permanencia')
        axes[0,1].set_ylabel('Frecuencia')
        axes[0,1].set_title('Distribución de Días de Permanencia')
        axes[0,1].legend()
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Scatter: NDVI vs Biomasa
        axes[1,0].scatter(gdf_analizado['ndvi'], gdf_analizado['biomasa_disponible_kg_ms_ha'], alpha=0.6, color='orange')
        axes[1,0].set_xlabel('NDVI')
        axes[1,0].set_ylabel('Biomasa Disponible (kg MS/ha)')
        axes[1,0].set_title('Relación NDVI vs Biomasa')
        axes[1,0].grid(True, alpha=0.3)
        
        # 4. Distribución por tipo de superficie (pie chart)
        if 'tipo_superficie' in gdf_analizado.columns:
            counts = gdf_analizado['tipo_superficie'].value_counts()
            colors = ['#8c510a', '#bf812d', '#dfc27d', '#80cdc1', '#01665e']
            axes[1,1].pie(counts.values, labels=counts.index, autopct='%1.1f%%', colors=colors[:len(counts)])
            axes[1,1].set_title('Distribución por Tipo de Superficie')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        st.error(f"Error creando dashboard: {str(e)}")
        return None

def crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total, params):
    """Crea un resumen ejecutivo en texto"""
    total_ev = gdf_analizado['ev_soportable'].sum()
    dias_prom = gdf_analizado['dias_permanencia'].mean()
    biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = gdf_analizado['biomasa_total_kg'].sum()
    
    # Calcular áreas por tipo de superficie
    area_por_tipo = gdf_analizado.groupby('tipo_superficie')['area_ha'].sum()
    area_vegetacion = area_por_tipo.get('VEGETACION_DENSA', 0) + area_por_tipo.get('VEGETACION_MODERADA', 0) + area_por_tipo.get('VEGETACION_ESCASA', 0)
    area_suelo = area_por_tipo.get('SUELO_DESNUDO', 0) + area_por_tipo.get('SUELO_PARCIAL', 0)
    
    resumen = f"""
RESUMEN EJECUTIVO - ANÁLISIS FORRAJERO PERSONALIZADO
====================================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Tipo de Pastura: {tipo_pastura}
Área Total: {area_total:.1f} ha
Sub-Lotes Analizados: {len(gdf_analizado)}

PARÁMETROS FORRAJEROS UTILIZADOS
-------------------------------
• MS Óptimo: {params['MS_POR_HA_OPTIMO']} kg MS/ha
• Crecimiento Diario: {params['CRECIMIENTO_DIARIO']} kg MS/ha/día
• Consumo: {params['CONSUMO_PORCENTAJE_PESO']*100}% del peso vivo
• Digestibilidad: {params['DIGESTIBILIDAD']*100}%
• Proteína Cruda: {params['PROTEINA_CRUDA']*100}%
• Tasa Utilización: {params['TASA_UTILIZACION_RECOMENDADA']*100}%

MÉTRICAS PRINCIPALES
-------------------
• Capacidad Total: {total_ev:.0f} Equivalentes Vaca
• Permanencia Promedio: {dias_prom:.0f} días
• Biomasa Disponible Promedio: {biomasa_prom:.0f} kg MS/ha
• Biomasa Total: {biomasa_total/1000:.1f} ton MS

ANÁLISIS DE COBERTURA MEJORADO
-----------------------------
• Área con Vegetación: {area_vegetacion:.1f} ha ({(area_vegetacion/area_total*100):.1f}%)
• Área sin Vegetación: {area_suelo:.1f} ha ({(area_suelo/area_total*100):.1f}%)
• Cobertura Vegetal Promedio: {(gdf_analizado['cobertura_vegetal'].mean()*100):.1f}%

DISTRIBUCIÓN POR TIPO DE SUPERFICIE
----------------------------------
"""
    
    for tipo in ['SUELO_DESNUDO', 'SUELO_PARCIAL', 'VEGETACION_ESCASA', 'VEGETACION_MODERADA', 'VEGETACION_DENSA']:
        if tipo in area_por_tipo:
            area_tipo = area_por_tipo[tipo]
            porcentaje = (area_tipo/area_total*100)
            count = len(gdf_analizado[gdf_analizado['tipo_superficie'] == tipo])
            resumen += f"• {tipo}: {count} sub-lotes, {area_tipo:.1f} ha ({porcentaje:.1f}%)\n"
    
    resumen += f"""
RECOMENDACIONES GENERALES
-----------------------
"""
    
    if dias_prom < 15:
        resumen += "• ROTACIÓN URGENTE: Considerar reducir carga animal o suplementar\n"
    elif dias_prom < 30:
        resumen += "• MANEJO VIGILANTE: Monitorear crecimiento y planificar rotaciones\n"
    else:
        resumen += "• SITUACIÓN ÓPTIMA: Mantener manejo actual y monitorear periódicamente\n"
    
    if area_suelo > area_total * 0.3:
        resumen += "• ALTA PROPORCIÓN DE SUELO: Considerar mejoras de suelo y resiembra\n"
    
    return resumen

# FUNCIÓN PRINCIPAL DE ANÁLISIS FORRAJERO - MEJORADA
def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, config_personalizada=None):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # OBTENER PARÁMETROS (BASE O PERSONALIZADOS)
        params = obtener_parametros_pastura(tipo_pastura, config_personalizada)
        
        # MOSTRAR RESUMEN DE PARÁMETROS
        with st.expander("📊 VER PARÁMETROS FORRAJEROS UTILIZADOS"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("MS Óptimo", f"{params['MS_POR_HA_OPTIMO']} kg/ha")
                st.metric("Crecimiento Diario", f"{params['CRECIMIENTO_DIARIO']} kg/ha/día")
            with col2:
                st.metric("Consumo", f"{params['CONSUMO_PORCENTAJE_PESO']*100}% peso")
                st.metric("Digestibilidad", f"{params['DIGESTIBILIDAD']*100}%")
            with col3:
                st.metric("Proteína Cruda", f"{params['PROTEINA_CRUDA']*100}%")
                st.metric("Tasa Utilización", f"{params['TASA_UTILIZACION_RECOMENDADA']*100}%")
        
        # PASO 1: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 2: CALCULAR ÍNDICES FORRAJEROS GEE MEJORADO
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS")
        with st.spinner("Ejecutando algoritmos con parámetros personalizados..."):
            indices_forrajeros = calcular_indices_forrajeros_gee(gdf_dividido, tipo_pastura, params)
        
        # Crear dataframe con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        # Añadir índices forrajeros
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 3: CALCULAR MÉTRICAS GANADERAS
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca y días de permanencia..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, params, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # =============================================================================
        # SECCIÓN DE VISUALIZACIONES Y ANÁLISIS
        # =============================================================================
        
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
        
        # Pestañas para diferentes tipos de visualización
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🗺️ MAPAS", "📈 ANÁLISIS", "📋 TABLAS", "📊 DASHBOARD", "📑 INFORME"
        ])
        
        with tab1:
            st.subheader("🗺️ Visualización de Mapas")
            
            col1, col2 = st.columns(2)
            with col1:
                # Mapa de productividad
                mapa_buf, titulo = crear_mapa_forrajero_gee(gdf_analizado, "PRODUCTIVIDAD", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
            
            with col2:
                # Mapa de días de permanencia
                mapa_buf, titulo = crear_mapa_forrajero_gee(gdf_analizado, "DIAS_PERMANENCIA", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
            
            # Mapa de cobertura
            mapa_cobertura = crear_mapa_cobertura(gdf_analizado, tipo_pastura)
            if mapa_cobertura:
                st.image(mapa_cobertura, caption="Mapa de Cobertura Vegetal y Tipos de Superficie", use_column_width=True)
        
        with tab2:
            st.subheader("📈 Análisis Estadístico")
            
            # Análisis de correlación
            correlacion_buf, corr_matrix = crear_analisis_correlacion_simple(gdf_analizado)
            if correlacion_buf:
                st.image(correlacion_buf, caption="Análisis de Correlación entre Variables", use_column_width=True)
                
                if corr_matrix is not None:
                    st.subheader("Matriz de Correlación")
                    st.dataframe(corr_matrix.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1), 
                               use_container_width=True)
        
        with tab3:
            st.subheader("📋 Tablas de Resultados Detallados")
            
            # Crear tablas de resultados
            df_resumen, stats_por_tipo, stats_generales = crear_tabla_resultados_detallada(gdf_analizado)
            
            if df_resumen is not None:
                st.subheader("Resumen por Sub-Lote")
                st.dataframe(df_resumen, use_container_width=True)
                
                # Estadísticas por tipo de superficie
                if stats_por_tipo is not None:
                    st.subheader("Estadísticas por Tipo de Superficie")
                    st.dataframe(stats_por_tipo, use_container_width=True)
                
                # Estadísticas generales
                if stats_generales is not None:
                    st.subheader("Estadísticas Generales")
                    st.dataframe(stats_generales, use_container_width=True)
                
                # Botón para descargar datos
                csv = df_resumen.to_csv(index=False)
                st.download_button(
                    "📥 Descargar Resultados Completos (CSV)",
                    csv,
                    file_name=f"resultados_forrajeros_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
        
        with tab4:
            st.subheader("📊 Dashboard de Métricas")
            
            # Dashboard visual
            dashboard_buf = crear_dashboard_metricas(gdf_analizado)
            if dashboard_buf:
                st.image(dashboard_buf, caption="Dashboard de Métricas Forrajeras", use_column_width=True)
        
        with tab5:
            st.subheader("📑 Informe Ejecutivo")
            
            # Resumen ejecutivo
            resumen = crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total, params)
            st.text_area("Resumen Ejecutivo", resumen, height=300)
            
            # Recomendaciones específicas
            st.subheader("🎯 Recomendaciones de Manejo")
            
            # Análisis de categorías
            if 'estado_forrajero' in gdf_analizado.columns:
                cats = gdf_analizado['estado_forrajero'].value_counts()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Lotes Óptimos/Buenos", f"{cats.get(4, 0) + cats.get(3, 0)}")
                    st.metric("Lotes en Alerta/Crítico", f"{cats.get(1, 0) + cats.get(0, 0)}")
                
                with col2:
                    st.metric("Lotes Adecuados", f"{cats.get(2, 0)}")
                    st.metric("Tasa de Éxito", f"{(cats.get(4, 0) + cats.get(3, 0) + cats.get(2, 0)) / len(gdf_analizado) * 100:.1f}%")
            
            # Recomendaciones basadas en análisis
            st.info("""
            **📋 RECOMENDACIONES BASADAS EN EL ANÁLISIS:**
            
            **✅ ACCIONES INMEDIATAS:**
            - Priorizar rotación en lotes con menos de 2 días de permanencia
            - Considerar suplementación en áreas críticas
            - Monitorear intensivamente lotes con estado forrajero bajo
            
            **📅 PLANEACIÓN MEDIO PLAZO:**
            - Optimizar rotación usando el mapa de días de permanencia
            - Planificar resiembras en áreas de suelo desnudo
            - Ajustar carga animal según capacidad por sub-lote
            
            **🌱 MEJORAS ESTRATÉGICAS:**
            - Implementar manejo diferenciado por tipo de superficie
            - Usar análisis de correlación para optimizar prácticas
            - Establecer monitoreo continuo con mismos parámetros
            """)
        
        # MOSTRAR RESUMEN CON PARÁMETROS PERSONALIZADOS
        st.subheader("📋 RESUMEN EJECUTIVO PERSONALIZADO")
        
        total_ev_soportable = gdf_analizado['ev_soportable'].sum()
        dias_promedio = gdf_analizado['dias_permanencia'].mean()
        biomasa_total = gdf_analizado['biomasa_total_kg'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🏭 CAPACIDAD TOTAL", f"{total_ev_soportable:.0f} EV")
        with col2:
            st.metric("📅 PERMANENCIA PROMEDIO", f"{dias_promedio:.0f} días")
        with col3:
            st.metric("🌿 BIOMASA TOTAL", f"{biomasa_total/1000:.1f} ton MS")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis forrajero: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

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
                    
                    # Cargar configuración si se subió
                    config_personalizada = None
                    if uploaded_config is not None:
                        try:
                            config_personalizada = json.load(uploaded_config)
                            st.success("✅ Configuración personalizada cargada")
                        except Exception as e:
                            st.error(f"❌ Error cargando configuración: {e}")
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO PERSONALIZADO", type="primary"):
                        analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, config_personalizada)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero personalizado")
    
    with st.expander("ℹ️ INFORMACIÓN SOBRE PARÁMETROS PERSONALIZABLES"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO - PARÁMETROS PERSONALIZABLES**
        
        **🎯 NUEVA FUNCIONALIDAD: PARÁMETROS AJUSTABLES**
        
        **📊 PARÁMETROS FORRAJeros PERSONALIZABLES:**
        - **MS Óptimo:** Producción máxima de materia seca por hectárea
        - **Crecimiento Diario:** Tasa de crecimiento diario del forraje
        - **Consumo (% peso):** Porcentaje del peso vivo que consume cada animal
        - **Digestibilidad:** Porcentaje de digestibilidad del forraje
        - **Proteína Cruda:** Contenido de proteína del forraje
        - **Tasa Utilización:** Porcentaje de forraje que puede ser consumido
        
        **🛰️ PARÁMETROS SATELITALES AVANZADOS:**
        - **Factores de Biomasa:** Conversión de índices vegetación a biomasa
        - **Umbrales de Suelo:** Límites para detección de suelo desnudo
        - **Penalizaciones:** Ajustes por tipo de superficie
        
        **💾 GUARDAR/CARGAR CONFIGURACIONES:**
        - **Guardar:** Descarga configuración actual como archivo JSON
        - **Cargar:** Usa configuraciones guardadas para análisis repetitivos
        - **Compartir:** Intercambia configuraciones entre usuarios/regiones
        
        **🚀 BENEFICIOS:**
        - **Específico por región:** Ajusta parámetros a condiciones locales
        - **Flexibilidad:** Adapta a diferentes tipos de pasturas
        - **Consistencia:** Mantiene configuraciones para análisis comparativos
        - **Precisión:** Mejora resultados con datos locales reales
        """)
