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

# ===== GOOGLE EARTH ENGINE CONFIGURACIÓN SIMPLIFICADA =====
EE_AVAILABLE = False  # Inicialmente asumimos no disponible

# Intentar importar ee de manera segura
try:
    # Primero intentamos importar sin inicializar
    import ee
    EE_AVAILABLE = True
    
    # Función para inicializar GEE de manera segura
    def inicializar_gee_seguro():
        """Inicializa GEE de manera segura para producción"""
        if not EE_AVAILABLE:
            return False
        
        try:
            # Opción 1: Intentar inicializar directamente
            ee.Initialize()
            st.session_state.gee_authenticated = True
            st.success("✅ Google Earth Engine inicializado")
            return True
        except Exception as e1:
            try:
                # Opción 2: Usar Service Account desde secrets
                import os
                import json
                
                # Intentar leer credenciales de variables de entorno
                service_account_json = os.environ.get('GEE_SERVICE_ACCOUNT')
                
                if service_account_json:
                    try:
                        # Parsear JSON de la variable de entorno
                        service_account_info = json.loads(service_account_json)
                        
                        # Crear credenciales
                        credentials = ee.ServiceAccountCredentials(
                            email=service_account_info['client_email'],
                            key_data=json.dumps(service_account_info)
                        )
                        
                        # Inicializar con credenciales
                        ee.Initialize(credentials)
                        st.session_state.gee_authenticated = True
                        st.success("✅ GEE inicializado con Service Account")
                        return True
                    except json.JSONDecodeError:
                        st.warning("⚠️ Formato incorrecto de Service Account")
                else:
                    # No hay credenciales en variables de entorno
                    st.warning("⚠️ No se encontraron credenciales de GEE")
                    
            except Exception as e2:
                # Último intento: inicializar sin autenticación para datos públicos
                try:
                    ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
                    st.session_state.gee_authenticated = True
                    st.success("✅ GEE inicializado en modo público")
                    return True
                except Exception as e3:
                    st.warning("⚠️ No se pudo inicializar Google Earth Engine")
                    st.session_state.gee_authenticated = False
                    return False
        
        return False
    
    # Intentar inicializar al cargar la app
    if EE_AVAILABLE:
        try:
            # Solo intentar inicializar si no está ya inicializado
            if not hasattr(st.session_state, 'gee_authenticated') or not st.session_state.gee_authenticated:
                # Usar un enfoque más directo
                ee.Initialize()
                st.session_state.gee_authenticated = True
        except Exception:
            # Si falla, marcar como no autenticado pero mantener disponible
            st.session_state.gee_authenticated = False
    else:
        st.session_state.gee_authenticated = False
        
except ImportError:
    EE_AVAILABLE = False
    st.session_state.gee_authenticated = False
    # Mostrar advertencia solo si se selecciona GEE más tarde

# Configuración de Streamlit
st.set_page_config(page_title="🌱 Sistema de Gestión Forrajera", layout="wide")
st.title("🌱 Sistema Avanzado de Gestión Forrajera")
st.markdown("""
<div style='background-color: #f0f8ff; padding: 20px; border-radius: 10px; margin-bottom: 20px;'>
<h3>🚀 Análisis Forrajero con Datos Satelitales y Climáticos</h3>
<p>Monitoreo de biomasa, capacidad de carga y planificación ganadera mediante tecnología geoespacial.</p>
</div>
""", unsafe_allow_html=True)

os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# ---------- APIs Externas ----------
NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# ---------- Parámetros por defecto ----------
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55

# Session state inicializado
for key in [
    'gdf_cargado', 'gdf_analizado', 'datos_clima', 'datos_suelo',
    'informe_generado', 'gee_authenticated', 'imagen_gee',
    'tipo_pastura_guardado', 'carga_animal_guardada', 'peso_promedio_guardado'
]:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------
# SIDEBAR (CONFIGURACIÓN MEJORADA)
# -----------------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/cow.png", width=80)
    st.header("⚙️ Configuración")
    
    st.subheader("🛰️ Fuente de Datos")
    fuente_satelital = st.selectbox(
        "Seleccionar fuente:",
        ["SENTINEL-2 (GEE)", "LANDSAT-8/9 (GEE)", "SIMULADO"],
        index=2  # Por defecto SIMULADO
    )
    
    # Mostrar estado de GEE
    if "GEE" in fuente_satelital:
        if st.session_state.get('gee_authenticated', False):
            st.success("✅ GEE disponible")
        else:
            st.warning("⚠️ GEE requiere configuración")
            st.info("""
            **Para usar datos satelitales reales:**
            1. Contacta al administrador
            2. O usa la opción 'SIMULADO'
            """)
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox("Seleccionar tipo:",
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", 
                                "PASTIZAL_NATURAL", "MEZCLA_LEGUMINOSAS", "PERSONALIZADO"])
    
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05,
                                            value=0.025, step=0.001, format="%.3f")
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 1, 1000, 100)
    
    st.subheader("📅 Fechas de Análisis")
    fecha_inicio = st.date_input(
        "Fecha inicial:",
        value=datetime.now() - timedelta(days=60)
    )
    fecha_fin = st.date_input(
        "Fecha final:",
        value=datetime.now()
    )
    
    # Nubes máximo solo para GEE
    if "GEE" in fuente_satelital:
        nubes_max = st.slider("Máximo % de nubes:", 0, 100, 20)
    
    st.subheader("🔪 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=50, value=16)
    
    st.subheader("📤 Cargar Potrero")
    tipo_archivo = st.radio(
        "Formato:",
        ["Shapefile (ZIP)", "KML", "KMZ"],
        horizontal=True
    )
    
    uploaded_file = None
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir archivo ZIP", type=['zip'])
    elif tipo_archivo == "KML":
        uploaded_file = st.file_uploader("Subir archivo KML", type=['kml'])
    else:
        uploaded_file = st.file_uploader("Subir archivo KMZ", type=['kmz'])
    
    # Botón para ejecutar análisis
    st.markdown("---")
    if uploaded_file:
        st.download_button(
            label="📥 Descargar plantilla CSV",
            data="id,area_ha,lat,lon\n1,10,-34.6,-58.4\n2,15,-34.7,-58.5",
            file_name="plantilla_potreros.csv",
            mime="text/csv"
        )

# -----------------------
# SERVICIOS EXTERNOS SIMPLIFICADOS
# -----------------------
class ServicioClima:
    """Servicio climático simplificado"""
    
    @staticmethod
    def obtener_datos_climaticos(lat, lon, fecha_inicio, fecha_fin):
        """Obtiene datos climáticos"""
        try:
            # Datos simulados basados en ubicación y época
            mes = fecha_inicio.month
            dias = (fecha_fin - fecha_inicio).days
            
            if lat < -35:  # Región pampeana
                if 10 <= mes <= 3:  # Primavera-verano
                    temp_max = 28 + np.random.uniform(-3, 3)
                    temp_min = 15 + np.random.uniform(-3, 3)
                    precip = 80 + np.random.uniform(-20, 40)
                else:  # Otoño-invierno
                    temp_max = 18 + np.random.uniform(-3, 3)
                    temp_min = 8 + np.random.uniform(-3, 3)
                    precip = 40 + np.random.uniform(-10, 20)
            else:  # Norte
                temp_max = 32 + np.random.uniform(-2, 4)
                temp_min = 20 + np.random.uniform(-2, 4)
                precip = 100 + np.random.uniform(-30, 60)
            
            return {
                'latitud': lat,
                'longitud': lon,
                'periodo': f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
                'precipitacion_total': round(precip, 1),
                'precipitacion_promedio': round(precip / max(dias, 30), 1),
                'temp_max_promedio': round(temp_max, 1),
                'temp_min_promedio': round(temp_min, 1),
                'humedad_promedio': round(65 + np.random.uniform(-10, 10), 1),
                'dias_lluvia': int(precip / 5),
                'fuente': 'Simulado basado en ubicación'
            }
        except Exception:
            return None

class ServicioSuelos:
    """Servicio de suelos simplificado"""
    
    @staticmethod
    def obtener_caracteristicas_suelo(lat, lon):
        """Obtiene características del suelo"""
        try:
            if lat < -35:  # Región pampeana
                textura = "Franco limoso"
                materia_organica = 3.2
                ph = 6.8
                profundidad = 65
            elif lat < -40:  # Patagonia
                textura = "Franco arenoso"
                materia_organica = 1.8
                ph = 7.5
                profundidad = 40
            else:  # Norte
                textura = "Franco arcilloso"
                materia_organica = 2.2
                ph = 6.5
                profundidad = 55
            
            return {
                'textura': textura,
                'profundidad': round(profundidad + np.random.uniform(-10, 15), 0),
                'materia_organica': round(materia_organica + np.random.uniform(-0.3, 0.3), 1),
                'ph': round(ph + np.random.uniform(-0.4, 0.4), 1),
                'capacidad_campo': round(25 + np.random.uniform(-5, 10), 1),
                'fuente': 'Simulado basado en ubicación'
            }
        except Exception:
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
        st.error(f"❌ Error cargando shapefile: {str(e)[:100]}")
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
        st.error(f"❌ Error cargando KML: {str(e)[:100]}")
        return None

# -----------------------
# ANÁLISIS FORRAJERO
# -----------------------
class AnalisisForrajero:
    """Clase para análisis forrajero simplificado"""
    
    def __init__(self):
        self.parametros = {
            'ALFALFA': {'ms_optimo': 5000, 'crecimiento': 100, 'proteina': 18},
            'RAYGRASS': {'ms_optimo': 4500, 'crecimiento': 90, 'proteina': 16},
            'FESTUCA': {'ms_optimo': 4000, 'crecimiento': 70, 'proteina': 14},
            'AGROPIRRO': {'ms_optimo': 3500, 'crecimiento': 60, 'proteina': 12},
            'PASTIZAL_NATURAL': {'ms_optimo': 3000, 'crecimiento': 40, 'proteina': 10},
            'MEZCLA_LEGUMINOSAS': {'ms_optimo': 4200, 'crecimiento': 85, 'proteina': 17}
        }
    
    def calcular_ndvi(self, id_sublote, area_ha, lat, lon):
        """Calcula NDVI simulado"""
        # Simulación basada en ubicación y área
        base = 0.3 + (lat + 40) / 100  # Aprox 0.3 a 0.6 para Argentina
        variacion = np.sin(id_sublote * 0.5) * 0.2
        ndvi = max(0.1, min(0.8, base + variacion + np.random.normal(0, 0.05)))
        return ndvi
    
    def clasificar_vegetacion(self, ndvi):
        """Clasifica vegetación según NDVI"""
        if ndvi < 0.15:
            return "SUELO_DESNUDO", 0.1
        elif ndvi < 0.25:
            return "SUELO_PARCIAL", 0.3
        elif ndvi < 0.40:
            return "VEGETACION_ESCASA", 0.5
        elif ndvi < 0.60:
            return "VEGETACION_MODERADA", 0.75
        else:
            return "VEGETACION_DENSA", 0.9
    
    def calcular_biomasa(self, ndvi, categoria, cobertura, tipo_pastura):
        """Calcula biomasa disponible"""
        params = self.parametros.get(tipo_pastura, self.parametros['PASTIZAL_NATURAL'])
        
        # Biomasa base según categoría
        if categoria == "SUELO_DESNUDO":
            biomasa_base = 50
        elif categoria == "SUELO_PARCIAL":
            biomasa_base = params['ms_optimo'] * 0.1
        elif categoria == "VEGETACION_ESCASA":
            biomasa_base = params['ms_optimo'] * 0.3
        elif categoria == "VEGETACION_MODERADA":
            biomasa_base = params['ms_optimo'] * 0.6
        else:
            biomasa_base = params['ms_optimo'] * 0.85
        
        # Ajustar por cobertura
        biomasa_disponible = biomasa_base * cobertura
        
        # Crecimiento diario
        crecimiento = params['crecimiento'] * cobertura
        
        return round(biomasa_disponible, 1), round(crecimiento, 1)

# -----------------------
# FUNCIONES AUXILIARES
# -----------------------
def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs is None or gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs(epsg=3857)
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000.0
    except Exception:
        return gdf.geometry.area / 10000.0

def dividir_potrero(gdf, n_zonas):
    """Divide un potrero en sub-lotes"""
    if gdf is None or len(gdf) == 0:
        return gdf
    
    lista_sublotes = []
    
    for idx, row in gdf.iterrows():
        geom = row.geometry
        
        if isinstance(geom, MultiPolygon):
            polygons = list(geom.geoms)
        else:
            polygons = [geom]
        
        for poly in polygons:
            minx, miny, maxx, maxy = poly.bounds
            
            # Calcular número de filas y columnas
            n_cols = int(np.sqrt(n_zonas))
            n_rows = int(np.ceil(n_zonas / n_cols))
            
            width = (maxx - minx) / n_cols
            height = (maxy - miny) / n_rows
            
            sublote_id = 1
            
            for i in range(n_rows):
                for j in range(n_cols):
                    if sublote_id > n_zonas:
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
                    
                    intersection = poly.intersection(cell)
                    if not intersection.is_empty and intersection.area > 0:
                        centroid = intersection.centroid
                        
                        lista_sublotes.append({
                            'id_sublote': sublote_id,
                            'id_potrero': idx + 1,
                            'geometry': intersection,
                            'centroid_lat': centroid.y,
                            'centroid_lon': centroid.x
                        })
                        sublote_id += 1
    
    if lista_sublotes:
        gdf_sublotes = gpd.GeoDataFrame(lista_sublotes, crs=gdf.crs)
        return gdf_sublotes
    
    return gdf

# -----------------------
# EJECUCIÓN DE ANÁLISIS
# -----------------------
def ejecutar_analisis(gdf, tipo_pastura, carga_animal, peso_promedio, n_divisiones):
    """Ejecuta análisis completo"""
    
    analizador = AnalisisForrajero()
    
    # Dividir potrero
    gdf_sublotes = dividir_potrero(gdf, n_divisiones)
    
    if gdf_sublotes is None:
        return None
    
    # Calcular áreas
    areas = calcular_superficie(gdf_sublotes)
    gdf_sublotes['area_ha'] = areas.values
    
    resultados = []
    
    # Progreso
    progress_bar = st.progress(0)
    
    for idx, row in gdf_sublotes.iterrows():
        progress_bar.progress((idx + 1) / len(gdf_sublotes))
        
        # Obtener coordenadas del centroide
        lat = row['centroid_lat']
        lon = row['centroid_lon']
        area_ha = row['area_ha']
        
        # Calcular NDVI
        ndvi = analizador.calcular_ndvi(row['id_sublote'], area_ha, lat, lon)
        
        # Clasificar vegetación
        categoria, cobertura = analizador.clasificar_vegetacion(ndvi)
        
        # Calcular biomasa
        biomasa_disponible, crecimiento = analizador.calcular_biomasa(
            ndvi, categoria, cobertura, tipo_pastura
        )
        
        # Calcular métricas ganaderas
        biomasa_total = biomasa_disponible * area_ha
        consumo_individual = peso_promedio * 0.025  # 2.5% del peso vivo
        consumo_total = carga_animal * consumo_individual
        
        if consumo_total > 0:
            dias_permanencia = biomasa_total / consumo_total
        else:
            dias_permanencia = 0
        
        if consumo_individual > 0:
            ev_soportable = biomasa_total / consumo_individual / 1000
        else:
            ev_soportable = 0
        
        resultados.append({
            'id_sublote': row['id_sublote'],
            'id_potrero': row['id_potrero'],
            'area_ha': round(area_ha, 2),
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'ndvi': round(ndvi, 3),
            'categoria_vegetacion': categoria,
            'cobertura': round(cobertura, 2),
            'biomasa_kg_ms_ha': round(biomasa_disponible, 1),
            'biomasa_total_kg': round(biomasa_total, 1),
            'crecimiento_diario_kg': round(crecimiento, 1),
            'ev_soportable': round(ev_soportable, 1),
            'dias_permanencia': round(dias_permanencia, 1),
            'consumo_individual_kg': round(consumo_individual, 1),
            'consumo_total_kg': round(consumo_total, 1)
        })
    
    progress_bar.empty()
    
    # Convertir a DataFrame
    df_resultados = pd.DataFrame(resultados)
    
    # Obtener datos climáticos y de suelo
    centroide = gdf_sublotes.geometry.unary_union.centroid
    datos_clima = ServicioClima.obtener_datos_climaticos(
        centroide.y, centroide.x, fecha_inicio, fecha_fin
    )
    datos_suelo = ServicioSuelos.obtener_caracteristicas_suelo(centroide.y, centroide.x)
    
    return df_resultados, datos_clima, datos_suelo, gdf_sublotes

# -----------------------
# VISUALIZACIÓN DE RESULTADOS
# -----------------------
def mostrar_resultados(df_resultados, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio):
    """Muestra resultados del análisis"""
    
    st.markdown("---")
    st.markdown("## 📊 RESULTADOS DEL ANÁLISIS")
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        area_total = df_resultados['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    with col2:
        biomasa_promedio = df_resultados['biomasa_kg_ms_ha'].mean()
        st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
    
    with col3:
        ev_total = df_resultados['ev_soportable'].sum()
        st.metric("EV Total", f"{ev_total:.1f}")
    
    with col4:
        dias_promedio = df_resultados['dias_permanencia'].mean()
        st.metric("Días Permanencia", f"{dias_promedio:.0f}")
    
    # Balance forrajero
    st.markdown("### 🌿 BALANCE FORRAJERO")
    
    col5, col6, col7 = st.columns(3)
    
    with col5:
        produccion_total = (df_resultados['crecimiento_diario_kg'] * df_resultados['area_ha']).sum()
        st.metric("Producción Diaria", f"{produccion_total:.0f} kg/día")
    
    with col6:
        consumo_total = carga_animal * peso_promedio * 0.025
        st.metric("Consumo Diario", f"{consumo_total:.0f} kg/día")
    
    with col7:
        balance = produccion_total - consumo_total
        st.metric("Balance Diario", f"{balance:.0f} kg/día")
    
    # Distribución de categorías
    st.markdown("### 🗺️ DISTRIBUCIÓN DE VEGETACIÓN")
    
    if 'categoria_vegetacion' in df_resultados.columns:
        distribucion = df_resultados['categoria_vegetacion'].value_counts()
        
        col8, col9 = st.columns(2)
        
        with col8:
            fig, ax = plt.subplots(figsize=(8, 6))
            colors = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 
                     'VEGETACION_ESCASA': '#fee08b', 'VEGETACION_MODERADA': '#a6d96a',
                     'VEGETACION_DENSA': '#1a9850'}
            
            categoria_colors = [colors.get(cat, '#808080') for cat in distribucion.index]
            
            ax.pie(distribucion.values, labels=distribucion.index,
                  autopct='%1.1f%%', colors=categoria_colors,
                  startangle=90)
            ax.set_title('Distribución de Categorías de Vegetación')
            st.pyplot(fig)
            plt.close(fig)
        
        with col9:
            # Tabla de distribución
            df_dist = pd.DataFrame({
                'Categoría': distribucion.index,
                'Sub-lotes': distribucion.values,
                '% Área': (distribucion.values / len(df_resultados) * 100).round(1)
            })
            st.dataframe(df_dist, use_container_width=True, hide_index=True)
    
    # Datos ambientales
    st.markdown("### 🌤️ DATOS AMBIENTALES")
    
    if datos_clima or datos_suelo:
        col10, col11 = st.columns(2)
        
        with col10:
            if datos_clima:
                st.markdown("**🌤️ Datos Climáticos**")
                df_clima = pd.DataFrame({
                    'Parámetro': ['Precipitación Total', 'Temperatura Máx', 
                                 'Temperatura Mín', 'Días con Lluvia'],
                    'Valor': [
                        f"{datos_clima.get('precipitacion_total', 0):.0f} mm",
                        f"{datos_clima.get('temp_max_promedio', 0):.1f}°C",
                        f"{datos_clima.get('temp_min_promedio', 0):.1f}°C",
                        f"{datos_clima.get('dias_lluvia', 0)} días"
                    ]
                })
                st.dataframe(df_clima, use_container_width=True, hide_index=True)
        
        with col11:
            if datos_suelo:
                st.markdown("**🌍 Datos de Suelo**")
                df_suelo = pd.DataFrame({
                    'Característica': ['Textura', 'Materia Orgánica', 
                                      'pH', 'Profundidad'],
                    'Valor': [
                        datos_suelo.get('textura', 'N/A'),
                        f"{datos_suelo.get('materia_organica', 0):.1f}%",
                        f"{datos_suelo.get('ph', 0):.1f}",
                        f"{datos_suelo.get('profundidad', 0):.0f} cm"
                    ]
                })
                st.dataframe(df_suelo, use_container_width=True, hide_index=True)
    
    # Recomendaciones
    st.markdown("### 💡 RECOMENDACIONES")
    
    biomasa_prom = df_resultados['biomasa_kg_ms_ha'].mean()
    
    if biomasa_prom < 600:
        st.error("🔴 **CRÍTICO**: Biomasa muy baja. Considerar suplementación inmediata.")
    elif biomasa_prom < 1200:
        st.warning("🟡 **ALERTA**: Biomasa baja. Monitorear diariamente.")
    elif biomasa_prom < 1800:
        st.success("🟢 **ACEPTABLE**: Biomasa moderada. Mantener manejo actual.")
    else:
        st.success("✅ **ÓPTIMO**: Biomasa adecuada. Buen crecimiento.")
    
    # Exportación de datos
    st.markdown("---")
    st.markdown("### 💾 EXPORTAR RESULTADOS")
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        # Exportar CSV
        csv = df_resultados.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Descargar CSV",
            data=csv,
            file_name=f"analisis_forrajero_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_exp2:
        # Exportar resumen
        resumen = f"""
        RESUMEN DE ANÁLISIS FORRAJERO
        Fecha: {datetime.now().strftime('%d/%m/%Y')}
        Tipo de Pastura: {tipo_pastura}
        Carga Animal: {carga_animal} cabezas
        Peso Promedio: {peso_promedio} kg
        
        RESULTADOS:
        - Área Total: {area_total:.1f} ha
        - Biomasa Promedio: {biomasa_promedio:.0f} kg MS/ha
        - EV Total Soportable: {ev_total:.1f}
        - Días de Permanencia: {dias_promedio:.0f} días
        - Producción Diaria: {produccion_total:.0f} kg
        - Consumo Diario: {consumo_total:.0f} kg
        - Balance Diario: {balance:.0f} kg
        
        RECOMENDACIONES:
        - {'Suplementación inmediata requerida' if biomasa_prom < 600 else 'Manejo normal recomendado'}
        """
        
        st.download_button(
            label="📝 Descargar Resumen (TXT)",
            data=resumen.encode('utf-8'),
            file_name=f"resumen_analisis_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    # Tabla completa de resultados
    st.markdown("### 📋 TABLA COMPLETA DE RESULTADOS")
    st.dataframe(df_resultados, use_container_width=True, height=400)

# -----------------------
# FLUJO PRINCIPAL
# -----------------------
st.markdown("### 📁 CARGAR POTRERO")

if uploaded_file is not None:
    with st.spinner("Cargando archivo..."):
        try:
            if tipo_archivo == "Shapefile (ZIP)":
                gdf = cargar_shapefile_desde_zip(uploaded_file)
            elif tipo_archivo == "KML":
                gdf = cargar_kml(uploaded_file)
            else:
                # Para KMZ, usar la misma función que KML después de extraer
                with tempfile.TemporaryDirectory() as tmp_dir:
                    kmz_path = os.path.join(tmp_dir, "upload.kmz")
                    with open(kmz_path, "wb") as f:
                        f.write(uploaded_file.getvalue())
                    
                    with zipfile.ZipFile(kmz_path, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    kml_files = [f for f in os.listdir(tmp_dir) if f.endswith('.kml')]
                    if kml_files:
                        gdf = gpd.read_file(os.path.join(tmp_dir, kml_files[0]))
                    else:
                        st.error("❌ No se encontró archivo KML en el KMZ")
                        gdf = None
            
            if gdf is not None and not gdf.empty:
                st.session_state.gdf_cargado = gdf
                
                # Calcular área
                areas = calcular_superficie(gdf)
                area_total = areas.sum() if hasattr(areas, 'sum') else areas
                
                st.success(f"✅ Potrero cargado correctamente")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Polígonos", len(gdf))
                with col2:
                    st.metric("Área Total", f"{area_total:.1f} ha")
                with col3:
                    st.metric("Tipo Pastura", tipo_pastura)
                with col4:
                    st.metric("Carga Animal", f"{carga_animal}")
                
                # Mostrar mapa si es posible
                if FOLIUM_AVAILABLE:
                    st.markdown("---")
                    st.markdown("### 🗺️ VISUALIZACIÓN DEL POTRERO")
                    
                    try:
                        centroide = gdf.geometry.unary_union.centroid
                        m = folium.Map(location=[centroide.y, centroide.x], zoom_start=14)
                        
                        # Agregar capa ESRI
                        esri_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
                        folium.TileLayer(
                            esri_url,
                            attr='Esri',
                            name='ESRI Satellite'
                        ).add_to(m)
                        
                        # Agregar polígono
                        folium.GeoJson(
                            gdf.__geo_interface__,
                            style_function=lambda x: {
                                'fillColor': '#00a8ff',
                                'color': '#00a8ff',
                                'weight': 3,
                                'fillOpacity': 0.4
                            }
                        ).add_to(m)
                        
                        st_folium(m, width=1200, height=500)
                    except Exception as e:
                        st.info("Mapa no disponible")
                
                # Botón para ejecutar análisis
                st.markdown("---")
                if st.button("🚀 EJECUTAR ANÁLISIS COMPLETO", type="primary", use_container_width=True):
                    with st.spinner("Analizando potrero..."):
                        resultados, datos_clima, datos_suelo, gdf_sublotes = ejecutar_analisis(
                            gdf, tipo_pastura, carga_animal, peso_promedio, n_divisiones
                        )
                        
                        if resultados is not None:
                            st.session_state.gdf_analizado = gdf_sublotes
                            st.session_state.datos_clima = datos_clima
                            st.session_state.datos_suelo = datos_suelo
                            st.session_state.tipo_pastura_guardado = tipo_pastura
                            st.session_state.carga_animal_guardada = carga_animal
                            st.session_state.peso_promedio_guardado = peso_promedio
                            
                            # Mostrar resultados
                            mostrar_resultados(
                                resultados, datos_clima, datos_suelo,
                                tipo_pastura, carga_animal, peso_promedio
                            )
                        else:
                            st.error("❌ Error en el análisis")
                
            else:
                st.info("⚠️ No se pudo cargar el archivo o está vacío")
                
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:200]}")
else:
    # Pantalla de bienvenida
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 30px; border-radius: 10px;'>
    <h3>👋 Bienvenido al Sistema de Gestión Forrajera</h3>
    <p>Este sistema te permite analizar la disponibilidad forrajera de tus potreros utilizando tecnología geoespacial.</p>
    
    <h4>🚀 Cómo comenzar:</h4>
    <ol>
    <li><strong>Configura los parámetros</strong> en la barra lateral</li>
    <li><strong>Sube un archivo espacial</strong> de tu potrero (ZIP con shapefile, KML o KMZ)</li>
    <li><strong>Ejecuta el análisis</strong> para obtener resultados detallados</li>
    <li><strong>Descarga los reportes</strong> en múltiples formatos</li>
    </ol>
    
    <h4>📊 Métricas calculadas:</h4>
    <ul>
    <li>📈 Biomasa disponible (kg MS/ha)</li>
    <li>🐄 Capacidad de carga (EV)</li>
    <li>📅 Días de permanencia</li>
    <li>🌱 Estado vegetativo (NDVI simulado)</li>
    <li>🌤️ Datos climáticos estimados</li>
    <li>🌍 Características del suelo</li>
    </ul>
    
    <h4>💡 Consejos:</h4>
    <ul>
    <li>Usa coordenadas en sistema WGS84 (lat/lon)</li>
    <li>Para shapefiles, comprime todos los archivos en un ZIP</li>
    <li>Los resultados se basan en modelos y deben validarse en campo</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Ejemplo rápido
    st.markdown("---")
    st.markdown("### 🎯 EJEMPLO RÁPIDO")
    
    if st.button("🎮 Probar con datos de ejemplo", use_container_width=True):
        # Crear un GeoDataFrame de ejemplo
        polygon = Polygon([
            (-58.5, -34.6),
            (-58.4, -34.6),
            (-58.4, -34.5),
            (-58.5, -34.5),
            (-58.5, -34.6)
        ])
        
        gdf_ejemplo = gpd.GeoDataFrame({'geometry': [polygon]}, crs='EPSG:4326')
        st.session_state.gdf_cargado = gdf_ejemplo
        
        st.success("✅ Potrero de ejemplo cargado")
        st.info("Ahora puedes ejecutar el análisis con los parámetros configurados")
        st.rerun()

# -----------------------
# PIE DE PÁGINA
# -----------------------
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 12px; padding: 20px;'>
<p>Sistema de Gestión Forrajera | Versión 2.0 | 🚀 Streamlit Cloud</p>
<p>Desarrollado para productores y técnicos agropecuarios | © 2024</p>
<p><a href="mailto:soporte@ejemplo.com" style='color: #0066cc;'>Contactar soporte técnico</a></p>
</div>
""", unsafe_allow_html=True)

# Script para inicializar GEE en segundo plano
if EE_AVAILABLE and not st.session_state.get('gee_authenticated', False) and "GEE" in fuente_satelital:
    # Intentar inicializar GEE en segundo plano
    import threading
    
    def intentar_inicializar_gee():
        try:
            ee.Initialize()
            st.session_state.gee_authenticated = True
        except Exception:
            st.session_state.gee_authenticated = False
    
    # Ejecutar en un hilo separado para no bloquear la interfaz
    thread = threading.Thread(target=intentar_inicializar_gee)
    thread.daemon = True
    thread.start()
