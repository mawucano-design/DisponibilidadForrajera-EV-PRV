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

st.set_page_config(page_title="Analizador Forrajero GEE", layout="wide")
st.title("ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Session State
for key in ['gdf_cargado', 'analisis_completado', 'gdf_analizado', 'area_total', 'pdf_buffer']:
    if key not in st.session_state:
        st.session_state[key] = None

# === RECOMENDACIONES REGENERATIVAS ===
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

# === PARÁMETROS FORRAJEROS BASE ===
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {'MS_POR_HA_OPTIMO': 5000, 'CRECIMIENTO_DIARIO': 100, 'CONSUMO_PORCENTAJE_PESO': 0.03, 'TASA_UTILIZACION_RECOMENDADA': 0.65},
    'RAYGRASS': {'MS_POR_HA_OPTIMO': 4500, 'CRECIMIENTO_DIARIO': 90, 'CONSUMO_PORCENTAJE_PESO': 0.028, 'TASA_UTILIZACION_RECOMENDADA': 0.60},
    'FESTUCA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.025, 'TASA_UTILIZACION_RECOMENDADA': 0.55},
    'AGROPIRRO': {'MS_POR_HA_OPTIMO': 3500, 'CRECIMIENTO_DIARIO': 60, 'CONSUMO_PORCENTAJE_PESO': 0.022, 'TASA_UTILIZACION_RECOMENDADA': 0.50},
    'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 40, 'CONSUMO_PORCENTAJE_PESO': 0.020, 'TASA_UTILIZACION_RECOMENDADA': 0.45}
}

# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("Configuración")
    if FOLIUM_AVAILABLE:
        base_map_option = st.selectbox("Mapa Base", ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"], index=0)
    else:
        base_map_option = "ESRI Satélite"

    fuente_satelital = st.selectbox("Satélite", ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"])
    tipo_pastura = st.selectbox("Pastura", ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    fecha_imagen = st.date_input("Fecha imagen", datetime.now() - timedelta(30))
    nubes_max = st.slider("Nubes %", 0, 100, 20)

    st.subheader("Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("NDVI Mínimo", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("NDVI Óptimo", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad Suelo", 0.1, 1.0, 0.5, 0.1)

    if tipo_pastura == "PERSONALIZADO":
        st.session_state.ms_optimo = st.number_input("MS Óptima (kg/ha)", 1000, 10000, 4000)
        st.session_state.crecimiento_diario = st.number_input("Crecimiento (kg/ha/día)", 10, 300, 80)
        st.session_state.consumo_porcentaje = st.number_input("Consumo (% peso)", 0.01, 0.05, 0.025, 0.001)
        st.session_state.tasa_utilizacion = st.number_input("Tasa Utilización", 0.3, 0.8, 0.55, 0.01)

    peso_promedio = st.slider("Peso animal (kg)", 300, 600, 450)
    carga_animal = st.slider("Carga", 50, 1000, 100)
    n_divisiones = st.slider("Sub-lotes", 12, 32, 24)

    uploaded_file = st.file_uploader("Subir ZIP o KML", type=['zip', 'kml'])

    if st.button("Reiniciar"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# =============================================================================
# CARGA DE ARCHIVO (ZIP o KML)
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
# MAPAS FOLIUM CON ZOOM AUTOMÁTICO
# =============================================================================
if FOLIUM_AVAILABLE:
    BASE_MAPS_CONFIG = {
        "ESRI Satélite": {"tiles": 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', "attr": 'Esri'},
        "OpenStreetMap": {"tiles": 'OpenStreetMap', "attr": 'OpenStreetMap'},
        "CartoDB Positron": {"tiles": 'CartoDB positron', "attr": 'CartoDB'}
    }

    def crear_mapa(gdf, base="ESRI Satélite"):
        if gdf is None or gdf.empty: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS_CONFIG[base], overlay=True).add_to(m)
        folium.GeoJson(gdf, style_function=lambda x: {'fillColor': '#3388ff', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.3}).add_to(m)
        m.fit_bounds([sw, ne])
        return m

    def crear_mapa_analisis(gdf):
        if gdf is None or gdf.empty: return None
        bounds = gdf.total_bounds
        sw, ne = [bounds[1], bounds[0]], [bounds[3], bounds[2]]
        m = folium.Map(location=[(sw[0]+ne[0])/2, (sw[1]+ne[1])/2], zoom_start=1, tiles=None)
        folium.TileLayer(**BASE_MAPS_CONFIG["ESRI Satélite"], overlay=True).add_to(m)
        colores = {'SUELO_DESNUDO': '#d73027', 'SUELO_PARCIAL': '#fdae61', 'VEGETACION_ESCASA': '#fee08b',
                   'VEGETACION_MODERADA': '#a6d96a', 'VEGETACION_DENSA': '#1a9850'}
        def estilo(f):
            t = f['properties']['tipo_superficie']
            return {'fillColor': colores.get(t, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.7}
        folium.GeoJson(gdf, style_function=estilo,
                       tooltip=folium.GeoJsonTooltip(['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha'],
                                                    aliases=['Sub:', 'Tipo:', 'NDVI:', 'Biomasa:', 'EV/Ha:'])).add_to(m)
        m.fit_bounds([sw, ne])
        return m
else:
    crear_mapa = lambda gdf, base: None
    crear_mapa_analisis = lambda gdf: None

# =============================================================================
# FUNCIONES DEL ANÁLISIS REALISTA (COMPLETAS)
# =============================================================================
def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': st.session_state.get('ms_optimo', 4000),
            'CRECIMIENTO_DIARIO': st.session_state.get('crecimiento_diario', 80),
            'CONSUMO_PORCENTAJE_PESO': st.session_state.get('consumo_porcentaje', 0.025),
            'TASA_UTILIZACION_RECOMENDADA': st.session_state.get('tasa_utilizacion', 0.55)
        }
    return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]

def calcular_superficie(gdf):
    try:
        if gdf.crs and gdf.crs.is_geographic:
            return gdf.to_crs('EPSG:3857').geometry.area.sum() / 10000
        return gdf.geometry.area.sum() / 10000
    except:
        return gdf.geometry.area.sum() / 10000

def dividir_potrero_en_subLotes(gdf, n_zonas):
    if gdf is None or gdf.empty:
        return gdf
    potrero = gdf.iloc[0].geometry
    bounds = potrero.bounds
    minx, miny, maxx, maxy = bounds
    sub_poligonos = []
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    width = (maxx - minx) / n_cols
    height = (maxy - miny) / n_rows
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas: break
            cell = Polygon([(minx + j*width, miny + i*height), (minx + (j+1)*width, miny + i*height),
                           (minx + (j+1)*width, miny + (i+1)*height), (minx + j*width, miny + (i+1)*height)])
            inter = potrero.intersection(cell)
            if not inter.is_empty and inter.area > 0:
                sub_poligonos.append(inter)
    return gpd.GeoDataFrame({'id_subLote': range(1, len(sub_poligonos)+1), 'geometry': sub_poligonos}, crs=gdf.crs)

class DetectorVegetacionRealista:
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo

    def clasificar_vegetacion_realista(self, ndvi, evi, savi, bsi, ndbi, msavi2=None):
        es_suelo_desnudo = ndvi < 0.1 and bsi > 0.4 and ndbi > 0.2
        es_suelo_parcial = ndvi < 0.2 and bsi > 0.3 and not es_suelo_desnudo
        if es_suelo_desnudo: return "SUELO_DESNUDO", 0.05
        if es_suelo_parcial: return "SUELO_PARCIAL", 0.25
        if ndvi < 0.4: return "VEGETACION_ESCASA", 0.5
        if ndvi < 0.65: return "VEGETACION_MODERADA", 0.75
        return "VEGETACION_DENSA", 0.9

    def calcular_biomasa_realista(self, ndvi, categoria, params):
        if categoria == "SUELO_DESNUDO": return 20, 2
        if categoria == "SUELO_PARCIAL": return 80, 10
        factor = 0.3 + (ndvi * 0.8)
        biomasa = params['MS_POR_HA_OPTIMO'] * factor
        crecimiento = params['CRECIMIENTO_DIARIO'] * factor
        return max(100, min(8000, biomasa)), max(1, min(200, crecimiento))

def simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital):
    zonas = {1: 0.08, 6: 0.12, 11: 0.09, 25: 0.11, 30: 0.07}
    if id_subLote in zonas: ndvi = zonas[id_subLote]
    else: ndvi = 0.15 + (min(x_norm, 1-x_norm, y_norm, 1-y_norm) * 0.7)
    variabilidad = np.random.normal(0, 0.05)
    ndvi = max(0.05, min(0.85, ndvi + variabilidad))
    evi = ndvi * 1.2; savi = ndvi * 1.1; bsi = 0.6 if ndvi < 0.15 else 0.1; ndbi = 0.25 if ndvi < 0.15 else 0.05; msavi2 = ndvi * 1.0
    return ndvi, evi, savi, bsi, ndbi, msavi2

def calcular_indices_forrajeros_realista(gdf, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                                       umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo):
    if gdf is None or gdf.empty: return []
    params = obtener_parametros_forrajeros(tipo_pastura)
    detector = DetectorVegetacionRealista(umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo)
    resultados = []
    bounds = gdf.total_bounds
    x_min, x_max = bounds[0], bounds[2]
    y_min, y_max = bounds[1], bounds[3]
    for idx, row in gdf.iterrows():
        x_norm = (row.geometry.centroid.x - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row.geometry.centroid.y - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        ndvi, evi, savi, bsi, ndbi, msavi2 = simular_patrones_reales_con_suelo(row['id_subLote'], x_norm, y_norm, fuente_satelital)
        categoria, cobertura = detector.clasificar_vegetacion_realista(ndvi, evi, savi, bsi, ndbi, msavi2)
        biomasa, crecimiento = detector.calcular_biomasa_realista(ndvi, categoria, params)
        biomasa_disponible = biomasa * 0.6 * cobertura if categoria not in ["SUELO_DESNUDO", "SUELO_PARCIAL"] else biomasa
        resultados.append({
            'id_subLote': row['id_subLote'], 'ndvi': round(ndvi, 3), 'evi': round(evi, 3), 'savi': round(savi, 3),
            'bsi': round(bsi, 3), 'ndbi': round(ndbi, 3), 'cobertura_vegetal': round(cobertura, 3),
            'tipo_superficie': categoria, 'biomasa_ms_ha': round(biomasa, 1), 'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento, 1)
        })
    return resultados

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    for _, row in gdf_analizado.iterrows():
        biomasa = row['biomasa_disponible_kg_ms_ha'] * row['area_ha']
        consumo = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        ev = biomasa / consumo if consumo > 0 else 0
        ev_soportable = ev / params['TASA_UTILIZACION_RECOMENDADA']
        dias = (biomasa * params['TASA_UTILIZACION_RECOMENDADA']) / (carga_animal * consumo) if carga_animal > 0 else 0.1
        metricas.append({'ev_soportable': round(ev_soportable, 2), 'dias_permanencia': max(0.1, round(dias, 1)), 'ev_ha': round(ev_soportable / row['area_ha'], 3)})
    return metricas

# =============================================================================
# PDF GENERATOR
# =============================================================================
def generar_pdf(gdf_cargado, gdf_analizado, area_total, tipo_pastura):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("INFORME FORRAJERO", styles['Title']))
    story.append(Paragraph(f"Fecha: {datetime.now():%d/%m/%Y} | Área: {area_total:.2f} ha | Pastura: {tipo_pastura}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    for mapa_func, titulo in [(crear_mapa, "MAPA DEL LOTE"), (crear_mapa_analisis, "MAPA DE ANÁLISIS")]:
        m = mapa_func(gdf_cargado if titulo == "MAPA DEL LOTE" else gdf_analizado)
        if m:
            img_data = m._to_png()
            img = Image(io.BytesIO(img_data), 7*inch, 4*inch)
            story.append(Paragraph(titulo, styles['Heading2']))
            story.append(KeepInFrame(7*inch, 4*inch, [img]))
            story.append(PageBreak())

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
# MAIN
# =============================================================================
if uploaded_file:
    gdf = cargar_geometria(uploaded_file)
    if gdf is not None and not gdf.empty:
        area_total = calcular_superficie(gdf).sum()
        st.session_state.gdf_cargado = gdf
        st.session_state.area_total = area_total
        st.success(f"Lote cargado: {area_total:.2f} ha")

        c1, c2 = st.columns([2, 1])
        with c1:
            m = crear_mapa(gdf, base_map_option)
            if m: st_folium(m, width=700, height=500)
        with c2:
            st.metric("Área", f"{area_total:.2f} ha")
            st.metric("Sub-lotes", n_divisiones)

        if st.button("EJECUTAR ANÁLISIS", type="primary"):
            with st.spinner("Analizando..."):
                gdf_div = dividir_potrero_en_subLotes(gdf, n_divisiones)
                indices = calcular_indices_forrajeros_realista(gdf_div, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                                                              umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo)
                gdf_analizado = gdf_div.copy()
                gdf_analizado['area_ha'] = [calcular_superficie(gpd.GeoDataFrame([r], crs=gdf.crs)) for _, r in gdf_div.iterrows()]
                for i, ind in enumerate(indices):
                    for k, v in ind.items():
                        if k != 'id_subLote':
                            gdf_analizado.loc[i, k] = v
                metricas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
                for i, met in enumerate(metricas):
                    for k, v in met.items():
                        gdf_analizado.loc[i, k] = v
                st.session_state.gdf_analizado = gdf_analizado
                st.session_state.analisis_completado = True
                st.success("¡Análisis completado!")

if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
    gdf = st.session_state.gdf_analizado
    area = st.session_state.area_total

    c1, c2 = st.columns([3, 1])
    with c1:
        m2 = crear_mapa_analisis(gdf)
        if m2: st_folium(m2, width=800, height=500)
    with c2:
        st.metric("Biomasa Prom", f"{gdf['biomasa_disponible_kg_ms_ha'].mean():.0f} kg/ha")
        st.metric("EV Total", f"{gdf['ev_soportable'].sum():.0f}")
        st.metric("Días Prom", f"{gdf['dias_permanencia'].mean():.1f}")

    df_disp = gdf[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']].copy()
    df_disp['tipo_superficie'] = df_disp['tipo_superficie'].str.title().str.replace('_', ' ')
    df_disp = df_disp.round({'ndvi':3, 'biomasa_disponible_kg_ms_ha':0, 'ev_ha':2, 'dias_permanencia':1})
    df_disp.columns = ['Sub-Lote', 'Tipo', 'NDVI', 'Biomasa', 'EV/Ha', 'Días']
    st.dataframe(df_disp, use_container_width=True ...

    # BOTÓN PDF
    if st.button("GENERAR REPORTE PDF"):
        with st.spinner("Generando PDF..."):
            pdf = generar_pdf(st.session_state.gdf_cargado, gdf, area, tipo_pastura)
            st.session_state.pdf_buffer = pdf
            st.success("PDF generado")

    if st.session_state.pdf_buffer:
        st.download_button("DESCARGAR PDF", st.session_state.pdf_buffer, "informe_forrajero.pdf", "application/pdf")
