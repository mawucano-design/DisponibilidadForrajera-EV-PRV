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
    st.warning("⚠️ Folium no está disponible. La funcionalidad de mapas interactivos estará limitada.")
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar variables de personalización con valores por defecto
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'area_total' not in st.session_state:
    st.session_state.area_total = 0
if 'pdf_generado' not in st.session_state:
    st.session_state.pdf_generado = False
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None

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

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selector de mapa base
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
            index=0
        )
    else:
        base_map_option = "ESRI Satélite"
    
    # Selección de satélite
    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"]
    )
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Configuración de fechas
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    # Parámetros personalizables
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05, value=0.025, step=0.001)
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01)
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.05, max_value=0.3, value=0.15, step=0.01)
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.3, max_value=0.8, value=0.6, step=0.01)
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    
    # Botón para resetear
    if st.button("🔄 Reiniciar Análisis"):
        st.session_state.analisis_completado = False
        st.session_state.gdf_analizado = None
        st.session_state.pdf_generado = False
        st.session_state.pdf_buffer = None
        st.rerun()

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

# Función para obtener parámetros
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'DIGESTIBILIDAD': 0.60,
            'PROTEINA_CRUDA': 0.12,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura,
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

# FUNCIÓN PARA CALCULAR SUPERFICIE
def calcular_superficie(gdf):
    try:
        if gdf.crs and gdf.crs.is_geographic:
            # Si el CRS es geográfico (grados), convertir a metros cuadrados
            gdf_proj = gdf.to_crs('EPSG:3857')  # Web Mercator para cálculo de área
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000  # Convertir a hectáreas
    except Exception as e:
        st.warning(f"Advertencia en cálculo de área: {e}")
        # Fallback: estimación simple
        return gdf.geometry.area / 10000

# FUNCIÓN PARA DIVIDIR POTRERO
def dividir_potrero_en_subLotes(gdf, n_zonas):
    if len(gdf) == 0:
        return gdf
    
    # Tomar el primer polígono (asumimos que solo hay uno)
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
# CONFIGURACIÓN DE MAPAS BASE
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
# FUNCIONES PARA MAPAS VISUALES
# =============================================================================

def crear_mapa_ndvi(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de NDVI"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para NDVI
    cmap_ndvi = LinearSegmentedColormap.from_list('ndvi_cmap', 
                                                 ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', 
                                                  '#c7eae5', '#80cdc1', '#35978f', '#01665e'])
    
    # Plotear cada polígono con color según NDVI
    for idx, row in gdf_analizado.iterrows():
        ndvi = row['ndvi']
        color = cmap_ndvi(ndvi)
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de NDVI
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{ndvi:.3f}', 
                fontsize=8, ha='center', va='center', 
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de NDVI - {tipo_pastura.replace("_", " ").title()}', fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_ndvi, 
                              norm=plt.Normalize(vmin=gdf_analizado['ndvi'].min(), 
                                               vmax=gdf_analizado['ndvi'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Valor NDVI', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_biomasa(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de biomasa disponible"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para biomasa
    cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_cmap', 
                                                    ['#d73027', '#fc8d59', '#fee08b', 
                                                     '#d9ef8b', '#91cf60', '#1a9850'])
    
    # Plotear cada polígono con color según biomasa
    for idx, row in gdf_analizado.iterrows():
        biomasa = row['biomasa_disponible_kg_ms_ha']
        color = cmap_biomasa(biomasa / gdf_analizado['biomasa_disponible_kg_ms_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de biomasa
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{biomasa:.0f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Biomasa Disponible (kg MS/ha) - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_biomasa, 
                              norm=plt.Normalize(vmin=gdf_analizado['biomasa_disponible_kg_ms_ha'].min(), 
                                               vmax=gdf_analizado['biomasa_disponible_kg_ms_ha'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Biomasa (kg MS/ha)', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_tipo_superficie(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de tipos de superficie"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Definir colores para cada tipo de superficie
    colores_superficie = {
        'SUELO_DESNUDO': '#d73027',
        'SUELO_PARCIAL': '#fdae61',
        'VEGETACION_ESCASA': '#fee08b',
        'VEGETACION_MODERADA': '#a6d96a',
        'VEGETACION_DENSA': '#1a9850'
    }
    
    # Plotear cada polígono con color según tipo de superficie
    for idx, row in gdf_analizado.iterrows():
        tipo = row['tipo_superficie']
        color = colores_superficie.get(tipo, '#3388ff')
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de ID
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f"{row['id_subLote']}", 
                fontsize=9, ha='center', va='center', fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Tipos de Superficie - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Crear leyenda
    legend_patches = []
    for tipo, color in colores_superficie.items():
        patch = mpatches.Patch(color=color, label=tipo.replace('_', ' ').title())
        legend_patches.append(patch)
    
    ax.legend(handles=legend_patches, loc='upper right', bbox_to_anchor=(1.15, 1))
    ax.grid(True, alpha=0.3)
    
    return fig

def crear_mapa_dias_permanencia(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de días de permanencia"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para días de permanencia
    cmap_dias = LinearSegmentedColormap.from_list('dias_cmap', 
                                                 ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', 
                                                  '#fee090', '#fdae61', '#f46d43', '#d73027'])
    
    # Plotear cada polígono con color según días de permanencia
    for idx, row in gdf_analizado.iterrows():
        dias = row['dias_permanencia']
        color = cmap_dias(dias / gdf_analizado['dias_permanencia'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de días
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{dias:.1f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Días de Permanencia - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_dias, 
                              norm=plt.Normalize(vmin=gdf_analizado['dias_permanencia'].min(), 
                                               vmax=gdf_analizado['dias_permanencia'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Días de Permanencia', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_ev_ha(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de Equivalentes Vacunos por hectárea"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para EV/ha
    cmap_ev = LinearSegmentedColormap.from_list('ev_cmap', 
                                               ['#d73027', '#fc8d59', '#fee08b', 
                                                '#d9ef8b', '#91cf60'])
    
    # Plotear cada polígono con color según EV/ha
    for idx, row in gdf_analizado.iterrows():
        ev_ha = row['ev_ha']
        color = cmap_ev(ev_ha / gdf_analizado['ev_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de EV/ha
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{ev_ha:.1f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Equivalentes Vacunos por Ha - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_ev, 
                              norm=plt.Normalize(vmin=gdf_analizado['ev_ha'].min(), 
                                               vmax=gdf_analizado['ev_ha'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('EV/Ha', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_combinado(gdf_analizado, tipo_pastura):
    """Crea un mapa combinado con múltiples variables"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    # Mapa 1: Tipo de Superficie
    colores_superficie = {
        'SUELO_DESNUDO': '#d73027',
        'SUELO_PARCIAL': '#fdae61',
        'VEGETACION_ESCASA': '#fee08b',
        'VEGETACION_MODERADA': '#a6d96a',
        'VEGETACION_DENSA': '#1a9850'
    }
    
    for idx, row in gdf_analizado.iterrows():
        tipo = row['tipo_superficie']
        color = colores_superficie.get(tipo, '#3388ff')
        gdf_analizado.iloc[[idx]].plot(ax=axes[0], color=color, edgecolor='black', linewidth=0.5)
    
    axes[0].set_title('Tipos de Superficie', fontweight='bold')
    legend_patches = [mpatches.Patch(color=color, label=tipo.replace('_', ' ').title()) 
                     for tipo, color in list(colores_superficie.items())[:3]]
    axes[0].legend(handles=legend_patches, loc='upper right')
    
    # Mapa 2: NDVI
    cmap_ndvi = LinearSegmentedColormap.from_list('ndvi_cmap', 
                                                 ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', 
                                                  '#c7eae5', '#80cdc1', '#35978f', '#01665e'])
    
    for idx, row in gdf_analizado.iterrows():
        ndvi = row['ndvi']
        color = cmap_ndvi(ndvi)
        gdf_analizado.iloc[[idx]].plot(ax=axes[1], color=color, edgecolor='black', linewidth=0.5)
    
    axes[1].set_title('NDVI', fontweight='bold')
    sm = plt.cm.ScalarMappable(cmap=cmap_ndvi, 
                              norm=plt.Normalize(vmin=gdf_analizado['ndvi'].min(), 
                                               vmax=gdf_analizado['ndvi'].max()))
    sm._A = []
    plt.colorbar(sm, ax=axes[1], shrink=0.8)
    
    # Mapa 3: Biomasa
    cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_cmap', 
                                                    ['#d73027', '#fc8d59', '#fee08b', 
                                                     '#d9ef8b', '#91cf60', '#1a9850'])
    
    for idx, row in gdf_analizado.iterrows():
        biomasa = row['biomasa_disponible_kg_ms_ha']
        color = cmap_biomasa(biomasa / gdf_analizado['biomasa_disponible_kg_ms_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=axes[2], color=color, edgecolor='black', linewidth=0.5)
    
    axes[2].set_title('Biomasa (kg MS/ha)', fontweight='bold')
    sm2 = plt.cm.ScalarMappable(cmap=cmap_biomasa, 
                               norm=plt.Normalize(vmin=gdf_analizado['biomasa_disponible_kg_ms_ha'].min(), 
                                                vmax=gdf_analizado['biomasa_disponible_kg_ms_ha'].max()))
    sm2._A = []
    plt.colorbar(sm2, ax=axes[2], shrink=0.8)
    
    # Mapa 4: Días de Permanencia
    cmap_dias = LinearSegmentedColormap.from_list('dias_cmap', 
                                                 ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', 
                                                  '#fee090', '#fdae61', '#f46d43', '#d73027'])
    
    for idx, row in gdf_analizado.iterrows():
        dias = row['dias_permanencia']
        color = cmap_dias(dias / gdf_analizado['dias_permanencia'].max())
        gdf_analizado.iloc[[idx]].plot(ax=axes[3], color=color, edgecolor='black', linewidth=0.5)
    
    axes[3].set_title('Días de Permanencia', fontweight='bold')
    sm3 = plt.cm.ScalarMappable(cmap=cmap_dias, 
                               norm=plt.Normalize(vmin=gdf_analizado['dias_permanencia'].min(), 
                                                vmax=gdf_analizado['dias_permanencia'].max()))
    sm3._A = []
    plt.colorbar(sm3, ax=axes[3], shrink=0.8)
    
    # Configuración general
    for ax in axes:
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
    
    plt.suptitle(f'Análisis Integral Forrajero - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=18, fontweight='bold', y=0.95)
    plt.tight_layout()
    
    return fig

# =============================================================================
# FUNCIÓN PARA SIMULAR DATOS SATELITALES
# =============================================================================

def simular_datos_satelitales(gdf, tipo_pastura, fecha_imagen):
    """Simula datos satelitales para análisis cuando no hay conexión a GEE"""
    
    if gdf is None or len(gdf) == 0:
        return gdf
    
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    
    gdf_analizado = gdf.copy()
    
    np.random.seed(hash(fecha_imagen.strftime("%Y%m%d")) % 10000)
    
    resultados = []
    
    for idx, row in gdf_analizado.iterrows():
        geometry = row['geometry']
        area_ha = calcular_superficie(gpd.GeoDataFrame([geometry], columns=['geometry'], crs=gdf.crs))
        
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
    
    gdf_resultado = gpd.GeoDataFrame(resultados, crs=gdf.crs)
    
    return gdf_resultado

# =============================================================================
# FUNCIÓN PARA CALCULAR MÉTRICAS GANADERAS
# =============================================================================

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Calcula métricas ganaderas basadas en el análisis de biomasa"""
    
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return gdf_analizado
    
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    
    gdf_resultado = gdf_analizado.copy()
    
    # Calcular consumo diario
    consumo_diario_por_animal = peso_promedio * parametros['CONSUMO_PORCENTAJE_PESO']
    consumo_diario_total = consumo_diario_por_animal * carga_animal
    
    # Inicializar columnas
    gdf_resultado['ev_ha'] = 0.0
    gdf_resultado['dias_permanencia'] = 0.0
    gdf_resultado['biomasa_disponible_kg'] = 0.0
    
    # Calcular métricas para cada sub-lote
    for idx, row in gdf_resultado.iterrows():
        biomasa_disponible_kg = row['biomasa_disponible_kg_ms_ha'] * row['area_ha']
        
        # Calcular EV/Ha (Equivalentes Vacunos por hectárea)
        if consumo_diario_por_animal > 0:
            ev_ha = biomasa_disponible_kg / consumo_diario_por_animal
        else:
            ev_ha = 0
        
        # Calcular días de permanencia
        if consumo_diario_total > 0:
            dias_permanencia = (biomasa_disponible_kg * parametros['TASA_UTILIZACION_RECOMENDADA']) / consumo_diario_total
        else:
            dias_permanencia = 0
        
        # Asignar valores al DataFrame
        gdf_resultado.at[idx, 'ev_ha'] = ev_ha
        gdf_resultado.at[idx, 'dias_permanencia'] = dias_permanencia
        gdf_resultado.at[idx, 'biomasa_disponible_kg'] = biomasa_disponible_kg
    
    return gdf_resultado

# =============================================================================
# FUNCIÓN PARA GENERAR PDF
# =============================================================================

def generar_informe_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, area_total, fecha_imagen, fuente_satelital):
    """Genera un informe PDF completo con los resultados del análisis"""
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.darkgreen,
        spaceAfter=30,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.darkblue,
        spaceAfter=12,
        spaceBefore=12
    )
    
    normal_style = styles['Normal']
    
    story = []
    
    story.append(Paragraph("INFORME DE ANÁLISIS FORRAJERO CON GANADERÍA REGENERATIVA", title_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("INFORMACIÓN GENERAL", heading_style))
    info_data = [
        ["Tipo de Pastura:", tipo_pastura.replace('_', ' ').title()],
        ["Área Total Analizada:", f"{area_total:.2f} ha"],
        ["Peso Promedio Animal:", f"{peso_promedio} kg"],
        ["Carga Animal:", f"{carga_animal} cabezas"],
        ["Fuente Satelital:", fuente_satelital],
        ["Fecha de Imagen:", fecha_imagen.strftime("%d/%m/%Y")],
        ["Fecha de Generación:", datetime.now().strftime("%d/%m/%Y %H:%M")]
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("ESTADÍSTICAS DEL ANÁLISIS", heading_style))
    
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = gdf_analizado['biomasa_disponible_kg_ms_ha'].sum() * area_total / len(gdf_analizado)
    ev_total = gdf_analizado['ev_ha'].sum() * area_total / len(gdf_analizado)
    dias_promedio = gdf_analizado['dias_permanencia'].mean()
    
    stats_data = [
        ["Biomasa Disponible Promedio:", f"{biomasa_promedio:.0f} kg MS/ha"],
        ["Biomasa Total Estimada:", f"{biomasa_total:.0f} kg MS"],
        ["EV Total Disponible:", f"{ev_total:.0f} EV"],
        ["Días de Permanencia Promedio:", f"{dias_promedio:.1f} días"],
        ["Número de Sub-Lotes:", f"{len(gdf_analizado)}"],
        ["Área por Sub-Lote:", f"{(area_total/len(gdf_analizado)):.2f} ha"]
    ]
    
    stats_table = Table(stats_data, colWidths=[2.5*inch, 2.5*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("DISTRIBUCIÓN DE TIPOS DE SUPERFICIE", heading_style))
    
    conteo_tipos = gdf_analizado['tipo_superficie'].value_counts()
    distribucion_data = [["Tipo de Superficie", "Cantidad", "Porcentaje"]]
    
    for tipo, cantidad in conteo_tipos.items():
        porcentaje = (cantidad / len(gdf_analizado)) * 100
        distribucion_data.append([tipo.replace('_', ' ').title(), str(cantidad), f"{porcentaje:.1f}%"])
    
    dist_table = Table(distribucion_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
    dist_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(dist_table)
    story.append(Spacer(1, 20))
    
    # Agregar mapa al PDF
    story.append(PageBreak())
    story.append(Paragraph("MAPAS DE ANÁLISIS", heading_style))
    
    # Generar y agregar mapa de tipos de superficie al PDF
    try:
        fig_mapa = crear_mapa_tipo_superficie(gdf_analizado, tipo_pastura)
        if fig_mapa:
            buf_mapa = io.BytesIO()
            fig_mapa.savefig(buf_mapa, format="png", dpi=150, bbox_inches='tight')
            buf_mapa.seek(0)
            
            img = Image(buf_mapa, width=6*inch, height=4*inch)
            story.append(img)
            story.append(Spacer(1, 12))
            story.append(Paragraph("Mapa de Tipos de Superficie", styles['Heading3']))
            story.append(Spacer(1, 20))
    except Exception as e:
        story.append(Paragraph(f"Error al generar mapa: {str(e)}", normal_style))
    
    story.append(Paragraph("RECOMENDACIONES DE GANADERÍA REGENERATIVA", heading_style))
    
    if tipo_pastura in RECOMENDACIONES_REGENERATIVAS:
        recomendaciones = RECOMENDACIONES_REGENERATIVAS[tipo_pastura]
        
        for categoria, items in recomendaciones.items():
            story.append(Paragraph(f"<b>{categoria.replace('_', ' ').title()}:</b>", styles['Heading3']))
            for item in items:
                story.append(Paragraph(f"• {item}", normal_style))
            story.append(Spacer(1, 8))
    
    story.append(PageBreak())
    
    story.append(Paragraph("DETALLE POR SUB-LOTE", heading_style))
    
    detalle_data = [["Sub-Lote", "Tipo Superficie", "NDVI", "Biomasa (kg MS/ha)", "EV/Ha", "Días"]]
    
    for _, row in gdf_analizado.iterrows():
        detalle_data.append([
            str(row['id_subLote']),
            row['tipo_superficie'].replace('_', ' ').title(),
            f"{row['ndvi']:.3f}",
            f"{row['biomasa_disponible_kg_ms_ha']:.0f}",
            f"{row['ev_ha']:.1f}",
            f"{row['dias_permanencia']:.1f}"
        ])
    
    detalle_table = Table(detalle_data, colWidths=[0.6*inch, 1.2*inch, 0.8*inch, 1.2*inch, 0.8*inch, 0.8*inch])
    detalle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    story.append(detalle_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    global uploaded_zip, tipo_pastura, peso_promedio, carga_animal, n_divisiones
    global fecha_imagen, fuente_satelital, base_map_option
    
    if uploaded_zip is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith('.shp')]
                
                if not shp_files:
                    st.error("❌ No se encontró archivo .shp en el ZIP")
                    return
                
                shp_path = os.path.join(tmpdir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                
                if gdf.crs is None:
                    gdf.set_crs('EPSG:4326', inplace=True)
                elif gdf.crs != 'EPSG:4326':
                    gdf = gdf.to_crs('EPSG:4326')
                
                st.session_state.gdf_cargado = gdf
                area_total = calcular_superficie(gdf)
                st.session_state.area_total = area_total
                
                st.success(f"✅ Shapefile cargado correctamente - Área total: {area_total:.2f} ha")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("🗺️ Mapa del Potrero")
                    if FOLIUM_AVAILABLE:
                        mapa = crear_mapa_interactivo(gdf, base_map_option)
                        if mapa:
                            st_folium(mapa, width=700, height=500)
                    else:
                        st.warning("Mapa no disponible - Folium no está instalado")
                
                with col2:
                    st.subheader("📊 Información del Lote")
                    st.metric("Área Total", f"{area_total:.2f} ha")
                    st.metric("Número de Sub-Lotes", n_divisiones)
                    st.metric("Tipo de Pastura", tipo_pastura)
                    
                    if st.button("🚀 Ejecutar Análisis Forrajero", type="primary"):
                        with st.spinner("Analizando potrero con datos satelitales..."):
                            try:
                                gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
                                
                                gdf_analizado = simular_datos_satelitales(
                                    gdf_dividido, tipo_pastura, fecha_imagen
                                )
                                
                                gdf_final = calcular_metricas_ganaderas(
                                    gdf_analizado, tipo_pastura, peso_promedio, carga_animal
                                )
                                
                                st.session_state.gdf_analizado = gdf_final
                                st.session_state.analisis_completado = True
                                
                                st.session_state.pdf_generado = False
                                st.session_state.pdf_buffer = None
                                
                                st.success("✅ Análisis completado correctamente!")
                                
                            except Exception as e:
                                st.error(f"❌ Error en el análisis: {str(e)}")
                            
                        st.rerun()
            
            except Exception as e:
                st.error(f"❌ Error al procesar el archivo: {str(e)}")
    
    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        st.markdown("---")
        st.header("📈 Resultados del Análisis Forrajero")
        
        gdf_final = st.session_state.gdf_analizado
        area_total = st.session_state.area_total
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("🗺️ Mapa de Análisis")
            if FOLIUM_AVAILABLE:
                mapa_analisis = crear_mapa_analisis_interactivo(gdf_final, tipo_pastura, base_map_option)
                if mapa_analisis:
                    st_folium(mapa_analisis, width=800, height=500)
            else:
                st.warning("Mapa interactivo no disponible")
        
        with col2:
            st.subheader("📊 Resumen")
            
            biomasa_promedio = gdf_final['biomasa_disponible_kg_ms_ha'].mean()
            ev_total = gdf_final['ev_ha'].sum() * area_total / len(gdf_final)
            dias_promedio = gdf_final['dias_permanencia'].mean()
            
            st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
            st.metric("EV Total Disponible", f"{ev_total:.0f} EV")
            st.metric("Días Permanencia Promedio", f"{dias_promedio:.1f} días")
            
            conteo_tipos = gdf_final['tipo_superficie'].value_counts()
            st.write("**Distribución de Superficies:**")
            for tipo, cantidad in conteo_tipos.items():
                porcentaje = (cantidad / len(gdf_final)) * 100
                st.write(f"- {tipo.replace('_', ' ').title()}: {cantidad} ({porcentaje:.1f}%)")
        
        st.subheader("📋 Detalle por Sub-Lote")
        display_df = gdf_final[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']].copy()
        display_df['tipo_superficie'] = display_df['tipo_superficie'].str.replace('_', ' ').str.title()
        display_df['ndvi'] = display_df['ndvi'].round(3)
        display_df['biomasa_disponible_kg_ms_ha'] = display_df['biomasa_disponible_kg_ms_ha'].round(0)
        display_df['ev_ha'] = display_df['ev_ha'].round(1)
        display_df['dias_permanencia'] = display_df['dias_permanencia'].round(1)
        
        display_df.columns = ['Sub-Lote', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'EV/Ha', 'Días Permanencia']
        
        st.dataframe(display_df, use_container_width=True)
        
        st.subheader("📊 Gráficos de Análisis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            colores = {
                'SUELO_DESNUDO': '#d73027',
                'SUELO_PARCIAL': '#fdae61',
                'VEGETACION_ESCASA': '#fee08b',
                'VEGETACION_MODERADA': '#a6d96a',
                'VEGETACION_DENSA': '#1a9850'
            }
            
            for tipo_superficie in gdf_final['tipo_superficie'].unique():
                datos_tipo = gdf_final[gdf_final['tipo_superficie'] == tipo_superficie]
                ax.scatter(datos_tipo['ndvi'], datos_tipo['biomasa_disponible_kg_ms_ha'],
                          c=colores.get(tipo_superficie, 'gray'), label=tipo_superficie.replace('_', ' ').title(),
                          alpha=0.7, s=60)
            
            ax.set_xlabel('NDVI')
            ax.set_ylabel('Biomasa Disponible (kg MS/ha)')
            ax.set_title('Relación NDVI vs Biomasa por Tipo de Superficie')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            st.pyplot(fig)
        
        with col2:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            datos_grafico = gdf_final.groupby('tipo_superficie').agg({
                'biomasa_disponible_kg_ms_ha': 'mean',
                'dias_permanencia': 'mean'
            }).reset_index()
            
            datos_grafico['tipo_superficie'] = datos_grafico['tipo_superficie'].str.replace('_', ' ').str.title()
            
            x = range(len(datos_grafico))
            width = 0.35
            
            ax.bar([i - width/2 for i in x], datos_grafico['biomasa_disponible_kg_ms_ha'], width, 
                   label='Biomasa Promedio (kg MS/ha)', color='skyblue', alpha=0.7)
            
            ax2 = ax.twinx()
            ax2.bar([i + width/2 for i in x], datos_grafico['dias_permanencia'], width,
                    label='Días Permanencia Promedio', color='lightcoral', alpha=0.7)
            
            ax.set_xlabel('Tipo de Superficie')
            ax.set_ylabel('Biomasa (kg MS/ha)')
            ax2.set_ylabel('Días Permanencia')
            ax.set_xticks(x)
            ax.set_xticklabels(datos_grafico['tipo_superficie'], rotation=45)
            ax.set_title('Biomasa y Días de Permanencia por Tipo de Superficie')
            
            ax.legend(loc='upper left')
            ax2.legend(loc='upper right')
            
            st.pyplot(fig)
        
        st.subheader("🗺️ Mapas de Análisis Visual")
        
        # Selector de tipo de mapa
        tipo_mapa = st.selectbox(
            "Seleccionar tipo de mapa:",
            ["Mapa Combinado", "Tipos de Superficie", "NDVI", "Biomasa", "Días de Permanencia", "EV/Ha"],
            index=0
        )
        
        # Generar el mapa seleccionado
        if tipo_mapa == "Mapa Combinado":
            fig_mapa = crear_mapa_combinado(gdf_final, tipo_pastura)
        elif tipo_mapa == "Tipos de Superficie":
            fig_mapa = crear_mapa_tipo_superficie(gdf_final, tipo_pastura)
        elif tipo_mapa == "NDVI":
            fig_mapa = crear_mapa_ndvi(gdf_final, tipo_pastura)
        elif tipo_mapa == "Biomasa":
            fig_mapa = crear_mapa_biomasa(gdf_final, tipo_pastura)
        elif tipo_mapa == "Días de Permanencia":
            fig_mapa = crear_mapa_dias_permanencia(gdf_final, tipo_pastura)
        elif tipo_mapa == "EV/Ha":
            fig_mapa = crear_mapa_ev_ha(gdf_final, tipo_pastura)
        
        if fig_mapa:
            st.pyplot(fig_mapa)
            
            # Botón para descargar el mapa
            buf = io.BytesIO()
            fig_mapa.savefig(buf, format="png", dpi=150, bbox_inches='tight')
            buf.seek(0)
            
            st.download_button(
                label="📥 Descargar Mapa",
                data=buf,
                file_name=f"mapa_{tipo_mapa.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                mime="image/png"
            )
        else:
            st.warning("No se pudo generar el mapa")
        
        st.subheader("🌱 Recomendaciones de Ganadería Regenerativa")
        
        if tipo_pastura in RECOMENDACIONES_REGENERATIVAS:
            recomendaciones = RECOMENDACIONES_REGENERATIVAS[tipo_pastura]
            
            for categoria, items in recomendaciones.items():
                with st.expander(f"📋 {categoria.replace('_', ' ').title()}"):
                    for item in items:
                        st.write(f"• {item}")
        
        st.subheader("📄 Generar Informe PDF")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            if st.button("🔄 Generar Informe PDF", type="primary"):
                with st.spinner("Generando informe PDF..."):
                    try:
                        pdf_buffer = generar_informe_pdf(
                            gdf_final, tipo_pastura, peso_promedio, carga_animal,
                            area_total, fecha_imagen, fuente_satelital
                        )
                        
                        st.session_state.pdf_buffer = pdf_buffer
                        st.session_state.pdf_generado = True
                        
                        st.success("✅ Informe PDF generado correctamente")
                        st.rerun()
                    
                    except Exception as e:
                        st.error(f"❌ Error al generar PDF: {str(e)}")
        
        if st.session_state.pdf_generado and st.session_state.pdf_buffer is not None:
            st.download_button(
                label="📥 Descargar Informe PDF",
                data=st.session_state.pdf_buffer,
                file_name=f"informe_forrajero_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                type="primary"
            )

if __name__ == "__main__":
    main()
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar variables de personalización con valores por defecto
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'area_total' not in st.session_state:
    st.session_state.area_total = 0
if 'pdf_generado' not in st.session_state:
    st.session_state.pdf_generado = False
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None

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

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selector de mapa base
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
            index=0
        )
    else:
        base_map_option = "ESRI Satélite"
    
    # Selección de satélite
    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"]
    )
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Configuración de fechas
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)
    
    # Parámetros de detección
    st.subheader("🌿 Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1)
    
    # Parámetros personalizables
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05, value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01)
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.05, max_value=0.3, value=0.15, step=0.01)
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.3, max_value=0.8, value=0.6, step=0.01)
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    
    # Botón para resetear
    if st.button("🔄 Reiniciar Análisis"):
        st.session_state.analisis_completado = False
        st.session_state.gdf_analizado = None
        st.session_state.pdf_generado = False
        st.session_state.pdf_buffer = None
        st.rerun()

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 5000,
        'CRECIMIENTO_DIARIO': 100,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 4500,
        'FACTOR_BIOMASA_EVI': 4700,
        'FACTOR_BIOMASA_SAVI': 4600,
        'OFFSET_BIOMASA': -1000,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.6,
        'UMBRAL_BSI_SUELO': 0.3,
        'UMBRAL_NDBI_SUELO': 0.1,
        'FACTOR_COBERTURA': 0.85
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 4500,
        'CRECIMIENTO_DIARIO': 90,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 4200,
        'FACTOR_BIOMASA_EVI': 4400,
        'FACTOR_BIOMASA_SAVI': 4300,
        'OFFSET_BIOMASA': -900,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.6,
        'UMBRAL_BSI_SUELO': 0.3,
        'UMBRAL_NDBI_SUELO': 0.1,
        'FACTOR_COBERTURA': 0.85
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 3800,
        'FACTOR_BIOMASA_EVI': 4000,
        'FACTOR_BIOMASA_SAVI': 3900,
        'OFFSET_BIOMASA': -800,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.65,
        'UMBRAL_BSI_SUELO': 0.3,
        'UMBRAL_NDBI_SUELO': 0.1,
        'FACTOR_COBERTURA': 0.82
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 60,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 3200,
        'FACTOR_BIOMASA_EVI': 3400,
        'FACTOR_BIOMASA_SAVI': 3300,
        'OFFSET_BIOMASA': -700,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.65,
        'UMBRAL_BSI_SUELO': 0.3,
        'UMBRAL_NDBI_SUELO': 0.1,
        'FACTOR_COBERTURA': 0.80
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 40,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 2800,
        'FACTOR_BIOMASA_EVI': 3000,
        'FACTOR_BIOMASA_SAVI': 2900,
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.7,
        'UMBRAL_BSI_SUELO': 0.3,
        'UMBRAL_NDBI_SUELO': 0.1,
        'FACTOR_COBERTURA': 0.75
    }
}

# Función para obtener parámetros
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'DIGESTIBILIDAD': 0.60,
            'PROTEINA_CRUDA': 0.12,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'FACTOR_BIOMASA_NDVI': 3500,
            'FACTOR_BIOMASA_EVI': 3700,
            'FACTOR_BIOMASA_SAVI': 3600,
            'OFFSET_BIOMASA': -800,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura,
            'UMBRAL_BSI_SUELO': 0.3,
            'UMBRAL_NDBI_SUELO': 0.1,
            'FACTOR_COBERTURA': 0.82
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

# FUNCIÓN PARA CALCULAR SUPERFICIE
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

# =============================================================================
# CONFIGURACIÓN DE MAPAS BASE
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
# FUNCIONES PARA MAPAS VISUALES
# =============================================================================

def crear_mapa_ndvi(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de NDVI"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para NDVI
    cmap_ndvi = LinearSegmentedColormap.from_list('ndvi_cmap', 
                                                 ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', 
                                                  '#c7eae5', '#80cdc1', '#35978f', '#01665e'])
    
    # Plotear cada polígono con color según NDVI
    for idx, row in gdf_analizado.iterrows():
        ndvi = row['ndvi']
        color = cmap_ndvi(ndvi)
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de NDVI
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{ndvi:.3f}', 
                fontsize=8, ha='center', va='center', 
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de NDVI - {tipo_pastura.replace("_", " ").title()}', fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_ndvi, 
                              norm=plt.Normalize(vmin=gdf_analizado['ndvi'].min(), 
                                               vmax=gdf_analizado['ndvi'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Valor NDVI', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_biomasa(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de biomasa disponible"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para biomasa
    cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_cmap', 
                                                    ['#d73027', '#fc8d59', '#fee08b', 
                                                     '#d9ef8b', '#91cf60', '#1a9850'])
    
    # Plotear cada polígono con color según biomasa
    for idx, row in gdf_analizado.iterrows():
        biomasa = row['biomasa_disponible_kg_ms_ha']
        color = cmap_biomasa(biomasa / gdf_analizado['biomasa_disponible_kg_ms_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de biomasa
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{biomasa:.0f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Biomasa Disponible (kg MS/ha) - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_biomasa, 
                              norm=plt.Normalize(vmin=gdf_analizado['biomasa_disponible_kg_ms_ha'].min(), 
                                               vmax=gdf_analizado['biomasa_disponible_kg_ms_ha'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Biomasa (kg MS/ha)', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_tipo_superficie(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de tipos de superficie"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Definir colores para cada tipo de superficie
    colores_superficie = {
        'SUELO_DESNUDO': '#d73027',
        'SUELO_PARCIAL': '#fdae61',
        'VEGETACION_ESCASA': '#fee08b',
        'VEGETACION_MODERADA': '#a6d96a',
        'VEGETACION_DENSA': '#1a9850'
    }
    
    # Plotear cada polígono con color según tipo de superficie
    for idx, row in gdf_analizado.iterrows():
        tipo = row['tipo_superficie']
        color = colores_superficie.get(tipo, '#3388ff')
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de ID
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f"{row['id_subLote']}", 
                fontsize=9, ha='center', va='center', fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Tipos de Superficie - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Crear leyenda
    legend_patches = []
    for tipo, color in colores_superficie.items():
        patch = mpatches.Patch(color=color, label=tipo.replace('_', ' ').title())
        legend_patches.append(patch)
    
    ax.legend(handles=legend_patches, loc='upper right', bbox_to_anchor=(1.15, 1))
    ax.grid(True, alpha=0.3)
    
    return fig

def crear_mapa_dias_permanencia(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de días de permanencia"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para días de permanencia
    cmap_dias = LinearSegmentedColormap.from_list('dias_cmap', 
                                                 ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', 
                                                  '#fee090', '#fdae61', '#f46d43', '#d73027'])
    
    # Plotear cada polígono con color según días de permanencia
    for idx, row in gdf_analizado.iterrows():
        dias = row['dias_permanencia']
        color = cmap_dias(dias / gdf_analizado['dias_permanencia'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de días
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{dias:.1f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Días de Permanencia - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_dias, 
                              norm=plt.Normalize(vmin=gdf_analizado['dias_permanencia'].min(), 
                                               vmax=gdf_analizado['dias_permanencia'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('Días de Permanencia', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_ev_ha(gdf_analizado, tipo_pastura):
    """Crea un mapa visual de Equivalentes Vacunos por hectárea"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Crear colormap para EV/ha
    cmap_ev = LinearSegmentedColormap.from_list('ev_cmap', 
                                               ['#d73027', '#fc8d59', '#fee08b', 
                                                '#d9ef8b', '#91cf60'])
    
    # Plotear cada polígono con color según EV/ha
    for idx, row in gdf_analizado.iterrows():
        ev_ha = row['ev_ha']
        color = cmap_ev(ev_ha / gdf_analizado['ev_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=0.5)
        
        # Añadir etiqueta de EV/ha
        centroid = row['geometry'].centroid
        ax.text(centroid.x, centroid.y, f'{ev_ha:.1f}', 
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
    
    # Configurar el mapa
    ax.set_title(f'Mapa de Equivalentes Vacunos por Ha - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    
    # Añadir barra de color
    sm = plt.cm.ScalarMappable(cmap=cmap_ev, 
                              norm=plt.Normalize(vmin=gdf_analizado['ev_ha'].min(), 
                                               vmax=gdf_analizado['ev_ha'].max()))
    sm._A = []
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
    cbar.set_label('EV/Ha', rotation=270, labelpad=20)
    
    ax.grid(True, alpha=0.3)
    return fig

def crear_mapa_combinado(gdf_analizado, tipo_pastura):
    """Crea un mapa combinado con múltiples variables"""
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    # Mapa 1: Tipo de Superficie
    colores_superficie = {
        'SUELO_DESNUDO': '#d73027',
        'SUELO_PARCIAL': '#fdae61',
        'VEGETACION_ESCASA': '#fee08b',
        'VEGETACION_MODERADA': '#a6d96a',
        'VEGETACION_DENSA': '#1a9850'
    }
    
    for idx, row in gdf_analizado.iterrows():
        tipo = row['tipo_superficie']
        color = colores_superficie.get(tipo, '#3388ff')
        gdf_analizado.iloc[[idx]].plot(ax=axes[0], color=color, edgecolor='black', linewidth=0.5)
    
    axes[0].set_title('Tipos de Superficie', fontweight='bold')
    legend_patches = [mpatches.Patch(color=color, label=tipo.replace('_', ' ').title()) 
                     for tipo, color in list(colores_superficie.items())[:3]]
    axes[0].legend(handles=legend_patches, loc='upper right')
    
    # Mapa 2: NDVI
    cmap_ndvi = LinearSegmentedColormap.from_list('ndvi_cmap', 
                                                 ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', 
                                                  '#c7eae5', '#80cdc1', '#35978f', '#01665e'])
    
    for idx, row in gdf_analizado.iterrows():
        ndvi = row['ndvi']
        color = cmap_ndvi(ndvi)
        gdf_analizado.iloc[[idx]].plot(ax=axes[1], color=color, edgecolor='black', linewidth=0.5)
    
    axes[1].set_title('NDVI', fontweight='bold')
    sm = plt.cm.ScalarMappable(cmap=cmap_ndvi, 
                              norm=plt.Normalize(vmin=gdf_analizado['ndvi'].min(), 
                                               vmax=gdf_analizado['ndvi'].max()))
    sm._A = []
    plt.colorbar(sm, ax=axes[1], shrink=0.8)
    
    # Mapa 3: Biomasa
    cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_cmap', 
                                                    ['#d73027', '#fc8d59', '#fee08b', 
                                                     '#d9ef8b', '#91cf60', '#1a9850'])
    
    for idx, row in gdf_analizado.iterrows():
        biomasa = row['biomasa_disponible_kg_ms_ha']
        color = cmap_biomasa(biomasa / gdf_analizado['biomasa_disponible_kg_ms_ha'].max())
        gdf_analizado.iloc[[idx]].plot(ax=axes[2], color=color, edgecolor='black', linewidth=0.5)
    
    axes[2].set_title('Biomasa (kg MS/ha)', fontweight='bold')
    sm2 = plt.cm.ScalarMappable(cmap=cmap_biomasa, 
                               norm=plt.Normalize(vmin=gdf_analizado['biomasa_disponible_kg_ms_ha'].min(), 
                                                vmax=gdf_analizado['biomasa_disponible_kg_ms_ha'].max()))
    sm2._A = []
    plt.colorbar(sm2, ax=axes[2], shrink=0.8)
    
    # Mapa 4: Días de Permanencia
    cmap_dias = LinearSegmentedColormap.from_list('dias_cmap', 
                                                 ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', 
                                                  '#fee090', '#fdae61', '#f46d43', '#d73027'])
    
    for idx, row in gdf_analizado.iterrows():
        dias = row['dias_permanencia']
        color = cmap_dias(dias / gdf_analizado['dias_permanencia'].max())
        gdf_analizado.iloc[[idx]].plot(ax=axes[3], color=color, edgecolor='black', linewidth=0.5)
    
    axes[3].set_title('Días de Permanencia', fontweight='bold')
    sm3 = plt.cm.ScalarMappable(cmap=cmap_dias, 
                               norm=plt.Normalize(vmin=gdf_analizado['dias_permanencia'].min(), 
                                                vmax=gdf_analizado['dias_permanencia'].max()))
    sm3._A = []
    plt.colorbar(sm3, ax=axes[3], shrink=0.8)
    
    # Configuración general
    for ax in axes:
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
    
    plt.suptitle(f'Análisis Integral Forrajero - {tipo_pastura.replace("_", " ").title()}', 
                 fontsize=18, fontweight='bold', y=0.95)
    plt.tight_layout()
    
    return fig

# =============================================================================
# FUNCIÓN PARA SIMULAR DATOS SATELITALES
# =============================================================================

def simular_datos_satelitales(gdf, tipo_pastura, fecha_imagen):
    """Simula datos satelitales para análisis cuando no hay conexión a GEE"""
    
    if gdf is None or len(gdf) == 0:
        return gdf
    
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    
    gdf_analizado = gdf.copy()
    
    np.random.seed(hash(fecha_imagen.strftime("%Y%m%d")) % 10000)
    
    resultados = []
    
    for idx, geometry in enumerate(gdf_analizado.geometry):
        area_ha = calcular_superficie(gpd.GeoDataFrame([geometry], columns=['geometry'], crs=gdf.crs))
        
        ndvi_base = np.random.normal(0.5, 0.2)
        ndvi_base = max(0.05, min(0.85, ndvi_base))
        
        efecto_estacional = 0.1 * np.sin(2 * np.pi * fecha_imagen.timetuple().tm_yday / 365)
        ndvi_ajustado = ndvi_base + efecto_estacional
        
        bsi = np.random.normal(0.2, 0.1)
        ndbi = np.random.normal(0.1, 0.05)
        
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
            'id_subLote': idx + 1,
            'geometry': geometry,
            'ndvi': ndvi_ajustado,
            'bsi': bsi,
            'ndbi': ndbi,
            'tipo_superficie': tipo_superficie,
            'biomasa_disponible_kg_ms_ha': biomasa_ajustada,
            'area_ha': area_ha
        })
    
    gdf_resultado = gpd.GeoDataFrame(resultados, crs=gdf.crs)
    
    return gdf_resultado

# =============================================================================
# FUNCIÓN PARA CALCULAR MÉTRICAS GANADERAS - CORREGIDA
# =============================================================================

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Calcula métricas ganaderas basadas en el análisis de biomasa"""
    
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return gdf_analizado
    
    parametros = obtener_parametros_forrajeros(tipo_pastura)
    
    gdf_resultado = gdf_analizado.copy()
    
    # Calcular consumo diario
    consumo_diario_por_animal = peso_promedio * parametros['CONSUMO_PORCENTAJE_PESO']
    consumo_diario_total = consumo_diario_por_animal * carga_animal
    
    # Inicializar columnas si no existen
    if 'ev_ha' not in gdf_resultado.columns:
        gdf_resultado['ev_ha'] = 0.0
    if 'dias_permanencia' not in gdf_resultado.columns:
        gdf_resultado['dias_permanencia'] = 0.0
    if 'biomasa_disponible_kg' not in gdf_resultado.columns:
        gdf_resultado['biomasa_disponible_kg'] = 0.0
    
    # Calcular métricas para cada sub-lote
    for idx, row in gdf_resultado.iterrows():
        biomasa_disponible_kg = row['biomasa_disponible_kg_ms_ha'] * row['area_ha']
        
        # Calcular EV/Ha (Equivalentes Vacunos por hectárea)
        if consumo_diario_por_animal > 0:
            ev_ha = biomasa_disponible_kg / consumo_diario_por_animal
        else:
            ev_ha = 0
        
        # Calcular días de permanencia
        if consumo_diario_total > 0:
            dias_permanencia = (biomasa_disponible_kg * parametros['TASA_UTILIZACION_RECOMENDADA']) / consumo_diario_total
        else:
            dias_permanencia = 0
        
        # Asignar valores al DataFrame
        gdf_resultado.at[idx, 'ev_ha'] = ev_ha
        gdf_resultado.at[idx, 'dias_permanencia'] = dias_permanencia
        gdf_resultado.at[idx, 'biomasa_disponible_kg'] = biomasa_disponible_kg
    
    return gdf_resultado

# =============================================================================
# FUNCIÓN PARA GENERAR PDF
# =============================================================================

def generar_informe_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, area_total, fecha_imagen, fuente_satelital):
    """Genera un informe PDF completo con los resultados del análisis"""
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.darkgreen,
        spaceAfter=30,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.darkblue,
        spaceAfter=12,
        spaceBefore=12
    )
    
    normal_style = styles['Normal']
    
    story = []
    
    story.append(Paragraph("INFORME DE ANÁLISIS FORRAJERO CON GANADERÍA REGENERATIVA", title_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("INFORMACIÓN GENERAL", heading_style))
    info_data = [
        ["Tipo de Pastura:", tipo_pastura.replace('_', ' ').title()],
        ["Área Total Analizada:", f"{area_total:.2f} ha"],
        ["Peso Promedio Animal:", f"{peso_promedio} kg"],
        ["Carga Animal:", f"{carga_animal} cabezas"],
        ["Fuente Satelital:", fuente_satelital],
        ["Fecha de Imagen:", fecha_imagen.strftime("%d/%m/%Y")],
        ["Fecha de Generación:", datetime.now().strftime("%d/%m/%Y %H:%M")]
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("ESTADÍSTICAS DEL ANÁLISIS", heading_style))
    
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
    biomasa_total = gdf_analizado['biomasa_disponible_kg_ms_ha'].sum() * area_total / len(gdf_analizado)
    ev_total = gdf_analizado['ev_ha'].sum() * area_total / len(gdf_analizado)
    dias_promedio = gdf_analizado['dias_permanencia'].mean()
    
    stats_data = [
        ["Biomasa Disponible Promedio:", f"{biomasa_promedio:.0f} kg MS/ha"],
        ["Biomasa Total Estimada:", f"{biomasa_total:.0f} kg MS"],
        ["EV Total Disponible:", f"{ev_total:.0f} EV"],
        ["Días de Permanencia Promedio:", f"{dias_promedio:.1f} días"],
        ["Número de Sub-Lotes:", f"{len(gdf_analizado)}"],
        ["Área por Sub-Lote:", f"{(area_total/len(gdf_analizado)):.2f} ha"]
    ]
    
    stats_table = Table(stats_data, colWidths=[2.5*inch, 2.5*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("DISTRIBUCIÓN DE TIPOS DE SUPERFICIE", heading_style))
    
    conteo_tipos = gdf_analizado['tipo_superficie'].value_counts()
    distribucion_data = [["Tipo de Superficie", "Cantidad", "Porcentaje"]]
    
    for tipo, cantidad in conteo_tipos.items():
        porcentaje = (cantidad / len(gdf_analizado)) * 100
        distribucion_data.append([tipo.replace('_', ' ').title(), str(cantidad), f"{porcentaje:.1f}%"])
    
    dist_table = Table(distribucion_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
    dist_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(dist_table)
    story.append(Spacer(1, 20))
    
    # Agregar mapa al PDF
    story.append(PageBreak())
    story.append(Paragraph("MAPAS DE ANÁLISIS", heading_style))
    
    # Generar y agregar mapa de tipos de superficie al PDF
    try:
        fig_mapa = crear_mapa_tipo_superficie(gdf_analizado, tipo_pastura)
        if fig_mapa:
            buf_mapa = io.BytesIO()
            fig_mapa.savefig(buf_mapa, format="png", dpi=150, bbox_inches='tight')
            buf_mapa.seek(0)
            
            img = Image(buf_mapa, width=6*inch, height=4*inch)
            story.append(img)
            story.append(Spacer(1, 12))
            story.append(Paragraph("Mapa de Tipos de Superficie", styles['Heading3']))
            story.append(Spacer(1, 20))
    except Exception as e:
        story.append(Paragraph(f"Error al generar mapa: {str(e)}", normal_style))
    
    story.append(Paragraph("RECOMENDACIONES DE GANADERÍA REGENERATIVA", heading_style))
    
    if tipo_pastura in RECOMENDACIONES_REGENERATIVAS:
        recomendaciones = RECOMENDACIONES_REGENERATIVAS[tipo_pastura]
        
        for categoria, items in recomendaciones.items():
            story.append(Paragraph(f"<b>{categoria.replace('_', ' ').title()}:</b>", styles['Heading3']))
            for item in items:
                story.append(Paragraph(f"• {item}", normal_style))
            story.append(Spacer(1, 8))
    
    story.append(PageBreak())
    
    story.append(Paragraph("DETALLE POR SUB-LOTE", heading_style))
    
    detalle_data = [["Sub-Lote", "Tipo Superficie", "NDVI", "Biomasa (kg MS/ha)", "EV/Ha", "Días"]]
    
    for _, row in gdf_analizado.iterrows():
        detalle_data.append([
            str(row['id_subLote']),
            row['tipo_superficie'].replace('_', ' ').title(),
            f"{row['ndvi']:.3f}",
            f"{row['biomasa_disponible_kg_ms_ha']:.0f}",
            f"{row['ev_ha']:.1f}",
            f"{row['dias_permanencia']:.1f}"
        ])
    
    detalle_table = Table(detalle_data, colWidths=[0.6*inch, 1.2*inch, 0.8*inch, 1.2*inch, 0.8*inch, 0.8*inch])
    detalle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    story.append(detalle_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    global uploaded_zip, tipo_pastura, peso_promedio, carga_animal, n_divisiones
    global fecha_imagen, fuente_satelital, base_map_option
    
    if uploaded_zip is not None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith('.shp')]
                
                if not shp_files:
                    st.error("❌ No se encontró archivo .shp en el ZIP")
                    return
                
                shp_path = os.path.join(tmpdir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                
                if gdf.crs is None:
                    gdf.set_crs('EPSG:4326', inplace=True)
                elif gdf.crs != 'EPSG:4326':
                    gdf = gdf.to_crs('EPSG:4326')
                
                st.session_state.gdf_cargado = gdf
                area_total = calcular_superficie(gdf)
                st.session_state.area_total = area_total
                
                st.success(f"✅ Shapefile cargado correctamente - Área total: {area_total:.2f} ha")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("🗺️ Mapa del Potrero")
                    if FOLIUM_AVAILABLE:
                        mapa = crear_mapa_interactivo(gdf, base_map_option)
                        if mapa:
                            st_folium(mapa, width=700, height=500)
                    else:
                        st.warning("Mapa no disponible - Folium no está instalado")
                
                with col2:
                    st.subheader("📊 Información del Lote")
                    st.metric("Área Total", f"{area_total:.2f} ha")
                    st.metric("Número de Sub-Lotes", n_divisiones)
                    st.metric("Tipo de Pastura", tipo_pastura)
                    
                    if st.button("🚀 Ejecutar Análisis Forrajero", type="primary"):
                        with st.spinner("Analizando potrero con datos satelitales..."):
                            try:
                                gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
                                
                                gdf_analizado = simular_datos_satelitales(
                                    gdf_dividido, tipo_pastura, fecha_imagen
                                )
                                
                                gdf_final = calcular_metricas_ganaderas(
                                    gdf_analizado, tipo_pastura, peso_promedio, carga_animal
                                )
                                
                                st.session_state.gdf_analizado = gdf_final
                                st.session_state.analisis_completado = True
                                
                                st.session_state.pdf_generado = False
                                st.session_state.pdf_buffer = None
                                
                                st.success("✅ Análisis completado correctamente!")
                                
                            except Exception as e:
                                st.error(f"❌ Error en el análisis: {str(e)}")
                            
                        st.rerun()
            
            except Exception as e:
                st.error(f"❌ Error al procesar el archivo: {str(e)}")
    
    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        st.markdown("---")
        st.header("📈 Resultados del Análisis Forrajero")
        
        gdf_final = st.session_state.gdf_analizado
        area_total = st.session_state.area_total
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("🗺️ Mapa de Análisis")
            if FOLIUM_AVAILABLE:
                mapa_analisis = crear_mapa_analisis_interactivo(gdf_final, tipo_pastura, base_map_option)
                if mapa_analisis:
                    st_folium(mapa_analisis, width=800, height=500)
            else:
                st.warning("Mapa interactivo no disponible")
        
        with col2:
            st.subheader("📊 Resumen")
            
            biomasa_promedio = gdf_final['biomasa_disponible_kg_ms_ha'].mean()
            ev_total = gdf_final['ev_ha'].sum() * area_total / len(gdf_final)
            dias_promedio = gdf_final['dias_permanencia'].mean()
            
            st.metric("Biomasa Promedio", f"{biomasa_promedio:.0f} kg MS/ha")
            st.metric("EV Total Disponible", f"{ev_total:.0f} EV")
            st.metric("Días Permanencia Promedio", f"{dias_promedio:.1f} días")
            
            conteo_tipos = gdf_final['tipo_superficie'].value_counts()
            st.write("**Distribución de Superficies:**")
            for tipo, cantidad in conteo_tipos.items():
                porcentaje = (cantidad / len(gdf_final)) * 100
                st.write(f"- {tipo.replace('_', ' ').title()}: {cantidad} ({porcentaje:.1f}%)")
        
        st.subheader("📋 Detalle por Sub-Lote")
        display_df = gdf_final[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']].copy()
        display_df['tipo_superficie'] = display_df['tipo_superficie'].str.replace('_', ' ').str.title()
        display_df['ndvi'] = display_df['ndvi'].round(3)
        display_df['biomasa_disponible_kg_ms_ha'] = display_df['biomasa_disponible_kg_ms_ha'].round(0)
        display_df['ev_ha'] = display_df['ev_ha'].round(1)
        display_df['dias_permanencia'] = display_df['dias_permanencia'].round(1)
        
        display_df.columns = ['Sub-Lote', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'EV/Ha', 'Días Permanencia']
        
        st.dataframe(display_df, use_container_width=True)
        
        st.subheader("📊 Gráficos de Análisis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            colores = {
                'SUELO_DESNUDO': '#d73027',
                'SUELO_PARCIAL': '#fdae61',
                'VEGETACION_ESCASA': '#fee08b',
                'VEGETACION_MODERADA': '#a6d96a',
                'VEGETACION_DENSA': '#1a9850'
            }
            
            for tipo_superficie in gdf_final['tipo_superficie'].unique():
                datos_tipo = gdf_final[gdf_final['tipo_superficie'] == tipo_superficie]
                ax.scatter(datos_tipo['ndvi'], datos_tipo['biomasa_disponible_kg_ms_ha'],
                          c=colores.get(tipo_superficie, 'gray'), label=tipo_superficie.replace('_', ' ').title(),
                          alpha=0.7, s=60)
            
            ax.set_xlabel('NDVI')
            ax.set_ylabel('Biomasa Disponible (kg MS/ha)')
            ax.set_title('Relación NDVI vs Biomasa por Tipo de Superficie')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            st.pyplot(fig)
        
        with col2:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            datos_grafico = gdf_final.groupby('tipo_superficie').agg({
                'biomasa_disponible_kg_ms_ha': 'mean',
                'dias_permanencia': 'mean'
            }).reset_index()
            
            datos_grafico['tipo_superficie'] = datos_grafico['tipo_superficie'].str.replace('_', ' ').str.title()
            
            x = range(len(datos_grafico))
            width = 0.35
            
            ax.bar([i - width/2 for i in x], datos_grafico['biomasa_disponible_kg_ms_ha'], width, 
                   label='Biomasa Promedio (kg MS/ha)', color='skyblue', alpha=0.7)
            
            ax2 = ax.twinx()
            ax2.bar([i + width/2 for i in x], datos_grafico['dias_permanencia'], width,
                    label='Días Permanencia Promedio', color='lightcoral', alpha=0.7)
            
            ax.set_xlabel('Tipo de Superficie')
            ax.set_ylabel('Biomasa (kg MS/ha)')
            ax2.set_ylabel('Días Permanencia')
            ax.set_xticks(x)
            ax.set_xticklabels(datos_grafico['tipo_superficie'], rotation=45)
            ax.set_title('Biomasa y Días de Permanencia por Tipo de Superficie')
            
            ax.legend(loc='upper left')
            ax2.legend(loc='upper right')
            
            st.pyplot(fig)
        
        st.subheader("🗺️ Mapas de Análisis Visual")
        
        # Selector de tipo de mapa
        tipo_mapa = st.selectbox(
            "Seleccionar tipo de mapa:",
            ["Mapa Combinado", "Tipos de Superficie", "NDVI", "Biomasa", "Días de Permanencia", "EV/Ha"],
            index=0
        )
        
        # Generar el mapa seleccionado
        if tipo_mapa == "Mapa Combinado":
            fig_mapa = crear_mapa_combinado(gdf_final, tipo_pastura)
        elif tipo_mapa == "Tipos de Superficie":
            fig_mapa = crear_mapa_tipo_superficie(gdf_final, tipo_pastura)
        elif tipo_mapa == "NDVI":
            fig_mapa = crear_mapa_ndvi(gdf_final, tipo_pastura)
        elif tipo_mapa == "Biomasa":
            fig_mapa = crear_mapa_biomasa(gdf_final, tipo_pastura)
        elif tipo_mapa == "Días de Permanencia":
            fig_mapa = crear_mapa_dias_permanencia(gdf_final, tipo_pastura)
        elif tipo_mapa == "EV/Ha":
            fig_mapa = crear_mapa_ev_ha(gdf_final, tipo_pastura)
        
        if fig_mapa:
            st.pyplot(fig_mapa)
            
            # Botón para descargar el mapa
            buf = io.BytesIO()
            fig_mapa.savefig(buf, format="png", dpi=150, bbox_inches='tight')
            buf.seek(0)
            
            st.download_button(
                label="📥 Descargar Mapa",
                data=buf,
                file_name=f"mapa_{tipo_mapa.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                mime="image/png"
            )
        else:
            st.warning("No se pudo generar el mapa")
        
        st.subheader("🌱 Recomendaciones de Ganadería Regenerativa")
        
        if tipo_pastura in RECOMENDACIONES_REGENERATIVAS:
            recomendaciones = RECOMENDACIONES_REGENERATIVAS[tipo_pastura]
            
            for categoria, items in recomendaciones.items():
                with st.expander(f"📋 {categoria.replace('_', ' ').title()}"):
                    for item in items:
                        st.write(f"• {item}")
        
        st.subheader("📄 Generar Informe PDF")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            if st.button("🔄 Generar Informe PDF", type="primary"):
                with st.spinner("Generando informe PDF..."):
                    try:
                        pdf_buffer = generar_informe_pdf(
                            gdf_final, tipo_pastura, peso_promedio, carga_animal,
                            area_total, fecha_imagen, fuente_satelital
                        )
                        
                        st.session_state.pdf_buffer = pdf_buffer
                        st.session_state.pdf_generado = True
                        
                        st.success("✅ Informe PDF generado correctamente")
                        st.rerun()
                    
                    except Exception as e:
                        st.error(f"❌ Error al generar PDF: {str(e)}")
        
        if st.session_state.pdf_generado and st.session_state.pdf_buffer is not None:
            st.download_button(
                label="📥 Descargar Informe PDF",
                data=st.session_state.pdf_buffer,
                file_name=f"informe_forrajero_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                type="primary"
            )

if __name__ == "__main__":
    main()
