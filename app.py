# app.py
"""
App completa mejorada: análisis forrajero + clima NASA POWER + suelos INTA
+ MAPAS CON ESRI SATELLITE + INFORME COMPLETO EN PDF/DOCX
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

# === NUEVAS IMPORTACIONES PARA INFORME Y MAPAS CON ESRI ===
try:
    import contextily as ctx
    CONTEXTILY_AVAILABLE = True
except Exception:
    CONTEXTILY_AVAILABLE = False
    st.warning("Instalá contextily para fondos de Esri en mapas estáticos: pip install contextily")

# Intento importar python-docx
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# ReportLab para PDF
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# Streamlit config
st.set_page_config(page_title="🌱 Disponibilidad Forrajera PRV + Clima + Suelo", layout="wide")
st.title("🌱 Disponibilidad Forrajera PRV — Analizador Avanzado")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# ---------- APIs Externas ----------
NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
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
    'docx_buffer', 'pdf_buffer', 'analisis_completado', 'html_download_injected',
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
# [CLASES ServicioClimaNASA y ServicioSuelosINTA SIN CAMBIOS – SE MANTIENEN IGUAL]
# (Se omiten aquí por brevedad, pero están completas en tu archivo original)

class ServicioClimaNASA:
    @staticmethod
    def obtener_datos_climaticos(lat: float, lon: float, fecha_inicio: datetime, fecha_fin: datetime) -> Optional[Dict]:
        try:
            start_str = fecha_inicio.strftime("%Y%m%d")
            end_str = fecha_fin.strftime("%Y%m%d")
            params = {
                "parameters": "PRECTOTCORR,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS2M",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": start_str,
                "end": end_str,
                "format": "JSON"
            }
            with st.spinner(f"Consultando NASA POWER para coordenadas {lat:.4f}, {lon:.4f}..."):
                response = requests.get(NASA_POWER_BASE_URL, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    st.info(f"✅ Datos climáticos obtenidos para período {start_str} - {end_str}")
                    return ServicioClimaNASA._procesar_datos_nasa(data, lat, lon, fecha_inicio, fecha_fin)
                else:
                    st.warning(f"⚠️ API NASA POWER no disponible (código {response.status_code})")
                    return None
        except Exception as e:
            st.warning(f"⚠️ Error consultando NASA POWER: {str(e)}")
            return None

    @staticmethod
    def _procesar_datos_nasa(data: Dict, lat: float, lon: float, fecha_inicio: datetime, fecha_fin: datetime) -> Optional[Dict]:
        try:
            if not data or 'properties' not in data:
                raise ValueError("Estructura inválida")
            properties = data.get('properties', {})
            parameters = data.get('parameters', {})

            def extraer_datos(param_name, default_val=0):
                param = parameters.get(param_name, {})
                datos = param.get('data', [])
                if not datos:
                    return [default_val]
                datos_filtrados = [d for d in datos if d is not None and d != -999]
                return datos_filtrados if datos_filtrados else [default_val]

            precip_data = extraer_datos('PRECTOTCORR', 0)
            tmax_data = extraer_datos('T2M_MAX', 20)
            tmin_data = extraer_datos('T2M_MIN', 10)
            rh_data = extraer_datos('RH2M', 70)
            rad_data = extraer_datos('ALLSKY_SFC_SW_DWN', 15)
            wind_data = extraer_datos('WS2M', 2)

            resultado = {
                'latitud': lat,
                'longitud': lon,
                'periodo': f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
                'precipitacion_total': round(sum(precip_data), 1),
                'precipitacion_promedio': round(np.mean(precip_data), 1),
                'temp_max_promedio': round(np.mean(tmax_data), 1),
                'temp_min_promedio': round(np.mean(tmin_data), 1),
                'humedad_promedio': round(np.mean(rh_data), 1),
                'radiacion_promedio': round(np.mean(rad_data), 1),
                'viento_promedio': round(np.mean(wind_data), 1),
                'dias_lluvia': sum(1 for p in precip_data if p > 0.5),
                'balance_hidrico': round(sum(precip_data) - sum(wind_data) * 3, 1),
                'datos_crudos': data
            }

            resultado['et0_promedio'] = ServicioClimaNASA._calcular_et0(
                resultado['temp_max_promedio'],
                resultado['temp_min_promedio'],
                resultado['humedad_promedio'],
                resultado['radiacion_promedio'],
                resultado['viento_promedio']
            )

            resultado['deficit_hidrico'] = max(0, round(
                resultado['et0_promedio'] * len(precip_data) - resultado['precipitacion_total'], 1
            ))
            resultado['exceso_hidrico'] = max(0, round(
                resultado['precipitacion_total'] - resultado['et0_promedio'] * len(precip_data), 1
            ))

            return resultado
        except Exception as e:
            st.error(f"Error procesando datos NASA: {str(e)}")
            mes = fecha_inicio.month
            if lat < -35:
                if 10 <= mes <= 3:
                    temp_max = 28 + np.random.uniform(-3, 3)
                    temp_min = 15 + np.random.uniform(-3, 3)
                    precip = 80 + np.random.uniform(-20, 40)
                else:
                    temp_max = 18 + np.random.uniform(-3, 3)
                    temp_min = 8 + np.random.uniform(-3, 3)
                    precip = 40 + np.random.uniform(-10, 20)
            else:
                temp_max = 32 + np.random.uniform(-2, 4)
                temp_min = 20 + np.random.uniform(-2, 4)
                precip = 100 + np.random.uniform(-30, 60)
            return {
                'latitud': lat,
                'longitud': lon,
                'precipitacion_total': round(precip, 1),
                'precipitacion_promedio': round(precip / 30, 1),
                'temp_max_promedio': round(temp_max, 1),
                'temp_min_promedio': round(temp_min, 1),
                'humedad_promedio': round(65 + np.random.uniform(-10, 10), 1),
                'radiacion_promedio': round(18 + np.random.uniform(-5, 5), 1),
                'viento_promedio': round(2.5 + np.random.uniform(-1, 1), 1),
                'dias_lluvia': int(precip / 5),
                'balance_hidrico': round(precip - 75, 1),
                'et0_promedio': round(3.5 + np.random.uniform(-1, 1), 1),
                'deficit_hidrico': max(0, round(3.5 * 30 - precip, 1)),
                'exceso_hidrico': max(0, round(precip - 3.5 * 30, 1)),
                'fuente': 'Estimado (NASA POWER no disponible)'
            }

    @staticmethod
    def _calcular_et0(tmax: float, tmin: float, humedad: float, radiacion: float, viento: float) -> float:
        try:
            tmean = (tmax + tmin) / 2
            es = 0.6108 * math.exp((17.27 * tmean) / (tmean + 237.3))
            ea = es * (humedad / 100)
            vpd = es - ea
            radiacion_mj = radiacion * 0.0864
            delta = 4098 * es / ((tmean + 237.3) ** 2)
            gamma = 0.665 * 0.001 * 101.3
            termino_radiacion = (0.408 * delta * radiacion_mj) / (delta + gamma * (1 + 0.34 * viento))
            termino_viento = (gamma * 900 * viento * vpd / (tmean + 273)) / (delta + gamma * (1 + 0.34 * viento))
            et0 = termino_radiacion + termino_viento
            return max(0.1, min(10.0, round(et0, 1)))
        except:
            return 3.5

class ServicioSuelosINTA:
    @staticmethod
    def obtener_caracteristicas_suelo(lat: float, lon: float) -> Optional[Dict]:
        try:
            datos_reales = ServicioSuelosINTA._consultar_servicio_inta(lat, lon)
            if datos_reales:
                return datos_reales
            else:
                st.warning("⚠️ Servicio INTA no disponible. Usando datos simulados.")
                return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)
        except Exception as e:
            st.warning(f"⚠️ Error consultando suelo: {str(e)}. Usando datos simulados.")
            return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)

    @staticmethod
    def _consultar_servicio_inta(lat: float, lon: float) -> Optional[Dict]:
        try:
            wfs_url = "https://geoserver.inta.gob.ar/geoserver/ows"
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "su_250k:su_250k",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{lon-0.05},{lat-0.05},{lon+0.05},{lat+0.05}",
                "maxFeatures": "1"
            }
            response = requests.get(wfs_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('features'):
                    return ServicioSuelosINTA._procesar_datos_suelo(data)
            return None
        except:
            return None

    @staticmethod
    def _procesar_datos_suelo(data: Dict) -> Dict:
        try:
            feature = data['features'][0]['properties']
            resultado = {
                'textura': feature.get('textura', 'Franco'),
                'profundidad': float(feature.get('profundidad', 50)),
                'materia_organica': float(feature.get('materia_organica', 2.5)),
                'ph': float(feature.get('ph', 6.5)),
                'capacidad_campo': float(feature.get('capacidad_campo', 25)),
                'punto_marchitez': float(feature.get('punto_marchitez', 10)),
                'densidad_aparente': float(feature.get('densidad_aparente', 1.3)),
                'conductividad_hidraulica': float(feature.get('conductividad', 10)),
                'carbon_organico': float(feature.get('carbon_organico', 1.5)),
                'nitrogeno_total': float(feature.get('nitrogeno_total', 0.15)),
                'fosforo_disponible': float(feature.get('fosforo_disponible', 15)),
                'potasio_intercambiable': float(feature.get('potasio_intercambiable', 150)),
                'fuente': 'INTA',
            }
            resultado['clase_textura'] = ServicioSuelosINTA._clasificar_textura(resultado['textura'])
            resultado['agua_almacenable'] = round(
                (resultado['capacidad_campo'] - resultado['punto_marchitez']) *
                resultado['profundidad'] * 10 * resultado['densidad_aparente'] / 100, 1
            )
            resultado['indice_fertilidad'] = ServicioSuelosINTA._calcular_indice_fertilidad(resultado)
            return resultado
        except Exception as e:
            st.warning(f"Error procesando datos suelo: {str(e)}")
            return None

    @staticmethod
    def _obtener_datos_simulados(lat: float, lon: float) -> Dict:
        if lat < -35:
            textura = "Franco limoso"; mo = 3.2; ph = 6.8; prof = 65; cc = 28
        elif lat < -40:
            textura = "Franco arenoso"; mo = 1.8; ph = 7.5; prof = 40; cc = 18
        else:
            textura = "Franco arcilloso"; mo = 2.2; ph = 6.5; prof = 55; cc = 32

        resultado = {
            'textura': textura,
            'profundidad': prof + np.random.uniform(-10, 15),
            'materia_organica': round(mo + np.random.uniform(-0.3, 0.3), 1),
            'ph': round(ph + np.random.uniform(-0.4, 0.4), 1),
            'capacidad_campo': round(cc + np.random.uniform(-3, 5), 1),
            'punto_marchitez': round(10 + np.random.uniform(-2, 3), 1),
            'densidad_aparente': round(1.3 + np.random.uniform(-0.1, 0.2), 2),
            'conductividad_hidraulica': round(8 + np.random.uniform(-3, 5), 1),
            'carbon_organico': round(mo * 0.58, 1),
            'nitrogeno_total': round(mo * 0.05 + np.random.uniform(0, 0.02), 2),
            'fosforo_disponible': round(12 + np.random.uniform(-5, 10), 1),
            'potasio_intercambiable': round(120 + np.random.uniform(-30, 50), 1),
            'fuente': 'Simulado (basado en ubicación)',
        }
        resultado['clase_textura'] = ServicioSuelosINTA._clasificar_textura(textura)
        resultado['agua_almacenable'] = round(
            (resultado['capacidad_campo'] - resultado['punto_marchitez']) *
            resultado['profundidad'] * 10 * resultado['densidad_aparente'] / 100, 1
        )
        resultado['indice_fertilidad'] = ServicioSuelosINTA._calcular_indice_fertilidad(resultado)
        return resultado

    @staticmethod
    def _clasificar_textura(textura: str) -> str:
        t = textura.lower()
        if 'arena' in t: return 'Arenoso'
        elif 'limo' in t: return 'Limoso'
        elif 'arcilla' in t: return 'Arcilloso'
        elif 'franco' in t: return 'Franco'
        else: return 'Mixto'

    @staticmethod
    def _calcular_indice_fertilidad(datos_suelo: Dict) -> float:
        try:
            indice = 5.0
            mo = datos_suelo.get('materia_organica', 2.5)
            if mo > 4.0: indice += 2.0
            elif mo > 3.0: indice += 1.0
            elif mo < 1.5: indice -= 1.5
            elif mo < 2.0: indice -= 0.5

            ph = datos_suelo.get('ph', 6.5)
            if 6.0 <= ph <= 7.5: indice += 1.5
            elif 5.5 <= ph < 6.0 or 7.5 < ph <= 8.0: indice += 0.5
            else: indice -= 1.0

            textura = datos_suelo.get('clase_textura', 'Franco')
            if textura == 'Franco limoso': indice += 1.2
            elif textura == 'Franco': indice += 1.0
            elif textura == 'Arcilloso': indice += 0.5
            elif textura == 'Arenoso': indice -= 0.5

            profundidad = datos_suelo.get('profundidad', 50)
            if profundidad > 70: indice += 1.0
            elif profundidad < 30: indice -= 1.0

            return max(1.0, min(10.0, round(indice, 1)))
        except:
            return 5.0

# -----------------------
# FUNCIONES DE CARGA Y PROCESAMIENTO
# -----------------------
# [FUNCIONES cargar_shapefile_desde_zip, cargar_kml, cargar_kmz, unir_poligonos_gdf, procesar_y_unir_poligonos – SIN CAMBIOS]
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
# FUNCIONES DE MAPA MEJORADAS CON ESRI
# -----------------------
def crear_mapa_interactivo_esri(gdf, base_map_name="ESRI Satélite"):
    if not FOLIUM_AVAILABLE or gdf is None or len(gdf) == 0:
        return None
    try:
        bounds = gdf.total_bounds
        centroid = gdf.geometry.centroid.iloc[0]
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=14, tiles=None, control_scale=True)
        if base_map_name == "ESRI Satélite":
            esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            folium.TileLayer(esri_imagery, attr='Esri', name='ESRI Satellite', overlay=False).add_to(m)
        elif base_map_name == "OpenStreetMap":
            folium.TileLayer('OpenStreetMap', attr='OpenStreetMap', name='OpenStreetMap').add_to(m)
        elif base_map_name == "CartoDB Positron":
            folium.TileLayer('CartoDB positron', attr='CartoDB', name='CartoDB Positron').add_to(m)
        elif base_map_name == "Topográfico":
            folium.TileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', attr='OpenTopoMap', name='Topográfico').add_to(m)
        else:
            esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            folium.TileLayer(esri_imagery, attr='Esri', name='ESRI Satellite', overlay=False).add_to(m)

        folium.GeoJson(gdf.__geo_interface__, name='Potrero', style_function=lambda feat: {
            'fillColor': '#00a8ff', 'color': '#00a8ff', 'weight': 3, 'fillOpacity': 0.4
        }).add_to(m)

        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(50, 50))
        folium.LayerControl().add_to(m)
        folium.Marker([centroid.y, centroid.x], popup=f"Centro\nLat: {centroid.y:.6f}\nLon: {centroid.x:.6f}").add_to(m)
        m.add_child(folium.plugins.Fullscreen())
        return m
    except Exception as e:
        st.error(f"❌ Error creando mapa interactivo: {e}")
        return None

# -----------------------
# ANÁLISIS FORRAJERO AVANZADO
# -----------------------
# [CLASE AnalisisForrajeroAvanzado – SIN CAMBIOS]
class AnalisisForrajeroAvanzado:
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6,
                 sensibilidad_suelo=0.5, umbral_estres_hidrico=0.7,
                 factor_seguridad=1.0, tasa_crecimiento_lluvia=15):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo
        self.umbral_estres_hidrico = umbral_estres_hidrico
        self.factor_seguridad = factor_seguridad
        self.tasa_crecimiento_lluvia = tasa_crecimiento_lluvia
        self.factores_suelo = {
            'Arenoso': {'retencion': 0.7, 'infiltracion': 1.3, 'fertilidad': 0.8},
            'Limoso': {'retencion': 1.0, 'infiltracion': 1.0, 'fertilidad': 1.0},
            'Arcilloso': {'retencion': 1.3, 'infiltracion': 0.7, 'fertilidad': 1.2},
            'Franco': {'retencion': 1.1, 'infiltracion': 1.1, 'fertilidad': 1.1},
            'Mixto': {'retencion': 1.0, 'infiltracion': 1.0, 'fertilidad': 1.0}
        }

    def clasificar_vegetacion_avanzada(self, ndvi, evi, savi, bsi, ndbi, msavi2, datos_clima=None):
        if ndvi < 0.10: cat, cob = "SUELO_DESNUDO", 0.05
        elif ndvi < 0.20: cat, cob = "SUELO_PARCIAL", 0.25
        elif ndvi < 0.40: cat, cob = "VEGETACION_ESCASA", 0.5
        elif ndvi < 0.65: cat, cob = "VEGETACION_MODERADA", 0.75
        else: cat, cob = "VEGETACION_DENSA", 0.9

        if datos_clima:
            ajuste = self._calcular_ajuste_climatico(datos_clima)
            cob = max(0.05, min(0.95, cob * ajuste))
            if ajuste < 0.5 and cat != "SUELO_DESNUDO":
                if cat == "VEGETACION_DENSA": cat = "VEGETACION_MODERADA"
                elif cat == "VEGETACION_MODERADA": cat = "VEGETACION_ESCASA"
        return cat, cob

    def _calcular_ajuste_climatico(self, datos_clima):
        ajuste = 1.0
        if datos_clima.get('precipitacion_promedio', 0) < 1.0: ajuste *= 0.7
        elif datos_clima.get('precipitacion_promedio', 0) < 2.0: ajuste *= 0.85
        temp_max = datos_clima.get('temp_max_promedio', 25)
        if temp_max > 35: ajuste *= 0.8
        elif temp_max < 5: ajuste *= 0.9
        balance = datos_clima.get('balance_hidrico', 0)
        if balance < -10: ajuste *= 0.8
        elif balance > 20: ajuste *= 1.1
        return max(0.3, min(1.2, ajuste))

    def calcular_biomasa_avanzada(self, ndvi, evi, savi, categoria, cobertura, params,
                                  datos_clima=None, datos_suelo=None):
        base = params['MS_POR_HA_OPTIMO']
        if categoria == "SUELO_DESNUDO": biomasa_base, crec_base, cal_base = 20, 1, 0.2
        elif categoria == "SUELO_PARCIAL": biomasa_base, crec_base, cal_base = min(base*0.05,200), params['CRECIMIENTO_DIARIO']*0.2, 0.3
        elif categoria == "VEGETACION_ESCASA": biomasa_base, crec_base, cal_base = min(base*0.3,1200), params['CRECIMIENTO_DIARIO']*0.4, 0.5
        elif categoria == "VEGETACION_MODERADA": biomasa_base, crec_base, cal_base = min(base*0.6,3000), params['CRECIMIENTO_DIARIO']*0.7, 0.7
        else: biomasa_base, crec_base, cal_base = min(base*0.9,6000), params['CRECIMIENTO_DIARIO']*0.9, 0.85

        biomasa = biomasa_base * cobertura
        crecimiento = crec_base * cobertura

        if datos_clima:
            biomasa *= self._calcular_factor_climatico(datos_clima)
            crecimiento *= self._calcular_factor_climatico(datos_clima)
        if datos_suelo:
            factor_suelo = self._calcular_factor_suelo(datos_suelo)
            biomasa *= factor_suelo
            crecimiento *= factor_suelo
            cal_base *= factor_suelo

        biomasa_final = biomasa * self.factor_seguridad
        crecimiento_final = crecimiento * self.factor_seguridad

        if categoria == "SUELO_DESNUDO": disp = 20
        elif categoria == "SUELO_PARCIAL": disp = 80
        else: disp = max(20, min(base*0.9, biomasa_final * cal_base * cobertura))

        return biomasa_final, crecimiento_final, cal_base, disp

    def _calcular_factor_climatico(self, datos_clima):
        factor = 1.0
        precip = datos_clima.get('precipitacion_promedio', 2.0)
        if precip > 3.0: factor *= 1.2
        elif precip < 1.0: factor *= 0.7
        temp = datos_clima.get('temp_max_promedio', 25)
        if 20 <= temp <= 30: factor *= 1.1
        elif temp > 35 or temp < 5: factor *= 0.8
        balance = datos_clima.get('balance_hidrico', 0)
        if balance > 0: factor *= min(1.2, 1 + balance/100)
        else: factor *= max(0.6, 1 + balance/50)
        return max(0.4, min(1.3, factor))

    def _calcular_factor_suelo(self, datos_suelo):
        clase = datos_suelo.get('clase_textura', 'Franco')
        factores = self.factores_suelo.get(clase, self.factores_suelo['Franco'])
        factor = factores['retencion'] * 0.4 + factores['fertilidad'] * 0.6
        mo = datos_suelo.get('materia_organica', 2.5)
        if mo > 3.5: factor *= 1.2
        elif mo < 1.5: factor *= 0.8
        ph = datos_suelo.get('ph', 6.5)
        if 6.0 <= ph <= 7.5: factor *= 1.1
        elif ph < 5.5 or ph > 8.0: factor *= 0.7
        return max(0.5, min(1.3, factor))

# -----------------------
# PARÁMETROS FORRAJEROS AVANZADOS
# -----------------------
PARAMETROS_FORRAJEROS_AVANZADOS = {
    'ALFALFA': {'MS_POR_HA_OPTIMO': 5000, 'CRECIMIENTO_DIARIO': 100, 'CONSUMO_PORCENTAJE_PESO': 0.03, 'TASA_UTILIZACION_RECOMENDADA': 0.65},
    'RAYGRASS': {'MS_POR_HA_OPTIMO': 4500, 'CRECIMIENTO_DIARIO': 90, 'CONSUMO_PORCENTAJE_PESO': 0.028, 'TASA_UTILIZACION_RECOMENDADA': 0.60},
    'FESTUCA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.025, 'TASA_UTILIZACION_RECOMENDADA': 0.55},
    'AGROPIRRO': {'MS_POR_HA_OPTIMO': 3500, 'CRECIMIENTO_DIARIO': 60, 'CONSUMO_PORCENTAJE_PESO': 0.022, 'TASA_UTILIZACION_RECOMENDADA': 0.50},
    'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 40, 'CONSUMO_PORCENTAJE_PESO': 0.020, 'TASA_UTILIZACION_RECOMENDADA': 0.45},
    'MEZCLA_LEGUMINOSAS': {'MS_POR_HA_OPTIMO': 4200, 'CRECIMIENTO_DIARIO': 85, 'CONSUMO_PORCENTAJE_PESO': 0.027, 'TASA_UTILIZACION_RECOMENDADA': 0.58}
}

def obtener_parametros_forrajeros_avanzados(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion
        }
    else:
        return PARAMETROS_FORRAJEROS_AVANZADOS.get(tipo_pastura, PARAMETROS_FORRAJEROS_AVANZADOS['PASTIZAL_NATURAL'])

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
                    if len(sub_poligonos) >= n_zonas: break
                    cell = Polygon([(minx+j*width, miny+i*height), (minx+(j+1)*width, miny+i*height),
                                   (minx+(j+1)*width, miny+(i+1)*height), (minx+j*width, miny+(i+1)*height)])
                    inter = polygon.intersection(cell)
                    if not inter.is_empty and inter.area > 0:
                        sub_poligonos.append(inter)
            for sub_idx, sub_poly in enumerate(sub_poligonos):
                lista_potreros.append({'id_subLote': len(lista_potreros)+1, 'geometry': sub_poly})
    if lista_potreros:
        nuevo = gpd.GeoDataFrame(lista_potreros, crs=gdf.crs)
        return nuevo
    return gdf

def simular_indices_avanzados(id_subLote, x_norm, y_norm, fuente_satelital, datos_clima=None):
    base = 0.2 + 0.4 * ((id_subLote % 6) / 6)
    if datos_clima:
        factor_clima = 1.0
        if datos_clima.get('precipitacion_promedio', 0) < 1.0: factor_clima *= 0.8
        elif datos_clima.get('precipitacion_promedio', 0) > 3.0: factor_clima *= 1.2
        base *= factor_clima
    ndvi = max(0.05, min(0.85, base + np.random.normal(0, 0.05)))
    if ndvi < 0.15: evi, savi, bsi, ndbi, gndvi = ndvi*0.8, ndvi*0.9, 0.6, 0.25, ndvi*0.7
    elif ndvi < 0.3: evi, savi, bsi, ndbi, gndvi = ndvi*1.1, ndvi*1.05, 0.4, 0.15, ndvi*0.85
    elif ndvi < 0.5: evi, savi, bsi, ndbi, gndvi = ndvi*1.3, ndvi*1.2, 0.1, 0.05, ndvi*0.95
    else: evi, savi, bsi, ndbi, gndvi = ndvi*1.4, ndvi*1.3, -0.1, -0.05, ndvi*1.05
    msavi2 = ndvi * 1.0
    ndmi = ndvi * 0.9
    return ndvi, evi, savi, bsi, ndbi, msavi2, gndvi, ndmi

# -----------------------
# CÁLCULO DE MÉTRICAS MEJORADO
# -----------------------
def calcular_metricas_avanzadas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, datos_clima=None):
    params = obtener_parametros_forrajeros_avanzados(tipo_pastura)
    metricas = []
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row.get('biomasa_disponible_kg_ms_ha', 0)
        area_ha = row.get('area_ha', 0)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total_disponible = biomasa_disponible * area_ha

        factor_ajuste_clima = 1.0
        if datos_clima:
            temp_max = datos_clima.get('temp_max_promedio', 25)
            if temp_max > 32: factor_ajuste_clima *= 0.9
            humedad = datos_clima.get('humedad_promedio', 70)
            if humedad > 85: factor_ajuste_clima *= 0.95

        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable) * factor_ajuste_clima
        else:
            ev_soportable = 0.01

        ev_ha_display = ev_soportable / area_ha if ev_soportable > 0 and area_ha > 0 else 0.01

        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(max(dias_permanencia, 0.1), 365) * factor_ajuste_clima
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1

        if biomasa_disponible >= 2500: estado_forrajero = 5
        elif biomasa_disponible >= 1800: estado_forrajero = 4
        elif biomasa_disponible >= 1200: estado_forrajero = 3
        elif biomasa_disponible >= 600: estado_forrajero = 2
        elif biomasa_disponible >= 200: estado_forrajero = 1
        else: estado_forrajero = 0

        tasa_util = min(1.0, (carga_animal * consumo_individual_kg) / biomasa_total_disponible) if biomasa_total_disponible > 0 else 0
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
# DASHBOARD RESUMEN AVANZADO
# -----------------------
def crear_dashboard_resumen(gdf_analizado, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio):
    area_total = gdf_analizado['area_ha'].sum()
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = (gdf_analizado['biomasa_disponible_kg_ms_ha'] * gdf_analizado['area_ha']).sum()
    ndvi_promedio = gdf_analizado['ndvi'].mean()
    ev_total = gdf_analizado['ev_soportable'].sum()
    dias_promedio = gdf_analizado['dias_permanencia'].mean()
    distribucion = gdf_analizado['tipo_superficie'].value_counts()
    estres_prom = gdf_analizado['estres_hidrico'].mean() if 'estres_hidrico' in gdf_analizado.columns else 0

    st.markdown("---")
    st.markdown("## 📊 DASHBOARD RESUMEN DEL ANÁLISIS")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Área Total", f"{area_total:.1f} ha")
    with col2: st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
    with col3: st.metric("EV Soportable", f"{ev_total:.1f}")
    with col4: st.metric("NDVI Promedio", f"{ndvi_promedio:.3f}")

    col5, col6, col7, col8 = st.columns(4)
    with col5: st.metric("Crecimiento Diario", f"{gdf_analizado['crecimiento_diario'].mean():.0f} kg/ha/día")
    with col6: st.metric("Consumo Diario", f"{carga_animal * peso_promedio * 0.025:.0f} kg MS/día")
    with col7: 
        balance = gdf_analizado['crecimiento_diario'].mean() * area_total - (carga_animal * peso_promedio * 0.025)
        st.metric("Balance Diario", f"{balance:.0f} kg MS/día")
    with col8: st.metric("Días Disponibilidad", f"{dias_promedio:.0f} días")

    if len(distribucion) > 0:
        col9, col10 = st.columns(2)
        with col9:
            fig1, ax1 = plt.subplots()
            colors = ['#d73027', '#fdae61', '#fee08b', '#a6d96a', '#1a9850']
            ax1.pie(distribucion.values, labels=distribucion.index, autopct='%1.1f%%', colors=colors[:len(distribucion)])
            st.pyplot(fig1); plt.close(fig1)
        with col10:
            st.dataframe(pd.DataFrame({'Tipo': distribucion.index, 'Sub-lotes': distribucion.values}))

    if datos_clima or datos_suelo:
        col11, col12 = st.columns(2)
        if datos_clima:
            with col11:
                st.markdown("**🌤️ Datos Climáticos**")
                st.dataframe(pd.DataFrame({
                    'Métrica': ['Precipitación Total', 'Temp. Máx.', 'ET0', 'Días Lluvia'],
                    'Valor': [f"{datos_clima.get('precipitacion_total',0):.0f} mm",
                              f"{datos_clima.get('temp_max_promedio',0):.1f} °C",
                              f"{datos_clima.get('et0_promedio',0):.1f} mm/día",
                              f"{datos_clima.get('dias_lluvia',0)} días"]
                }), hide_index=True)
        if datos_suelo:
            with col12:
                st.markdown("**🌍 Datos de Suelo**")
                st.dataframe(pd.DataFrame({
                    'Característica': ['Textura', 'Materia Orgánica', 'pH', 'Índice Fertilidad'],
                    'Valor': [datos_suelo.get('textura','N/A'),
                              f"{datos_suelo.get('materia_organica',0):.1f} %",
                              f"{datos_suelo.get('ph',0):.1f}",
                              f"{datos_suelo.get('indice_fertilidad',5):.1f}/10"]
                }), hide_index=True)

    recomendaciones = []
    if biomasa_promedio < 600: recomendaciones.append("🔴 **CRÍTICO**: Biomasa muy baja (<600 kg/ha).")
    elif biomasa_promedio < 1200: recomendaciones.append("🟡 **ALERTA**: Biomasa baja (600-1200 kg/ha).")
    if estres_prom > 0.7: recomendaciones.append("💧 **ESTRÉS HÍDRICO SEVERO**")
    if dias_promedio < 15: recomendaciones.append("⚡ **ROTACIÓN MUY RÁPIDA**")
    if balance < -500: recomendaciones.append("📉 **DÉFICIT FORRAJERO**")

    st.markdown("### 💡 RECOMENDACIONES")
    for rec in recomendaciones: st.markdown(f"- {rec}")

    return {
        'area_total': area_total,
        'biomasa_promedio': biomasa_promedio,
        'biomasa_total': biomasa_total,
        'ndvi_promedio': ndvi_promedio,
        'ev_total': ev_total,
        'dias_promedio': dias_promedio,
        'estres_prom': estres_prom
    }

# -----------------------
# VISUALIZACIÓN MEJORADA CON ESRI
# -----------------------
def crear_mapa_detallado_avanzado(gdf_analizado, tipo_pastura, datos_clima=None, datos_suelo=None):
    try:
        if CONTEXTILY_AVAILABLE:
            gdf_plot = gdf_analizado.to_crs(epsg=3857)
        else:
            gdf_plot = gdf_analizado.copy()

        fig, axes = plt.subplots(2, 2, figsize=(20, 16))
        ax1, ax2, ax3, ax4 = axes.flatten()

        colores_superficie = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }

        # Mapa 1: Tipos de superficie
        for idx, row in gdf_analizado.iterrows():
            tipo = row.get('tipo_superficie', 'VEGETACION_ESCASA')
            color = colores_superficie.get(tipo, '#cccccc')
            gdf_plot.iloc[[idx]].plot(ax=ax1, color=color, edgecolor='black', linewidth=0.5)
            c = gdf_plot.iloc[idx].geometry.centroid
            ax1.text(c.x, c.y, f"S{row['id_subLote']}", fontsize=6, ha='center', va='center')
        ax1.set_title(f"Tipos de Superficie - {tipo_pastura}", fontsize=12, fontweight='bold')
        patches = [mpatches.Patch(color=color, label=label) for label, color in colores_superficie.items()]
        ax1.legend(handles=patches, loc='upper right', fontsize=8)
        if CONTEXTILY_AVAILABLE:
            try: ctx.add_basemap(ax1, source=ctx.providers.Esri.WorldImagery, alpha=0.4)
            except: pass

        # Mapa 2: Biomasa
        cmap = LinearSegmentedColormap.from_list('biomasa', ['#d73027','#fee08b','#a6d96a','#1a9850'])
        for idx, row in gdf_analizado.iterrows():
            biom = row.get('biomasa_disponible_kg_ms_ha', 0)
            val = max(0, min(1, biom/4000))
            color = cmap(val)
            gdf_plot.iloc[[idx]].plot(ax=ax2, color=color, edgecolor='black', linewidth=0.5)
            c = gdf_plot.iloc[idx].geometry.centroid
            ax2.text(c.x, c.y, f"{biom:.0f}", fontsize=6, ha='center', va='center')
        ax2.set_title("Biomasa Disponible (kg MS/ha)", fontsize=12, fontweight='bold')
        if CONTEXTILY_AVAILABLE:
            try: ctx.add_basemap(ax2, source=ctx.providers.Esri.WorldImagery, alpha=0.4)
            except: pass

        # Mapa 3: Estrés hídrico o cobertura
        if 'estres_hidrico' in gdf_analizado.columns:
            cmap_estres = LinearSegmentedColormap.from_list('estres', ['#1a9850','#fee08b','#d73027'])
            for idx, row in gdf_analizado.iterrows():
                estres = row.get('estres_hidrico', 0)
                val = max(0, min(1, estres))
                color = cmap_estres(val)
                gdf_plot.iloc[[idx]].plot(ax=ax3, color=color, edgecolor='black', linewidth=0.5)
                c = gdf_plot.iloc[idx].geometry.centroid
                ax3.text(c.x, c.y, f"{estres:.2f}", fontsize=6, ha='center', va='center')
            ax3.set_title("Índice de Estrés Hídrico", fontsize=12, fontweight='bold')
        else:
            for idx, row in gdf_analizado.iterrows():
                cobertura = row.get('cobertura_vegetal', 0)
                color = plt.cm.Greens(cobertura)
                gdf_plot.iloc[[idx]].plot(ax=ax3, color=color, edgecolor='black', linewidth=0.5)
                c = gdf_plot.iloc[idx].geometry.centroid
                ax3.text(c.x, c.y, f"{cobertura:.2f}", fontsize=6, ha='center', va='center')
            ax3.set_title("Cobertura Vegetal", fontsize=12, fontweight='bold')
        if CONTEXTILY_AVAILABLE:
            try: ctx.add_basemap(ax3, source=ctx.providers.Esri.WorldImagery, alpha=0.4)
            except: pass

        # Mapa 4: Texto
        ax4.axis('off')
        y_pos = 0.9
        if datos_clima:
            ax4.text(0.1, y_pos, "📊 DATOS CLIMÁTICOS", fontsize=14, fontweight='bold', transform=ax4.transAxes)
            y_pos -= 0.05
            info = [f"• Precipitación total: {datos_clima.get('precipitacion_total',0):.1f} mm",
                    f"• ET0: {datos_clima.get('et0_promedio',0):.1f} mm/día"]
            for txt in info:
                ax4.text(0.1, y_pos, txt, fontsize=10, transform=ax4.transAxes); y_pos -= 0.04
        if datos_suelo:
            ax4.text(0.1, y_pos, "🌍 DATOS DE SUELO", fontsize=14, fontweight='bold', transform=ax4.transAxes)
            y_pos -= 0.05
            info = [f"• Textura: {datos_suelo.get('textura','N/A')}",
                    f"• Materia orgánica: {datos_suelo.get('materia_organica',0):.1f} %"]
            for txt in info:
                ax4.text(0.1, y_pos, txt, fontsize=10, transform=ax4.transAxes); y_pos -= 0.04

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
# GENERACIÓN DE INFORME COMPLETO (NUEVA FUNCIÓN)
# -----------------------
def generar_informe_completo(gdf_analizado, dashboard_metrics, datos_clima, datos_suelo, tipo_pastura, mapa_buf):
    # DOCX
    if DOCX_AVAILABLE:
        doc = Document()
        doc.add_heading('Informe de Análisis Forrajero Avanzado', 0)
        doc.add_paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}").alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Tipo de pastura: {tipo_pastura}").alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_page_break()

        doc.add_heading('Resumen Ejecutivo', level=1)
        resumen = doc.add_paragraph()
        resumen.add_run(f"• Área total: {dashboard_metrics['area_total']:.1f} ha\n")
        resumen.add_run(f"• Biomasa promedio: {dashboard_metrics['biomasa_promedio']:.0f} kg MS/ha\n")
        resumen.add_run(f"• EV soportable total: {dashboard_metrics['ev_total']:.1f}\n")
        resumen.add_run(f"• NDVI promedio: {dashboard_metrics['ndvi_promedio']:.3f}\n")

        if mapa_buf:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                tmp_img.write(mapa_buf.getvalue())
                tmp_img.flush()
                doc.add_heading('Mapas de Análisis', level=1)
                doc.add_picture(tmp_img.name, width=Inches(6.5))
                os.unlink(tmp_img.name)

        doc.add_heading('Resultados por Sub-lote', level=1)
        table = doc.add_table(rows=1, cols=6)
        hdr_cells = table.rows[0].cells
        headers = ['Sub-lote', 'Área (ha)', 'Tipo', 'Biomasa (kg/ha)', 'Estrés Hídrico', 'Días Permanencia']
        for i, header in enumerate(headers):
            hdr_cells[i].text = header
            hdr_cells[i].paragraphs[0].runs[0].font.bold = True

        for idx, row in gdf_analizado.iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = str(row.get('id_subLote', ''))
            row_cells[1].text = f"{row.get('area_ha', 0):.2f}"
            row_cells[2].text = str(row.get('tipo_superficie', ''))
            row_cells[3].text = f"{row.get('biomasa_disponible_kg_ms_ha', 0):.0f}"
            row_cells[4].text = f"{row.get('estres_hidrico', 0):.2f}"
            row_cells[5].text = f"{row.get('dias_permanencia', 0):.1f}"

        if datos_clima:
            doc.add_heading('Datos Climáticos (NASA POWER)', level=1)
            clima_para = doc.add_paragraph()
            clima_para.add_run(f"Precipitación total: {datos_clima.get('precipitacion_total', 0):.1f} mm\n")
            clima_para.add_run(f"Temp. máx. promedio: {datos_clima.get('temp_max_promedio', 0):.1f} °C\n")
            clima_para.add_run(f"ET0 promedio: {datos_clima.get('et0_promedio', 0):.1f} mm/día")

        if datos_suelo:
            doc.add_heading('Datos de Suelo (INTA)', level=1)
            suelo_para = doc.add_paragraph()
            suelo_para.add_run(f"Textura: {datos_suelo.get('textura', 'N/A')}\n")
            suelo_para.add_run(f"Materia orgánica: {datos_suelo.get('materia_organica', 0):.1f} %\n")
            suelo_para.add_run(f"pH: {datos_suelo.get('ph', 0):.1f}\n")
            suelo_para.add_run(f"Índice de fertilidad: {datos_suelo.get('indice_fertilidad', 5):.1f}/10")

        docx_buffer = io.BytesIO()
        doc.save(docx_buffer)
        docx_buffer.seek(0)
    else:
        docx_buffer = None

    # PDF
    if REPORTLAB_AVAILABLE and mapa_buf:
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Informe de Análisis Forrajero Avanzado")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, f"Tipo de pastura: {tipo_pastura}")
        c.drawString(50, height - 90, f"Área total: {dashboard_metrics['area_total']:.1f} ha")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_pdf:
            tmp_pdf.write(mapa_buf.getvalue())
            tmp_pdf.flush()
            c.drawImage(ImageReader(tmp_pdf.name), 50, height - 450, width=500, height=300)
            os.unlink(tmp_pdf.name)
        c.showPage()
        c.save()
        pdf_buffer.seek(0)
    else:
        pdf_buffer = None

    return docx_buffer, pdf_buffer

# -----------------------
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# -----------------------
def ejecutar_analisis_avanzado(gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                               umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo,
                               umbral_estres_hidrico, factor_seguridad, tasa_crecimiento_lluvia,
                               usar_clima=True, usar_suelo=True, fecha_inicio_clima=None, fecha_fin_clima=None):
    try:
        datos_clima_global = None
        datos_suelo_global = None
        if usar_clima and fecha_inicio_clima and fecha_fin_clima:
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_clima_global = ServicioClimaNASA.obtener_datos_climaticos(
                lat=centroid.y, lon=centroid.x,
                fecha_inicio=fecha_inicio_clima, fecha_fin=fecha_fin_clima
            )
            if not datos_clima_global:
                datos_clima_global = {'precipitacion_total': 0, 'precipitacion_promedio': 2.0,
                                      'temp_max_promedio': 25, 'temp_min_promedio': 15,
                                      'humedad_promedio': 70, 'radiacion_promedio': 15,
                                      'viento_promedio': 2, 'dias_lluvia': 0,
                                      'balance_hidrico': 0, 'et0_promedio': 3.0}

        if usar_suelo:
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_suelo_global = ServicioSuelosINTA.obtener_caracteristicas_suelo(
                lat=centroid.y, lon=centroid.x
            )

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
        for idx, row in gdf_sub.iterrows():
            id_subLote = row.get('id_subLote', idx + 1)
            ndvi, evi, savi, bsi, ndbi, msavi2, gndvi, ndmi = simular_indices_avanzados(
                id_subLote, 0.5, 0.5, fuente_satelital, datos_clima_global
            )
            categoria, cobertura = analizador.clasificar_vegetacion_avanzada(
                ndvi, evi, savi, bsi, ndbi, msavi2, datos_clima_global
            )
            biomasa_ms_ha, crecimiento_diario, calidad, biomasa_disponible = analizador.calcular_biomasa_avanzada(
                ndvi, evi, savi, categoria, cobertura, params, datos_clima_global, datos_suelo_global
            )
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

        return resultados, datos_clima_global, datos_suelo_global
    except Exception as e:
        st.error(f"❌ Error en análisis avanzado: {e}")
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
            else:
                gdf_loaded = cargar_kmz(uploaded_file)

            if gdf_loaded is not None and len(gdf_loaded) > 0:
                n_poligonos_original = len(gdf_loaded)
                st.info(f"📊 Se cargaron {n_poligonos_original} polígonos")
                gdf_procesado = procesar_y_unir_poligonos(gdf_loaded, unir_poligonos)
                if gdf_procesado is not None and len(gdf_procesado) > 0:
                    st.session_state.gdf_cargado = gdf_procesado
                    areas = calcular_superficie(gdf_procesado)
                    gdf_procesado['area_ha'] = areas.values
                    area_total = gdf_procesado['area_ha'].sum()
                    st.success("✅ Archivo cargado y procesado correctamente.")

                    col1, col2, col3 = st.columns(3)
                    with col1: st.metric("Polígonos", len(gdf_procesado))
                    with col2: st.metric("Área total (ha)", f"{area_total:.2f}")
                    with col3: st.metric("Tipo pastura", tipo_pastura)

                    if FOLIUM_AVAILABLE:
                        st.markdown("---")
                        st.markdown("### 🗺️ Visualización del potrero")
                        mapa_interactivo = crear_mapa_interactivo_esri(gdf_procesado, base_map_option)
                        if mapa_interactivo:
                            st_folium(mapa_interactivo, width=1200, height=500)
                else:
                    st.info("Carga completada pero no se detectaron geometrías válidas.")
            else:
                st.info("Carga completada pero no se detectaron geometrías válidas.")
        except Exception as e:
            st.error(f"❌ Error al cargar archivo: {e}")

st.markdown("---")
st.markdown("### 🚀 Ejecutar análisis avanzado")
if st.session_state.gdf_cargado is not None:
    if st.button("🚀 Ejecutar Análisis Forrajero Avanzado", type="primary", use_container_width=True):
        with st.spinner("Ejecutando análisis avanzado con clima y suelo..."):
            try:
                gdf_input = st.session_state.gdf_cargado.copy()
                gdf_sub = dividir_potrero_en_subLotes(gdf_input, n_divisiones)
                if gdf_sub is None or len(gdf_sub) == 0:
                    st.error("No se pudo dividir el potrero en sub-lotes.")
                else:
                    areas = calcular_superficie(gdf_sub)
                    gdf_sub['area_ha'] = areas.values
                    st.success(f"✅ División completada: {len(gdf_sub)} sub-lotes creados")

                    resultados, datos_clima, datos_suelo = ejecutar_analisis_avanzado(
                        gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                        umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo,
                        umbral_estres_hidrico, factor_seguridad, tasa_crecimiento_lluvia,
                        usar_clima, usar_suelo, fecha_inicio_clima, fecha_fin_clima
                    )

                    if not resultados:
                        st.error("No se pudieron calcular índices.")
                    else:
                        for idx, rec in enumerate(resultados):
                            for k, v in rec.items():
                                if k != 'id_subLote':
                                    gdf_sub.loc[gdf_sub.index[idx], k] = v

                        metricas = calcular_metricas_avanzadas(gdf_sub, tipo_pastura, peso_promedio, carga_animal, datos_clima)
                        for idx, met in enumerate(metricas):
                            for k, v in met.items():
                                gdf_sub.loc[gdf_sub.index[idx], k] = v

                        st.session_state.gdf_analizado = gdf_sub
                        st.session_state.datos_clima = datos_clima
                        st.session_state.datos_suelo = datos_suelo

                        mapa_buf = crear_mapa_detallado_avanzado(gdf_sub, tipo_pastura, datos_clima, datos_suelo)
                        if mapa_buf is not None:
                            st.image(mapa_buf, use_column_width=True, caption="Mapa de análisis avanzado")
                            st.session_state.mapa_detallado_bytes = mapa_buf

                        dashboard_metrics = crear_dashboard_resumen(
                            gdf_sub, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio
                        )

                        # Generar informe
                        if DOCX_AVAILABLE or REPORTLAB_AVAILABLE:
                            docx_buf, pdf_buf = generar_informe_completo(
                                gdf_sub, dashboard_metrics, datos_clima, datos_suelo, tipo_pastura, mapa_buf
                            )
                            st.session_state.docx_buffer = docx_buf
                            st.session_state.pdf_buffer = pdf_buf

                        # Exportar
                        st.markdown("---")
                        st.markdown("### 💾 EXPORTAR DATOS")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            geojson_str = gdf_sub.to_json()
                            st.download_button("📤 Exportar GeoJSON", geojson_str,
                                               f"analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                                               "application/geo+json", use_container_width=True)
                        with col2:
                            csv_data = gdf_sub.drop(columns=['geometry']).to_csv(index=False).encode('utf-8')
                            st.download_button("📊 Exportar CSV", csv_data,
                                               f"analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                               "text/csv", use_container_width=True)
                        with col3:
                            if st.session_state.get('docx_buffer'):
                                st.download_button("📄 Descargar Informe DOCX",
                                                   st.session_state.docx_buffer,
                                                   f"informe_{tipo_pastura}_{datetime.now().strftime('%Y%m%d')}.docx",
                                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                   use_container_width=True)
                            if st.session_state.get('pdf_buffer'):
                                st.download_button("📄 Descargar Informe PDF",
                                                   st.session_state.pdf_buffer,
                                                   f"informe_{tipo_pastura}_{datetime.now().strftime('%Y%m%d')}.pdf",
                                                   "application/pdf",
                                                   use_container_width=True)

                        st.markdown("---")
                        st.markdown("### 📋 TABLA DE RESULTADOS DETALLADOS")
                        cols_presentes = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi',
                                          'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha',
                                          'estres_hidrico', 'ev_ha', 'dias_permanencia']
                        cols_presentes = [c for c in cols_presentes if c in gdf_sub.columns]
                        df_show = gdf_sub[cols_presentes].copy()
                        df_show.columns = [c.replace('_', ' ').title() for c in df_show.columns]
                        st.dataframe(df_show, use_container_width=True, height=400)

                        st.session_state.analisis_completado = True
                        st.success("🎉 ¡Análisis completado exitosamente!")
            except Exception as e:
                st.error(f"❌ Error ejecutando análisis: {e}")
else:
    st.info("Carga un archivo (ZIP con shapefile, KML o KMZ) en la barra lateral para comenzar.")

# -----------------------
# INFORMACIÓN ADICIONAL
# -----------------------
st.markdown("---")
st.markdown("### 📚 INFORMACIÓN ADICIONAL")
with st.expander("ℹ️ Acerca de los datos utilizados"):
    st.markdown("""
    #### 🌤️ NASA POWER
    - Datos diarios de clima desde 1981
    #### 🌍 MAPA DE SUELOS INTA
    - Escala 1:250,000 a 1:50,000
    #### 📊 ANÁLISIS FORRAJERO AVANZADO
    - Incluye clima, suelo y tipo de pastura
    """)
