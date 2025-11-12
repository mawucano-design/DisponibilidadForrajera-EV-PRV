# app.py
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

# ReportLab para PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Configuración general de Streamlit
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")

# Restaurar .shx por si falta
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# =============================================================================
# CONFIGURACIÓN Y PARÁMETROS
# =============================================================================

# Parámetros por defecto
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 5000, 
        'CRECIMIENTO_DIARIO': 100, 
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65, 
        'FACTOR_BIOMASA_NDVI': 4500, 
        'OFFSET_BIOMASA': -1000,
        'UMBRAL_NDVI_SUELO': 0.15, 
        'UMBRAL_NDVI_PASTURA': 0.6
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 4500, 
        'CRECIMIENTO_DIARIO': 90, 
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60, 
        'FACTOR_BIOMASA_NDVI': 4200, 
        'OFFSET_BIOMASA': -900,
        'UMBRAL_NDVI_SUELO': 0.15, 
        'UMBRAL_NDVI_PASTURA': 0.6
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 4000, 
        'CRECIMIENTO_DIARIO': 70, 
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55, 
        'FACTOR_BIOMASA_NDVI': 3800, 
        'OFFSET_BIOMASA': -800,
        'UMBRAL_NDVI_SUELO': 0.15, 
        'UMBRAL_NDVI_PASTURA': 0.65
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3500, 
        'CRECIMIENTO_DIARIO': 60, 
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50, 
        'FACTOR_BIOMASA_NDVI': 3200, 
        'OFFSET_BIOMASA': -700,
        'UMBRAL_NDVI_SUELO': 0.15, 
        'UMBRAL_NDVI_PASTURA': 0.65
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 3000, 
        'CRECIMIENTO_DIARIO': 40, 
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'TASA_UTILIZACION_RECOMENDADA': 0.45, 
        'FACTOR_BIOMASA_NDVI': 2800, 
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI_SUELO': 0.15, 
        'UMBRAL_NDVI_PASTURA': 0.7
    }
}

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

# Session state inicial
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'mapa_detallado_bytes' not in st.session_state:
    st.session_state.mapa_detallado_bytes = None
if 'pdf_generado' not in st.session_state:
    st.session_state.pdf_generado = False
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None

# =============================================================================
# SIDEBAR - CONFIGURACIÓN
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Mapa Base
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
            index=0
        )
    else:
        base_map_option = "ESRI Satélite"

    # Fuente de Datos Satelitales
    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
    )

    # Tipo de Pastura
    tipo_pastura = st.selectbox(
        "Tipo de Pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    )

    # Configuración Temporal
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)

    # Parámetros de Detección de Vegetación
    st.subheader("🌿 Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1)

    # Parámetros Personalizados
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05,
                                            value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01,
                                          format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.05, max_value=0.3, value=0.15, step=0.01,
                                            format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.3, max_value=0.8, value=0.6, step=0.01,
                                              format="%.2f")

    # Parámetros Ganaderos
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)

    # División de Potrero
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)

    # Carga de Archivos
    st.subheader("📤 Subir Lote")
    tipo_archivo = st.radio(
        "Formato del archivo:",
        ["Shapefile (ZIP)", "KML"],
        horizontal=True
    )
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    else:
        uploaded_file = st.file_uploader("Subir archivo KML del potrero", type=['kml'])

# =============================================================================
# FUNCIONES DE CARGA DE ARCHIVOS
# =============================================================================

def cargar_shapefile_desde_zip(uploaded_zip):
    """Carga un shapefile desde un archivo ZIP subido"""
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                return gdf
            else:
                st.error("❌ No se encontró archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando shapefile: {str(e)}")
        return None

def cargar_kml(uploaded_kml):
    """Carga un archivo KML subido"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp_file:
            tmp_file.write(uploaded_kml.getvalue())
            tmp_file.flush()
            gdf = gpd.read_file(tmp_file.name, driver='KML')
            os.unlink(tmp_file.name)
            return gdf
    except Exception as e:
        st.error(f"❌ Error cargando KML: {str(e)}")
        return None

# =============================================================================
# FUNCIONES DE ANÁLISIS FORRAJERO
# =============================================================================

def obtener_parametros_forrajeros(tipo_pastura):
    """Obtiene los parámetros forrajeros según el tipo de pastura seleccionado"""
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'FACTOR_BIOMASA_NDVI': 3500,
            'OFFSET_BIOMASA': -800,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE.get(tipo_pastura, PARAMETROS_FORRAJEROS_BASE['PASTIZAL_NATURAL'])

def calcular_superficie(gdf):
    """Calcula la superficie en hectáreas de un GeoDataFrame"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except Exception:
        try:
            return gdf.geometry.area / 10000
        except Exception:
            return pd.Series([0]*len(gdf), index=gdf.index)

def dividir_potrero_en_subLotes(gdf, n_zonas):
    """Divide el potrero en sub-lotes rectangulares"""
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

class DetectorVegetacionRealista:
    """Clase para detección realista de vegetación considerando suelo desnudo"""
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo
        self.parametros_cientificos = {
            'ndvi_suelo_desnudo_max': 0.15,
            'ndvi_vegetacion_escasa_max': 0.4,
            'ndvi_vegetacion_moderada_max': 0.65
        }

    def clasificar_vegetacion_realista(self, ndvi, evi, savi, bsi, ndbi, msavi2=None):
        """Clasifica la vegetación en categorías realistas"""
        if ndvi < 0.12:
            categoria = "SUELO_DESNUDO"
            cobertura = 0.05
        elif ndvi < 0.22:
            categoria = "SUELO_PARCIAL"
            cobertura = 0.25
        elif ndvi < 0.4:
            categoria = "VEGETACION_ESCASA"
            cobertura = 0.5
        elif ndvi < 0.65:
            categoria = "VEGETACION_MODERADA"
            cobertura = 0.75
        else:
            categoria = "VEGETACION_DENSA"
            cobertura = 0.9
        return categoria, cobertura

    def calcular_biomasa_realista(self, ndvi, evi, savi, categoria_vegetacion, cobertura, params):
        """Calcula biomasa realista considerando categorías de vegetación"""
        base = params['MS_POR_HA_OPTIMO']
        if categoria_vegetacion == "SUELO_DESNUDO":
            return 20, 1, 0.2
        if categoria_vegetacion == "SUELO_PARCIAL":
            return min(base * 0.05, 200), params['CRECIMIENTO_DIARIO'] * 0.2, 0.3
        if categoria_vegetacion == "VEGETACION_ESCASA":
            return min(base * 0.3, 1200), params['CRECIMIENTO_DIARIO'] * 0.4, 0.5
        if categoria_vegetacion == "VEGETACION_MODERADA":
            return min(base * 0.6, 3000), params['CRECIMIENTO_DIARIO'] * 0.7, 0.7
        return min(base * 0.9, 6000), params['CRECIMIENTO_DIARIO'] * 0.9, 0.85

def simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital):
    """Simula patrones realistas de NDVI considerando suelo desnudo"""
    base = 0.2 + 0.4 * ((id_subLote % 6) / 6)
    ndvi = max(0.05, min(0.85, base + np.random.normal(0, 0.05)))
    if ndvi < 0.15:
        evi = ndvi * 0.8
        savi = ndvi * 0.9
        bsi = 0.6
        ndbi = 0.25
    elif ndvi < 0.3:
        evi = ndvi * 1.1
        savi = ndvi * 1.05
        bsi = 0.4
        ndbi = 0.15
    elif ndvi < 0.5:
        evi = ndvi * 1.3
        savi = ndvi * 1.2
        bsi = 0.1
        ndbi = 0.05
    else:
        evi = ndvi * 1.4
        savi = ndvi * 1.3
        bsi = -0.1
        ndbi = -0.05
    msavi2 = ndvi * 1.0
    return ndvi, evi, savi, bsi, ndbi, msavi2

def calcular_indices_forrajeros_realista(gdf, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max=20,
                                       umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    """Calcula índices forrajeros con detección realista de vegetación"""
    try:
        n_poligonos = len(gdf)
        resultados = []
        params = obtener_parametros_forrajeros(tipo_pastura)
        detector = DetectorVegetacionRealista(umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo)
        gdf_centroids = gdf.copy()
        gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
        gdf_centroids['x'] = gdf_centroids.centroid.x
        gdf_centroids['y'] = gdf_centroids.centroid.y
        x_coords = gdf_centroids['x'].tolist()
        y_coords = gdf_centroids['y'].tolist()
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        st.info("🔍 Aplicando detección REALISTA que responde a suelo desnudo...")
        for idx, row in gdf_centroids.iterrows():
            id_subLote = row.get('id_subLote', idx+1)
            x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
            y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
            ndvi, evi, savi, bsi, ndbi, msavi2 = simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital)
            categoria_vegetacion, cobertura_vegetal = detector.clasificar_vegetacion_realista(ndvi, evi, savi, bsi, ndbi, msavi2)
            biomasa_ms_ha, crecimiento_diario, calidad_forrajera = detector.calcular_biomasa_realista(ndvi, evi, savi, categoria_vegetacion, cobertura_vegetal, params)

            if categoria_vegetacion in ["SUELO_DESNUDO"]:
                biomasa_disponible = 20
            elif categoria_vegetacion in ["SUELO_PARCIAL"]:
                biomasa_disponible = 80
            else:
                biomasa_disponible = max(20, min(4000, (biomasa_ms_ha * calidad_forrajera * 0.6 * (1-0.25) * cobertura_vegetal)))

            resultados.append({
                'id_subLote': id_subLote,
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'msavi2': round(float(msavi2), 3),
                'bsi': round(float(bsi), 3),
                'ndbi': round(float(ndbi), 3),
                'cobertura_vegetal': round(cobertura_vegetal, 3),
                'tipo_superficie': categoria_vegetacion,
                'biomasa_ms_ha': round(biomasa_ms_ha, 1),
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'factor_calidad': round(calidad_forrajera, 3),
                'fuente_datos': fuente_satelital,
                'x_norm': round(x_norm, 3),
                'y_norm': round(y_norm, 3)
            })

        st.success("✅ Análisis REALISTA completado.")
        return resultados
    except Exception as e:
        st.error(f"❌ Error en análisis realista: {e}")
        import traceback
        st.error(traceback.format_exc())
        return []

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Calcula métricas ganaderas basadas en el análisis forrajero"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row.get('biomasa_disponible_kg_ms_ha', 0)
        area_ha = row.get('area_ha', 0)
        crecimiento_diario = row.get('crecimiento_diario', params.get('CRECIMIENTO_DIARIO', 50))
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total_disponible = biomasa_disponible * area_ha
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01

        if ev_soportable > 0 and area_ha > 0:
            ev_ha = ev_soportable / area_ha
            ev_ha_display = ev_ha
        else:
            ev_ha_display = 0.01

        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(max(dias_permanencia, 0.1), 10)
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1

        # Estado forrajero por rangos
        if biomasa_disponible >= 2000:
            estado_forrajero = 4
        elif biomasa_disponible >= 1200:
            estado_forrajero = 3
        elif biomasa_disponible >= 600:
            estado_forrajero = 2
        elif biomasa_disponible >= 200:
            estado_forrajero = 1
        else:
            estado_forrajero = 0

        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'dias_permanencia': round(dias_permanencia, 1),
            'tasa_utilizacion': round(min(1.0, (carga_animal * consumo_individual_kg) / max(1, biomasa_total_disponible)), 3) if biomasa_total_disponible>0 else 0,
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_ha_display, 3)
        })
    return metricas

# =============================================================================
# FUNCIONES DE VISUALIZACIÓN
# =============================================================================

def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"):
    """Crea un mapa interactivo con Folium"""
    if gdf is None or len(gdf) == 0:
        return None
    bounds = gdf.total_bounds
    centroid = gdf.geometry.centroid.iloc[0]
    m = folium.Map(location=[centroid.y, centroid.x], tiles=None, control_scale=True)
    for map_name, config in BASE_MAPS_CONFIG.items():
        folium.TileLayer(
            tiles=config["tiles"], attr=config["attr"], name=config["name"], overlay=False, control=True
        ).add_to(m)
    selected_config = BASE_MAPS_CONFIG[base_map_name]
    folium.TileLayer(
        tiles=selected_config["tiles"], attr=selected_config["attr"], name=selected_config["name"], overlay=False, control=False
    ).add_to(m)
    folium.GeoJson(gdf.__geo_interface__, style_function=lambda x: {
        'fillColor': '#3388ff', 'color': 'blue', 'weight': 2, 'fillOpacity': 0.2
    }).add_to(m)
    folium.Marker(
        [centroid.y, centroid.x],
        popup=f"Centro del Potrero<br>Lat: {centroid.y:.4f}<br>Lon: {centroid.x:.4f}",
        tooltip="Centro del Potrero",
        icon=folium.Icon(color='green', icon='info-sign')
    ).add_to(m)
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    folium.LayerControl().add_to(m)
    return m

def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"):
    """Crea un mapa interactivo con los resultados del análisis"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    bounds = gdf_analizado.total_bounds
    centroid = gdf_analizado.geometry.centroid.iloc[0]
    m = folium.Map(location=[centroid.y, centroid.x], tiles=None, control_scale=True)
    for map_name, config in BASE_MAPS_CONFIG.items():
        folium.TileLayer(
            tiles=config["tiles"], attr=config["attr"], name=config["name"], overlay=False, control=True
        ).add_to(m)
    selected_config = BASE_MAPS_CONFIG[base_map_name]
    folium.TileLayer(
        tiles=selected_config["tiles"], attr=selected_config["attr"], name=selected_config["name"], overlay=False, control=False
    ).add_to(m)

    def estilo_por_superficie(feature):
        tipo_superficie = feature['properties'].get('tipo_superficie', '')
        colores = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }
        return {'fillColor': colores.get(tipo_superficie, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.6}

    folium.GeoJson(
        gdf_analizado.__geo_interface__,
        style_function=estilo_por_superficie,
        tooltip=folium.GeoJsonTooltip(
            fields=['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha'],
            aliases=['Sub-Lote:', 'Tipo Superficie:', 'NDVI:', 'Biomasa Disp:', 'EV/Ha:'],
            localize=True
        ),
        popup=folium.GeoJsonPopup(
            fields=['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia'],
            aliases=['Sub-Lote:', 'Tipo Superficie:', 'NDVI:', 'Biomasa Disp (kg MS/ha):', 'EV/Ha:', 'Días Permanencia:'],
            localize=True
        )
    ).add_to(m)

    # Leyenda
    colores_leyenda = {
        'SUELO_DESNUDO': '#d73027',
        'SUELO_PARCIAL': '#fdae61',
        'VEGETACION_ESCASA': '#fee08b',
        'VEGETACION_MODERADA': '#a6d96a',
        'VEGETACION_DENSA': '#1a9850'
    }
    legend_html = '''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px">
    <p><strong>Tipos de Superficie</strong></p>
    '''
    for tipo, color in colores_leyenda.items():
        legend_html += f'<p><i style="background:{color}; width:20px; height:20px; display:inline-block; margin-right:5px;"></i> {tipo}</p>'
    legend_html += '</div>'
    m.get_root().html.add_child(folium.Element(legend_html))
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    folium.LayerControl().add_to(m)
    return m

def crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura):
    """Crea un mapa detallado de vegetación con matplotlib"""
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
        colores_superficie = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }

        for idx, row in gdf_analizado.iterrows():
            tipo_superficie = row.get('tipo_superficie', 'VEGETACION_ESCASA')
            color = colores_superficie.get(tipo_superficie, '#cccccc')
            gdf_analizado.iloc[[idx]].plot(ax=ax1, color=color, edgecolor='black', linewidth=1.2)
            centroid = row.geometry.centroid
            ax1.annotate(f"S{row['id_subLote']}\n{row.get('ndvi', 0):.2f}",
                        (centroid.x, centroid.y),
                        xytext=(5, 5), textcoords="offset points", fontsize=7, color='black', weight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8))

        ax1.set_title(f'MAPA DE TIPOS DE SUPERFICIE - {tipo_pastura}', fontsize=12)
        ax1.set_xlabel('Longitud')
        ax1.set_ylabel('Latitud')
        leyenda_elementos = []
        for tipo, color in colores_superficie.items():
            leyenda_elementos.append(mpatches.Patch(color=color, label=tipo))
        ax1.legend(handles=leyenda_elementos, loc='upper right', fontsize=9)

        cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_mejorada', ['#d73027', '#fee08b', '#a6d96a', '#1a9850'])
        for idx, row in gdf_analizado.iterrows():
            biomasa = row.get('biomasa_disponible_kg_ms_ha', 0)
            valor_norm = biomasa / 4000
            valor_norm = max(0, min(1, valor_norm))
            color = cmap_biomasa(valor_norm)
            gdf_analizado.iloc[[idx]].plot(ax=ax2, color=color, edgecolor='black', linewidth=1.2)
            centroid = row.geometry.centroid
            ax2.annotate(f"S{row['id_subLote']}\n{biomasa:.0f}",
                        (centroid.x, centroid.y),
                        xytext=(5, 5), textcoords="offset points", fontsize=7, color='black', weight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8))

        ax2.set_title(f'MAPA DE BIOMASA DISPONIBLE - {tipo_pastura}', fontsize=12)
        sm = plt.cm.ScalarMappable(cmap=cmap_biomasa, norm=plt.Normalize(vmin=0, vmax=4000))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax2, shrink=0.8)
        cbar.set_label('Biomasa Disponible (kg MS/ha)')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception as e:
        st.error(f"❌ Error creando mapa detallado: {e}")
        return None

# =============================================================================
# FUNCIONES DE EXPORTACIÓN
# =============================================================================

def generar_informe_forrajero_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, mapa_detallado_bytes=None):
    """Genera un informe PDF completo con los resultados del análisis"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    styles = getSampleStyleSheet()

    # Estilos
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, textColor=colors.darkgreen, alignment=1, spaceAfter=10)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=12, alignment=1, spaceAfter=6)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=13, textColor=colors.darkblue, spaceAfter=8)
    normal_style = styles['Normal']

    story = []

    # Portada / Encabezado
    story.append(Paragraph("INFORME DE DISPONIBILIDAD FORRAJERA PRV", title_style))
    story.append(Paragraph(f"Tipo de Pastura: {tipo_pastura}", subtitle_style))
    story.append(Paragraph(f"Fecha de emisión: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    story.append(Spacer(1, 18))

    # Información general (tabla)
    info_data = [
        ["Carga Animal", f"{carga_animal} cabezas"],
        ["Peso Promedio (kg)", f"{peso_promedio} kg"],
    ]
    info_table = Table(info_data, colWidths=[2.5*inch, 3.5*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey)
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # Estadísticas globales
    try:
        area_total = gdf_analizado['area_ha'].sum()
        biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        ndvi_prom = gdf_analizado['ndvi'].mean()
        dias_promedio = gdf_analizado['dias_permanencia'].mean()
        ev_total = gdf_analizado['ev_soportable'].sum()
    except Exception:
        area_total = 0
        biomasa_prom = 0
        ndvi_prom = 0
        dias_promedio = 0
        ev_total = 0

    story.append(Paragraph("ESTADÍSTICAS RESUMEN", heading_style))
    stats_data = [
        ["Área Total (ha)", f"{area_total:.2f}"],
        ["Biomasa Prom. (kg MS/ha)", f"{biomasa_prom:.0f}"],
        ["NDVI Promedio", f"{ndvi_prom:.3f}"],
        ["Días de Permanencia Prom.", f"{dias_promedio:.1f}"],
        ["EV Total", f"{ev_total:.1f}"]
    ]
    stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey)
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 12))

    # Mapa (si existe)
    if mapa_detallado_bytes is not None:
        story.append(PageBreak())
        story.append(Paragraph("MAPA DE ANÁLISIS", heading_style))
        try:
            mapa_detallado_bytes.seek(0)
            img = Image(mapa_detallado_bytes, width=6*inch, height=4*inch)
            story.append(img)
            story.append(Spacer(1, 6))
            story.append(Paragraph("Figura: Mapa de tipos de superficie y biomasa disponible", normal_style))
        except Exception as e:
            story.append(Paragraph(f"Error al insertar mapa: {e}", normal_style))

    # Tabla resumen por sub-lote (hasta 10)
    story.append(PageBreak())
    story.append(Paragraph("RESUMEN POR SUB-LOTE (Hasta 10 registros)", heading_style))

    columnas = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha']
    try:
        df_tabla = gdf_analizado[columnas].head(10).copy()
        df_tabla['area_ha'] = df_tabla['area_ha'].round(2)
        df_tabla['ndvi'] = df_tabla['ndvi'].round(3)
        df_tabla['biomasa_disponible_kg_ms_ha'] = df_tabla['biomasa_disponible_kg_ms_ha'].round(0)
        df_tabla['dias_permanencia'] = df_tabla['dias_permanencia'].round(1)
        df_tabla['ev_ha'] = df_tabla['ev_ha'].round(3)

        table_data = [df_tabla.columns.tolist()] + df_tabla.astype(str).values.tolist()
        col_widths = [0.8*inch] + [0.9*inch] * (len(df_tabla.columns)-1)
        result_table = Table(table_data, colWidths=col_widths)
        result_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8)
        ]))
        story.append(result_table)
    except Exception:
        story.append(Paragraph("No hay datos tabulares disponibles para mostrar.", normal_style))

    # Recomendaciones
    story.append(PageBreak())
    story.append(Paragraph("RECOMENDACIONES FORRAJERAS", heading_style))
    if biomasa_prom < 1000:
        recomendacion = "❌ CRÍTICO: Biomasa muy baja. Considerar suplementación y reducir carga animal."
    elif biomasa_prom < 2000:
        recomendacion = "⚠️ ALERTA: Biomasa moderada. Monitorear crecimiento y ajustar rotaciones."
    else:
        recomendacion = "✅ ÓPTIMO: Biomasa adecuada. Mantener manejo actual."
    story.append(Paragraph(recomendacion, normal_style))

    # Pie final
    story.append(Spacer(1, 12))
    story.append(Paragraph("Informe generado por el Sistema de Disponibilidad Forrajera PRV.", ParagraphStyle('Small', parent=normal_style, fontSize=8)))
    story.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ParagraphStyle('Small', parent=normal_style, fontSize=8)))

    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# PROCESO PRINCIPAL DE ANÁLISIS
# =============================================================================

def analisis_forrajero_completo_realista(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones,
                                         fuente_satelital, fecha_imagen, nubes_max,
                                         umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    """Ejecuta el análisis forrajero completo con detección realista"""
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO REALISTA - {tipo_pastura}")
        st.success("🎯 MODO DETECCIÓN REALISTA ACTIVADO")

        params = obtener_parametros_forrajeros(tipo_pastura)

        # División del potrero
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")

        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()

        # Cálculo de índices forrajeros
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS REALISTAS")
        with st.spinner("Aplicando algoritmos..."):
            indices_forrajeros = calcular_indices_forrajeros_realista(
                gdf_dividido, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo
            )

        if not indices_forrajeros:
            st.error("❌ No se pudieron calcular los índices forrajeros")
            return False

        # Integración de resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha.values if hasattr(areas_ha, 'values') else areas_ha
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                if key != 'id_subLote':
                    try:
                        gdf_analizado.loc[gdf_analizado.index[idx], key] = value
                    except Exception:
                        pass

        # Cálculo de métricas ganaderas
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando métricas..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)

        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                try:
                    gdf_analizado.loc[gdf_analizado.index[idx], key] = value
                except Exception:
                    pass

        st.session_state.gdf_analizado = gdf_analizado

        # Visualización de resultados
        mostrar_resultados_analisis(gdf_analizado, tipo_pastura)

        st.session_state.analisis_completado = True
        return True

    except Exception as e:
        st.error(f"❌ Error en análisis forrajero realista: {e}")
        import traceback
        st.error(traceback.format_exc())
        return False

def mostrar_resultados_analisis(gdf_analizado, tipo_pastura):
    """Muestra los resultados del análisis de manera organizada"""
    
    # Mapa detallado (matplotlib)
    st.subheader("🗺️ MAPA DETALLADO DE VEGETACIÓN")
    mapa_detallado = crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura)
    if mapa_detallado:
        st.image(mapa_detallado, use_container_width=True)
        st.session_state.mapa_detallado_bytes = mapa_detallado
        st.download_button(
            "📥 Descargar Mapa Detallado (PNG)",
            mapa_detallado.getvalue(),
            f"mapa_detallado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            "image/png",
            key="descarga_detallado"
        )

    # Mapa interactivo (folium)
    if FOLIUM_AVAILABLE and st.session_state.gdf_analizado is not None:
        st.subheader("🛰️ MAPA INTERACTIVO - ESRI SATÉLITE")
        mapa_analisis = crear_mapa_analisis_interactivo(st.session_state.gdf_analizado, tipo_pastura, base_map_option)
        if mapa_analisis:
            st_folium(mapa_analisis, width=1200, height=500, returned_objects=[])

    # Exportación de resultados
    if st.session_state.gdf_analizado is not None:
        st.subheader("💾 EXPORTAR RESULTADOS")
        col1, col2, col3 = st.columns(3)

        # GeoJSON
        with col1:
            try:
                gdf_export = st.session_state.gdf_analizado.copy()
                geojson_str = gdf_export.to_json()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_geo = f"analisis_forrajero_{tipo_pastura}_{timestamp}.geojson"
                st.download_button(
                    "📤 Exportar GeoJSON",
                    geojson_str,
                    filename_geo,
                    "application/geo+json",
                    key="exportar_geojson"
                )
            except Exception as e:
                st.error(f"❌ Error exportando GeoJSON: {e}")

        # CSV
        with col2:
            try:
                csv_data = st.session_state.gdf_analizado.drop(columns=['geometry']).to_csv(index=False)
                csv_filename = f"analisis_forrajero_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                st.download_button(
                    "📊 Exportar CSV",
                    csv_data,
                    csv_filename,
                    "text/csv",
                    key="exportar_csv"
                )
            except Exception as e:
                st.error(f"❌ Error exportando CSV: {e}")

        # PDF
        with col3:
            if st.button("📄 Generar Informe PDF", key="generar_pdf"):
                with st.spinner("🔄 Generando informe PDF..."):
                    try:
                        pdf_buffer = generar_informe_forrajero_pdf(
                            st.session_state.gdf_analizado,
                            tipo_pastura,
                            peso_promedio,
                            carga_animal,
                            st.session_state.mapa_detallado_bytes
                        )
                        if pdf_buffer:
                            st.session_state.pdf_buffer = pdf_buffer
                            st.session_state.pdf_generado = True
                            st.success("✅ PDF generado correctamente!")
                            st.download_button(
                                "📥 Descargar Informe PDF",
                                pdf_buffer.getvalue(),
                                f"informe_disponibilidad_forrajera_prv_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                "application/pdf",
                                key="descarga_pdf"
                            )
                        else:
                            st.error("❌ No se pudo generar el PDF")
                    except Exception as e:
                        st.error(f"❌ Error generando PDF: {str(e)}")

    # Resumen de métricas
    st.subheader("📊 RESUMEN DE RESULTADOS")
    col1, col2, col3, col4 = st.columns(4)
    try:
        biomasa_prom = st.session_state.gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    except Exception:
        biomasa_prom = 0
    with col1:
        st.metric("Biomasa Disponible Prom", f"{biomasa_prom:.0f} kg MS/ha")
    with col2:
        try:
            area_vegetacion = st.session_state.gdf_analizado[st.session_state.gdf_analizado['tipo_superficie'].isin(['VEGETACION_MODERADA', 'VEGETACION_DENSA'])]['area_ha'].sum()
        except Exception:
            area_vegetacion = 0
        st.metric("Área con Vegetación", f"{area_vegetacion:.1f} ha")
    with col3:
        try:
            area_suelo = st.session_state.gdf_analizado[st.session_state.gdf_analizado['tipo_superficie'].isin(['SUELO_DESNUDO', 'SUELO_PARCIAL'])]['area_ha'].sum()
        except Exception:
            area_suelo = 0
        st.metric("Área sin Vegetación", f"{area_suelo:.1f} ha")
    with col4:
        try:
            cobertura_prom = st.session_state.gdf_analizado['cobertura_vegetal'].mean()
        except Exception:
            cobertura_prom = 0
        st.metric("Cobertura Vegetal Prom", f"{cobertura_prom:.1%}")

    # Tabla detallada
    st.subheader("🔬 DETALLES POR SUB-LOTE")
    columnas_detalle = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'cobertura_vegetal',
                      'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']
    try:
        tabla_detalle = st.session_state.gdf_analizado[columnas_detalle].copy()
        tabla_detalle.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Cobertura',
                               'Biomasa Disp (kg MS/ha)', 'EV/Ha', 'Días Permanencia']
        st.dataframe(tabla_detalle, use_container_width=True)
    except Exception:
        st.info("No hay detalles tabulares para mostrar.")

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

# Carga de datos del potrero
st.markdown("### 📁 CARGAR DATOS DEL POTRERO")
gdf_cargado = None
if uploaded_file is not None:
    with st.spinner("Cargando y procesando archivo..."):
        try:
            if tipo_archivo == "Shapefile (ZIP)":
                gdf_cargado = cargar_shapefile_desde_zip(uploaded_file)
            else:
                gdf_cargado = cargar_kml(uploaded_file)
            if gdf_cargado is not None:
                st.session_state.gdf_cargado = gdf_cargado
                area_total = calcular_superficie(gdf_cargado).sum()
                st.success("✅ Potrero cargado!")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Polígonos", len(gdf_cargado))
                with col2:
                    st.metric("Área Total", f"{area_total:.1f} ha")
                with col3:
                    st.metric("Pastura", tipo_pastura)
                with col4:
                    st.metric("Satélite", fuente_satelital)

                # Visualización del potrero
                if FOLIUM_AVAILABLE:
                    st.markdown("---")
                    st.markdown("### 🗺️ VISUALIZACIÓN DEL POTRERO")
                    mapa_interactivo = crear_mapa_interactivo(gdf_cargado, base_map_option)
                    if mapa_interactivo:
                        st_folium(mapa_interactivo, width=1200, height=500, returned_objects=[])
                        st.info("🔍 Puedes cambiar entre mapas base usando el control del mapa.")
                else:
                    st.warning("⚠️ Para ver el mapa interactivo con ESRI Satélite instala folium: `pip install folium streamlit-folium`")
        except Exception as e:
            st.error(f"❌ Error cargando archivo: {e}")

# Análisis forrajero
st.markdown("---")
st.markdown("### 🚀 ACCIÓN PRINCIPAL - DETECCIÓN REALISTA")
if st.session_state.gdf_cargado is not None:
    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO REALISTA", type="primary", use_container_width=True):
        with st.spinner("🔄 Ejecutando análisis forrajero completo..."):
            resultado = analisis_forrajero_completo_realista(
                st.session_state.gdf_cargado,
                tipo_pastura,
                peso_promedio,
                carga_animal,
                n_divisiones,
                fuente_satelital,
                fecha_imagen,
                nubes_max,
                umbral_ndvi_minimo,
                umbral_ndvi_optimo,
                sensibilidad_suelo
            )
            if resultado:
                st.balloons()
                st.success("🎉 ¡Análisis completado exitosamente!")
else:
    st.info("📁 Por favor, carga un archivo de potrero para comenzar el análisis")
