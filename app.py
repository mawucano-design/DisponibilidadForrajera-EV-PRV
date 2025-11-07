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
        'ms_optimo': 4000,
        'crecimiento_diario': 80,
        'consumo_porcentaje': 0.025,
        'tasa_utilizacion': 0.55,
        'umbral_ndvi_suelo': 0.15,
        'umbral_ndvi_pastura': 0.6
    }

# === DATOS BASE ===
RECOMENDACIONES_REGENERATIVAS = {
    'ALFALFA': {
        'PRÁCTICAS_REGENERATIVAS': ["Sistema PRV 1-3 días", "Leguminosas nativas", "Biofertilizantes", "Bancos de proteína"],
        'MANEJO_SUELO': ["Compost 2-3 ton/ha", "Harinas de rocas", "Micorrizas", "Coberturas vivas"],
        'BIODIVERSIDAD': ["Corredores biológicos", "Cercas vivas", "Rotación con cultivos", "Control biológico"],
        'AGUA_RETENCIÓN': ["Swales", "Keyline", "Mulching", "Riego por goteo"]
    },
    'RAYGRASS': {
        'PRÁCTICAS_REGENERATIVAS': ["Pastoreo ultra rápido", "Descansos 45-60 días", "Trébol blanco/rojo", "Gallinas post-pastoreo"],
        'MANEJO_SUELO': ["Té de compost", "Fosfatos naturales", "Bacterias fijadoras", "Aporques"],
        'BIODIVERSIDAD': ["Chicoria + plantago", "Bordes aromáticos", "Avena forrajera", "Altura 8-10 cm"],
        'AGUA_RETENCIÓN': ["Microrepresas", "Bebederos móviles", "Árboles nativos", "Cobertura permanente"]
    },
    'FESTUCA': {
        'PRÁCTICAS_REGENERATIVAS': ["Pastoreo Voisin 4-7 días", "Integración avícola", "Árboles forrajeros", "Silvopastoriles"],
        'MANEJO_SUELO': ["Bokashi", "Carbonatos", "Trichoderma", "Labranza cero"],
        'BIODIVERSIDAD': ["Pastos nativos", "Gliricidia", "Kikuyo", "Control mecánico"],
        'AGUA_RETENCIÓN': ["Terrazas", "Aspersión eficiente", "Barreras vivas", "Mulching"]
    },
    'AGROPIRRO': {
        'PRÁCTICAS_REGENERATIVAS': ["Pastoreo de precisión", "Integración porcina", "Abonos verdes", "Agrosilvopastoriles"],
        'MANEJO_SUELO': ["Humus lombriz", "Yeso agrícola", "Azospirillum", "Coberturas muertas"],
        'BIODIVERSIDAD': ["Brachiaria", "Plantas repelentes", "Sorgo forrajero", "Microclimas"],
        'AGUA_RETENCIÓN': ["Zanjas", "Sub-riego", "Curvas a nivel", "Protección fuentes"]
    },
    'PASTIZAL_NATURAL': {
        'PRÁCTICAS_REGENERATIVAS': ["Pastoreo holístico", "Multipaddock", "Regeneración nativa", "Herbívoros mixtos"],
        'MANEJO_SUELO': ["Microorganismos", "Rocas molidas", "Hongos nativos", "Pioneras"],
        'BIODIVERSIDAD': ["Bancos semilla", "Corredores", "Carga estacional", "Áreas regeneración"],
        'AGUA_RETENCIÓN': ["Restauración quebradas", "Cosecha lluvia", "Escorrentías", "Recarga acuíferos"]
    },
    'PERSONALIZADO': {
        'PRÁCTICAS_REGENERATIVAS': ["Diseño adaptativo", "Monitoreo continuo", "Integración animal", "Planificación holística"],
        'MANEJO_SUELO': ["Análisis específico", "Regeneración local", "Insumos locales", "Topografía"],
        'BIODIVERSIDAD': ["Microclimas", "Paisaje diversificado", "Sucesión", "Germoplasma local"],
        'AGUA_RETENCIÓN': ["Keyline adaptado", "Captación", "Eficiencia hídrica", "Retención específica"]
    }
}

PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {'MS_POR_HA_OPTIMO': 5000, 'CRECIMIENTO_DIARIO': 100, 'CONSUMO_PORCENTAJE_PESO': 0.03, 'DIGESTIBILIDAD': 0.65, 'PROTEINA_CRUDA': 0.18, 'TASA_UTILIZACION_RECOMENDADA': 0.65, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'RAYGRASS': {'MS_POR_HA_OPTIMO': 4500, 'CRECIMIENTO_DIARIO': 90, 'CONSUMO_PORCENTAJE_PESO': 0.028, 'DIGESTIBILIDAD': 0.70, 'PROTEINA_CRUDA': 0.15, 'TASA_UTILIZACION_RECOMENDADA': 0.60, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'FESTUCA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.025, 'DIGESTIBILIDAD': 0.60, 'PROTEINA_CRUDA': 0.12, 'TASA_UTILIZACION_RECOMENDADA': 0.55, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'AGROPIRRO': {'MS_POR_HA_OPTIMO': 3500, 'CREC 60, 'CONSUMO_PORCENTAJE_PESO': 0.022, 'DIGESTIBILIDAD': 0.55, 'PROTEINA_CRUDA': 0.10, 'TASA_UTILIZACION_RECOMENDADA': 0.50, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 40, 'CONSUMO_PORCENTAJE_PESO': 0.020, 'DIGESTIBILIDAD': 0.50, 'PROTEINA_CRUDA': 0.08, 'TASA_UTILIZACION_RECOMENDADA': 0.45, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.7},
}

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def obtener_parametros(tipo):
    if tipo == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': st.session_state.config['ms_optimo'],
            'CRECIMIENTO_DIARIO': st.session_state.config['crecimiento_diario'],
            'CONSUMO_PORCENTAJE_PESO': st.session_state.config['consumo_porcentaje'],
            'DIGESTIBILIDAD': 0.60,
            'PROTEINA_CRUDA': 0.12,
            'TASA_UTILIZACION_RECOMENDADA': st.session_state.config['tasa_utilizacion'],
            'UMBRAL_NDVI_SUELO': st.session_state.config['umbral_ndvi_suelo'],
            'UMBRAL_NDVI_PASTURA': st.session_state.config['umbral_ndvi_pastura'],
        }
    return PARAMETROS_FORRAJEROS_BASE[tipo]

def calcular_superficie(gdf):
    if gdf is None or len(gdf) == 0:
        return 0.0
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')
            return gdf_proj.geometry.area.sum() / 10000
        return gdf.geometry.area.sum() / 10000
    except:
        return gdf.geometry.area.sum() / 10000

def area_individual(row, crs):
    temp_gdf = gpd.GeoDataFrame([row], crs=crs)
    return calcular_superficie(temp_gdf)

def dividir_potrero(gdf, n_zonas):
    if gdf is None or len(gdf) == 0:
        return gdf
    poly = gdf.iloc[0].geometry
    b = poly.bounds
    cols = math.ceil(math.sqrt(n_zonas))
    rows = math.ceil(n_zonas / cols)
    w, h = (b[2]-b[0])/cols, (b[3]-b[1])/rows
    subs = []
    for i in range(rows):
        for j in range(cols):
            if len(subs) >= n_zonas: break
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
    BASE_MAPS = {
        "ESRI Satélite": {"tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', "attr": 'Esri'}
    }

    def crear_mapa_lote(gdf):
        if gdf is None or len(gdf) == 0: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS["ESRI Satélite"], overlay=True).add_to(m)
        folium.GeoJson(gdf, style_function=lambda x: {'fillColor': '#3388ff', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.3}).add_to(m)
        m.fit_bounds([sw, ne])
        return m

    def crear_mapa_analisis(gdf):
        if gdf is None or len(gdf) == 0: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS["ESRI Satélite"], overlay=True).add_to(m)
        colores = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 'VEGETACION_ESCASA': '#fee08b',
                   'VEGETACION_MODERADA': '#a6d96a', 'VEGETACION_DENSA': '#1a9850'}
        def estilo(f):
            t = f['properties']['tipo_superficie']
            return {'fillColor': colores.get(t, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.7}
        folium.GeoJson(gdf, style_function=estilo,
                       tooltip=folium.GeoJsonTooltip(['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_kg_ha', 'ev_total'],
                                                    aliases=['Sub:', 'Tipo:', 'NDVI:', 'Biomasa:', 'EV:'])).add_to(m)
        m.fit_bounds([sw, ne])
        return m
else:
    def crear_mapa_lote(gdf): return None
    def crear_mapa_analisis(gdf): return None

# =============================================================================
# SIMULACIÓN Y CÁLCULOS
# =============================================================================
def simular_satelite(gdf, tipo, fecha):
    if gdf is None or len(gdf) == 0: return gdf
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
    if gdf is None or len(gdf) == 0: return gdf
    p = obtener_parametros(tipo)
    consumo_animal = peso * p['CONSUMO_PORCENTAJE_PESO']
    consumo_total = consumo_animal * carga
    gdf = gdf.copy()
    gdf['biomasa_kg'] = gdf['biomasa_kg_ha'] * gdf['area_ha']
    gdf['ev_total'] = gdf['biomasa_kg'] / consumo_animal
    gdf['ev_ha'] = gdf['ev_total'] / gdf['area_ha']
    gdf['dias_permanencia'] = (gdf['biomasa_kg'] * p['TASA_UTILIZACION_RECOMENDADA']) / consumo_total
    return gdf

# =============================================================================
# PDF
# =============================================================================
def generar_pdf(gdf, area_total, tipo, mapa_lote_html, mapa_analisis_html):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("INFORME FORRAJERO", styles['Title']))
    story.append(Paragraph(f"Fecha: {datetime.now():%d/%m/%Y} | Área: {area_total:.2f} ha | Pastura: {tipo}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    for html, titulo in [(mapa_lote_html, "MAPA DEL LOTE"), (mapa_analisis_html, "MAPA DE ANÁLISIS")]:
        img_data = folium.Figure().add_child(folium.Element(html))._repr_png_()
        img = Image(io.BytesIO(img_data), 7*inch, 4*inch)
        story.append(Paragraph(titulo, styles['Heading2']))
        story.append(KeepInFrame(7*inch, 4*inch, [img]))
        story.append(PageBreak())

    data = [["Sub-Lote", "Tipo", "NDVI", "Biomasa (kg/ha)", "EV Total", "Días"]]
    for _, r in gdf.iterrows():
        data.append([r['id_subLote'], r['tipo_superficie'].replace('_', ' ').title(),
                     f"{r['ndvi']:.3f}", f"{r['biomasa_kg_ha']:.0f}",
                     f"{r['ev_total']:.1f}", f"{r['dias_permanencia']:.1f}"])
    table = Table(data)
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), '#1a9850'), ('TEXTCOLOR',(0,0),(-1,0), colors.white), ('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    story.append(Paragraph("DETALLE POR SUB-LOTE", styles['Heading2']))
    story.append(table)
    story.append(PageBreak())

    rec = RECOMENDACIONES_REGENERATIVAS.get(tipo, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
    story.append(Paragraph("RECOMENDACIONES REGENERATIVAS", styles['Heading1']))
    for sec, items in rec.items():
        story.append(Paragraph(sec.replace('_', ' ').title(), styles['Heading3']))
        for i in items: story.append(Paragraph(f"• {i}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))

    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# SIDEBAR
# =============================================================================
def sidebar():
    with st.sidebar:
        st.header("Configuración")
        tipo = st.selectbox("Tipo de Pastura", ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"], key="tipo")
        fecha = st.date_input("Fecha imagen", datetime.now() - timedelta(30), key="fecha")

        if tipo == "PERSONALIZADO":
            st.subheader("Parámetros Personalizados")
            st.session_state.config['ms_optimo'] = st.number_input("MS Óptima (kg/ha)", 1000, 10000, 4000, key="ms")
            st.session_state.config['crecimiento_diario'] = st.number_input("Crecimiento (kg/ha/día)", 10, 300, 80, key="crec")
            st.session_state.config['consumo_porcentaje'] = st.number_input("Consumo (% peso)", 0.01, 0.05, 0.025, 0.001, key="cons")
            st.session_state.config['tasa_utilizacion'] = st.number_input("Tasa Utilización", 0.3, 0.8, 0.55, 0.01, key="tasa")
            st.session_state.config['umbral_ndvi_suelo'] = st.number_input("NDVI Mínimo (suelo)", 0.05, 0.3, 0.15, 0.01, key="ndvi_min")
            st.session_state.config['umbral_ndvi_pastura'] = st.number_input("NDVI Máximo (pastura)", 0.3, 0.8, 0.6, 0.01, key="ndvi_max")

        peso = st.slider("Peso animal (kg)", 300, 600, 450, key="peso")
        carga = st.slider("Carga animal", 50, 1000, 100, key="carga")
        n_sublotes = st.slider("Sub-lotes", 12, 32, 24, key="sublotes")
        zip_file = st.file_uploader("ZIP con shapefile", type='zip', key="zip")

        if st.button("Reiniciar"):
            for k in list(st.session_state.keys()):
                if k != 'config': del st.session_state[k]
            st.rerun()

        return zip_file, tipo, peso, carga, n_sublotes, fecha

# =============================================================================
# MAIN
# =============================================================================
def main():
    zip_file, tipo, peso, carga, n_sublotes, fecha = sidebar()

    if zip_file:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with zipfile.ZipFile(zip_file) as z: z.extractall(tmp)
                shp = [f for f in os.listdir(tmp) if f.endswith('.shp')][0]
                gdf = gpd.read_file(os.path.join(tmp, shp))
                if gdf.crs is None: gdf.set_crs('EPSG:4326', inplace=True)
                elif gdf.crs != 'EPSG:4326': gdf = gdf.to_crs('EPSG:4326')
                area = calcular_superficie(gdf)
                st.session_state.gdf_cargado = gdf
                st.session_state.area_total = area
                st.success(f"Lote cargado: {area:.2f} ha")

                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader("MAPA DEL LOTE")
                    m = crear_mapa_lote(gdf)
                    if m: st_folium(m, width=700, height=500, key="mapa_lote")
                with c2:
                    st.metric("Área", f"{area:.2f} ha")
                    st.metric("Sub-lotes", n_sublotes)
                    if st.button("EJECUTAR ANÁLISIS", type="primary"):
                        with st.spinner("Analizando..."):
                            gdf_div = dividir_potrero(gdf, n_sublotes)
                            gdf_sim = simular_satelite(gdf_div, tipo, fecha)
                            gdf_fin = calcular_ganaderia(gdf_sim, tipo, peso, carga)
                            st.session_state.gdf_analizado = gdf_fin
                            st.session_state.analisis_completado = True
                            st.success("¡Análisis completado!")

            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        gdf = st.session_state.gdf_analizado
        area = st.session_state.area_total

        c1, c2 = st.columns([3, 1])
        with c1:
            st.subheader("MAPA DE ANÁLISIS")
            m2 = crear_mapa_analisis(gdf)
            if m2: st_folium(m2, width=800, height=500, key="mapa_analisis")
        with c2:
            st.metric("Biomasa Promedio", f"{gdf['biomasa_kg_ha'].mean():.0f} kg/ha")
            st.metric("EV Total", f"{gdf['ev_total'].sum():.0f}")
            st.metric("Días Promedio", f"{gdf['dias_permanencia'].mean():.1f}")

        df_disp = gdf[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_kg_ha', 'ev_total', 'dias_permanencia']].copy()
        df_disp['tipo_superficie'] = df_disp['tipo_superficie'].str.title().str.replace('_', ' ')
        df_disp = df_disp.round({'ndvi':3, 'biomasa_kg_ha':0, 'ev_total':1, 'dias_permanencia':1})
        df_disp.columns = ['Sub-Lote', 'Tipo', 'NDVI', 'Biomasa', 'EV Total', 'Días']
        st.dataframe(df_disp, use_container_width=True)

        if st.button("GENERAR PDF"):
            with st.spinner("Creando PDF..."):
                m1_html = crear_mapa_lote(st.session_state.gdf_cargado)._repr_html_()
                m2_html = crear_mapa_analisis(gdf)._repr_html_()
                pdf = generar_pdf(gdf, area, tipo, m1_html, m2_html)
                st.session_state.pdf_buffer = pdf
                st.success("PDF listo")

        if st.session_state.pdf_buffer:
            st.download_button("DESCARGAR INFORME PDF", st.session_state.pdf_buffer, "informe_forrajero.pdf", "application/pdf")

if __name__ == "__main__":
    main()
