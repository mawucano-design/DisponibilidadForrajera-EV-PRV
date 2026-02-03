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
from matplotlib.colors import LinearSegmentedColormap, Normalize
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

# Importar python-docx
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# Folium para mapas
try:
    import folium
    from folium.plugins import HeatMap
    from streamlit_folium import st_folium, folium_static
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False

# ===== GOOGLE EARTH ENGINE CONFIGURACIÓN MEJORADA =====
try:
    import ee
    EE_AVAILABLE = True
except Exception:
    EE_AVAILABLE = False

# ===== INICIALIZACIÓN AUTOMÁTICA GEE =====
def inicializar_gee_automatico():
    """Inicializa GEE automáticamente sin autenticación local"""
    if not EE_AVAILABLE:
        st.session_state.gee_authenticated = False
        return False
    
    
        try:
            # Opción 2: Usar Service Account desde variables de entorno (Streamlit Cloud)
            service_account = os.environ.get('GEE_SERVICE_ACCOUNT', '')
            
            if service_account:
                credentials_dict = json.loads(service_account)
                credentials = ee.ServiceAccountCredentials(
                    email=credentials_dict['client_email'],
                    key_data=json.dumps(credentials_dict)
                )
                ee.Initialize(credentials, project='ee-prv-forrajes')
                st.session_state.gee_authenticated = True
                st.session_state.gee_project = 'ee-prv-forrajes'
                st.success("✅ Google Earth Engine inicializado con Service Account")
                return True
            else:
                # Opción 3: Usar autenticación pública para datos públicos
                ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
                st.session_state.gee_authenticated = True
                st.session_state.gee_project = 'ee-prv-forrajes'
                st.success("✅ Google Earth Engine inicializado en modo público")
                return True
                
        except Exception as e2:
            st.warning(f"⚠️ No se pudo inicializar Google Earth Engine automáticamente")
            st.session_state.gee_authenticated = False
            return False

# Inicializar GEE automáticamente al cargar la app
if EE_AVAILABLE and not st.session_state.get('gee_authenticated', False):
    inicializar_gee_automatico()

# Configuración de Streamlit
st.set_page_config(page_title="🌱 Disponibilidad Forrajera PRV + Clima + Suelo + GEE", layout="wide")
st.title("🌱 Sistema Avanzado de Gestión Forrajera con Satélites")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# ---------- APIs Externas ----------
NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
INTA_SUELOS_WFS_URL = "https://geoserver.inta.gob.ar/geoserver/ows"

# ---------- Parámetros por defecto ----------
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Forzar ESRI Satellite como mapa base único
FORCED_BASE_MAP = "ESRI Satelite"

# Session state inicializado
for key in [
    'gdf_cargado', 'gdf_analizado', 'mapa_detallado_bytes',
    'docx_buffer', 'analisis_completado', 'html_download_injected',
    'datos_clima', 'datos_suelo', 'indices_avanzados', 'informe_generado',
    'heatmap_data', 'heatmap_variable', 'gee_authenticated',
    'imagen_gee', 'coleccion_gee', 'estadisticas_gee', 'usando_gee'
]:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------
# SIDEBAR (CONFIGURACIÓN MEJORADA)
# -----------------------
with st.sidebar:
    st.header("⚙️ Configuración del Análisis")
    
    # Logo y créditos
    st.markdown("---")
    st.markdown("### 🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2 (GEE)", "LANDSAT-8/9 (GEE)", "MOD13Q1 NDVI (GEE)", "SIMULADO"],
    )
    
    # Mostrar estado de GEE
    if "GEE" in fuente_satelital:
        if st.session_state.get('gee_authenticated', False):
            st.success(f"✅ {fuente_satelital} disponible")
        else:
            st.warning(f"⚠️ GEE requiere configuración")
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox("Seleccionar tipo:",
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", 
                                "PASTIZAL_NATURAL", "MEZCLA_LEGUMINOSAS", "PERSONALIZADO"])
    
    # Parámetros personalizados
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05,
                                            value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01,
                                          format="%.2f")
    
    st.subheader("📅 Configuración Temporal")
    col1, col2 = st.columns(2)
    with col1:
        fecha_imagen = st.date_input(
            "Fecha imagen satelital:",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now()
        )
    with col2:
        fecha_fin = st.date_input(
            "Fecha final análisis:",
            value=datetime.now()
        )
    
    # Período para GEE
    if "GEE" in fuente_satelital:
        st.subheader("⚙️ Configuración GEE")
        nubes_max = st.slider("Máximo % de nubes:", 0, 100, 20)
        if "SENTINEL-2" in fuente_satelital:
            st.caption("Sentinel-2: Resolución 10m")
        elif "LANDSAT" in fuente_satelital:
            st.caption("Landsat 8/9: Resolución 30m")
    
    # Parámetros de detección
    st.subheader("🎯 Parámetros de Detección")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI óptimo:", 0.4, 0.8, 0.6, 0.01)
    
    # Parámetros ganaderos
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal:", 1, 1000, 100)
    
    # Datos externos
    st.subheader("🌐 Datos Externos")
    usar_clima = st.checkbox("Usar datos climáticos NASA POWER", value=True)
    usar_suelo = st.checkbox("Usar datos de suelos INTA", value=True)
    
    # División del potrero
    st.subheader("🔪 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=100, value=24)
    
    # Unión de polígonos
    st.subheader("🔄 Unión de Polígonos")
    unir_poligonos = st.checkbox(
        "Unir todos los polígonos", 
        value=True,
        help="Unir todos los polígonos del archivo en un solo potrero"
    )
    
    # Carga de archivos
    st.subheader("📤 Subir Lote")
    tipo_archivo = st.radio(
        "Formato del archivo:",
        ["Shapefile (ZIP)", "KML", "KMZ"],
        horizontal=True
    )
    
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir ZIP con shapefile", type=['zip'])
    elif tipo_archivo == "KML":
        uploaded_file = st.file_uploader("Subir archivo KML", type=['kml'])
    else:
        uploaded_file = st.file_uploader("Subir archivo KMZ", type=['kmz'])
    
    # Información de ayuda
    st.markdown("---")
    with st.expander("ℹ️ Ayuda rápida"):
        st.markdown("""
        **Guía rápida:**
        1. Selecciona fuente satelital
        2. Configura parámetros del potrero
        3. Sube tu archivo espacial
        4. Ejecuta el análisis
        5. Descarga resultados
        
        **Datos disponibles:**
        - 🛰️ Satélites: Sentinel-2, Landsat, MODIS
        - 🌤️ Clima: NASA POWER API
        - 🌍 Suelos: INTA Argentina
        """)

# -----------------------
# SERVICIOS EXTERNOS
# -----------------------
class ServicioClimaNASA:
    """Clase para obtener datos climáticos de NASA POWER API"""
    
    @staticmethod
    def obtener_datos_climaticos(lat: float, lon: float, fecha_inicio: datetime, fecha_fin: datetime) -> Optional[Dict]:
        """Obtiene datos climáticos históricos"""
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
            
            with st.spinner(f"Consultando NASA POWER..."):
                response = requests.get(NASA_POWER_BASE_URL, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    return ServicioClimaNASA._procesar_datos_nasa(data, lat, lon, fecha_inicio, fecha_fin)
                else:
                    return None
                    
        except Exception as e:
            return None
    
    @staticmethod
    def _procesar_datos_nasa(data: Dict, lat: float, lon: float, fecha_inicio: datetime, fecha_fin: datetime) -> Dict:
        """Procesa los datos crudos de NASA POWER"""
        try:
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
            }
            
            return resultado
            
        except Exception as e:
            # Datos por defecto según ubicación
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
                'periodo': f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
                'precipitacion_total': round(precip, 1),
                'precipitacion_promedio': round(precip / 30, 1),
                'temp_max_promedio': round(temp_max, 1),
                'temp_min_promedio': round(temp_min, 1),
                'humedad_promedio': round(65 + np.random.uniform(-10, 10), 1),
                'radiacion_promedio': round(18 + np.random.uniform(-5, 5), 1),
                'viento_promedio': round(2.5 + np.random.uniform(-1, 1), 1),
                'dias_lluvia': int(precip / 5),
                'fuente': 'Estimado'
            }

class ServicioSuelosINTA:
    """Clase para obtener datos de suelos del INTA"""
    
    @staticmethod
    def obtener_caracteristicas_suelo(lat: float, lon: float) -> Optional[Dict]:
        """Obtiene características del suelo"""
        try:
            datos_reales = ServicioSuelosINTA._consultar_servicio_inta(lat, lon)
            if datos_reales:
                return datos_reales
            else:
                return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)
                
        except Exception as e:
            return ServicioSuelosINTA._obtener_datos_simulados(lat, lon)
    
    @staticmethod
    def _consultar_servicio_inta(lat: float, lon: float) -> Optional[Dict]:
        """Intenta consultar el servicio del INTA"""
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
                if data.get('features') and len(data['features']) > 0:
                    return ServicioSuelosINTA._procesar_datos_suelo(data)
            
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
            }
            
            return resultado
            
        except Exception as e:
            return None
    
    @staticmethod
    def _obtener_datos_simulados(lat: float, lon: float) -> Dict:
        """Genera datos de suelo simulados"""
        if lat < -35:
            textura = "Franco limoso"
            materia_organica = 3.2
            ph = 6.8
            profundidad = 65
            capacidad_campo = 28
        elif lat < -40:
            textura = "Franco arenoso"
            materia_organica = 1.8
            ph = 7.5
            profundidad = 40
            capacidad_campo = 18
        else:
            textura = "Franco arcilloso"
            materia_organica = 2.2
            ph = 6.5
            profundidad = 55
            capacidad_campo = 32
        
        resultado = {
            'textura': textura,
            'profundidad': profundidad + np.random.uniform(-10, 15),
            'materia_organica': round(materia_organica + np.random.uniform(-0.3, 0.3), 1),
            'ph': round(ph + np.random.uniform(-0.4, 0.4), 1),
            'capacidad_campo': round(capacidad_campo + np.random.uniform(-3, 5), 1),
            'punto_marchitez': round(10 + np.random.uniform(-2, 3), 1),
            'densidad_aparente': round(1.3 + np.random.uniform(-0.1, 0.2), 2),
            'fuente': 'Simulado',
        }
        
        return resultado

# -----------------------
# GOOGLE EARTH ENGINE MEJORADO
# -----------------------
class ServicioGoogleEarthEngine:
    """Clase mejorada para Google Earth Engine"""
    
    @staticmethod
    def inicializar_gee():
        """Inicializa Google Earth Engine automáticamente"""
        return inicializar_gee_automatico()
    
    @staticmethod
    def obtener_imagen_gee(geometry, fecha_inicio, fecha_fin, fuente_satelital, nubes_max=20):
        """Obtiene una imagen satelital de GEE"""
        try:
            if not EE_AVAILABLE:
                return None
            
            if not st.session_state.get('gee_authenticated', False):
                if not ServicioGoogleEarthEngine.inicializar_gee():
                    return None
            
            import json
            if isinstance(geometry, gpd.GeoDataFrame):
                geojson = json.loads(geometry.to_json())
                if geojson['features']:
                    gee_geom = ee.Geometry(geojson['features'][0]['geometry'])
                else:
                    return None
            else:
                try:
                    coords = list(geometry.exterior.coords)
                    gee_geom = ee.Geometry.Polygon(coords)
                except:
                    return None
            
            start_date = ee.Date(fecha_inicio.strftime('%Y-%m-%d'))
            end_date = ee.Date(fecha_fin.strftime('%Y-%m-%d'))
            
            with st.spinner(f"🛰️ Buscando imágenes {fuente_satelital}..."):
                
                if "SENTINEL-2" in fuente_satelital:
                    collection = ee.ImageCollection('COPERNICUS/S2_SR') \
                        .filterBounds(gee_geom) \
                        .filterDate(start_date, end_date) \
                        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nubes_max)) \
                        .sort('CLOUDY_PIXEL_PERCENTAGE', False)
                    
                    image = collection.first()
                    
                    if image is None:
                        return None
                    
                    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
                    evi = image.expression(
                        '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
                        {
                            'NIR': image.select('B8'),
                            'RED': image.select('B4'),
                            'BLUE': image.select('B2')
                        }
                    ).rename('EVI')
                    
                    result_image = image.addBands([ndvi, evi])
                    
                    st.session_state.imagen_gee = result_image
                    st.session_state.coleccion_gee = collection
                    
                    return result_image
                
                elif "LANDSAT" in fuente_satelital:
                    collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                        .filterBounds(gee_geom) \
                        .filterDate(start_date, end_date) \
                        .filter(ee.Filter.lt('CLOUD_COVER', nubes_max)) \
                        .sort('CLOUD_COVER', False)
                    
                    image = collection.first()
                    
                    if image is None:
                        return None
                    
                    ndvi = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
                    
                    result_image = image.addBands([ndvi])
                    
                    st.session_state.imagen_gee = result_image
                    st.session_state.coleccion_gee = collection
                    
                    return result_image
                
                else:
                    return None
                    
        except Exception as e:
            return None
    
    @staticmethod
    def extraer_estadisticas_gee(geometry, imagen_gee):
        """Extrae estadísticas de índices de vegetación"""
        try:
            if not EE_AVAILABLE or imagen_gee is None:
                return None
            
            import json
            if isinstance(geometry, gpd.GeoDataFrame):
                geojson = json.loads(geometry.to_json())
                gee_geom = ee.Geometry(geojson['features'][0]['geometry'])
            else:
                coords = list(geometry.exterior.coords)
                gee_geom = ee.Geometry.Polygon(coords)
            
            stats = imagen_gee.select('NDVI').reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=gee_geom,
                scale=30,
                maxPixels=1e9
            )
            
            valor = stats.get('NDVI').getInfo()
            
            if valor is not None:
                return float(valor)
            else:
                return None
                
        except Exception as e:
            return None
    
    @staticmethod
    def crear_mapa_ndvi_gee(geometry, imagen_gee):
        """Crea un mapa de NDVI desde GEE"""
        try:
            if not FOLIUM_AVAILABLE or imagen_gee is None:
                return None
            
            centroide = geometry.centroid
            m = folium.Map(location=[centroide.y, centroide.x], zoom_start=12)
            
            esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            folium.TileLayer(
                esri_imagery, 
                attr='Esri',
                name='ESRI Satellite',
                overlay=False,
                max_zoom=19
            ).add_to(m)
            
            return m
            
        except Exception as e:
            return None

# -----------------------
# FUNCIONES DE CARGA
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
            return gdf
            
    except Exception as e:
        return gdf

def procesar_y_unir_poligonos(gdf, unir=True):
    if gdf is None or gdf.empty:
        return gdf
    
    if not unir:
        return gdf
    
    gdf_unido = unir_poligonos_gdf(gdf)
    
    return gdf_unido

# -----------------------
# FUNCIONES DE MAPA
# -----------------------
def crear_mapa_interactivo_esri(gdf):
    """Crea mapa interactivo solo con ESRI Satellite"""
    if not FOLIUM_AVAILABLE or gdf is None or len(gdf) == 0:
        return None
    
    try:
        bounds = gdf.total_bounds
        centroid = gdf.geometry.centroid.iloc[0]
        
        m = folium.Map(
            location=[centroid.y, centroid.x], 
            zoom_start=14,
            tiles=None, 
            control_scale=True,
            control_size=30
        )
        
        esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
        folium.TileLayer(
            esri_imagery, 
            attr='Esri, Maxar, Earthstar Geographics',
            name='ESRI Satellite',
            overlay=False,
            max_zoom=19
        ).add_to(m)
        
        folium.GeoJson(
            gdf.__geo_interface__, 
            name='Potrero',
            style_function=lambda feat: {
                'fillColor': '#00a8ff',
                'color': '#00a8ff',
                'weight': 3,
                'fillOpacity': 0.4,
                'dashArray': '5, 5'
            }
        ).add_to(m)
        
        if len(gdf) > 0:
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(50, 50))
        
        folium.LayerControl(position='topright', collapsed=True).add_to(m)
        
        folium.Marker(
            [centroid.y, centroid.x],
            popup=folium.Popup(
                f"""
                <div style="font-family: Arial; font-size: 14px;">
                <b>Centro del Potrero</b><br>
                Lat: {centroid.y:.6f}<br>
                Lon: {centroid.x:.6f}<br>
                Área: {gdf['area_ha'].sum() if 'area_ha' in gdf.columns else 'N/A'} ha
                </div>
                """,
                max_width=300
            ),
            tooltip="Centro del potrero",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        m.add_child(folium.plugins.Fullscreen())
        
        return m
        
    except Exception as e:
        return None

# -----------------------
# ANÁLISIS FORRAJERO
# -----------------------
class AnalisisForrajeroAvanzado:
    """Clase para análisis forrajero con clima y suelo"""
    
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
    
    def clasificar_vegetacion(self, ndvi):
        """Clasificación de vegetación según NDVI"""
        if ndvi < 0.10:
            categoria = "SUELO_DESNUDO"
            cobertura = 0.05
        elif ndvi < 0.20:
            categoria = "SUELO_PARCIAL"
            cobertura = 0.25
        elif ndvi < 0.40:
            categoria = "VEGETACION_ESCASA"
            cobertura = 0.5
        elif ndvi < 0.65:
            categoria = "VEGETACION_MODERADA"
            cobertura = 0.75
        else:
            categoria = "VEGETACION_DENSA"
            cobertura = 0.9
        
        return categoria, cobertura
    
    def calcular_biomasa(self, ndvi, categoria, cobertura, params):
        """Cálculo de biomasa"""
        base = params['MS_POR_HA_OPTIMO']
        
        if categoria == "SUELO_DESNUDO":
            biomasa_base = 20
            crecimiento_base = 1
        elif categoria == "SUELO_PARCIAL":
            biomasa_base = min(base * 0.05, 200)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.2
        elif categoria == "VEGETACION_ESCASA":
            biomasa_base = min(base * 0.3, 1200)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.4
        elif categoria == "VEGETACION_MODERADA":
            biomasa_base = min(base * 0.6, 3000)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.7
        else:
            biomasa_base = min(base * 0.9, 6000)
            crecimiento_base = params['CRECIMIENTO_DIARIO'] * 0.9
        
        biomasa_final = biomasa_base * cobertura
        crecimiento_final = crecimiento_base * cobertura
        
        if categoria == "SUELO_DESNUDO":
            biomasa_disponible = 20
        elif categoria == "SUELO_PARCIAL":
            biomasa_disponible = 80
        else:
            biomasa_disponible = max(20, min(base * 0.9, biomasa_final * cobertura))
        
        return biomasa_final, crecimiento_final, biomasa_disponible

# -----------------------
# PARÁMETROS FORRAJEROS
# -----------------------
PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 5000, 
        'CRECIMIENTO_DIARIO': 100, 
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'PROTEINA': 18.0,
        'FIBRA': 30.0,
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 4500, 
        'CRECIMIENTO_DIARIO': 90, 
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'PROTEINA': 16.0,
        'FIBRA': 28.0,
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 4000, 
        'CRECIMIENTO_DIARIO': 70, 
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'PROTEINA': 14.0,
        'FIBRA': 32.0,
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3500, 
        'CRECIMIENTO_DIARIO': 60, 
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'PROTEINA': 12.0,
        'FIBRA': 35.0,
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 3000, 
        'CRECIMIENTO_DIARIO': 40, 
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'PROTEINA': 10.0,
        'FIBRA': 40.0,
    },
    'MEZCLA_LEGUMINOSAS': {
        'MS_POR_HA_OPTIMO': 4200, 
        'CRECIMIENTO_DIARIO': 85, 
        'CONSUMO_PORCENTAJE_PESO': 0.027,
        'TASA_UTILIZACION_RECOMENDADA': 0.58,
        'PROTEINA': 17.0,
        'FIBRA': 29.0,
    }
}

def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'PROTEINA': 15.0,
            'FIBRA': 30.0,
        }
    else:
        return PARAMETROS_FORRAJEROS.get(
            tipo_pastura, 
            PARAMETROS_FORRAJEROS['PASTIZAL_NATURAL']
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

def dividir_potrero_en_sublotes(gdf, n_zonas):
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
                    'id_sublote': len(lista_potreros) + 1,
                    'geometry': sub_poly
                })
    
    if lista_potreros:
        nuevo = gpd.GeoDataFrame(lista_potreros)
        nuevo.crs = gdf.crs
        return nuevo
    return gdf

def simular_indices(id_sublote):
    """Simulación de índices de vegetación"""
    base = 0.2 + 0.4 * ((id_sublote % 6) / 6)
    ndvi = max(0.05, min(0.85, base + np.random.normal(0, 0.05)))
    evi = ndvi * 1.1
    savi = ndvi * 1.05
    
    return ndvi, evi, savi

def calcular_metricas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Cálculo de métricas ganaderas"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row.get('biomasa_disponible_kg_ms_ha', 0)
        area_ha = row.get('area_ha', 0)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        # Cálculo de EV soportable
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01
        
        # Días de permanencia
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(max(dias_permanencia, 0.1), 365)
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1
        
        # Estado forrajero
        if biomasa_disponible >= 2500:
            estado_forrajero = 5
        elif biomasa_disponible >= 1800:
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
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'produccion_diaria_kg': round(row.get('crecimiento_diario', 0) * area_ha, 1),
            'consumo_diario_kg': round(carga_animal * consumo_individual_kg, 1),
        })
    
    return metricas

# -----------------------
# DASHBOARD RESUMEN
# -----------------------
def crear_dashboard_resumen(gdf_analizado, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio):
    """Crea un dashboard resumen completo"""
    
    area_total = gdf_analizado['area_ha'].sum()
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = (gdf_analizado['biomasa_disponible_kg_ms_ha'] * gdf_analizado['area_ha']).sum()
    ndvi_promedio = gdf_analizado['ndvi'].mean()
    ev_total = gdf_analizado['ev_soportable'].sum()
    dias_promedio = gdf_analizado['dias_permanencia'].mean()
    
    st.markdown("---")
    st.markdown("## 📊 DASHBOARD RESUMEN")
    
    # Métricas clave
    st.markdown("### 📈 MÉTRICAS CLAVE")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Área Total", f"{area_total:.1f} ha")
        st.caption("Superficie analizada")
    
    with col2:
        st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
        st.caption("Productividad forrajera")
    
    with col3:
        st.metric("EV Soportable", f"{ev_total:.1f}")
        st.caption("Capacidad de carga total")
    
    with col4:
        st.metric("NDVI Promedio", f"{ndvi_promedio:.3f}")
        st.caption("Estado vegetativo")
    
    # Balance forrajero
    st.markdown("### 🌿 BALANCE FORRAJERO")
    col5, col6, col7 = st.columns(3)
    
    with col5:
        biomasa_ha_dia = gdf_analizado['crecimiento_diario'].mean()
        st.metric("Crecimiento Diario", f"{biomasa_ha_dia:.0f} kg/ha/día")
        st.caption("Producción diaria")
    
    with col6:
        consumo_total = carga_animal * peso_promedio * 0.025
        st.metric("Consumo Diario", f"{consumo_total:.0f} kg MS/día")
        st.caption("Demanda ganadera")
    
    with col7:
        balance_diario = biomasa_ha_dia * area_total - consumo_total
        st.metric("Balance Diario", f"{balance_diario:.0f} kg MS/día")
        st.caption("Saldo producción-consumo")
    
    # Distribución de superficies
    st.markdown("### 🗺️ DISTRIBUCIÓN DE SUPERFICIES")
    
    if 'tipo_superficie' in gdf_analizado.columns:
        distribucion = gdf_analizado['tipo_superficie'].value_counts()
        
        if len(distribucion) > 0:
            col8, col9 = st.columns(2)
            
            with col8:
                fig1, ax1 = plt.subplots(figsize=(6, 4))
                colors = ['#d73027', '#fdae61', '#fee08b', '#a6d96a', '#1a9850']
                ax1.pie(
                    distribucion.values, 
                    labels=distribucion.index,
                    autopct='%1.1f%%',
                    colors=colors[:len(distribucion)],
                    startangle=90
                )
                ax1.set_title('Distribución de Tipos de Superficie')
                st.pyplot(fig1)
                plt.close(fig1)
            
            with col9:
                st.dataframe(
                    pd.DataFrame({
                        'Tipo de Superficie': distribucion.index,
                        'Sub-lotes': distribucion.values,
                        'Porcentaje': (distribucion.values / len(gdf_analizado) * 100).round(1)
                    }),
                    use_container_width=True,
                    hide_index=True
                )
    
    # Datos ambientales
    st.markdown("### 🌤️ DATOS AMBIENTALES")
    
    if datos_clima or datos_suelo:
        col10, col11 = st.columns(2)
        
        with col10:
            if datos_clima:
                st.markdown("**🌤️ Datos Climáticos**")
                clima_df = pd.DataFrame({
                    'Métrica': [
                        'Precipitación Total',
                        'Temp. Máx. Promedio',
                        'Temp. Mín. Promedio',
                        'Días con Lluvia'
                    ],
                    'Valor': [
                        f"{datos_clima.get('precipitacion_total', 0):.0f} mm",
                        f"{datos_clima.get('temp_max_promedio', 0):.1f} °C",
                        f"{datos_clima.get('temp_min_promedio', 0):.1f} °C",
                        f"{datos_clima.get('dias_lluvia', 0)} días"
                    ]
                })
                st.dataframe(clima_df, use_container_width=True, hide_index=True)
        
        with col11:
            if datos_suelo:
                st.markdown("**🌍 Datos de Suelo**")
                suelo_df = pd.DataFrame({
                    'Característica': [
                        'Textura',
                        'Materia Orgánica',
                        'pH',
                        'Profundidad'
                    ],
                    'Valor': [
                        datos_suelo.get('textura', 'N/A'),
                        f"{datos_suelo.get('materia_organica', 0):.1f} %",
                        f"{datos_suelo.get('ph', 0):.1f}",
                        f"{datos_suelo.get('profundidad', 0):.0f} cm"
                    ]
                })
                st.dataframe(suelo_df, use_container_width=True, hide_index=True)
    
    return {
        'area_total': area_total,
        'biomasa_promedio': biomasa_promedio,
        'biomasa_total': biomasa_total,
        'ndvi_promedio': ndvi_promedio,
        'ev_total': ev_total,
        'dias_promedio': dias_promedio
    }

# -----------------------
# GENERADOR DE INFORME
# -----------------------
def generar_informe_completo(gdf_analizado, datos_clima, datos_suelo, tipo_pastura, 
                            carga_animal, peso_promedio, dashboard_metrics, 
                            fecha_imagen, n_divisiones, params):
    """Genera un informe DOCX completo"""
    
    if not DOCX_AVAILABLE:
        return None
    
    try:
        doc = Document()
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        # Título
        title = doc.add_heading('INFORME DE ANÁLISIS FORRAJERO', 0)
        title.alignment = 1
        
        doc.add_paragraph(f"Fecha de generación: {fecha_actual}")
        doc.add_paragraph(f"Fecha de imagen satelital: {fecha_imagen.strftime('%d/%m/%Y')}")
        doc.add_paragraph("")
        
        # Resumen ejecutivo
        doc.add_heading('1. RESUMEN EJECUTIVO', level=1)
        resumen_text = f"""
        Este informe presenta los resultados del análisis forrajero avanzado.
        Tipo de pastura: {tipo_pastura}
        Área total analizada: {dashboard_metrics['area_total']:.1f} ha
        Biomasa promedio: {dashboard_metrics['biomasa_promedio']:.0f} kg MS/ha
        EV total soportable: {dashboard_metrics['ev_total']:.1f}
        NDVI promedio: {dashboard_metrics['ndvi_promedio']:.3f}
        Días de permanencia promedio: {dashboard_metrics['dias_promedio']:.1f} días
        Sub-lotes creados: {n_divisiones}
        Carga animal considerada: {carga_animal} cabezas
        Peso promedio: {peso_promedio} kg
        """
        doc.add_paragraph(resumen_text)
        
        # Parámetros de análisis
        doc.add_heading('2. PARÁMETROS DE ANÁLISIS', level=1)
        table_params = doc.add_table(rows=1, cols=2)
        hdr_cells = table_params.rows[0].cells
        hdr_cells[0].text = 'Parámetro'
        hdr_cells[1].text = 'Valor'
        
        parametros_data = [
            ('Tipo de Pastura', tipo_pastura),
            ('MS Óptimo', f"{params['MS_POR_HA_OPTIMO']} kg/ha"),
            ('Crecimiento Diario', f"{params['CRECIMIENTO_DIARIO']} kg/ha/día"),
            ('Consumo (% peso)', f"{params['CONSUMO_PORCENTAJE_PESO']*100:.1f}%"),
            ('Carga Animal', f"{carga_animal} cabezas"),
            ('Peso Promedio', f"{peso_promedio} kg"),
            ('Sub-lotes', f"{n_divisiones}")
        ]
        
        for param, valor in parametros_data:
            row_cells = table_params.add_row().cells
            row_cells[0].text = param
            row_cells[1].text = str(valor)
        
        # Recomendaciones
        doc.add_heading('3. RECOMENDACIONES', level=1)
        
        recomendaciones = []
        biomasa_prom = dashboard_metrics['biomasa_promedio']
        
        if biomasa_prom < 600:
            recomendaciones.append("🔴 **CRÍTICO**: Biomasa muy baja. Considerar suplementación inmediata.")
        elif biomasa_prom < 1200:
            recomendaciones.append("🟡 **ALERTA**: Biomasa baja. Monitorear diariamente.")
        elif biomasa_prom < 1800:
            recomendaciones.append("🟢 **ACEPTABLE**: Biomasa moderada. Mantener manejo actual.")
        else:
            recomendaciones.append("✅ **ÓPTIMO**: Biomasa adecuada. Buen crecimiento.")
        
        dias_prom = dashboard_metrics['dias_promedio']
        if dias_prom < 15:
            recomendaciones.append("⚡ **ROTACIÓN MUY RÁPIDA**: Considerar aumentar área o reducir carga.")
        elif dias_prom > 60:
            recomendaciones.append("🐌 **ROTACIÓN LENTA**: Podría aumentar carga animal.")
        
        for rec in recomendaciones:
            doc.add_paragraph(rec)
        
        # Plan de acción
        doc.add_heading('4. PLAN DE ACCIÓN', level=1)
        plan_accion = [
            ("INMEDIATO (1-7 días)", [
                "Verificar estado actual del ganado",
                "Revisar disponibilidad de agua",
                "Ajustar carga animal según resultados"
            ]),
            ("CORTO PLAZO (8-30 días)", [
                "Implementar rotación de potreros",
                "Monitorear crecimiento forrajero",
                "Evaluar necesidad de fertilización"
            ])
        ]
        
        for periodo, acciones in plan_accion:
            doc.add_heading(periodo, level=2)
            for accion in acciones:
                doc.add_paragraph(f"• {accion}", style='List Bullet')
        
        # Guardar documento
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        return buffer
        
    except Exception as e:
        return None

# -----------------------
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# -----------------------
def ejecutar_analisis_completo(gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                              umbral_ndvi_minimo, umbral_ndvi_optimo, usar_clima=True, 
                              usar_suelo=True, fecha_inicio_clima=None, fecha_fin_clima=None):
    """Ejecuta análisis forrajero completo"""
    
    try:
        # Obtener datos climáticos y de suelo
        datos_clima_global = None
        datos_suelo_global = None
        imagen_gee = None
        
        if usar_clima and fecha_inicio_clima and fecha_fin_clima:
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_clima_global = ServicioClimaNASA.obtener_datos_climaticos(
                lat=centroid.y,
                lon=centroid.x,
                fecha_inicio=fecha_inicio_clima,
                fecha_fin=fecha_fin_clima
            )
        
        if usar_suelo:
            centroid = gdf_sub.geometry.unary_union.centroid
            datos_suelo_global = ServicioSuelosINTA.obtener_caracteristicas_suelo(
                lat=centroid.y,
                lon=centroid.x
            )
        
        # Obtener imagen de GEE si está seleccionado
        if "GEE" in fuente_satelital and st.session_state.get('gee_authenticated', False):
            imagen_gee = ServicioGoogleEarthEngine.obtener_imagen_gee(
                geometry=gdf_sub,
                fecha_inicio=fecha_imagen - timedelta(days=30),
                fecha_fin=fecha_imagen + timedelta(days=15),
                fuente_satelital=fuente_satelital,
                nubes_max=nubes_max
            )
        
        # Inicializar analizador
        analizador = AnalisisForrajeroAvanzado(
            umbral_ndvi_minimo=umbral_ndvi_minimo,
            umbral_ndvi_optimo=umbral_ndvi_optimo
        )
        
        params = obtener_parametros_forrajeros(tipo_pastura)
        resultados = []
        
        st.info("🔍 Analizando sub-lotes...")
        
        for idx, row in gdf_sub.iterrows():
            id_sublote = row.get('id_sublote', idx + 1)
            
            # Obtener índices según la fuente de datos
            if imagen_gee and "GEE" in fuente_satelital:
                ndvi = ServicioGoogleEarthEngine.extraer_estadisticas_gee(row.geometry, imagen_gee)
                if ndvi is None:
                    ndvi, evi, savi = simular_indices(id_sublote)
                else:
                    evi = ndvi * 1.1
                    savi = ndvi * 1.05
            else:
                ndvi, evi, savi = simular_indices(id_sublote)
            
            # Clasificar vegetación
            categoria, cobertura = analizador.clasificar_vegetacion(ndvi)
            
            # Calcular biomasa
            biomasa_ms_ha, crecimiento_diario, biomasa_disponible = analizador.calcular_biomasa(
                ndvi, categoria, cobertura, params
            )
            
            resultados.append({
                'id_sublote': id_sublote,
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'cobertura_vegetal': round(cobertura, 3),
                'tipo_superficie': categoria,
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'fuente_datos': fuente_satelital,
                'usando_gee': "GEE" in fuente_satelital and imagen_gee is not None
            })
        
        st.success("✅ Análisis completado.")
        return resultados, datos_clima_global, datos_suelo_global, imagen_gee
        
    except Exception as e:
        st.error(f"❌ Error en análisis: {e}")
        return [], None, None, None

# -----------------------
# FLUJO PRINCIPAL
# -----------------------
st.markdown("### 📁 Cargar y visualizar lote")
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
                gdf_procesado = procesar_y_unir_poligonos(gdf_loaded, unir_poligonos)
                
                if gdf_procesado is not None and len(gdf_procesado) > 0:
                    st.session_state.gdf_cargado = gdf_procesado
                    
                    areas = calcular_superficie(gdf_procesado)
                    gdf_procesado['area_ha'] = areas.values
                    area_total = gdf_procesado['area_ha'].sum()
                    
                    st.success("✅ Archivo cargado correctamente.")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1: 
                        st.metric("Polígonos", len(gdf_procesado))
                    with col2: st.metric("Área total (ha)", f"{area_total:.2f}")
                    with col3: st.metric("Tipo pastura", tipo_pastura)
                    with col4: 
                        st.metric("Clima", "NASA POWER" if usar_clima else "No")
                    
                    if FOLIUM_AVAILABLE:
                        st.markdown("---")
                        st.markdown("### 🗺️ Visualización del potrero")
                        mapa_interactivo = crear_mapa_interactivo_esri(gdf_procesado)
                        if mapa_interactivo:
                            st_folium(mapa_interactivo, width=1200, height=500)
                    else:
                        st.info("Instala folium para ver el mapa interactivo")
                else:
                    st.info("Carga completada pero no se detectaron geometrías válidas.")
            else:
                st.info("Carga completada pero no se detectaron geometrías válidas.")
        except Exception as e:
            st.error(f"❌ Error al cargar archivo: {e}")

st.markdown("---")
st.markdown("### 🚀 Ejecutar análisis completo")

# SI YA HAY ANÁLISIS EN SESSION_STATE, MOSTRAR LOS RESULTADOS
if st.session_state.gdf_analizado is not None:
    gdf_sub = st.session_state.gdf_analizado
    datos_clima = st.session_state.datos_clima
    datos_suelo = st.session_state.datos_suelo
    tipo_pastura = st.session_state.get('tipo_pastura_guardado', tipo_pastura)
    carga_animal = st.session_state.get('carga_animal_guardada', carga_animal)
    peso_promedio = st.session_state.get('peso_promedio_guardado', peso_promedio)
    
    # Mostrar información de GEE si está disponible
    if st.session_state.get('usando_gee', False):
        st.success("✅ Análisis realizado con datos satelitales de Google Earth Engine")
    
    # Crear y mostrar dashboard resumen
    st.markdown("---")
    params = obtener_parametros_forrajeros(tipo_pastura)
    dashboard_metrics = crear_dashboard_resumen(
        gdf_sub, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio
    )
    
    # Mostrar datos climáticos detallados
    if datos_clima:
        with st.expander("📊 DATOS CLIMÁTICOS DETALLADOS"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**🌡️ Temperaturas**")
                temp_data = pd.DataFrame({
                    'Métrica': ['Máxima Promedio', 'Mínima Promedio'],
                    'Valor (°C)': [
                        datos_clima.get('temp_max_promedio', 0),
                        datos_clima.get('temp_min_promedio', 0)
                    ]
                })
                st.dataframe(temp_data, use_container_width=True, hide_index=True)
            
            with col2:
                st.markdown("**💧 Precipitación**")
                agua_data = pd.DataFrame({
                    'Métrica': ['Precipitación Total', 'Días con Lluvia'],
                    'Valor': [
                        f"{datos_clima.get('precipitacion_total', 0)} mm",
                        f"{datos_clima.get('dias_lluvia', 0)} días"
                    ]
                })
                st.dataframe(agua_data, use_container_width=True, hide_index=True)
    
    # Exportar datos
    st.markdown("---")
    st.markdown("### 💾 EXPORTAR DATOS")
    
    col_export1, col_export2, col_export3 = st.columns(3)
    
    with col_export1:
        try:
            geojson_str = gdf_sub.to_json()
            st.download_button(
                "📤 Exportar GeoJSON",
                geojson_str,
                f"analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                "application/geo+json",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error exportando GeoJSON: {e}")
    
    with col_export2:
        try:
            csv_data = gdf_sub.drop(columns=['geometry']).copy()
            csv_bytes = csv_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📊 Exportar CSV completo",
                csv_bytes,
                f"analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error exportando CSV: {e}")
    
    with col_export3:
        if DOCX_AVAILABLE:
            generar_informe = st.button(
                "📑 Generar Informe (DOCX)", 
                use_container_width=True,
                key="generar_informe_btn"
            )
            
            if generar_informe:
                with st.spinner("Generando informe..."):
                    informe_buffer = generar_informe_completo(
                        gdf_sub, datos_clima, datos_suelo, tipo_pastura,
                        carga_animal, peso_promedio, dashboard_metrics,
                        fecha_imagen, n_divisiones, params
                    )
                    
                    if informe_buffer:
                        st.session_state.informe_generado = informe_buffer
                        st.success("✅ Informe generado correctamente.")
            
            if st.session_state.informe_generado is not None:
                st.download_button(
                    "📥 Descargar Informe",
                    st.session_state.informe_generado,
                    f"informe_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key="descargar_informe"
                )
            else:
                st.info("Presiona 'Generar Informe'")
        else:
            st.warning("python-docx no disponible")
    
    # Mostrar tabla de resultados
    st.markdown("---")
    st.markdown("### 📋 TABLA DE RESULTADOS")
    
    columnas_detalle = ['id_sublote', 'area_ha', 'tipo_superficie', 'ndvi', 
                       'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha',
                       'ev_soportable', 'dias_permanencia']
    cols_presentes = [c for c in columnas_detalle if c in gdf_sub.columns]
    
    df_show = gdf_sub[cols_presentes].copy()
    df_show.columns = [c.replace('_', ' ').title() for c in df_show.columns]
    
    st.dataframe(df_show, use_container_width=True, height=400)
    
    st.success("🎉 ¡Análisis completado exitosamente!")

# SI NO HAY ANÁLISIS PERO SÍ HAY ARCHIVO CARGADO
elif st.session_state.gdf_cargado is not None:
    if st.button("🚀 Ejecutar Análisis Completo", type="primary", use_container_width=True):
        with st.spinner("Ejecutando análisis..."):
            try:
                gdf_input = st.session_state.gdf_cargado.copy()
                
                # Dividir en sub-lotes
                gdf_sub = dividir_potrero_en_sublotes(gdf_input, n_divisiones)
                
                if gdf_sub is None or len(gdf_sub) == 0:
                    st.error("No se pudo dividir el potrero en sub-lotes.")
                else:
                    # Calcular áreas
                    areas = calcular_superficie(gdf_sub)
                    gdf_sub['area_ha'] = areas.values
                    
                    st.success(f"✅ División completada: {len(gdf_sub)} sub-lotes creados")
                    
                    # Ejecutar análisis
                    resultados, datos_clima, datos_suelo, imagen_gee = ejecutar_analisis_completo(
                        gdf_sub, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                        umbral_ndvi_minimo, umbral_ndvi_optimo, usar_clima, usar_suelo,
                        fecha_imagen - timedelta(days=60), fecha_imagen
                    )
                    
                    if not resultados:
                        st.error("No se pudieron calcular índices.")
                    else:
                        # Asignar resultados
                        for idx, rec in enumerate(resultados):
                            for k, v in rec.items():
                                if k != 'id_sublote':
                                    try:
                                        gdf_sub.loc[gdf_sub.index[idx], k] = v
                                    except Exception:
                                        pass
                        
                        # Calcular métricas
                        metricas = calcular_metricas(gdf_sub, tipo_pastura, peso_promedio, carga_animal)
                        
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
                        st.session_state.imagen_gee = imagen_gee
                        st.session_state.usando_gee = "GEE" in fuente_satelital and imagen_gee is not None
                        st.session_state.tipo_pastura_guardado = tipo_pastura
                        st.session_state.carga_animal_guardada = carga_animal
                        st.session_state.peso_promedio_guardado = peso_promedio
                        
                        st.rerun()
                        
            except Exception as e:
                st.error(f"❌ Error ejecutando análisis: {e}")

# SI NO HAY NADA CARGADO
else:
    st.info("""
    ### 👋 Bienvenido al Sistema de Gestión Forrajera
    
    **Para comenzar:**
    1. 📤 Sube un archivo espacial (ZIP con shapefile, KML o KMZ)
    2. ⚙️ Configura los parámetros en la barra lateral
    3. 🚀 Ejecuta el análisis completo
    
    **Características principales:**
    - 🛰️ Datos satelitales reales de Google Earth Engine
    - 🌤️ Información climática de NASA POWER
    - 🌍 Datos de suelos del INTA
    - 📊 Análisis avanzado de biomasa forrajera
    - 🗺️ Mapas interactivos con ESRI Satellite
    - 📑 Informes completos en formato DOCX
    
    **Soporte técnico:**
    - Soporte para múltiples formatos espaciales
    - Conexión automática a GEE
    - Fallback a datos simulados si es necesario
    - Interfaz intuitiva y responsive
    """)
    
    # Mostrar información de estado de servicios
    with st.expander("🔧 Estado de los servicios"):
        col1, col2, col3 = st.columns(3)
        with col1:
            if EE_AVAILABLE and st.session_state.get('gee_authenticated', False):
                st.success("✅ Google Earth Engine")
            else:
                st.warning("⚠️ Google Earth Engine")
        with col2:
            st.info("🌤️ NASA POWER API")
        with col3:
            st.info("🌍 INTA Suelos")

# -----------------------
# INFORMACIÓN ADICIONAL
# -----------------------
st.markdown("---")
st.markdown("### 📚 INFORMACIÓN ADICIONAL")

with st.expander("ℹ️ Acerca del sistema"):
    st.markdown("""
    #### 🛰️ Google Earth Engine (GEE)
    - **Plataforma**: Análisis geoespacial en la nube
    - **Datos disponibles**: Sentinel-2, Landsat 8/9, MODIS
    - **Resolución**: 10m a 30m según satélite
    - **Actualización**: 5 a 16 días según satélite
    
    #### 🔐 Configuración GEE para producción:
    1. **Streamlit Cloud**: Agregar credenciales en Secrets
    2. **Local**: Ejecutar `ee.Authenticate()` una vez
    3. **Sin GEE**: Usar opción 'SIMULADO'
    
    #### 🎯 Métricas calculadas:
    - **NDVI**: Índice de vegetación normalizado
    - **Biomasa disponible**: kg MS/ha
    - **EV soportable**: Equivalentes vacunos
    - **Días de permanencia**: Duración estimada
    - **Balance forrajero**: Producción vs consumo
    
    #### 📊 Salidas generadas:
    - Mapas interactivos con ESRI Satellite
    - Dashboard con métricas clave
    - Tablas de resultados detallados
    - Informes completos en DOCX
    - Archivos GeoJSON y CSV
    """)

with st.expander("🎯 Guía de uso"):
    st.markdown("""
    **Paso a paso:**
    
    1. **Configuración inicial**
       - Selecciona fuente satelital
       - Define tipo de pastura
       - Configura parámetros ganaderos
    
    2. **Carga de datos**
       - Sube tu archivo espacial
       - Verifica la visualización
       - Ajusta parámetros si es necesario
    
    3. **Análisis**
       - Ejecuta el análisis completo
       - Revisa el dashboard de resultados
       - Explora los mapas interactivos
    
    4. **Exportación**
       - Descarga resultados en múltiples formatos
       - Genera informes profesionales
       - Comparte los resultados
    
    **Consejos:**
    - Para mayor precisión, usa datos reales de GEE
    - Valida resultados con observaciones de campo
    - Realiza análisis periódicos para seguimiento
    - Consulta las recomendaciones generadas
    """)

# Pie de página
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px;'>
    <p>Sistema de Gestión Forrajera | Versión 3.0 | 🛰️ Google Earth Engine | 🌤️ NASA POWER | 🌍 INTA</p>
    <p>© 2024 - Desarrollado para productores agropecuarios</p>
</div>
""", unsafe_allow_html=True)
