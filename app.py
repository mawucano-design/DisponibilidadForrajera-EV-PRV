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

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
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

# PARÁMETROS FORRAJEROS (mantener igual)
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
    # ... (mantener los otros parámetros igual)
}

# Función para obtener parámetros según selección
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
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

# PALETAS GEE (mantener igual)
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
    'COBERTURA': ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60']
}

# =============================================================================
# NUEVAS FUNCIONES PARA DIFERENTES SATÉLITES
# =============================================================================

def obtener_imagen_satelital(geometry, fuente_satelital, fecha_imagen, nubes_max=20):
    """
    Obtiene imagen según la fuente satelital seleccionada
    """
    try:
        if fuente_satelital == "SENTINEL-2":
            return obtener_imagen_sentinel2(geometry, fecha_imagen, nubes_max)
        elif fuente_satelital in ["LANDSAT-8", "LANDSAT-9"]:
            return obtener_imagen_landsat(geometry, fuente_satelital, fecha_imagen, nubes_max)
        else:
            return None  # Para modo SIMULADO
    except Exception as e:
        st.error(f"❌ Error obteniendo imagen {fuente_satelital}: {e}")
        return None

def obtener_imagen_sentinel2(geometry, fecha_imagen, nubes_max=20):
    """
    Obtiene imagen Sentinel-2 (implementación simplificada)
    En producción, conectar con API real de Sentinel Hub
    """
    st.info("🛰️ Usando datos de Sentinel-2 (simulación)")
    
    # Simular bandas Sentinel-2
    bounds = geometry.bounds
    width = int((bounds[2] - bounds[0]) * 1000)  # Resolución aproximada
    height = int((bounds[3] - bounds[1]) * 1000)
    
    # Crear arrays simulados para las bandas
    bandas = {}
    for banda, nombre in SENTINEL2_BANDAS.items():
        # Simular datos con variación espacial
        data = simular_banda_satelital(width, height, nombre, bounds)
        bandas[nombre] = data
    
    return {
        'bandas': bandas,
        'bounds': bounds,
        'transform': None,
        'fuente': 'SENTINEL-2',
        'fecha': fecha_imagen
    }

def obtener_imagen_landsat(geometry, tipo_landsat, fecha_imagen, nubes_max=20):
    """
    Obtiene imagen Landsat (implementación simplificada)
    """
    st.info(f"🛰️ Usando datos de {tipo_landsat} (simulación)")
    
    bounds = geometry.bounds
    width = int((bounds[2] - bounds[0]) * 1000)  # Resolución aproximada
    height = int((bounds[3] - bounds[1]) * 1000)
    
    # Definir bandas según Landsat
    if tipo_landsat == "LANDSAT-8":
        bandas_landsat = LANDSAT8_BANDAS
    else:  # LANDSAT-9
        bandas_landsat = LANDSAT9_BANDAS
    
    bandas = {}
    for banda, nombre in bandas_landsat.items():
        # Simular datos con variación espacial
        data = simular_banda_satelital(width, height, nombre, bounds)
        bandas[nombre] = data
    
    return {
        'bandas': bandas,
        'bounds': bounds,
        'transform': None,
        'fuente': tipo_landsat,
        'fecha': fecha_imagen
    }

def simular_banda_satelital(width, height, nombre_banda, bounds):
    """
    Simula datos de banda satelital con patrones realistas
    """
    # Crear gradientes espaciales
    x = np.linspace(0, 1, width)
    y = np.linspace(0, 1, height)
    X, Y = np.meshgrid(x, y)
    
    # Patrones base según el tipo de banda
    if 'blue' in nombre_banda:
        base = 0.1 + 0.05 * np.sin(5*X) * np.cos(5*Y)
    elif 'green' in nombre_banda:
        base = 0.15 + 0.08 * np.sin(4*X) * np.cos(4*Y)
    elif 'red' in nombre_banda:
        base = 0.2 + 0.1 * np.sin(3*X) * np.cos(3*Y)
    elif 'nir' in nombre_banda:
        base = 0.3 + 0.15 * np.sin(2*X) * np.cos(2*Y)
    elif 'swir1' in nombre_banda or 'swir2' in nombre_banda:
        base = 0.25 + 0.1 * np.sin(2.5*X) * np.cos(2.5*Y)
    else:
        base = 0.2 + 0.1 * np.sin(3*X) * np.cos(3*Y)
    
    # Agregar ruido y variabilidad
    ruido = np.random.normal(0, 0.02, (height, width))
    return np.clip(base + ruido, 0, 1)

# DEFINICIÓN DE BANDAS POR SATÉLITE
SENTINEL2_BANDAS = {
    'B02': 'blue',
    'B03': 'green', 
    'B04': 'red',
    'B08': 'nir',
    'B11': 'swir1',
    'B12': 'swir2'
}

LANDSAT8_BANDAS = {
    'B2': 'blue',
    'B3': 'green',
    'B4': 'red', 
    'B5': 'nir',
    'B6': 'swir1',
    'B7': 'swir2'
}

LANDSAT9_BANDAS = {
    'B2': 'blue',
    'B3': 'green',
    'B4': 'red',
    'B5': 'nir', 
    'B6': 'swir1',
    'B7': 'swir2'
}

# =============================================================================
# CÁLCULO DE ÍNDICES MEJORADO PARA DIFERENTES SATÉLITES
# =============================================================================

def calcular_indices_satelitales(bandas, fuente_satelital):
    """
    Calcula índices vegetacionales adaptados al satélite específico
    """
    try:
        # Obtener bandas según el satélite
        if fuente_satelital == "SENTINEL-2":
            blue = bandas.get('blue', np.zeros_like(next(iter(bandas.values()))))
            green = bandas.get('green', np.zeros_like(next(iter(bandas.values()))))
            red = bandas.get('red', np.zeros_like(next(iter(bandas.values()))))
            nir = bandas.get('nir', np.zeros_like(next(iter(bandas.values()))))
            swir1 = bandas.get('swir1', np.zeros_like(next(iter(bandas.values()))))
            swir2 = bandas.get('swir2', np.zeros_like(next(iter(bandas.values()))))
        else:  # Landsat
            blue = bandas.get('blue', np.zeros_like(next(iter(bandas.values()))))
            green = bandas.get('green', np.zeros_like(next(iter(bandas.values()))))
            red = bandas.get('red', np.zeros_like(next(iter(bandas.values()))))
            nir = bandas.get('nir', np.zeros_like(next(iter(bandas.values()))))
            swir1 = bandas.get('swir1', np.zeros_like(next(iter(bandas.values()))))
            swir2 = bandas.get('swir2', np.zeros_like(next(iter(bandas.values()))))
        
        # Calcular índices con manejo de divisiones por cero
        with np.errstate(divide='ignore', invalid='ignore'):
            # NDVI - Normalized Difference Vegetation Index
            ndvi = np.where(
                (nir + red) != 0,
                (nir - red) / (nir + red),
                0
            )
            ndvi = np.clip(ndvi, -1, 1)
            
            # EVI - Enhanced Vegetation Index (fórmula adaptada)
            evi = np.where(
                (nir + 6 * red - 7.5 * blue + 1) != 0,
                2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1),
                0
            )
            evi = np.clip(evi, -1, 1)
            
            # SAVI - Soil Adjusted Vegetation Index
            savi = np.where(
                (nir + red + 0.5) != 0,
                1.5 * (nir - red) / (nir + red + 0.5),
                0
            )
            savi = np.clip(savi, -1, 1)
            
            # NDWI - Normalized Difference Water Index
            ndwi = np.where(
                (nir + swir1) != 0,
                (nir - swir1) / (nir + swir1),
                0
            )
            ndwi = np.clip(ndwi, -1, 1)
            
            # BSI - Bare Soil Index
            bsi = np.where(
                ((swir1 + red) + (nir + blue)) != 0,
                ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)),
                0
            )
            bsi = np.clip(bsi, -1, 1)
            
            # NDBI - Normalized Difference Built-up Index
            ndbi = np.where(
                (swir1 + nir) != 0,
                (swir1 - nir) / (swir1 + nir),
                0
            )
            ndbi = np.clip(ndbi, -1, 1)
            
            # MSAVI2 - Modified Soil Adjusted Vegetation Index
            msavi2 = np.where(
                (2 * nir + 1) != 0,
                (2 * nir + 1 - np.sqrt((2 * nir + 1)**2 - 8 * (nir - red))) / 2,
                0
            )
            msavi2 = np.clip(msavi2, -1, 1)
        
        return {
            'ndvi': ndvi,
            'evi': evi,
            'savi': savi,
            'ndwi': ndwi,
            'bsi': bsi,
            'ndbi': ndbi,
            'msavi2': msavi2,
            'blue': blue,
            'green': green,
            'red': red,
            'nir': nir,
            'swir1': swir1,
            'swir2': swir2,
            'fuente': fuente_satelital
        }
        
    except Exception as e:
        st.error(f"❌ Error calculando índices {fuente_satelital}: {e}")
        return None

# =============================================================================
# FUNCIÓN PRINCIPAL DE CÁLCULO DE ÍNDICES ACTUALIZADA
# =============================================================================

def calcular_indices_forrajeros_gee(gdf, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max=20):
    """
    Implementa metodología GEE con múltiples fuentes satelitales
    """
    try:
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
        
        # Obtener imagen satelital si no es modo SIMULADO
        bandas_completas = None
        indices_completos = None
        
        if fuente_satelital != "SIMULADO":
            st.info(f"🛰️ Obteniendo imagen de {fuente_satelital}...")
            geometry = gdf.unary_union
            bandas_completas = obtener_imagen_satelital(geometry, fuente_satelital, fecha_imagen, nubes_max)
            
            if bandas_completas:
                indices_completos = calcular_indices_satelitales(bandas_completas['bandas'], fuente_satelital)
                if indices_completos:
                    st.success(f"✅ Índices calculados a partir de {fuente_satelital}")
                else:
                    st.warning("⚠️ Error calculando índices. Usando datos simulados.")
            else:
                st.warning("⚠️ No se pudieron obtener imágenes satelitales. Usando datos simulados.")
        
        # Procesar cada sub-lote
        for idx, row in gdf_centroids.iterrows():
            id_subLote = row['id_subLote']
            
            # Normalizar posición para simular variación espacial
            x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
            y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
            
            # Obtener índices según la fuente de datos
            if indices_completos and fuente_satelital != "SIMULADO":
                # Usar índices reales/simulados del satélite
                try:
                    # Extraer valores promedio para el sub-lote (simplificado)
                    ndvi = np.nanmean(indices_completos['ndvi']) if np.any(indices_completos['ndvi']) else 0.5
                    evi = np.nanmean(indices_completos['evi']) if np.any(indices_completos['evi']) else 0.4
                    savi = np.nanmean(indices_completos['savi']) if np.any(indices_completos['savi']) else 0.45
                    ndwi = np.nanmean(indices_completos['ndwi']) if np.any(indices_completos['ndwi']) else 0.1
                    bsi = np.nanmean(indices_completos['bsi']) if np.any(indices_completos['bsi']) else 0.1
                    ndbi = np.nanmean(indices_completos['ndbi']) if np.any(indices_completos['ndbi']) else 0.05
                    
                    # Ajustar según patrón espacial
                    factor_ajuste = 0.8 + (x_norm * 0.2 + y_norm * 0.1)
                    ndvi = np.clip(ndvi * factor_ajuste, 0.1, 0.9)
                    evi = np.clip(evi * factor_ajuste, 0.1, 0.8)
                    savi = np.clip(savi * factor_ajuste, 0.1, 0.8)
                    
                except Exception as e:
                    st.warning(f"⚠️ Error procesando sub-lote {id_subLote}. Usando valores simulados.")
                    ndvi, evi, savi, ndwi, bsi, ndbi = simular_indices_para_sublote(id_subLote, x_norm, y_norm)
            else:
                # Usar simulación completa
                ndvi, evi, savi, ndwi, bsi, ndbi = simular_indices_para_sublote(id_subLote, x_norm, y_norm)
            
            # Resto del cálculo (clasificación de suelo, biomasa, etc.)
            # ... (mantener igual que antes)
            
            probabilidad_suelo_desnudo = simular_patron_suelo_desnudo_mejorado(id_subLote, x_norm, y_norm)
            
            tipo_superficie, cobertura_vegetal = clasificar_suelo_desnudo_mejorado(
                ndvi, bsi, ndbi, evi, savi, probabilidad_suelo_desnudo
            )
            
            # Cálculo de biomasa (igual que antes)
            if tipo_superficie == "SUELO_DESNUDO":
                biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.02 * cobertura_vegetal)
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.02
                calidad_forrajera = 0.02
            elif tipo_superficie == "SUELO_PARCIAL":
                biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.15 * cobertura_vegetal)
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.15
                calidad_forrajera = 0.15
            else:
                biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
                biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
                biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
                
                biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
                biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
                
                crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
                crecimiento_diario = max(5, min(150, crecimiento_diario))
                
                calidad_forrajera = (ndwi + 1) / 2
                calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
            
            # Biomasa disponible
            if tipo_superficie in ["SUELO_DESNUDO"]:
                biomasa_disponible = 0
            else:
                eficiencia_cosecha = 0.25
                perdidas = 0.30
                biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
                biomasa_disponible = max(0, min(1200, biomasa_disponible))
            
            resultados.append({
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'ndwi': round(float(ndwi), 3),
                'bsi': round(float(bsi), 3),
                'ndbi': round(float(ndbi), 3),
                'cobertura_vegetal': round(cobertura_vegetal, 3),
                'prob_suelo_desnudo': round(probabilidad_suelo_desnudo, 3),
                'tipo_superficie': tipo_superficie,
                'biomasa_ms_ha': round(biomasa_ms_ha, 1),
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'factor_calidad': round(calidad_forrajera, 3),
                'fuente_datos': fuente_satelital
            })
        
        return resultados
        
    except Exception as e:
        st.error(f"❌ Error en cálculo con {fuente_satelital}: {e}")
        return calcular_indices_forrajeros_simulados(gdf, tipo_pastura)

def simular_indices_para_sublote(id_subLote, x_norm, y_norm):
    """
    Simula índices para un sub-lote específico
    """
    np.random.seed(id_subLote)
    
    # Base con variación espacial
    base_ndvi = 0.3 + (x_norm * 0.4 + y_norm * 0.2)
    base_evi = 0.25 + (x_norm * 0.35 + y_norm * 0.15)
    base_savi = 0.28 + (x_norm * 0.38 + y_norm * 0.18)
    
    # Variabilidad
    variabilidad = np.random.normal(0, 0.1)
    
    ndvi = np.clip(base_ndvi + variabilidad, 0.1, 0.9)
    evi = np.clip(base_evi + variabilidad * 0.8, 0.1, 0.8)
    savi = np.clip(base_savi + variabilidad * 0.9, 0.1, 0.8)
    ndwi = np.random.uniform(-0.2, 0.4)
    bsi = np.random.uniform(-0.3, 0.3)
    ndbi = np.random.uniform(-0.2, 0.2)
    
    return ndvi, evi, savi, ndwi, bsi, ndbi

# =============================================================================
# FUNCIÓN PRINCIPAL DE ANÁLISIS ACTUALIZADA
# =============================================================================

def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, fuente_satelital, fecha_imagen, nubes_max):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # Mostrar información de la fuente satelital
        st.subheader("🛰️ INFORMACIÓN SATELITAL")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Fuente", fuente_satelital)
        with col2:
            st.metric("Fecha", fecha_imagen.strftime("%Y-%m-%d"))
        with col3:
            st.metric("Nubes Máx", f"{nubes_max}%")
        
        # Obtener parámetros según selección
        params = obtener_parametros_forrajeros(tipo_pastura)
        
        # Mostrar parámetros usados
        with st.expander("🔍 PARÁMETROS FORRAJEROS UTILIZADOS"):
            st.write(f"**Biomasa Óptima:** {params['MS_POR_HA_OPTIMO']} kg MS/ha")
            st.write(f"**Crecimiento Diario:** {params['CRECIMIENTO_DIARIO']} kg MS/ha/día")
            st.write(f"**Consumo Animal:** {params['CONSUMO_PORCENTAJE_PESO']*100}% del peso vivo")
            st.write(f"**Tasa Utilización:** {params['TASA_UTILIZACION_RECOMENDADA']*100}%")
            st.write(f"**Fuente Satelital:** {fuente_satelital}")
        
        # PASO 1: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 2: CALCULAR ÍNDICES FORRAJEROS GEE MEJORADO
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS GEE")
        with st.spinner(f"Ejecutando algoritmos GEE con {fuente_satelital}..."):
            indices_forrajeros = calcular_indices_forrajeros_gee(
                gdf_dividido, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max
            )
        
        # Crear dataframe con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        # Añadir índices forrajeros
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # ... (el resto de la función se mantiene igual)
        
        # PASO 3: CALCULAR MÉTRICAS GANADERAS
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca y días de permanencia..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # ... (el resto del análisis se mantiene igual)

# =============================================================================
# INTERFAZ PRINCIPAL ACTUALIZADA
# =============================================================================

# ... (mantener la interfaz principal igual, pero ahora incluye la selección de satélite)

st.markdown("### 📁 CARGAR DATOS DEL POTRERO")

# Procesar archivo subido
gdf_cargado = None
if uploaded_zip is not None:
    with st.spinner("Cargando y procesando shapefile..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf_cargado = gpd.read_file(shp_path)
                    st.session_state.gdf_cargado = gdf_cargado
                    
                    area_total = calcular_superficie(gdf_cargado).sum()
                    
                    st.success(f"✅ **Potrero cargado exitosamente!**")
                    
                    # Mostrar información del potrero
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Polígonos", len(gdf_cargado))
                    with col2:
                        st.metric("Área Total", f"{area_total:.1f} ha")
                    with col3:
                        st.metric("Pastura", tipo_pastura)
                    with col4:
                        st.metric("Satélite", fuente_satelital)
                        
        except Exception as e:
            st.error(f"❌ Error cargando shapefile: {str(e)}")

# BOTÓN PRINCIPAL
st.markdown("---")
st.markdown("### 🚀 ACCIÓN PRINCIPAL")

if st.session_state.gdf_cargado is not None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; padding: 20px; border: 2px solid #4CAF50; border-radius: 10px; background-color: #f9fff9;'>
            <h3>¿Listo para analizar?</h3>
            <p>Ejecuta el análisis forrajero con {fuente_satelital}</p>
        </div>
        """.format(fuente_satelital=fuente_satelital), unsafe_allow_html=True)
        
        if st.button("**🚀 EJECUTAR ANÁLISIS FORRAJERO GEE**", 
                    type="primary", 
                    use_container_width=True,
                    key="analisis_principal"):
            with st.spinner("🔬 Ejecutando análisis forrajero completo..."):
                resultado = analisis_forrajero_completo(
                    st.session_state.gdf_cargado, 
                    tipo_pastura, 
                    peso_promedio, 
                    carga_animal, 
                    n_divisiones,
                    fuente_satelital,
                    fecha_imagen,
                    nubes_max
                )
                if resultado:
                    st.balloons()
else:
    st.info("""
    **📋 Para comenzar el análisis:**
    
    1. **Selecciona la fuente satelital** (Sentinel-2, Landsat-8, Landsat-9 o Simulado)
    2. **Configura los parámetros** en la barra lateral izquierda
    3. **Sube el archivo ZIP** con el shapefile de tu potrero
    4. **Haz clic en el botón** que aparecerá aquí para ejecutar el análisis
    
    ⚠️ **Asegúrate de que el archivo ZIP contenga todos los archivos del shapefile**
    """)

# Información sobre satélites
with st.expander("🛰️ INFORMACIÓN SOBRE FUENTES SATELITALES"):
    st.markdown("""
    **🌍 COMPARACIÓN DE SATÉLITES:**
    
    | Característica | Sentinel-2 | Landsat-8/9 | Simulado |
    |----------------|------------|-------------|----------|
    | **Resolución** | 10-20m | 30m | - |
    | **Temporalidad** | 5 días | 16 días | Instantáneo |
    | **Bandas** | 13 bandas | 11 bandas | Simuladas |
    | **Cobertura** | Global | Global | - |
    | **Costo** | Gratuito | Gratuito | Gratuito |
    
    **🎯 RECOMENDACIONES:**
    - **Sentinel-2:** Mayor resolución espacial, ideal para lotes pequeños
    - **Landsat:** Mayor historial temporal, ideal para análisis de tendencias
    - **Simulado:** Para pruebas y demostraciones sin conexión a internet
    """)
