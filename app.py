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
import requests
import json
from typing import Dict, Optional
import warnings
warnings.filterwarnings('ignore')

# ================ CONFIGURACIÓN CRÍTICA DE GEE ================
import sys
import subprocess
import pkgutil

# Verificar e instalar earthengine-api si no está disponible
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    st.warning("⚠️ Instalando Google Earth Engine API...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "earthengine-api"])
        import ee
        GEE_AVAILABLE = True
        st.success("✅ Google Earth Engine instalado correctamente")
    except:
        GEE_AVAILABLE = False
        st.error("❌ No se pudo instalar Google Earth Engine")

# ================ INICIALIZACIÓN GEE CON SERVICE ACCOUNT ================
def inicializar_gee_con_service_account():
    """Inicializa GEE usando Service Account desde secrets"""
    if not GEE_AVAILABLE:
        return False
    
    try:
        # Intentar inicializar primero (por si ya está autenticado)
        ee.Initialize()
        st.session_state.gee_authenticated = True
        st.success("✅ GEE inicializado (ya autenticado)")
        return True
    except Exception as e:
        try:
            # Método 1: Intentar con Service Account desde secrets
            import os
            
            # Verificar si hay credenciales en secrets
            service_account_json = os.environ.get('GEE_SERVICE_ACCOUNT')
            
            if service_account_json:
                # Parsear JSON
                service_account_info = json.loads(service_account_json)
                
                # Crear credenciales de Service Account
                credentials = ee.ServiceAccountCredentials(
                    email=service_account_info['client_email'],
                    key_data=service_account_json
                )
                
                # Inicializar con credenciales
                ee.Initialize(credentials)
                st.session_state.gee_authenticated = True
                st.success("✅ GEE inicializado con Service Account")
                return True
            else:
                # Método 2: Intentar inicialización normal (puede fallar en Streamlit Cloud)
                ee.Initialize()
                st.session_state.gee_authenticated = True
                st.success("✅ GEE inicializado sin credenciales")
                return True
                
        except Exception as e2:
            st.error(f"❌ Error crítico inicializando GEE: {str(e2)}")
            st.info("""
            ### 🔧 CONFIGURACIÓN REQUERIDA PARA GOOGLE EARTH ENGINE
            
            **Para usar datos satelitales reales, debes configurar:**
            
            1. **Crear una cuenta de servicio en Google Cloud Console:**
               - Ve a https://console.cloud.google.com/
               - Crea un proyecto nuevo o selecciona uno existente
               - Ve a "IAM y administración" → "Cuentas de servicio"
               - Crea una nueva cuenta de servicio
            
            2. **Habilitar Earth Engine API:**
               - En la misma cuenta, ve a "APIs y servicios" → "Biblioteca"
               - Busca "Earth Engine API" y habilítala
            
            3. **Generar credenciales:**
               - Ve a "Claves" en la cuenta de servicio
               - Crea una nueva clave JSON
               - Descarga el archivo JSON
            
            4. **Configurar en Streamlit Cloud:**
               - En tu app, ve a Settings → Secrets
               - Agrega:
                 ```
                 GEE_SERVICE_ACCOUNT = '{"type": "service_account", "project_id": "...", "private_key_id": "...", ...}'
                 ```
               - Pega TODO el contenido del JSON
            
            **O usa datos simulados temporalmente.**
            """)
            st.session_state.gee_authenticated = False
            return False

# Intentar inicializar GEE al cargar
if GEE_AVAILABLE and 'gee_authenticated' not in st.session_state:
    inicializar_gee_con_service_account()

# ================ CONFIGURACIÓN STREAMLIT ================
st.set_page_config(
    page_title="🌱 Sistema de Análisis Forrajero con GEE",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.8rem;
        color: #1B5E20;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: 700;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #388E3C;
        text-align: center;
        margin-bottom: 2rem;
    }
    .info-box {
        background-color: #E8F5E9;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #4CAF50;
    }
    .warning-box {
        background-color: #FFF3E0;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #FF9800;
    }
    .metric-box {
        background-color: #F5F5F5;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        border: 1px solid #E0E0E0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🌱 ANÁLISIS FORRAJERO AVANZADO CON GOOGLE EARTH ENGINE</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Sistema profesional de monitoreo de biomasa y gestión ganadera con datos satelitales reales</p>', unsafe_allow_html=True)

# ================ SESSION STATE ================
if 'gee_authenticated' not in st.session_state:
    st.session_state.gee_authenticated = False
if 'imagen_gee' not in st.session_state:
    st.session_state.imagen_gee = None
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'datos_clima' not in st.session_state:
    st.session_state.datos_clima = None

# ================ BARRA LATERAL ================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/satellite.png", width=80)
    
    st.markdown("### ⚙️ CONFIGURACIÓN PRINCIPAL")
    
    # Estado de GEE
    st.markdown("#### 🔌 ESTADO DE CONEXIÓN")
    if st.session_state.gee_authenticated:
        st.success("✅ **GEE CONECTADO**")
        st.caption("Datos satelitales reales disponibles")
    else:
        st.error("❌ **GEE NO CONECTADO**")
        st.caption("Se usarán datos simulados")
    
    # Selección de fuente de datos
    st.markdown("#### 🛰️ FUENTE DE DATOS")
    fuente_opciones = ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"]
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        fuente_opciones,
        index=3 if not st.session_state.gee_authenticated else 0
    )
    
    if "SIMULADO" not in fuente_satelital and not st.session_state.gee_authenticated:
        st.warning("⚠️ Necesitas GEE para datos reales")
    
    # Tipo de pastura
    st.markdown("#### 🌿 TIPO DE PASTURA")
    tipo_pastura = st.selectbox(
        "Seleccionar:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "MEZCLA_LEGUMINOSAS", "PERSONALIZADO"]
    )
    
    # Parámetros temporales
    st.markdown("#### 📅 PERÍODO DE ANÁLISIS")
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Inicio:", datetime.now() - timedelta(days=60))
    with col2:
        fecha_fin = st.date_input("Fin:", datetime.now())
    
    # Parámetros ganaderos
    st.markdown("#### 🐄 PARÁMETROS GANADEROS")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal:", 1, 1000, 100)
    
    # Número de divisiones
    st.markdown("#### 🔪 DIVISIÓN DE POTRERO")
    n_divisiones = st.slider("Sub-lotes:", 4, 100, 16)
    
    # Carga de archivo
    st.markdown("#### 📤 CARGA DE ARCHIVO")
    tipo_archivo = st.radio("Formato:", ["Shapefile (ZIP)", "KML", "KMZ"], horizontal=True)
    
    uploaded_file = st.file_uploader(
        "Subir archivo del potrero",
        type=['zip'] if tipo_archivo == "Shapefile (ZIP)" else ['kml', 'kmz'],
        key="file_uploader"
    )
    
    # Botón para inicializar GEE
    st.markdown("---")
    if not st.session_state.gee_authenticated and GEE_AVAILABLE:
        if st.button("🔑 INICIALIZAR GOOGLE EARTH ENGINE", type="primary", use_container_width=True):
            with st.spinner("Inicializando GEE..."):
                if inicializar_gee_con_service_account():
                    st.rerun()
    
    # Información de ayuda
    with st.expander("ℹ️ Ayuda rápida"):
        st.markdown("""
        **Para datos satelitales reales:**
        1. Configura una Service Account
        2. Agrega credenciales en Secrets
        3. Usa Sentinel-2 o Landsat
        
        **Formatos soportados:**
        - Shapefile (comprimido en ZIP)
        - KML (Google Earth)
        - KMZ (KML comprimido)
        
        **Resolución:**
        - Sentinel-2: 10m
        - Landsat-8/9: 30m
        """)

# ================ CLASE GEE MEJORADA ================
class GoogleEarthEngineService:
    """Servicio mejorado para Google Earth Engine"""
    
    @staticmethod
    def obtener_imagen_sentinel2(geometry, fecha_inicio, fecha_fin, nubes_max=20):
        """Obtiene imagen Sentinel-2 de GEE"""
        if not st.session_state.gee_authenticated:
            return None
        
        try:
            # Convertir geometría
            if isinstance(geometry, gpd.GeoDataFrame):
                geojson = json.loads(geometry.to_json())
                coords = geojson['features'][0]['geometry']['coordinates']
            else:
                coords = list(geometry.exterior.coords)
            
            # Crear geometría GEE
            gee_geometry = ee.Geometry.Polygon(coords)
            
            # Fechas
            start_date = ee.Date(fecha_inicio.strftime('%Y-%m-%d'))
            end_date = ee.Date(fecha_fin.strftime('%Y-%m-%d'))
            
            # Filtrar colección
            collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                         .filterBounds(gee_geometry)
                         .filterDate(start_date, end_date)
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nubes_max))
                         .sort('CLOUDY_PIXEL_PERCENTAGE'))
            
            # Obtener imagen
            image = collection.first()
            
            if image is None:
                return None
            
            # Calcular NDVI
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            image = image.addBands(ndvi)
            
            return image
            
        except Exception as e:
            st.error(f"Error GEE Sentinel-2: {str(e)}")
            return None
    
    @staticmethod
    def obtener_imagen_landsat(geometry, fecha_inicio, fecha_fin, landsat_version='LANDSAT/LC08/C02/T1_L2'):
        """Obtiene imagen Landsat de GEE"""
        if not st.session_state.gee_authenticated:
            return None
        
        try:
            # Convertir geometría
            if isinstance(geometry, gpd.GeoDataFrame):
                geojson = json.loads(geometry.to_json())
                coords = geojson['features'][0]['geometry']['coordinates']
            else:
                coords = list(geometry.exterior.coords)
            
            gee_geometry = ee.Geometry.Polygon(coords)
            
            # Fechas
            start_date = ee.Date(fecha_inicio.strftime('%Y-%m-%d'))
            end_date = ee.Date(fecha_fin.strftime('%Y-%m-%d'))
            
            # Filtrar colección
            collection = (ee.ImageCollection(landsat_version)
                         .filterBounds(gee_geometry)
                         .filterDate(start_date, end_date)
                         .filter(ee.Filter.lt('CLOUD_COVER', 20))
                         .sort('CLOUD_COVER'))
            
            image = collection.first()
            
            if image is None:
                return None
            
            # Calcular NDVI para Landsat
            if 'LC08' in landsat_version or 'LC09' in landsat_version:
                # Landsat 8/9: B5 = NIR, B4 = Red
                ndvi = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
            else:
                # Landsat antiguos
                ndvi = image.normalizedDifference(['B4', 'B3']).rename('NDVI')
            
            image = image.addBands(ndvi)
            
            return image
            
        except Exception as e:
            st.error(f"Error GEE Landsat: {str(e)}")
            return None
    
    @staticmethod
    def calcular_ndvi_promedio(geometry, imagen_gee):
        """Calcula NDVI promedio para una geometría"""
        if imagen_gee is None:
            return None
        
        try:
            if isinstance(geometry, gpd.GeoDataFrame):
                geojson = json.loads(geometry.to_json())
                coords = geojson['features'][0]['geometry']['coordinates']
            else:
                coords = list(geometry.exterior.coords)
            
            gee_geometry = ee.Geometry.Polygon(coords)
            
            # Calcular estadísticas
            reduccion = imagen_gee.select('NDVI').reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=gee_geometry,
                scale=30,
                maxPixels=1e9
            )
            
            ndvi_promedio = reduccion.get('NDVI').getInfo()
            
            return float(ndvi_promedio) if ndvi_promedio is not None else None
            
        except Exception as e:
            return None

# ================ FUNCIONES DE CARGA ================
def cargar_shapefile_desde_zip(uploaded_zip):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Guardar archivo ZIP
            zip_path = os.path.join(tmp_dir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_zip.getvalue())
            
            # Extraer contenido
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            # Buscar archivo .shp
            shp_files = [f for f in os.listdir(tmp_dir) if f.lower().endswith('.shp')]
            
            if not shp_files:
                # Intentar buscar en subdirectorios
                for root, dirs, files in os.walk(tmp_dir):
                    for file in files:
                        if file.lower().endswith('.shp'):
                            shp_files.append(os.path.join(root, file))
            
            if shp_files:
                shp_path = shp_files[0]
                gdf = gpd.read_file(shp_path)
                
                # Asegurar sistema de coordenadas
                if gdf.crs is None:
                    gdf.set_crs(epsg=4326, inplace=True)
                
                return gdf
            else:
                st.error("No se encontró archivo .shp en el ZIP")
                return None
                
    except Exception as e:
        st.error(f"Error cargando shapefile: {str(e)[:200]}")
        return None

def cargar_kml(uploaded_file):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        gdf = gpd.read_file(tmp_path, driver='KML')
        os.unlink(tmp_path)
        
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        
        return gdf
    except Exception as e:
        st.error(f"Error cargando KML: {str(e)}")
        return None

def cargar_kmz(uploaded_file):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            kmz_path = os.path.join(tmp_dir, "upload.kmz")
            with open(kmz_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            
            with zipfile.ZipFile(kmz_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            # Buscar KML
            kml_files = []
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    if file.lower().endswith('.kml'):
                        kml_files.append(os.path.join(root, file))
            
            if kml_files:
                gdf = gpd.read_file(kml_files[0], driver='KML')
                
                if gdf.crs is None:
                    gdf.set_crs(epsg=4326, inplace=True)
                
                return gdf
            else:
                st.error("No se encontró KML en el KMZ")
                return None
    except Exception as e:
        st.error(f"Error cargando KMZ: {str(e)}")
        return None

# ================ ANÁLISIS FORRAJERO ================
class AnalisisForrajero:
    """Sistema de análisis forrajero"""
    
    def __init__(self):
        self.parametros = {
            'ALFALFA': {'ms_optimo': 5000, 'crecimiento': 100, 'consumo': 0.03},
            'RAYGRASS': {'ms_optimo': 4500, 'crecimiento': 90, 'consumo': 0.028},
            'FESTUCA': {'ms_optimo': 4000, 'crecimiento': 70, 'consumo': 0.025},
            'AGROPIRRO': {'ms_optimo': 3500, 'crecimiento': 60, 'consumo': 0.022},
            'PASTIZAL_NATURAL': {'ms_optimo': 3000, 'crecimiento': 40, 'consumo': 0.02},
            'MEZCLA_LEGUMINOSAS': {'ms_optimo': 4200, 'crecimiento': 85, 'consumo': 0.027}
        }
    
    def calcular_biomasa_por_ndvi(self, ndvi, tipo_pastura):
        """Calcula biomasa basada en NDVI"""
        params = self.parametros.get(tipo_pastura, self.parametros['PASTIZAL_NATURAL'])
        
        if ndvi < 0.15:
            factor = 0.1
            categoria = "SUELO DESNUDO"
        elif ndvi < 0.25:
            factor = 0.3
            categoria = "VEGETACIÓN ESCASA"
        elif ndvi < 0.40:
            factor = 0.5
            categoria = "VEGETACIÓN MODERADA"
        elif ndvi < 0.60:
            factor = 0.75
            categoria = "VEGETACIÓN BUENA"
        else:
            factor = 0.9
            categoria = "VEGETACIÓN EXCELENTE"
        
        biomasa = params['ms_optimo'] * factor
        crecimiento = params['crecimiento'] * factor
        
        return {
            'biomasa_kg_ms_ha': round(biomasa, 1),
            'crecimiento_kg_dia_ha': round(crecimiento, 1),
            'categoria': categoria,
            'ndvi': round(ndvi, 3)
        }

# ================ INTERFAZ PRINCIPAL ================
st.markdown('<div class="info-box">', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Estado GEE", "✅ CONECTADO" if st.session_state.gee_authenticated else "❌ NO CONECTADO")
with col2:
    fuente_display = "🛰️ " + fuente_satelital
    st.metric("Fuente de Datos", fuente_display)
with col3:
    st.metric("Tipo de Pastura", tipo_pastura)
st.markdown('</div>', unsafe_allow_html=True)

# ================ CARGA DE ARCHIVO ================
if uploaded_file is not None:
    with st.spinner("Procesando archivo..."):
        try:
            if tipo_archivo == "Shapefile (ZIP)":
                gdf = cargar_shapefile_desde_zip(uploaded_file)
            elif tipo_archivo == "KML":
                gdf = cargar_kml(uploaded_file)
            else:  # KMZ
                gdf = cargar_kmz(uploaded_file)
            
            if gdf is not None and not gdf.empty:
                st.session_state.gdf_cargado = gdf
                
                # Calcular área
                if gdf.crs != 'EPSG:4326':
                    gdf = gdf.to_crs('EPSG:4326')
                
                # Crear copia para calcular área
                gdf_area = gdf.copy()
                if gdf_area.crs.is_geographic:
                    gdf_area = gdf_area.to_crs('EPSG:3857')
                
                gdf_area['area_m2'] = gdf_area.geometry.area
                gdf['area_ha'] = gdf_area['area_m2'] / 10000
                area_total = gdf['area_ha'].sum()
                
                st.success(f"✅ Archivo cargado correctamente")
                
                # Mostrar información
                st.markdown("### 📊 INFORMACIÓN DEL POTRERO")
                col_info1, col_info2, col_info3, col_info4 = st.columns(4)
                with col_info1:
                    st.metric("Polígonos", len(gdf))
                with col_info2:
                    st.metric("Área Total", f"{area_total:.2f} ha")
                with col_info3:
                    st.metric("Centroide Lat", f"{gdf.geometry.centroid.y.mean():.4f}")
                with col_info4:
                    st.metric("Centroide Lon", f"{gdf.geometry.centroid.x.mean():.4f}")
                
                # Botón para análisis
                st.markdown("---")
                if st.button("🚀 EJECUTAR ANÁLISIS SATELITAL", type="primary", use_container_width=True):
                    with st.spinner("Analizando con datos satelitales..."):
                        try:
                            # Obtener imagen de GEE si está disponible
                            imagen_gee = None
                            ndvi_promedio = None
                            
                            if st.session_state.gee_authenticated and "SIMULADO" not in fuente_satelital:
                                servicio_gee = GoogleEarthEngineService()
                                
                                if "SENTINEL" in fuente_satelital:
                                    imagen_gee = servicio_gee.obtener_imagen_sentinel2(
                                        gdf, fecha_inicio, fecha_fin
                                    )
                                elif "LANDSAT" in fuente_satelital:
                                    landsat_version = 'LANDSAT/LC08/C02/T1_L2' if "8" in fuente_satelital else 'LANDSAT/LC09/C02/T1_L2'
                                    imagen_gee = servicio_gee.obtener_imagen_landsat(
                                        gdf, fecha_inicio, fecha_fin, landsat_version
                                    )
                                
                                if imagen_gee:
                                    ndvi_promedio = servicio_gee.calcular_ndvi_promedio(gdf, imagen_gee)
                                    st.session_state.imagen_gee = imagen_gee
                                    st.success(f"✅ NDVI calculado desde satélite: {ndvi_promedio:.3f}")
                                else:
                                    st.warning("No se pudo obtener imagen satelital, usando simulación")
                                    ndvi_promedio = 0.5 + np.random.uniform(-0.2, 0.2)
                            else:
                                # Datos simulados
                                ndvi_promedio = 0.5 + np.random.uniform(-0.2, 0.2)
                                st.info(f"📊 NDVI simulado: {ndvi_promedio:.3f}")
                            
                            # Realizar análisis forrajero
                            analizador = AnalisisForrajero()
                            resultados = analizador.calcular_biomasa_por_ndvi(ndvi_promedio, tipo_pastura)
                            
                            # Calcular métricas ganaderas
                            biomasa_total = resultados['biomasa_kg_ms_ha'] * area_total
                            consumo_individual = peso_promedio * resultados['consumo']
                            consumo_total = carga_animal * consumo_individual
                            
                            if consumo_total > 0:
                                dias_permanencia = biomasa_total / consumo_total
                            else:
                                dias_permanencia = 0
                            
                            if consumo_individual > 0:
                                ev_soportable = biomasa_total / consumo_individual / 1000
                            else:
                                ev_soportable = 0
                            
                            # Mostrar resultados
                            st.markdown("## 📈 RESULTADOS DEL ANÁLISIS")
                            
                            col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                            with col_res1:
                                st.metric("NDVI", f"{resultados['ndvi']:.3f}")
                            with col_res2:
                                st.metric("Biomasa", f"{resultados['biomasa_kg_ms_ha']:.0f} kg MS/ha")
                            with col_res3:
                                st.metric("EV Soportable", f"{ev_soportable:.1f}")
                            with col_res4:
                                st.metric("Días", f"{dias_permanencia:.0f}")
                            
                            st.markdown(f"**Categoría:** {resultados['categoria']}")
                            st.markdown(f"**Crecimiento diario:** {resultados['crecimiento_kg_dia_ha']:.1f} kg/ha/día")
                            st.markdown(f"**Área total:** {area_total:.2f} ha")
                            st.markdown(f"**Biomasa total:** {biomasa_total:.0f} kg MS")
                            
                            # Recomendaciones
                            st.markdown("### 💡 RECOMENDACIONES")
                            
                            if resultados['biomasa_kg_ms_ha'] < 1000:
                                st.error("🔴 **CRÍTICO:** Biomasa muy baja. Considerar suplementación urgente.")
                            elif resultados['biomasa_kg_ms_ha'] < 2000:
                                st.warning("🟡 **ALERTA:** Biomasa moderada. Monitorear diariamente.")
                            else:
                                st.success("✅ **ÓPTIMO:** Biomasa adecuada. Manejo normal.")
                            
                            if dias_permanencia < 15:
                                st.warning("⚡ **ROTACIÓN RÁPIDA:** Considerar aumentar área o reducir carga.")
                            elif dias_permanencia > 60:
                                st.info("🐌 **ROTACIÓN LENTA:** Podría aumentar carga animal.")
                            
                            # Exportar datos
                            st.markdown("---")
                            st.markdown("### 💾 EXPORTAR RESULTADOS")
                            
                            datos_exportar = {
                                'Fecha': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'Fuente': fuente_satelital,
                                'Tipo_Pastura': tipo_pastura,
                                'NDVI': resultados['ndvi'],
                                'Categoria': resultados['categoria'],
                                'Biomasa_kg_ms_ha': resultados['biomasa_kg_ms_ha'],
                                'Crecimiento_kg_dia_ha': resultados['crecimiento_kg_dia_ha'],
                                'Area_ha': area_total,
                                'Biomasa_Total_kg': biomasa_total,
                                'EV_Soportable': ev_soportable,
                                'Dias_Permanencia': dias_permanencia,
                                'Peso_Promedio': peso_promedio,
                                'Carga_Animal': carga_animal,
                                'Consumo_Individual': consumo_individual,
                                'Consumo_Total': consumo_total
                            }
                            
                            df_exportar = pd.DataFrame([datos_exportar])
                            
                            col_exp1, col_exp2 = st.columns(2)
                            with col_exp1:
                                csv = df_exportar.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    "📥 Descargar CSV",
                                    csv,
                                    f"analisis_forrajero_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                    "text/csv",
                                    use_container_width=True
                                )
                            
                            with col_exp2:
                                json_str = json.dumps(datos_exportar, indent=2, ensure_ascii=False)
                                st.download_button(
                                    "📄 Descargar JSON",
                                    json_str.encode('utf-8'),
                                    f"analisis_forrajero_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                                    "application/json",
                                    use_container_width=True
                                )
                            
                        except Exception as e:
                            st.error(f"Error en análisis: {str(e)}")
                
            else:
                st.error("No se pudo cargar el archivo")
                
        except Exception as e:
            st.error(f"Error procesando archivo: {str(e)}")
else:
    # Pantalla de inicio
    st.markdown("""
    <div class="info-box">
    <h3>👋 BIENVENIDO AL SISTEMA DE ANÁLISIS FORRAJERO</h3>
    <p>Este sistema utiliza <strong>Google Earth Engine</strong> para analizar la disponibilidad forrajera de tus potreros con datos satelitales reales.</p>
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.gee_authenticated:
        st.markdown("""
        <div class="warning-box">
        <h4>⚠️ CONFIGURACIÓN REQUERIDA</h4>
        <p>Para usar datos satelitales reales, necesitas configurar Google Earth Engine:</p>
        <ol>
        <li>Ve a <strong>Settings → Secrets</strong> en tu app de Streamlit</li>
        <li>Agrega las credenciales de Service Account de GEE</li>
        <li>Reinicia la aplicación</li>
        </ol>
        <p>Mientras tanto, puedes usar la opción <strong>"SIMULADO"</strong> para pruebas.</p>
        </div>
        """, unsafe_allow_html=True)
    
    col_inst1, col_inst2, col_inst3 = st.columns(3)
    
    with col_inst1:
        st.markdown("""
        <div class="metric-box">
        <h4>📁 CARGA DE DATOS</h4>
        <p>Sube tu potrero en formato Shapefile (ZIP), KML o KMZ</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_inst2:
        st.markdown("""
        <div class="metric-box">
        <h4>🛰️ ANÁLISIS SATELITAL</h4>
        <p>Obten datos reales de Sentinel-2 o Landsat</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col_inst3:
        st.markdown("""
        <div class="metric-box">
        <h4>📊 RESULTADOS</h4>
        <p>Calcula biomasa, capacidad de carga y recomendaciones</p>
        </div>
        """, unsafe_allow_html=True)

# ================ PIE DE PÁGINA ================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 11px;'>
<p><strong>Sistema de Análisis Forrajero con Google Earth Engine</strong> | Versión 3.0 | 🛰️ Datos Satelitales Reales</p>
<p>© 2024 - Para uso técnico y profesional | Contacto: soporte@analisisfograjeero.com</p>
</div>
""", unsafe_allow_html=True)

# ================ SCRIPT PARA CONFIGURACIÓN GEE ================
if not st.session_state.gee_authenticated and st.checkbox("Mostrar instrucciones detalladas de configuración"):
    st.markdown("""
    ### 🔧 CONFIGURACIÓN DETALLADA DE GOOGLE EARTH ENGINE
    
    **Paso 1: Crear proyecto en Google Cloud**
    1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
    2. Crea un nuevo proyecto o selecciona uno existente
    3. Habilita la API de Earth Engine
    
    **Paso 2: Crear Service Account**
    1. En Cloud Console, ve a IAM → Service Accounts
    2. Haz clic en "Create Service Account"
    3. Dale un nombre (ej: "gee-streamlit-app")
    4. Concede el rol "Earth Engine User"
    5. Haz clic en "Done"
    
    **Paso 3: Generar clave JSON**
    1. En la lista de cuentas de servicio, haz clic en la que creaste
    2. Ve a la pestaña "Keys"
    3. Haz clic en "Add Key" → "Create new key"
    4. Selecciona JSON y descarga el archivo
    
    **Paso 4: Configurar en Streamlit Cloud**
    1. Ve a tu app en Streamlit Cloud
    2. Haz clic en "Settings" (engranaje)
    3. Ve a "Secrets"
    4. Agrega:
       ```
       GEE_SERVICE_ACCOUNT = '{"type": "service_account", "project_id": "...", ...}'
       ```
    5. Pega TODO el contenido del archivo JSON que descargaste
    6. Guarda y reinicia la app
    
    **Paso 5: Habilitar Earth Engine para la cuenta**
    1. Ve a [Earth Engine](https://earthengine.google.com/)
    2. Regístrate con la cuenta de servicio (el email de la cuenta)
    3. Acepta los términos y condiciones
    
    **Nota:** El proceso puede tardar unos minutos en propagarse.
    """)
