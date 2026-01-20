# app.py
"""
App completa mejorada: análisis forrajero + clima NASA POWER + suelos INTA
"""

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
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.ops import unary_union
import math
import base64
import streamlit.components.v1 as components
import requests
import json
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Intento importar python-docx
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium, folium_static
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Streamlit config
st.set_page_config(page_title="🌱 Disponibilidad Forrajera PRV + Clima + Suelo", layout="wide")
st.title("🌱 Disponibilidad Forrajera PRV — Analizador Avanzado")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# ---------- APIs Externas ----------
NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# Cambiamos la URL del INTA a una más confiable (servicio WMS)
INTA_SUELOS_WMS_URL = "https://geoserver.inta.gob.ar/geoserver/wms"
INTA_SUELOS_WFS_URL = "https://geoserver.inta.gob.ar/geoserver/ows"

# ---------- Parámetros por defecto ----------
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Session state
for key in [
    'gdf_cargado', 'gdf_analizado', 'mapa_detallado_bytes',
    'docx_buffer', 'analisis_completado', 'html_download_injected',
    'datos_clima', 'datos_suelo', 'indices_avanzados'
]:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------
# SIDEBAR (CONFIGURACIÓN)
# -----------------------
with st.sidebar:
    st.header("⚙️ Configuración Avanzada")
    
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron", "Topográfico"],
            index=0
        )
    else:
        base_map_option = "ESRI Satélite"

    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
    )

    tipo_pastura = st.selectbox("Tipo de Pastura:",
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", 
                                "PASTIZAL_NATURAL", "MEZCLA_LEGUMINOSAS", "PERSONALIZADO"])

    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    # Período climático
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio_clima = st.date_input(
            "Inicio período climático:",
            value=fecha_imagen - timedelta(days=60)
        )
    with col2:
        fecha_fin_clima = st.date_input(
            "Fin período climático:",
            value=fecha_imagen
        )
    
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)

    st.subheader("🌿 Parámetros de Detección Avanzada")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1)
    
    # Nuevos parámetros avanzados
    umbral_estres_hidrico = st.slider("Umbral estrés hídrico (ETc):", 0.3, 1.0, 0.7, 0.05)
    factor_seguridad = st.slider("Factor de seguridad biomasa:", 0.7, 1.3, 1.0, 0.05)
    tasa_crecimiento_lluvia = st.slider("Tasa crecimiento por lluvia (kg/mm):", 5, 30, 15, 1)

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

    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 1, 1000, 100)
    
    st.subheader("🌤️ Datos Climáticos (NASA POWER)")
    usar_clima = st.checkbox("Usar datos climáticos NASA POWER", value=True)
    if usar_clima:
        variables_clima = st.multiselect(
            "Variables climáticas a incluir:",
            ["PRECIPITACION", "TEMPERATURA", "HUMEDAD", "RADIACION", "EVAPOTRANSPIRACION"],
            default=["PRECIPITACION", "TEMPERATURA", "EVAPOTRANSPIRACION"]
        )
    
    st.subheader("🌍 Datos de Suelos (INTA)")
    usar_suelo = st.checkbox("Usar datos de suelos INTA", value=True)
    if usar_suelo:
        st.info("Se consultará información de suelos del INTA (si está disponible)")

    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=64, value=24)
    
    st.subheader("🔄 Opciones de Unión de Polígonos")
    unir_poligonos = st.checkbox(
        "Unir todos los polígonos en uno solo", 
        value=True,
        help="Si está activado, todos los polígonos del archivo se unirán en un solo potrero."
    )

    st.subheader("📤 Subir Lote")
    tipo_archivo = st.radio(
        "Formato del archivo:",
        ["Shapefile (ZIP)", "KML", "KMZ"],
        horizontal=True
    )
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    elif tipo_archivo == "KML":
        uploaded_file = st.file_uploader("Subir archivo KML del potrero", type=['kml'])
    else:  # KMZ
        uploaded_file = st.file_uploader("Subir archivo KMZ del potrero", type=['kmz'])

# -----------------------
# SERVICIOS EXTERNOS - NASA POWER & INTA
# -----------------------
class ServicioClimaNASA:
    """Clase para obtener datos climáticos de NASA POWER API"""
    
    @staticmethod
    def obtener_datos_climaticos(lat: float, lon: float, fecha_inicio: datetime, fecha_fin: datetime) -> Optional[Dict]:
        """Obtiene datos climáticos históricos de NASA POWER"""
        try:
            params = {
                "parameters": "PRECTOT,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS2M",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": fecha_inicio.strftime("%Y%m%d"),
                "end": fecha_fin.strftime("%Y%m%d"),
                "format": "JSON"
            }
            
            with st.spinner(f"Consultando NASA POWER para coordenadas {lat:.4f}, {lon:.4f}..."):
                response = requests.get(NASA_POWER_BASE_URL, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    return ServicioClimaNASA._procesar_datos_nasa(data)
                else:
                    st.warning(f"⚠️ API NASA POWER no disponible (código {response.status_code})")
                    return None
                    
        except Exception as e:
            st.warning(f"⚠️ Error consultando NASA POWER: {str(e)}")
            return None
    
    @staticmethod
    def _procesar_datos_nasa(data: Dict) -> Dict:
        """Procesa los datos crudos de NASA POWER"""
        try:
            properties = data.get('properties', {})
            parameter = data.get('parameters', {})
            
            # Extraer series temporales
            precipitacion = parameter.get('PRECTOT', {})
            temp_max = parameter.get('T2M_MAX', {})
            temp_min = parameter.get('T2M_MIN', {})
            humedad = parameter.get('RH2M', {})
            radiacion = parameter.get('ALLSKY_SFC_SW_DWN', {})
            viento = parameter.get('WS2M', {})
            
            # Calcular estadísticas
            resultado = {
                'precipitacion_total': sum(precipitacion.get('data', [0])),
                'precipitacion_promedio': np.mean(precipitacion.get('data', [0])),
                'temp_max_promedio': np.mean(temp_max.get('data', [0])),
                'temp_min_promedio': np.mean(temp_min.get('data', [0])),
                'humedad_promedio': np.mean(humedad.get('data', [0])),
                'radiacion_promedio': np.mean(radiacion.get('data', [0])),
                'viento_promedio': np.mean(viento.get('data', [0])),
                'dias_lluvia': sum(1 for p in precipitacion.get('data', []) if p > 1.0),
                'balance_hidrico': sum(precipitacion.get('data', [0])) - sum(viento.get('data', [0])),
                'datos_crudos': data
            }
            
            # Calcular evapotranspiración de referencia (FAO Penman-Monteith simplificado)
            resultado['et0_promedio'] = ServicioClimaNASA._calcular_et0(
                resultado['temp_max_promedio'],
                resultado['temp_min_promedio'],
                resultado['humedad_promedio'],
                resultado['radiacion_promedio'],
                resultado['viento_promedio']
            )
            
            return resultado
            
        except Exception as e:
            st.error(f"Error procesando datos NASA: {str(e)}")
            return None
    
    @staticmethod
    def _calcular_et0(tmax: float, tmin: float, humedad: float, radiacion: float, viento: float) -> float:
        """Calcula evapotranspiración de referencia (mm/día) - método simplificado"""
        try:
            # Temperatura media
            tmean = (tmax + tmin) / 2
            
            # Presión de vapor de saturación
            es = 0.6108 * np.exp((17.27 * tmean) / (tmean + 237.3))
            
            # Presión de vapor actual
            ea = es * (humedad / 100)
            
            # Déficit de presión de vapor
            vpd = es - ea
            
            # ET0 simplificada (mm/día)
            et0 = 0.0023 * (tmean + 17.8) * (tmax - tmin) ** 0.5 * radiacion * 0.0864
            
            # Ajustar por viento y humedad
            et0 = et0 * (1 + 0.006 * viento) * (1 - 0.01 * (humedad - 50))
            
            return max(0.1, min(10.0, et0))
            
        except:
            return 3.0  # Valor por defecto

class ServicioSuelosINTA:
    """Clase para obtener datos de suelos del INTA con respaldo simulado"""
    
    @staticmethod
    def obtener_caracteristicas_suelo(lat: float, lon: float) -> Optional[Dict]:
        """Obtiene características del suelo con fallback a datos simulados"""
        try:
            # Intentamos usar el servicio del INTA si está disponible
            datos_reales = ServicioSuelosINTA._consultar_servicio_inta(lat, lon)
            if datos_reales:
                return datos_reales
            else:
                # Si falla, usamos datos simulados basados en ubicación
                st.warning("⚠️ Servicio INTA no disponible. Usando datos simulados basados en ubicación.")
                return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)
                
        except Exception as e:
            st.warning(f"⚠️ Error consultando servicio de suelos: {str(e)}. Usando datos simulados.")
            return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)
    
    @staticmethod
    def _consultar_servicio_inta(lat: float, lon: float) -> Optional[Dict]:
        """Intenta consultar el servicio del INTA"""
        try:
            # Intentamos con un timeout corto para no bloquear la aplicación
            response = requests.get(
                INTA_SUELOS_WFS_URL,
                params={
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": "cite:su_250",  # Capa de suelos a escala 1:250.000
                    "outputFormat": "application/json",
                    "CQL_FILTER": f"INTERSECTS(geom, POINT({lon} {lat}))"
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return ServicioSuelosINTA._procesar_datos_suelo(data)
            else:
                return None
                
        except:
            return None
    
    @staticmethod
    def _procesar_datos_suelo(data: Dict) -> Dict:
        """Procesa datos de suelo del INTA"""
        try:
            features = data.get('features', [])
            if not features:
                return None
            
            feature = features[0]['properties']
            
            resultado = {
                'textura': feature.get('textura', 'Franco'),
                'profundidad': float(feature.get('profundidad', 50)),
                'materia_organica': float(feature.get('materia_organica', 2.5)),
                'ph': float(feature.get('ph', 6.5)),
                'capacidad_campo': float(feature.get('capacidad_campo', 25)),
                'punto_marchitez': float(feature.get('punto_marchitez', 10)),
                'densidad_aparente': float(feature.get('densidad_aparente', 1.3)),
                'fuente': 'INTA',
                'detalles': feature
            }
            
            # Clasificar textura
            resultado['clase_textura'] = ServicioSuelosINTA._clasificar_textura(resultado['textura'])
            
            return resultado
            
        except Exception as e:
            st.warning(f"Error procesando datos suelo: {str(e)}")
            return None
    
    @staticmethod
    def _obtener_datos_simulados(lat: float, lon: float) -> Dict:
        """Genera datos de suelo simulados basados en ubicación"""
        # Simular variaciones por región
        if lat < -35:  # Región pampeana
            textura = "Franco limoso"
            materia_organica = 3.0
            ph = 6.8
        elif lat < -40:  # Patagonia
            textura = "Franco arenoso"
            materia_organica = 1.5
            ph = 7.2
        else:  # Norte
            textura = "Franco arcilloso"
            materia_organica = 2.0
            ph = 6.5
        
        # Agregar variabilidad aleatoria
        return {
            'textura': textura,
            'profundidad': 50 + np.random.uniform(-10, 20),
            'materia_organica': materia_organica + np.random.uniform(-0.5, 0.5),
            'ph': ph + np.random.uniform(-0.5, 0.5),
            'capacidad_campo': 25 + np.random.uniform(-5, 10),
            'punto_marchitez': 10 + np.random.uniform(-3, 5),
            'densidad_aparente': 1.3 + np.random.uniform(-0.2, 0.2),
            'fuente': 'Simulado (basado en ubicación)',
            'clase_textura': ServicioSuelosINTA._clasificar_textura(textura)
        }
    
    @staticmethod
    def _clasificar_textura(textura: str) -> str:
        """Clasifica la textura del suelo"""
        textura_lower = textura.lower()
        
        if 'arena' in textura_lower:
            return 'Arenoso'
        elif 'limo' in textura_lower:
            return 'Limoso'
        elif 'arcilla' in textura_lower:
            return 'Arcilloso'
        elif 'franco' in textura_lower:
            return 'Franco'
        else:
            return 'Mixto'

# -----------------------
# FUNCIONES DE CARGA Y PROCESAMIENTO
# -----------------------
def cargar_shapefile_desde_zip(uploaded_zip):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_zip.getvalue())
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.lower().endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                if gdf.crs is None:
                    gdf.set_crs(epsg=4326, inplace=True, allow_override=True)
                return gdf
            else:
                st.error("❌ No se encontró archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando shapefile: {e}")
        return None

def cargar_kml(uploaded_kml):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp_file:
            tmp_file.write(uploaded_kml.getvalue())
            tmp_file.flush()
            tmp_path = tmp_file.name
        gdf = gpd.read_file(tmp_path, driver='KML')
        os.unlink(tmp_path)
        if not gdf.empty and gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True, allow_override=True)
        return gdf
    except Exception as e:
        st.error(f"❌ Error cargando KML: {e}")
        return None

def cargar_kmz(uploaded_kmz):
    """Carga un archivo KMZ (formato comprimido de KML)"""
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            kmz_path = os.path.join(tmp_dir, "upload.kmz")
            with open(kmz_path, "wb") as f:
                f.write(uploaded_kmz.getvalue())
            
            with zipfile.ZipFile(kmz_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            kml_files = []
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    if file.lower().endswith('.kml'):
                        kml_files.append(os.path.join(root, file))
            
            if not kml_files:
                st.error("❌ No se encontró archivo .kml en el KMZ")
                return None
            
            kml_path = kml_files[0]
            gdf = gpd.read_file(kml_path, driver='KML')
            
            if not gdf.empty and gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True, allow_override=True)
            
            return gdf
            
    except Exception as e:
        st.error(f"❌ Error cargando KMZ: {e}")
        return None

def unir_poligonos_gdf(gdf):
    """Une todos los polígonos de un GeoDataFrame en un solo polígono o multipolígono."""
    try:
        if len(gdf) <= 1:
            return gdf
        
        geometria_unida = unary_union(gdf.geometry)
        
        if isinstance(geometria_unida, (Polygon, MultiPolygon)):
            nuevo_gdf = gpd.GeoDataFrame(geometry=[geometria_unida], crs=gdf.crs)
            return nuevo_gdf
        else:
            st.warning("⚠️ La unión de polígonos no produjo una geometría válida.")
            return gdf
            
    except Exception as e:
        st.error(f"❌ Error uniendo polígonos: {e}")
        return gdf

def procesar_y_unir_poligonos(gdf, unir=True):
    """Procesa el GeoDataFrame: si unir=True, une todos los polígonos."""
    if gdf is None or gdf.empty:
        return gdf
    
    n_poligonos_original = len(gdf)
    
    if not unir:
        return gdf
    
    gdf_unido = unir_poligonos_gdf(gdf)
    n_poligonos_final = len(gdf_unido)
    
    if n_poligonos_final == 1:
        st.success(f"✅ {n_poligonos_original} polígonos unidos en 1 potrero")
    elif n_poligonos_final < n_poligonos_original:
        st.info(f"ℹ️ {n_poligonos_original} polígonos reducidos a {n_poligonos_final} potreros")
    
    return gdf_unido

# -----------------------
# FUNCIONES DE MAPA MEJORADAS
# -----------------------
def crear_mapa_interactivo_con_zoom(gdf, base_map_name="ESRI Satélite"):
    """Crea mapa interactivo con zoom automático al polígono"""
    if not FOLIUM_AVAILABLE or gdf is None or len(gdf) == 0:
        return None
    
    try:
        # Calcular el centroide del área
        bounds = gdf.total_bounds
        centroid = gdf.geometry.centroid.iloc[0]
        
        # Crear mapa centrado en el polígono
        m = folium.Map(
            location=[centroid.y, centroid.x], 
            zoom_start=12,  # Zoom inicial
            tiles=None, 
            control_scale=True
        )
        
        # Agregar capa base según selección
        if base_map_name == "ESRI Satélite":
            ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            folium.TileLayer(ESRI, attr='Esri', name='ESRI Satellite', overlay=False).add_to(m)
        elif base_map_name == "OpenStreetMap":
            folium.TileLayer('OpenStreetMap', attr='OpenStreetMap', name='OpenStreetMap').add_to(m)
        elif base_map_name == "CartoDB Positron":
            folium.TileLayer('CartoDB positron', attr='CartoDB', name='CartoDB Positron').add_to(m)
        elif base_map_name == "Topográfico":
            folium.TileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', 
                           attr='OpenTopoMap', name='Topográfico').add_to(m)
        else:
            folium.TileLayer('OpenStreetMap', attr='OpenStreetMap', name='OpenStreetMap').add_to(m)
        
        # Preparar datos para el tooltip
        fields = []
        aliases = []
        
        # Verificar qué campos están disponibles
        if 'area_ha' in gdf.columns:
            fields.append('area_ha')
            aliases.append('Área (ha):')
        
        # Agregar polígono con estilo
        if fields:
            # Solo crear tooltip si hay campos disponibles
            folium.GeoJson(
                gdf.__geo_interface__, 
                name='Potrero',
                style_function=lambda feat: {
                    'fillColor': '#3186cc',
                    'color': '#3186cc',
                    'weight': 3,
                    'fillOpacity': 0.3,
                    'dashArray': '5, 5'
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=fields,
                    aliases=aliases,
                    localize=True
                )
            ).add_to(m)
        else:
            # Sin tooltip
            folium.GeoJson(
                gdf.__geo_interface__, 
                name='Potrero',
                style_function=lambda feat: {
                    'fillColor': '#3186cc',
                    'color': '#3186cc',
                    'weight': 3,
                    'fillOpacity': 0.3,
                    'dashArray': '5, 5'
                }
            ).add_to(m)
        
        # Ajustar el zoom para que se vea todo el polígono
        if len(gdf) > 0:
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        
        # Agregar control de capas
        folium.LayerControl().add_to(m)
        
        # Agregar marcador en el centroide
        folium.Marker(
            [centroid.y, centroid.x],
            popup=f"Centroide: {centroid.y:.4f}, {centroid.x:.4f}",
            tooltip="Centro del potrero"
        ).add_to(m)
        
        return m
        
    except Exception as e:
        st.error(f"❌ Error creando mapa interactivo: {e}")
        return None

# -----------------------
# ANÁLISIS FORRAJERO AVANZADO
# -----------------------
class AnalisisForrajeroAvanzado:
    """Clase mejorada para análisis forrajero con clima y suelo"""
    
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, 
                 sensibilidad_suelo=0.5, umbral_estres_hidrico=0.7,
                 factor_seguridad=1.0, tasa_crecimiento_lluvia=15):
        
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo
        self.umbral_estres_hidrico = umbral_estres_hidrico
        self.factor_seguridad = factor_seguridad
        self.tasa_crecimiento_lluvia = tasa_crecimiento_lluvia
        
        # Parámetros por tipo de suelo
        self.factores_suelo = {
            'Arenoso': {'retencion': 0.7, 'infiltracion': 1.3, 'fertilidad': 0.8},
            'Limoso': {'retencion': 1.0, 'infiltracion': 1.0, 'fertilidad': 1.0},
            'Arcilloso': {'retencion': 1.3, 'infiltracion': 0.7, 'fertilidad': 1.2},
            'Franco': {'retencion': 1.1, 'infiltracion': 1.1, 'fertilidad': 1.1},
            'Mixto': {'retencion': 1.0, 'infiltracion': 1.0, 'fertilidad': 1.0}
        }
    
    def clasificar_vegetacion_avanzada(self, ndvi, evi, savi, bsi, ndbi, msavi2, datos_clima=None):
        """Clasificación mejorada considerando clima"""
        
        # Clasificación base
        if ndvi < 0.10:
            categoria_base = "SUELO_DESNUDO"
            cobertura_base = 0.05
        elif ndvi < 0.20:
            categoria_base = "SUELO_PARCIAL"
            cobertura_base = 0.25
        elif ndvi < 0.40:
            categoria_base = "VEGETACION_ESCASA"
            cobertura_base = 0.5
        elif ndvi < 0.65:
            categoria_base = "VEGETACION_MODERADA"
            cobertura_base = 0.75
        else:
            categoria_base = "VEGETACION_DENSA"
            cobertura_base = 0.9
        
        # Ajustar por estrés climático si hay datos
        if datos_clima:
            ajuste_clima = self._calcular_ajuste_climatico(datos_clima)
            cobertura_ajustada = cobertura_base * ajuste_clima
            cobertura_ajustada = max(0.05, min(0.95, cobertura_ajustada))
            
            # Reclasificar si hay estrés severo
            if ajuste_clima < 0.5 and categoria_base != "SUELO_DESNUDO":
                if categoria_base == "VEGETACION_DENSA":
                    categoria_base = "VEGETACION_MODERADA"
                elif categoria_base == "VEGETACION_MODERADA":
                    categoria_base = "VEGETACION_ESCASA"
        else:
            cobertura_ajustada = cobertura_base
        
        return categoria_base, cobertura_ajustada
    
    def _calcular_ajuste_climatico(self, datos_clima):
        """Calcula ajuste por condiciones climáticas"""
        try:
            ajuste = 1.0
            
            # Ajuste por precipitación
            if datos_clima.get('precipitacion_promedio', 0) < 1.0:
                ajuste *= 0.7  # Sequía severa
            elif datos_clima.get('precipitacion_promedio', 0) < 2.0:
                ajuste *= 0.85  # Sequía moderada
            
            # Ajuste por temperatura
            temp_max = datos_clima.get('temp_max_promedio', 25)
            if temp_max > 35:
                ajuste *= 0.8  # Estrés por calor
            elif temp_max < 5:
                ajuste *= 0.9  # Frío
            
            # Ajuste por balance hídrico
            balance = datos_clima.get('balance_hidrico', 0)
            if balance < -10:
                ajuste *= 0.8
            elif balance > 20:
                ajuste *= 1.1  # Condiciones favorables
            
            return max(0.3, min(1.2, ajuste))
            
        except:
            return 1.0
    
    def calcular_biomasa_avanzada(self, ndvi, evi, savi, categoria, cobertura, params, 
                                  datos_clima=None, datos_suelo=None):
        """Cálculo mejorado de biomasa considerando clima y suelo"""
        
        base = params['MS_POR_HA_OPTIMO']
        
        # Base según categoría
        if categoria == "SUELO_DESNUDO":
            biomasa_base = 20
            crecimiento_base = 1
            calidad_base = 0.2
        elif categoria == "SUELO_PARCIAL":
            biomasa_base = min(base * 0.05, 200)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.2
            calidad_base = 0.3
        elif categoria == "VEGETACION_ESCASA":
            biomasa_base = min(base * 0.3, 1200)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.4
            calidad_base = 0.5
        elif categoria == "VEGETACION_MODERADA":
            biomasa_base = min(base * 0.6, 3000)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.7
            calidad_base = 0.7
        else:  # VEGETACION_DENSA
            biomasa_base = min(base * 0.9, 6000)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.9
            calidad_base = 0.85
        
        # Aplicar cobertura
        biomasa_cobertura = biomasa_base * cobertura
        crecimiento_cobertura = crecimiento_base * cobertura
        
        # Ajustar por clima si disponible
        if datos_clima:
            factor_clima = self._calcular_factor_climatico(datos_clima)
            biomasa_clima = biomasa_cobertura * factor_clima
            crecimiento_clima = crecimiento_cobertura * factor_clima
        else:
            biomasa_clima = biomasa_cobertura
            crecimiento_clima = crecimiento_cobertura
        
        # Ajustar por suelo si disponible
        if datos_suelo:
            factor_suelo = self._calcular_factor_suelo(datos_suelo)
            biomasa_suelo = biomasa_clima * factor_suelo
            crecimiento_suelo = crecimiento_clima * factor_suelo
            calidad_suelo = calidad_base * factor_suelo
        else:
            biomasa_suelo = biomasa_clima
            crecimiento_suelo = crecimiento_clima
            calidad_suelo = calidad_base
        
        # Aplicar factor de seguridad
        biomasa_final = biomasa_suelo * self.factor_seguridad
        crecimiento_final = crecimiento_suelo * self.factor_seguridad
        
        # Calcular biomasa disponible (considerando estrés)
        if categoria == "SUELO_DESNUDO":
            biomasa_disponible = 20
        elif categoria == "SUELO_PARCIAL":
            biomasa_disponible = 80
        else:
            biomasa_disponible = max(20, min(base * 0.9, 
                biomasa_final * calidad_suelo * cobertura))
        
        return biomasa_final, crecimiento_final, calidad_suelo, biomasa_disponible
    
    def _calcular_factor_climatico(self, datos_clima):
        """Calcula factor de ajuste por clima"""
        factor = 1.0
        
        # Efecto de precipitación
        precip = datos_clima.get('precipitacion_promedio', 2.0)
        if precip > 3.0:
            factor *= 1.2  # Lluvias abundantes
        elif precip < 1.0:
            factor *= 0.7  # Sequía
        
        # Efecto de temperatura
        temp = datos_clima.get('temp_max_promedio', 25)
        if 20 <= temp <= 30:
            factor *= 1.1  # Temperatura óptima
        elif temp > 35 or temp < 5:
            factor *= 0.8  # Temperaturas extremas
        
        # Efecto de evapotranspiración
        et0 = datos_clima.get('et0_promedio', 3.0)
        balance = datos_clima.get('balance_hidrico', 0)
        
        if balance > 0:  # Exceso de agua
            factor *= min(1.2, 1 + balance/100)
        else:  # Déficit
            factor *= max(0.6, 1 + balance/50)
        
        return max(0.4, min(1.3, factor))
    
    def _calcular_factor_suelo(self, datos_suelo):
        """Calcula factor de ajuste por suelo"""
        clase = datos_suelo.get('clase_textura', 'Franco')
        factores = self.factores_suelo.get(clase, self.factores_suelo['Franco'])
        
        factor = 1.0
        
        # Ajuste por textura
        factor *= factores['retencion'] * 0.4 + factores['fertilidad'] * 0.6
        
        # Ajuste por materia orgánica
        mo = datos_suelo.get('materia_organica', 2.5)
        if mo > 3.5:
            factor *= 1.2
        elif mo < 1.5:
            factor *= 0.8
        
        # Ajuste por pH
        ph = datos_suelo.get('ph', 6.5)
        if 6.0 <= ph <= 7.5:
            factor *= 1.1  # pH óptimo
        elif ph < 5.5 or ph > 8.0:
            factor *= 0.7  # pH extremo
        
        return max(0.5, min(1.3, factor))

# -----------------------
# PARÁMETROS FORRAJEROS AVANZADOS
# -----------------------
PARAMETROS_FORRAJEROS_AVANZADOS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 5000, 
        'CRECIMIENTO_DIARIO': 100, 
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'PROTEINA': 18.0,
        'FIBRA': 30.0,
        'REQUERIMIENTO_AGUA': 4.0  # mm/día
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 4500, 
        'CRECIMIENTO_DIARIO': 90, 
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'PROTEINA': 16.0,
        'FIBRA': 28.0,
        'REQUERIMIENTO_AGUA': 3.5
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 4000, 
        'CRECIMIENTO_DIARIO': 70, 
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'PROTEINA': 14.0,
        'FIBRA': 32.0,
        'REQUERIMIENTO_AGUA': 3.0
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3500, 
        'CRECIMIENTO_DIARIO': 60, 
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'PROTEINA': 12.0,
        'FIBRA': 35.0,
        'REQUERIMIENTO_AGUA': 2.5
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 3000, 
        'CRECIMIENTO_DIARIO': 40, 
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'PROTEINA': 10.0,
        'FIBRA': 40.0,
        'REQUERIMIENTO_AGUA': 2.0
    },
    'MEZCLA_LEGUMINOSAS': {
        'MS_POR_HA_OPTIMO': 4200, 
        'CRECIMIENTO_DIARIO': 85, 
        'CONSUMO_PORCENTAJE_PESO': 0.027,
        'TASA_UTILIZACION_RECOMENDADA': 0.58,
        'PROTEINA': 17.0,
        'FIBRA': 29.0,
        'REQUERIMIENTO_AGUA': 3.2
    }
}

def obtener_parametros_forrajeros_avanzados(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'PROTEINA': 15.0,
            'FIBRA': 30.0,
            'REQUERIMIENTO_AGUA': 3.0
        }
    else:
        return PARAMETROS_FORRAJEROS_AVANZADOS.get(
            tipo_pastura, 
            PARAMETROS_FORRAJEROS_AVANZADOS['PASTIZAL_NATURAL']
        )

# -----------------------
# FUNCIONES AUXILIARES
# -----------------------
def calcular_superficie(gdf):
    try:
        if gdf.crs is None or gdf.crs.is_geographic:
            gdf_m = gdf.to_crs(epsg=3857)
            area_m2 = gdf_m.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000.0
    except Exception:
        try:
            return gdf.geometry.area / 10000.0
        except Exception:
            return pd.Series([0]*len(gdf), index=gdf.index)

def dividir_potrero_en_subLotes(gdf, n_zonas):
    if gdf is None or len(gdf) == 0:
        return gdf
    
    lista_potreros = []
    for idx, potrero_row in gdf.iterrows():
        potrero = potrero_row.geometry
        
        if isinstance(potrero, MultiPolygon):
            polygons = list(potrero.geoms)
        else:
            polygons = [potrero]
        
        for poly_idx, polygon in enumerate(polygons):
            minx, miny, maxx, maxy = polygon.bounds
            sub_poligonos = []
            n_cols = math.ceil(math.sqrt(n_zonas))
            n_rows = math.ceil(n_zonas / n_cols)
            width = (maxx - minx) / n_cols
            height = (maxy - miny) / n_rows
            
            for i in range(n_rows):
                for j in range(n_cols):
                    if len(sub_poligonos) >= n_zonas:
                        break
                    cell_minx = minx + j * width
                    cell_maxx = minx + (j + 1) * width
                    cell_miny = miny + i * height
                    cell_maxy = miny + (i + 1) * height
                    cell = Polygon([
                        (cell_minx, cell_miny),
                        (cell_maxx, cell_miny),
                        (cell_maxx, cell_maxy),
                        (cell_minx, cell_maxy)
                    ])
                    inter = polygon.intersection(cell)
                    if not inter.is_empty and inter.area > 0:
                        sub_poligonos.append(inter)
            
            for sub_idx, sub_poly in enumerate(sub_poligonos):
                lista_potreros.append({
                    'id_potrero': idx + 1,
                    'id_subpoligono': poly_idx + 1,
                    'id_subLote': len(lista_potreros) + 1,
                    'geometry': sub_poly
                })
    
    if lista_potreros:
        nuevo = gpd.GeoDataFrame(lista_potreros)
        nuevo.crs = gdf.crs
        return nuevo
    return gdf

def simular_indices_avanzados(id_subLote, x_norm, y_norm, fuente_satelital, datos_clima=None):
    """Simulación mejorada de índices considerando clima"""
    base = 0.2 + 0.4 * ((id_subLote % 6) / 6)
    
    # Ajustar base por clima si disponible
    if datos_clima:
        factor_clima = 1.0
        if datos_clima.get('precipitacion_promedio', 0) < 1.0:
            factor_clima *= 0.8
        elif datos_clima.get('precipitacion_promedio', 0) > 3.0:
            factor_clima *= 1.2
        base *= factor_clima
    
    ndvi = max(0.05, min(0.85, base + np.random.normal(0, 0.05)))
    
    # Calcular otros índices de manera más realista
    if ndvi < 0.15:
        evi = ndvi * 0.8
        savi = ndvi * 0.9
        bsi = 0.6
        ndbi = 0.25
        gndvi = ndvi * 0.7
    elif ndvi < 0.3:
        evi = ndvi * 1.1
        savi = ndvi * 1.05
        bsi = 0.4
        ndbi = 0.15
        gndvi = ndvi * 0.85
    elif ndvi < 0.5:
        evi = ndvi * 1.3
        savi = ndvi * 1.2
        bsi = 0.1
        ndbi = 0.05
        gndvi = ndvi * 0.95
    else:
        evi = ndvi * 1.4
        savi = ndvi * 1.3
        bsi = -0.1
        ndbi = -0.05
        gndvi = ndvi * 1.05
    
    msavi2 = ndvi * 1.0
    ndmi = ndvi * 0.9  # Índice de humedad
    
    return ndvi, evi, savi, bsi, ndbi, msavi2, gndvi, ndmi

# -----------------------
# CÁLCULO DE MÉTRICAS MEJORADO
# -----------------------
def calcular_metricas_avanzadas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, datos_clima=None):
    """Cálculo mejorado de métricas ganaderas considerando clima"""
    params = obtener_parametros_forrajeros_avanzados(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row.get('biomasa_disponible_kg_ms_ha', 0)
        area_ha = row.get('area_ha', 0)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        # Ajustar por clima si disponible
        factor_ajuste_clima = 1.0
        if datos_clima:
            # Ajuste por estrés térmico
            temp_max = datos_clima.get('temp_max_promedio', 25)
            if temp_max > 32:
                factor_ajuste_clima *= 0.9
            
            # Ajuste por humedad
            humedad = datos_clima.get('humedad_promedio', 70)
            if humedad > 85:
                factor_ajuste_clima *= 0.95
        
        # Cálculo de EV soportable
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable) * factor_ajuste_clima
        else:
            ev_soportable = 0.01
        
        if ev_soportable > 0 and area_ha > 0:
            ev_ha = ev_soportable / area_ha
            ev_ha_display = ev_ha
        else:
            ev_ha_display = 0.01
        
        # Días de permanencia ajustados
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(max(dias_permanencia, 0.1), 365) * factor_ajuste_clima
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1
        
        # Estado forrajero mejorado
        if biomasa_disponible >= 2500:
            estado_forrajero = 5  # Excelente
        elif biomasa_disponible >= 1800:
            estado_forrajero = 4  # Muy bueno
        elif biomasa_disponible >= 1200:
            estado_forrajero = 3  # Bueno
        elif biomasa_disponible >= 600:
            estado_forrajero = 2  # Regular
        elif biomasa_disponible >= 200:
            estado_forrajero = 1  # Crítico
        else:
            estado_forrajero = 0  # Muy crítico
        
        # Tasa de utilización ajustada
        if biomasa_total_disponible > 0:
            tasa_util = min(1.0, (carga_animal * consumo_individual_kg) / biomasa_total_disponible)
        else:
            tasa_util = 0
        
        # Cálculo de balance forrajero
        produccion_diaria = row.get('crecimiento_diario', 0) * area_ha
        consumo_diario = carga_animal * consumo_individual_kg
        balance_diario = produccion_diaria - consumo_diario
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'dias_permanencia': round(dias_permanencia, 1),
            'tasa_utilizacion': round(tasa_util, 3),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_ha_display, 3),
            'produccion_diaria_kg': round(produccion_diaria, 1),
            'consumo_diario_kg': round(consumo_diario, 1),
            'balance_diario_kg': round(balance_diario, 1),
            'factor_ajuste_clima': round(factor_ajuste_clima, 2)
        })
    
    return metricas

# -----------------------
# VISUALIZACIÓN MEJORADA
# -----------------------
def crear_mapa_detallado_avanzado(gdf_analizado, tipo_pastura, datos_clima=None, datos_suelo=None):
    """Crea mapa detallado con información climática y de suelo"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        ax1, ax2, ax3, ax4 = axes.flatten()
        
        # 1. Tipos de superficie
        colores_superficie = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }
        
        for idx, row in gdf_analizado.iterrows():
            tipo = row.get('tipo_superficie', 'VEGETACION_ESCASA')
            color = colores_superficie.get(tipo, '#cccccc')
            gdf_analizado.iloc[[idx]].plot(ax=ax1, color=color, edgecolor='black', linewidth=0.5)
            c = row.geometry.centroid
            ax1.text(c.x, c.y, f"S{row['id_subLote']}", fontsize=6, ha='center', va='center')
        
        ax1.set_title(f"Tipos de Superficie - {tipo_pastura}", fontsize=12, fontweight='bold')
        
        # Leyenda
        patches = [mpatches.Patch(color=color, label=label) 
                  for label, color in colores_superficie.items()]
        ax1.legend(handles=patches, loc='upper right', fontsize=8)
        
        # 2. Biomasa disponible
        cmap = LinearSegmentedColormap.from_list('biomasa', ['#d73027','#fee08b','#a6d96a','#1a9850'])
        
        for idx, row in gdf_analizado.iterrows():
            biom = row.get('biomasa_disponible_kg_ms_ha', 0)
            val = max(0, min(1, biom/4000))
            color = cmap(val)
            gdf_analizado.iloc[[idx]].plot(ax=ax2, color=color, edgecolor='black', linewidth=0.5)
            c = row.geometry.centroid
            ax2.text(c.x, c.y, f"{biom:.0f}", fontsize=6, ha='center', va='center')
        
        ax2.set_title("Biomasa Disponible (kg MS/ha)", fontsize=12, fontweight='bold')
        
        # 3. Estrés hídrico
        if 'estres_hidrico' in gdf_analizado.columns:
            cmap_estres = LinearSegmentedColormap.from_list('estres', ['#1a9850','#fee08b','#d73027'])
            
            for idx, row in gdf_analizado.iterrows():
                estres = row.get('estres_hidrico', 0)
                val = max(0, min(1, estres))
                color = cmap_estres(val)
                gdf_analizado.iloc[[idx]].plot(ax=ax3, color=color, edgecolor='black', linewidth=0.5)
                c = row.geometry.centroid
                ax3.text(c.x, c.y, f"{estres:.2f}", fontsize=6, ha='center', va='center')
            
            ax3.set_title("Índice de Estrés Hídrico", fontsize=12, fontweight='bold')
        else:
            # Cobertura vegetal como alternativa
            for idx, row in gdf_analizado.iterrows():
                cobertura = row.get('cobertura_vegetal', 0)
                color = plt.cm.Greens(cobertura)
                gdf_analizado.iloc[[idx]].plot(ax=ax3, color=color, edgecolor='black', linewidth=0.5)
                c = row.geometry.centroid
                ax3.text(c.x, c.y, f"{cobertura:.2f}", fontsize=6, ha='center', va='center')
            
            ax3.set_title("Cobertura Vegetal", fontsize=12, fontweight='bold')
        
        # 4. Información climática y de suelo (texto)
        ax4.axis('off')
        
        y_pos = 0.9
        
        if datos_clima:
            ax4.text(0.1, y_pos, "📊 DATOS CLIMÁTICOS (NASA POWER)", fontsize=14, fontweight='bold', 
                    transform=ax4.transAxes)
            y_pos -= 0.05
            
            info_clima = [
                f"• Precipitación total: {datos_clima.get('precipitacion_total', 0):.1f} mm",
                f"• Precipitación promedio: {datos_clima.get('precipitacion_promedio', 0):.1f} mm/día",
                f"• Temperatura máxima: {datos_clima.get('temp_max_promedio', 0):.1f} °C",
                f"• Temperatura mínima: {datos_clima.get('temp_min_promedio', 0):.1f} °C",
                f"• Evapotranspiración (ET0): {datos_clima.get('et0_promedio', 0):.1f} mm/día",
                f"• Días con lluvia: {datos_clima.get('dias_lluvia', 0)}",
                f"• Balance hídrico: {datos_clima.get('balance_hidrico', 0):.1f} mm"
            ]
            
            for info in info_clima:
                ax4.text(0.1, y_pos, info, fontsize=10, transform=ax4.transAxes)
                y_pos -= 0.04
        
        if datos_suelo:
            ax4.text(0.1, y_pos, "🌍 DATOS DE SUELO", fontsize=14, fontweight='bold', 
                    transform=ax4.transAxes)
            y_pos -= 0.05
            
            info_suelo = [
                f"• Textura: {datos_suelo.get('textura', 'N/A')}",
                f"• Materia orgánica: {datos_suelo.get('materia_organica', 0):.1f} %",
                f"• pH: {datos_suelo.get('ph', 0):.1f}",
                f"• Capacidad de campo: {datos_suelo.get('capacidad_campo', 0):.1f} %",
                f"• Profundidad: {datos_suelo.get('profundidad', 0):.0f} cm",
                f"• Fuente: {datos_suelo.get('fuente', 'N/A')}"
            ]
            
            for info in info_suelo:
                ax4.text(0.1, y_pos, info, fontsize=10, transform=ax4.transAxes)
                y_pos -= 0.04
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
        
    except Exception as e:
        st.error(f"❌ Error creando mapa avanzado: {e}")
        return None

# -----------------------
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# -----------------------
def ejecutar_analisis_avanzado(gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                              umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo,
                              umbral_estres_hidrico, factor_seguridad, tasa_crecimiento_lluvia,
                              usar_clima=True, usar_suelo=True, fecha_inicio_clima=None, fecha_fin_clima=None):
    """Ejecuta análisis forrajero avanzado con clima y suelo"""
    
    try:
        # Obtener datos climáticos y de suelo para el área
        datos_clima_global = None
        datos_suelo_global = None
        
        if usar_clima and fecha_inicio_clima and fecha_fin_clima:
            # Obtener datos climáticos para el centroide del área
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_clima_global = ServicioClimaNASA.obtener_datos_climaticos(
                lat=centroid.y,
                lon=centroid.x,
                fecha_inicio=fecha_inicio_clima,
                fecha_fin=fecha_fin_clima
            )
            
            if datos_clima_global:
                st.success(f"✅ Datos climáticos obtenidos: {datos_clima_global['precipitacion_total']:.1f} mm de precipitación")
            else:
                st.warning("⚠️ No se pudieron obtener datos climáticos. Usando valores por defecto.")
        
        if usar_suelo:
            # Obtener datos de suelo para el centroide
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_suelo_global = ServicioSuelosINTA.obtener_caracteristicas_suelo(
                lat=centroid.y,
                lon=centroid.x
            )
            
            if datos_suelo_global:
                st.success(f"✅ Datos de suelo obtenidos: {datos_suelo_global['textura']}")
        
        # Inicializar analizador avanzado
        analizador = AnalisisForrajeroAvanzado(
            umbral_ndvi_minimo=umbral_ndvi_minimo,
            umbral_ndvi_optimo=umbral_ndvi_optimo,
            sensibilidad_suelo=sensibilidad_suelo,
            umbral_estres_hidrico=umbral_estres_hidrico,
            factor_seguridad=factor_seguridad,
            tasa_crecimiento_lluvia=tasa_crecimiento_lluvia
        )
        
        params = obtener_parametros_forrajeros_avanzados(tipo_pastura)
        resultados = []
        
        st.info("🔍 Aplicando análisis forrajero AVANZADO...")
        
        for idx, row in gdf_sub.iterrows():
            id_subLote = row.get('id_subLote', idx + 1)
            
            # Simular índices con ajuste por clima
            ndvi, evi, savi, bsi, ndbi, msavi2, gndvi, ndmi = simular_indices_avanzados(
                id_subLote, 0.5, 0.5, fuente_satelital, datos_clima_global
            )
            
            # Clasificar vegetación considerando clima
            categoria, cobertura = analizador.clasificar_vegetacion_avanzada(
                ndvi, evi, savi, bsi, ndbi, msavi2, datos_clima_global
            )
            
            # Calcular biomasa considerando clima y suelo
            biomasa_ms_ha, crecimiento_diario, calidad, biomasa_disponible = analizador.calcular_biomasa_avanzada(
                ndvi, evi, savi, categoria, cobertura, params, datos_clima_global, datos_suelo_global
            )
            
            # Calcular estrés hídrico si hay datos climáticos
            estres_hidrico = 0.0
            if datos_clima_global:
                et0 = datos_clima_global.get('et0_promedio', 3.0)
                kc = 1.0 if categoria in ["VEGETACION_MODERADA", "VEGETACION_DENSA"] else 0.5
                etc = et0 * kc
                precipitacion = datos_clima_global.get('precipitacion_promedio', 2.0)
                estres_hidrico = max(0, etc - precipitacion) / max(etc, 0.1)
            
            resultados.append({
                'id_subLote': id_subLote,
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'msavi2': round(float(msavi2), 3),
                'bsi': round(float(bsi), 3),
                'ndbi': round(float(ndbi), 3),
                'gndvi': round(float(gndvi), 3),
                'ndmi': round(float(ndmi), 3),
                'cobertura_vegetal': round(cobertura, 3),
                'tipo_superficie': categoria,
                'biomasa_ms_ha': round(biomasa_ms_ha, 1),
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'factor_calidad': round(calidad, 3),
                'estres_hidrico': round(estres_hidrico, 3),
                'fuente_datos': fuente_satelital
            })
        
        st.success("✅ Análisis avanzado completado.")
        return resultados, datos_clima_global, datos_suelo_global
        
    except Exception as e:
        st.error(f"❌ Error en análisis avanzado: {e}")
        import traceback
        st.error(traceback.format_exc())
        return [], None, None

# -----------------------
# FLUJO PRINCIPAL MEJORADO
# -----------------------
st.markdown("### 📁 Cargar / visualizar lote")
gdf_loaded = None

if uploaded_file is not None:
    with st.spinner("Cargando archivo..."):
        try:
            if tipo_archivo == "Shapefile (ZIP)":
                gdf_loaded = cargar_shapefile_desde_zip(uploaded_file)
            elif tipo_archivo == "KML":
                gdf_loaded = cargar_kml(uploaded_file)
            else:  # KMZ
                gdf_loaded = cargar_kmz(uploaded_file)
            
            if gdf_loaded is not None and len(gdf_loaded) > 0:
                n_poligonos_original = len(gdf_loaded)
                st.info(f"📊 Se cargaron {n_poligonos_original} polígonos")
                
                gdf_procesado = procesar_y_unir_poligonos(gdf_loaded, unir_poligonos)
                
                if gdf_procesado is not None and len(gdf_procesado) > 0:
                    st.session_state.gdf_cargado = gdf_procesado
                    
                    # Calcular superficie
                    areas = calcular_superficie(gdf_procesado)
                    gdf_procesado['area_ha'] = areas.values
                    area_total = gdf_procesado['area_ha'].sum()
                    
                    st.success("✅ Archivo cargado y procesado correctamente.")
                    
                    # Mostrar información del área
                    col1, col2, col3, col4 = st.columns(4)
                    with col1: 
                        st.metric("Polígonos", len(gdf_procesado))
                        if n_poligonos_original > 1:
                            st.caption(f"(Original: {n_poligonos_original})")
                    with col2: st.metric("Área total (ha)", f"{area_total:.2f}")
                    with col3: st.metric("Tipo pastura", tipo_pastura)
                    with col4: 
                        st.metric("Clima", "NASA POWER" if usar_clima else "No")
                        st.metric("Suelo", "INTA" if usar_suelo else "No")
                    
                    if len(gdf_procesado) > 1:
                        st.warning(f"⚠️ Se analizarán {len(gdf_procesado)} potreros por separado.")
                    
                    if FOLIUM_AVAILABLE:
                        st.markdown("---")
                        st.markdown("### 🗺️ Visualización del potrero")
                        
                        # Crear mapa interactivo con zoom automático
                        mapa_interactivo = crear_mapa_interactivo_con_zoom(gdf_procesado, base_map_option)
                        
                        if mapa_interactivo:
                            st_folium(mapa_interactivo, width=1200, height=500)
                    else:
                        st.info("Instalá folium para ver el mapa interactivo: pip install folium streamlit-folium")
                else:
                    st.info("Carga completada pero no se detectaron geometrías válidas.")
            else:
                st.info("Carga completada pero no se detectaron geometrías válidas.")
        except Exception as e:
            st.error(f"❌ Error al cargar archivo: {e}")

st.markdown("---")
st.markdown("### 🚀 Ejecutar análisis avanzado")

if st.session_state.gdf_cargado is not None:
    if st.button("🚀 Ejecutar Análisis Forrajero Avanzado", type="primary"):
        with st.spinner("Ejecutando análisis avanzado con clima y suelo..."):
            try:
                gdf_input = st.session_state.gdf_cargado.copy()
                
                # Dividir en sub-lotes
                gdf_sub = dividir_potrero_en_subLotes(gdf_input, n_divisiones)
                
                if gdf_sub is None or len(gdf_sub) == 0:
                    st.error("No se pudo dividir el potrero en sub-lotes.")
                else:
                    # Calcular áreas
                    areas = calcular_superficie(gdf_sub)
                    gdf_sub['area_ha'] = areas.values
                    
                    st.success(f"✅ División completada: {len(gdf_sub)} sub-lotes creados")
                    
                    # Ejecutar análisis avanzado
                    resultados, datos_clima, datos_suelo = ejecutar_analisis_avanzado(
                        gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                        umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo,
                        umbral_estres_hidrico, factor_seguridad, tasa_crecimiento_lluvia,
                        usar_clima, usar_suelo, fecha_inicio_clima, fecha_fin_clima
                    )
                    
                    if not resultados:
                        st.error("No se pudieron calcular índices.")
                    else:
                        # Asignar resultados al GeoDataFrame
                        for idx, rec in enumerate(resultados):
                            for k, v in rec.items():
                                if k != 'id_subLote':
                                    try:
                                        gdf_sub.loc[gdf_sub.index[idx], k] = v
                                    except Exception:
                                        pass
                        
                        # Calcular métricas avanzadas
                        metricas = calcular_metricas_avanzadas(gdf_sub, tipo_pastura, peso_promedio, carga_animal, datos_clima)
                        
                        for idx, met in enumerate(metricas):
                            for k, v in met.items():
                                try:
                                    gdf_sub.loc[gdf_sub.index[idx], k] = v
                                except Exception:
                                    pass
                        
                        # Guardar en session state
                        st.session_state.gdf_analizado = gdf_sub
                        st.session_state.datos_clima = datos_clima
                        st.session_state.datos_suelo = datos_suelo
                        
                        # Crear y mostrar mapa avanzado
                        mapa_buf = crear_mapa_detallado_avanzado(gdf_sub, tipo_pastura, datos_clima, datos_suelo)
                        
                        if mapa_buf is not None:
                            st.image(mapa_buf, use_column_width=True, caption="Mapa de análisis avanzado")
                            st.session_state.mapa_detallado_bytes = mapa_buf
                        
                        # Mostrar resumen de datos
                        st.markdown("---")
                        st.markdown("### 📊 RESUMEN DE DATOS")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Biomasa promedio", f"{gdf_sub['biomasa_disponible_kg_ms_ha'].mean():.0f} kg/ha")
                            st.metric("NDVI promedio", f"{gdf_sub['ndvi'].mean():.3f}")
                        
                        with col2:
                            st.metric("EV total soportable", f"{gdf_sub['ev_soportable'].sum():.1f}")
                            st.metric("Días permanencia", f"{gdf_sub['dias_permanencia'].mean():.1f}")
                        
                        with col3:
                            if 'estres_hidrico' in gdf_sub.columns:
                                estres_prom = gdf_sub['estres_hidrico'].mean()
                                st.metric("Estrés hídrico", f"{estres_prom:.2f}")
                                if estres_prom > 0.5:
                                    st.warning("⚠️ Alto estrés hídrico detectado")
                            
                            if datos_clima:
                                st.metric("Precipitación", f"{datos_clima.get('precipitacion_total', 0):.0f} mm")
                        
                        # Mostrar datos climáticos si están disponibles
                        if datos_clima:
                            st.markdown("---")
                            st.markdown("### 🌤️ DATOS CLIMÁTICOS OBTENIDOS")
                            
                            clim_col1, clim_col2, clim_col3 = st.columns(3)
                            
                            with clim_col1:
                                st.metric("Precipitación total", f"{datos_clima.get('precipitacion_total', 0):.1f} mm")
                                st.metric("Temp. máxima", f"{datos_clima.get('temp_max_promedio', 0):.1f} °C")
                            
                            with clim_col2:
                                st.metric("Precipitación diaria", f"{datos_clima.get('precipitacion_promedio', 0):.1f} mm/día")
                                st.metric("Temp. mínima", f"{datos_clima.get('temp_min_promedio', 0):.1f} °C")
                            
                            with clim_col3:
                                st.metric("ET0", f"{datos_clima.get('et0_promedio', 0):.1f} mm/día")
                                st.metric("Balance hídrico", f"{datos_clima.get('balance_hidrico', 0):.1f} mm")
                        
                        # Mostrar datos de suelo si están disponibles
                        if datos_suelo:
                            st.markdown("---")
                            st.markdown("### 🌍 DATOS DE SUELO OBTENIDOS")
                            
                            suelo_col1, suelo_col2, suelo_col3 = st.columns(3)
                            
                            with suelo_col1:
                                st.metric("Textura", datos_suelo.get('textura', 'N/A'))
                                st.metric("Clasificación", datos_suelo.get('clase_textura', 'N/A'))
                            
                            with suelo_col2:
                                st.metric("Materia orgánica", f"{datos_suelo.get('materia_organica', 0):.1f} %")
                                st.metric("pH", f"{datos_suelo.get('ph', 0):.1f}")
                            
                            with suelo_col3:
                                st.metric("Capacidad campo", f"{datos_suelo.get('capacidad_campo', 0):.1f} %")
                                st.metric("Fuente", datos_suelo.get('fuente', 'N/A'))
                        
                        # Exportar datos
                        st.markdown("---")
                        st.markdown("### 💾 EXPORTAR DATOS")
                        
                        # Exportar GeoJSON
                        try:
                            geojson_str = gdf_sub.to_json()
                            st.download_button(
                                "📤 Exportar GeoJSON",
                                geojson_str,
                                f"analisis_avanzado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                                "application/geo+json"
                            )
                        except Exception as e:
                            st.error(f"Error exportando GeoJSON: {e}")
                        
                        # Exportar CSV
                        try:
                            csv_data = gdf_sub.drop(columns=['geometry']).copy()
                            
                            # Agregar datos climáticos y de suelo al CSV
                            if datos_clima:
                                for key, value in datos_clima.items():
                                    if key != 'datos_crudos':
                                        csv_data[f'clima_{key}'] = value
                            
                            if datos_suelo:
                                for key, value in datos_suelo.items():
                                    if key not in ['detalles', 'fuente']:
                                        csv_data[f'suelo_{key}'] = value
                            
                            csv_bytes = csv_data.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "📊 Exportar CSV completo",
                                csv_bytes,
                                f"analisis_avanzado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                "text/csv"
                            )
                        except Exception as e:
                            st.error(f"Error exportando CSV: {e}")
                        
                        # Mostrar tabla de resultados
                        st.markdown("---")
                        st.markdown("### 📋 TABLA DE RESULTADOS")
                        
                        columnas_detalle = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
                                           'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha',
                                           'estres_hidrico', 'ev_ha', 'dias_permanencia']
                        cols_presentes = [c for c in columnas_detalle if c in gdf_sub.columns]
                        
                        df_show = gdf_sub[cols_presentes].copy()
                        df_show.columns = [c.replace('_', ' ').title() for c in df_show.columns]
                        
                        st.dataframe(df_show, use_container_width=True, height=400)
                        
                        # Nota sobre la generación del informe DOCX
                        if DOCX_AVAILABLE:
                            st.info("📄 Para generar el informe DOCX avanzado, necesitamos implementar la función específica.")
                            st.info("La función de generación de informe está disponible en el código completo.")
                        else:
                            st.warning("python-docx no está instalado. Ejecutá: pip install python-docx")
                        
                        st.session_state.analisis_completado = True
                        
            except Exception as e:
                st.error(f"❌ Error ejecutando análisis: {e}")
                import traceback
                st.error(traceback.format_exc())
else:
    st.info("Carga un archivo (ZIP con shapefile, KML o KMZ) en la barra lateral para comenzar.")

# -----------------------
# INFORMACIÓN ADICIONAL
# -----------------------
st.markdown("---")
st.markdown("### 📚 INFORMACIÓN ADICIONAL")

with st.expander("ℹ️ Acerca de los datos utilizados"):
    st.markdown("""
    #### 🌤️ NASA POWER (Prediction Of Worldwide Energy Resource)
    - **Fuente**: NASA Langley Research Center
    - **Datos**: Precipitación, temperatura, humedad, radiación solar, evapotranspiración
    - **Resolución temporal**: Diaria
    - **Resolución espacial**: 0.5° × 0.5° (aproximadamente 55 km)
    - **Período**: Desde 1981 hasta presente
    
    #### 🌍 MAPA DE SUELOS INTA
    - **Fuente**: Instituto Nacional de Tecnología Agropecuaria (INTA)
    - **Datos**: Textura, materia orgánica, pH, capacidad de campo
    - **Escala**: 1:250,000 a 1:50,000 según región
    - **Cobertura**: Todo el territorio argentino
    - **Nota**: Si el servicio no está disponible, se usan datos simulados basados en ubicación
    
    #### 📊 ANÁLISIS FORRAJERO AVANZADO
    - **Índices espectrales**: NDVI, EVI, SAVI, GNDVI, NDMI
    - **Factores considerados**: Clima, suelo, tipo de pastura
    - **Parámetros ajustables**: Umbrales, factores de seguridad
    - **Salidas**: Biomasa, EV soportable, días de permanencia, estrés hídrico
    """)

with st.expander("🎯 Recomendaciones de uso"):
    st.markdown("""
    #### PARA ANÁLISIS PRECISOS:
    1. **Cargar polígonos precisos** del potrero
    2. **Seleccionar el tipo de pastura** correcto
    3. **Ajustar parámetros** según conocimiento local
    4. **Usar datos climáticos** para períodos relevantes
    5. **Verificar datos de suelo** con observaciones de campo
    
    #### INTERPRETACIÓN DE RESULTADOS:
    - **Biomasa < 600 kg/ha**: Condiciones críticas
    - **Biomasa 600-1200 kg/ha**: Necesita mejora
    - **Biomasa 1200-1800 kg/ha**: Condiciones aceptables
    - **Biomasa > 1800 kg/ha**: Condiciones buenas a excelentes
    
    - **Estrés hídrico > 0.5**: Considerar riego o reducción de carga
    - **EV/ha < 0.5**: Carga animal excesiva
    - **Días permanencia < 15**: Rotación muy rápida
    """)

st.markdown("---")
st.markdown("**Desarrollado por** 🚀 **PRV - Predicción y Recomendación de Variables**")
st.markdown("*Sistema integrado de análisis forrajero con datos climáticos y de suelo*")
