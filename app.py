import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
from shapely.geometry import Polygon
import math
import io

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepInFrame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    st.warning("Folium no disponible. Mapas limitados.")
    FOLIUM_AVAILABLE = False

# Config
st.set_page_config(page_title="Analizador Forrajero", layout="wide")
st.title("ANALIZADOR FORRAJERO - GANADERÍA REGENERATIVA")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Session State
for key in ['gdf_cargado', 'analisis_completado', 'gdf_analizado', 'area_total', 'pdf_buffer']:
    if key not in st.session_state:
        st.session_state[key] = None
if 'config' not in st.session_state:
    st.session_state.config = {
        'ms_optimo': 4000, 'crecimiento_diario': 80, 'consumo_porcentaje': 0.025,
        'tasa_utilizacion': 0.55, 'umbral_ndvi_suelo': 0.15, 'umbral_ndvi_pastura': 0.6
    }

# === DATOS BASE ===
RECOMENDACIONES_REGENERATIVAS = { ... }  # ← (igual que tu código)
PARAMETROS_FORRAJEROS_BASE = { ... }      # ← (igual que tu código)

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def obtener_parametros(tipo):
    if tipo == "PERSONALIZADO":
        return {k: st.session_state.config.get(k, v) for k, v in PARAMETROS_FORRAJEROS_BASE['FESTUCA'].items()}
    return PARAMETROS_FORRAJEROS_BASE[tipo]

def calcular_superficie(gdf):
    if gdf.empty: return 0.0
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf = gdf.to_crs('EPSG:3857')
        return gdf.geometry.area.sum() / 10000
    except:
        return gdf.geometry.area.sum() / 10000

def area_individual(row, crs):
    gdf_temp = gpd.GeoDataFrame([row], crs=crs)
    return calcular_superficie(gdf_temp)

def dividir_potrero(gdf, n):
    if gdf.empty: return gdf
    poly = gdf.iloc[0].geometry
    b = poly.bounds
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    w, h = (b[2]-b[0])/cols, (b[3]-b[1])/rows
    subs = []
    for i in range(rows):
        for j in range(cols):
            if len(subs) >= n: break
            cell = Polygon([(b[0]+j*w, b[1]+i*h), (b[0]+(j+1)*w, b[1]+i*h),
                           (b[0]+(j+1)*w, b[1]+(i+1)*h), (b[0]+j*w, b[1]+(i+1)*h)])
            inter = poly.intersection(cell)
            if not inter.is_empty and inter.area > 0:
                subs.append(inter)
    return gpd.GeoDataFrame({'id_subLote': range(1, len(subs)+1), 'geometry': subs}, crs=gdf.crs)

# =============================================================================
# MAPAS CON ZOOM AUTOMÁTICO
# =============================================================================
if FOLIUM_AVAILABLE:
    BASE = {
        "ESRI": {"tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', "attr": 'Esri'}
    }

    def mapa_lote(gdf, base="ESRI"):
        if not gdf: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE[base], name=base, overlay=True).add_to(m)
        folium.GeoJson(gdf, style_function=lambda x: {'fillColor': '#3388ff', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.3}).add_to(m)
        m.fit_bounds([sw, ne])
        return m

    def mapa_analisis(gdf, base="ESRI"):
        if not gdf: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE[base], overlay=True).add_to(m)
        def estilo(f):
            t = f['properties']['tipo_superficie']
            c = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 'VEGETACION_ESCASA': '#fee08b',
                 'VEGETACION_MODERADA': '#a6d96a', 'VEGETACION_DENSA': '#1a9850'}.get(t, '#3388ff')
            return {'fillColor': c, 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.7}
        folium.GeoJson(gdf, style_function=estilo,
                       tooltip=folium.GeoJsonTooltip(['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_kg_ha', 'ev_total'],
                                                    aliases=['Sub:', 'Tipo:', 'NDVI:', 'Biomasa:', 'EV:'])).add_to(m)
        m.fit_bounds([sw, ne])
        return m
else:
    def mapa_lote(*a): return None
    def mapa_analisis(*a): return None

# =============================================================================
# SIMULACIÓN Y CÁLCULOS
# =============================================================================
def simular_satelite(gdf, tipo, fecha):
    if gdf.empty: return gdf
    p = obtener_parametros(tipo)
    np.random.seed(hash(fecha.strftime("%Y%m%d")) % 10000)
    res = []
    for _, r in gdf.iterrows():
        area = area_individual(r, gdf.crs)
        ndvi = np.clip(np.random.normal(0.5, 0.2) + 0.1 * np.sin(2 * np.pi * fecha.timetuple().tm_yday / 365), 0.05, 0.85)
        if ndvi < p['UMBRAL_NDVI_SUELO']: t, b = 'SUELO_DESNUDO', np.random.uniform(100, 500)
        elif ndvi < p['UMBRAL_NDVI_SUELO'] + 0.1: t, b = 'SUELO_PARCIAL', np.random.uniform(500, 1000)
        elif ndvi < p['UMBRAL_NDVI_PASTURA'] - 0.1: t, b = 'VEGETACION_ESCASA', np.random.uniform(1000, 2000)
        elif ndvi < p['UMBRAL_NDVI_PASTURA']: t, b = 'VEGETACION_MODERADA', np.random.uniform(2000, p['MS_POR_HA_OPTIMO']*0.8)
        else: t, b = 'VEGETACION_DENSA', np.random.uniform(p['MS_POR_HA_OPTIMO']*0.8, p['MS_POR_HA_OPTIMO']*1.2)
        b = max(100, b * (1 + (ndvi - 0.5)*0.5))
        res.append({'id_subLote': r['id_subLote'], 'geometry': r.geometry, 'ndvi': ndvi, 'tipo_superficie': t,
                    'biomasa_kg_ha': b, 'area_ha': area})
    return gpd.GeoDataFrame(res, crs=gdf.crs)

def calcular_ganaderia(gdf, tipo, peso, carga):
    if gdf.empty: return gdf
    p = obtener_parametros(tipo)
    consumo_animal = peso * p['CONSUMO_PORCENTAJE_PESO']
    consumo_total = consumo_animal * carga
    gdf = gdf.copy()
    gdf['biomasa_kg'] = gdf['biomasa_kg_ha'] * gdf['area_ha']
    gdf['ev_total'] = gdf['biomasa_kg'] / consumo_animal
    gdf['ev_ha'] = gdf['ev_total'] / gdf['area_ha']
    gdf['dias'] = (gdf['biomasa_kg'] * p['TASA_UTILIZACION_RECOMENDADA']) / consumo_total
    return gdf

# =============================================================================
# PDF
# =============================================================================
def generar_pdf(gdf, area_total, tipo, mapa1_html, mapa2_html):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Center', alignment=1))
    story = []

    story.append(Paragraph("INFORME FORRAJERO", styles['Title']))
    story.append(Paragraph(f"Fecha: {datetime.now():%d/%m/%Y} | Área: {area_total:.2f} ha | Pastura: {tipo}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    for html, titulo in [(mapa1_html, "MAPA DEL LOTE"), (mapa2_html, "MAPA DE ANÁLISIS")]:
        img = Image(io.BytesIO(folium.Figure().add_child(folium.Element(html))._repr_png_()), 7*inch, 4*inch)
        story.append(Paragraph(titulo, styles['Heading2']))
        story.append(KeepInFrame(7*inch, 4*inch, [img]))
        story.append(PageBreak())

    data = [["Sub", "Tipo", "NDVI", "Biomasa", "EV", "Días"]]
    for _, r in gdf.iterrows():
        data.append([r['id_subLote'], r['tipo_superficie'].title().replace('_', ' '),
                     f"{r['ndvi']:.3f}", f"{r['biomasa_kg_ha']:.0f}",
                     f"{r['ev_total']:.1f}", f"{r['dias']:.1f}"])
    table = Table(data)
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), '#1a9850'),
                               ('TEXTCOLOR',(0,0),(-1,0), colors.white),
                               ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    story.append(Paragraph("DETALLE", styles['Heading2']))
    story.append(table)
    story.append(PageBreak())

    rec = RECOMENDACIONES_REGENERATIVAS.get(tipo, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
    story.append(Paragraph("RECOMENDACIONES REGENERATIVAS", styles['Heading1']))
    for sec, items in rec.items():
        story.append(Paragraph(sec.title().replace('_', ' '), styles['Heading3']))
        for i in items: story.append(Paragraph(f"• {i}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))

    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# SIDEBAR Y MAIN
# =============================================================================
def sidebar():
    with st.sidebar:
        st.header("Configuración")
        base = st.selectbox("Mapa", ["ESRI"], key="base") if FOLIUM_AVAILABLE else "ESRI"
        tipo = st.selectbox("Pastura", ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"], key="tipo")
        fecha = st.date_input("Fecha", datetime.now() - timedelta(30), key="fecha")
        if tipo == "PERSONALIZADO":
            st.session_state.config['ms_optimo'] = st.number_input("MS/ha", 1000, 10000, 4000, key="ms")
            st.session_state.config['tasa_utilizacion'] = st.number_input("Tasa", 0.3, 0.8, 0.55, 0.01, key="tasa")
        peso = st.slider("Peso (kg)", 300, 600, 450, key="peso")
        carga = st.slider("Carga", 50, 1000, 100, key="carga")
        n = st.slider("Sub-lotes", 12, 32, 24, key="n")
        zip_file = st.file_uploader("ZIP shapefile", type='zip', key="zip")
        if st.button("Reiniciar"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        return zip_file, tipo, peso, carga, n, fecha, base

def procesar_zip(zip_file):
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(zip_file) as z: z.extractall(tmp)
            shp = [f for f in os.listdir(tmp) if f.endswith('.shp')][0]
            gdf = gpd.read_file(os.path.join(tmp, shp))
            if gdf.crs is None: gdf.set_crs('EPSG:4326', inplace=True)
            elif gdf.crs != 'EPSG:4326': gdf = gdf.to_crs('EPSG:4326')
            return gdf
        except Exception as e:
            st.error(f"Error: {e}")
            return None

def main():
    zip_file, tipo, peso, carga, n, fecha, base = sidebar()

    if zip_file:
        gdf = procesar_zip(zip_file)
        if gdf is not None:
            area = calcular_superficie(gdf)
            st.session_state.gdf_cargado = gdf
            st.session_state.area_total = area
            st.success(f"Lote cargado: {area:.2f} ha")

            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader("MAPA DEL LOTE")
                m1 = mapa_lote(gdf, base)
                if m1: st_folium(m1, width=700, height=500, key="m1")
            with c2:
                st.metric("Área", f"{area:.2f} ha")
                st.metric("Sub-lotes", n)
                if st.button("EJECUTAR ANÁLISIS", type="primary"):
                    with st.spinner("Analizando..."):
                        gdf_div = dividir_potrero(gdf, n)
                        gdf_sim = simular_satelite(gdf_div, tipo, fecha)
                        gdf_fin = calcular_ganaderia(gdf_sim, tipo, peso, carga)
                        st.session_state.gdf_analizado = gdf_fin
                        st.session_state.analisis_completado = True
                        st.success("¡Listo!")

    if st.session_state.analisis_completado:
        gdf = st.session_state.gdf_analizado
        area = st.session_state.area_total

        c1, c2 = st.columns([3, 1])
        with c1:
            st.subheader("MAPA DE ANÁLISIS")
            m2 = mapa_analisis(gdf, base)
            if m2: st_folium(m2, width=800, height=500, key="m2")
        with c2:
            st.metric("Biomasa", f"{gdf['biomasa_kg_ha'].mean():.0f} kg/ha")
            st.metric("EV Total", f"{gdf['ev_total'].sum():.0f}")
            st.metric("Días", f"{gdf['dias'].mean():.1f}")

        df_disp = gdf[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_kg_ha', 'ev_total', 'dias']].round({'ndvi':3, 'biomasa_kg_ha':0, 'ev_total':1, 'dias':1})
        df_disp['tipo_superficie'] = df_disp['tipo_superficie'].str.title().str.replace('_', ' ')
        df_disp.columns = ['Sub', 'Tipo', 'NDVI', 'Biomasa', 'EV', 'Días']
        st.dataframe(df_disp, use_container_width=True)

        if st.button("GENERAR PDF"):
            with st.spinner("PDF..."):
                m1_html = mapa_lote(st.session_state.gdf_cargado, base)._repr_html_()
                m2_html = mapa_analisis(gdf, base)._repr_html_()
                pdf = generar_pdf(gdf, area, tipo, m1_html, m2_html)
                st.session_state.pdf_buffer = pdf
                st.success("PDF listo")

        if st.session_state.pdf_buffer:
            st.download_button("DESCARGAR PDF", st.session_state.pdf_buffer, "informe.pdf", "application/pdf")

if __name__ == "__main__":
    main()
