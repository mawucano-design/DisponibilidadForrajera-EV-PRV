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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    st.warning("Folium no está disponible. Mapas interactivos limitados.")
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Configuración
st.set_page_config(page_title="Analizador Forrajero GEE", layout="wide")
st.title("ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# === SESSION STATE ===
for key in ['gdf_cargado', 'analisis_completado', 'gdf_analizado', 'area_total', 'pdf_generado', 'pdf_buffer']:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'analisis_completado' else False

# === RECOMENDACIONES ===
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
            "Pastoreo racional Voisin - 4-7 días por potrero",
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

# === SIDEBAR ===
with st.sidebar:
    st.header("Configuración")

    if FOLIUM_AVAILABLE:
        st.subheader("Mapa Base")
        base_map_option = st.selectbox("Seleccionar mapa base:", ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"], index=0)
    else:
        base_map_option = "ESRI Satélite"

    st.subheader("Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox("Seleccionar satélite:", ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"])

    tipo_pastura = st.selectbox("Tipo de Pastura:",
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])

    st.subheader("Configuración Temporal")
    fecha_imagen = st.date_input("Fecha de imagen satelital:", value=datetime.now() - timedelta(days=30), max_value=datetime.now())

    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)

    st.subheader("Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1)

    if tipo_pastura == "PERSONALIZADO":
        st.subheader("Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", 1000, 10000, 4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", 10, 300, 80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", 0.01, 0.05, 0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", 0.3, 0.8, 0.55, step=0.01, format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", 0.05, 0.3, 0.15, step=0.01, format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", 0.3, 0.8, 0.6, step=0.01, format="%.2f")
    else:
        ms_optimo = crecimiento_diario = consumo_porcentaje = tasa_utilizacion = umbral_ndvi_suelo = umbral_ndvi_pastura = None

    st.subheader("Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)

    st.subheader("División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 12, 32, 24)

    st.subheader("Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

    if st.button("Reiniciar Análisis"):
        for key in st.session_state.keys():
            st.session_state[key] = None if key != 'analisis_completado' else False
        st.rerun()

# === PARÁMETROS FORRAJEROS ===
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {'MS_POR_HA_OPTIMO': 5000, 'CRECIMIENTO_DIARIO': 100, 'CONSUMO_PORCENTAJE_PESO': 0.03, 'TASA_UTILIZACION_RECOMENDADA': 0.65, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'RAYGRASS': {'MS_POR_HA_OPTIMO': 4500, 'CRECIMIENTO_DIARIO': 90, 'CONSUMO_PORCENTAJE_PESO': 0.028, 'TASA_UTILIZACION_RECOMENDADA': 0.60, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'FESTUCA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.025, 'TASA_UTILIZACION_RECOMENDADA': 0.55, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'AGROPIRRO': {'MS_POR_HA_OPTIMO': 3500, 'CRECIMIENTO_DIARIO': 60, 'CONSUMO_PORCENTAJE_PESO': 0.022, 'TASA_UTILIZACION_RECOMENDADA': 0.50, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 40, 'CONSUMO_PORCENTAJE_PESO': 0.020, 'TASA_UTILIZACION_RECOMENDADA': 0.45, 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.7},
}

def obtener_parametros_forrajeros(tipo):
    if tipo == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura,
        }
    return PARAMETROS_FORRAJEROS_BASE.get(tipo, PARAMETROS_FORRAJEROS_BASE['ALFALFA'])

# === FUNCIONES ===
def calcular_superficie(gdf):
    if gdf is None or len(gdf) == 0: return 0
    gdf_proj = gdf.to_crs(epsg=3857)
    return gdf_proj.geometry.area.sum() / 10000

def dividir_potrero_en_subLotes(gdf, n_zonas):
    if gdf is None or len(gdf) == 0: return gpd.GeoDataFrame()
    poly = gdf.unary_union
    bounds = poly.bounds
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
            inter = poly.intersection(cell)
            if not inter.is_empty and inter.area > 0:
                sub_poligonos.append(inter)
    return gpd.GeoDataFrame({'id_subLote': range(1, len(sub_poligonos)+1), 'geometry': sub_poligonos}, crs=gdf.crs)

def simular_datos_satelitales(gdf, tipo_pastura, fecha):
    if gdf is None or len(gdf) == 0: return gdf
    params = obtener_parametros_forrajeros(tipo_pastura)
    np.random.seed(hash(str(fecha)) % 10000)
    gdf_out = gdf.copy()
    ndvi = np.clip(np.random.normal(0.5, 0.2, len(gdf_out)) + 0.1 * np.sin(2 * np.pi * fecha.timetuple().tm_yday / 365), 0.05, 0.85)
    areas = [calcular_superficie(gpd.GeoDataFrame([g], crs=gdf.crs)) for g in gdf_out.geometry]
    tipos = []
    biomasas = []
    for n in ndvi:
        if n < params['UMBRAL_NDVI_SUELO']: 
            tipos.append('SUELO_DESNUDO'); biomasas.append(np.random.uniform(100, 500))
        elif n < params['UMBRAL_NDVI_SUELO'] + 0.1: 
            tipos.append('SUELO_PARCIAL'); biomasas.append(np.random.uniform(500, 1000))
        elif n < params['UMBRAL_NDVI_PASTURA'] - 0.1: 
            tipos.append('VEGETACION_ESCASA'); biomasas.append(np.random.uniform(1000, 2000))
        elif n < params['UMBRAL_NDVI_PASTURA']: 
            tipos.append('VEGETACION_MODERADA'); biomasas.append(np.random.uniform(2000, params['MS_POR_HA_OPTIMO'] * 0.8))
        else: 
            tipos.append('VEGETACION_DENSA'); biomasas.append(np.random.uniform(params['MS_POR_HA_OPTIMO'] * 0.8, params['MS_POR_HA_OPTIMO'] * 1.2))
    gdf_out['ndvi'] = ndvi
    gdf_out['tipo_superficie'] = tipos
    gdf_out['biomasa_disponible_kg_ms_ha'] = [max(100, b * (1 + (n-0.5)*0.5)) for b, n in zip(biomasas, ndvi)]
    gdf_out['area_ha'] = areas
    return gdf_out

def calcular_metricas_ganaderas(gdf, tipo, peso, carga):
    if gdf is None: return gdf
    params = obtener_parametros_forrajeros(tipo)
    consumo_diario = peso * params['CONSUMO_PORCENTAJE_PESO'] * carga
    gdf = gdf.copy()
    biomasa_kg = gdf['biomasa_disponible_kg_ms_ha'] * gdf['area_ha']
    gdf['ev_ha'] = biomasa_kg / (peso * params['CONSUMO_PORCENTAJE_PESO'])
    gdf['dias_permanencia'] = (biomasa_kg * params['TASA_UTILIZACION_RECOMENDADA']) / consumo_diario
    gdf['biomasa_disponible_kg'] = biomasa_kg
    return gdf

def generar_informe_pdf(gdf, tipo, peso, carga, area, fecha, fuente):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=inch)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("INFORME FORRAJERO", styles['Title']))
    story.append(Spacer(1, 20))
    info = [["Pastura:", tipo], ["Área:", f"{area:.2f} ha"], ["Peso:", f"{peso} kg"], ["Carga:", f"{carga} cabezas"]]
    story.append(Table(info))
    story.append(PageBreak())
    story.append(Paragraph("DETALLE", styles['Heading2']))
    data = [["ID", "Tipo", "NDVI", "Biomasa", "EV/Ha", "Días"]]
    for _, r in gdf.iterrows():
        data.append([str(r['id_subLote']), r['tipo_superficie'], f"{r['ndvi']:.3f}", f"{r['biomasa_disponible_kg_ms_ha']:.0f}", f"{r['ev_ha']:.1f}", f"{r['dias_permanencia']:.1f}"])
    story.append(Table(data))
    doc.build(story)
    buffer.seek(0)
    return buffer

# === MAIN ===
def main():
    if uploaded_zip:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with zipfile.ZipFile(uploaded_zip, 'r') as z:
                    z.extractall(tmp)
                shp = next(f for f in os.listdir(tmp) if f.endswith('.shp'))
                gdf = gpd.read_file(os.path.join(tmp, shp))
                gdf = gdf.to_crs('EPSG:4326') if gdf.crs != 'EPSG:4326' else gdf
                st.session_state.gdf_cargado = gdf
                st.session_state.area_total = calcular_superficie(gdf)
                st.success(f"Shapefile cargado - Área: {st.session_state.area_total:.2f} ha")

                if st.button("Ejecutar Análisis", type="primary"):
                    with st.spinner("Analizando..."):
                        gdf_div = dividir_potrero_en_subLotes(gdf, n_divisiones)
                        gdf_sim = simular_datos_satelitales(gdf_div, tipo_pastura, fecha_imagen)
                        gdf_final = calcular_metricas_ganaderas(gdf_sim, tipo_pastura, peso_promedio, carga_animal)
                        st.session_state.gdf_analizado = gdf_final
                        st.session_state.analisis_completado = True
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.analisis_completado and st.session_state.gdf_analizado is not None:
        gdf = st.session_state.gdf_analizado
        area = st.session_state.area_total
        st.header("Resultados")
        st.metric("Biomasa Promedio", f"{gdf['biomasa_disponible_kg_ms_ha'].mean():.0f} kg MS/ha")
        st.dataframe(gdf[['id_subLote', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']])

        if st.button("Generar PDF"):
            with st.spinner("Generando PDF..."):
                pdf = generar_informe_pdf(gdf, tipo_pastura, peso_promedio, carga_animal, area, fecha_imagen, fuente_satelital)
                st.session_state.pdf_buffer = pdf
                st.session_state.pdf_generado = True
            st.rerun()

        if st.session_state.pdf_generado:
            st.download_button("Descargar PDF", st.session_state.pdf_buffer, f"informe_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")

if __name__ == "__main__":
    main()
