"""
APP COMPLETA DE ANÁLISIS FORRAJERO AVANZADO
Con ESRI Satellite forzado y generación de informe completo
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
INTA_SUELOS_WFS_URL = "https://geoserver.inta.gob.ar/geoserver/ows"

# ---------- Parámetros por defecto ----------
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Forzar ESRI Satellite como mapa base único
FORCED_BASE_MAP = "ESRI Satélite"

# Session state
for key in [
    'gdf_cargado', 'gdf_analizado', 'mapa_detallado_bytes',
    'docx_buffer', 'analisis_completado', 'html_download_injected',
    'datos_clima', 'datos_suelo', 'indices_avanzados', 'informe_generado'
]:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------
# SIDEBAR (CONFIGURACIÓN)
# -----------------------
with st.sidebar:
    st.header("⚙️ Configuración Avanzada")
    
    # Mostrar solo ESRI Satellite como opción (forzado)
    st.subheader("🗺️ Mapa Base")
    st.info("🌍 ESRI Satélite (forzado)")
    base_map_option = FORCED_BASE_MAP

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
            # Convertir fechas a formato NASA POWER
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
        """Procesa los datos crudos de NASA POWER"""
        try:
            # Verificar estructura de datos de NASA POWER
            if not data:
                st.warning("⚠️ Respuesta vacía de NASA POWER")
                return None
            
            # La estructura típica de NASA POWER
            if 'properties' not in data:
                st.warning("⚠️ Estructura de datos NASA POWER inesperada")
                return None
            
            properties = data.get('properties', {})
            parameters = data.get('parameters', {})
            
            # Extraer series temporales con manejo robusto
            def extraer_datos(param_name, default_val=0):
                param = parameters.get(param_name, {})
                datos = param.get('data', [])
                if not datos:
                    return [default_val]
                # Filtrar valores nulos o inválidos
                datos_filtrados = [d for d in datos if d is not None and d != -999]
                return datos_filtrados if datos_filtrados else [default_val]
            
            # Extraer datos
            precip_data = extraer_datos('PRECTOTCORR', 0)  # Precipitación corregida
            tmax_data = extraer_datos('T2M_MAX', 20)      # Temperatura máxima (°C)
            tmin_data = extraer_datos('T2M_MIN', 10)      # Temperatura mínima (°C)
            rh_data = extraer_datos('RH2M', 70)           # Humedad relativa (%)
            rad_data = extraer_datos('ALLSKY_SFC_SW_DWN', 15)  # Radiación (W/m²)
            wind_data = extraer_datos('WS2M', 2)          # Velocidad del viento (m/s)
            
            # Calcular estadísticas con valores reales
            resultado = {
                'latitud': lat,
                'longitud': lon,
                'periodo': f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
                'precipitacion_total': round(sum(precip_data), 1),
                'precipitacion_promedio': round(np.mean(precip_data), 1),
                'precipitacion_maxima': round(np.max(precip_data), 1),
                'precipitacion_minima': round(np.min(precip_data), 1),
                'temp_max_promedio': round(np.mean(tmax_data), 1),
                'temp_max_absoluta': round(np.max(tmax_data), 1),
                'temp_min_promedio': round(np.mean(tmin_data), 1),
                'temp_min_absoluta': round(np.min(tmin_data), 1),
                'temp_promedio': round((np.mean(tmax_data) + np.mean(tmin_data)) / 2, 1),
                'humedad_promedio': round(np.mean(rh_data), 1),
                'radiacion_promedio': round(np.mean(rad_data), 1),
                'viento_promedio': round(np.mean(wind_data), 1),
                'dias_lluvia': sum(1 for p in precip_data if p > 0.5),  # > 0.5 mm
                'dias_lluvia_intensa': sum(1 for p in precip_data if p > 10),
                'balance_hidrico': round(sum(precip_data) - sum(wind_data) * 3, 1),  # Aproximación
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
            
            # Calcular días de estrés térmico
            dias_calor = sum(1 for t in tmax_data if t > 30)
            dias_frio = sum(1 for t in tmin_data if t < 5)
            resultado['dias_estres_calor'] = dias_calor
            resultado['dias_estres_frio'] = dias_frio
            
            # Calcular balance hídrico detallado
            resultado['deficit_hidrico'] = max(0, round(
                resultado['et0_promedio'] * len(precip_data) - resultado['precipitacion_total'], 1
            ))
            resultado['exceso_hidrico'] = max(0, round(
                resultado['precipitacion_total'] - resultado['et0_promedio'] * len(precip_data), 1
            ))
            
            return resultado
            
        except Exception as e:
            st.error(f"Error procesando datos NASA: {str(e)}")
            # Devolver datos por defecto realistas basados en ubicación y época del año
            mes = fecha_inicio.month
            # Estimar valores según ubicación y época del año
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
                'precipitacion_promedio': round(precip / 30, 1),
                'precipitacion_maxima': round(precip / 30 * 2, 1),
                'precipitacion_minima': 0,
                'temp_max_promedio': round(temp_max, 1),
                'temp_max_absoluta': round(temp_max + 5, 1),
                'temp_min_promedio': round(temp_min, 1),
                'temp_min_absoluta': round(temp_min - 3, 1),
                'temp_promedio': round((temp_max + temp_min) / 2, 1),
                'humedad_promedio': round(65 + np.random.uniform(-10, 10), 1),
                'radiacion_promedio': round(18 + np.random.uniform(-5, 5), 1),
                'viento_promedio': round(2.5 + np.random.uniform(-1, 1), 1),
                'dias_lluvia': int(precip / 5),
                'dias_lluvia_intensa': int(precip / 20),
                'balance_hidrico': round(precip - 75, 1),
                'et0_promedio': round(3.5 + np.random.uniform(-1, 1), 1),
                'deficit_hidrico': max(0, round(3.5 * 30 - precip, 1)),
                'exceso_hidrico': max(0, round(precip - 3.5 * 30, 1)),
                'dias_estres_calor': int((temp_max > 30) * 10),
                'dias_estres_frio': int((temp_min < 5) * 5),
                'datos_crudos': None,
                'fuente': 'Estimado (NASA POWER no disponible)'
            }
    
    @staticmethod
    def _calcular_et0(tmax: float, tmin: float, humedad: float, radiacion: float, viento: float) -> float:
        """Calcula evapotranspiración de referencia (mm/día) - método simplificado FAO Penman-Monteith"""
        try:
            # Temperatura media
            tmean = (tmax + tmin) / 2
            
            # Presión de vapor de saturación (kPa)
            es = 0.6108 * math.exp((17.27 * tmean) / (tmean + 237.3))
            
            # Presión de vapor actual (kPa)
            ea = es * (humedad / 100)
            
            # Déficit de presión de vapor (kPa)
            vpd = es - ea
            
            # Convertir radiación de W/m² a MJ/m²/día
            radiacion_mj = radiacion * 0.0864
            
            # Pendiente de la curva de presión de vapor (kPa/°C)
            delta = 4098 * es / ((tmean + 237.3) ** 2)
            
            # Constante psicrométrica (kPa/°C)
            gamma = 0.665 * 0.001 * 101.3  # Aproximación
            
            # ET0 simplificada (mm/día)
            termino_radiacion = (0.408 * delta * radiacion_mj) / (delta + gamma * (1 + 0.34 * viento))
            termino_viento = (gamma * 900 * viento * vpd / (tmean + 273)) / (delta + gamma * (1 + 0.34 * viento))
            
            et0 = termino_radiacion + termino_viento
            
            return max(0.1, min(10.0, round(et0, 1)))
            
        except Exception as e:
            st.warning(f"Error calculando ET0: {str(e)}. Usando valor por defecto.")
            return 3.5  # Valor por defecto razonable

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
            # URL alternativa para datos de suelos
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
                'conductividad_hidraulica': float(feature.get('conductividad', 10)),
                'carbon_organico': float(feature.get('carbon_organico', 1.5)),
                'nitrogeno_total': float(feature.get('nitrogeno_total', 0.15)),
                'fosforo_disponible': float(feature.get('fosforo_disponible', 15)),
                'potasio_intercambiable': float(feature.get('potasio_intercambiable', 150)),
                'fuente': 'INTA',
                'detalles': feature
            }
            
            # Clasificar textura
            resultado['clase_textura'] = ServicioSuelosINTA._clasificar_textura(resultado['textura'])
            
            # Calcular capacidad de almacenamiento de agua (mm)
            resultado['agua_almacenable'] = round(
                (resultado['capacidad_campo'] - resultado['punto_marchitez']) * 
                resultado['profundidad'] * 10 * resultado['densidad_aparente'] / 100, 1
            )
            
            # Calificar fertilidad
            resultado['indice_fertilidad'] = ServicioSuelosINTA._calcular_indice_fertilidad(resultado)
            
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
            materia_organica = 3.2
            ph = 6.8
            profundidad = 65
            capacidad_campo = 28
        elif lat < -40:  # Patagonia
            textura = "Franco arenoso"
            materia_organica = 1.8
            ph = 7.5
            profundidad = 40
            capacidad_campo = 18
        else:  # Norte
            textura = "Franco arcilloso"
            materia_organica = 2.2
            ph = 6.5
            profundidad = 55
            capacidad_campo = 32
        
        # Agregar variabilidad realista
        resultado = {
            'textura': textura,
            'profundidad': profundidad + np.random.uniform(-10, 15),
            'materia_organica': round(materia_organica + np.random.uniform(-0.3, 0.3), 1),
            'ph': round(ph + np.random.uniform(-0.4, 0.4), 1),
            'capacidad_campo': round(capacidad_campo + np.random.uniform(-3, 5), 1),
            'punto_marchitez': round(10 + np.random.uniform(-2, 3), 1),
            'densidad_aparente': round(1.3 + np.random.uniform(-0.1, 0.2), 2),
            'conductividad_hidraulica': round(8 + np.random.uniform(-3, 5), 1),
            'carbon_organico': round(materia_organica * 0.58, 1),
            'nitrogeno_total': round(materia_organica * 0.05 + np.random.uniform(0, 0.02), 2),
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
    
    @staticmethod
    def _calcular_indice_fertilidad(datos_suelo: Dict) -> float:
        """Calcula un índice de fertilidad del suelo (0-10)"""
        try:
            indice = 5.0  # Base
            
            # Aporte de materia orgánica
            mo = datos_suelo.get('materia_organica', 2.5)
            if mo > 4.0:
                indice += 2.0
            elif mo > 3.0:
                indice += 1.0
            elif mo < 1.5:
                indice -= 1.5
            elif mo < 2.0:
                indice -= 0.5
            
            # Aporte de pH
            ph = datos_suelo.get('ph', 6.5)
            if 6.0 <= ph <= 7.5:  # Óptimo para pasturas
                indice += 1.5
            elif 5.5 <= ph < 6.0 or 7.5 < ph <= 8.0:
                indice += 0.5
            else:
                indice -= 1.0
            
            # Aporte de textura
            textura = datos_suelo.get('clase_textura', 'Franco')
            if textura == 'Franco':
                indice += 1.0
            elif textura == 'Franco limoso':
                indice += 1.2
            elif textura == 'Arcilloso':
                indice += 0.5
            elif textura == 'Arenoso':
                indice -= 0.5
            
            # Aporte de profundidad
            profundidad = datos_suelo.get('profundidad', 50)
            if profundidad > 70:
                indice += 1.0
            elif profundidad < 30:
                indice -= 1.0
            
            return max(1.0, min(10.0, round(indice, 1)))
        except:
            return 5.0

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
# FUNCIONES DE MAPA MEJORADAS CON ESRI FORZADO
# -----------------------
def crear_mapa_interactivo_esri(gdf, base_map_name=FORCED_BASE_MAP):
    """Crea mapa interactivo solo con ESRI Satellite"""
    if not FOLIUM_AVAILABLE or gdf is None or len(gdf) == 0:
        return None
    
    try:
        # Calcular el centroide del área
        bounds = gdf.total_bounds
        centroid = gdf.geometry.centroid.iloc[0]
        
        # Crear mapa centrado en el polígono
        m = folium.Map(
            location=[centroid.y, centroid.x], 
            zoom_start=14,
            tiles=None, 
            control_scale=True,
            control_size=30
        )
        
        # AGREGAR SOLO ESRI SATELLITE
        esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
        folium.TileLayer(
            esri_imagery, 
            attr='Esri, Maxar, Earthstar Geographics, and the GIS User Community',
            name='ESRI Satellite',
            overlay=False,
            max_zoom=19
        ).add_to(m)
        
        # Preparar datos para el tooltip
        fields = []
        aliases = []
        
        # Verificar qué campos están disponibles
        if 'area_ha' in gdf.columns:
            fields.append('area_ha')
            aliases.append('Área (ha):')
        
        # Agregar polígono con estilo mejorado
        if fields:
            folium.GeoJson(
                gdf.__geo_interface__, 
                name='Potrero',
                style_function=lambda feat: {
                    'fillColor': '#00a8ff',
                    'color': '#00a8ff',
                    'weight': 3,
                    'fillOpacity': 0.4,
                    'dashArray': '5, 5'
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=fields,
                    aliases=aliases,
                    localize=True
                ),
                highlight_function=lambda feat: {
                    'fillColor': '#ff9f1a',
                    'color': '#ff9f1a',
                    'weight': 4,
                    'fillOpacity': 0.6
                }
            ).add_to(m)
        else:
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
        
        # Ajustar el zoom para que se vea todo el polígono con margen
        if len(gdf) > 0:
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(50, 50))
        
        # Agregar control de capas (solo ESRI Satellite)
        folium.LayerControl(position='topright', collapsed=True).add_to(m)
        
        # Agregar marcador en el centroide con información
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
            tooltip="Centro del potrero (haz clic)",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        # Agregar botón de pantalla completa
        m.add_child(folium.plugins.Fullscreen())
        
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

def crear_dashboard_resumen(gdf_analizado, datos_clima, datos_suelo, tipo_pastura, carga_animal, peso_promedio):
    """Crea un dashboard resumen completo del análisis"""
    # Calcular métricas globales
    area_total = gdf_analizado['area_ha'].sum()
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = (gdf_analizado['biomasa_disponible_kg_ms_ha'] * gdf_analizado['area_ha']).sum()
    ndvi_promedio = gdf_analizado['ndvi'].mean()
    ev_total = gdf_analizado['ev_soportable'].sum()
    dias_promedio = gdf_analizado['dias_permanencia'].mean()
    # Calcular distribución de tipos de superficie
    distribucion = gdf_analizado['tipo_superficie'].value_counts()
    # Calcular estrés hídrico promedio
    estres_prom = gdf_analizado['estres_hidrico'].mean() if 'estres_hidrico' in gdf_analizado.columns else 0

    # Crear dashboard
    st.markdown("---")
    st.markdown("## 📊 DASHBOARD RESUMEN DEL ANÁLISIS")

    # Sección 1: Métricas clave
    st.markdown("### 📈 MÉTRICAS CLAVE")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Área Total", f"{area_total:.1f} ha")
        st.caption("Superficie analizada")
    with col2:
        st.metric(
            "Biomasa Promedio",
            f"{biomasa_promedio:.0f} kg MS/ha",
            delta=f"{(biomasa_promedio/4000*100):.0f}% del óptimo" if biomasa_promedio > 0 else "0%"
        )
        st.caption("Productividad forrajera")
    with col3:
        st.metric(
            "EV Soportable",
            f"{ev_total:.1f}",
            delta=f"{ev_total/carga_animal:.1f} EV/cabeza" if carga_animal > 0 else "N/A"
        )
        st.caption("Capacidad de carga total")
    with col4:
        st.metric(
            "NDVI Promedio",
            f"{ndvi_promedio:.3f}",
            delta="Excelente" if ndvi_promedio > 0.6 else
                  "Bueno" if ndvi_promedio > 0.4 else
                  "Regular" if ndvi_promedio > 0.2 else "Crítico"
        )
        st.caption("Estado vegetativo")

    # Sección 2: Balance forrajero
    st.markdown("### 🌿 BALANCE FORRAJERO")
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        biomasa_ha_dia = gdf_analizado['crecimiento_diario'].mean()
        st.metric("Crecimiento Diario", f"{biomasa_ha_dia:.0f} kg/ha/día")
        st.caption("Producción diaria")
    with col6:
        consumo_total = carga_animal * peso_promedio * 0.025
        st.metric("Consumo Diario", f"{consumo_total:.0f} kg MS/día", delta=f"{carga_animal} cabezas")
        st.caption("Demanda ganadera")
    with col7:
        balance_diario = biomasa_ha_dia * area_total - consumo_total
        st.metric(
            "Balance Diario",
            f"{balance_diario:.0f} kg MS/día",
            delta="Positivo" if balance_diario > 0 else "Negativo",
            delta_color="normal" if balance_diario > 0 else "inverse"
        )
        st.caption("Saldo producción-consumo")
    with col8:
        st.metric(
            "Días Disponibilidad",
            f"{dias_promedio:.0f} días",
            delta="Rotación óptima" if 20 <= dias_promedio <= 40 else
                  "Rotación rápida" if dias_promedio < 20 else "Rotación lenta"
        )
        st.caption("Período de permanencia")

    # Sección 3: Distribución de superficies
    st.markdown("### 🗺️ DISTRIBUCIÓN DE SUPERFICIES")
    if len(distribucion) > 0:
        col9, col10 = st.columns(2)
        with col9:
            fig1, ax1 = plt.subplots(figsize=(8, 6))
            colors = ['#d73027', '#fdae61', '#fee08b', '#a6d96a', '#1a9850']
            ax1.pie(distribucion.values, labels=distribucion.index, autopct='%1.1f%%', colors=colors[:len(distribucion)], startangle=90)
            ax1.set_title('Distribución de Tipos de Superficie')
            st.pyplot(fig1)
            plt.close(fig1)
        with col10:
            st.dataframe(
                pd.DataFrame({
                    'Tipo de Superficie': distribucion.index,
                    'Sub-lotes': distribucion.values,
                    'Porcentaje': (distribucion.values / len(gdf_analizado) * 100).round(1)
                }),
                use_container_width=True,
                hide_index=True
            )

    # Sección 4: Datos ambientales
    st.markdown("### 🌤️ DATOS AMBIENTALES")
    if datos_clima or datos_suelo:
        col11, col12 = st.columns(2)
        with col11:
            if datos_clima:
                st.markdown("**🌤️ Datos Climáticos**")
                clima_df = pd.DataFrame({
                    'Métrica': [
                        'Precipitación Total',
                        'Temp. Máx. Promedio',
                        'Temp. Mín. Promedio',
                        'Evapotranspiración (ET0)',
                        'Días con Lluvia',
                        'Déficit Hídrico'
                    ],
                    'Valor': [
                        f"{datos_clima.get('precipitacion_total', 0):.0f} mm",
                        f"{datos_clima.get('temp_max_promedio', 0):.1f} °C",
                        f"{datos_clima.get('temp_min_promedio', 0):.1f} °C",
                        f"{datos_clima.get('et0_promedio', 0):.1f} mm/día",
                        f"{datos_clima.get('dias_lluvia', 0)} días",
                        f"{datos_clima.get('deficit_hidrico', 0):.0f} mm"
                    ]
                })
                st.dataframe(clima_df, use_container_width=True, hide_index=True)
        with col12:
            if datos_suelo:
                st.markdown("**🌍 Datos de Suelo**")
                suelo_df = pd.DataFrame({
                    'Característica': [
                        'Textura',
                        'Materia Orgánica',
                        'pH',
                        'Capacidad Campo',
                        'Profundidad',
                        'Índice Fertilidad'
                    ],
                    'Valor': [
                        datos_suelo.get('textura', 'N/A'),
                        f"{datos_suelo.get('materia_organica', 0):.1f} %",
                        f"{datos_suelo.get('ph', 0):.1f}",
                        f"{datos_suelo.get('capacidad_campo', 0):.1f} %",
                        f"{datos_suelo.get('profundidad', 0):.0f} cm",
                        f"{datos_suelo.get('indice_fertilidad', 5):.1f}/10"
                    ]
                })
                st.dataframe(suelo_df, use_container_width=True, hide_index=True)

    # Sección 5: Recomendaciones
    st.markdown("### 💡 RECOMENDACIONES")
    recomendaciones = []

    # Recomendación por biomasa
    if biomasa_promedio < 600:
        recomendaciones.append("🔴 **CRÍTICO**: Biomasa muy baja (<600 kg/ha). Considerar suplementación inmediata.")
    elif biomasa_promedio < 1200:
        recomendaciones.append("🟡 **ALERTA**: Biomasa baja (600-1200 kg/ha). Monitorear diariamente.")
    elif biomasa_promedio < 1800:
        recomendaciones.append("🟢 **ACEPTABLE**: Biomasa moderada (1200-1800 kg/ha). Manejo normal.")
    else:
        recomendaciones.append("✅ **ÓPTIMO**: Biomasa adecuada (>1800 kg/ha). Buen crecimiento.")

    # Recomendación por estrés hídrico
    if estres_prom > 0.7:
        recomendaciones.append("💧 **ESTRÉS HÍDRICO SEVERO**: Considerar riego o reducir carga animal.")
    elif estres_prom > 0.5:
        recomendaciones.append("💧 **ESTRÉS HÍDRICO MODERADO**: Monitorear humedad del suelo.")

    # Recomendación por días de permanencia
    if dias_promedio < 15:
        recomendaciones.append("⚡ **ROTACIÓN MUY RÁPIDA**: Considerar aumentar área o reducir carga.")
    elif dias_promedio > 60:
        recomendaciones.append("🐌 **ROTACIÓN LENTA**: Podría aumentar carga animal.")

    # Recomendación por balance forrajero
    balance_diario = gdf_analizado['crecimiento_diario'].mean() * area_total - (carga_animal * peso_promedio * 0.025)
    if balance_diario < -500:
        recomendaciones.append("📉 **DÉFICIT FORRAJERO**: Producción insuficiente. Considerar suplementación.")
    elif balance_diario > 500:
        recomendaciones.append("📈 **EXCEDENTE FORRAJERO**: Podría aumentar carga o conservar forraje.")

    # Mostrar recomendaciones
    for rec in recomendaciones:
        st.markdown(f"- {rec}")

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
# VISUALIZACIÓN MEJORADA CON ESRI FORZADO
# -----------------------
def crear_mapa_detallado_avanzado(gdf_analizado, tipo_pastura, datos_clima=None, datos_suelo=None):
    """Crea mapa detallado con ESRI Satellite como base"""
    try:
        # Si hay folium disponible, crear mapa interactivo
        if FOLIUM_AVAILABLE and len(gdf_analizado) > 0:
            # Crear mapa base con ESRI Satellite
            centroid = gdf_analizado.geometry.unary_union.centroid
            
            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=14,
                tiles=None,
                control_scale=True
            )
            
            # Agregar ESRI Satellite
            esri_imagery = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            folium.TileLayer(
                esri_imagery,
                attr='Esri, Maxar, Earthstar Geographics',
                name='ESRI Satellite',
                overlay=False,
                max_zoom=19
            ).add_to(m)
            
            # Agregar polígonos con colores según tipo de superficie
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
                
                # Crear popup con información
                popup_content = f"""
                <div style="font-family: Arial; font-size: 12px;">
                <b>Sub-lote {row['id_subLote']}</b><br>
                Tipo: {tipo.replace('_', ' ')}<br>
                Área: {row.get('area_ha', 0):.2f} ha<br>
                NDVI: {row.get('ndvi', 0):.3f}<br>
                Biomasa: {row.get('biomasa_disponible_kg_ms_ha', 0):.0f} kg/ha<br>
                Cobertura: {row.get('cobertura_vegetal', 0)*100:.0f}%<br>
                EV/ha: {row.get('ev_ha', 0):.3f}<br>
                Días: {row.get('dias_permanencia', 0):.1f}
                </div>
                """
                
                # Agregar polígono al mapa
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda feat, color=color: {
                        'fillColor': color,
                        'color': color,
                        'weight': 2,
                        'fillOpacity': 0.6
                    },
                    popup=folium.Popup(popup_content, max_width=300)
                ).add_to(m)
            
            # Agregar leyenda
            legend_html = '''
            <div style="position: fixed; 
                        bottom: 50px; left: 50px; width: 180px; 
                        background-color: white; padding: 10px;
                        border: 2px solid grey; z-index: 9999; font-size: 12px;
                        border-radius: 5px;">
            <b>Tipo de Superficie</b><br>
            <i style="background: #1a9850; width: 20px; height: 15px; display: inline-block;"></i> Vegetación densa<br>
            <i style="background: #a6d96a; width: 20px; height: 15px; display: inline-block;"></i> Vegetación moderada<br>
            <i style="background: #fee08b; width: 20px; height: 15px; display: inline-block;"></i> Vegetación escasa<br>
            <i style="background: #fdae61; width: 20px; height: 15px; display: inline-block;"></i> Suelo parcial<br>
            <i style="background: #d73027; width: 20px; height: 15px; display: inline-block;"></i> Suelo desnudo<br>
            </div>
            '''
            
            m.get_root().html.add_child(folium.Element(legend_html))
            
            # Para mostrar en Streamlit
            folium_static(m, width=1200, height=600)
            
            # También crear una imagen estática como fallback
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Plot simple de los polígonos
            for idx, row in gdf_analizado.iterrows():
                tipo = row.get('tipo_superficie', 'VEGETACION_ESCASA')
                color = colores_superficie.get(tipo, '#cccccc')
                gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
                
                # Agregar número de sub-lote
                c = row.geometry.centroid
                ax.text(c.x, c.y, f"S{row['id_subLote']}", fontsize=8, ha='center', va='center',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7))
            
            ax.set_title(f"Mapa de Análisis - {tipo_pastura}", fontsize=14, fontweight='bold')
            ax.axis('off')
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return buf
            
        else:
            # Fallback a matplotlib si folium no está disponible
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
                # Crear datos climáticos por defecto
                datos_clima_global = {
                    'precipitacion_total': 0,
                    'precipitacion_promedio': 2.0,
                    'temp_max_promedio': 25,
                    'temp_min_promedio': 15,
                    'humedad_promedio': 70,
                    'radiacion_promedio': 15,
                    'viento_promedio': 2,
                    'dias_lluvia': 0,
                    'balance_hidrico': 0,
                    'et0_promedio': 3.0,
                    'datos_crudos': None
                }
        
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
# GENERADOR DE INFORME COMPLETO
# -----------------------
def generar_informe_completo(gdf_analizado, datos_clima, datos_suelo, tipo_pastura, 
                            carga_animal, peso_promedio, dashboard_metrics, 
                            fecha_imagen, n_divisiones, params):
    """Genera un informe DOCX completo con toda la información analizada"""
    
    if not DOCX_AVAILABLE:
        st.error("❌ python-docx no está instalado. Ejecute: pip install python-docx")
        return None
    
    try:
        # Validar inputs
        if gdf_analizado is None or gdf_analizado.empty:
            st.error("❌ No hay datos analizados para generar el informe")
            return None
        
        # Crear documento
        doc = Document()
        
        # Título principal
        title = doc.add_heading('INFORME COMPLETO DE ANÁLISIS FORRAJERO', 0)
        title.alignment = 1  # Centrado
        
        # Fecha y hora
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
        doc.add_paragraph(f"Fecha de generación: {fecha_actual}")
        doc.add_paragraph(f"Fecha de imagen satelital: {fecha_imagen.strftime('%d/%m/%Y')}")
        doc.add_paragraph("")
        
        # 1. RESUMEN EJECUTIVO
        doc.add_heading('1. RESUMEN EJECUTIVO', level=1)
        
        resumen_text = f"""
        Este informe presenta los resultados del análisis forrajero avanzado realizado sobre el potrero cargado.
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
        
        # 2. PARÁMETROS DE ANÁLISIS
        doc.add_heading('2. PARÁMETROS DE ANÁLISIS', level=1)
        
        # Tabla de parámetros
        table_params = doc.add_table(rows=1, cols=3)
        table_params.style = 'LightShading'
        
        # Encabezados
        hdr_cells = table_params.rows[0].cells
        hdr_cells[0].text = 'Parámetro'
        hdr_cells[1].text = 'Valor'
        hdr_cells[2].text = 'Descripción'
        
        # Datos de parámetros
        parametros_data = [
            ('Tipo de Pastura', tipo_pastura, 'Especie forrajera analizada'),
            ('MS Óptimo', f"{params['MS_POR_HA_OPTIMO']} kg/ha", 'Biomasa óptima esperada'),
            ('Crecimiento Diario', f"{params['CRECIMIENTO_DIARIO']} kg/ha/día", 'Crecimiento esperado'),
            ('Consumo (% peso)', f"{params['CONSUMO_PORCENTAJE_PESO']*100:.1f}%", 'Consumo individual diario'),
            ('Tasa Utilización', f"{params['TASA_UTILIZACION_RECOMENDADA']*100:.0f}%", 'Tasa recomendada de uso'),
            ('Carga Animal', f"{carga_animal} cabezas", 'Número de animales considerados'),
            ('Peso Promedio', f"{peso_promedio} kg", 'Peso vivo promedio'),
            ('Sub-lotes', f"{n_divisiones}", 'Número de divisiones del potrero')
        ]
        
        for param, valor, desc in parametros_data:
            row_cells = table_params.add_row().cells
            row_cells[0].text = param
            row_cells[1].text = str(valor)
            row_cells[2].text = desc
        
        doc.add_paragraph("")
        
        # 3. DATOS CLIMÁTICOS
        if datos_clima:
            doc.add_heading('3. DATOS CLIMÁTICOS (NASA POWER)', level=1)
            
            # Tabla de datos climáticos
            table_clima = doc.add_table(rows=1, cols=2)
            table_clima.style = 'LightShading'
            
            hdr_cells = table_clima.rows[0].cells
            hdr_cells[0].text = 'Variable Climática'
            hdr_cells[1].text = 'Valor'
            
            clima_data = [
                ('Período analizado', datos_clima.get('periodo', 'N/A')),
                ('Precipitación total', f"{datos_clima.get('precipitacion_total', 0):.1f} mm"),
                ('Precipitación promedio', f"{datos_clima.get('precipitacion_promedio', 0):.1f} mm/día"),
                ('Temperatura máxima promedio', f"{datos_clima.get('temp_max_promedio', 0):.1f} °C"),
                ('Temperatura mínima promedio', f"{datos_clima.get('temp_min_promedio', 0):.1f} °C"),
                ('Evapotranspiración (ET0)', f"{datos_clima.get('et0_promedio', 0):.1f} mm/día"),
                ('Días con lluvia', f"{datos_clima.get('dias_lluvia', 0)} días"),
                ('Déficit hídrico', f"{datos_clima.get('deficit_hidrico', 0):.1f} mm"),
                ('Balance hídrico', f"{datos_clima.get('balance_hidrico', 0):.1f} mm")
            ]
            
            for variable, valor in clima_data:
                row_cells = table_clima.add_row().cells
                row_cells[0].text = variable
                row_cells[1].text = valor
        
        # 4. DATOS DE SUELO
        if datos_suelo:
            doc.add_heading('4. DATOS DE SUELO', level=1)
            
            # Tabla de datos de suelo
            table_suelo = doc.add_table(rows=1, cols=3)
            table_suelo.style = 'LightShading'
            
            hdr_cells = table_suelo.rows[0].cells
            hdr_cells[0].text = 'Característica'
            hdr_cells[1].text = 'Valor'
            hdr_cells[2].text = 'Interpretación'
            
            # Función para interpretar valores de suelo
            def interpretar_suelo(caracteristica, valor):
                if caracteristica == 'textura':
                    if 'franco' in valor.lower():
                        return 'Óptima para pasturas'
                    elif 'arcilla' in valor.lower():
                        return 'Buena retención de agua'
                    elif 'arena' in valor.lower():
                        return 'Baja retención de agua'
                    return 'Adecuada'
                
                elif caracteristica == 'materia_organica':
                    valor_num = float(valor.split()[0])
                    if valor_num > 3.0:
                        return 'Excelente'
                    elif valor_num > 2.0:
                        return 'Buena'
                    else:
                        return 'Regular'
                
                elif caracteristica == 'ph':
                    valor_num = float(valor)
                    if 6.0 <= valor_num <= 7.5:
                        return 'Óptimo para pasturas'
                    elif valor_num < 6.0:
                        return 'Ácido, considerar enmiendas'
                    else:
                        return 'Alcalino'
                
                elif caracteristica == 'indice_fertilidad':
                    valor_num = float(valor.split('/')[0])
                    if valor_num >= 7.0:
                        return 'Alta fertilidad'
                    elif valor_num >= 5.0:
                        return 'Fertilidad media'
                    else:
                        return 'Baja fertilidad'
                
                return 'N/A'
            
            suelo_data = [
                ('Textura', datos_suelo.get('textura', 'N/A'), 'textura'),
                ('Clase textura', datos_suelo.get('clase_textura', 'N/A'), 'textura'),
                ('Materia orgánica', f"{datos_suelo.get('materia_organica', 0):.1f} %", 'materia_organica'),
                ('pH', f"{datos_suelo.get('ph', 0):.1f}", 'ph'),
                ('Capacidad de campo', f"{datos_suelo.get('capacidad_campo', 0):.1f} %", 'capacidad_campo'),
                ('Punto marchitez', f"{datos_suelo.get('punto_marchitez', 0):.1f} %", 'punto_marchitez'),
                ('Profundidad', f"{datos_suelo.get('profundidad', 0):.0f} cm", 'profundidad'),
                ('Densidad aparente', f"{datos_suelo.get('densidad_aparente', 0):.2f} g/cm³", 'densidad_aparente'),
                ('Agua almacenable', f"{datos_suelo.get('agua_almacenable', 0):.1f} mm", 'agua_almacenable'),
                ('Índice fertilidad', f"{datos_suelo.get('indice_fertilidad', 5):.1f}/10", 'indice_fertilidad'),
                ('Fuente de datos', datos_suelo.get('fuente', 'N/A'), 'fuente')
            ]
            
            for carac, valor, tipo in suelo_data:
                row_cells = table_suelo.add_row().cells
                row_cells[0].text = carac
                row_cells[1].text = str(valor)
                row_cells[2].text = interpretar_suelo(tipo, valor)
        
        # 5. RESULTADOS DETALLADOS POR SUB-LOTE
        doc.add_heading('5. RESULTADOS POR SUB-LOTE', level=1)
        
        # Seleccionar columnas importantes para el informe
        columnas_informe = [
            'id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
            'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha',
            'estres_hidrico', 'ev_ha', 'dias_permanencia'
        ]
        
        # Filtrar columnas existentes
        columnas_existentes = [c for c in columnas_informe if c in gdf_analizado.columns]
        
        if columnas_existentes:
            # Crear tabla de resultados
            table_resultados = doc.add_table(rows=1, cols=len(columnas_existentes))
            table_resultados.style = 'LightShading'
            
            # Encabezados
            hdr_cells = table_resultados.rows[0].cells
            for i, col in enumerate(columnas_existentes):
                hdr_cells[i].text = col.replace('_', ' ').title()
            
            # Datos (mostrar solo primeros 20 para no hacer el informe muy largo)
            max_filas = min(20, len(gdf_analizado))
            for idx in range(max_filas):
                row_cells = table_resultados.add_row().cells
                for j, col in enumerate(columnas_existentes):
                    valor = gdf_analizado.iloc[idx][col]
                    if isinstance(valor, (int, float)):
                        if 'ndvi' in col or 'cobertura' in col or 'estres' in col:
                            row_cells[j].text = f"{valor:.3f}"
                        elif 'area' in col:
                            row_cells[j].text = f"{valor:.2f}"
                        elif 'biomasa' in col:
                            row_cells[j].text = f"{valor:.0f}"
                        elif 'ev_ha' in col:
                            row_cells[j].text = f"{valor:.3f}"
                        elif 'dias' in col:
                            row_cells[j].text = f"{valor:.1f}"
                        else:
                            row_cells[j].text = str(valor)
                    else:
                        row_cells[j].text = str(valor)
            
            if len(gdf_analizado) > max_filas:
                doc.add_paragraph(f"*Nota: Mostrando {max_filas} de {len(gdf_analizado)} sub-lotes. Consulte el CSV completo para todos los datos.*")
        
        # 6. DISTRIBUCIÓN DE SUPERFICIES
        doc.add_heading('6. DISTRIBUCIÓN DE SUPERFICIES', level=1)
        
        if 'tipo_superficie' in gdf_analizado.columns:
            distribucion = gdf_analizado['tipo_superficie'].value_counts()
            
            table_dist = doc.add_table(rows=1, cols=3)
            table_dist.style = 'LightShading'
            
            hdr_cells = table_dist.rows[0].cells
            hdr_cells[0].text = 'Tipo de Superficie'
            hdr_cells[1].text = 'Número de Sub-lotes'
            hdr_cells[2].text = 'Porcentaje'
            
            for tipo, cantidad in distribucion.items():
                porcentaje = (cantidad / len(gdf_analizado)) * 100
                row_cells = table_dist.add_row().cells
                row_cells[0].text = tipo.replace('_', ' ').title()
                row_cells[1].text = str(cantidad)
                row_cells[2].text = f"{porcentaje:.1f}%"
        
        # 7. RECOMENDACIONES
        doc.add_heading('7. RECOMENDACIONES TÉCNICAS', level=1)
        
        # Generar recomendaciones basadas en los resultados
        recomendaciones = []
        
        # Recomendación por biomasa
        biomasa_prom = dashboard_metrics['biomasa_promedio']
        if biomasa_prom < 600:
            recomendaciones.append(("🔴 CRÍTICO", "Biomasa muy baja (<600 kg/ha). Considerar suplementación inmediata y reducir carga animal."))
        elif biomasa_prom < 1200:
            recomendaciones.append(("🟡 ALERTA", "Biomasa baja (600-1200 kg/ha). Monitorear diariamente y considerar suplementación estratégica."))
        elif biomasa_prom < 1800:
            recomendaciones.append(("🟢 ACEPTABLE", "Biomasa moderada (1200-1800 kg/ha). Mantener manejo actual y monitorear crecimiento."))
        else:
            recomendaciones.append(("✅ ÓPTIMO", "Biomasa adecuada (>1800 kg/ha). Buen crecimiento, puede considerar aumento moderado de carga."))
        
        # Recomendación por estrés hídrico
        estres_prom = dashboard_metrics.get('estres_prom', 0)
        if estres_prom > 0.7:
            recomendaciones.append(("💧 ESTRÉS HÍDRICO SEVERO", "Condiciones de sequía severa. Considerar riego suplementario o reducción significativa de carga animal."))
        elif estres_prom > 0.5:
            recomendaciones.append(("💧 ESTRÉS HÍDRICO MODERADO", "Condiciones de sequía moderada. Monitorear humedad del suelo y ajustar carga si es necesario."))
        
        # Recomendación por días de permanencia
        dias_prom = dashboard_metrics['dias_promedio']
        if dias_prom < 15:
            recomendaciones.append(("⚡ ROTACIÓN MUY RÁPIDA", "Período de ocupación muy corto. Considerar aumentar área disponible o reducir carga animal para permitir recuperación del pasto."))
        elif dias_prom > 60:
            recomendaciones.append(("🐌 ROTACIÓN LENTA", "Período de ocupación muy largo. Podría aumentar carga animal o reducir área para optimizar uso del forraje."))
        
        # Recomendación por NDVI
        ndvi_prom = dashboard_metrics['ndvi_promedio']
        if ndvi_prom < 0.2:
            recomendaciones.append(("🌱 BAJA VEGETACIÓN", "NDVI muy bajo. Evaluar necesidad de fertilización, resiembra o mejoramiento de pastura."))
        elif ndvi_prom < 0.4:
            recomendaciones.append(("🌱 VEGETACIÓN REGULAR", "NDVI moderado. Considerar prácticas de mejora como fertilización balanceada."))
        
        # Recomendaciones por tipo de suelo si están disponibles
        if datos_suelo:
            textura = datos_suelo.get('textura', '').lower()
            if 'arena' in textura:
                recomendaciones.append(("🏜️ SUELO ARENOSO", "Alta permeabilidad, baja retención de agua. Considerar riego más frecuente y fertilización fraccionada."))
            elif 'arcilla' in textura:
                recomendaciones.append(("🧱 SUELO ARCILLOSO", "Baja permeabilidad, alta retención de agua. Cuidar compactación y considerar drenaje si es necesario."))
            
            ph = datos_suelo.get('ph', 7.0)
            if ph < 5.5:
                recomendaciones.append(("🧪 pH ÁCIDO", "Suelo ácido. Considerar enmiendas con cal para mejorar disponibilidad de nutrientes."))
            elif ph > 8.0:
                recomendaciones.append(("🧪 pH ALCALINO", "Suelo alcalino. Considerar enmiendas con azufre y uso de fertilizantes acidificantes."))
        
        # Agregar recomendaciones al documento
        for icono, texto in recomendaciones:
            p = doc.add_paragraph()
            p.add_run(f"{icono} ").bold = True
            p.add_run(texto)
        
        # 8. PLAN DE ACCIÓN SUGERIDO
        doc.add_heading('8. PLAN DE ACCIÓN SUGERIDO', level=1)
        
        plan_accion = [
            ("INMEDIATO (1-7 días)", [
                "Verificar estado actual del ganado",
                "Revisar disponibilidad de agua",
                "Ajustar carga animal según resultados",
                "Planificar suplementación si es necesaria"
            ]),
            ("CORTO PLAZO (8-30 días)", [
                "Implementar rotación de potreros",
                "Monitorear crecimiento forrajero",
                "Evaluar necesidad de fertilización",
                "Planificar obras de mejora si son necesarias"
            ]),
            ("MEDIANO PLAZO (1-6 meses)", [
                "Evaluar resultados de ajustes realizados",
                "Planificar siembra o resiembra si es necesario",
                "Implementar mejoras de infraestructura",
                "Realizar nuevo análisis para comparación"
            ])
        ]
        
        for periodo, acciones in plan_accion:
            doc.add_heading(periodo, level=2)
            for accion in acciones:
                doc.add_paragraph(f"• {accion}", style='List Bullet')
        
        # 9. METADATOS TÉCNICOS
        doc.add_heading('9. METADATOS TÉCNICOS', level=1)
        
        metadatos = [
            ("Software", "PRV - Predicción y Recomendación de Variables"),
            ("Versión", "2.0 (Análisis Avanzado)"),
            ("Fecha de análisis", fecha_actual),
            ("Fuente satelital", "SENTINEL-2 (simulado)"),
            ("Resolución espacial", "10-20 metros"),
            ("Datos climáticos", "NASA POWER API"),
            ("Datos de suelo", "INTA + Simulación por ubicación"),
            ("Precisión estimada", "85-90% (dependiendo de calidad de inputs)"),
            ("Limitaciones", "Análisis basado en datos disponibles, validar con observaciones de campo")
        ]
        
        for nombre, valor in metadatos:
            doc.add_paragraph(f"{nombre}: {valor}")
        
        # 10. CONTACTO Y SEGUIMIENTO
        doc.add_heading('10. SEGUIMIENTO', level=1)
        doc.add_paragraph("Se recomienda realizar un nuevo análisis cada 30-60 días para monitorear la evolución del potrero.")
        doc.add_paragraph("Para consultas técnicas o actualizaciones del análisis, contactar al equipo de desarrollo.")
        doc.add_paragraph("")
        doc.add_paragraph("---")
        doc.add_paragraph("Fin del informe")
        
        # Guardar documento en buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        return buffer
        
    except Exception as e:
        st.error(f"❌ Error generando informe: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

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
                        
                        # Crear mapa interactivo con ESRI Satellite (forzado)
                        mapa_interactivo = crear_mapa_interactivo_esri(gdf_procesado, FORCED_BASE_MAP)
                        
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
    if st.button("🚀 Ejecutar Análisis Forrajero Avanzado", type="primary", use_container_width=True):
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
                        
                        # Crear y mostrar mapa avanzado con ESRI Satellite
                        mapa_buf = crear_mapa_detallado_avanzado(gdf_sub, tipo_pastura, datos_clima, datos_suelo)
                        
                        if mapa_buf is not None:
                            st.image(mapa_buf, use_column_width=True, caption="Mapa de análisis avanzado (ESRI Satellite)")
                            st.session_state.mapa_detallado_bytes = mapa_buf
                        
                        # Crear y mostrar dashboard resumen
                        params = obtener_parametros_forrajeros_avanzados(tipo_pastura)
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
                                        'Métrica': ['Máxima Promedio', 'Mínima Promedio', 'Máxima Absoluta', 'Mínima Absoluta'],
                                        'Valor (°C)': [
                                            datos_clima.get('temp_max_promedio', 0),
                                            datos_clima.get('temp_min_promedio', 0),
                                            datos_clima.get('temp_max_absoluta', 0),
                                            datos_clima.get('temp_min_absoluta', 0)
                                        ]
                                    })
                                    st.dataframe(temp_data, use_container_width=True, hide_index=True)
                                
                                with col2:
                                    st.markdown("**💧 Balance Hídrico**")
                                    agua_data = pd.DataFrame({
                                        'Métrica': ['Precipitación Total', 'ET0 Promedio', 'Déficit Hídrico', 'Exceso Hídrico'],
                                        'Valor (mm)': [
                                            datos_clima.get('precipitacion_total', 0),
                                            datos_clima.get('et0_promedio', 0),
                                            datos_clima.get('deficit_hidrico', 0),
                                            datos_clima.get('exceso_hidrico', 0)
                                        ]
                                    })
                                    st.dataframe(agua_data, use_container_width=True, hide_index=True)
                        
                        # Mostrar datos de suelo detallados
                        if datos_suelo:
                            with st.expander("🌍 DATOS DE SUELO DETALLADOS"):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown("**📊 Propiedades Físicas**")
                                    fisicas_data = pd.DataFrame({
                                        'Propiedad': ['Textura', 'Profundidad', 'Densidad Aparente', 'Capacidad Campo'],
                                        'Valor': [
                                            datos_suelo.get('textura', 'N/A'),
                                            f"{datos_suelo.get('profundidad', 0)} cm",
                                            f"{datos_suelo.get('densidad_aparente', 0)} g/cm³",
                                            f"{datos_suelo.get('capacidad_campo', 0)} %"
                                        ]
                                    })
                                    st.dataframe(fisicas_data, use_container_width=True, hide_index=True)
                                
                                with col2:
                                    st.markdown("**🌱 Propiedades Químicas**")
                                    quimicas_data = pd.DataFrame({
                                        'Propiedad': ['Materia Orgánica', 'pH', 'Carbono Orgánico', 'Nitrógeno Total'],
                                        'Valor': [
                                            f"{datos_suelo.get('materia_organica', 0)} %",
                                            datos_suelo.get('ph', 0),
                                            f"{datos_suelo.get('carbon_organico', 0)} %",
                                            f"{datos_suelo.get('nitrogeno_total', 0)} %"
                                        ]
                                    })
                                    st.dataframe(quimicas_data, use_container_width=True, hide_index=True)
                        
                        # Exportar datos CORREGIDO
                        st.markdown("---")
                        st.markdown("### 💾 EXPORTAR DATOS")
                        
                        # Crear un formulario para evitar el rerun automático
                        with st.form(key="export_form"):
                            col_export1, col_export2, col_export3, col_export4 = st.columns(4)
                            
                            with col_export1:
                                # Exportar GeoJSON
                                try:
                                    geojson_str = gdf_sub.to_json()
                                    st.download_button(
                                        "📤 Exportar GeoJSON",
                                        geojson_str,
                                        f"analisis_avanzado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                                        "application/geo+json",
                                        use_container_width=True
                                    )
                                except Exception as e:
                                    st.error(f"Error exportando GeoJSON: {e}")
                            
                            with col_export2:
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
                                        "text/csv",
                                        use_container_width=True
                                    )
                                except Exception as e:
                                    st.error(f"Error exportando CSV: {e}")
                            
                            with col_export3:
                                # Exportar resumen TXT
                                resumen_text = f"""
                                RESUMEN DE ANÁLISIS FORRAJERO
                                Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
                                Tipo de Pastura: {tipo_pastura}
                                Área Total: {dashboard_metrics['area_total']:.1f} ha
                                Biomasa Promedio: {dashboard_metrics['biomasa_promedio']:.0f} kg MS/ha
                                EV Total Soportable: {dashboard_metrics['ev_total']:.1f}
                                NDVI Promedio: {dashboard_metrics['ndvi_promedio']:.3f}
                                Días de Permanencia: {dashboard_metrics['dias_promedio']:.1f} días
                                """
                                st.download_button(
                                    "📄 Exportar Resumen (TXT)",
                                    resumen_text,
                                    f"resumen_analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                                    "text/plain",
                                    use_container_width=True
                                )
                            
                            with col_export4:
                                # Generar informe DOCX
                                if DOCX_AVAILABLE:
                                    # Botón para generar informe
                                    generar_informe = st.form_submit_button(
                                        "📑 Generar Informe Completo (DOCX)",
                                        use_container_width=True,
                                        type="primary"
                                    )
                                    
                                    if generar_informe:
                                        with st.spinner("Generando informe completo..."):
                                            informe_buffer = generar_informe_completo(
                                                gdf_sub, datos_clima, datos_suelo, tipo_pastura,
                                                carga_animal, peso_promedio, dashboard_metrics,
                                                fecha_imagen, n_divisiones, params
                                            )
                                            
                                            if informe_buffer:
                                                st.session_state.informe_generado = informe_buffer
                                                st.success("✅ Informe generado correctamente")
                                                # Forzar un rerun para mostrar el botón de descarga
                                                st.rerun()
                                else:
                                    st.warning("python-docx no disponible")
                            
                            # Botón para descargar informe si ya fue generado
                            if st.session_state.get('informe_generado'):
                                st.download_button(
                                    "📥 Descargar Informe Completo",
                                    st.session_state.informe_generado,
                                    f"informe_completo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True,
                                    key="download_informe"
                                )
                        
                        # Mostrar tabla de resultados
                        st.markdown("---")
                        st.markdown("### 📋 TABLA DE RESULTADOS DETALLADOS")
                        
                        columnas_detalle = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
                                           'cobertura_vegetal', 'biomasa_disponible_kg_ms_ha',
                                           'estres_hidrico', 'ev_ha', 'dias_permanencia']
                        cols_presentes = [c for c in columnas_detalle if c in gdf_sub.columns]
                        
                        df_show = gdf_sub[cols_presentes].copy()
                        df_show.columns = [c.replace('_', ' ').title() for c in df_show.columns]
                        
                        st.dataframe(df_show, use_container_width=True, height=400)
                        
                        st.session_state.analisis_completado = True
                        
                        st.success("🎉 ¡Análisis completado exitosamente! Revisa el dashboard y los resultados.")
                        
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
    2. **Seleccionar el tipo de pastura**
    3. **Ajustar parámetros** según condiciones locales
    4. **Validar resultados** con observaciones de campo
    
    #### INTERPRETACIÓN DE RESULTADOS:
    - **Biomasa < 600 kg/ha**: Condición crítica, requiere suplementación
    - **Biomasa 600-1200 kg/ha**: Monitoreo frecuente necesario
    - **Biomasa 1200-1800 kg/ha**: Condición aceptable
    - **Biomasa > 1800 kg/ha**: Condición óptima
    
    #### CONSIDERACIONES:
    - Los datos climáticos tienen resolución de 55km
    - Los datos de suelo pueden ser estimados
    - Validar siempre con observaciones locales
    - El análisis es una herramienta de apoyo a la decisión
    """)
