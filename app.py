import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon
import math
import requests
import rasterio
from rasterio.mask import mask
import json
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN MEJORADA DE VEGETACIÓN")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar variables de personalización con valores por defecto
ms_optimo = 3000
crecimiento_diario = 50
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.2
umbral_ndvi_pastura = 0.55

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selector de mapa base - NUEVA FUNCIONALIDAD
    st.subheader("🗺️ Mapa Base")
    base_map_option = st.selectbox(
        "Seleccionar mapa base:",
        ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
        index=0,
        help="ESRI Satélite: Imágenes satelitales reales. OpenStreetMap: Mapa estándar. CartoDB: Mapa claro."
    )
    
    # Selección de satélite
    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
        help="Sentinel-2: Mayor resolución (10m). Landsat: Cobertura global histórica."
    )
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Configuración de fechas para imágenes satelitales
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now(),
        help="Selecciona la fecha para la imagen satelital"
    )
    
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)
    
    # Parámetros avanzados de detección de vegetación
    st.subheader("🌿 Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.1, 0.5, 0.3, 0.01,
                                  help="NDVI por debajo de este valor se considera suelo desnudo")
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.5, 0.9, 0.7, 0.01,
                                  help="NDVI por encima de este valor se considera vegetación densa")
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.7, 0.1,
                                  help="Mayor valor = más estricto en detectar suelo desnudo")
    
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

# =============================================================================
# CONFIGURACIÓN DE MAPAS BASE - NUEVA SECCIÓN
# =============================================================================

# Configuración de mapas base
BASE_MAPS_CONFIG = {
    "ESRI Satélite": {
        "tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        "attr": 'Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        "name": "ESRI Satellite"
    },
    "OpenStreetMap": {
        "tiles": 'OpenStreetMap',
        "attr": 'OpenStreetMap contributors',
        "name": "OpenStreetMap"
    },
    "CartoDB Positron": {
        "tiles": 'CartoDB positron',
        "attr": 'CartoDB',
        "name": "CartoDB Positron"
    }
}

def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"):
    """
    Crea un mapa interactivo con múltiples opciones de base map
    """
    if gdf is None or len(gdf) == 0:
        return None
    
    # Obtener el centro del geometry
    centroid = gdf.geometry.centroid.iloc[0]
    center_lat, center_lon = centroid.y, centroid.x
    
    # Crear mapa base
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles=None,  # Important: no tiles por defecto
        control_scale=True
    )
    
    # Agregar todos los mapas base como opciones
    for map_name, config in BASE_MAPS_CONFIG.items():
        folium.TileLayer(
            tiles=config["tiles"],
            attr=config["attr"],
            name=config["name"],
            overlay=False,
            control=True
        ).add_to(m)
    
    # Establecer el mapa base seleccionado por defecto
    selected_config = BASE_MAPS_CONFIG[base_map_name]
    folium.TileLayer(
        tiles=selected_config["tiles"],
        attr=selected_config["attr"],
        name=selected_config["name"],
        overlay=True  # Esto asegura que se muestre por defecto
    ).add_to(m)
    
    # Agregar el geometry al mapa
    folium.GeoJson(
        gdf.__geo_interface__,
        style_function=lambda x: {
            'fillColor': '#3388ff',
            'color': 'blue',
            'weight': 2,
            'fillOpacity': 0.2
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['id_subLote'] if 'id_subLote' in gdf.columns else [],
            aliases=['Sub-Lote:'] if 'id_subLote' in gdf.columns else ['Área:'],
            localize=True
        )
    ).add_to(m)
    
    # Agregar control de capas
    folium.LayerControl().add_to(m)
    
    # Agregar marcador en el centro
    folium.Marker(
        [center_lat, center_lon],
        popup=f"Centro del Potrero\nLat: {center_lat:.4f}\nLon: {center_lon:.4f}",
        tooltip="Centro del Potrero",
        icon=folium.Icon(color='green', icon='info-sign')
    ).add_to(m)
    
    return m

# =============================================================================
# PARÁMETROS FORRAJEROS Y FUNCIONES BÁSICAS
# =============================================================================

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA
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

# =============================================================================
# ALGORITMOS MEJORADOS DE DETECCIÓN DE VEGETACIÓN
# =============================================================================

class DetectorVegetacionMejorado:
    """
    Clase mejorada para detección realista de vegetación basada en investigación científica
    """
    
    def __init__(self, umbral_ndvi_minimo=0.3, umbral_ndvi_optimo=0.7, sensibilidad_suelo=0.7):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo
        
        # Parámetros basados en investigación científica
        self.parametros_cientificos = {
            'ndvi_suelo_desnudo_max': 0.2,
            'ndvi_vegetacion_escasa_min': 0.2,
            'ndvi_vegetacion_escasa_max': 0.4,
            'ndvi_vegetacion_moderada_min': 0.4,
            'ndvi_vegetacion_moderada_max': 0.6,
            'ndvi_vegetacion_densa_min': 0.6,
            'bsi_suelo_min': 0.1,
            'ndbi_suelo_min': 0.05,
            'evi_vegetacion_min': 0.15,
            'savi_vegetacion_min': 0.15
        }
    
    def clasificar_vegetacion_cientifica(self, ndvi, evi, savi, bsi, ndbi, msavi2=None):
        """
        Clasificación mejorada basada en múltiples índices y criterios científicos
        """
        # 1. ANÁLISIS PRINCIPAL CON NDVI
        if ndvi < self.parametros_cientificos['ndvi_suelo_desnudo_max']:
            categoria_ndvi = "SUELO_DESNUDO"
            confianza_ndvi = 0.9
        elif ndvi < self.parametros_cientificos['ndvi_vegetacion_escasa_max']:
            categoria_ndvi = "VEGETACION_ESCASA"
            confianza_ndvi = 0.7
        elif ndvi < self.parametros_cientificos['ndvi_vegetacion_moderada_max']:
            categoria_ndvi = "VEGETACION_MODERADA"
            confianza_ndvi = 0.8
        else:
            categoria_ndvi = "VEGETACION_DENSA"
            confianza_ndvi = 0.9
        
        # 2. VERIFICACIÓN CON OTROS ÍNDICES
        criterios_suelo = 0
        criterios_vegetacion = 0
        
        # Criterios para suelo desnudo
        if bsi > self.parametros_cientificos['bsi_suelo_min']:
            criterios_suelo += 2
        if ndbi > self.parametros_cientificos['ndbi_suelo_min']:
            criterios_suelo += 1
        if evi < self.parametros_cientificos['evi_vegetacion_min']:
            criterios_suelo += 1
        if savi < self.parametros_cientificos['savi_vegetacion_min']:
            criterios_suelo += 1
        
        # Criterios para vegetación
        if evi > self.parametros_cientificos['evi_vegetacion_min']:
            criterios_vegetacion += 1
        if savi > self.parametros_cientificos['savi_vegetacion_min']:
            criterios_vegetacion += 1
        if msavi2 and msavi2 > 0.2:
            criterios_vegetacion += 1
        
        # 3. DECISIÓN FINAL CON PESOS
        if criterios_suelo >= 3 and ndvi < 0.25:
            # Fuerte evidencia de suelo desnudo
            categoria_final = "SUELO_DESNUDO"
            cobertura = max(0.01, 0.05 - (criterios_suelo * 0.01))
        elif criterios_suelo >= 2 and ndvi < 0.3:
            # Evidencia moderada de suelo desnudo
            categoria_final = "SUELO_PARCIAL"
            cobertura = 0.15
        elif categoria_ndvi == "SUELO_DESNUDO" and criterios_vegetacion >= 1:
            # Posible falso positivo de suelo desnudo
            categoria_final = "VEGETACION_ESCASA"
            cobertura = 0.25
        elif categoria_ndvi == "VEGETACION_DENSA" and criterios_vegetacion >= 2:
            # Confirmación de vegetación densa
            categoria_final = "VEGETACION_DENSA"
            # Calcular cobertura basada en NDVI
            cobertura = min(0.95, 0.6 + (ndvi - 0.6) * 0.7)
        else:
            # Seguir la clasificación NDVI con ajustes
            categoria_final = categoria_ndvi
            if categoria_final == "SUELO_DESNUDO":
                cobertura = 0.05
            elif categoria_final == "VEGETACION_ESCASA":
                cobertura = 0.3
            elif categoria_final == "VEGETACION_MODERADA":
                cobertura = 0.6
            else:
                cobertura = 0.85
        
        # Aplicar sensibilidad del usuario
        if self.sensibilidad_suelo > 0.7 and categoria_final in ["VEGETACION_ESCASA", "VEGETACION_MODERADA"]:
            # Ser más estricto con vegetación escasa
            if ndvi < 0.35:
                categoria_final = "SUELO_PARCIAL"
                cobertura = 0.2
        
        return categoria_final, max(0.01, min(0.95, cobertura))
    
    def calcular_biomasa_realista(self, ndvi, evi, savi, categoria_vegetacion, cobertura, params):
        """
        Cálculo mejorado de biomasa basado en investigación forrajera
        """
        # Factores de corrección según tipo de vegetación
        if categoria_vegetacion == "SUELO_DESNUDO":
            return 0, 0, 0.1
        
        elif categoria_vegetacion == "SUELO_PARCIAL":
            # Biomasa muy reducida para áreas con suelo parcial
            factor_biomasa = 0.1
            factor_crecimiento = 0.1
            factor_calidad = 0.2
        
        elif categoria_vegetacion == "VEGETACION_ESCASA":
            # Vegetación escasa - usar índices más conservadores
            factor_biomasa = 0.3 + (ndvi * 0.4)
            factor_crecimiento = 0.4
            factor_calidad = 0.4 + (ndvi * 0.3)
        
        elif categoria_vegetacion == "VEGETACION_MODERADA":
            # Vegetación moderada
            factor_biomasa = 0.6 + (ndvi * 0.3)
            factor_crecimiento = 0.7
            factor_calidad = 0.6 + (ndvi * 0.2)
        
        else:  # VEGETACION_DENSA
            # Vegetación densa - máximo potencial
            factor_biomasa = 0.8 + (ndvi * 0.2)
            factor_crecimiento = 0.9
            factor_calidad = 0.8 + (ndvi * 0.1)
        
        # Aplicar factores de corrección por cobertura
        factor_cobertura = cobertura ** 0.8  # Reducción no lineal
        
        # Cálculo final de biomasa
        biomasa_base = params['MS_POR_HA_OPTIMO'] * factor_biomasa
        biomasa_ajustada = biomasa_base * factor_cobertura
        
        # Limitar valores máximos realistas
        biomasa_ms_ha = min(6000, max(0, biomasa_ajustada))
        
        # Crecimiento diario ajustado
        crecimiento_diario = params['CRECIMIENTO_DIARIO'] * factor_crecimiento * factor_cobertura
        crecimiento_diario = min(150, max(1, crecimiento_diario))
        
        # Calidad forrajera
        calidad_forrajera = min(0.9, max(0.1, factor_calidad * factor_cobertura))
        
        return biomasa_ms_ha, crecimiento_diario, calidad_forrajera

# =============================================================================
# SIMULACIÓN MEJORADA BASADA EN PATRONES REALES
# =============================================================================

def simular_patrones_reales_vegetacion(id_subLote, x_norm, y_norm, fuente_satelital):
    """
    Simula patrones realistas de vegetación basados en casos reales
    """
    # Patrones específicos de suelo desnudo (basado en casos reales)
    zonas_suelo_desnudo_alto = {
        17: 0.02,  # S17 - Suelo completamente desnudo
        12: 0.05,  # S12 - Suelo mayoritariamente desnudo
        7: 0.08,   # S7 - Suelo con muy poca vegetación
        3: 0.10,   # S3 - Suelo parcial
        14: 0.15   # S14 - Suelo con vegetación muy escasa
    }
    
    zonas_vegetacion_escasa = {
        1: 0.25, 8: 0.28, 15: 0.22, 22: 0.30, 5: 0.26
    }
    
    zonas_vegetacion_moderada = {
        2: 0.45, 9: 0.50, 16: 0.48, 23: 0.52, 6: 0.47
    }
    
    zonas_vegetacion_densa = {
        4: 0.72, 11: 0.68, 18: 0.75, 25: 0.70, 10: 0.73
    }
    
    # Determinar NDVI base según el patrón
    if id_subLote in zonas_suelo_desnudo_alto:
        ndvi_base = zonas_suelo_desnudo_alto[id_subLote]
    elif id_subLote in zonas_vegetacion_escasa:
        ndvi_base = zonas_vegetacion_escasa[id_subLote]
    elif id_subLote in zonas_vegetacion_moderada:
        ndvi_base = zonas_vegetacion_moderada[id_subLote]
    elif id_subLote in zonas_vegetacion_densa:
        ndvi_base = zonas_vegetacion_densa[id_subLote]
    else:
        # Patrón espacial general - los bordes tienden a tener menos vegetación
        distancia_borde = min(x_norm, 1-x_norm, y_norm, 1-y_norm)
        ndvi_base = 0.3 + (distancia_borde * 0.4)  # Mejor vegetación en el centro
    
    # Variabilidad natural
    variabilidad = np.random.normal(0, 0.08)
    ndvi = max(0.05, min(0.85, ndvi_base + variabilidad))
    
    # Calcular otros índices de forma consistente
    if ndvi < 0.2:
        # Suelo desnudo
        evi = ndvi * 0.8
        savi = ndvi * 0.7
        bsi = 0.3 + np.random.uniform(0, 0.2)
        ndbi = 0.1 + np.random.uniform(0, 0.1)
        msavi2 = ndvi * 0.6
    elif ndvi < 0.4:
        # Vegetación escasa
        evi = ndvi * 1.1
        savi = ndvi * 1.0
        bsi = 0.1 + np.random.uniform(0, 0.1)
        ndbi = 0.05 + np.random.uniform(0, 0.05)
        msavi2 = ndvi * 0.9
    elif ndvi < 0.6:
        # Vegetación moderada
        evi = ndvi * 1.2
        savi = ndvi * 1.1
        bsi = np.random.uniform(-0.1, 0.1)
        ndbi = np.random.uniform(-0.05, 0.05)
        msavi2 = ndvi * 1.0
    else:
        # Vegetación densa
        evi = ndvi * 1.3
        savi = ndvi * 1.2
        bsi = -0.1 + np.random.uniform(0, 0.1)
        ndbi = -0.05 + np.random.uniform(0, 0.05)
        msavi2 = ndvi * 1.1
    
    return ndvi, evi, savi, bsi, ndbi, msavi2

# =============================================================================
# FUNCIONES DE MÉTRICAS GANADERAS
# =============================================================================

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """
    Calcula equivalentes vaca y días de permanencia
    """
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        crecimiento_diario = row['crecimiento_diario']
        
        # 1. CONSUMO INDIVIDUAL (kg MS/animal/día)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # 2. EQUIVALENTES VACA (EV)
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01
        
        # EV por hectárea
        if ev_soportable > 0 and area_ha > 0:
            ev_ha = ev_soportable / area_ha
            if ev_ha < 0.1:
                ha_por_ev =
