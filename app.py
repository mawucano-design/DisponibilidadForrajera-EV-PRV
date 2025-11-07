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

# PDF
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepInFrame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Folium (opcional)
try:
    import folium
    from folium import plugins
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    st.warning("Folium no está disponible. Mapas interactivos limitados.")
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Configuración
st.set_page_config(page_title="Analizador Forrajero", layout="wide")
st.title("ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Session State
for key in ['gdf_cargado', 'analisis_completado', 'gdf_analizado', 'area_total', 'pdf_buffer']:
    if key not in st.session_state:
        st.session_state[key] = None
if 'configuracion' not in st.session_state:
    st.session_state.configuracion = {
        'ms_optimo': 4000, 'crecimiento_diario': 80, 'consumo_porcentaje': 0.025,
        'tasa_utilizacion': 0.55, 'umbral_ndvi_suelo': 0.15, 'umbral_ndvi_pastura': 0.6
    }

# === RECOMENDACIONES Y PARÁMETROS (igual que antes) ===
RECOMENDACIONES_REGENERATIVAS = { ... }  # ← (mismo contenido que antes)
PARAMETROS_FORRAJEROS_BASE = { ... }      # ← (mismo contenido que antes)

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {k: st.session_state.configuracion[k] if k in st.session_state.configuracion else v 
                for k, v in PARAMETROS_FORRAJEROS_BASE['FESTUCA'].items()}
    return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

def calcular_superficie(gdf):
    try:
        if gdf.empty: return 0.0 if len(gdf) == 1 else pd.Series([0.0] * len(gdf))
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        areas_ha = area_m2 / 10000
        return float(areas_ha.iloc[0]) if len(gdf) == 1 else areas_ha
    except:
        areas_ha = gdf.geometry.area / 10000
        return float(areas_ha.iloc[0]) if len(gdf) == 1 else areas_ha

def dividir_potrero_en_subLotes(gdf, n_zonas):
    if len(gdf) == 0 or gdf.iloc[0].geometry is None:
        return gdf
    potrero = gdf.iloc[0].geometry
    bounds = potrero.bounds
    minx, miny, maxx, maxy = bounds
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    width, height = (maxx - minx) / n_cols, (maxy - miny) / n_rows
    sub_poligonos = []
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas: break
            cell = Polygon([(minx + j*width, miny + i*height), (minx + (j+1)*width, miny + i*height),
                           (minx + (j+1)*width, miny + (i+1)*height), (minx + j*width, miny + (i+1)*height)])
            inter = potrero.intersection(cell)
            if not inter.is_empty and inter.area > 0:
                sub_poligonos.append(inter)
    return gpd.GeoDataFrame({'id_subLote': range(1, len(sub_poligonos)+1), 'geometry': sub_poligonos}, crs=gdf.crs)

# =============================================================================
# MAPAS CON ZOOM AUTOMÁTICO
# =============================================================================
if FOLIUM_AVAILABLE:
    BASE_MAPS_CONFIG = {
        "ESRI Satélite": {"tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', "attr": 'Esri', "name": "ESRI"},
        "OpenStreetMap": {"tiles": 'OpenStreetMap', "attr": 'OSM', "name": "OSM"},
        "CartoDB Positron": {"tiles": 'CartoDB positron', "attr": 'CartoDB', "name": "Carto"}
    }

    def crear_mapa_lote(gdf, base_map_name="ESRI Satélite"):
        if not gdf or len(gdf) == 0: return None
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        sw = [bounds[1], bounds[0]]
        ne = [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        for name, cfg in BASE_MAPS_CONFIG.items():
            folium.TileLayer(tiles=cfg["tiles"], attr=cfg["attr"], name=cfg["name"], overlay=(name == base_map_name), control=True).add_to(m)
        folium.GeoJson(gdf.__geo_interface__, style_function=lambda x: {'fillColor': '#3388ff', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.3}).add_to(m)
        m.fit_bounds([sw, ne])
        folium.LayerControl().add_to(m)
        return m

    def crear_mapa_analisis(gdf_analizado, base_map_name="ESRI Satélite"):
        if not gdf_analizado or len(gdf_analizado) == 0: return None
        bounds = gdf_analizado.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS_CONFIG["ESRI Satélite"], overlay=True).add_to(m)
        for name, cfg in BASE_MAPS_CONFIG.items():
            if name != "ESRI Satélite":
                folium.TileLayer(tiles=cfg["tiles"], attr=cfg["attr"], name=cfg["name"], overlay=False, control=True).add_to(m)

        def estilo(feature):
            t = feature['properties']['tipo_superficie']
            colores = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 'VEGETACION_ESCASA': '#fee08b',
                       'VEGETACION_MODERADA': '#a6d96a', 'VEGETACION_DENSA': '#1a9850'}
            return {'fillColor': colores.get(t, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.7}

        folium.GeoJson(gdf_analizado.__geo_interface__, style_function=estilo,
                       tooltip=folium.GeoJsonTooltip(fields=['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha'],
                                                    aliases=['Sub-Lote:', 'Superficie:', 'NDVI:', 'Biomasa:', 'EV/Ha:']),
                       popup=folium.GeoJsonPopup(fields=['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia'],
                                                aliases=['Sub-Lote:', 'Superficie:', 'NDVI:', 'Biomasa (kg/ha):', 'EV Total:', 'Días:'])).add_to(m)
        m.fit_bounds([sw, ne])
        folium.LayerControl().add_to(m)
        return m
else:
    def crear_mapa_lote(*args, **kwargs): return None
    def crear_mapa_analisis(*args, **kwargs): return None

# =============================================================================
# ANÁLISIS
# =============================================================================
def simular_datos_satelitales(gdf, tipo_pastura, fecha):
    if not gdf or len(gdf) == 0: return gdf
    params = obtener_parametros_forrajeros(tipo_pastura)
    np.random.seed(hash(fecha.strftime("%Y%m%d")) % 10000)
    results = []
    for _, row in gdf.iterrows():
        area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf.crs))
        ndvi = np.clip(np.random.normal(0.5, 0.2) + 0.1 * np.sin(2 * np.pi * fecha.timetuple().tm_yday / 365), 0.05, 0.85)
        if ndvi < params['UMBRAL_NDVI_SUELO']: tipo, biomasa = 'SUELO_DESNUDO', np.random.uniform(100, 500)
        elif ndvi < params['UMBRAL_NDVI_SUELO'] + 0.1: tipo, biomasa = 'SUELO_PARCIAL', np.random.uniform(500, 1000)
        elif ndvi < params['UMBRAL_NDVI_PASTURA'] - 0.1: tipo, biomasa = 'VEGETACION_ESCASA', np.random.uniform(1000, 2000)
        elif ndvi < params['UMBRAL_NDVI_PASTURA']: tipo, biomasa = 'VEGETACION_MODERADA', np.random.uniform(2000, params['MS_POR_HA_OPTIMO'] * 0.8)
        else: tipo, biomasa = 'VEGETACION_DENSA', np.random.uniform(params['MS_POR_HA_OPTIMO'] * 0.8, params['MS_POR_HA_OPTIMO'] * 1.2)
        biomasa = max(100, biomasa * (1 + (ndvi - 0.5) * 0.5))
        results.append({'id_subLote': row['id_subLote'], 'geometry': row.geometry, 'ndvi': ndvi, 'tipo_superficie': tipo,
                        'biomasa_disponible_kg_ms_ha': biomasa, 'area_ha': area_ha})
    return gpd.GeoDataFrame(results, crs=gdf.crs)

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    if not gdf_analizado: return gdf_analizado
    params = obtener_parametros_forrajeros(tipo_pastura)
    consumo_animal = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
    consumo_total = consumo_animal * carga_animal
    gdf = gdf_analizado.copy()
    gdf['biomasa_kg'] = gdf['biomasa_disponible_kg_ms_ha'] * gdf['area_ha']
    gdf['ev_total'] = gdf['biomasa_kg'] / consumo_animal  # EV totales por sublote
    gdf['ev_ha'] = gdf['ev_total'] / gdf['area_ha']       # EV por hectárea
    gdf['dias_permanencia'] = (gdf['biomasa_kg'] * params['TASA_UTILIZACION_RECOMENDADA']) / consumo_total
    return gdf

# =============================================================================
# GENERAR PDF
# =============================================================================
def generar_pdf(gdf_final, area_total, tipo_pastura, mapa_lote_html, mapa_analisis_html):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Center', alignment=1, fontSize=12, spaceAfter=10))
    story = []

    # Título
    story.append(Paragraph("INFORME FORRAJERO - GANADERÍA REGENERATIVA", styles['Title']))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y')} | Área Total: {area_total:.2f} ha | Pastura: {tipo_pastura}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    # Mapas como imágenes
    for html, titulo in [(mapa_lote_html, "MAPA DEL LOTE"), (mapa_analisis_html, "MAPA DE ANÁLISIS")]:
        img_data = folium.Figure().add_child(folium.Element(html))._repr_png_()
        img = Image(io.BytesIO(img_data), width=7*inch, height=4*inch)
        story.append(Paragraph(titulo, styles['Heading2']))
        story.append(KeepInFrame(max_width=7*inch, max_height=4*inch, content=[img]))
        story.append(PageBreak())

    # Tabla de resultados
    data = [["Sub-Lote", "Tipo", "NDVI", "Biomasa (kg/ha)", "EV Total", "Días"]]
    for _, r in gdf_final.iterrows():
        data.append([r['id_subLote'], r['tipo_superficie'].replace('_', ' ').title(),
                     f"{r['ndvi']:.3f}", f"{r['biomasa_disponible_kg_ms_ha']:.0f}",
                     f"{r['ev_total']:.1f}", f"{r['dias_permanencia']:.1f}"])
    table = Table(data, colWidths=[60, 90, 50, 70, 60, 60])
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a9850')),
                               ('TEXTCOLOR',(0,0),(-1,0), colors.white),
                               ('ALIGN',(0,0),(-1,-1),'CENTER'),
                               ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                               ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    story.append(Paragraph("DETALLE POR SUB-LOTE", styles['Heading2']))
    story.append(table)
    story.append(PageBreak())

    # Recomendaciones
    rec = RECOMENDACIONES_REGENERATIVAS.get(tipo_pastura, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
    story.append(Paragraph("RECOMENDACIONES DE GANADERÍA REGENERATIVA", styles['Heading1']))
    for seccion, items in rec.items():
        story.append(Paragraph(seccion.replace('_', ' ').title(), styles['Heading3']))
        for item in items:
            story.append(Paragraph(f"• {item}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# SIDEBAR
# =============================================================================
def mostrar_sidebar():
    with st.sidebar:
        st.header("Configuración")
        base_map = st.selectbox("Mapa Base", ["ESRI Satélite", "OpenStreetMap"], key="mapa_base") if FOLIUM_AVAILABLE else "ESRI Satélite"
        fuente = st.selectbox("Satélite", ["SIMULADO"], key="satelite")
        tipo_pastura = st.selectbox("Pastura", ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"], key="pastura")
        fecha = st.date_input("Fecha imagen", datetime.now() - timedelta(days=30), max_value=datetime.now(), key="fecha")
        
        if tipo_pastura == "PERSONALIZADO":
            st.session_state.configuracion['ms_optimo'] = st.number_input("MS Óptima (kg/ha)", 1000, 10000, 4000, key="ms")
            st.session_state.configuracion['tasa_utilizacion'] = st.number_input("Tasa Utilización", 0.3, 0.8, 0.55, 0.01, key="tasa")
        
        peso = st.slider("Peso animal (kg)", 300, 600, 450, key="peso")
        carga = st.slider("Carga (cabezas)", 50, 1000, 100, key="carga")
        n_div = st.slider("Sub-lotes", 12, 32, 24, key="div")
        uploaded = st.file_uploader("ZIP con shapefile", type=['zip'], key="zip")
        if st.button("Reiniciar", key="reset"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        return uploaded, tipo_pastura, peso, carga, n_div, fecha, base_map

# =============================================================================
# MAIN
# =============================================================================
def main():
    uploaded, tipo_pastura, peso, carga, n_div, fecha, base_map = mostrar_sidebar()
    
    if uploaded:
        gdf = procesar_archivo(uploaded)
        if gdf is not None:
            st.session_state.gdf_cargado = gdf
            area_total = calcular_superficie(gdf)
            st.session_state.area_total = area_total
            st.success(f"Lote cargado: {area_total:.2f} ha")

            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader("MAPA DEL LOTE")
                mapa_lote = crear_mapa_lote(gdf, base_map)
                if mapa_lote and FOLIUM_AVAILABLE:
                    st_folium(mapa_lote, width=700, height=500, key="mapa_lote")
            with col2:
                st.metric("Área Total", f"{area_total:.2f} ha")
                st.metric("Sub-lotes", n_div)
                if st.button("EJECUTAR ANÁLISIS", type="primary"):
                    with st.spinner("Analizando..."):
                        gdf_div = dividir_potrero_en_subLotes(gdf, n_div)
                        gdf_sim = simular_datos_satelitales(gdf_div, tipo_pastura, fecha)
                        gdf_final = calcular_metricas_ganaderas(gdf_sim, tipo_pastura, peso, carga)
                        st.session_state.gdf_analizado = gdf_final
                        st.session_state.analisis_completado = True
                        st.success("¡Análisis completado!")

    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        gdf_final = st.session_state.gdf_analizado
        area_total = st.session_state.area_total

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader("MAPA DE ANÁLISIS")
            mapa_analisis = crear_mapa_analisis(gdf_final, base_map)
            if mapa_analisis:
                mapa_html = st_folium(mapa_analisis, width=800, height=500, returned_objects=[])
            else:
                mapa_html = None
        with col2:
            st.metric("Biomasa Promedio", f"{gdf_final['biomasa_disponible_kg_ms_ha'].mean():.0f} kg/ha")
            st.metric("EV Total", f"{gdf_final['ev_total'].sum():.0f}")
            st.metric("Días Promedio", f"{gdf_final['dias_permanencia'].mean():.1f}")

        st.markdown("---")
        display_df = gdf_final[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_total', 'dias_permanencia']].copy()
        display_df.columns = ['Sub-Lote', 'Tipo', 'NDVI', 'Biomasa (kg/ha)', 'EV Total', 'Días']
        display_df['Tipo'] = display_df['Tipo'].str.replace('_', ' ').str.title()
        display_df = display_df.round({'NDVI': 3, 'Biomasa (kg/ha)': 0, 'EV Total': 1, 'Días': 1})
        st.dataframe(display_df, use_container_width=True)

        if st.button("GENERAR PDF"):
            with st.spinner("Generando PDF..."):
                mapa_lote_html = crear_mapa_lote(st.session_state.gdf_cargado, base_map)._repr_html_()
                mapa_analisis_html = crear_mapa_analisis(gdf_final, base_map)._repr_html_()
                pdf_buffer = generar_pdf(gdf_final, area_total, tipo_pastura, mapa_lote_html, mapa_analisis_html)
                st.session_state.pdf_buffer = pdf_buffer
                st.success("PDF generado")

        if st.session_state.pdf_buffer:
            st.download_button("DESCARGAR INFORME PDF", st.session_state.pdf_buffer, "informe_forrajero.pdf", "application/pdf")

def procesar_archivo(zip_file):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(zip_file, 'r') as z:
                z.extractall(tmp)
            shp = [f for f in os.listdir(tmp) if f.endswith('.shp')][0]
            gdf = gpd.read_file(os.path.join(tmp, shp))
            if gdf.crs is None: gdf.set_crs('EPSG:4326', inplace=True)
            elif gdf.crs != 'EPSG:4326': gdf = gdf.to_crs('EPSG:4326')
            return gdf
        except Exception as e:
            st.error(f"Error: {e}")
            return None

if __name__ == "__main__":
    main()
