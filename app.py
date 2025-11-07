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
import requests
import rasterio
from rasterio.mask import mask
import json

# Importaciones para PDF (igual que en el archivo funcionando)
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import base64

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
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01, format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.05, max_value=0.3, value=0.15, step=0.01, format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.3, max_value=0.8, value=0.6, step=0.01, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

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

# PALETAS GEE
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
    'COBERTURA': ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60']
}

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

# FUNCIÓN PARA GENERAR PDF (ESTILO DEL ARCHIVO FUNCIONANDO)
def generar_informe_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, area_total, fecha_imagen, fuente_satelital):
    """Genera un informe PDF completo con los resultados del análisis"""
    
    # Crear buffer para el PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    styles = getSampleStyleSheet()
    
    # Crear estilos personalizados
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
    
    # Contenido del PDF
    story = []
    
    # Título principal
    story.append(Paragraph("INFORME DE ANÁLISIS FORRAJERO CON GANADERÍA REGENERATIVA", title_style))
    story.append(Spacer(1, 20))
    
    # Información general
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
    
    # Estadísticas resumen
    story.append(Paragraph("ESTADÍSTICAS DEL ANÁLISIS", heading_style))
    
    # Calcular estadísticas básicas
    biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean() if 'biomasa_disponible_kg_ms_ha' in gdf_analizado.columns else 0
    ndvi_promedio = gdf_analizado['ndvi'].mean() if 'ndvi' in gdf_analizado.columns else 0
    
    stats_data = [
        ["Estadística", "Valor"],
        ["Biomasa Disponible Promedio", f"{biomasa_promedio:.0f} kg MS/ha"],
        ["NDVI Promedio", f"{ndvi_promedio:.3f}"],
        ["Número de Sub-Lotes", f"{len(gdf_analizado)}"],
        ["Área Total", f"{area_total:.2f} ha"]
    ]
    
    stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 20))
    
    # Recomendaciones regenerativas
    story.append(PageBreak())
    story.append(Paragraph("RECOMENDACIONES DE GANADERÍA REGENERATIVA", heading_style))
    
    # Determinar enfoque
    if biomasa_promedio < 1000:
        enfoque = "ENFOQUE: REGENERACIÓN URGENTE - Intensidad: Alta"
    elif biomasa_promedio < 2000:
        enfoque = "ENFOQUE: MEJORA CONTINUA - Intensidad: Media"
    else:
        enfoque = "ENFOQUE: OPTIMIZACIÓN REGENERATIVA - Intensidad: Baja"
    
    story.append(Paragraph(f"<b>Enfoque Principal:</b> {enfoque}", normal_style))
    story.append(Spacer(1, 10))
    
    # Recomendaciones específicas
    recomendaciones = RECOMENDACIONES_REGENERATIVAS.get(tipo_pastura, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
    
    for categoria_rec, items in recomendaciones.items():
        story.append(Paragraph(f"<b>{categoria_rec.replace('_', ' ').title()}:</b>", normal_style))
        for item in items[:2]:  # Mostrar solo 2 items por categoría
            story.append(Paragraph(f"• {item}", normal_style))
        story.append(Spacer(1, 5))
    
    # Plan de implementación
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>PLAN DE IMPLEMENTACIÓN:</b>", normal_style))
    
    planes = [
        ("INMEDIATO (0-30 días)", [
            "Diagnóstico participativo con equipo técnico",
            "Preparación de insumos orgánicos locales",
            "Identificación de áreas prioritarias"
        ]),
        ("CORTO PLAZO (1-3 meses)", [
            "Implementación de rotación de pastoreo",
            "Establecimiento de coberturas vivas",
            "Aplicación de biofertilizantes"
        ]),
        ("MEDIANO PLAZO (3-12 meses)", [
            "Ajuste del sistema según monitoreo",
            "Diversificación con árboles y arbustos",
            "Capacitación del personal"
        ])
    ]
    
    for periodo, acciones in planes:
        story.append(Paragraph(f"<b>{periodo}:</b>", normal_style))
        for accion in acciones:
            story.append(Paragraph(f"• {accion}", normal_style))
        story.append(Spacer(1, 5))
    
    # Pie de página
    story.append(Spacer(1, 20))
    story.append(Paragraph("INFORMACIÓN ADICIONAL", heading_style))
    story.append(Paragraph("Este informe fue generado automáticamente por el Sistema de Análisis Forrajero con Ganadería Regenerativa.", normal_style))
    story.append(Paragraph("Para consultas técnicas o implementación de sistemas regenerativos, contacte con especialistas certificados.", normal_style))
    
    # Generar PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer

# FUNCIÓN PARA MOSTRAR SECCIÓN DE PDF
def mostrar_seccion_exportacion_pdf():
    """Muestra la sección de exportación de PDF en la interfaz"""
    
    if hasattr(st.session_state, 'gdf_analizado') and st.session_state.gdf_analizado is not None:
        st.markdown("---")
        st.subheader("📄 GENERAR INFORME PDF COMPLETO")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.info("""
            **El informe PDF incluirá:**
            • Resumen ejecutivo del análisis
            • Estadísticas detalladas
            • Recomendaciones de ganadería regenerativa
            • Plan de implementación por fases
            """)
        
        with col2:
            if st.button("🖨️ Generar Informe PDF", type="primary", use_container_width=True):
                with st.spinner("Generando informe PDF..."):
                    pdf_buffer = generar_informe_pdf(
                        st.session_state.gdf_analizado,
                        tipo_pastura,
                        peso_promedio,
                        carga_animal,
                        st.session_state.area_total,
                        fecha_imagen,
                        fuente_satelital
                    )
                    
                    if pdf_buffer:
                        st.download_button(
                            "📥 Descargar Informe PDF Completo",
                            pdf_buffer.getvalue(),
                            f"informe_regenerativo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            "application/pdf",
                            key="descarga_pdf"
                        )
                        st.success("✅ Informe PDF generado exitosamente!")
                    else:
                        st.error("❌ Error al generar el PDF")

# INTERFAZ PRINCIPAL SIMPLIFICADA (para probar el PDF)
def main():
    st.markdown("### 📁 CARGAR DATOS DEL POTRERO")
    
    # Procesar archivo subido
    gdf_cargado = None
    if uploaded_zip is not None:
        with st.spinner("Cargando y procesando shapefile..."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                    if shp_files:
                        shp_path = os.path.join(tmp_dir, shp_files[0])
                        gdf_cargado = gpd.read_file(shp_path)
                        st.session_state.gdf_cargado = gdf_cargado
                        
                        area_total = calcular_superficie(gdf_cargado).sum()
                        st.session_state.area_total = area_total
                        
                        st.success(f"✅ **Potrero cargado exitosamente!**")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Polígonos", len(gdf_cargado))
                        with col2:
                            st.metric("Área Total", f"{area_total:.1f} ha")
                        with col3:
                            st.metric("Pastura", tipo_pastura)
                            
            except Exception as e:
                st.error(f"❌ Error cargando shapefile: {str(e)}")
    
    # Botón de análisis simplificado
    st.markdown("---")
    st.markdown("### 🚀 ANÁLISIS RÁPIDO")
    
    if st.session_state.gdf_cargado is not None:
        if st.button("🔬 Realizar Análisis Forrajero", type="primary"):
            with st.spinner("Realizando análisis..."):
                # Simular análisis básico
                gdf_dividido = dividir_potrero_en_subLotes(st.session_state.gdf_cargado, n_divisiones)
                
                # Crear datos de ejemplo para el análisis
                gdf_analizado = gdf_dividido.copy()
                gdf_analizado['area_ha'] = calcular_superficie(gdf_analizado)
                gdf_analizado['ndvi'] = np.random.uniform(0.3, 0.8, len(gdf_analizado))
                gdf_analizado['biomasa_disponible_kg_ms_ha'] = np.random.uniform(500, 3500, len(gdf_analizado))
                gdf_analizado['tipo_superficie'] = np.random.choice(['VEGETACION_DENSA', 'VEGETACION_MODERADA', 'VEGETACION_ESCASA'], len(gdf_analizado))
                
                st.session_state.gdf_analizado = gdf_analizado
                st.session_state.analisis_completado = True
                
                st.success("✅ Análisis completado!")
                
                # Mostrar sección de exportación
                mostrar_seccion_exportacion_pdf()
                
                # Mostrar tabla de resultados
                st.subheader("📊 Resultados del Análisis")
                st.dataframe(gdf_analizado[['id_subLote', 'area_ha', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'tipo_superficie']].head(10))
    else:
        st.info("""
        **📋 Para comenzar:**
        1. **Sube un archivo ZIP** con el shapefile del potrero
        2. **Ajusta los parámetros** en la barra lateral  
        3. **Haz clic en el botón** para realizar el análisis
        4. **Genera el PDF** con recomendaciones regenerativas
        """)

# EJECUTAR APLICACIÓN
if __name__ == "__main__":
    main()
