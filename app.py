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
import json

# Importaciones para PDF
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Importaciones opcionales para folium
try:
    import folium
    from folium import plugins
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError as e:
    st.warning("Folium no está disponible. La funcionalidad de mapas interactivos estará limitada.")
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Configuración de la página
st.set_page_config(page_title="Analizador Forrajero GEE", layout="wide")
st.title("ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'area_total' not in st.session_state:
    st.session_state.area_total = 0.0
if 'pdf_generado' not in st.session_state:
    st.session_state.pdf_generado = False
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None
if 'configuracion' not in st.session_state:
    st.session_state.configuracion = {
        'ms_optimo': 4000,
        'crecimiento_diario': 80,
        'consumo_porcentaje': 0.025,
        'tasa_utilizacion': 0.55,
        'umbral_ndvi_suelo': 0.15,
        'umbral_ndvi_pastura': 0.6
    }

# RECOMENDACIONES DE GANADERÍA REGENERATIVA
RECOMENDACIONES_REGENERATIVAS = {
    'ALFALFA': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Sistema de pastoreo rotacional intensivo (PRV) - 1-3 días por potrero",
            "Integración con leguminosas nativas para fijación de nitrógeno",
            "Uso de biofertilizantes a base de microorganismos nativos",
            "Siembra de bancos de proteína con variedades nativas"
        ],
        'MANEJO_SUELO': [
            "Aplicación de compost de 2-3 ton/ha en épocas secas",
            "Uso de harinas de rocas para mineralización",
            "Inoculación con micorrizas para mejor absorción",
            "Coberturas vivas con tréboles y otras leguminosas"
        ],
        'BIODIVERSIDAD': [
            "Corredores biológicos con vegetación nativa",
            "Cercas vivas con especies multipropósito",
            "Rotación con cultivos de cobertura en épocas lluviosas",
            "Manejo integrado de plagas con control biológico"
        ],
        'AGUA_RETENCIÓN': [
            "Swales (zanjas de infiltración) en pendientes suaves",
            "Keyline design para manejo de aguas",
            "Mulching con residuos vegetales locales",
            "Sistemas de riego por goteo con agua de lluvia"
        ]
    },
    'RAYGRASS': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo ultra rápido - 12-24 horas por lote",
            "Descansos prolongados de 45-60 días entre pastoreos",
            "Mezcla con trébol blanco y rojo para fijación N",
            "Uso de gallinas después del pastoreo bovino"
        ],
        'MANEJO_SUELO': [
            "Aplicación de té de compost cada 30 días",
            "Mineralización con fosfatos naturales",
            "Inoculación con bacterias fijadoras",
            "Aporques para mejorar estructura del suelo"
        ],
        'BIODIVERSIDAD': [
            "Asociación con chicoria y plantago",
            "Bordes diversificados con plantas aromáticas",
            "Rotación con avena forrajera en invierno",
            "Manejo de altura de pastoreo (8-10 cm)"
        ],
        'AGUA_RETENCIÓN': [
            "Cosecha de agua de lluvia en microrepresas",
            "Puntos de bebederos móviles",
            "Sombras naturales con árboles nativos",
            "Cobertura permanente del suelo"
        ]
    },
    'FESTUCA': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo racional Voisin - 4-7 días por poteo",
            "Integración avícola después del pastoreo bovino",
            "Uso de árboles forrajeros (Leucaena, Moringa)",
            "Sistemas silvopastoriles intensivos"
        ],
        'MANEJO_SUELO': [
            "Aplicación de bokashi especializado",
            "Enmiendas con carbonatos naturales",
            "Inoculación con trichoderma",
            "Labranza cero con siembra directa"
        ],
        'BIODIVERSIDAD': [
            "Mezclas con pastos nativos adaptados",
            "Cercas vivas con gliricidia y eritrina",
            "Rotación con kikuyo en zonas altas",
            "Control mecánico de malezas selectivas"
        ],
        'AGUA_RETENCIÓN': [
            "Terrazas de absorción en laderas",
            "Sistemas de riego por aspersión eficiente",
            "Barreras vivas contra erosión",
            "Retención de humedad con mulching"
        ]
    },
    'AGROPIRRO': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo de precisión según biomasa disponible",
            "Integración con porcinos en lotes específicos",
            "Uso de abonos verdes entre rotaciones",
            "Sistemas agrosilvopastoriles"
        ],
        'MANEJO_SUELO': [
            "Aplicación de humus de lombriz",
            "Enmiendas con yeso agrícola",
            "Inoculación con azospirillum",
            "Coberturas muertas con paja"
        ],
        'BIODIVERSIDAD': [
            "Asociación con brachiaria en zonas bajas",
            "Plantas repelentes naturales en bordes",
            "Rotación con sorgo forrajero",
            "Manejo diferenciado por microclimas"
        ],
        'AGUA_RETENCIÓN': [
            "Zanjas de drenaje y retención",
            "Sistemas de sub-riego",
            "Cultivo en curvas a nivel",
            "Protección de fuentes hídricas"
        ]
    },
    'PASTIZAL_NATURAL': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo holístico planificado",
            "Manejo adaptativo multipaddock",
            "Regeneración de pastos nativos",
            "Uso de herbívoros mixtos (ovinos, caprinos)"
        ],
        'MANEJO_SUELO': [
            "Regeneración con microorganismos eficientes",
            "Mineralización con rocas molidas locales",
            "Inoculación con hongos micorrízicos nativos",
            "Coberturas con especies pioneras"
        ],
        'BIODIVERSIDAD': [
            "Recuperación de bancos de semillas nativas",
            "Corredores de conectividad ecológica",
            "Manejo de carga animal según estacionalidad",
            "Protección de áreas de regeneración natural"
        ],
        'AGUA_RETENCIÓN': [
            "Restauración de quebradas y nacimientos",
            "Sistemas de cosecha de aguas lluvias",
            "Manejo de escorrentías con geomembranas",
            "Recarga de acuíferos con técnicas permaculturales"
        ]
    },
    'PERSONALIZADO': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Diseño de sistema según condiciones específicas del terreno",
            "Monitoreo continuo con ajustes adaptativos",
            "Integración animal según recursos disponibles",
            "Planificación holística del manejo"
        ],
        'MANEJO_SUELO': [
            "Análisis de suelo para enmiendas específicas",
            "Regeneración según diagnóstico particular",
            "Uso de insumos locales disponibles",
            "Técnicas adaptadas a la topografía"
        ],
        'BIODIVERSIDAD': [
            "Selección de especies según microclimas",
            "Diseño de paisaje productivo diversificado",
            "Manejo de sucesión ecológica",
            "Conservación de germoplasma local"
        ],
        'AGUA_RETENCIÓN': [
            "Diseño hidrológico keyline adaptado",
            "Sistemas de captación y almacenamiento",
            "Manejo eficiente según disponibilidad hídrica",
            "Técnicas de retención específicas para el terreno"
        ]
    }
}

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 5000,
        'CRECIMIENTO_DIARIO': 100,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.6,
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 4500,
        'CRECIMIENTO_DIARIO': 90,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.6,
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.65,
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 60,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.65,
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 40,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.7,
    }
}

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': st.session_state.configuracion['ms_optimo'],
            'CRECIMIENTO_DIARIO': st.session_state.configuracion['crecimiento_diario'],
            'CONSUMO_PORCENTAJE_PESO': st.session_state.configuracion['consumo_porcentaje'],
            'DIGESTIBILIDAD': 0.60,
            'PROTEINA_CRUDA': 0.12,
            'TASA_UTILIZACION_RECOMENDADA': st.session_state.configuracion['tasa_utilizacion'],
            'UMBRAL_NDVI_SUELO': st.session_state.configuracion['umbral_ndvi_suelo'],
            'UMBRAL_NDVI_PASTURA': st.session_state.configuracion['umbral_ndvi_pastura'],
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

def calcular_superficie(gdf):
    """
    Calcula el área en hectáreas.
    - Si es un solo polígono → float
    - Si son múltiples → pd.Series
    """
    try:
        if gdf.empty:
            return 0.0 if len(gdf) <= 1 else pd.Series([0.0] * len(gdf))
        
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        
        areas_ha = area_m2 / 10000
        return float(areas_ha.iloc[0]) if len(gdf) == 1 else areas_ha
            
    except Exception as e:
        st.warning(f"Error en proyección: {e}. Usando área sin proyectar.")
        areas_ha = gdf.geometry.area / 10000
        return float(areas_ha.iloc[0]) if len(gdf) == 1 else areas_ha

def dividir_potrero_en_subLotes(gdf, n_zonas):
    if len(gdf) == 0 or gdf.iloc[0].geometry is None:
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

# =============================================================================
# FUNCIONES DE MAPAS
# =============================================================================
if FOLIUM_AVAILABLE:
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

    def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"):
        if gdf is None or len(gdf) == 0:
            return None
       
        centroid = gdf.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
       
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=14,
            tiles=None,
            control_scale=True
        )
       
        for map_name, config in BASE_MAPS_CONFIG.items():
            folium.TileLayer(
                tiles=config["tiles"],
                attr=config["attr"],
                name=config["name"],
                overlay=False,
                control=True
            ).add_to(m)
       
        selected_config = BASE_MAPS_CONFIG[base_map_name]
        folium.TileLayer(
            tiles=selected_config["tiles"],
            attr=selected_config["attr"],
            name=selected_config["name"],
            overlay=True
        ).add_to(m)
       
        folium.GeoJson(
            gdf.__geo_interface__,
            style_function=lambda x: {
                'fillColor': '#3388ff',
                'color': 'blue',
                'weight': 2,
                'fillOpacity': 0.2
            }
        ).add_to(m)
       
        folium.LayerControl().add_to(m)
       
        folium.Marker(
            [center_lat, center_lon],
            popup=f"Centro del Potrero\nLat: {center_lat:.4f}\nLon: {center_lon:.4f}",
            tooltip="Centro del Potrero",
            icon=folium.Icon(color='green', icon='info-sign')
        ).add_to(m)
       
        return m

    def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"):
        if gdf_analizado is None or len(gdf_analizado) == 0:
            return None
       
        centroid = gdf_analizado.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
       
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=16,
            tiles=None,
            control_scale=True
        )
       
        esri_config = BASE_MAPS_CONFIG["ESRI Satélite"]
        folium.TileLayer(
            tiles=esri_config["tiles"],
            attr=esri_config["attr"],
            name=esri_config["name"],
            overlay=True
        ).add_to(m)
       
        for map_name, config in BASE_MAPS_CONFIG.items():
            if map_name != "ESRI Satélite":
                folium.TileLayer(
                    tiles=config["tiles"],
                    attr=config["attr"],
                    name=config["name"],
                    overlay=False,
                    control=True
                ).add_to(m)
       
        def estilo_por_superficie(feature):
            tipo_superficie = feature['properties']['tipo_superficie']
            colores = {
                'SUELO_DESNUDO': '#d73027',
                'SUELO_PARCIAL': '#fdae61',
                'VEGETACION_ESCASA': '#fee08b',
                'VEGETACION_MODERADA': '#a6d96a',
                'VEGETACION_DENSA': '#1a9850'
            }
            color = colores.get(tipo_superficie, '#3388ff')
            return {
                'fillColor': color,
                'color': 'black',
                'weight': 1.5,
                'fillOpacity': 0.6
            }
       
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
       
        colores_leyenda = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }
       
        legend_html = '''
        <div style="position: fixed;
                    bottom: 30px; left: 30px; width: 130px; height: auto;
                    background-color: white; border:2px solid grey; z-index:9999;
                    font-size:10px; padding: 10px">
        <p><strong>Tipos de Superficie</strong></p>
        '''
        for tipo, color in colores_leyenda.items():
            legend_html += f'<p><i style="background:{color}; width:13px; height:13px; display:inline-block; margin-right:4px;"></i> {tipo}</p>'
        legend_html += '</div>'
       
        m.get_root().html.add_child(folium.Element(legend_html))
        folium.LayerControl().add_to(m)
       
        return m
else:
    def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"):
        return None
   
    def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"):
        return None

# =============================================================================
# FUNCIONES DE ANÁLISIS
# =============================================================================
def simular_datos_satelitales(gdf, tipo_pastura, fecha_imagen):
    if gdf is None or len(gdf) == 0:
        return gdf
   
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    gdf_analizado = gdf.copy()
    np.random.seed(hash(fecha_imagen.strftime("%Y%m%d")) % 10000)
   
    resultados = []
   
    for idx, row in gdf_analizado.iterrows():
        geometry = row['geometry']
        area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf.crs))
       
        ndvi_base = np.random.normal(0.5, 0.2)
        ndvi_base = max(0.05, min(0.85, ndvi_base))
       
        efecto_estacional = 0.1 * np.sin(2 * np.pi * fecha_imagen.timetuple().tm_yday / 365)
        ndvi_ajustado = ndvi_base + efecto_estacional
       
        if ndvi_ajustado < parametros['UMBRAL_NDVI_SUELO']:
            tipo_superficie = 'SUELO_DESNUDO'
            biomasa = np.random.uniform(100, 500)
        elif ndvi_ajustado < parametros['UMBRAL_NDVI_SUELO'] + 0.1:
            tipo_superficie = 'SUELO_PARCIAL'
            biomasa = np.random.uniform(500, 1000)
        elif ndvi_ajustado < parametros['UMBRAL_NDVI_PASTURA'] - 0.1:
            tipo_superficie = 'VEGETACION_ESCASA'
            biomasa = np.random.uniform(1000, 2000)
        elif ndvi_ajustado < parametros['UMBRAL_NDVI_PASTURA']:
            tipo_superficie = 'VEGETACION_MODERADA'
            biomasa = np.random.uniform(2000, parametros['MS_POR_HA_OPTIMO'] * 0.8)
        else:
            tipo_superficie = 'VEGETACION_DENSA'
            biomasa = np.random.uniform(parametros['MS_POR_HA_OPTIMO'] * 0.8, parametros['MS_POR_HA_OPTIMO'] * 1.2)
       
        biomasa_ajustada = max(100, biomasa * (1 + (ndvi_ajustado - 0.5) * 0.5))
       
        resultados.append({
            'id_subLote': row['id_subLote'],
            'geometry': geometry,
            'ndvi': ndvi_ajustado,
            'tipo_superficie': tipo_superficie,
            'biomasa_disponible_kg_ms_ha': biomasa_ajustada,
            'area_ha': area_ha
        })
   
    return gpd.GeoDataFrame(resultados, crs=gdf.crs)

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return gdf_analizado
   
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    gdf_resultado = gdf_analizado.copy()
   
    consumo_diario_por_animal = peso_promedio * parametros['CONSUMO_PORCENTAJE_PESO']
    consumo_diario_total = consumo_diario_por_animal * carga_animal
   
    gdf_resultado['ev_ha'] = 0.0
    gdf_resultado['dias_permanencia'] = 0.0
    gdf_resultado['biomasa_disponible_kg'] = 0.0
   
    for idx, row in gdf_resultado.iterrows():
        biomasa_disponible_kg = row['biomasa_disponible_kg_ms_ha'] * row['area_ha']
       
        if consumo_diario_por_animal > 0:
            ev_ha = biomasa_disponible_kg / consumo_diario_por_animal
        else:
            ev_ha = 0
       
        if consumo_diario_total > 0:
            dias_permanencia = (biomasa_disponible_kg * parametros['TASA_UTILIZACION_RECOMENDADA']) / consumo_diario_total
        else:
            dias_permanencia = 0
       
        gdf_resultado.at[idx, 'ev_ha'] = ev_ha
        gdf_resultado.at[idx, 'dias_permanencia'] = dias_permanencia
        gdf_resultado.at[idx, 'biomasa_disponible_kg'] = biomasa_disponible_kg
   
    return gdf_resultado

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================
def mostrar_sidebar():
    with st.sidebar:
        st.header("Configuración")
       
        if FOLIUM_AVAILABLE:
            st.subheader("Mapa Base")
            base_map_option = st.selectbox(
                "Seleccionar mapa base:",
                ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
                index=0,
                key="mapa_base_selector"
            )
        else:
            base_map_option = "ESRI Satélite"
       
        st.subheader("Fuente de Datos Satelitales")
        fuente_satelital = st.selectbox(
            "Seleccionar satélite:",
            ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
            key="satelite_selector"
        )
       
        tipo_pastura = st.selectbox(
            "Tipo de Pastura:",
            ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"],
            key="pastura_selector"
        )
       
        st.subheader("Configuración Temporal")
        fecha_imagen = st.date_input(
            "Fecha de imagen satelital:",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now(),
            key="fecha_imagen_selector"
        )
       
        if tipo_pastura == "PERSONALIZADO":
            st.subheader("Parámetros Forrajeros Personalizados")
            st.session_state.configuracion['ms_optimo'] = st.number_input(
                "Biomasa Óptima (kg MS/ha):",
                min_value=1000, max_value=10000, value=4000,
                key="ms_optimo_input"
            )
            st.session_state.configuracion['crecimiento_diario'] = st.number_input(
                "Crecimiento Diario (kg MS/ha/día):",
                min_value=10, max_value=300, value=80,
                key="crecimiento_diario_input"
            )
            st.session_state.configuracion['consumo_porcentaje'] = st.number_input(
                "Consumo (% peso vivo):",
                min_value=0.01, max_value=0.05, value=0.025, step=0.001,
                key="consumo_porcentaje_input"
            )
            st.session_state.configuracion['tasa_utilizacion'] = st.number_input(
                "Tasa Utilización:",
                min_value=0.3, max_value=0.8, value=0.55, step=0.01,
                key="tasa_utilizacion_input"
            )
            st.session_state.configuracion['umbral_ndvi_suelo'] = st.number_input(
                "Umbral NDVI Suelo:",
                min_value=0.05, max_value=0.3, value=0.15, step=0.01,
                key="umbral_ndvi_suelo_input"
            )
            st.session_state.configuracion['umbral_ndvi_pastura'] = st.number_input(
                "Umbral NDVI Pastura:",
                min_value=0.3, max_value=0.8, value=0.6, step=0.01,
                key="umbral_ndvi_pastura_input"
            )
       
        st.subheader("Parámetros Ganaderos")
        peso_promedio = st.slider(
            "Peso promedio animal (kg):",
            300, 600, 450,
            key="peso_promedio_slider"
        )
        carga_animal = st.slider(
            "Carga animal (cabezas):",
            50, 1000, 100,
            key="carga_animal_slider"
        )
       
        st.subheader("División de Potrero")
        n_divisiones = st.slider(
            "Número de sub-lotes:",
            min_value=12, max_value=32, value=24,
            key="divisiones_slider"
        )
       
        st.subheader("Subir Lote")
        uploaded_zip = st.file_uploader(
            "Subir ZIP con shapefile del potrero",
            type=['zip'],
            key="file_uploader"
        )
       
        if st.button("Reiniciar Análisis", key="reset_button"):
            for key in ['analisis_completado', 'gdf_analizado', 'pdf_generado', 'pdf_buffer', 'gdf_cargado']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
       
        return uploaded_zip, tipo_pastura, peso_promedio, carga_animal, n_divisiones, fecha_imagen, fuente_satelital, base_map_option

def procesar_archivo(uploaded_zip):
    if uploaded_zip is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
               
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith('.shp')]
               
                if not shp_files:
                    st.error("No se encontró archivo .shp en el ZIP")
                    return None
               
                shp_path = os.path.join(tmpdir, shp_files[0])
                gdf = gpd.read_file(shp_path)
               
                if gdf.crs is None:
                    gdf.set_crs('EPSG:4326', inplace=True)
                elif gdf.crs != 'EPSG:4326':
                    gdf = gdf.to_crs('EPSG:4326')
               
                return gdf
           
            except Exception as e:
                st.error(f"Error al procesar el archivo: {str(e)}")
                return None
    return None

def mostrar_resultados(gdf_final, area_total, tipo_pastura, base_map_option):
    st.markdown("---")
    st.header("Resultados del Análisis Forrajero")
   
    col1, col2 = st.columns([3, 1])
   
    with col1:
        st.subheader("Mapa de Análisis")
        if FOLIUM_AVAILABLE:
            mapa_analisis = crear_mapa_analisis_interactivo(gdf_final, tipo_pastura, base_map_option)
            if mapa_analisis:
                st_folium(mapa_analisis, width=800, height=500)
        else:
            st.warning("Mapa interactivo no disponible")
   
    with col2:
        st.subheader("Resumen")
       
        biomasa_promedio = gdf_final['biomasa_disponible_kg_ms_ha'].mean()
        ev_total = gdf_final['ev_ha'].sum()  # CORREGIDO: ya es EV total
        dias_promedio = gdf_final['dias_permanencia'].mean()
       
        st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
        st.metric("EV Total Disponible", f"{ev_total:.0f} EV")
        st.metric("Días Permanencia Promedio", f"{dias_promedio:.1f} días")
       
        conteo_tipos = gdf_final['tipo_superficie'].value_counts()
        st.write("**Distribución de Superficies:**")
        for tipo, cantidad in conteo_tipos.items():
            porcentaje = (cantidad / len(gdf_final)) * 100
            st.write(f"- {tipo.replace('_', ' ').title()}: {cantidad} ({porcentaje:.1f}%)")
   
    st.subheader("Detalle por Sub-Lote")
    display_df = gdf_final[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']].copy()
    display_df['tipo_superficie'] = display_df['tipo_superficie'].str.replace('_', ' ').str.title()
    display_df['ndvi'] = display_df['ndvi'].round(3)
    display_df['biomasa_disponible_kg_ms_ha'] = display_df['biomasa_disponible_kg_ms_ha'].round(0)
    display_df['ev_ha'] = display_df['ev_ha'].round(1)
    display_df['dias_permanencia'] = display_df['dias_permanencia'].round(1)
   
    display_df.columns = ['Sub-Lote', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'EV/Ha', 'Días Permanencia']
   
    st.dataframe(display_df, use_container_width=True)

def main():
    (uploaded_zip, tipo_pastura, peso_promedio, carga_animal,
     n_divisiones, fecha_imagen, fuente_satelital, base_map_option) = mostrar_sidebar()
   
    if uploaded_zip is not None:
        gdf = procesar_archivo(uploaded_zip)
        if gdf is not None:
            st.session_state.gdf_cargado = gdf
            area_total = calcular_superficie(gdf)
            st.session_state.area_total = area_total
           
            st.success(f"Shapefile cargado correctamente - Área total: {area_total:.2f} ha")
           
            col1, col2 = st.columns([2, 1])
           
            with col1:
                st.subheader("Mapa del Potrero")
                if FOLIUM_AVAILABLE:
                    mapa = crear_mapa_interactivo(gdf, base_map_option)
                    if mapa:
                        st_folium(mapa, width=700, height=500)
                else:
                    st.warning("Mapa no disponible - Folium no está instalado")
           
            with col2:
                st.subheader("Información del Lote")
                st.metric("Área Total", f"{area_total:.2f} ha")
                st.metric("Número de Sub-Lotes", n_divisiones)
                st.metric("Tipo de Pastura", tipo_pastura)
               
                if st.button("Ejecutar Análisis Forrajero", type="primary", key="analizar_button"):
                    with st.spinner("Analizando potrero con datos satelitales..."):
                        try:
                            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
                            gdf_analizado = simular_datos_satelitales(gdf_dividido, tipo_pastura, fecha_imagen)
                            gdf_final = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
                           
                            st.session_state.gdf_analizado = gdf_final
                            st.session_state.analisis_completado = True
                            st.session_state.pdf_generado = False
                            st.session_state.pdf_buffer = None
                           
                            st.success("Análisis completado correctamente!")
                            # No usar st.rerun() → flujo natural
                           
                        except Exception as e:
                            st.error(f"Error en el análisis: {str(e)}")
   
    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        mostrar_resultados(st.session_state.gdf_analizado, st.session_state.area_total, tipo_pastura, base_map_option)

if __name__ == "__main__":
    main()
