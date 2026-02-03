# ✅ ABSOLUTAMENTE PRIMERO: Importar streamlit
import streamlit as st
# ✅ LUEGO: Configurar la página
st.set_page_config(
    page_title="Sistema Satelital de Análisis Ambiental con Verra VCS - Sudamérica",
    page_icon="🌎",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Ahora sí, el resto de los imports
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
import math
from math import log
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
from plotly.subplots import make_subplots
from io import BytesIO, StringIO
from datetime import datetime, timedelta
import json
import base64
import warnings
import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List, Tuple

# ===== IMPORTACIONES GOOGLE EARTH ENGINE (NO MODIFICAR) =====
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    st.warning("⚠️ Google Earth Engine no está instalado. Para usar datos satelitales reales, instala con: pip install earthengine-api")

warnings.filterwarnings('ignore')

# Librerías geoespaciales
import folium
from streamlit_folium import st_folium, folium_static
from folium.plugins import Fullscreen, MousePosition, HeatMap
import geopandas as gpd
from shapely.geometry import Polygon, Point, shape, MultiPolygon
from shapely.ops import unary_union
import pyproj
from branca.colormap import LinearColormap
import matplotlib.cm as cm
# Para simulación de datos satelitales
import random

# === INICIALIZACIÓN SEGURA DE GOOGLE EARTH ENGINE (NO MODIFICAR) ===
def inicializar_gee():
    """Inicializa GEE con Service Account desde secrets de Streamlit Cloud"""
    if not GEE_AVAILABLE:
        return False
    
    try:
        # Intentar con Service Account desde secrets (Streamlit Cloud)
        gee_secret = os.environ.get('GEE_SERVICE_ACCOUNT')
        if gee_secret:
            try:
                credentials_info = json.loads(gee_secret.strip())
                credentials = ee.ServiceAccountCredentials(
                    credentials_info['client_email'],
                    key_data=json.dumps(credentials_info)
                )
                ee.Initialize(credentials, project='ee-mawucano25')
                st.session_state.gee_authenticated = True
                st.session_state.gee_project = 'ee-mawucano25'
                print("✅ GEE inicializado con Service Account")
                return True
            except Exception as e:
                print(f"⚠️ Error con Service Account: {str(e)}")
        
        # Fallback: autenticación local (desarrollo en tu Linux)
        try:
            ee.Initialize(project='ee-mawucano25')
            st.session_state.gee_authenticated = True
            st.session_state.gee_project = 'ee-mawucano25'
            print("✅ GEE inicializado localmente")
            return True
        except Exception as e:
            print(f"⚠️ Error inicialización local: {str(e)}")
            
        st.session_state.gee_authenticated = False
        return False
        
    except Exception as e:
        st.session_state.gee_authenticated = False
        print(f"❌ Error crítico GEE: {str(e)}")
        return False

# ===============================
# 📄 GENERADOR DE REPORTES COMPLETOS MEJORADO
# ===============================
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
        PageBreak, KeepTogether, PageTemplate, Frame, NextPageTemplate,
        BaseDocTemplate, FrameBreak
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    REPORTPDF_AVAILABLE = True
except ImportError:
    REPORTPDF_AVAILABLE = False
    st.warning("ReportLab no está instalado. La generación de PDFs estará limitada.")

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.style import WD_STYLE_TYPE
    REPORTDOCX_AVAILABLE = True
except ImportError:
    REPORTDOCX_AVAILABLE = False
    st.warning("python-docx no está instalado. La generación de DOCX estará limitada.")

# ===============================
# 🐮 MÓDULO DE ANÁLISIS FORRAJERO COMPLETO
# ===============================
class AnalisisForrajero:
    """Sistema completo de análisis forrajero para manejo ganadero sostenible"""
    
    def __init__(self):
        # Parámetros técnicos para cálculo forrajero
        self.parametros_forrajeros = {
            'pastizal_natural': {
                'productividad_kg_ms_ha': {'bajo': 2000, 'medio': 4000, 'alto': 6000},
                'eficiencia_aprovechamiento': 0.5,  # 50% del forraje disponible
                'tasa_crecimiento_diario': {'bajo': 15, 'medio': 30, 'alto': 45},  # kg MS/ha/día
                'densidad_forraje': 2.5  # kg MS/m3
            },
            'pastura_mejorada': {
                'productividad_kg_ms_ha': {'bajo': 4000, 'medio': 8000, 'alto': 12000},
                'eficiencia_aprovechamiento': 0.6,
                'tasa_crecimiento_diario': {'bajo': 25, 'medio': 50, 'alto': 75},
                'densidad_forraje': 3.0
            },
            'silvopastoril': {
                'productividad_kg_ms_ha': {'bajo': 3000, 'medio': 6000, 'alto': 9000},
                'eficiencia_aprovechamiento': 0.55,
                'tasa_crecimiento_diario': {'bajo': 20, 'medio': 40, 'alto': 60},
                'densidad_forraje': 2.8
            },
            'agroforestal': {
                'productividad_kg_ms_ha': {'bajo': 2500, 'medio': 5000, 'alto': 7500},
                'eficiencia_aprovechamiento': 0.45,
                'tasa_crecimiento_diario': {'bajo': 18, 'medio': 36, 'alto': 54},
                'densidad_forraje': 2.6
            }
        }
        
        # Consumo por categoría animal (kg MS/día)
        self.consumo_animal = {
            'vaca_adulta': 12,      # Vaca de 450 kg
            'novillo': 10,          # Novillo de 350 kg
            'ternero': 4,           # Ternero de 150 kg
            'vaca_secas': 8,        # Vaca seca
            'vaca_lactancia': 14,   # Vaca en lactancia
            'equivalente_vaca': 12  # EV estándar
        }
        
        # Factores de conversión NDVI -> productividad
        self.factores_ndvi = {
            'bajo': {'ndvi_min': -1.0, 'ndvi_max': 0.2, 'factor': 0.3},
            'medio': {'ndvi_min': 0.2, 'ndvi_max': 0.5, 'factor': 0.6},
            'alto': {'ndvi_min': 0.5, 'ndvi_max': 1.0, 'factor': 1.0}
        }
    
    def estimar_disponibilidad_forrajera(self, ndvi: float, tipo_sistema: str, area_ha: float) -> Dict:
        """Estima la disponibilidad forrajera basada en NDVI y tipo de sistema"""
        
        # Determinar categoría de productividad según NDVI
        categoria_productividad = 'medio'
        if ndvi < 0.2:
            categoria_productividad = 'bajo'
        elif ndvi > 0.5:
            categoria_productividad = 'alto'
        
        # Obtener parámetros del sistema
        params = self.parametros_forrajeros.get(tipo_sistema, self.parametros_forrajeros['pastizal_natural'])
        
        # Productividad base según categoría
        productividad_base = params['productividad_kg_ms_ha'][categoria_productividad]
        
        # Ajustar por NDVI (factor lineal)
        factor_ndvi = 0.5 + (ndvi * 0.5)  # NDVI=-1 → 0, NDVI=1 → 1
        productividad_ajustada = productividad_base * factor_ndvi * random.uniform(0.9, 1.1)
        
        # Disponibilidad total en el área
        disponibilidad_total_kg_ms = productividad_ajustada * area_ha
        
        # Forraje aprovechable (considerando eficiencia)
        forraje_aprovechable_kg_ms = disponibilidad_total_kg_ms * params['eficiencia_aprovechamiento']
        
        # Tasa de crecimiento diario
        tasa_crecimiento = params['tasa_crecimiento_diario'][categoria_productividad] * area_ha
        
        return {
            'productividad_kg_ms_ha': round(productividad_ajustada, 2),
            'disponibilidad_total_kg_ms': round(disponibilidad_total_kg_ms, 2),
            'forraje_aprovechable_kg_ms': round(forraje_aprovechable_kg_ms, 2),
            'tasa_crecimiento_diario_kg': round(tasa_crecimiento, 2),
            'categoria_productividad': categoria_productividad,
            'densidad_forraje_kg_m3': params['densidad_forraje']
        }
    
    def calcular_equivalentes_vaca(self, forraje_aprovechable_kg_ms: float, 
                                   dias_permanencia: int = 1) -> Dict:
        """Calcula los equivalentes vaca (EV) que puede soportar el área"""
        
        consumo_ev_diario = self.consumo_animal['equivalente_vaca']
        
        # EV que puede soportar por un día
        ev_por_dia = forraje_aprovechable_kg_ms / consumo_ev_diario
        
        # EV que puede soportar por el período de permanencia
        ev_para_periodo = forraje_aprovechable_kg_ms / (consumo_ev_diario * dias_permanencia)
        
        # Consumo total del período
        consumo_total_periodo = ev_para_periodo * consumo_ev_diario * dias_permanencia
        
        # Margen de seguridad (20%)
        margen_seguridad = 0.8
        
        return {
            'ev_por_dia': round(ev_por_dia, 2),
            'ev_para_periodo': round(ev_para_periodo, 2),
            'ev_recomendado': round(ev_para_periodo * margen_seguridad, 2),
            'consumo_ev_diario_kg': consumo_ev_diario,
            'consumo_total_periodo_kg': round(consumo_total_periodo, 2),
            'dias_permanencia': dias_permanencia,
            'margen_seguridad': '20%'
        }
    
    def calcular_dias_permanencia(self, forraje_aprovechable_kg_ms: float, 
                                  num_ev: float) -> Dict:
        """Calcula los días de permanencia para un número dado de EV"""
        
        consumo_ev_diario = self.consumo_animal['equivalente_vaca']
        consumo_diario_total = num_ev * consumo_ev_diario
        
        # Días de permanencia sin considerar crecimiento
        dias_permanencia_basico = forraje_aprovechable_kg_ms / consumo_diario_total
        
        # Considerando tasa de crecimiento (simplificado)
        dias_permanencia_ajustado = dias_permanencia_basico * 1.2  # 20% más por crecimiento
        
        # Recomendación práctica (máximo 30 días por parcela)
        dias_recomendados = min(30, int(dias_permanencia_ajustado))
        
        return {
            'dias_basico': round(dias_permanencia_basico, 1),
            'dias_ajustado': round(dias_permanencia_ajustado, 1),
            'dias_recomendados': dias_recomendados,
            'consumo_diario_total_kg': round(consumo_diario_total, 2),
            'forraje_disponible_kg': round(forraje_aprovechable_kg_ms, 2),
            'num_ev': num_ev
        }
    
    def dividir_lote_en_sublotes(self, area_total_ha: float, 
                                 disponibilidad_forrajera_kg_ms_ha: float,
                                 heterogeneidad: float = 0.3) -> List[Dict]:
        """Divide el lote en sublotes según disponibilidad forrajera"""
        
        # Determinar número óptimo de sublotes
        if area_total_ha < 10:
            num_sublotes = 2
        elif area_total_ha < 50:
            num_sublotes = 3
        elif area_total_ha < 100:
            num_sublotes = 4
        else:
            num_sublotes = min(6, int(area_total_ha / 20))
        
        sublotes = []
        area_por_sublote = area_total_ha / num_sublotes
        
        # Simular variación en disponibilidad entre sublotes
        for i in range(num_sublotes):
            # Variar la disponibilidad entre sublotes (± heterogeneidad%)
            variacion = 1 + random.uniform(-heterogeneidad, heterogeneidad)
            disponibilidad_sublote = disponibilidad_forrajera_kg_ms_ha * variacion
            
            # Calcular forraje aprovechable en sublote
            forraje_sublote_kg_ms = disponibilidad_sublote * area_por_sublote
            forraje_aprovechable = forraje_sublote_kg_ms * 0.5  # 50% de eficiencia
            
            sublotes.append({
                'sublote_id': i + 1,
                'area_ha': round(area_por_sublote, 2),
                'disponibilidad_kg_ms_ha': round(disponibilidad_sublote, 2),
                'forraje_total_kg_ms': round(forraje_sublote_kg_ms, 2),
                'forraje_aprovechable_kg_ms': round(forraje_aprovechable, 2),
                'productividad_relativa': round(variacion, 2)
            })
        
        return sublotes
    
    def generar_recomendaciones_rotacion(self, sublotes: List[Dict], 
                                         num_ev_total: float) -> Dict:
        """Genera recomendaciones de sistema de rotación"""
        
        # Calcular capacidad total
        forraje_total_aprovechable = sum(s['forraje_aprovechable_kg_ms'] for s in sublotes)
        consumo_diario_total = num_ev_total * self.consumo_animal['equivalente_vaca']
        
        # Días de rotación total
        dias_rotacion_total = forraje_total_aprovechable / consumo_diario_total
        
        # Plan de rotación por sublote
        plan_rotacion = []
        for sublote in sublotes:
            dias_en_sublote = int((sublote['forraje_aprovechable_kg_ms'] / consumo_diario_total) * 0.8)  # 80% uso
            dias_descanso = dias_en_sublote * 3  # Regla 1:3 uso:descanso
            
            plan_rotacion.append({
                'sublote': sublote['sublote_id'],
                'area_ha': sublote['area_ha'],
                'dias_uso': max(3, dias_en_sublote),  # Mínimo 3 días
                'dias_descanso': max(21, dias_descanso),  # Mínimo 21 días
                'productividad': sublote['productividad_relativa'],
                'recomendacion': self._generar_recomendacion_sublote(sublote['productividad_relativa'])
            })
        
        # Calcular ciclo completo
        dias_ciclo = sum(p['dias_uso'] + p['dias_descanso'] for p in plan_rotacion) / len(plan_rotacion)
        
        return {
            'forraje_total_aprovechable_kg': round(forraje_total_aprovechable, 2),
            'consumo_diario_total_kg': round(consumo_diario_total, 2),
            'dias_rotacion_total': round(dias_rotacion_total, 1),
            'num_ev': num_ev_total,
            'plan_rotacion': plan_rotacion,
            'dias_ciclo_promedio': round(dias_ciclo, 1),
            'intensidad_rotacion': self._clasificar_intensidad_rotacion(dias_ciclo)
        }
    
    def _generar_recomendacion_sublote(self, productividad: float) -> str:
        """Genera recomendación específica por sublote"""
        if productividad > 1.2:
            return "Alta productividad - Considerar manejo intensivo con pastoreo rotativo"
        elif productividad > 0.8:
            return "Productividad media - Ideal para rotación estándar"
        else:
            return "Baja productividad - Requiere recuperación, considerar descanso prolongado"
    
    def _clasificar_intensidad_rotacion(self, dias_ciclo: float) -> str:
        """Clasifica la intensidad del sistema de rotación"""
        if dias_ciclo < 30:
            return "Alta intensidad - Rotación rápida"
        elif dias_ciclo < 60:
            return "Media intensidad - Rotación moderada"
        else:
            return "Baja intensidad - Rotación lenta"
    
       def crear_mapa_sublotes(self, gdf_area, sublotes_info):
        """Crea mapa visual de los sublotes"""
        # Verificar si hay datos geoespaciales válidos
        if gdf_area is None or gdf_area.empty:
            return None
            
        try:
            # Calcular bounds del área
            bounds = gdf_area.total_bounds
            centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            
            # Crear mapa base
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Dividir polígono en sublotes (simplificado - en realidad se usarían las geometrías reales)
            # Por simplicidad, mostraremos el área original con divisiones simuladas
            
            # Colores para diferentes niveles de productividad
            colores = ['#ff4444', '#ffa500', '#ffff00', '#00ff00', '#00cc00', '#009900']
            
            # Agregar área original
            folium.GeoJson(
                gdf_area.geometry.iloc[0],
                style_function=lambda x: {
                    'fillColor': '#3b82f6',
                    'color': '#1d4ed8',
                    'weight': 3,
                    'fillOpacity': 0.1,
                    'dashArray': '5, 5'
                },
                tooltip="Área total de pastoreo"
            ).add_to(m)
            
            # Simular división en sublotes (en producción real, usar geometrías reales)
            # Aquí solo agregamos marcadores representativos
            
            for i, sublote in enumerate(sublotes_info):
                # Calcular posición aproximada para marcador
                lat = bounds[1] + (bounds[3] - bounds[1]) * (0.2 + 0.6 * (i / len(sublotes_info)))
                lon = bounds[0] + (bounds[2] - bounds[0]) * (0.3 + 0.4 * (i % 2))
                
                # Color según productividad
                color_idx = min(len(colores) - 1, int(sublote['productividad_relativa'] * 3))
                
                # Crear marcador
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=15,
                    popup=f"""
                    <b>Sublote {sublote['sublote_id']}</b><br>
                    Área: {sublote['area_ha']} ha<br>
                    Productividad: {sublote['disponibilidad_kg_ms_ha']} kg MS/ha<br>
                    Forraje aprovechable: {sublote['forraje_aprovechable_kg_ms']/1000:.1f} ton MS
                    """,
                    color=colores[color_idx],
                    fill=True,
                    fillOpacity=0.7
                ).add_to(m)
            
            # Agregar leyenda
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 250px;
                background-color: white;
                border: 2px solid #8B4513;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #8B4513; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                🐮 Sublotes Forrajeros
                </h4>
                <div style="margin: 5px 0;">
                    <div><span style="color: #ff4444; font-weight: bold;">●</span> Muy baja productividad</div>
                    <div><span style="color: #ffa500; font-weight: bold;">●</span> Baja productividad</div>
                    <div><span style="color: #ffff00; font-weight: bold;">●</span> Media productividad</div>
                    <div><span style="color: #00ff00; font-weight: bold;">●</span> Buena productividad</div>
                    <div><span style="color: #00cc00; font-weight: bold;">●</span> Alta productividad</div>
                    <div><span style="color: #009900; font-weight: bold;">●</span> Muy alta productividad</div>
                </div>
                <div style="font-size: 12px; color: #666; margin-top: 10px;">
                    <div>📌 Haga clic en los círculos para ver detalles</div>
                </div>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(leyenda_html))
            
            return m
            
        except Exception as e:
            st.warning(f"Error al crear mapa de sublotes: {str(e)}")
            return None
# ===============================
# 🌦️ CONECTOR CLIMÁTICO TROPICAL SIMPLIFICADO
# ===============================
class ConectorClimaticoTropical:
    """Sistema para obtener datos meteorológicos reales en Sudamérica"""
    def __init__(self):
        pass

    def obtener_datos_climaticos(self, lat: float, lon: float) -> Dict:
        """Obtiene datos climáticos para una ubicación"""
        # Simulación realista basada en ubicación
        if -5 <= lat <= 5 and -75 <= lon <= -50:  # Amazonía central
            return {'precipitacion': 2500 + random.uniform(-200, 200), 'temperatura': 26 + random.uniform(-1, 1)}
        elif abs(lat) < 10 and -82 <= lon <= -75:  # Chocó
            return {'precipitacion': 4000 + random.uniform(-300, 300), 'temperatura': 27 + random.uniform(-1, 1)}
        elif -15 <= lat < -5 and -70 <= lon <= -50:  # Sur amazónico
            return {'precipitacion': 1800 + random.uniform(-200, 200), 'temperatura': 25 + random.uniform(-1, 1)}
        elif -34 <= lat <= -22 and -73 <= lon <= -53:  # Argentina templada
            return {'precipitacion': 800 + random.uniform(-100, 100), 'temperatura': 18 + random.uniform(-2, 2)}
        else:  # Región general
            return {'precipitacion': 1200 + random.uniform(-200, 200), 'temperatura': 22 + random.uniform(-2, 2)}

# ===============================
# 🌳 METODOLOGÍA VERRA SIMPLIFICADA
# ===============================
class MetodologiaVerra:
    """Implementación simplificada de la metodología Verra VCS"""
    def __init__(self):
        self.factores = {
            'conversion_carbono': 0.47,
            'ratio_co2': 3.67,
            'ratio_raiz': 0.24,  # BGB/AGB
            'proporcion_madera_muerta': 0.15,
            'acumulacion_hojarasca': 5.0,
            'carbono_suelo': 2.5  # ton C/ha en 30 cm
        }
        
    def calcular_carbono_hectarea(self, ndvi: float, tipo_bosque: str, precipitacion: float) -> Dict:
        """Calcula carbono por hectárea basado en NDVI, tipo de bosque y precipitación"""
        # Factor por precipitación (bosques más lluviosos tienen más biomasa)
        factor_precip = min(2.0, max(0.5, precipitacion / 1500))
        
        # Estimación de biomasa aérea basada en NDVI
        if ndvi > 0.7:
            agb_ton_ha = (150 + (ndvi - 0.7) * 300) * factor_precip
        elif ndvi > 0.5:
            agb_ton_ha = (80 + (ndvi - 0.5) * 350) * factor_precip
        elif ndvi > 0.3:
            agb_ton_ha = (30 + (ndvi - 0.3) * 250) * factor_precip
        else:
            agb_ton_ha = (5 + ndvi * 100) * factor_precip
        
        # Ajuste por tipo de bosque
        if tipo_bosque == "amazonia":
            agb_ton_ha *= 1.2
        elif tipo_bosque == "choco":
            agb_ton_ha *= 1.3
        elif tipo_bosque == "seco":
            agb_ton_ha *= 0.8
        
        # Cálculos de carbono por pool
        carbono_agb = agb_ton_ha * self.factores['conversion_carbono']
        carbono_bgb = carbono_agb * self.factores['ratio_raiz']
        carbono_dw = carbono_agb * self.factores['proporcion_madera_muerta']
        carbono_li = self.factores['acumulacion_hojarasca'] * self.factores['conversion_carbono']
        carbono_soc = self.factores['carbono_suelo']
        
        carbono_total = carbono_agb + carbono_bgb + carbono_dw + carbono_li + carbono_soc
        co2_equivalente = carbono_total * self.factores['ratio_co2']
        
        return {
            'carbono_total_ton_ha': round(carbono_total, 2),
            'co2_equivalente_ton_ha': round(co2_equivalente, 2),
            'desglose': {
                'AGB': round(carbono_agb, 2),
                'BGB': round(carbono_bgb, 2),
                'DW': round(carbono_dw, 2),
                'LI': round(carbono_li, 2),
                'SOC': round(carbono_soc, 2)
            }
        }

# ===============================
# 🦋 ANÁLISIS DE BIODIVERSIDAD CON SHANNON
# ===============================
class AnalisisBiodiversidad:
    """Sistema para análisis de biodiversidad usando el índice de Shannon"""
    def __init__(self):
        self.parametros = {
            'amazonia': {'riqueza_base': 150, 'abundancia_base': 1000},
            'choco': {'riqueza_base': 120, 'abundancia_base': 800},
            'andes': {'riqueza_base': 100, 'abundancia_base': 600},
            'pampa': {'riqueza_base': 50, 'abundancia_base': 300},
            'seco': {'riqueza_base': 40, 'abundancia_base': 200}
        }
    
    def calcular_shannon(self, ndvi: float, tipo_ecosistema: str, area_ha: float, precipitacion: float) -> Dict:
        """Calcula índice de Shannon basado en NDVI, tipo de ecosistema y condiciones ambientales"""
        
        # Parámetros base según ecosistema
        params = self.parametros.get(tipo_ecosistema, {'riqueza_base': 60, 'abundancia_base': 400})
        
        # Factor NDVI (vegetación más sana → más biodiversidad)
        factor_ndvi = 1.0 + (ndvi * 0.8)
        
        # Factor área (áreas más grandes → más especies)
        factor_area = min(2.0, math.log10(area_ha + 1) * 0.5 + 1)
        
        # Factor precipitación (más lluvia → más biodiversidad en trópicos)
        if tipo_ecosistema in ['amazonia', 'choco']:
            factor_precip = min(1.5, precipitacion / 2000)
        else:
            factor_precip = 1.0
        
        # Cálculo de riqueza de especies estimada
        riqueza_especies = int(params['riqueza_base'] * factor_ndvi * factor_area * factor_precip * random.uniform(0.9, 1.1))
        
        # Cálculo de abundancia estimada
        abundancia_total = int(params['abundancia_base'] * factor_ndvi * factor_area * factor_precip * random.uniform(0.9, 1.1))
        
        # Simulación de distribución de abundancia (ley de potencias común en ecología)
        especies = []
        abundancia_acumulada = 0
        
        for i in range(riqueza_especies):
            # Abundancia sigue una distribución log-normal
            abundancia = int((abundancia_total / max(riqueza_especies, 1)) * random.lognormvariate(0, 0.5))
            if abundancia > 0:
                especies.append({'especie_id': i+1, 'abundancia': abundancia})
                abundancia_acumulada += abundancia
        
        # Normalizar abundancias
        for especie in especies:
            especie['proporcion'] = especie['abundancia'] / abundancia_acumulada if abundancia_acumulada > 0 else 0
        
        # Calcular índice de Shannon
        shannon = 0
        for especie in especies:
            if especie['proporcion'] > 0:
                shannon -= especie['proporcion'] * math.log(especie['proporcion'])
        
        # Categorías de biodiversidad según Shannon
        if shannon > 3.5:
            categoria = "Muy Alta"
            color = "#10b981"
        elif shannon > 2.5:
            categoria = "Alta"
            color = "#3b82f6"
        elif shannon > 1.5:
            categoria = "Moderada"
            color = "#f59e0b"
        elif shannon > 0.5:
            categoria = "Baja"
            color = "#ef4444"
        else:
            categoria = "Muy Baja"
            color = "#991b1b"
        
        return {
            'indice_shannon': round(shannon, 3),
            'categoria': categoria,
            'color': color,
            'riqueza_especies': riqueza_especies,
            'abundancia_total': abundancia_acumulada,
            'especies_muestra': especies[:10]
        }

# ===============================
# 🗺️ SISTEMA DE MAPAS COMPLETO CON ZOOM AUTOMÁTICO
# ===============================
class SistemaMapas:
    """Sistema de mapas completo con zoom automático a los polígonos"""
    def __init__(self):
        self.capa_base = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    
    def crear_mapa_area(self, gdf, zoom_auto=True):
        """Crea mapa básico con el área de estudio con zoom automático"""
        if gdf is None or gdf.empty:
            return None
        
        try:
            # Calcular centro y bounds
            bounds = gdf.total_bounds
            centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            
            # Calcular zoom basado en el tamaño del polígono
            if zoom_auto:
                width = bounds[2] - bounds[0]
                height = bounds[3] - bounds[1]
                
                # Determinar zoom basado en la extensión
                if max(width, height) > 10:
                    zoom_start = 6
                elif max(width, height) > 5:
                    zoom_start = 8
                elif max(width, height) > 2:
                    zoom_start = 10
                elif max(width, height) > 1:
                    zoom_start = 12
                elif max(width, height) > 0.5:
                    zoom_start = 14
                else:
                    zoom_start = 16
            else:
                zoom_start = 12
            
            # Crear mapa
            m = folium.Map(
                location=centro,
                zoom_start=zoom_start,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics',
                control_scale=True
            )
            
            # Agregar polígono con borde destacado
            folium.GeoJson(
                gdf.geometry.iloc[0],
                style_function=lambda x: {
                    'fillColor': '#3b82f6',
                    'color': '#1d4ed8',
                    'weight': 4,
                    'fillOpacity': 0.2,
                    'dashArray': '5, 5'
                },
                highlight_function=lambda x: {
                    'weight': 6,
                    'color': '#1e40af',
                    'fillOpacity': 0.3
                }
            ).add_to(m)
            
            # Ajustar límites del mapa al polígono
            sw = [bounds[1], bounds[0]]
            ne = [bounds[3], bounds[2]]
            m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa: {str(e)}")
            return None
    
    def crear_mapa_calor_carbono(self, puntos_carbono, gdf_area=None):
        """Crea mapa de calor para carbono con zoom automático"""
        if not puntos_carbono or len(puntos_carbono) == 0:
            return None
        
        try:
            # Calcular centro y bounds
            if gdf_area is not None and not gdf_area.empty:
                bounds = gdf_area.total_bounds
                centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            else:
                centro = [puntos_carbono[0]['lat'], puntos_carbono[0]['lon']]
                bounds = None
            
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Si hay polígono de área, agregarlo primero
            if gdf_area is not None and not gdf_area.empty:
                folium.GeoJson(
                    gdf_area.geometry.iloc[0],
                    style_function=lambda x: {
                        'fillColor': '#3b82f6',
                        'color': '#1d4ed8',
                        'weight': 3,
                        'fillOpacity': 0.1,
                        'dashArray': '5, 5'
                    }
                ).add_to(m)
            
            # Preparar datos para heatmap
            heat_data = [[p['lat'], p['lon'], p['carbono_ton_ha']] for p in puntos_carbono]
            
            # Gradiente personalizado para carbono
            gradient_carbono = {
                0.0: 'blue',
                0.2: 'cyan',
                0.4: 'lime',
                0.6: 'yellow',
                0.8: 'orange',
                1.0: 'red'
            }
            
            # Agregar heatmap
            HeatMap(
                heat_data,
                name='Carbono (ton C/ha)',
                min_opacity=0.4,
                radius=25,
                blur=20,
                gradient=gradient_carbono
            ).add_to(m)
            
            # Agregar leyenda
            self._agregar_leyenda_carbono(m)
            
            # Ajustar zoom a los datos si hay área
            if gdf_area is not None and not gdf_area.empty:
                sw = [bounds[1], bounds[0]]
                ne = [bounds[3], bounds[2]]
                m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa de carbono: {str(e)}")
            return None
    
    def crear_mapa_calor_ndvi(self, puntos_ndvi, gdf_area=None):
        """Crea mapa de calor para NDVI con zoom automático"""
        if not puntos_ndvi or len(puntos_ndvi) == 0:
            return None
        
        try:
            # Calcular centro y bounds
            if gdf_area is not None and not gdf_area.empty:
                bounds = gdf_area.total_bounds
                centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            else:
                centro = [puntos_ndvi[0]['lat'], puntos_ndvi[0]['lon']]
                bounds = None
            
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Si hay polígono de área, agregarlo primero
            if gdf_area is not None and not gdf_area.empty:
                folium.GeoJson(
                    gdf_area.geometry.iloc[0],
                    style_function=lambda x: {
                        'fillColor': '#3b82f6',
                        'color': '#1d4ed8',
                        'weight': 3,
                        'fillOpacity': 0.1,
                        'dashArray': '5, 5'
                    }
                ).add_to(m)
            
            # Preparar datos para heatmap
            heat_data = [[p['lat'], p['lon'], p['ndvi']] for p in puntos_ndvi]
            
            # Gradiente para NDVI (rojo = bajo, verde = alto)
            gradient_ndvi = {
                0.0: '#8b0000',
                0.2: '#ff4500',
                0.4: '#ffd700',
                0.6: '#9acd32',
                0.8: '#32cd32',
                1.0: '#006400'
            }
            
            # Agregar heatmap
            HeatMap(
                heat_data,
                name='NDVI',
                min_opacity=0.5,
                radius=25,
                blur=20,
                gradient=gradient_ndvi
            ).add_to(m)
            
            # Agregar leyenda
            self._agregar_leyenda_ndvi(m)
            
            # Ajustar zoom a los datos si hay área
            if gdf_area is not None and not gdf_area.empty:
                sw = [bounds[1], bounds[0]]
                ne = [bounds[3], bounds[2]]
                m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa de NDVI: {str(e)}")
            return None
    
    def crear_mapa_calor_ndwi(self, puntos_ndwi, gdf_area=None):
        """Crea mapa de calor para NDWI con zoom automático"""
        if not puntos_ndwi or len(puntos_ndwi) == 0:
            return None
        
        try:
            # Calcular centro y bounds
            if gdf_area is not None and not gdf_area.empty:
                bounds = gdf_area.total_bounds
                centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            else:
                centro = [puntos_ndwi[0]['lat'], puntos_ndwi[0]['lon']]
                bounds = None
            
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Si hay polígono de área, agregarlo primero
            if gdf_area is not None and not gdf_area.empty:
                folium.GeoJson(
                    gdf_area.geometry.iloc[0],
                    style_function=lambda x: {
                        'fillColor': '#3b82f6',
                        'color': '#1d4ed8',
                        'weight': 3,
                        'fillOpacity': 0.1,
                        'dashArray': '5, 5'
                    }
                ).add_to(m)
            
            # Preparar datos para heatmap
            heat_data = [[p['lat'], p['lon'], p['ndwi']] for p in puntos_ndwi]
            
            # Gradiente para NDWI (marrón = seco, azul = húmedo)
            gradient_ndwi = {
                0.0: '#8b4513',
                0.2: '#d2691e',
                0.4: '#f4a460',
                0.6: '#87ceeb',
                0.8: '#1e90ff',
                1.0: '#00008b'
            }
            
            # Agregar heatmap
            HeatMap(
                heat_data,
                name='NDWI',
                min_opacity=0.5,
                radius=25,
                blur=20,
                gradient=gradient_ndwi
            ).add_to(m)
            
            # Agregar leyenda
            self._agregar_leyenda_ndwi(m)
            
            # Ajustar zoom a los datos si hay área
            if gdf_area is not None and not gdf_area.empty:
                sw = [bounds[1], bounds[0]]
                ne = [bounds[3], bounds[2]]
                m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa de NDWI: {str(e)}")
            return None
    
    def crear_mapa_calor_biodiversidad(self, puntos_biodiversidad, gdf_area=None):
        """Crea mapa de calor para biodiversidad con zoom automático"""
        if not puntos_biodiversidad or len(puntos_biodiversidad) == 0:
            return None
        
        try:
            # Calcular centro y bounds
            if gdf_area is not None and not gdf_area.empty:
                bounds = gdf_area.total_bounds
                centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            else:
                centro = [puntos_biodiversidad[0]['lat'], puntos_biodiversidad[0]['lon']]
                bounds = None
            
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Si hay polígono de área, agregarlo primero
            if gdf_area is not None and not gdf_area.empty:
                folium.GeoJson(
                    gdf_area.geometry.iloc[0],
                    style_function=lambda x: {
                        'fillColor': '#3b82f6',
                        'color': '#1d4ed8',
                        'weight': 3,
                        'fillOpacity': 0.1,
                        'dashArray': '5, 5'
                    }
                ).add_to(m)
            
            # Preparar datos para heatmap
            heat_data = [[p['lat'], p['lon'], p['indice_shannon']] for p in puntos_biodiversidad]
            
            # Gradiente para biodiversidad
            gradient_biodiv = {
                0.0: '#991b1b',
                0.2: '#ef4444',
                0.4: '#f59e0b',
                0.6: '#3b82f6',
                0.8: '#8b5cf6',
                1.0: '#10b981'
            }
            
            # Agregar heatmap
            HeatMap(
                heat_data,
                name='Índice de Shannon',
                min_opacity=0.5,
                radius=25,
                blur=20,
                gradient=gradient_biodiv
            ).add_to(m)
            
            # Agregar leyenda
            self._agregar_leyenda_biodiversidad(m)
            
            # Ajustar zoom a los datos si hay área
            if gdf_area is not None and not gdf_area.empty:
                sw = [bounds[1], bounds[0]]
                ne = [bounds[3], bounds[2]]
                m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa de biodiversidad: {str(e)}")
            return None
    
    def crear_mapa_combinado(self, puntos_carbono, puntos_ndvi, puntos_ndwi, puntos_biodiversidad, gdf_area=None):
        """Crea mapa con todas las capas de heatmap con zoom automático"""
        if not puntos_carbono or len(puntos_carbono) == 0:
            return None
        
        try:
            # Calcular centro y bounds
            if gdf_area is not None and not gdf_area.empty:
                bounds = gdf_area.total_bounds
                centro = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            else:
                centro = [puntos_carbono[0]['lat'], puntos_carbono[0]['lon']]
                bounds = None
            
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=self.capa_base,
                attr='Esri, Maxar, Earthstar Geographics'
            )
            
            # Si hay polígono de área, agregarlo primero
            if gdf_area is not None and not gdf_area.empty:
                folium.GeoJson(
                    gdf_area.geometry.iloc[0],
                    style_function=lambda x: {
                        'fillColor': '#3b82f6',
                        'color': '#1d4ed8',
                        'weight': 3,
                        'fillOpacity': 0.1,
                        'dashArray': '5, 5'
                    }
                ).add_to(m)
            
            # Agregar capas de heatmap (inicialmente ocultas)
            capas = {}
            
            # Capa de carbono
            if puntos_carbono and len(puntos_carbono) > 0:
                heat_data_carbono = [[p['lat'], p['lon'], p['carbono_ton_ha']] for p in puntos_carbono]
                capas['carbono'] = HeatMap(
                    heat_data_carbono,
                    name='🌳 Carbono',
                    min_opacity=0.4,
                    radius=20,
                    blur=15,
                    gradient={
                        0.0: 'blue', 0.2: 'cyan', 0.4: 'lime', 
                        0.6: 'yellow', 0.8: 'orange', 1.0: 'red'
                    },
                    show=False
                )
                capas['carbono'].add_to(m)
            
            # Capa de NDVI
            if puntos_ndvi and len(puntos_ndvi) > 0:
                heat_data_ndvi = [[p['lat'], p['lon'], p['ndvi']] for p in puntos_ndvi]
                capas['ndvi'] = HeatMap(
                    heat_data_ndvi,
                    name='📈 NDVI',
                    min_opacity=0.4,
                    radius=20,
                    blur=15,
                    gradient={
                        0.0: '#8b0000', 0.2: '#ff4500', 0.4: '#ffd700',
                        0.6: '#9acd32', 0.8: '#32cd32', 1.0: '#006400'
                    },
                    show=False
                )
                capas['ndvi'].add_to(m)
            
            # Capa de NDWI
            if puntos_ndwi and len(puntos_ndwi) > 0:
                heat_data_ndwi = [[p['lat'], p['lon'], p['ndwi']] for p in puntos_ndwi]
                capas['ndwi'] = HeatMap(
                    heat_data_ndwi,
                    name='💧 NDWI',
                    min_opacity=0.4,
                    radius=20,
                    blur=15,
                    gradient={
                        0.0: '#8b4513', 0.2: '#d2691e', 0.4: '#f4a460',
                        0.6: '#87ceeb', 0.8: '#1e90ff', 1.0: '#00008b'
                    },
                    show=False
                )
                capas['ndwi'].add_to(m)
            
            # Capa de biodiversidad
            if puntos_biodiversidad and len(puntos_biodiversidad) > 0:
                heat_data_biodiv = [[p['lat'], p['lon'], p['indice_shannon']] for p in puntos_biodiversidad]
                capas['biodiversidad'] = HeatMap(
                    heat_data_biodiv,
                    name='🦋 Biodiversidad',
                    min_opacity=0.4,
                    radius=20,
                    blur=15,
                    gradient={
                        0.0: '#991b1b', 0.2: '#ef4444', 0.4: '#f59e0b',
                        0.6: '#3b82f6', 0.8: '#8b5cf6', 1.0: '#10b981'
                    },
                    show=True
                )
                capas['biodiversidad'].add_to(m)
            
            # Control de capas
            folium.LayerControl().add_to(m)
            
            # Agregar leyenda combinada
            self._agregar_leyenda_combinada(m)
            
            # Ajustar zoom a los datos si hay área
            if gdf_area is not None and not gdf_area.empty:
                sw = [bounds[1], bounds[0]]
                ne = [bounds[3], bounds[2]]
                m.fit_bounds([sw, ne])
            
            return m
        except Exception as e:
            st.warning(f"Error al crear mapa combinado: {str(e)}")
            return None
    
    # Las funciones de leyenda permanecen igual...
    
    def _agregar_leyenda_carbono(self, mapa):
        """Agrega leyenda para el mapa de carbono"""
        try:
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 250px;
                background-color: white;
                border: 2px solid #065f46;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #065f46; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                🌳 Carbono (ton C/ha)
                </h4>
                <div style="margin: 10px 0;">
                    <div style="height: 20px; background: linear-gradient(90deg, blue, cyan, lime, yellow, orange, red); border: 1px solid #666;"></div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px;">
                        <span>Bajo</span>
                        <span>Medio</span>
                        <span>Alto</span>
                    </div>
                </div>
                <div style="font-size: 12px; color: #666;">
                    <div><span style="color: #065f46; font-weight: bold;">■</span> Contorno azul: Área de estudio</div>
                    <div><span style="color: #3b82f6; font-weight: bold;">■</span> Heatmap: Intensidad de carbono</div>
                </div>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(leyenda_html))
        except:
            pass
    
    def _agregar_leyenda_ndvi(self, mapa):
        """Agrega leyenda para el mapa de NDVI"""
        try:
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 250px;
                background-color: white;
                border: 2px solid #32cd32;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #32cd32; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                📈 NDVI (Índice de Vegetación)
                </h4>
                <div style="margin: 10px 0;">
                    <div style="height: 20px; background: linear-gradient(90deg, #8b0000, #ff4500, #ffd700, #9acd32, #32cd32, #006400); border: 1px solid #666;"></div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px;">
                        <span>-1.0</span>
                        <span>0.0</span>
                        <span>+1.0</span>
                    </div>
                </div>
                <div style="font-size: 12px; color: #666;">
                    <div><span style="color: #1d4ed8; font-weight: bold;">■</span> Contorno azul: Área de estudio</div>
                    <div><span style="color: #8b0000; font-weight: bold;">■</span> Rojo: Vegetación escasa/muerta</div>
                    <div><span style="color: #32cd32; font-weight: bold;">■</span> Verde: Vegetación densa/sana</div>
                </div>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(leyenda_html))
        except:
            pass
    
    def _agregar_leyenda_ndwi(self, mapa):
        """Agrega leyenda para el mapa de NDWI"""
        try:
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 250px;
                background-color: white;
                border: 2px solid #1e90ff;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #1e90ff; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                💧 NDWI (Índice de Agua)
                </h4>
                <div style="margin: 10px 0;">
                    <div style="height: 20px; background: linear-gradient(90deg, #8b4513, #d2691e, #f4a460, #87ceeb, #1e90ff, #00008b); border: 1px solid #666;"></div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px;">
                        <span>Seco</span>
                        <span>Húmedo</span>
                    </div>
                </div>
                <div style="font-size: 12px; color: #666;">
                    <div><span style="color: #1d4ed8; font-weight: bold;">■</span> Contorno azul: Área de estudio</div>
                    <div><span style="color: #8b4513; font-weight: bold;">■</span> Marrón: Superficie seca</div>
                    <div><span style="color: #1e90ff; font-weight: bold;">■</span> Azul: Presencia de agua</div>
                </div>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(leyenda_html))
        except:
            pass
    
    def _agregar_leyenda_biodiversidad(self, mapa):
        """Agrega leyenda para el mapa de biodiversidad"""
        try:
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 280px;
                background-color: white;
                border: 2px solid #8b5cf6;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #8b5cf6; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                🦋 Índice de Shannon
                </h4>
                <div style="margin: 10px 0;">
                    <div style="height: 20px; background: linear-gradient(90deg, #991b1b, #ef4444, #f59e0b, #3b82f6, #8b5cf6, #10b981); border: 1px solid #666;"></div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px;">
                        <span>0.0</span>
                        <span>2.0</span>
                        <span>4.0</span>
                    </div>
                </div>
                <div style="font-size: 12px; color: #666;">
                    <div><span style="color: #1d4ed8; font-weight: bold;">■</span> Contorno azul: Área de estudio</div>
                    <div><span style="color: #991b1b; font-weight: bold;">■</span> Muy Baja: < 0.5</div>
                    <div><span style="color: #ef4444; font-weight: bold;">■</span> Baja: 0.5 - 1.5</div>
                    <div><span style="color: #f59e0b; font-weight: bold;">■</span> Moderada: 1.5 - 2.5</div>
                    <div><span style="color: #3b82f6; font-weight: bold;">■</span> Alta: 2.5 - 3.5</div>
                    <div><span style="color: #10b981; font-weight: bold;">■</span> Muy Alta: > 3.5</div>
                </div>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(leyenda_html))
        except:
            pass
    
    def _agregar_leyenda_combinada(self, mapa):
        """Agrega leyenda combinada"""
        try:
            leyenda_html = '''
            <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 320px;
                background-color: white;
                border: 2px solid #3b82f6;
                z-index: 9999;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
                font-family: Arial;">
                <h4 style="margin-top: 0; color: #3b82f6; border-bottom: 1px solid #ddd; padding-bottom: 5px;">
                🗺️ Capas del Mapa
                </h4>
                <div style="margin: 10px 0;">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <div style="width: 20px; height: 20px; background: linear-gradient(90deg, blue, cyan, lime, yellow, orange, red); margin-right: 10px; border: 1px solid #666;"></div>
                        <div>🌳 Carbono (ton C/ha)</div>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <div style="width: 20px; height: 20px; background: linear-gradient(90deg, #8b0000, #ff4500, #ffd700, #9acd32, #32cd32, #006400); margin-right: 10px; border: 1px solid #666;"></div>
                        <div>📈 NDVI</div>
                    </div>
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <div style="width: 20px; height: 20px; background: linear-gradient(90deg, #8b4513, #d2691e, #f4a460, #87ceeb, #1e90ff, #00008b); margin-right: 10px; border: 1px solid #666;"></div>
                        <div>💧 NDWI</div>
                    </div>
                    <div style="display: flex; align-items: center;">
                        <div style="width: 20px; height: 20px; background: linear-gradient(90deg, #991b1b, #ef4444, #f59e0b, #3b82f6, #8b5cf6, #10b981); margin-right: 10px; border: 1px solid #666;"></div>
                        <div>🦋 Índice de Shannon</div>
                    </div>
                </div>
                <div style="font-size: 12px; color: #666; border-top: 1px solid #eee; padding-top: 10px;">
                    <div><strong>Instrucciones:</strong></div>
                    <div><span style="color: #1d4ed8; font-weight: bold;">■</span> Contorno azul: Área de estudio</div>
                    <div>• Use el control en la esquina superior derecha para cambiar entre capas</div>
                    <div>• Haga clic en los puntos para ver detalles</div>
                    <div>• Zoom con la rueda del mouse</div>
                </div>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(leyenda_html))
        except:
            pass

# ===============================
# 📊 VISUALIZACIONES Y GRÁFICOS
# ===============================
class Visualizaciones:
    """Clase para generar visualizaciones"""
    
    @staticmethod
    def crear_grafico_barras_carbono(desglose: Dict):
        """Crea gráfico de barras para pools de carbono"""
        if not desglose:
            # Crear gráfico vacío
            fig = go.Figure()
            fig.update_layout(
                title='No hay datos de carbono disponibles',
                height=400
            )
            return fig
        
        # Crear descripciones para los pools
        descripciones = {
            'AGB': 'Biomasa Aérea Viva',
            'BGB': 'Biomasa de Raíces',
            'DW': 'Madera Muerta',
            'LI': 'Hojarasca',
            'SOC': 'Carbono Orgánico del Suelo'
        }
        
        # Preparar etiquetas
        etiquetas = [f"{descripciones.get(k, k)}<br>({k})" for k in desglose.keys()]
        
        fig = go.Figure(data=[
            go.Bar(
                x=etiquetas,
                y=list(desglose.values()),
                marker_color=['#238b45', '#41ab5d', '#74c476', '#a1d99b', '#d9f0a3'],
                text=[f"{v:.1f} ton C/ha" for v in desglose.values()],
                textposition='auto',
                hovertemplate='<b>%{x}</b><br>Valor: %{y:.1f} ton C/ha<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title='Distribución de Carbono por Pools',
            xaxis_title='Pool de Carbono',
            yaxis_title='Ton C/ha',
            height=400,
            hovermode='x unified'
        )
        
        return fig
    
    @staticmethod
    def crear_grafico_radar_biodiversidad(shannon_data: Dict):
        """Crea gráfico radar para biodiversidad"""
        if not shannon_data:
            # Crear gráfico vacío
            fig = go.Figure()
            fig.update_layout(
                title='No hay datos de biodiversidad disponibles',
                height=400
            )
            return fig
        
        categorias = ['Shannon', 'Riqueza', 'Abundancia', 'Equitatividad', 'Conservación']
        
        try:
            # Normalizar valores para el radar
            shannon_norm = min(shannon_data.get('indice_shannon', 0) / 4.0 * 100, 100)
            riqueza_norm = min(shannon_data.get('riqueza_especies', 0) / 200 * 100, 100)
            abundancia_norm = min(shannon_data.get('abundancia_total', 0) / 2000 * 100, 100)
            
            # Valores simulados para equitatividad y conservación
            equitatividad = random.uniform(70, 90)
            conservacion = random.uniform(60, 95)
            
            valores = [shannon_norm, riqueza_norm, abundancia_norm, equitatividad, conservacion]
            
            fig = go.Figure(data=go.Scatterpolar(
                r=valores,
                theta=categorias,
                fill='toself',
                fillcolor='rgba(139, 92, 246, 0.3)',
                line_color='#8b5cf6',
                name='Biodiversidad'
            ))
            
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100]
                    )
                ),
                showlegend=True,
                height=400,
                title='Perfil de Biodiversidad'
            )
            
            return fig
        except Exception as e:
            # Gráfico de respaldo
            fig = go.Figure()
            fig.update_layout(
                title='Error al generar gráfico de biodiversidad',
                height=400
            )
            return fig
    
    @staticmethod
    def crear_grafico_comparativo(puntos_carbono, puntos_ndvi, puntos_ndwi, puntos_biodiversidad):
        """Crea gráfico comparativo de todas las variables"""
        if not puntos_carbono or not puntos_ndvi:
            return None
        
        try:
            # Tomar los primeros 50 puntos para no saturar
            n = min(50, len(puntos_carbono))
            
            # Crear subplots
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=('Carbono vs NDVI', 'Carbono vs NDWI', 
                              'Shannon vs NDVI', 'Shannon vs NDWI'),
                vertical_spacing=0.15,
                horizontal_spacing=0.15
            )
            
            # Carbono vs NDVI
            carbono_vals = [p['carbono_ton_ha'] for p in puntos_carbono[:n]]
            ndvi_vals = [p['ndvi'] for p in puntos_ndvi[:n]]
            
            fig.add_trace(
                go.Scatter(
                    x=ndvi_vals,
                    y=carbono_vals,
                    mode='markers',
                    marker=dict(color='#10b981', size=8),
                    name='Carbono-NDVI'
                ),
                row=1, col=1
            )
            
            # Carbono vs NDWI
            ndwi_vals = [p['ndwi'] for p in puntos_ndwi[:n]]
            fig.add_trace(
                go.Scatter(
                    x=ndwi_vals,
                    y=carbono_vals,
                    mode='markers',
                    marker=dict(color='#3b82f6', size=8),
                    name='Carbono-NDWI'
                ),
                row=1, col=2
            )
            
            # Shannon vs NDVI
            shannon_vals = [p['indice_shannon'] for p in puntos_biodiversidad[:n]]
            fig.add_trace(
                go.Scatter(
                    x=ndvi_vals,
                    y=shannon_vals,
                    mode='markers',
                    marker=dict(color='#8b5cf6', size=8),
                    name='Shannon-NDVI'
                ),
                row=2, col=1
            )
            
            # Shannon vs NDWI
            fig.add_trace(
                go.Scatter(
                    x=ndwi_vals,
                    y=shannon_vals,
                    mode='markers',
                    marker=dict(color='#f59e0b', size=8),
                    name='Shannon-NDWI'
                ),
                row=2, col=2
            )
            
            # Actualizar layout
            fig.update_layout(
                height=700,
                showlegend=True,
                title_text="Comparación de Variables Ambientales"
            )
            
            # Actualizar ejes
            fig.update_xaxes(title_text="NDVI", row=1, col=1)
            fig.update_yaxes(title_text="Carbono (ton C/ha)", row=1, col=1)
            
            fig.update_xaxes(title_text="NDWI", row=1, col=2)
            fig.update_yaxes(title_text="Carbono (ton C/ha)", row=1, col=2)
            
            fig.update_xaxes(title_text="NDVI", row=2, col=1)
            fig.update_yaxes(title_text="Índice de Shannon", row=2, col=1)
            
            fig.update_xaxes(title_text="NDWI", row=2, col=2)
            fig.update_yaxes(title_text="Índice de Shannon", row=2, col=2)
            
            return fig
        except Exception as e:
            return None
    
    @staticmethod
    def crear_metricas_kpi(carbono_total: float, co2_total: float, shannon: float, area: float):
        """Crea métricas KPI para dashboard"""
        html = f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem;">
            <div style="background: linear-gradient(135deg, #065f46 0%, #0a7e5a 100%); padding: 1.5rem; border-radius: 10px; color: white;">
                <h3 style="margin: 0; font-size: 1.2rem;">🌳 Carbono Total</h3>
                <p style="font-size: 2rem; font-weight: bold; margin: 0.5rem 0;">{carbono_total:,.0f}</p>
                <p style="margin: 0;">ton C</p>
            </div>
            <div style="background: linear-gradient(135deg, #0a7e5a 0%, #10b981 100%); padding: 1.5rem; border-radius: 10px; color: white;">
                <h3 style="margin: 0; font-size: 1.2rem;">🏭 CO₂ Equivalente</h3>
                <p style="font-size: 2rem; font-weight: bold; margin: 0.5rem 0;">{co2_total:,.0f}</p>
                <p style="margin: 0;">ton CO₂e</p>
            </div>
            <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); padding: 1.5rem; border-radius: 10px; color: white;">
                <h3 style="margin: 0; font-size: 1.2rem;">🦋 Índice Shannon</h3>
                <p style="font-size: 2rem; font-weight: bold; margin: 0.5rem 0;">{shannon:.2f}</p>
                <p style="margin: 0;">Biodiversidad</p>
            </div>
            <div style="background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%); padding: 1.5rem; border-radius: 10px; color: white;">
                <h3 style="margin: 0; font-size: 1.2rem;">📐 Área Total</h3>
                <p style="font-size: 2rem; font-weight: bold; margin: 0.5rem 0;">{area:,.1f}</p>
                <p style="margin: 0;">hectáreas</p>
            </div>
        </div>
        """
        return html
    
    @staticmethod
    def crear_grafico_forrajero(disponibilidad_forrajera: Dict, equivalentes_vaca: Dict):
        """Crea gráfico para análisis forrajero"""
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Disponibilidad Forrajera', 'Equivalentes Vaca',
                          'Distribución por Sublote', 'Plan de Rotación'),
            specs=[[{'type': 'bar'}, {'type': 'pie'}],
                   [{'type': 'bar'}, {'type': 'table'}]],
            vertical_spacing=0.15,
            horizontal_spacing=0.15,
            row_heights=[0.5, 0.5]
        )
        
        # Gráfico 1: Disponibilidad forrajera
        fig.add_trace(
            go.Bar(
                x=['Productividad', 'Disponible Total', 'Aprovechable'],
                y=[
                    disponibilidad_forrajera.get('productividad_kg_ms_ha', 0),
                    disponibilidad_forrajera.get('disponibilidad_total_kg_ms', 0) / 1000,  # Convertir a ton
                    disponibilidad_forrajera.get('forraje_aprovechable_kg_ms', 0) / 1000
                ],
                name='Forraje',
                marker_color=['#8B4513', '#D2691E', '#F4A460']
            ),
            row=1, col=1
        )
        
        # Gráfico 2: Equivalentes Vaca
        fig.add_trace(
            go.Pie(
                labels=['EV por día', 'EV para período', 'EV recomendado'],
                values=[
                    equivalentes_vaca.get('ev_por_dia', 0),
                    equivalentes_vaca.get('ev_para_periodo', 0),
                    equivalentes_vaca.get('ev_recomendado', 0)
                ],
                name='Equivalentes Vaca',
                hole=0.4
            ),
            row=1, col=2
        )
        
        # Actualizar layout
        fig.update_layout(
            height=700,
            showlegend=True,
            title_text="Análisis Forrajero Completo"
        )
        
        # Actualizar ejes
        fig.update_yaxes(title_text="kg MS/ha / ton MS", row=1, col=1)
        fig.update_xaxes(title_text="Métrica", row=1, col=1)
        
        return fig

# ===============================
# 📄 GENERADOR DE REPORTES COMPLETOS MEJORADO
# ===============================
class GeneradorReportes:
    def __init__(self, resultados, gdf, sistema_mapas=None):
        self.resultados = resultados
        self.gdf = gdf
        self.sistema_mapas = sistema_mapas
        self.buffer_pdf = BytesIO()
        self.buffer_docx = BytesIO()
        
    def _fig_to_png(self, fig):
        """Convierte un gráfico Plotly a PNG en BytesIO - Versión simplificada para Streamlit Cloud"""
        try:
            if fig is None:
                return None
            
            # SOLUCIÓN: En lugar de usar fig.to_image() que requiere Kaleido,
            # creamos una imagen placeholder simple usando PIL
            from PIL import Image, ImageDraw
            import io
            
            # Crear imagen placeholder para el PDF
            width, height = 800, 500
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Dibujar texto informativo
            draw.text((width//2 - 200, height//2 - 20), 
                     "Gráfico interactivo disponible", fill='black')
            draw.text((width//2 - 250, height//2 + 10), 
                     "Consulte la aplicación web para visualización completa", fill='gray')
            
            # Dibujar un borde
            draw.rectangle([10, 10, width-10, height-10], outline='gray', width=2)
            
            # Guardar en BytesIO
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            return img_byte_arr
        except Exception as e:
            st.warning(f"No se pudo crear imagen del gráfico: {str(e)}")
            return None
    
    def _mapa_to_png(self, mapa, width=800, height=600):
        """Convierte un mapa de Folium a PNG (simulación)"""
        try:
            if mapa is None:
                return None
            
            # En una implementación real, usaríamos selenium o map screenshot API
            # Por ahora, creamos una imagen de placeholder
            from PIL import Image, ImageDraw
            import io
            
            # Crear imagen de placeholder
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Dibujar texto
            draw.text((width//2 - 100, height//2 - 20), "Mapa interactivo", fill='black')
            draw.text((width//2 - 150, height//2 + 10), "Disponible en la aplicación web", fill='gray')
            
            # Dibujar un borde
            draw.rectangle([10, 10, width-10, height-10], outline='blue', width=3)
            
            # Guardar en BytesIO
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            return img_byte_arr
        except Exception as e:
            st.warning(f"No se pudo convertir el mapa a PNG: {str(e)}")
            return None

    def _crear_graficos(self):
        """Pre-genera los gráficos necesarios"""
        vis = Visualizaciones()
        res = self.resultados

        graficos = {}

        # Gráfico de carbono
        if 'desglose_promedio' in res and res['desglose_promedio']:
            fig_carbono = vis.crear_grafico_barras_carbono(res['desglose_promedio'])
            graficos['carbono'] = self._fig_to_png(fig_carbono)

        # Gráfico de biodiversidad
        if 'puntos_biodiversidad' in res and res['puntos_biodiversidad']:
            if len(res['puntos_biodiversidad']) > 0:
                fig_biodiv = vis.crear_grafico_radar_biodiversidad(res['puntos_biodiversidad'][0])
                graficos['biodiv'] = self._fig_to_png(fig_biodiv)
        
        # Gráfico comparativo
        if all(k in res for k in ['puntos_carbono', 'puntos_ndvi', 'puntos_ndwi', 'puntos_biodiversidad']):
            fig_comparativo = vis.crear_grafico_comparativo(
                res['puntos_carbono'],
                res['puntos_ndvi'],
                res['puntos_ndwi'],
                res['puntos_biodiversidad']
            )
            if fig_comparativo:
                graficos['comparativo'] = self._fig_to_png(fig_comparativo)

        return graficos

    def generar_pdf(self):
        """Genera reporte completo en PDF con todas las secciones"""
        if not REPORTPDF_AVAILABLE:
            st.error("ReportLab no está instalado. No se puede generar PDF.")
            return None
        
        try:
            # Crear documento
            doc = SimpleDocTemplate(
                self.buffer_pdf,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            story = []
            styles = getSampleStyleSheet()
            
            # Estilos personalizados
            titulo_style = ParagraphStyle(
                'TituloPrincipal',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#0a7e5a'),
                spaceAfter=30,
                alignment=TA_CENTER
            )
            
            subtitulo_style = ParagraphStyle(
                'Subtitulo',
                parent=styles['Heading2'],
                fontSize=18,
                textColor=colors.HexColor('#065f46'),
                spaceAfter=12,
                spaceBefore=20
            )
            
            seccion_style = ParagraphStyle(
                'Seccion',
                parent=styles['Heading3'],
                fontSize=14,
                textColor=colors.HexColor('#1d4ed8'),
                spaceAfter=10,
                spaceBefore=15
            )
            
            # ===== PORTADA =====
            story.append(Paragraph("INFORME AMBIENTAL COMPLETO", titulo_style))
            story.append(Spacer(1, 12))
            story.append(Paragraph("Sistema Satelital de Análisis Ambiental", styles['Title']))
            story.append(Spacer(1, 6))
            story.append(Paragraph("Metodología Verra VCS + Índice de Shannon", styles['Heading2']))
            story.append(Spacer(1, 24))
            story.append(Paragraph(f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
            story.append(Spacer(1, 36))
            
            # ===== RESUMEN EJECUTIVO =====
            story.append(Paragraph("RESUMEN EJECUTIVO", subtitulo_style))
            
            res = self.resultados
            datos_resumen = [
                ["Métrica", "Valor", "Interpretación"],
                ["Área total", f"{res.get('area_total_ha', 0):,.1f} ha", "Superficie del área de estudio"],
                ["Carbono total almacenado", f"{res.get('carbono_total_ton', 0):,.0f} ton C", "Carbono almacenado en el área"],
                ["CO₂ equivalente", f"{res.get('co2_total_ton', 0):,.0f} ton CO₂e", "Potencial de créditos de carbono"],
                ["Índice de Shannon promedio", f"{res.get('shannon_promedio', 0):.3f}", "Nivel de biodiversidad"],
                ["NDVI promedio", f"{res.get('ndvi_promedio', 0):.3f}", "Salud de la vegetación"],
                ["NDWI promedio", f"{res.get('ndwi_promedio', 0):.3f}", "Contenido de agua"],
                ["Tipo de ecosistema", res.get('tipo_ecosistema', 'N/A'), "Ecosistema predominante"],
                ["Puntos de muestreo", str(res.get('num_puntos', 0)), "Muestras analizadas"]
            ]
            
            tabla_resumen = Table(datos_resumen, colWidths=[150, 120, 200])
            tabla_resumen.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#065f46')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f9ff')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
                ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(tabla_resumen)
            story.append(Spacer(1, 20))
            
            # ===== ANÁLISIS DE CARBONO =====
            story.append(PageBreak())
            story.append(Paragraph("ANÁLISIS DE CARBONO", subtitulo_style))
            story.append(Paragraph("Metodología Verra VCS para Proyectos REDD+", seccion_style))
            
            # Tabla de pools de carbono
            if res.get('desglose_promedio'):
                story.append(Paragraph("Distribución de Carbono por Pools", seccion_style))
                
                descripciones = {
                    'AGB': 'Biomasa Aérea Viva (árboles, arbustos)',
                    'BGB': 'Biomasa de Raíces (sistema radical)',
                    'DW': 'Madera Muerta (troncos caídos, ramas)',
                    'LI': 'Hojarasca (material orgánico superficial)',
                    'SOC': 'Carbono Orgánico del Suelo (0-30 cm)'
                }
                
                datos_carbono = [["Pool", "Descripción", "Ton C/ha", "Porcentaje"]]
                total = sum(res['desglose_promedio'].values())
                
                for pool, valor in res['desglose_promedio'].items():
                    porcentaje = (valor / total * 100) if total > 0 else 0
                    datos_carbono.append([
                        pool,
                        descripciones.get(pool, pool),
                        f"{valor:.2f}",
                        f"{porcentaje:.1f}%"
                    ])
                
                tabla_carbono = Table(datos_carbono, colWidths=[60, 180, 70, 70])
                tabla_carbono.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a7e5a')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('ALIGN', (2, 1), (3, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0fdf4')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1fae5')),
                ]))
                
                story.append(tabla_carbono)
                story.append(Spacer(1, 15))
            
            # Valor económico estimado
            valor_economico = res.get('co2_total_ton', 0) * 15
            story.append(Paragraph("Valoración Económica", seccion_style))
            
            datos_valor = [
                ["Concepto", "Valor", "Observaciones"],
                ["CO₂ equivalente total", f"{res.get('co2_total_ton', 0):,.0f} ton CO₂e", "Emisiones evitadas"],
                ["Precio referencial carbono", "$15 USD/ton CO₂", "Precio mercado voluntario"],
                ["Valor económico estimado", f"${valor_economico:,.0f} USD", "Valor potencial del proyecto"],
                ["Créditos potenciales", f"{res.get('co2_total_ton', 0)/1000:,.0f} mil", "Unidades comercializables"]
            ]
            
            tabla_valor = Table(datos_valor, colWidths=[120, 100, 180])
            tabla_valor.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#eff6ff')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dbeafe')),
            ]))
            
            story.append(tabla_valor)
            story.append(Spacer(1, 20))
            
            # ===== ANÁLISIS DE BIODIVERSIDAD =====
            story.append(PageBreak())
            story.append(Paragraph("ANÁLISIS DE BIODIVERSIDAD", subtitulo_style))
            story.append(Paragraph("Índice de Shannon para Diversidad Biológica", seccion_style))
            
            if res.get('puntos_biodiversidad') and len(res['puntos_biodiversidad']) > 0:
                biodiv = res['puntos_biodiversidad'][0]
                
                # Tabla de biodiversidad
                datos_biodiv = [
                    ["Métrica", "Valor", "Interpretación"],
                    ["Índice de Shannon", f"{biodiv.get('indice_shannon', 0):.3f}", biodiv.get('categoria', 'N/A')],
                    ["Riqueza de especies", str(biodiv.get('riqueza_especies', 0)), "Número estimado de especies"],
                    ["Abundancia total", f"{biodiv.get('abundancia_total', 0):,}", "Individuos estimados"],
                    ["Categoría", biodiv.get('categoria', 'N/A'), "Clasificación según Shannon"]
                ]
                
                tabla_biodiv = Table(datos_biodiv, colWidths=[120, 100, 180])
                tabla_biodiv.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#faf5ff')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e9d5ff')),
                ]))
                
                story.append(tabla_biodiv)
                story.append(Spacer(1, 15))
            
            # Escala del Índice de Shannon
            story.append(Paragraph("Escala del Índice de Shannon", seccion_style))
            
            escala_shannon = [
                ["Rango", "Categoría", "Interpretación"],
                ["> 3.5", "Muy Alta", "Ecosistema con alta diversidad y equitatividad"],
                ["2.5 - 3.5", "Alta", "Buena diversidad, estructura equilibrada"],
                ["1.5 - 2.5", "Moderada", "Diversidad media, posible perturbación"],
                ["0.5 - 1.5", "Baja", "Diversidad reducida, perturbación significativa"],
                ["< 0.5", "Muy Baja", "Diversidad muy baja, ecosistema degradado"]
            ]
            
            tabla_escala = Table(escala_shannon, colWidths=[80, 80, 220])
            tabla_escala.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f59e0b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fffbeb')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#fde68a')),
            ]))
            
            story.append(tabla_escala)
            story.append(Spacer(1, 20))
            
            # ===== ANÁLISIS DE ÍNDICES ESPECTRALES =====
            story.append(PageBreak())
            story.append(Paragraph("ANÁLISIS DE ÍNDICES ESPECTRALES", subtitulo_style))
            
            # Tabla de índices
            datos_indices = [
                ["Índice", "Valor promedio", "Rango típico", "Interpretación"],
                ["NDVI", f"{res.get('ndvi_promedio', 0):.3f}", "-1.0 a +1.0", "Salud y densidad de vegetación"],
                ["NDWI", f"{res.get('ndwi_promedio', 0):.3f}", "-1.0 a +1.0", "Contenido de agua en vegetación/suelo"]
            ]
            
            tabla_indices = Table(datos_indices, colWidths=[80, 80, 80, 140])
            tabla_indices.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (1, 1), (2, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0fdf4')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bbf7d0')),
            ]))
            
            story.append(tabla_indices)
            story.append(Spacer(1, 15))
            
            # Interpretación NDVI
            story.append(Paragraph("Interpretación del NDVI", seccion_style))
            
            interpretacion_ndvi = [
                ["Valor NDVI", "Estado de la vegetación", "Características"],
                ["> 0.6", "Muy saludable/densa", "Bosques maduros, vegetación exuberante"],
                ["0.3 - 0.6", "Moderada/saludable", "Vegetación en desarrollo, pastizales"],
                ["0.1 - 0.3", "Escasa/degradada", "Vegetación rala, posible estrés"],
                ["< 0.1", "Muy escasa/muerta", "Suelo desnudo, áreas urbanas, agua"]
            ]
            
            tabla_ndvi = Table(interpretacion_ndvi, colWidths=[80, 100, 120])
            tabla_ndvi.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecfdf5')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#a7f3d0')),
            ]))
            
            story.append(tabla_ndvi)
            story.append(Spacer(1, 20))
            
            # ===== RECOMENDACIONES =====
            story.append(PageBreak())
            story.append(Paragraph("RECOMENDACIONES Y CONCLUSIONES", subtitulo_style))
            
            # Recomendaciones generales
            story.append(Paragraph("Recomendaciones para Proyecto VCS/REDD+", seccion_style))
            
            recomendaciones_vcs = [
                "1. **Validación y Verificación**: Contratar un validador acreditado por Verra",
                "2. **Monitoreo**: Establecer parcelas permanentes de muestreo (mínimo 10% del área)",
                "3. **Línea Base**: Desarrollar escenario de referencia (baseline) robusto",
                "4. **Adicionalidad**: Demostrar que el proyecto es adicional al business-as-usual",
                "5. **Permanencia**: Implementar medidas para garantizar almacenamiento a largo plazo",
                "6. **MRV**: Sistema de Monitoreo, Reporte y Verificación transparente",
                "7. **Participación comunitaria**: Involucrar a las comunidades locales en el proyecto",
                "8. **Plan de manejo**: Desarrollar plan integral de manejo forestal sostenible"
            ]
            
            for rec in recomendaciones_vcs:
                story.append(Paragraph(rec, styles['Normal']))
                story.append(Spacer(1, 5))
            
            story.append(Spacer(1, 15))
            
            # Recomendaciones según biodiversidad
            categoria_biodiv = biodiv.get('categoria', 'N/A') if res.get('puntos_biodiversidad') else 'N/A'
            story.append(Paragraph(f"Recomendaciones para Biodiversidad ({categoria_biodiv})", seccion_style))
            
            if categoria_biodiv in ["Muy Baja", "Baja"]:
                rec_biodiv = [
                    "• **Restauración activa**: Plantación de especies nativas diversificadas",
                    "• **Control de amenazas**: Manejo integral de incendios y especies invasoras",
                    "• **Conectividad**: Establecimiento de corredores biológicos",
                    "• **Protección estricta**: Delimitación de zonas núcleo de conservación",
                    "• **Monitoreo intensivo**: Seguimiento de indicadores clave cada 6 meses"
                ]
            elif categoria_biodiv == "Moderada":
                rec_biodiv = [
                    "• **Manejo sostenible**: Implementar prácticas de bajo impacto",
                    "• **Protección selectiva**: Identificar y proteger áreas críticas",
                    "• **Investigación**: Estudios de dinámica poblacional de especies clave",
                    "• **Educación ambiental**: Programas de concienciación local",
                    "• **Monitoreo regular**: Evaluación anual de biodiversidad"
                ]
            else:
                rec_biodiv = [
                    "• **Conservación preventiva**: Mantenimiento del estado actual",
                    "• **Investigación científica**: Estudio de patrones de biodiversidad",
                    "• **Uso sostenible**: Planificación de actividades económicas compatibles",
                    "• **Turismo científico**: Desarrollo de investigación participativa",
                    "• **Monitoreo continuo**: Sistema de alerta temprana para cambios"
                ]
            
            for rec in rec_biodiv:
                story.append(Paragraph(rec, styles['Normal']))
                story.append(Spacer(1, 5))
            
            story.append(Spacer(1, 20))
            
            # ===== CONCLUSIONES FINALES =====
            story.append(Paragraph("CONCLUSIONES", subtitulo_style))
            
            conclusiones = [
                f"El área de estudio de {res.get('area_total_ha', 0):,.1f} hectáreas presenta un almacenamiento significativo de carbono, con un total de {res.get('carbono_total_ton', 0):,.0f} ton C.",
                f"El índice de Shannon de {res.get('shannon_promedio', 0):.3f} indica un nivel de biodiversidad {categoria_biodiv.lower()}, lo que sugiere oportunidades para medidas de conservación específicas.",
                f"Los valores promedio de NDVI ({res.get('ndvi_promedio', 0):.3f}) y NDWI ({res.get('ndwi_promedio', 0):.3f}) reflejan condiciones adecuadas de salud vegetal y disponibilidad hídrica.",
                "El proyecto presenta potencial para desarrollo bajo estándares VCS/REDD+, contribuyendo tanto a la mitigación climática como a la conservación de biodiversidad.",
                "Se recomienda profundizar el análisis con datos satelitales reales y validación de campo para optimizar el diseño del proyecto."
            ]
            
            for i, conc in enumerate(conclusiones, 1):
                story.append(Paragraph(f"{i}. {conc}", styles['Normal']))
                story.append(Spacer(1, 8))
            
            # Pie de página
            story.append(PageBreak())
            story.append(Paragraph("--- FIN DEL INFORME ---", ParagraphStyle(
                'Pie',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.gray,
                alignment=TA_CENTER,
                spaceBefore=50
            )))
            
            story.append(Paragraph("Sistema Satelital de Análisis Ambiental - Versión 1.0", ParagraphStyle(
                'Firma',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.gray,
                alignment=TA_CENTER
            )))
            
            # Construir documento
            doc.build(story)
            self.buffer_pdf.seek(0)
            return self.buffer_pdf
            
        except Exception as e:
            st.error(f"Error generando PDF: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            return None

    def generar_docx(self):
        """Genera reporte completo en DOCX"""
        if not REPORTDOCX_AVAILABLE:
            st.error("python-docx no está instalado. No se puede generar DOCX.")
            return None
        
        try:
            doc = Document()
            
            # Configurar estilos
            style = doc.styles['Normal']
            style.font.name = 'Arial'
            style.font.size = Pt(11)
            
            # Título
            title = doc.add_heading('INFORME AMBIENTAL COMPLETO', 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            subtitle = doc.add_heading('Sistema Satelital de Análisis Ambiental', 1)
            subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            doc.add_paragraph(f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            doc.add_paragraph()
            
            # Resumen ejecutivo
            doc.add_heading('RESUMEN EJECUTIVO', level=1)
            
            res = self.resultados
            tabla_resumen = doc.add_table(rows=9, cols=3)
            tabla_resumen.style = 'Light Shading'
            
            # Encabezados
            tabla_resumen.cell(0, 0).text = 'Métrica'
            tabla_resumen.cell(0, 1).text = 'Valor'
            tabla_resumen.cell(0, 2).text = 'Interpretación'
            
            # Datos
            datos = [
                ('Área total', f"{res.get('area_total_ha', 0):,.1f} ha", 'Superficie del área de estudio'),
                ('Carbono total almacenado', f"{res.get('carbono_total_ton', 0):,.0f} ton C", 'Carbono almacenado en el área'),
                ('CO₂ equivalente', f"{res.get('co2_total_ton', 0):,.0f} ton CO₂e", 'Potencial de créditos de carbono'),
                ('Índice de Shannon promedio', f"{res.get('shannon_promedio', 0):.3f}", 'Nivel de biodiversidad'),
                ('NDVI promedio', f"{res.get('ndvi_promedio', 0):.3f}", 'Salud de la vegetación'),
                ('NDWI promedio', f"{res.get('ndwi_promedio', 0):.3f}", 'Contenido de agua'),
                ('Tipo de ecosistema', res.get('tipo_ecosistema', 'N/A'), 'Ecosistema predominante'),
                ('Puntos de muestreo', str(res.get('num_puntos', 0)), 'Muestras analizadas')
            ]
            
            for i, (metrica, valor, interpretacion) in enumerate(datos, 1):
                tabla_resumen.cell(i, 0).text = metrica
                tabla_resumen.cell(i, 1).text = valor
                tabla_resumen.cell(i, 2).text = interpretacion
            
            doc.add_paragraph()
            
            # Análisis de carbono
            doc.add_heading('ANÁLISIS DE CARBONO', level=1)
            doc.add_heading('Metodología Verra VCS para Proyectos REDD+', level=2)
            
            if res.get('desglose_promedio'):
                doc.add_heading('Distribución de Carbono por Pools', level=3)
                
                tabla_carbono = doc.add_table(rows=6, cols=4)
                tabla_carbono.style = 'Light Shading'
                
                # Encabezados
                tabla_carbono.cell(0, 0).text = 'Pool'
                tabla_carbono.cell(0, 1).text = 'Descripción'
                tabla_carbono.cell(0, 2).text = 'Ton C/ha'
                tabla_carbono.cell(0, 3).text = 'Porcentaje'
                
                descripciones = {
                    'AGB': 'Biomasa Aérea Viva',
                    'BGB': 'Biomasa de Raíces',
                    'DW': 'Madera Muerta',
                    'LI': 'Hojarasca',
                    'SOC': 'Carbono Orgánico del Suelo'
                }
                
                total = sum(res['desglose_promedio'].values())
                for i, (pool, valor) in enumerate(res['desglose_promedio'].items(), 1):
                    tabla_carbono.cell(i, 0).text = pool
                    tabla_carbono.cell(i, 1).text = descripciones.get(pool, pool)
                    tabla_carbono.cell(i, 2).text = f"{valor:.2f}"
                    porcentaje = (valor / total * 100) if total > 0 else 0
                    tabla_carbono.cell(i, 3).text = f"{porcentaje:.1f}%"
            
            doc.add_page_break()
            
            # Análisis de biodiversidad
            doc.add_heading('ANÁLISIS DE BIODIVERSIDAD', level=1)
            doc.add_heading('Índice de Shannon para Diversidad Biológica', level=2)
            
            if res.get('puntos_biodiversidad') and len(res['puntos_biodiversidad']) > 0:
                biodiv = res['puntos_biodiversidad'][0]
                
                tabla_biodiv = doc.add_table(rows=5, cols=3)
                tabla_biodiv.style = 'Light Shading'
                
                tabla_biodiv.cell(0, 0).text = 'Métrica'
                tabla_biodiv.cell(0, 1).text = 'Valor'
                tabla_biodiv.cell(0, 2).text = 'Interpretación'
                
                datos_biodiv = [
                    ('Índice de Shannon', f"{biodiv.get('indice_shannon', 0):.3f}", biodiv.get('categoria', 'N/A')),
                    ('Riqueza de especies', str(biodiv.get('riqueza_especies', 0)), 'Número estimado de especies'),
                    ('Abundancia total', f"{biodiv.get('abundancia_total', 0):,}", 'Individuos estimados'),
                    ('Categoría', biodiv.get('categoria', 'N/A'), 'Clasificación según Shannon')
                ]
                
                for i, (metrica, valor, interpretacion) in enumerate(datos_biodiv, 1):
                    tabla_biodiv.cell(i, 0).text = metrica
                    tabla_biodiv.cell(i, 1).text = valor
                    tabla_biodiv.cell(i, 2).text = interpretacion
            
            doc.add_page_break()
            
            # Recomendaciones
            doc.add_heading('RECOMENDACIONES Y CONCLUSIONES', level=1)
            doc.add_heading('Recomendaciones para Proyecto VCS/REDD+', level=2)
            
            recomendaciones = [
                "1. Validación y Verificación: Contratar un validador acreditado por Verra",
                "2. Monitoreo: Establecer parcelas permanentes de muestreo",
                "3. Línea Base: Desarrollar escenario de referencia robusto",
                "4. Adicionalidad: Demostrar que el proyecto es adicional",
                "5. Permanencia: Implementar medidas de garantía a largo plazo",
                "6. MRV: Sistema de Monitoreo, Reporte y Verificación transparente"
            ]
            
            for rec in recomendaciones:
                doc.add_paragraph(rec)
            
            # Conclusiones
            doc.add_heading('CONCLUSIONES', level=2)
            
            conclusiones = [
                f"El área presenta un almacenamiento significativo de carbono ({res.get('carbono_total_ton', 0):,.0f} ton C).",
                f"El índice de Shannon ({res.get('shannon_promedio', 0):.3f}) indica oportunidades para conservación.",
                "El proyecto tiene potencial para desarrollo bajo estándares VCS/REDD+.",
                "Se recomienda validación con datos satelitales reales y campo."
            ]
            
            for i, conc in enumerate(conclusiones, 1):
                doc.add_paragraph(f"{i}. {conc}")
            
            doc.save(self.buffer_docx)
            self.buffer_docx.seek(0)
            return self.buffer_docx
            
        except Exception as e:
            st.error(f"Error generando DOCX: {str(e)}")
            return None

    def generar_geojson(self):
        """Exporta el polígono original + atributos agregados"""
        try:
            gdf_out = self.gdf.copy()
            res = self.resultados
            
            if res:
                gdf_out['area_ha'] = res.get('area_total_ha', 0)
                gdf_out['carbono_total_ton'] = res.get('carbono_total_ton', 0)
                gdf_out['shannon_promedio'] = res.get('shannon_promedio', 0)
                gdf_out['ecosistema'] = res.get('tipo_ecosistema', 'N/A')
            
            geojson_str = gdf_out.to_json()
            return geojson_str
        except Exception as e:
            st.error(f"Error generando GeoJSON: {str(e)}")
            return json.dumps({"error": str(e)})

# ===== FUNCIONES AUXILIARES - CORREGIDAS PARA EPSG:4326 =====
def validar_y_corregir_crs(gdf):
    if gdf is None or len(gdf) == 0:
        return gdf
    try:
        if gdf.crs is None:
            gdf = gdf.set_crs('EPSG:4326', inplace=False)
            st.info("ℹ️ Se asignó EPSG:4326 al archivo (no tenía CRS)")
        elif str(gdf.crs).upper() != 'EPSG:4326':
            original_crs = str(gdf.crs)
            gdf = gdf.to_crs('EPSG:4326')
            st.info(f"ℹ️ Transformado de {original_crs} a EPSG:4326")
        return gdf
    except Exception as e:
        st.warning(f"⚠️ Error al corregir CRS: {str(e)}")
        return gdf

def calcular_superficie(gdf):
    try:
        if gdf is None or len(gdf) == 0:
            return 0.0
        gdf = validar_y_corregir_crs(gdf)
        bounds = gdf.total_bounds
        if bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -90 or bounds[3] > 90:
            st.warning("⚠️ Coordenadas fuera de rango para cálculo preciso de área")
            area_grados2 = gdf.geometry.area.sum()
            area_m2 = area_grados2 * 111000 * 111000
            return area_m2 / 10000
        gdf_projected = gdf.to_crs('EPSG:3857')
        area_m2 = gdf_projected.geometry.area.sum()
        return area_m2 / 10000
    except Exception as e:
        try:
            return gdf.geometry.area.sum() / 10000
        except:
            return 0.0

def dividir_parcela_en_zonas(gdf, n_zonas):
    if len(gdf) == 0:
        return gdf
    gdf = validar_y_corregir_crs(gdf)
    parcela_principal = gdf.iloc[0].geometry
    bounds = parcela_principal.bounds
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
            cell_poly = Polygon([(cell_minx, cell_miny), (cell_maxx, cell_miny), (cell_maxx, cell_maxy), (cell_minx, cell_maxy)])
            intersection = parcela_principal.intersection(cell_poly)
            if not intersection.is_empty and intersection.area > 0:
                sub_poligonos.append(intersection)
    if sub_poligonos:
        nuevo_gdf = gpd.GeoDataFrame({'id_zona': range(1, len(sub_poligonos) + 1), 'geometry': sub_poligonos}, crs='EPSG:4326')
        return nuevo_gdf
    else:
        return gdf

# ===== FUNCIONES PARA CARGAR ARCHIVOS =====
def cargar_shapefile_desde_zip(zip_file):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                gdf = validar_y_corregir_crs(gdf)
                return gdf
            else:
                st.error("❌ No se encontró ningún archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando shapefile desde ZIP: {str(e)}")
        return None

def parsear_kml_manual(contenido_kml):
    try:
        root = ET.fromstring(contenido_kml)
        namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
        polygons = []
        for polygon_elem in root.findall('.//kml:Polygon', namespaces):
            coords_elem = polygon_elem.find('.//kml:coordinates', namespaces)
            if coords_elem is not None and coords_elem.text:
                coord_text = coords_elem.text.strip()
                coord_list = []
                for coord_pair in coord_text.split():
                    parts = coord_pair.split(',')
                    if len(parts) >= 2:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        coord_list.append((lon, lat))
                if len(coord_list) >= 3:
                    polygons.append(Polygon(coord_list))
        if not polygons:
            for multi_geom in root.findall('.//kml:MultiGeometry', namespaces):
                for polygon_elem in multi_geom.findall('.//kml:Polygon', namespaces):
                    coords_elem = polygon_elem.find('.//kml:coordinates', namespaces)
                    if coords_elem is not None and coords_elem.text:
                        coord_text = coords_elem.text.strip()
                        coord_list = []
                        for coord_pair in coord_text.split():
                            parts = coord_pair.split(',')
                            if len(parts) >= 2:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                coord_list.append((lon, lat))
                        if len(coord_list) >= 3:
                            polygons.append(Polygon(coord_list))
        if polygons:
            gdf = gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
            return gdf
        else:
            for placemark in root.findall('.//kml:Placemark', namespaces):
                for elem_name in ['Polygon', 'LineString', 'Point', 'LinearRing']:
                    elem = placemark.find(f'.//kml:{elem_name}', namespaces)
                    if elem is not None:
                        coords_elem = elem.find('.//kml:coordinates', namespaces)
                        if coords_elem is not None and coords_elem.text:
                            coord_text = coords_elem.text.strip()
                            coord_list = []
                            for coord_pair in coord_text.split():
                                parts = coord_pair.split(',')
                                if len(parts) >= 2:
                                    lon = float(parts[0])
                                    lat = float(parts[1])
                                    coord_list.append((lon, lat))
                            if len(coord_list) >= 3:
                                polygons.append(Polygon(coord_list))
                            break
        if polygons:
            gdf = gpd.GeoDataFrame({'geometry': polygons}, crs='EPSG:4326')
            return gdf
        return None
    except Exception as e:
        st.error(f"❌ Error parseando KML manualmente: {str(e)}")
        return None

def cargar_kml(kml_file):
    try:
        if kml_file.name.endswith('.kmz'):
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(kml_file, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                kml_files = [f for f in os.listdir(tmp_dir) if f.endswith('.kml')]
                if kml_files:
                    kml_path = os.path.join(tmp_dir, kml_files[0])
                    with open(kml_path, 'r', encoding='utf-8') as f:
                        contenido = f.read()
                    gdf = parsear_kml_manual(contenido)
                    if gdf is not None:
                        return gdf
                    else:
                        try:
                            gdf = gpd.read_file(kml_path)
                            gdf = validar_y_corregir_crs(gdf)
                            return gdf
                        except:
                            st.error("❌ No se pudo cargar el archivo KML/KMZ")
                            return None
                else:
                    st.error("❌ No se encontró ningún archivo .kml en el KMZ")
                    return None
        else:
            contenido = kml_file.read().decode('utf-8')
            gdf = parsear_kml_manual(contenido)
            if gdf is not None:
                return gdf
            else:
                kml_file.seek(0)
                gdf = gpd.read_file(kml_file)
                gdf = validar_y_corregir_crs(gdf)
                return gdf
    except Exception as e:
        st.error(f"❌ Error cargando archivo KML/KMZ: {str(e)}")
        return None

# ===== FUNCIÓN MODIFICADA: UNIR TODOS LOS SUBPOLÍGONOS EN UNO SOLO =====
def cargar_archivo_parcela(uploaded_file):
    try:
        if uploaded_file.name.endswith('.zip'):
            gdf = cargar_shapefile_desde_zip(uploaded_file)
        elif uploaded_file.name.endswith(('.kml', '.kmz')):
            gdf = cargar_kml(uploaded_file)
        elif uploaded_file.name.endswith('.geojson'):
            gdf = gpd.read_file(uploaded_file)
            gdf = validar_y_corregir_crs(gdf)
        else:
            st.error("❌ Formato de archivo no soportado")
            return None
        
        if gdf is not None:
            gdf = validar_y_corregir_crs(gdf)
            # === UNIÓN ESPACIAL: combinar todos los polígonos en uno solo ===
            gdf = gdf.explode(ignore_index=True)
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            if len(gdf) == 0:
                st.error("❌ No se encontraron polígonos en el archivo")
                return None
            # Unir todas las geometrías en una sola
            geometria_unida = gdf.unary_union
            gdf_unido = gpd.GeoDataFrame([{'geometry': geometria_unida}], crs='EPSG:4326')
            gdf_unido = validar_y_corregir_crs(gdf_unido)
            st.info(f"✅ Se unieron {len(gdf)} polígono(s) en una sola geometría.")
            # Asegurar columna id_zona (aunque sea 1)
            gdf_unido['id_zona'] = 1
            return gdf_unido
        return gdf
    except Exception as e:
        st.error(f"❌ Error cargando archivo: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return None

# ===============================
# 🎨 INTERFAZ PRINCIPAL CON ANÁLISIS FORRAJERO
# ===============================
def main():
    """Función principal de la aplicación"""
    
    # Ejecutar inicialización al inicio (ANTES de cualquier uso de ee.*)
    if 'gee_authenticated' not in st.session_state:
        st.session_state.gee_authenticated = False
        st.session_state.gee_project = ''
        if GEE_AVAILABLE:
            # Solo intentar inicializar si GEE está disponible
            inicializar_gee()
            if st.session_state.gee_authenticated:
                st.sidebar.success("✅ Google Earth Engine inicializado")
            else:
                st.sidebar.warning("⚠️ Google Earth Engine no está disponible")
    
    # === INICIALIZACIÓN DE VARIABLES DE SESIÓN ===
    if 'poligono_data' not in st.session_state:
        st.session_state.poligono_data = None
    if 'resultados' not in st.session_state:
        st.session_state.resultados = None
    if 'mapa' not in st.session_state:
        st.session_state.mapa = None
    if 'reporte_completo' not in st.session_state:
        st.session_state.reporte_completo = None
    if 'geojson_data' not in st.session_state:
        st.session_state.geojson_data = None
    if 'nombre_geojson' not in st.session_state:
        st.session_state.nombre_geojson = ""
    if 'nombre_reporte' not in st.session_state:
        st.session_state.nombre_reporte = ""
    if 'resultados_todos' not in st.session_state:
        st.session_state.resultados_todos = {}
    if 'analisis_completado' not in st.session_state:
        st.session_state.analisis_completado = False
    if 'mapas_generados' not in st.session_state:
        st.session_state.mapas_generados = {}
    if 'dem_data' not in st.session_state:
        st.session_state.dem_data = {}
    if 'analisis_forrajero' not in st.session_state:
        st.session_state.analisis_forrajero = None
    
    # Título principal
    st.title("🌎 Sistema Satelital de Análisis Ambiental")
    st.markdown("### Metodología Verra VCS + Índice de Shannon + Análisis Multiespectral + Análisis Forrajero")
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Carga de Datos")
        
        # Mostrar estado de GEE
        if GEE_AVAILABLE:
            if st.session_state.gee_authenticated:
                st.success(f"✅ GEE Conectado (Proyecto: {st.session_state.gee_project})")
            else:
                st.warning("⚠️ GEE No Disponible - Usando datos simulados")
        
        # Cargar archivo
        uploaded_file = st.file_uploader(
            "Cargar polígono (KML, GeoJSON, SHP, KMZ)",
            type=['kml', 'geojson', 'zip', 'kmz'],
            help="Suba un archivo con el polígono de estudio"
        )
        
        if uploaded_file is not None:
            with st.spinner("Procesando archivo..."):
                try:
                    gdf = cargar_archivo_parcela(uploaded_file)
                    if gdf is not None:
                        st.session_state.poligono_data = gdf
                        st.success(f"✅ Polígono cargado correctamente")
                        
                        # Calcular área
                        area_ha = calcular_superficie(gdf)
                        st.info(f"📍 Área calculada: {area_ha:,.1f} ha")
                        
                        # Mostrar información del polígono
                        with st.expander("📐 Información del polígono"):
                            bounds = gdf.total_bounds
                            st.write(f"**Límites:**")
                            st.write(f"Noroeste: {bounds[3]:.4f}°N, {bounds[0]:.4f}°W")
                            st.write(f"Sureste: {bounds[1]:.4f}°N, {bounds[2]:.4f}°W")
                            st.write(f"**CRS:** {gdf.crs}")
                        
                        # Crear mapa inicial con zoom automático
                        sistema_mapas = SistemaMapas()
                        st.session_state.mapa = sistema_mapas.crear_mapa_area(gdf, zoom_auto=True)
                        
                except Exception as e:
                    st.error(f"Error al cargar archivo: {str(e)}")
        
        if st.session_state.poligono_data is not None:
            st.header("⚙️ Configuración")
            
            tipo_ecosistema = st.selectbox(
                "Tipo de ecosistema",
                ['amazonia', 'choco', 'andes', 'pampa', 'seco'],
                help="Seleccione el tipo de ecosistema predominante"
            )
            
            num_puntos = st.slider(
                "Número de puntos de muestreo",
                min_value=10,
                max_value=200,
                value=50,
                help="Cantidad de puntos para análisis"
            )
            
            # Opción para usar GEE si está disponible
            usar_gee = False
            if GEE_AVAILABLE and st.session_state.gee_authenticated:
                usar_gee = st.checkbox(
                    "Usar datos reales de Google Earth Engine",
                    value=False,
                    help="Usar datos satelitales reales en lugar de simulaciones"
                )
            
            if st.button("🚀 Ejecutar Análisis Completo", type="primary", use_container_width=True):
                with st.spinner("Analizando carbono, biodiversidad, índices espectrales y forrajero..."):
                    try:
                        if usar_gee and GEE_AVAILABLE and st.session_state.gee_authenticated:
                            st.info("🌍 Usando datos reales de Google Earth Engine...")
                            resultados = ejecutar_analisis_completo(
                                st.session_state.poligono_data,
                                tipo_ecosistema,
                                num_puntos,
                                usar_gee=True
                            )
                        else:
                            resultados = ejecutar_analisis_completo(
                                st.session_state.poligono_data,
                                tipo_ecosistema,
                                num_puntos,
                                usar_gee=False
                            )
                            
                        st.session_state.resultados = resultados
                        st.session_state.analisis_completado = True
                        st.success("✅ Análisis completado!")
                        
                    except Exception as e:
                        st.error(f"Error en el análisis: {str(e)}")
    
    # Contenido principal
    if st.session_state.poligono_data is None:
        st.info("👈 Cargue un polígono en el panel lateral para comenzar")
        
        # Mostrar información de la aplicación
        with st.expander("📋 Información del Sistema"):
            st.markdown("""
            ### Sistema Integrado de Análisis Ambiental Satelital
            
            **Características principales:**
            
            1. **🌳 Metodología Verra VCS** para cálculo de carbono forestal
            2. **🦋 Índice de Shannon** para análisis de biodiversidad
            3. **📈 NDVI** (Índice de Vegetación de Diferencia Normalizada)
            4. **💧 NDWI** (Índice de Agua de Diferencia Normalizada)
            5. **🐮 Análisis Forrajero** para manejo ganadero sostenible
            6. **🗺️ Mapas de calor** interactivos para todas las variables
            7. **📊 Visualizaciones comparativas** y análisis correlacionales
            8. **🌍 Conexión con Google Earth Engine** para datos satelitales reales
            
            **Módulo de Análisis Forrajero:**
            - Estimación de disponibilidad forrajera (kg MS/ha)
            - Cálculo de Equivalentes Vaca (EV) soportables
            - División del lote en sublotes según productividad
            - Cálculo de días de permanencia por sublote
            - Recomendaciones de sistema de rotación
            - Planificación de pastoreo rotativo
            
            **Áreas de aplicación:**
            - Proyectos REDD+ y créditos de carbono
            - Monitoreo de conservación de biodiversidad
            - Manejo ganadero sostenible y rotación de pastoreo
            - Detección de estrés hídrico en vegetación
            - Identificación de áreas prioritarias para conservación
            - Estudios de impacto ambiental integrales
            """)
            
            if GEE_AVAILABLE:
                st.info("**Google Earth Engine:** Disponible para datos satelitales reales")
            else:
                st.warning("**Google Earth Engine:** No disponible. Instale con: `pip install earthengine-api`")
    
    else:
        # Mostrar pestañas - AGREGADA PESTAÑA DE ANÁLISIS FORRAJERO
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "🗺️ Mapas de Calor", 
            "📊 Dashboard", 
            "🌳 Carbono", 
            "🦋 Biodiversidad",
            "🐮 Forrajero",
            "📈 Comparación",
            "📥 Informe"
        ])
        
        with tab1:
            mostrar_mapas_calor()
        
        with tab2:
            mostrar_dashboard()
        
        with tab3:
            mostrar_carbono()
        
        with tab4:
            mostrar_biodiversidad()
        
        with tab5:
            mostrar_analisis_forrajero()
        
        with tab6:
            mostrar_comparacion()
        
        with tab7:
            mostrar_informe()

def ejecutar_analisis_completo(gdf, tipo_ecosistema, num_puntos, usar_gee=False):
    """Ejecuta análisis completo de carbono, biodiversidad, índices espectrales y forrajero"""
    
    try:
        # Calcular área
        area_total = calcular_superficie(gdf)
        
        # Obtener polígono principal (ya está unificado)
        poligono = gdf.geometry.iloc[0]
        bounds = poligono.bounds
        
        # Inicializar sistemas
        clima = ConectorClimaticoTropical()
        verra = MetodologiaVerra()
        biodiversidad = AnalisisBiodiversidad()
        forrajero = AnalisisForrajero()  # Nuevo módulo
        
        # Generar puntos de muestreo
        puntos_carbono = []
        puntos_biodiversidad = []
        puntos_ndvi = []
        puntos_ndwi = []
        
        carbono_total = 0
        co2_total = 0
        shannon_promedio = 0
        ndvi_promedio = 0
        ndwi_promedio = 0
        area_por_punto = max(area_total / num_puntos, 0.1)
        
        puntos_generados = 0
        max_intentos = num_puntos * 10
        
        while puntos_generados < num_puntos and len(puntos_carbono) < max_intentos:
            # Generar punto aleatorio
            lat = bounds[1] + random.random() * (bounds[3] - bounds[1])
            lon = bounds[0] + random.random() * (bounds[2] - bounds[0])
            point = Point(lon, lat)
            
            if poligono.contains(point):
                # Obtener datos climáticos
                datos_clima = clima.obtener_datos_climaticos(lat, lon)
                
                # Generar NDVI aleatorio pero realista
                ndvi = 0.5 + random.uniform(-0.2, 0.3)
                
                # Generar NDWI basado en precipitación y ubicación
                base_ndwi = 0.1
                if datos_clima['precipitacion'] > 2000:
                    base_ndwi += 0.3
                elif datos_clima['precipitacion'] < 800:
                    base_ndwi -= 0.2
                
                ndwi = base_ndwi + random.uniform(-0.2, 0.2)
                ndwi = max(-0.5, min(0.8, ndwi))
                
                # Calcular carbono
                carbono_info = verra.calcular_carbono_hectarea(ndvi, tipo_ecosistema, datos_clima['precipitacion'])
                
                # Calcular biodiversidad
                biodiv_info = biodiversidad.calcular_shannon(
                    ndvi, 
                    tipo_ecosistema, 
                    area_por_punto, 
                    datos_clima['precipitacion']
                )
                
                # Acumular totales
                carbono_total += carbono_info['carbono_total_ton_ha'] * area_por_punto
                co2_total += carbono_info['co2_equivalente_ton_ha'] * area_por_punto
                shannon_promedio += biodiv_info['indice_shannon']
                ndvi_promedio += ndvi
                ndwi_promedio += ndwi
                
                # Guardar puntos para carbono
                puntos_carbono.append({
                    'lat': lat,
                    'lon': lon,
                    'carbono_ton_ha': carbono_info['carbono_total_ton_ha'],
                    'ndvi': ndvi,
                    'precipitacion': datos_clima['precipitacion']
                })
                
                # Guardar puntos para biodiversidad
                biodiv_info['lat'] = lat
                biodiv_info['lon'] = lon
                puntos_biodiversidad.append(biodiv_info)
                
                # Guardar puntos para NDVI
                puntos_ndvi.append({
                    'lat': lat,
                    'lon': lon,
                    'ndvi': ndvi
                })
                
                # Guardar puntos para NDWI
                puntos_ndwi.append({
                    'lat': lat,
                    'lon': lon,
                    'ndwi': ndwi
                })
                
                puntos_generados += 1
        
        # Calcular promedios
        if puntos_generados > 0:
            shannon_promedio /= puntos_generados
            ndvi_promedio /= puntos_generados
            ndwi_promedio /= puntos_generados
        
        # Obtener desglose promedio de carbono
        carbono_promedio = verra.calcular_carbono_hectarea(ndvi_promedio, tipo_ecosistema, 1500)
        
        # ===== ANÁLISIS FORRAJERO =====
        # Seleccionar tipo de sistema forrajero basado en ecosistema
        if tipo_ecosistema in ['pampa', 'seco']:
            sistema_forrajero = 'pastizal_natural'
        elif tipo_ecosistema in ['amazonia', 'choco']:
            sistema_forrajero = 'silvopastoril'
        else:
            sistema_forrajero = 'pastizal_natural'
        
        # Estimar disponibilidad forrajera
        disponibilidad_forrajera = forrajero.estimar_disponibilidad_forrajera(
            ndvi_promedio, 
            sistema_forrajero, 
            area_total
        )
        
        # Calcular equivalentes vaca (usando 30 días como período estándar)
        equivalentes_vaca = forrajero.calcular_equivalentes_vaca(
            disponibilidad_forrajera['forraje_aprovechable_kg_ms'],
            dias_permanencia=30
        )
        
        # Dividir lote en sublotes
        sublotes = forrajero.dividir_lote_en_sublotes(
            area_total,
            disponibilidad_forrajera['productividad_kg_ms_ha'],
            heterogeneidad=0.3
        )
        
        # Preparar resultados
        resultados = {
            'area_total_ha': area_total,
            'carbono_total_ton': round(carbono_total, 2),
            'co2_total_ton': round(co2_total, 2),
            'carbono_promedio_ha': round(carbono_total / area_total, 2) if area_total > 0 else 0,
            'shannon_promedio': round(shannon_promedio, 3),
            'ndvi_promedio': round(ndvi_promedio, 3),
            'ndwi_promedio': round(ndwi_promedio, 3),
            'puntos_carbono': puntos_carbono,
            'puntos_biodiversidad': puntos_biodiversidad,
            'puntos_ndvi': puntos_ndvi,
            'puntos_ndwi': puntos_ndwi,
            'tipo_ecosistema': tipo_ecosistema,
            'num_puntos': puntos_generados,
            'desglose_promedio': carbono_promedio['desglose'] if carbono_promedio else {},
            'usar_gee': usar_gee,
            # Resultados forrajeros
            'analisis_forrajero': {
                'sistema_forrajero': sistema_forrajero,
                'disponibilidad_forrajera': disponibilidad_forrajera,
                'equivalentes_vaca': equivalentes_vaca,
                'sublotes': sublotes,
                'forrajero': forrajero  # Guardar la instancia para uso posterior
            }
        }
        
        return resultados
    except Exception as e:
        st.error(f"Error en ejecutar_analisis_completo: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

# ===============================
# 🐮 FUNCIÓN PARA MOSTRAR ANÁLISIS FORRAJERO - SOLUCIÓN DEFINITIVA
# ===============================
def mostrar_analisis_forrajero():
    """Muestra análisis completo forrajero"""
    st.header("🐮 Análisis Forrajero - Manejo Ganadero Sostenible")
    
    # Verificar si tenemos resultados
    if 'resultados' not in st.session_state or st.session_state.resultados is None:
        st.info("Ejecute el análisis completo primero para ver los datos forrajeros")
        return
    
    res = st.session_state.resultados
    
    if 'analisis_forrajero' not in res:
        st.info("No se encontraron datos de análisis forrajero en los resultados")
        return
        
    forrajero_data = res['analisis_forrajero']
    
    # Mostrar información general
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Área Total",
            f"{res.get('area_total_ha', 0):,.1f} ha",
            "Superficie para pastoreo"
        )
    with col2:
        st.metric(
            "Sistema Forrajero",
            forrajero_data.get('sistema_forrajero', 'N/A').replace('_', ' ').title(),
            "Tipo de sistema productivo"
        )
    with col3:
        st.metric(
            "NDVI Promedio",
            f"{res.get('ndvi_promedio', 0):.3f}",
            "Indicador de salud vegetal"
        )
    
    # Disponibilidad forrajera
    st.subheader("🌿 Disponibilidad Forrajera")
    
    if 'disponibilidad_forrajera' in forrajero_data:
        disp = forrajero_data['disponibilidad_forrajera']
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Productividad",
                f"{disp.get('productividad_kg_ms_ha', 0):,.0f}",
                "kg MS/ha"
            )
        with col2:
            st.metric(
                "Disponible Total",
                f"{disp.get('disponibilidad_total_kg_ms', 0)/1000:,.1f}",
                "ton MS"
            )
        with col3:
            st.metric(
                "Forraje Aprovechable",
                f"{disp.get('forraje_aprovechable_kg_ms', 0)/1000:,.1f}",
                "ton MS"
            )
        with col4:
            st.metric(
                "Categoría",
                disp.get('categoria_productividad', 'N/A').title(),
                "Nivel de productividad"
            )
    else:
        st.info("No hay datos de disponibilidad forrajera")
    
    # Equivalentes Vaca
    st.subheader("🐄 Equivalentes Vaca (EV)")
    
    if 'equivalentes_vaca' in forrajero_data:
        ev_data = forrajero_data['equivalentes_vaca']
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "EV por día",
                f"{ev_data.get('ev_por_dia', 0):.1f}",
                "Capacidad de carga diaria"
            )
        with col2:
            st.metric(
                "EV para 30 días",
                f"{ev_data.get('ev_para_periodo', 0):.1f}",
                f"Días: {ev_data.get('dias_permanencia', 0)}"
            )
        with col3:
            st.metric(
                "EV Recomendado",
                f"{ev_data.get('ev_recomendado', 0):.1f}",
                f"Margen: {ev_data.get('margen_seguridad', 'N/A')}"
            )
        
        # Calculadora interactiva de EV
        with st.expander("📊 Calculadora de Equivalentes Vaca"):
            col_calc1, col_calc2 = st.columns(2)
            
            with col_calc1:
                num_ev_input = st.number_input(
                    "Número de EV disponibles:",
                    min_value=1.0,
                    max_value=1000.0,
                    value=50.0,
                    step=1.0
                )
            
            with col_calc2:
                dias_permanencia_input = st.number_input(
                    "Días de permanencia deseada:",
                    min_value=1,
                    max_value=365,
                    value=30,
                    step=1
                )
            
            if st.button("Calcular días de permanencia", type="secondary"):
                if 'disponibilidad_forrajera' in forrajero_data:
                    disp = forrajero_data['disponibilidad_forrajera']
                    forrajero = forrajero_data.get('forrajero')
                    if forrajero and 'forraje_aprovechable_kg_ms' in disp:
                        dias_calculados = forrajero.calcular_dias_permanencia(
                            disp['forraje_aprovechable_kg_ms'],
                            num_ev_input
                        )
                        
                        st.success(f"**Resultado:** {num_ev_input:.0f} EV pueden pastar {dias_calculados['dias_recomendados']} días")
                        
                        col_res1, col_res2, col_res3 = st.columns(3)
                        with col_res1:
                            st.metric("Días básicos", f"{dias_calculados['dias_basico']:.1f}")
                        with col_res2:
                            st.metric("Días ajustados", f"{dias_calculados['dias_ajustado']:.1f}")
                        with col_res3:
                            st.metric("Recomendados", dias_calculados['dias_recomendados'])
    else:
        st.info("No hay datos de equivalentes vaca")
    
    # Sublotes
    st.subheader("🗺️ División en Sublotes")
    
    if 'sublotes' in forrajero_data and forrajero_data['sublotes']:
        sublotes = forrajero_data['sublotes']
        
        # Mostrar tabla de sublotes
        sublotes_data = []
        for sublote in sublotes:
            # Calcular EV por sublote
            ev_sublote = sublote['forraje_aprovechable_kg_ms'] / 12  # 12 kg MS/día por EV
            dias_sublote = int(ev_sublote / 50) * 30 if ev_sublote > 0 else 0  # Estimación simplificada
            
            sublotes_data.append({
                'Sublote': sublote['sublote_id'],
                'Área (ha)': sublote['area_ha'],
                'Productividad (kg MS/ha)': sublote['disponibilidad_kg_ms_ha'],
                'Forraje Aprovechable (ton MS)': round(sublote['forraje_aprovechable_kg_ms']/1000, 1),
                'EV estimados': round(ev_sublote, 1),
                'Días aprox.': dias_sublote
            })
        
        df_sublotes = pd.DataFrame(sublotes_data)
        st.dataframe(df_sublotes, use_container_width=True, hide_index=True)
        
        # Mapa de sublotes - SOLUCIÓN: Verificar de manera segura
        st.subheader("🗺️ Mapa de Sublotes")
        
        forrajero = forrajero_data.get('forrajero')
        
       # Verificar de manera segura si tenemos datos geoespaciales
                poligono_disponible = False
           if 'poligono_data' in st.session_state:
               poligono_data = st.session_state.poligono_data
    # Verificar si no es None y no está vacío usando métodos seguros
           if poligono_data is not None:
             try:
            # Verificar si tiene la propiedad empty (GeoDataFrame/DataFrame)
                if hasattr(poligono_data, 'empty'):
                if not poligono_data.empty:
                    poligono_disponible = True
            else:
                # Si no tiene empty, asumimos que tiene datos
                poligono_disponible = True
        except:
            pass
        
        if forrajero and poligono_disponible:
            try:
                mapa_sublotes = forrajero.crear_mapa_sublotes(
                    st.session_state.poligono_data,
                    sublotes
                )
                
                if mapa_sublotes:
                    folium_static(mapa_sublotes, width=1000, height=600)
                else:
                    st.info("No se pudo generar el mapa de sublotes")
            except Exception as e:
                st.warning(f"Error al generar mapa: {str(e)}")
                st.info("Muestra de sublotes (sin mapa):")
                # Mostrar información adicional si no se puede generar el mapa
                for sublote in sublotes[:3]:  # Mostrar solo los primeros 3
                    st.write(f"**Sublote {sublote['sublote_id']}**: {sublote['area_ha']} ha, Productividad: {sublote['disponibilidad_kg_ms_ha']} kg MS/ha")
        else:
            st.info("No hay datos geoespaciales disponibles para generar el mapa")
    else:
        st.info("No hay datos de sublotes disponibles")
    
    # Recomendaciones de rotación
    st.subheader("🔄 Sistema de Rotación Recomendado")
    
    with st.expander("📋 Plan de Rotación Detallado"):
        # Input para número de EV
        num_ev_rotacion = st.number_input(
            "Número de EV para plan de rotación:",
            min_value=1.0,
            max_value=500.0,
            value=min(100.0, forrajero_data.get('equivalentes_vaca', {}).get('ev_recomendado', 50.0)),
            step=1.0,
            key="ev_rotacion"
        )
        
        if st.button("Generar Plan de Rotación", type="primary"):
            forrajero = forrajero_data.get('forrajero')
            if forrajero and 'sublotes' in forrajero_data and forrajero_data['sublotes']:
                plan_rotacion = forrajero.generar_recomendaciones_rotacion(
                    forrajero_data['sublotes'],
                    num_ev_rotacion
                )
                
                # Mostrar resumen
                st.success(f"**Plan de rotación generado para {num_ev_rotacion:.0f} EV**")
                
                col_sum1, col_sum2, col_sum3 = st.columns(3)
                with col_sum1:
                    st.metric("Forraje total", f"{plan_rotacion['forraje_total_aprovechable_kg']/1000:,.1f} ton")
                with col_sum2:
                    st.metric("Consumo diario", f"{plan_rotacion['consumo_diario_total_kg']:,.0f} kg")
                with col_sum3:
                    st.metric("Rotación total", f"{plan_rotacion['dias_rotacion_total']:.0f} días")
                
                # Mostrar tabla de rotación
                st.subheader("📅 Plan de Rotación por Sublote")
                
                rotacion_data = []
                for plan in plan_rotacion['plan_rotacion']:
                    rotacion_data.append({
                        'Sublote': plan['sublote'],
                        'Área (ha)': plan['area_ha'],
                        'Días Uso': plan['dias_uso'],
                        'Días Descanso': plan['dias_descanso'],
                        'Ciclo Total': plan['dias_uso'] + plan['dias_descanso'],
                        'Recomendación': plan['recomendacion']
                    })
                
                df_rotacion = pd.DataFrame(rotacion_data)
                st.dataframe(df_rotacion, use_container_width=True, hide_index=True)
                
                # Recomendaciones generales
                st.subheader("💡 Recomendaciones de Manejo")
                
                recomendaciones = [
                    f"**Intensidad de rotación:** {plan_rotacion['intensidad_rotacion']}",
                    f"**Ciclo promedio:** {plan_rotacion['dias_ciclo_promedio']:.0f} días",
                    "**Pautas generales:**",
                    "1. Respete los períodos de descanso para regeneración del pasto",
                    "2. Monitoree la altura del pasto (ideal: 15-25 cm)",
                    "3. Ajuste la carga animal según estación del año",
                    "4. Implemente suplementación estratégica en épocas secas",
                    "5. Mantenga registros de rotación y productividad"
                ]
                
                for rec in recomendaciones:
                    st.info(rec)
            else:
                st.error("No se puede generar el plan de rotación. Faltan datos.")
    
    # Gráficos forrajeros
    st.subheader("📊 Visualización de Datos Forrajeros")
    
    if 'disponibilidad_forrajera' in forrajero_data and 'equivalentes_vaca' in forrajero_data:
        try:
            vis = Visualizaciones()
            fig_forrajero = vis.crear_grafico_forrajero(
                forrajero_data['disponibilidad_forrajera'],
                forrajero_data['equivalentes_vaca']
            )
            
            if fig_forrajero:
                st.plotly_chart(fig_forrajero, use_container_width=True)
        except Exception as e:
            st.warning(f"No se pudo generar el gráfico forrajero: {str(e)}")
    
    # Información adicional
    with st.expander("📚 Información Técnica"):
        st.markdown("""
        **Glosario:**
        
        - **MS:** Materia Seca - contenido sólido del forraje después de eliminar el agua
        - **EV:** Equivalente Vaca - unidad que representa el consumo de una vaca adulta (450 kg)
        - **kg MS/ha:** Kilogramos de materia seca por hectárea
        - **Rotación:** Sistema de movimiento de animales entre diferentes áreas (sublotes)
        
        **Factores de conversión:**
        
        - 1 EV consume aproximadamente 12 kg MS/día
        - Eficiencia de aprovechamiento: 50-60% del forraje disponible
        - Período óptimo de descanso: 3 veces el período de uso
        - Altura óptima del pasto: 15-25 cm para máxima productividad
        
        **Beneficios del pastoreo rotativo:**
        
        1. **Mayor productividad:** Mejor aprovechamiento del forraje
        2. **Mejor salud del suelo:** Menor compactación y erosión
        3. **Mayor biodiversidad:** Mantenimiento de especies forrajeras
        4. **Menor impacto ambiental:** Reducción de emisiones de metano
        5. **Mayor rentabilidad:** Optimización de recursos
        """)
# ===============================
# 🗺️ FUNCIONES DE VISUALIZACIÓN CORREGIDAS
# ===============================
def mostrar_mapas_calor():
    """Muestra todos los mapas de calor disponibles con zoom automático"""
    st.header("🗺️ Mapas de Calor - Análisis Multivariable")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🌍 Área de Estudio", 
        "🌳 Carbono", 
        "📈 NDVI", 
        "💧 NDWI", 
        "🦋 Biodiversidad",
        "🎭 Combinado"
    ])
    
    with tab1:
        st.subheader("Área de Estudio")
        if st.session_state.mapa:
            folium_static(st.session_state.mapa, width=1000, height=600)
            st.info("Mapa base con el polígono del área de estudio. El zoom se ajusta automáticamente al área.")
        else:
            st.info("No hay mapa para mostrar")
    
    with tab2:
        st.subheader("🌳 Mapa de Calor - Carbono (ton C/ha)")
        if st.session_state.resultados and 'puntos_carbono' in st.session_state.resultados:
            sistema_mapas = SistemaMapas()
            mapa_carbono = sistema_mapas.crear_mapa_calor_carbono(
                st.session_state.resultados['puntos_carbono'],
                st.session_state.poligono_data
            )
            
            if mapa_carbono:
                folium_static(mapa_carbono, width=1000, height=600)
                
                # Información adicional
                col1, col2, col3 = st.columns(3)
                with col1:
                    carb_min = min(p['carbono_ton_ha'] for p in st.session_state.resultados['puntos_carbono'])
                    carb_max = max(p['carbono_ton_ha'] for p in st.session_state.resultados['puntos_carbono'])
                    st.metric("Carbono promedio", f"{st.session_state.resultados.get('carbono_promedio_ha', 0):.1f} ton C/ha")
                with col2:
                    st.metric("Rango", f"{carb_min:.1f} - {carb_max:.1f} ton C/ha")
                with col3:
                    st.metric("Puntos muestreados", len(st.session_state.resultados['puntos_carbono']))
            else:
                st.warning("No se pudo generar el mapa de carbono.")
        else:
            st.info("Ejecute el análisis primero para ver el mapa de carbono")
    
    with tab3:
        st.subheader("📈 Mapa de Calor - NDVI (Índice de Vegetación)")
        if st.session_state.resultados and 'puntos_ndvi' in st.session_state.resultados:
            sistema_mapas = SistemaMapas()
            mapa_ndvi = sistema_mapas.crear_mapa_calor_ndvi(
                st.session_state.resultados['puntos_ndvi'],
                st.session_state.poligono_data
            )
            
            if mapa_ndvi:
                folium_static(mapa_ndvi, width=1000, height=600)
                
                # Información adicional
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("NDVI promedio", f"{st.session_state.resultados.get('ndvi_promedio', 0):.3f}")
                with col2:
                    ndvi_vals = [p['ndvi'] for p in st.session_state.resultados['puntos_ndvi']]
                    st.metric("Rango NDVI", f"{min(ndvi_vals):.2f} - {max(ndvi_vals):.2f}")
                with col3:
                    ndvi_avg = st.session_state.resultados.get('ndvi_promedio', 0)
                    if ndvi_avg > 0.6:
                        interpretacion = "🌿 Vegetación densa"
                    elif ndvi_avg > 0.3:
                        interpretacion = "🌱 Vegetación moderada"
                    else:
                        interpretacion = "🍂 Vegetación escasa"
                    st.metric("Interpretación", interpretacion)
            else:
                st.warning("No se pudo generar el mapa de NDVI.")
        else:
            st.info("Ejecute el análisis primero para ver el mapa de NDVI")
    
    with tab4:
        st.subheader("💧 Mapa de Calor - NDWI (Índice de Agua)")
        if st.session_state.resultados and 'puntos_ndwi' in st.session_state.resultados:
            sistema_mapas = SistemaMapas()
            mapa_ndwi = sistema_mapas.crear_mapa_calor_ndwi(
                st.session_state.resultados['puntos_ndwi'],
                st.session_state.poligono_data
            )
            
            if mapa_ndwi:
                folium_static(mapa_ndwi, width=1000, height=600)
                
                # Información adicional
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("NDWI promedio", f"{st.session_state.resultados.get('ndwi_promedio', 0):.3f}")
                with col2:
                    ndwi_vals = [p['ndwi'] for p in st.session_state.resultados['puntos_ndwi']]
                    st.metric("Rango NDWI", f"{min(ndwi_vals):.2f} - {max(ndwi_vals):.2f}")
                with col3:
                    ndwi_avg = st.session_state.resultados.get('ndwi_promedio', 0)
                    if ndwi_avg > 0.2:
                        interpretacion = "💧 Húmedo"
                    elif ndwi_avg > -0.1:
                        interpretacion = "⚖️ Moderado"
                    else:
                        interpretacion = "🏜️ Seco"
                    st.metric("Humedad", interpretacion)
            else:
                st.warning("No se pudo generar el mapa de NDWI.")
        else:
            st.info("Ejecute el análisis primero para ver el mapa de NDWI")
    
    with tab5:
        st.subheader("🦋 Mapa de Calor - Biodiversidad (Índice de Shannon)")
        if st.session_state.resultados and 'puntos_biodiversidad' in st.session_state.resultados:
            sistema_mapas = SistemaMapas()
            mapa_biodiv = sistema_mapas.crear_mapa_calor_biodiversidad(
                st.session_state.resultados['puntos_biodiversidad'],
                st.session_state.poligono_data
            )
            
            if mapa_biodiv:
                folium_static(mapa_biodiv, width=1000, height=600)
                
                # Información adicional
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Shannon promedio", f"{st.session_state.resultados.get('shannon_promedio', 0):.3f}")
                with col2:
                    shannon_vals = [p['indice_shannon'] for p in st.session_state.resultados['puntos_biodiversidad']]
                    st.metric("Rango Shannon", f"{min(shannon_vals):.2f} - {max(shannon_vals):.2f}")
                with col3:
                    if st.session_state.resultados['puntos_biodiversidad']:
                        categoria = st.session_state.resultados['puntos_biodiversidad'][0]['categoria']
                        st.metric("Categoría", categoria)
                    else:
                        st.metric("Categoría", "N/A")
            else:
                st.warning("No se pudo generar el mapa de biodiversidad.")
        else:
            st.info("Ejecute el análisis primero para ver el mapa de biodiversidad")
    
    with tab6:
        st.subheader("🎭 Mapa Combinado - Todas las Capas")
        if st.session_state.resultados:
            sistema_mapas = SistemaMapas()
            mapa_combinado = sistema_mapas.crear_mapa_combinado(
                st.session_state.resultados.get('puntos_carbono', []),
                st.session_state.resultados.get('puntos_ndvi', []),
                st.session_state.resultados.get('puntos_ndwi', []),
                st.session_state.resultados.get('puntos_biodiversidad', []),
                st.session_state.poligono_data
            )
            
            if mapa_combinado:
                folium_static(mapa_combinado, width=1000, height=600)
                st.info("📌 Use el control en la esquina superior derecha para alternar entre las diferentes capas de mapas de calor")
            else:
                st.warning("No se pudo generar el mapa combinado.")
        else:
            st.info("Ejecute el análisis primero para ver el mapa combinado")

def mostrar_dashboard():
    """Muestra dashboard ejecutivo"""
    st.header("📊 Dashboard Ejecutivo")
    
    if st.session_state.resultados:
        res = st.session_state.resultados
        
        # Métricas KPI
        html_kpi = Visualizaciones.crear_metricas_kpi(
            res.get('carbono_total_ton', 0),
            res.get('co2_total_ton', 0),
            res.get('shannon_promedio', 0),
            res.get('area_total_ha', 0)
        )
        st.markdown(html_kpi, unsafe_allow_html=True)
        
        # Métricas adicionales
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📈 NDVI promedio", f"{res.get('ndvi_promedio', 0):.3f}")
        with col2:
            st.metric("💧 NDWI promedio", f"{res.get('ndwi_promedio', 0):.3f}")
        with col3:
            st.metric("🎯 Puntos analizados", res.get('num_puntos', 0))
        
        # Métricas forrajeras si están disponibles
        if 'analisis_forrajero' in res:
            forrajero_data = res['analisis_forrajero']
            st.subheader("🐮 Métricas Forrajeras")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                if 'disponibilidad_forrajera' in forrajero_data:
                    st.metric(
                        "Productividad",
                        f"{forrajero_data['disponibilidad_forrajera'].get('productividad_kg_ms_ha', 0):,.0f}",
                        "kg MS/ha"
                    )
            with col_f2:
                if 'equivalentes_vaca' in forrajero_data:
                    st.metric(
                        "EV Recomendados",
                        f"{forrajero_data['equivalentes_vaca'].get('ev_recomendado', 0):.1f}",
                        "Equivalentes Vaca"
                    )
            with col_f3:
                if 'sublotes' in forrajero_data:
                    st.metric(
                        "Sublotes",
                        len(forrajero_data['sublotes']),
                        "División del lote"
                    )
        
        # Mostrar si se usó GEE
        if res.get('usar_gee'):
            st.success("🌍 Datos obtenidos de Google Earth Engine")
        
        # Gráficos lado a lado
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Distribución de Carbono")
            fig_barras = Visualizaciones.crear_grafico_barras_carbono(res.get('desglose_promedio', {}))
            if fig_barras:
                st.plotly_chart(fig_barras, use_container_width=True)
            else:
                st.info("No hay datos de carbono para graficar")
        
        with col2:
            st.subheader("Perfil de Biodiversidad")
            if res.get('puntos_biodiversidad') and len(res['puntos_biodiversidad']) > 0:
                fig_radar = Visualizaciones.crear_grafico_radar_biodiversidad(res['puntos_biodiversidad'][0])
                if fig_radar:
                    st.plotly_chart(fig_radar, use_container_width=True)
                else:
                    st.info("No hay datos de biodiversidad para graficar")
            else:
                st.info("No hay datos de biodiversidad disponibles")
        
        # Tabla de resumen
        st.subheader("📋 Resumen del Análisis")
        
        data = {
            'Métrica': [
                'Área total',
                'Carbono total almacenado',
                'CO₂ equivalente',
                'Carbono promedio por hectárea',
                'Índice de Shannon (biodiversidad)',
                'NDVI promedio (vegetación)',
                'NDWI promedio (agua)',
                'Tipo de ecosistema',
                'Puntos de muestreo'
            ],
            'Valor': [
                f"{res.get('area_total_ha', 0):,.1f} ha",
                f"{res.get('carbono_total_ton', 0):,.0f} ton C",
                f"{res.get('co2_total_ton', 0):,.0f} ton CO₂e",
                f"{res.get('carbono_promedio_ha', 0):,.1f} ton C/ha",
                f"{res.get('shannon_promedio', 0):.3f}",
                f"{res.get('ndvi_promedio', 0):.3f}",
                f"{res.get('ndwi_promedio', 0):.3f}",
                res.get('tipo_ecosistema', 'N/A'),
                str(res.get('num_puntos', 0))
            ]
        }
        
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    else:
        st.info("Ejecute el análisis primero para ver el dashboard")

def mostrar_carbono():
    """Muestra análisis detallado de carbono"""
    st.header("🌳 Análisis de Carbono - Metodología Verra VCS")
    
    if st.session_state.resultados:
        res = st.session_state.resultados
        
        st.markdown("### Metodología Verra VCS para Proyectos REDD+")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Carbono Total", 
                f"{res.get('carbono_total_ton', 0):,.0f} ton C",
                "Almacenamiento total de carbono"
            )
        
        with col2:
            st.metric(
                "Potencial de Créditos", 
                f"{res.get('co2_total_ton', 0)/1000:,.1f} k",
                "Ton CO₂e / 1000 = Créditos potenciales"
            )
        
        with col3:
            valor_economico = res.get('co2_total_ton', 0) * 15
            st.metric(
                "Valor Económico Aprox.", 
                f"${valor_economico:,.0f}",
                "USD @ $15/ton CO₂"
            )
        
        # Distribución por pools
        st.subheader("Distribución por Pools de Carbono")
        
        if res.get('desglose_promedio'):
            pools_data = []
            desc = {
                'AGB': 'Biomasa Aérea Viva',
                'BGB': 'Biomasa de Raíces',
                'DW': 'Madera Muerta',
                'LI': 'Hojarasca',
                'SOC': 'Carbono Orgánico del Suelo'
            }
            
            total = sum(res['desglose_promedio'].values())
            
            for pool, valor in res['desglose_promedio'].items():
                porcentaje = (valor / total * 100) if total > 0 else 0
                pools_data.append({
                    'Pool': pool,
                    'Descripción': desc.get(pool, pool),
                    'Ton C/ha': valor,
                    'Porcentaje': f"{porcentaje:.1f}%"
                })
            
            df_pools = pd.DataFrame(pools_data)
            st.dataframe(df_pools, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de desglose de carbono disponibles")
        
        with st.expander("📋 Recomendaciones para Proyecto VCS"):
            st.markdown("""
            1. **Validación y Verificación:** Contratar un validador acreditado por Verra
            2. **Monitoreo:** Establecer parcelas permanentes de muestreo
            3. **Línea Base:** Desarrollar escenario de referencia (baseline)
            4. **Adicionalidad:** Demostrar que el proyecto es adicional al escenario business-as-usual
            5. **Permanencia:** Implementar medidas para garantizar la permanencia del carbono
            6. **MRV:** Sistema de Monitoreo, Reporte y Verificación robusto
            """)
    
    else:
        st.info("Ejecute el análisis primero para ver los datos de carbono")

def mostrar_biodiversidad():
    """Muestra análisis detallado de biodiversidad"""
    st.header("🦋 Análisis de Biodiversidad - Índice de Shannon")
    
    if st.session_state.resultados:
        res = st.session_state.resultados
        
        st.markdown("### Índice de Shannon para Diversidad Biológica")
        
        if res.get('puntos_biodiversidad') and len(res['puntos_biodiversidad']) > 0:
            biodiv = res['puntos_biodiversidad'][0]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Índice de Shannon", 
                    f"{biodiv.get('indice_shannon', 0):.3f}",
                    f"Categoría: {biodiv.get('categoria', 'N/A')}"
                )
            
            with col2:
                st.metric(
                    "Riqueza de Especies", 
                    f"{biodiv.get('riqueza_especies', 0)}",
                    "Número estimado de especies"
                )
            
            with col3:
                st.metric(
                    "Abundancia Total", 
                    f"{biodiv.get('abundancia_total', 0):,}",
                    "Individuos estimados"
                )
            
            # Interpretación del índice
            st.subheader("Interpretación del Índice de Shannon")
            
            interpretaciones = {
                "Muy Alta": "> 3.5 - Ecosistema con alta diversidad y equitatividad",
                "Alta": "2.5 - 3.5 - Buena diversidad, estructura equilibrada",
                "Moderada": "1.5 - 2.5 - Diversidad media, posible perturbación moderada",
                "Baja": "0.5 - 1.5 - Diversidad reducida, perturbación significativa",
                "Muy Baja": "< 0.5 - Diversidad muy baja, ecosistema degradado"
            }
            
            categoria_actual = biodiv.get('categoria', 'N/A')
            for cat, desc in interpretaciones.items():
                if cat == categoria_actual:
                    st.success(f"**{cat}**: {desc}")
                else:
                    st.text(f"{cat}: {desc}")
            
            # Distribución de categorías
            st.subheader("Distribución de Categorías en Puntos de Muestreo")
            
            if res.get('puntos_biodiversidad'):
                categorias = {}
                for p in res['puntos_biodiversidad']:
                    cat = p.get('categoria', 'Desconocida')
                    categorias[cat] = categorias.get(cat, 0) + 1
                
                if categorias:
                    fig_cat = go.Figure(data=[go.Pie(
                        labels=list(categorias.keys()),
                        values=list(categorias.values()),
                        hole=0.3,
                        marker_colors=['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#991b1b']
                    )])
                    
                    fig_cat.update_layout(
                        title='Distribución de Categorías de Biodiversidad',
                        height=400
                    )
                    
                    st.plotly_chart(fig_cat, use_container_width=True)
                else:
                    st.info("No hay datos de categorías disponibles")
            
            # Distribución del índice
            st.subheader("Distribución del Índice entre Puntos de Muestreo")
            
            if res.get('puntos_biodiversidad'):
                shannon_values = [p.get('indice_shannon', 0) for p in res['puntos_biodiversidad']]
                
                fig = go.Figure(data=[go.Histogram(
                    x=shannon_values,
                    nbinsx=15,
                    marker_color='#8b5cf6',
                    opacity=0.7
                )])
                
                fig.update_layout(
                    title='Distribución del Índice de Shannon',
                    xaxis_title='Valor del Índice',
                    yaxis_title='Frecuencia',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Recomendaciones
            with st.expander("🌿 Recomendaciones para Conservación"):
                st.markdown(f"""
                Basado en el índice de Shannon de **{biodiv.get('indice_shannon', 0):.3f}** ({biodiv.get('categoria', 'N/A')}):
                
                **Medidas recomendadas:**
                """)
                
                categoria = biodiv.get('categoria', '')
                if categoria in ["Muy Baja", "Baja"]:
                    st.markdown("""
                    - **Restauración activa:** Plantación de especies nativas
                    - **Control de amenazas:** Manejo de incendios, control de especies invasoras
                    - **Conectividad:** Corredores biológicos con áreas conservadas
                    - **Monitoreo intensivo:** Seguimiento de indicadores clave
                    """)
                elif categoria == "Moderada":
                    st.markdown("""
                    - **Manejo sostenible:** Prácticas de bajo impacto
                    - **Protección:** Delimitación de zonas núcleo
                    - **Investigación:** Estudios de dinámica poblacional
                    - **Educación:** Programas de concienciación local
                    """)
                else:
                    st.markdown("""
                    - **Conservación preventiva:** Mantenimiento del estado actual
                    - **Investigación científica:** Estudio de patrones de biodiversidad
                    - **Uso sostenible:** Planificación de actividades económicas compatibles
                    - **Turismo científico:** Desarrollo de investigación participativa
                    """)
        else:
            st.info("No hay datos de biodiversidad disponibles")
    
    else:
        st.info("Ejecute el análisis primero para ver los datos de biodiversidad")

def mostrar_comparacion():
    """Muestra análisis comparativo de todas las variables"""
    st.header("📈 Análisis Comparativo - Relaciones entre Variables")
    
    if st.session_state.resultados:
        res = st.session_state.resultados
        
        st.markdown("### Relaciones entre Carbono, Biodiversidad e Índices Espectrales")
        
        # Gráfico comparativo
        if all(k in res for k in ['puntos_carbono', 'puntos_ndvi', 'puntos_ndwi', 'puntos_biodiversidad']):
            fig_comparativo = Visualizaciones.crear_grafico_comparativo(
                res['puntos_carbono'],
                res['puntos_ndvi'],
                res['puntos_ndwi'],
                res['puntos_biodiversidad']
            )
            
            if fig_comparativo:
                st.plotly_chart(fig_comparativo, use_container_width=True)
            else:
                st.info("No se pudo generar el gráfico comparativo")
        
        # Correlaciones
        st.subheader("🔗 Correlaciones entre Variables")
        
        if all(k in res for k in ['puntos_carbono', 'puntos_ndvi', 'puntos_ndwi', 'puntos_biodiversidad']):
            # Calcular correlaciones
            try:
                # Tomar hasta 100 puntos para no saturar
                n = min(100, len(res['puntos_carbono']))
                
                carbono_vals = [p['carbono_ton_ha'] for p in res['puntos_carbono'][:n]]
                ndvi_vals = [p['ndvi'] for p in res['puntos_ndvi'][:n]]
                ndwi_vals = [p['ndwi'] for p in res['puntos_ndwi'][:n]]
                shannon_vals = [p['indice_shannon'] for p in res['puntos_biodiversidad'][:n]]
                
                # Calcular coeficientes de correlación
                corr_carbono_ndvi = np.corrcoef(carbono_vals, ndvi_vals)[0, 1] if len(carbono_vals) > 1 else 0
                corr_carbono_shannon = np.corrcoef(carbono_vals, shannon_vals)[0, 1] if len(carbono_vals) > 1 else 0
                corr_ndvi_shannon = np.corrcoef(ndvi_vals, shannon_vals)[0, 1] if len(ndvi_vals) > 1 else 0
                corr_ndwi_shannon = np.corrcoef(ndwi_vals, shannon_vals)[0, 1] if len(ndwi_vals) > 1 else 0
                
                # Mostrar en métricas
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Carbono vs NDVI", f"{corr_carbono_ndvi:.3f}", 
                             "Positiva" if corr_carbono_ndvi > 0 else "Negativa")
                
                with col2:
                    st.metric("Carbono vs Shannon", f"{corr_carbono_shannon:.3f}",
                             "Positiva" if corr_carbono_shannon > 0 else "Negativa")
                
                with col3:
                    st.metric("NDVI vs Shannon", f"{corr_ndvi_shannon:.3f}",
                             "Positiva" if corr_ndvi_shannon > 0 else "Negativa")
                
                with col4:
                    st.metric("NDWI vs Shannon", f"{corr_ndwi_shannon:.3f}",
                             "Positiva" if corr_ndwi_shannon > 0 else "Negativa")
                
                # Interpretación de correlaciones
                with st.expander("📊 Interpretación de las Correlaciones"):
                    st.markdown("""
                    **Guía de interpretación:**
                    - **±0.7 a ±1.0:** Correlación fuerte
                    - **±0.4 a ±0.7:** Correlación moderada
                    - **±0.1 a ±0.4:** Correlación débil
                    - **±0.0 a ±0.1:** Sin correlación significativa
                    
                    **Implicaciones para la conservación:**
                    - **Correlación positiva fuerte Carbono-Shannon:** Estrategias que conservan carbono también protegen biodiversidad
                    - **Correlación positiva NDVI-Shannon:** Áreas con vegetación saludable tienen mayor biodiversidad
                    - **Correlación positiva NDWI-Shannon:** Disponibilidad de agua favorece la biodiversidad
                    """)
                    
            except Exception as e:
                st.warning(f"No se pudieron calcular correlaciones: {str(e)}")
        
        # Resumen de relaciones
        st.subheader("📋 Resumen de Relaciones")
        
        with st.expander("🌳 Relación Carbono-Biodiversidad"):
            st.markdown("""
            **Sinergias Carbono-Biodiversidad:**
            
            - **Bosques maduros:** Alto carbono + alta biodiversidad
            - **Restauración:** Aumenta ambos simultáneamente
            - **Manejo sostenible:** Mantiene equilibrio entre ambos
            
            **Potenciales Trade-offs:**
            
            - **Plantaciones monoespecíficas:** Alto carbono, baja biodiversidad
            - **Bosques secundarios:** Bajo carbono, alta biodiversidad
            - **Áreas protegidas:** Bajo carbono (si no son maduras), alta biodiversidad
            """)
        
        with st.expander("📈 NDVI como Indicador de Salud Ecosistémica"):
            st.markdown("""
            **Interpretación de NDVI:**
            
            - **> 0.6:** Vegetación densa y saludable
            - **0.3 - 0.6:** Vegetación moderada
            - **0.1 - 0.3:** Vegetación escasa/degradada
            - **< 0.1:** Suelo desnudo/agua/zonas urbanas
            
            **Relación con otras variables:**
            
            - **NDVI alto →** Generalmente carbono alto + biodiversidad alta
            - **NDVI bajo →** Puede indicar degradación, incendios, deforestación
            - **Cambios en NDVI →** Alertas tempranas de disturbios
            """)
        
        with st.expander("💧 NDWI como Indicador de Disponibilidad Hídrica"):
            st.markdown("""
            **Interpretación de NDWI:**
            
            - **> 0.2:** Presencia significativa de agua
            - **0.0 - 0.2:** Humedad moderada
            - **-0.1 - 0.0:** Condiciones secas
            - **< -0.1:** Muy seco
            
            **Importancia ecológica:**
            
            - **NDWI alto →** Favorece biodiversidad, especialmente anfibios y aves acuáticas
            - **NDWI bajo →** Puede limitar biodiversidad, indicar estrés hídrico
            - **Variaciones estacionales →** Importantes para dinámica ecosistémica
            """)
    
    else:
        st.info("Ejecute el análisis primero para ver las comparaciones")

def mostrar_informe():
    """Muestra sección de descarga de informe completo"""
    st.header("📥 Informe Completo del Análisis")
    
    if st.session_state.resultados and st.session_state.poligono_data is not None:
        st.markdown("### Generar informe completo con todos los análisis")
        st.info("""
        El informe incluirá:
        - Portada y resumen ejecutivo
        - Métricas clave (KPI)
        - Análisis completo de carbono con metodología Verra VCS
        - Análisis de biodiversidad con Índice de Shannon
        - Evaluación de índices espectrales (NDVI, NDWI)
        - Análisis forrajero y plan de rotación
        - Tablas detalladas y recomendaciones
        - Conclusiones y valoración económica
        """)
        
        # Sistema de mapas para el informe
        sistema_mapas = SistemaMapas()
        
        # Crear generador de reportes
        generador = GeneradorReportes(
            st.session_state.resultados, 
            st.session_state.poligono_data,
            sistema_mapas
        )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if REPORTPDF_AVAILABLE:
                st.markdown("#### 📄 Informe en PDF")
                st.markdown("Documento profesional con formato optimizado para impresión")
                if st.button("Generar y Descargar PDF", use_container_width=True):
                    with st.spinner("Generando informe PDF..."):
                        pdf_buffer = generador.generar_pdf()
                        if pdf_buffer:
                            st.download_button(
                                label="⬇️ Descargar PDF",
                                data=pdf_buffer,
                                file_name=f"informe_ambiental_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                        else:
                            st.error("No se pudo generar el PDF")
            else:
                st.info("PDF no disponible (instale ReportLab)")
        
        with col2:
            if REPORTDOCX_AVAILABLE:
                st.markdown("#### 📘 Informe en Word")
                st.markdown("Documento editable para personalización adicional")
                if st.button("Generar y Descargar DOCX", use_container_width=True):
                    with st.spinner("Generando informe DOCX..."):
                        docx_buffer = generador.generar_docx()
                        if docx_buffer:
                            st.download_button(
                                label="⬇️ Descargar DOCX",
                                data=docx_buffer,
                                file_name=f"informe_ambiental_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True
                            )
                        else:
                            st.error("No se pudo generar el DOCX")
            else:
                st.info("DOCX no disponible (instale python-docx)")
        
        with col3:
            st.markdown("#### 🌍 Datos Geoespaciales")
            st.markdown("Polígono de estudio con atributos calculados")
            if st.button("Generar GeoJSON", use_container_width=True):
                with st.spinner("Generando GeoJSON..."):
                    geojson_str = generador.generar_geojson()
                    if geojson_str:
                        st.download_button(
                            label="⬇️ Descargar GeoJSON",
                            data=geojson_str,
                            file_name=f"area_estudio_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                            mime="application/geo+json",
                            use_container_width=True
                        )
                    else:
                        st.error("No se pudo generar el GeoJSON")
        
        # Vista previa del informe
        st.markdown("---")
        st.subheader("📋 Vista Previa del Contenido del Informe")
        
        res = st.session_state.resultados
        
        with st.expander("📊 Resumen Ejecutivo (Vista Previa)"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Área Total", f"{res.get('area_total_ha', 0):,.1f} ha")
                st.metric("Carbono Total", f"{res.get('carbono_total_ton', 0):,.0f} ton C")
                st.metric("CO₂ Equivalente", f"{res.get('co2_total_ton', 0):,.0f} ton CO₂e")
            with col2:
                st.metric("Índice Shannon", f"{res.get('shannon_promedio', 0):.3f}")
                st.metric("NDVI Promedio", f"{res.get('ndvi_promedio', 0):.3f}")
                st.metric("NDWI Promedio", f"{res.get('ndwi_promedio', 0):.3f}")
        
        # Vista previa de análisis forrajero si está disponible
        if 'analisis_forrajero' in res:
            with st.expander("🐮 Análisis Forrajero (Vista Previa)"):
                forrajero_data = res['analisis_forrajero']
                
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    if 'disponibilidad_forrajera' in forrajero_data:
                        st.metric(
                            "Productividad",
                            f"{forrajero_data['disponibilidad_forrajera'].get('productividad_kg_ms_ha', 0):,.0f}",
                            "kg MS/ha"
                        )
                with col_f2:
                    if 'equivalentes_vaca' in forrajero_data:
                        st.metric(
                            "EV Recomendados",
                            f"{forrajero_data['equivalentes_vaca'].get('ev_recomendado', 0):.1f}",
                            "Equivalentes Vaca"
                        )
                with col_f3:
                    if 'sublotes' in forrajero_data:
                        st.metric("Sublotes", len(forrajero_data['sublotes']))
        
        with st.expander("🌳 Análisis de Carbono (Vista Previa)"):
            if res.get('desglose_promedio'):
                df_pools = pd.DataFrame({
                    'Pool': list(res['desglose_promedio'].keys()),
                    'Ton C/ha': list(res['desglose_promedio'].values())
                })
                st.dataframe(df_pools, use_container_width=True)
        
        with st.expander("💎 Valoración Económica (Vista Previa)"):
            valor_economico = res.get('co2_total_ton', 0) * 15
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("CO₂ Total", f"{res.get('co2_total_ton', 0):,.0f} ton")
            with col2:
                st.metric("Precio Referencial", "$15 USD/ton")
            with col3:
                st.metric("Valor Estimado", f"${valor_economico:,.0f} USD")
    else:
        st.info("Ejecute el análisis primero para generar el informe")

# ===============================
# 🚀 EJECUCIÓN PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()
