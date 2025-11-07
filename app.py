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

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepInFrame
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors

# Folium
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    st.warning("Folium no disponible. Mapas limitados.")
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

st.set_page_config(page_title="Analizador Forrajero GEE", layout="wide")
st.title("ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Session State
for key in ['gdf_cargado', 'analisis_completado', 'gdf_analizado', 'area_total', 'pdf_buffer']:
    if key not in st.session_state:
        st.session_state[key] = None

# =============================================================================
# TU CÓDIGO ORIGINAL (SIN MODIFICAR)
# =============================================================================
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# ... [TODAS TUS IMPORTACIONES Y FUNCIONES ORIGINALES] ...

# === RECOMENDACIONES REGENERATIVAS (NUEVAS) ===
RECOMENDACIONES_REGENERATIVAS = {
    'ALFALFA': {
        'PRÁCTICAS_REGENERATIVAS': ["Sistema PRV 1-3 días", "Leguminosas nativas", "Biofertilizantes", "Bancos de proteína"],
        'MANEJO_SUELO': ["Compost 2-3 ton/ha", "Harinas de rocas", "Micorrizas", "Coberturas vivas"],
        'BIODIVERSIDAD': ["Corredores biológicos", "Cercas vivas", "Rotación con cultivos", "Control biológico"],
        'AGUA_RETENCIÓN': ["Swales", "Keyline", "Mulching", "Riego por goteo"]
    },
    # ... (el resto igual que antes)
    'PERSONALIZADO': { ... }
}

# =============================================================================
# CARGA DE ARCHIVO (ZIP O KML) - NUEVO
# =============================================================================
def cargar_geometria(uploaded_file):
    if not uploaded_file:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if uploaded_file.name.endswith('.zip'):
                with zipfile.ZipFile(uploaded_file) as z:
                    z.extractall(tmp)
                shp = [f for f in os.listdir(tmp) if f.endswith('.shp')][0]
                gdf = gpd.read_file(os.path.join(tmp, shp))
            elif uploaded_file.name.endswith('.kml'):
                path = os.path.join(tmp, 'file.kml')
                with open(path, 'wb') as f:
                    f.write(uploaded_file.getvalue())
                gdf = gpd.read_file(path, driver='KML')
            else:
                st.error("Formato no soportado")
                return None

            if gdf.crs is None:
                gdf.set_crs('EPSG:4326', inplace=True)
            elif gdf.crs != 'EPSG:4326':
                gdf = gdf.to_crs('EPSG:4326')
            return gdf
        except Exception as e:
            st.error(f"Error: {e}")
            return None

# =============================================================================
# MAPAS FOLIUM CON ZOOM AUTOMÁTICO - MEJORADO
# =============================================================================
if FOLIUM_AVAILABLE:
    BASE_MAPS_CONFIG = {
        "ESRI Satélite": {"tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', "attr": 'Esri'},
        "OpenStreetMap": {"tiles": 'OpenStreetMap', "attr": 'OpenStreetMap'},
        "CartoDB Positron": {"tiles": 'CartoDB positron', "attr": 'CartoDB'}
    }

    def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"):
        if gdf is None or gdf.empty: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS_CONFIG[base_map_name], overlay=True).add_to(m)
        folium.GeoJson(gdf, style_function=lambda x: {'fillColor': '#3388ff', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.3}).add_to(m)
        m.fit_bounds([sw, ne])
        return m

    def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"):
        if gdf_analizado is None or gdf_analizado.empty: return None
        bounds = gdf_analizado.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS_CONFIG["ESRI Satélite"], overlay=True).add_to(m)
        colores = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 'VEGETACION_ESCASA': '#fee08b',
                   'VEGETACION_MODERADA': '#a6d96a', 'VEGETACION_DENSA': '#1a9850'}
        def estilo(f):
            t = f['properties']['tipo_superficie']
            return {'fillColor': colores.get(t, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.7}
        folium.GeoJson(gdf_analizado, style_function=estilo,
                       tooltip=folium.GeoJsonTooltip(['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha'],
                                                    aliases=['Sub:', 'Tipo:', 'NDVI:', 'Biomasa:', 'EV/Ha:'])).add_to(m)
        m.fit_bounds([sw, ne])
        return m
else:
    crear_mapa_interactivo = lambda gdf, base: None
    crear_mapa_analisis_interactivo = lambda gdf, tipo, base: None

# =============================================================================
# PDF GENERATOR - NUEVO
# =============================================================================
def generar_pdf(gdf_cargado, gdf_analizado, area_total, tipo_pastura):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("INFORME FORRAJERO REGENERATIVO", styles['Title']))
    story.append(Paragraph(f"Fecha: {datetime.now():%d/%m/%Y} | Área: {area_total:.2f} ha | Pastura: {tipo_pastura}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    # Mapas
    for mapa_func, titulo in [(crear_mapa_interactivo, "MAPA DEL LOTE"), (crear_mapa_analisis_interactivo, "MAPA DE ANÁLISIS")]:
        m = mapa_func(gdf_cargado if "LOTE" in titulo else gdf_analizado, tipo_pastura)
        if m:
            img_data = m._to_png()
            img = Image(io.BytesIO(img_data), 7*inch, 4*inch)
            story.append(Paragraph(titulo, styles['Heading2']))
            story.append(KeepInFrame(7*inch, 4*inch, [img]))
            story.append(PageBreak())

    # Tabla
    data = [["Sub", "Tipo", "NDVI", "Biomasa", "EV/Ha", "Días"]]
    for _, r in gdf_analizado.iterrows():
        data.append([r['id_subLote'], r['tipo_superficie'].replace('_', ' ').title(),
                     f"{r['ndvi']:.3f}", f"{r['biomasa_disponible_kg_ms_ha']:.0f}",
                     f"{r['ev_ha']:.2f}", f"{r['dias_permanencia']:.1f}"])
    table = Table(data)
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), '#1a9850'), ('TEXTCOLOR',(0,0),(-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    story.append(Paragraph("DETALLE POR SUB-LOTE", styles['Heading2']))
    story.append(table)
    story.append(PageBreak())

    # Recomendaciones
    rec = RECOMENDACIONES_REGENERATIVAS.get(tipo_pastura, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
    story.append(Paragraph("RECOMENDACIONES REGENERATIVAS", styles['Heading1']))
    for sec, items in rec.items():
        story.append(Paragraph(sec.replace('_', ' ').title(), styles['Heading3']))
        for i in items: story.append(Paragraph(f"• {i}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))

    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# MAIN - TU CÓDIGO ORIGINAL + PDF + KML
# =============================================================================
uploaded_file = st.file_uploader("Subir ZIP o KML", type=['zip', 'kml'])

if uploaded_file:
    gdf = cargar_geometria(uploaded_file)
    if gdf is not None and not gdf.empty:
        area_total = calcular_superficie(gdf).sum()
        st.session_state.gdf_cargado = gdf
        st.session_state.area_total = area_total
        st.success(f"Lote cargado: {area_total:.2f} ha")

        if FOLIUM_AVAILABLE:
            m = crear_mapa_interactivo(gdf, base_map_option)
            if m: st_folium(m, width=700, height=500)

        if st.button("EJECUTAR ANÁLISIS FORRAJERO REALISTA", type="primary"):
            with st.spinner("Analizando..."):
                # === TU ANÁLISIS COMPLETO (SIN CAMBIOS) ===
                resultado = analisis_forrajero_completo_realista(
                    gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones,
                    fuente_satelital, fecha_imagen, nubes_max,
                    umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo
                )
                if resultado:
                    st.balloons()
                    st.success("Análisis completado!")

# =============================================================================
# BOTÓN PDF - NUEVO
# =============================================================================
if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("GENERAR REPORTE PDF"):
            with st.spinner("Generando PDF..."):
                pdf = generar_pdf(
                    st.session_state.gdf_cargado,
                    st.session_state.gdf_analizado,
                    st.session_state.area_total,
                    tipo_pastura
                )
                st.session_state.pdf_buffer = pdf
                st.success("PDF generado")

    if st.session_state.pdf_buffer:
        st.download_button(
            "DESCARGAR REPORTE PDF",
            st.session_state.pdf_buffer,
            f"informe_forrajero_{tipo_pastura}_{datetime.now():%Y%m%d}.pdf",
            "application/pdf"
        )
