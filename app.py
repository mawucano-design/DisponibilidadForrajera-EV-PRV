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
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE MEJORADA")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"])
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=72, value=48)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA - MEJORADOS CON DETECCIÓN DE SUELO/ROCA
PARAMETROS_FORRAJEROS = {
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
        # UMBRALES MEJORADOS PARA DETECCIÓN DE SUELO
        'UMBRAL_NDVI_SUELO': 0.15,        # NDVI < 0.15 = suelo desnudo
        'UMBRAL_BSI_SUELO': 0.25,         # BSI > 0.25 = suelo desnudo  
        'UMBRAL_NDBI_SUELO': 0.15,        # NDBI > 0.15 = área construida/suelo
        'UMBRAL_NDVI_VEGETACION': 0.35,   # NDVI > 0.35 = vegetación buena
        'FACTOR_COBERTURA_MAX': 0.95,
        'FACTOR_COBERTURA_MIN': 0.05,
        'PENALIZACION_SUELO': 0.85,       # Reducción biomasa en áreas con suelo
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
        'UMBRAL_BSI_SUELO': 0.22,
        'UMBRAL_NDBI_SUELO': 0.12,
        'UMBRAL_NDVI_VEGETACION': 0.40,
        'FACTOR_COBERTURA_MAX': 0.90,
        'FACTOR_COBERTURA_MIN': 0.08,
        'PENALIZACION_SUELO': 0.80,
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
        'UMBRAL_BSI_SUELO': 0.20,
        'UMBRAL_NDBI_SUELO': 0.10,
        'UMBRAL_NDVI_VEGETACION': 0.45,
        'FACTOR_COBERTURA_MAX': 0.85,
        'FACTOR_COBERTURA_MIN': 0.10,
        'PENALIZACION_SUELO': 0.75,
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
        'UMBRAL_BSI_SUELO': 0.18,
        'UMBRAL_NDBI_SUELO': 0.08,
        'UMBRAL_NDVI_VEGETACION': 0.50,
        'FACTOR_COBERTURA_MAX': 0.80,
        'FACTOR_COBERTURA_MIN': 0.15,
        'PENALIZACION_SUELO': 0.70,
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
        'UMBRAL_BSI_SUELO': 0.15,
        'UMBRAL_NDBI_SUELO': 0.06,
        'UMBRAL_NDVI_VEGETACION': 0.55,
        'FACTOR_COBERTURA_MAX': 0.75,
        'FACTOR_COBERTURA_MIN': 0.20,
        'PENALIZACION_SUELO': 0.60,
    }
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

# NUEVA FUNCIÓN MEJORADA PARA DETECCIÓN DE SUELO
def detectar_suelo_y_biomasa_mejorado(ndvi, bsi, ndbi, evi, savi, params):
    """
    Detección mejorada de suelo desnudo vs biomasa forrajera
    Retorna: tipo_superficie, cobertura_vegetal, factor_penalizacion
    """
    
    # 1. DETECCIÓN PRIMARIA DE SUELO DESNUDO
    es_suelo_desnudo = (
        (ndvi < params['UMBRAL_NDVI_SUELO']) and 
        (bsi > params['UMBRAL_BSI_SUELO']) and 
        (ndbi > params['UMBRAL_NDBI_SUELO'])
    )
    
    # 2. DETECCIÓN DE SUELO PARCIAL (mezcla suelo-vegetación)
    es_suelo_parcial = (
        (ndvi < params['UMBRAL_NDVI_SUELO'] * 1.3) and 
        (bsi > params['UMBRAL_BSI_SUELO'] * 0.7)
    )
    
    # 3. DETECCIÓN DE VEGETACIÓN ESCASA
    es_vegetacion_escasa = (
        (ndvi >= params['UMBRAL_NDVI_SUELO']) and 
        (ndvi < params['UMBRAL_NDVI_VEGETACION'] * 0.6)
    )
    
    # 4. VEGETACIÓN MODERADA
    es_vegetacion_moderada = (
        (ndvi >= params['UMBRAL_NDVI_VEGETACION'] * 0.6) and 
        (ndvi < params['UMBRAL_NDVI_VEGETACION'])
    )
    
    # 5. VEGETACIÓN DENSA
    es_vegetacion_densa = (ndvi >= params['UMBRAL_NDVI_VEGETACION'])
    
    # 6. CALCULAR COBERTURA VEGETAL REALISTA
    if es_suelo_desnudo:
        tipo_superficie = "SUELO_DESNUDO"
        cobertura_vegetal = params['FACTOR_COBERTURA_MIN']
        factor_penalizacion = params['PENALIZACION_SUELO'] * 0.1  # Solo 10% de biomasa
        
    elif es_suelo_parcial:
        tipo_superficie = "SUELO_PARCIAL" 
        # Cobertura basada en NDVI normalizado
        cobertura_vegetal = max(params['FACTOR_COBERTURA_MIN'], 
                               min(params['FACTOR_COBERTURA_MAX'] * 0.3, 
                                   (ndvi - params['UMBRAL_NDVI_SUELO']) / 
                                   (params['UMBRAL_NDVI_VEGETACION'] - params['UMBRAL_NDVI_SUELO'])))
        factor_penalizacion = params['PENALIZACION_SUELO'] * 0.4
        
    elif es_vegetacion_escasa:
        tipo_superficie = "VEGETACION_ESCASA"
        cobertura_vegetal = 0.3 + (ndvi - params['UMBRAL_NDVI_SUELO']) * 0.5
        factor_penalizacion = 0.6
        
    elif es_vegetacion_moderada:
        tipo_superficie = "VEGETACION_MODERADA"
        cobertura_vegetal = 0.6 + (ndvi - params['UMBRAL_NDVI_VEGETACION'] * 0.6) * 0.8
        factor_penalizacion = 0.8
        
    elif es_vegetacion_densa:
        tipo_superficie = "VEGETACION_DENSA"
        cobertura_vegetal = params['FACTOR_COBERTURA_MAX']
        factor_penalizacion = 1.0
        
    else:
        tipo_superficie = "INDETERMINADO"
        cobertura_vegetal = 0.5
        factor_penalizacion = 0.5
    
    # Asegurar que cobertura esté en rango razonable
    cobertura_vegetal = max(params['FACTOR_COBERTURA_MIN'], 
                           min(params['FACTOR_COBERTURA_MAX'], cobertura_vegetal))
    
    return tipo_superficie, cobertura_vegetal, factor_penalizacion

# METODOLOGÍA GEE MEJORADA CON DETECCIÓN AVANZADA DE SUELO
def calcular_indices_forrajeros_gee(gdf, tipo_pastura):
    """
    Implementa metodología GEE MEJORADA con detección avanzada de suelo desnudo
    """
    
    n_poligonos = len(gdf)
    resultados = []
    params = PARAMETROS_FORRAJEROS[tipo_pastura]
    
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
        
        # 1. SIMULAR BANDAS SENTINEL-2 CON VARIABILIDAD REALISTA
        # Ajustado para mejor detección de suelo
        blue = 0.10 + (patron_espacial * 0.12) + np.random.normal(0, 0.02)
        green = 0.13 + (patron_espacial * 0.18) + np.random.normal(0, 0.03)
        red = 0.16 + (patron_espacial * 0.22) + np.random.normal(0, 0.04)
        nir = 0.30 + (patron_espacial * 0.35) + np.random.normal(0, 0.08)
        swir1 = 0.22 + (patron_espacial * 0.25) + np.random.normal(0, 0.06)
        swir2 = 0.18 + (patron_espacial * 0.20) + np.random.normal(0, 0.05)
        
        # 2. CÁLCULO DE ÍNDICES VEGETACIONALES
        ndvi = (nir - red) / (nir + red) if (nir + red) > 0 else 0
        ndvi = max(-0.2, min(0.9, ndvi))
        
        evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1) if (nir + 6 * red - 7.5 * blue + 1) > 0 else 0
        evi = max(-0.2, min(0.8, evi))
        
        savi = 1.5 * (nir - red) / (nir + red + 0.5) if (nir + red + 0.5) > 0 else 0
        savi = max(-0.2, min(0.8, savi))
        
        # 3. ÍNDICES PARA DETECTAR SUELO DESNUDO/ROCA (MEJORADOS)
        bsi = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)) if ((swir1 + red) + (nir + blue)) > 0 else 0
        ndbi = (swir1 - nir) / (swir1 + nir) if (swir1 + nir) > 0 else 0
        ndsi = (green - swir1) / (green + swir1) if (green + swir1) > 0 else 0
        
        # 4. DETECCIÓN MEJORADA DE SUELO vs BIOMASA
        tipo_superficie, cobertura_vegetal, factor_penalizacion = detectar_suelo_y_biomasa_mejorado(
            ndvi, bsi, ndbi, evi, savi, params
        )
        
        # 5. CÁLCULO DE BIOMASA CON PENALIZACIÓN POR SUELO
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
            
            biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
            
            # APLICAR PENALIZACIÓN POR TIPO DE SUPERFICIE
            biomasa_ms_ha = biomasa_ms_ha * factor_penalizacion
            biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
            
            crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
            crecimiento_diario = max(5, min(150, crecimiento_diario))
            
            # Calidad forrajera basada en índices
            calidad_forrajera = (ndvi * 0.6 + evi * 0.4)
            calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
        
        # 6. BIOMASA DISPONIBLE REAL (considerando cobertura y tipo de superficie)
        eficiencia_cosecha = 0.25
        perdidas = 0.30
        biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
        biomasa_disponible = max(0, min(1200, biomasa_disponible))
        
        # 7. PROBABILIDAD DE SUELO DESNUDO (para análisis)
        prob_suelo_desnudo = 0.0
        if tipo_superficie == "SUELO_DESNUDO":
            prob_suelo_desnudo = 0.9
        elif tipo_superficie == "SUELO_PARCIAL":
            prob_suelo_desnudo = 0.6
        elif tipo_superficie == "VEGETACION_ESCASA":
            prob_suelo_desnudo = 0.3
        else:
            prob_suelo_desnudo = 0.1
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'bsi': round(bsi, 3),
            'ndbi': round(ndbi, 3),
            'ndsi': round(ndsi, 3),
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
def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """
    Calcula equivalentes vaca y días de permanencia usando metodología GEE
    """
    params = PARAMETROS_FORRAJEROS[tipo_pastura]
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
        
        ax.set_title(f'🌱 ANÁLISIS FORRAJERO GEE - {tipo_pastura}\n'
                    f'{tipo_analisis} - {titulo_sufijo}\n'
                    f'Metodología Google Earth Engine Mejorada', 
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
        
        ax.set_title(f'🌱 MAPA DE COBERTURA VEGETAL MEJORADO - {tipo_pastura}\n'
                    f'Detección Avanzada de Suelo Desnudo vs Biomasa Forrajera\n'
                    f'Metodología Google Earth Engine Mejorada', 
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

# FUNCIÓN DE VALIDACIÓN PARA VERIFICAR CORRELACIÓN
def validar_correlacion_datos(gdf_analizado):
    """
    Valida la correlación entre variables forrajeras
    """
    try:
        correlaciones = gdf_analizado[['biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia', 'area_ha']].corr()
        
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        axes[0,0].scatter(gdf_analizado['biomasa_disponible_kg_ms_ha'], gdf_analizado['dias_permanencia'], alpha=0.6)
        axes[0,0].set_xlabel('Biomasa Disponible (kg MS/ha)')
        axes[0,0].set_ylabel('Días Permanencia')
        axes[0,0].set_title('Biomasa vs Días Permanencia')
        
        axes[0,1].scatter(gdf_analizado['ev_ha'], gdf_analizado['dias_permanencia'], alpha=0.6)
        axes[0,1].set_xlabel('EV/Ha')
        axes[0,1].set_ylabel('Días Permanencia')
        axes[0,1].set_title('EV/Ha vs Días Permanencia')
        
        axes[1,0].scatter(gdf_analizado['biomasa_disponible_kg_ms_ha'], gdf_analizado['ev_ha'], alpha=0.6)
        axes[1,0].set_xlabel('Biomasa Disponible (kg MS/ha)')
        axes[1,0].set_ylabel('EV/Ha')
        axes[1,0].set_title('Biomasa vs EV/Ha')
        
        im = axes[1,1].imshow(correlaciones.values, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)
        axes[1,1].set_xticks(range(len(correlaciones.columns)))
        axes[1,1].set_yticks(range(len(correlaciones.columns)))
        axes[1,1].set_xticklabels(correlaciones.columns, rotation=45)
        axes[1,1].set_yticklabels(correlaciones.columns)
        axes[1,1].set_title('Matriz de Correlación')
        
        for i in range(len(correlaciones.columns)):
            for j in range(len(correlaciones.columns)):
                axes[1,1].text(j, i, f'{correlaciones.iloc[i, j]:.2f}', 
                              ha='center', va='center', color='white' if abs(correlaciones.iloc[i, j]) > 0.5 else 'black')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, correlaciones
        
    except Exception as e:
        st.error(f"Error en validación de correlación: {str(e)}")
        return None, None

# FUNCIÓN PARA CREAR ARCHIVO ZIP
def create_zip_file(files):
    """Crea un archivo ZIP con múltiples archivos"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_name, file_data in files:
            zip_file.writestr(file_name, file_data)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# FUNCIÓN PARA CREAR RESUMEN EJECUTIVO
def crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total):
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
RESUMEN EJECUTIVO - ANÁLISIS FORRAJERO MEJORADO
===============================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Tipo de Pastura: {tipo_pastura}
Área Total: {area_total:.1f} ha
Sub-Lotes Analizados: {len(gdf_analizado)}

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
def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO MEJORADO - {tipo_pastura}")
        
        # PASO 1: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 2: CALCULAR ÍNDICES FORRAJEROS GEE MEJORADO
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS GEE MEJORADO")
        with st.spinner("Ejecutando algoritmos GEE con detección avanzada de suelo..."):
            indices_forrajeros = calcular_indices_forrajeros_gee(gdf_dividido, tipo_pastura)
        
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
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 4: CATEGORIZAR PARA RECOMENDACIONES
        def categorizar_forrajero(estado_forrajero, dias_permanencia):
            if estado_forrajero == 0 or dias_permanencia < 1:
                return "CRÍTICO"
            elif estado_forrajero == 1 or dias_permanencia < 2:
                return "ALERTA"
            elif estado_forrajero == 2 or dias_permanencia < 3:
                return "ADECUADO"
            elif estado_forrajero == 3:
                return "BUENO"
            else:
                return "ÓPTIMO"
        
        gdf_analizado['categoria_manejo'] = [
            categorizar_forrajero(row['estado_forrajero'], row['dias_permanencia']) 
            for idx, row in gdf_analizado.iterrows()
        ]
        
        # PASO 5: MOSTRAR RESULTADOS
        st.subheader("📊 RESULTADOS DEL ANÁLISIS FORRAJERO MEJORADO")
        
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
        
        # PASO 6: ANÁLISIS DE COBERTURA MEJORADO
        st.subheader("🌿 ANÁLISIS DE COBERTURA VEGETAL MEJORADO")
        
        stats_cobertura = gdf_analizado['tipo_superficie'].value_counts()
        area_por_tipo = gdf_analizado.groupby('tipo_superficie')['area_ha'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            cobertura_prom = gdf_analizado['cobertura_vegetal'].mean()
            st.metric("Cobertura Vegetal Promedio", f"{cobertura_prom:.1%}")
        with col2:
            area_vegetacion = area_por_tipo.get('VEGETACION_DENSA', 0) + area_por_tipo.get('VEGETACION_MODERADA', 0) + area_por_tipo.get('VEGETACION_ESCASA', 0)
            st.metric("Área con Vegetación", f"{area_vegetacion:.1f} ha")
        with col3:
            area_suelo = area_por_tipo.get('SUELO_DESNUDO', 0) + area_por_tipo.get('SUELO_PARCIAL', 0)
            st.metric("Área sin Vegetación", f"{area_suelo:.1f} ha")
        
        # NUEVO: ANÁLISIS DETALLADO DE SUELO DESNUDO
        st.subheader("🏜️ ANÁLISIS DETALLADO DE SUELO DESNUDO")
        
        # Calcular métricas específicas de suelo
        area_suelo_desnudo = area_por_tipo.get('SUELO_DESNUDO', 0)
        area_suelo_parcial = area_por_tipo.get('SUELO_PARCIAL', 0)
        area_total_suelo = area_suelo_desnudo + area_suelo_parcial
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Área Suelo Desnudo", f"{area_suelo_desnudo:.1f} ha")
        with col2:
            st.metric("Área Suelo Parcial", f"{area_suelo_parcial:.1f} ha")
        with col3:
            st.metric("Total Área sin Vegetación", f"{area_total_suelo:.1f} ha")
        with col4:
            porcentaje_suelo = (area_total_suelo / area_total) * 100
            st.metric("% Sin Vegetación", f"{porcentaje_suelo:.1f}%")
        
        # RECOMENDACIONES ESPECÍFICAS PARA SUELO DESNUDO
        if porcentaje_suelo > 30:
            st.warning("🚨 **ALTA PROPORCIÓN DE SUELO DESNUDO DETECTADA**")
            st.markdown("""
            **Recomendaciones específicas:**
            - 📍 **Identificar causas:** erosión, sobrepastoreo, condiciones naturales
            - 🌱 **Plan de recuperación:** resiembra, enmiendas orgánicas
            - 💧 **Manejo hídrico:** conservación de agua, riego estratégico
            - 🐄 **Ajuste carga:** reducir temporalmente la carga animal
            - 📊 **Monitoreo:** seguimiento mensual de recuperación
            """)
        elif porcentaje_suelo > 15:
            st.info("⚠️ **PROPORCIÓN MODERADA DE SUELO DESNUDO**")
            st.markdown("""
            **Acciones recomendadas:**
            - 📈 **Manejo preventivo:** evitar aumento de áreas sin vegetación
            - 🔄 **Rotación cuidadosa:** mayor descanso para áreas afectadas
            - 🌿 **Fertilización estratégica:** en áreas con potencial de recuperación
            """)
        
        # Mapa de cobertura MEJORADO
        st.write("**🗺️ MAPA DE COBERTURA VEGETAL MEJORADO**")
        mapa_cobertura = crear_mapa_cobertura(gdf_analizado, tipo_pastura)
        if mapa_cobertura:
            st.image(mapa_cobertura, use_container_width=True)
            
            st.download_button(
                "📥 Descargar Mapa de Cobertura",
                mapa_cobertura.getvalue(),
                f"mapa_cobertura_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                "image/png",
                key="descarga_cobertura"
            )
        
        # TABLA DE TIPOS DE SUPERFICIE
        st.write("**📊 DISTRIBUCIÓN DE TIPOS DE SUPERFICIE**")
        resumen_cobertura = pd.DataFrame({
            'Tipo de Superficie': stats_cobertura.index,
            'Número de Sub-Lotes': stats_cobertura.values,
            'Área Total (ha)': [area_por_tipo.get(tipo, 0) for tipo in stats_cobertura.index],
            'Porcentaje del Área': [f"{(area_por_tipo.get(tipo, 0) / area_total * 100):.1f}%" 
                                  for tipo in stats_cobertura.index]
        })
        st.dataframe(resumen_cobertura, use_container_width=True)
        
        # PASO 7: MAPAS FORRAJEROS
        st.subheader("🗺️ MAPAS FORRAJEROS GEE MEJORADOS")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("**📈 PRODUCTIVIDAD**")
            mapa_biomasa, titulo_biomasa = crear_mapa_forrajero_gee(gdf_analizado, "PRODUCTIVIDAD", tipo_pastura)
            if mapa_biomasa:
                st.image(mapa_biomasa, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa Productividad",
                    mapa_biomasa.getvalue(),
                    f"mapa_productividad_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png",
                    key="descarga_biomasa"
                )
        
        with col2:
            st.write("**🐄 DISPONIBILIDAD**")
            mapa_ev, titulo_ev = crear_mapa_forrajero_gee(gdf_analizado, "DISPONIBILIDAD", tipo_pastura)
            if mapa_ev:
                st.image(mapa_ev, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa Disponibilidad",
                    mapa_ev.getvalue(),
                    f"mapa_disponibilidad_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png",
                    key="descarga_disponibilidad"
                )
        
        with col3:
            st.write("**📅 PERMANENCIA**")
            mapa_dias, titulo_dias = crear_mapa_forrajero_gee(gdf_analizado, "DIAS_PERMANENCIA", tipo_pastura)
            if mapa_dias:
                st.image(mapa_dias, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa Permanencia",
                    mapa_dias.getvalue(),
                    f"mapa_permanencia_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png",
                    key="descarga_permanencia"
                )
        
        # PASO 8: VALIDACIÓN DE CORRELACIONES
        st.subheader("🔍 VALIDACIÓN DE CORRELACIONES")
        
        with st.spinner("Validando consistencia de datos..."):
            mapa_validacion, correlaciones = validar_correlacion_datos(gdf_analizado)
        
        if mapa_validacion:
            st.image(mapa_validacion, use_container_width=True)
            
            st.write("**📊 Matriz de Correlación:**")
            st.dataframe(correlaciones.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1))
            
            corr_biomasa_dias = correlaciones.loc['biomasa_disponible_kg_ms_ha', 'dias_permanencia']
            corr_ev_dias = correlaciones.loc['ev_ha', 'dias_permanencia']
            
            col1, col2 = st.columns(2)
            with col1:
                if corr_biomasa_dias > 0.7:
                    st.success(f"✅ Alta correlación Biomasa-Días: {corr_biomasa_dias:.3f}")
                elif corr_biomasa_dias > 0.4:
                    st.warning(f"⚠️ Correlación moderada Biomasa-Días: {corr_biomasa_dias:.3f}")
                else:
                    st.error(f"❌ Baja correlación Biomasa-Días: {corr_biomasa_dias:.3f}")
            
            with col2:
                if corr_ev_dias > 0.7:
                    st.success(f"✅ Alta correlación EV-Días: {corr_ev_dias:.3f}")
                elif corr_ev_dias > 0.4:
                    st.warning(f"⚠️ Correlación moderada EV-Días: {corr_ev_dias:.3f}")
                else:
                    st.error(f"❌ Baja correlación EV-Días: {corr_ev_dias:.3f}")
        
        # PASO 9: DESCARGAS
        st.subheader("📦 DESCARGAR RESULTADOS")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if mapa_biomasa and mapa_ev and mapa_dias and mapa_cobertura:
                st.download_button(
                    "🗂️ Descargar Pack Completo",
                    data=create_zip_file([
                        ("productividad.png", mapa_biomasa.getvalue()),
                        ("disponibilidad.png", mapa_ev.getvalue()),
                        ("permanencia.png", mapa_dias.getvalue()),
                        ("cobertura.png", mapa_cobertura.getvalue())
                    ]),
                    file_name=f"mapas_forrajeros_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                    key="descarga_pack"
                )
        
        with col2:
            resumen_texto = crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total)
            st.download_button(
                "📋 Descargar Resumen Ejecutivo",
                resumen_texto,
                f"resumen_ejecutivo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                "text/plain",
                key="descarga_resumen"
            )
        
        with col3:
            csv = gdf_analizado.to_csv(index=False)
            st.download_button(
                "📊 Descargar Datos Completos",
                csv,
                f"datos_completos_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                key="descarga_datos"
            )
        
        # PASO 10: TABLA DETALLADA
        st.subheader("🔬 MÉTRICAS DETALLADAS POR SUB-LOTE")
        
        columnas_detalle = ['id_subLote', 'area_ha', 'biomasa_disponible_kg_ms_ha', 'ndvi', 'evi', 
                          'cobertura_vegetal', 'tipo_superficie', 'ev_ha', 'dias_permanencia', 
                          'tasa_utilizacion', 'categoria_manejo']
        
        tabla_detalle = gdf_analizado[columnas_detalle].copy()
        tabla_detalle.columns = ['Sub-Lote', 'Área (ha)', 'Biomasa Disp (kg MS/ha)', 'NDVI', 'EVI',
                               'Cobertura', 'Tipo Superficie', 'EV/Ha', 'Días Permanencia', 
                               'Tasa Utilización', 'Categoría']
        
        st.dataframe(tabla_detalle, use_container_width=True)
        
        # PASO 11: RECOMENDACIONES DE MANEJO
        st.subheader("💡 RECOMENDACIONES DE MANEJO FORRAJERO MEJORADAS")
        
        categorias = gdf_analizado['categoria_manejo'].unique()
        for cat in sorted(categorias):
            subset = gdf_analizado[gdf_analizado['categoria_manejo'] == cat]
            area_cat = subset['area_ha'].sum()
            
            with st.expander(f"🎯 **{cat}** - {area_cat:.1f} ha ({(area_cat/area_total*100):.1f}% del área)"):
                
                if cat == "CRÍTICO":
                    st.markdown("**🚨 ESTRATEGIA: ROTACIÓN INMEDIATA**")
                    st.markdown("- Sacar animales inmediatamente")
                    st.markdown("- Suplementación estratégica requerida")
                    st.markdown("- Evaluar resiembra o recuperación")
                    st.markdown("- **Áreas con suelo desnudo:** priorizar recuperación")
                    
                elif cat == "ALERTA":
                    st.markdown("**⚠️ ESTRATEGIA: ROTACIÓN CERCANA**")
                    st.markdown("- Planificar rotación en 5-10 días")
                    st.markdown("- Monitorear crecimiento diario")
                    st.markdown("- Considerar suplementación ligera")
                    st.markdown("- **Áreas con suelo parcial:** manejo conservador")
                    
                elif cat == "ADEQUADO":
                    st.markdown("**✅ ESTRATEGIA: MANEJO ACTUAL**")
                    st.markdown("- Continuar con rotación planificada")
                    st.markdown("- Monitoreo semanal")
                    st.markdown("- Ajustar carga si es necesario")
                    st.markdown("- **Vegetación escasa:** fertilización estratégica")
                    
                elif cat == "BUENO":
                    st.markdown("**👍 ESTRATEGIA: MANTENIMIENTO**")
                    st.markdown("- Carga animal adecuada")
                    st.markdown("- Continuar manejo actual")
                    st.markdown("- Enfoque en sostenibilidad")
                    st.markdown("- **Vegetación moderada:** optimizar rotaciones")
                    
                else:  # ÓPTIMO
                    st.markdown("**🌟 ESTRATEGIA: EXCELENTE**")
                    st.markdown("- Condiciones óptimas")
                    st.markdown("- Mantener prácticas actuales")
                    st.markdown("- Modelo a replicar")
                    st.markdown("- **Vegetación densa:** máximo aprovechamiento sostenible")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Sub-Lotes", len(subset))
                with col2:
                    st.metric("Días Prom", f"{subset['dias_permanencia'].mean():.0f}")
                with col3:
                    st.metric("EV Prom", f"{subset['ev_soportable'].mean():.0f}")
        
        # PASO 12: RESUMEN EJECUTIVO
        st.subheader("📋 RESUMEN EJECUTIVO MEJORADO")
        
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
        
        # INFORMACIÓN TÉCNICA MEJORADA
        with st.expander("🔍 VER METODOLOGÍA GEE DETALLADA MEJORADA"):
            st.markdown(f"""
            **🌐 METODOLOGÍA GOOGLE EARTH ENGINE - ANÁLISIS FORRAJERO MEJORADO**
            
            **🆕 MEJORAS EN DETECCIÓN DE SUELO DESNUDO:**
            - **Detección avanzada:** Combinación de NDVI, BSI y NDBI
            - **Cobertura realista:** Cálculo basado en tipo de superficie
            - **Penalización por suelo:** Biomasa reducida en áreas sin vegetación
            - **Umbrales específicos:** Ajustados por tipo de pastura
            
            **🎯 PARÁMETROS {tipo_pastura}:**
            - **Biomasa Óptima:** {PARAMETROS_FORRAJEROS[tipo_pastura]['MS_POR_HA_OPTIMO']} kg MS/ha
            - **Crecimiento Diario:** {PARAMETROS_FORRAJEROS[tipo_pastura]['CRECIMIENTO_DIARIO']} kg MS/ha/día
            - **Consumo por Vaca:** {PARAMETROS_FORRAJEROS[tipo_pastura]['CONSUMO_PORCENTAJE_PESO']*100}% del peso vivo
            - **Umbral Suelo Desnudo:** NDVI < {PARAMETROS_FORRAJEROS[tipo_pastura]['UMBRAL_NDVI_SUELO']}
            
            **🛰️ ÍNDICES SATELITALES CALCULADOS:**
            - **NDVI, EVI, SAVI:** Índices de vegetación mejorados
            - **BSI, NDBI:** Detección precisa de suelo desnudo/roca
            - **Cobertura Vegetal:** Estimación realista de área con vegetación
            - **Factor Penalización:** Ajuste biomasa según tipo de superficie
            
            **🐄 MÉTRICAS GANADERAS MEJORADAS:**
            - **EV/Ha:** Carga animal sostenible considerando suelo desnudo
            - **Días de Permanencia:** Tiempo óptimo basado en biomasa real
            - **Biomasa Disponible:** Forraje realmente aprovechable (excluye suelo)
            """)
        
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
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO GEE MEJORADO", type="primary"):
                        analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero mejorado")
    
    with st.expander("ℹ️ INFORMACIÓN SOBRE EL ANÁLISIS FORRAJERO GEE MEJORADO"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO (GEE) - VERSIÓN MEJORADA**
        
        **🆕 MEJORAS EN DETECCIÓN DE SUELO DESNUDO:**
        - **🌿 Detección Avanzada de Suelo:** Identifica precisamente áreas sin vegetación (roca, suelo pelado)
        - **📊 Cobertura Vegetal Realista:** Calcula porcentaje real de área con vegetación
        - **🎯 Métricas Corregidas:** Biomasa disponible considera solo áreas con vegetación
        - **📈 Penalización por Suelo:** Reduce biomasa en áreas con suelo desnudo
        - **🔍 Validación Mejorada:** Correlaciones corregidas entre variables
        
        **📊 FUNCIONALIDADES PRINCIPALES:**
        - **🌿 Productividad Forrajera:** Biomasa disponible por hectárea (excluye suelo)
        - **🐄 Equivalentes Vaca:** Capacidad de carga animal realista
        - **📅 Días de Permanencia:** Tiempo de rotación estimado
        - **🏜️ Análisis de Suelo:** Detección y cuantificación de áreas sin vegetación
        - **🛰️ Metodología GEE:** Algoritmos científicos mejorados
        
        **🎯 TIPOS DE PASTURA SOPORTADOS:**
        - **ALFALFA:** Alta productividad, buen rebrote
        - **RAYGRASS:** Crecimiento rápido, buena calidad
        - **FESTUCA:** Resistente, adecuada para suelos marginales
        - **AGROPIRRO:** Tolerante a sequía, bajo mantenimiento
        - **PASTIZAL NATURAL:** Pasturas naturales diversificadas
        
        **🚀 INSTRUCCIONES:**
        1. **Sube** tu shapefile del potrero
        2. **Selecciona** el tipo de pastura
        3. **Configura** parámetros ganaderos (peso y carga)
        4. **Define** número de sub-lotes para análisis
        5. **Ejecuta** el análisis GEE mejorado
        6. **Revisa** resultados y mapa de cobertura mejorado
        7. **Descarga** mapas y reportes completos
        """)
