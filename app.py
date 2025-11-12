# app.py
# Versión: HTML->PDF con fallback a HTML y DOCX
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
import base64
import shutil

# PDF HTML -> PDF
try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except Exception:
    PDFKIT_AVAILABLE = False

# DOCX fallback
try:
    from docx import Document
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# Folium (opcional)
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False
    folium = None
    st_folium = None

# Configuración general de Streamlit
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN REALISTA DE VEGETACIÓN")
st.markdown("---")
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Parámetros por defecto (se actualizan si el usuario elige 'PERSONALIZADO')
ms_optimo = 4000
crecimiento_diario = 80
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.15
umbral_ndvi_pastura = 0.6

# Session state inicial
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'gdf_analizado' not in st.session_state:
    st.session_state.gdf_analizado = None
if 'mapa_detallado_bytes' not in st.session_state:
    st.session_state.mapa_detallado_bytes = None
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None
if 'html_informe' not in st.session_state:
    st.session_state.html_informe = None

# -----------------------
# SIDEBAR (CONFIGURACIÓN)
# -----------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
            index=0
        )
    else:
        base_map_option = "ESRI Satélite"

    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
    )

    tipo_pastura = st.selectbox("Tipo de Pastura:",
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])

    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)

    st.subheader("🌿 Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1)

    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=10000, value=4000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=300, value=80)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05,
                                            value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01,
                                          format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.05, max_value=0.3, value=0.15, step=0.01,
                                            format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.3, max_value=0.8, value=0.6, step=0.01,
                                              format="%.2f")

    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)

    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)

    st.subheader("📤 Subir Lote")
    tipo_archivo = st.radio(
        "Formato del archivo:",
        ["Shapefile (ZIP)", "KML"],
        horizontal=True
    )
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    else:
        uploaded_file = st.file_uploader("Subir archivo KML del potrero", type=['kml'])

# -----------------------
# FUNCIONES DE CARGA
# -----------------------
def cargar_shapefile_desde_zip(uploaded_zip):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                return gdf
            else:
                st.error("❌ No se encontró archivo .shp en el ZIP")
                return None
    except Exception as e:
        st.error(f"❌ Error cargando shapefile: {str(e)}")
        return None

def cargar_kml(uploaded_kml):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.kml') as tmp_file:
            tmp_file.write(uploaded_kml.getvalue())
            tmp_file.flush()
            gdf = gpd.read_file(tmp_file.name, driver='KML')
            os.unlink(tmp_file.name)
            return gdf
    except Exception as e:
        st.error(f"❌ Error cargando KML: {str(e)}")
        return None

# -----------------------
# UTILIDADES FORRAJERAS (resumidas)
# -----------------------
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {'MS_POR_HA_OPTIMO': 5000, 'CRECIMIENTO_DIARIO': 100, 'CONSUMO_PORCENTAJE_PESO': 0.03,
                'TASA_UTILIZACION_RECOMENDADA': 0.65, 'FACTOR_BIOMASA_NDVI': 4500, 'OFFSET_BIOMASA': -1000,
                'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'RAYGRASS': {'MS_POR_HA_OPTIMO': 4500, 'CRECIMIENTO_DIARIO': 90, 'CONSUMO_PORCENTAJE_PESO': 0.028,
                 'TASA_UTILIZACION_RECOMENDADA': 0.60, 'FACTOR_BIOMASA_NDVI': 4200, 'OFFSET_BIOMASA': -900,
                 'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.6},
    'FESTUCA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.025,
                'TASA_UTILIZACION_RECOMENDADA': 0.55, 'FACTOR_BIOMASA_NDVI': 3800, 'OFFSET_BIOMASA': -800,
                'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'AGROPIRRO': {'MS_POR_HA_OPTIMO': 3500, 'CRECIMIENTO_DIARIO': 60, 'CONSUMO_PORCENTAJE_PESO': 0.022,
                  'TASA_UTILIZACION_RECOMENDADA': 0.50, 'FACTOR_BIOMASA_NDVI': 3200, 'OFFSET_BIOMASA': -700,
                  'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.65},
    'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 40, 'CONSUMO_PORCENTAJE_PESO': 0.020,
                         'TASA_UTILIZACION_RECOMENDADA': 0.45, 'FACTOR_BIOMASA_NDVI': 2800, 'OFFSET_BIOMASA': -600,
                         'UMBRAL_NDVI_SUELO': 0.15, 'UMBRAL_NDVI_PASTURA': 0.7}
}

def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'FACTOR_BIOMASA_NDVI': 3500,
            'OFFSET_BIOMASA': -800,
            'UMBRAL_NDVI_SUELO': umbral_ndvi_suelo,
            'UMBRAL_NDVI_PASTURA': umbral_ndvi_pastura
        }
    else:
        return PARAMETROS_FORRAJEROS_BASE.get(tipo_pastura, PARAMETROS_FORRAJEROS_BASE['PASTIZAL_NATURAL'])

def calcular_superficie(gdf):
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except Exception:
        try:
            return gdf.geometry.area / 10000
        except Exception:
            return pd.Series([0]*len(gdf), index=gdf.index)

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

# -----------------------
# DETECCIÓN REALISTA (simplificada)
# -----------------------
class DetectorVegetacionRealista:
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo

    def clasificar_vegetacion_realista(self, ndvi, evi, savi, bsi, ndbi, msavi2=None):
        if ndvi < 0.12:
            categoria = "SUELO_DESNUDO"
            cobertura = 0.05
        elif ndvi < 0.22:
            categoria = "SUELO_PARCIAL"
            cobertura = 0.25
        elif ndvi < 0.4:
            categoria = "VEGETACION_ESCASA"
            cobertura = 0.5
        elif ndvi < 0.65:
            categoria = "VEGETACION_MODERADA"
            cobertura = 0.75
        else:
            categoria = "VEGETACION_DENSA"
            cobertura = 0.9
        return categoria, cobertura

    def calcular_biomasa_realista(self, ndvi, evi, savi, categoria_vegetacion, cobertura, params):
        base = params['MS_POR_HA_OPTIMO']
        if categoria_vegetacion == "SUELO_DESNUDO":
            return 20, 1, 0.2
        if categoria_vegetacion == "SUELO_PARCIAL":
            return min(base * 0.05, 200), params['CRECIMIENTO_DIARIO'] * 0.2, 0.3
        if categoria_vegetacion == "VEGETACION_ESCASA":
            return min(base * 0.3, 1200), params['CRECIMIENTO_DIARIO'] * 0.4, 0.5
        if categoria_vegetacion == "VEGETACION_MODERADA":
            return min(base * 0.6, 3000), params['CRECIMIENTO_DIARIO'] * 0.7, 0.7
        return min(base * 0.9, 6000), params['CRECIMIENTO_DIARIO'] * 0.9, 0.85

# -----------------------
# SIMULACIÓN Y MÉTRICAS
# -----------------------
def simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital):
    base = 0.2 + 0.4 * ((id_subLote % 6) / 6)
    ndvi = max(0.05, min(0.85, base + np.random.normal(0, 0.05)))
    if ndvi < 0.15:
        evi = ndvi * 0.8
        savi = ndvi * 0.9
        bsi = 0.6
        ndbi = 0.25
    elif ndvi < 0.3:
        evi = ndvi * 1.1
        savi = ndvi * 1.05
        bsi = 0.4
        ndbi = 0.15
    elif ndvi < 0.5:
        evi = ndvi * 1.3
        savi = ndvi * 1.2
        bsi = 0.1
        ndbi = 0.05
    else:
        evi = ndvi * 1.4
        savi = ndvi * 1.3
        bsi = -0.1
        ndbi = -0.05
    msavi2 = ndvi * 1.0
    return ndvi, evi, savi, bsi, ndbi, msavi2

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row.get('biomasa_disponible_kg_ms_ha', 0)
        area_ha = row.get('area_ha', 0)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total_disponible = biomasa_disponible * area_ha
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01

        if ev_soportable > 0 and area_ha > 0:
            ev_ha = ev_soportable / area_ha
            ev_ha_display = ev_ha
        else:
            ev_ha_display = 0.01

        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(max(dias_permanencia, 0.1), 10)
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1

        if biomasa_disponible >= 2000:
            estado_forrajero = 4
        elif biomasa_disponible >= 1200:
            estado_forrajero = 3
        elif biomasa_disponible >= 600:
            estado_forrajero = 2
        elif biomasa_disponible >= 200:
            estado_forrajero = 1
        else:
            estado_forrajero = 0

        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'dias_permanencia': round(dias_permanencia, 1),
            'tasa_utilizacion': round(min(1.0, (carga_animal * consumo_individual_kg) / max(1, biomasa_total_disponible)), 3) if biomasa_total_disponible>0 else 0,
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_ha_display, 3)
        })
    return metricas

def calcular_indices_forrajeros_realista(gdf, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max=20,
                                       umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    try:
        resultados = []
        params = obtener_parametros_forrajeros(tipo_pastura)
        detector = DetectorVegetacionRealista(umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo)
        gdf_centroids = gdf.copy()
        gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
        gdf_centroids['x'] = gdf_centroids.centroid.x
        gdf_centroids['y'] = gdf_centroids.centroid.y
        x_coords = gdf_centroids['x'].tolist()
        y_coords = gdf_centroids['y'].tolist()
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        st.info("🔍 Aplicando detección REALISTA que responde a suelo desnudo...")
        for idx, row in gdf_centroids.iterrows():
            id_subLote = row.get('id_subLote', idx+1)
            x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
            y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
            ndvi, evi, savi, bsi, ndbi, msavi2 = simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital)
            categoria_vegetacion, cobertura_vegetal = detector.clasificar_vegetacion_realista(ndvi, evi, savi, bsi, ndbi, msavi2)
            biomasa_ms_ha, crecimiento_diario, calidad_forrajera = detector.calcular_biomasa_realista(ndvi, evi, savi, categoria_vegetacion, cobertura_vegetal, params)

            if categoria_vegetacion in ["SUELO_DESNUDO"]:
                biomasa_disponible = 20
            elif categoria_vegetacion in ["SUELO_PARCIAL"]:
                biomasa_disponible = 80
            else:
                biomasa_disponible = max(20, min(4000, (biomasa_ms_ha * calidad_forrajera * 0.6 * (1-0.25) * cobertura_vegetal)))

            resultados.append({
                'id_subLote': id_subLote,
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'msavi2': round(float(msavi2), 3),
                'bsi': round(float(bsi), 3),
                'ndbi': round(float(ndbi), 3),
                'cobertura_vegetal': round(cobertura_vegetal, 3),
                'tipo_superficie': categoria_vegetacion,
                'biomasa_ms_ha': round(biomasa_ms_ha, 1),
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'factor_calidad': round(calidad_forrajera, 3),
                'fuente_datos': fuente_satelital,
                'x_norm': round(x_norm, 3),
                'y_norm': round(y_norm, 3)
            })

        st.success("✅ Análisis REALISTA completado.")
        return resultados
    except Exception as e:
        st.error(f"❌ Error en análisis realista: {e}")
        import traceback
        st.error(traceback.format_exc())
        return []

def crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura):
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
        colores_superficie = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61',
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }

        for idx, row in gdf_analizado.iterrows():
            tipo_superficie = row.get('tipo_superficie', 'VEGETACION_ESCASA')
            color = colores_superficie.get(tipo_superficie, '#cccccc')
            gdf_analizado.iloc[[idx]].plot(ax=ax1, color=color, edgecolor='black', linewidth=1.2)
            centroid = row.geometry.centroid
            ax1.annotate(f"S{row['id_subLote']}\n{row.get('ndvi', 0):.2f}",
                        (centroid.x, centroid.y),
                        xytext=(5, 5), textcoords="offset points", fontsize=7, color='black', weight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8))

        ax1.set_title(f'MAPA DE TIPOS DE SUPERFICIE - {tipo_pastura}', fontsize=12)
        ax1.set_xlabel('Longitud')
        ax1.set_ylabel('Latitud')
        leyenda_elementos = []
        for tipo, color in colores_superficie.items():
            leyenda_elementos.append(mpatches.Patch(color=color, label=tipo))
        ax1.legend(handles=leyenda_elementos, loc='upper right', fontsize=9)

        cmap_biomasa = LinearSegmentedColormap.from_list('biomasa_mejorada', ['#d73027', '#fee08b', '#a6d96a', '#1a9850'])
        for idx, row in gdf_analizado.iterrows():
            biomasa = row.get('biomasa_disponible_kg_ms_ha', 0)
            valor_norm = biomasa / 4000
            valor_norm = max(0, min(1, valor_norm))
            color = cmap_biomasa(valor_norm)
            gdf_analizado.iloc[[idx]].plot(ax=ax2, color=color, edgecolor='black', linewidth=1.2)
            centroid = row.geometry.centroid
            ax2.annotate(f"S{row['id_subLote']}\n{biomasa:.0f}",
                        (centroid.x, centroid.y),
                        xytext=(5, 5), textcoords="offset points", fontsize=7, color='black', weight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8))

        ax2.set_title(f'MAPA DE BIOMASA DISPONIBLE - {tipo_pastura}', fontsize=12)
        sm = plt.cm.ScalarMappable(cmap=cmap_biomasa, norm=plt.Normalize(vmin=0, vmax=4000))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax2, shrink=0.8)
        cbar.set_label('Biomasa Disponible (kg MS/ha)')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception as e:
        st.error(f"❌ Error creando mapa detallado: {e}")
        return None

# -----------------------
# INFORME HTML -> PDF / FALLBACK
# -----------------------
def dataframe_to_html_table(df):
    """Simple conversion of DataFrame to styled HTML table (first 10 rows)."""
    df_short = df.head(10).copy()
    # Convert any geometry to WKT or string for display
    df_short = df_short.drop(columns=[c for c in df_short.columns if c == 'geometry'], errors='ignore')
    return df_short.to_html(index=False, classes="table", border=0)

def image_bytes_to_base64(img_bytesio):
    img_bytesio.seek(0)
    b64 = base64.b64encode(img_bytesio.read()).decode("utf-8")
    return b64

def generar_informe_html(gdf, tipo_pastura, peso_promedio, carga_animal, fecha_imagen, mapa_buffer=None):
    """Genera HTML del informe; lo guarda en session_state.html_informe también."""
    area_total = 0
    biomasa_prom = 0
    ndvi_prom = 0
    dias_promedio = 0
    ev_total = 0
    try:
        area_total = gdf['area_ha'].sum()
        biomasa_prom = gdf['biomasa_disponible_kg_ms_ha'].mean()
        ndvi_prom = gdf['ndvi'].mean()
        dias_promedio = gdf['dias_permanencia'].mean()
        ev_total = gdf['ev_soportable'].sum()
    except Exception:
        pass

    titulo = f"INFORME DE DISPONIBILIDAD FORRAJERA PRV – {fecha_imagen.strftime('%Y/%m')}"
    html_parts = []
    html_parts.append(f"<html><head><meta charset='utf-8'><style>"
                      "body{font-family:Arial,Helvetica,sans-serif;margin:30px;}"
                      "h1{color:#2E7D32;text-align:center}"
                      "table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ccc;padding:6px;text-align:center}"
                      "th{background:#2E7D32;color:white}"
                      ".small{font-size:0.8em;color:#666}"
                      "</style></head><body>")
    html_parts.append(f"<h1>{titulo}</h1>")
    html_parts.append(f"<p><b>Generado:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>")
    html_parts.append(f"<p><b>Tipo de Pastura:</b> {tipo_pastura} &nbsp;&nbsp; <b>Peso Promedio:</b> {peso_promedio} kg &nbsp;&nbsp; <b>Carga:</b> {carga_animal} cabezas</p>")
    html_parts.append("<h3>Resumen</h3>")
    html_parts.append("<table><tr><th>Área Total (ha)</th><th>Biomasa Prom. (kg MS/ha)</th><th>NDVI Promedio</th><th>Días Perm.</th><th>EV Total</th></tr>")
    html_parts.append(f"<tr><td>{area_total:.2f}</td><td>{(biomasa_prom or 0):.0f}</td><td>{(ndvi_prom or 0):.3f}</td><td>{(dias_promedio or 0):.1f}</td><td>{(ev_total or 0):.1f}</td></tr></table>")

    if mapa_buffer is not None:
        try:
            img_b64 = image_bytes_to_base64(mapa_buffer)
            html_parts.append("<h3>Mapa</h3>")
            html_parts.append(f"<div style='text-align:center'><img src='data:image/png;base64,{img_b64}' style='max-width:100%;height:auto;border:1px solid #ccc;padding:4px'></div>")
        except Exception:
            pass

    html_parts.append("<h3>Primeros 10 registros</h3>")
    try:
        html_parts.append(dataframe_to_html_table(gdf))
    except Exception:
        html_parts.append("<p>No hay tabla disponible</p>")

    html_parts.append("<hr><p class='small'>Informe generado por el Sistema de Disponibilidad Forrajera PRV.</p>")
    html_parts.append("</body></html>")
    html = "\n".join(html_parts)
    st.session_state.html_informe = html
    return html

def generar_pdf_desde_html(html_string):
    """Intenta convertir HTML->PDF con pdfkit/wkhtmltopdf.
       Devuelve BytesIO si tuvo éxito, o None si falló.
    """
    # Detectar wkhtmltopdf en PATH
    wkpath = shutil.which('wkhtmltopdf')
    if not PDFKIT_AVAILABLE or wkpath is None:
        return None

    try:
        config = pdfkit.configuration(wkhtmltopdf=wkpath)
        # Generar a un buffer en memoria usando una ruta temporal (pdfkit suele requerir archivo de salida)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
            tmp_path = tmpf.name
        pdfkit.from_string(html_string, tmp_path, configuration=config, options={'enable-local-file-access': None})
        with open(tmp_path, 'rb') as f:
            pdf_bytes = f.read()
        os.remove(tmp_path)
        buf = io.BytesIO(pdf_bytes)
        buf.seek(0)
        return buf
    except Exception as e:
        st.warning(f"⚠️ pdfkit/wkhtmltopdf falló: {e}")
        return None

def generar_docx_desde_html_simple(html_string):
    """Fallback: genera un DOCX básico con el contenido textual del HTML (si python-docx está instalado)."""
    if not DOCX_AVAILABLE:
        return None
    try:
        # Extraer texto simple (muy básico) - no render HTML complejo
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_string, 'html.parser')
        text_blocks = soup.find_all(['h1','h2','h3','p','table'])
        doc = Document()
        for block in text_blocks:
            if block.name.startswith('h'):
                doc.add_heading(block.get_text().strip(), level=1)
            elif block.name == 'p':
                doc.add_paragraph(block.get_text().strip())
            elif block.name == 'table':
                # Convertir tabla HTML a tabla docx (simple)
                rows = block.find_all('tr')
                if not rows:
                    continue
                header_cells = [td.get_text().strip() for td in rows[0].find_all(['th','td'])]
                table = doc.add_table(rows=1, cols=len(header_cells))
                hdr_cells = table.rows[0].cells
                for i, h in enumerate(header_cells):
                    hdr_cells[i].text = h
                for r in rows[1:]:
                    cols = [td.get_text().strip() for td in r.find_all('td')]
                    if not cols:
                        continue
                    row_cells = table.add_row().cells
                    for i, c in enumerate(cols):
                        row_cells[i].text = c
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except Exception:
        return None

# -----------------------
# PROCESO PRINCIPAL DE ANÁLISIS
# (estructura similar a la versión previa)
# -----------------------
def analisis_forrajero_completo_realista(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones,
                                         fuente_satelital, fecha_imagen, nubes_max,
                                         umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO REALISTA - {tipo_pastura}")
        st.success("🎯 MODO DETECCIÓN REALISTA ACTIVADO")

        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")

        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()

        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS REALISTAS")
        with st.spinner("Aplicando algoritmos..."):
            indices_forrajeros = calcular_indices_forrajeros_realista(
                gdf_dividido, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max,
                umbral_ndvi_minimo, umbral_ndvi_optimo, sensibilidad_suelo
            )

        if not indices_forrajeros:
            st.error("❌ No se pudieron calcular los índices forrajeros")
            return False

        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha.values if hasattr(areas_ha, 'values') else areas_ha
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                if key != 'id_subLote':
                    try:
                        gdf_analizado.loc[gdf_analizado.index[idx], key] = value
                    except Exception:
                        pass

        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando métricas..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)

        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                try:
                    gdf_analizado.loc[gdf_analizado.index[idx], key] = value
                except Exception:
                    pass

        st.session_state.gdf_analizado = gdf_analizado

        # Mapa detallado (matplotlib) - se muestra como imagen y se guarda en session_state
        st.subheader("🗺️ MAPA DETALLADO DE VEGETACIÓN")
        mapa_detallado = crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura)
        if mapa_detallado:
            st.image(mapa_detallado, use_container_width=True)
            st.session_state.mapa_detallado_bytes = mapa_detallado
            st.download_button(
                "📥 Descargar Mapa Detallado (PNG)",
                mapa_detallado.getvalue(),
                f"mapa_detallado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                "image/png",
                key="descarga_detallado"
            )

        # Mapa interactivo (folium) si está disponible
        if FOLIUM_AVAILABLE and st.session_state.gdf_analizado is not None:
            st.subheader("🛰️ MAPA INTERACTIVO - ESRI SATÉLITE")
            mapa_analisis = crear_mapa_analisis_interactivo(st.session_state.gdf_analizado, tipo_pastura, base_map_option)
            if mapa_analisis:
                st_folium(mapa_analisis, width=1200, height=500, returned_objects=[])

        # Sección de exportes: GeoJSON, CSV, HTML/PDF/DOCX
        if st.session_state.gdf_analizado is not None:
            st.subheader("💾 EXPORTAR RESULTADOS")
            col1, col2, col3 = st.columns(3)

            # GeoJSON
            with col1:
                try:
                    gdf_export = st.session_state.gdf_analizado.copy()
                    geojson_str = gdf_export.to_json()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename_geo = f"analisis_forrajero_{tipo_pastura}_{timestamp}.geojson"
                    st.download_button(
                        "📤 Exportar GeoJSON",
                        geojson_str,
                        filename_geo,
                        "application/geo+json",
                        key="exportar_geojson"
                    )
                except Exception as e:
                    st.error(f"❌ Error exportando GeoJSON: {e}")

            # CSV
            with col2:
                try:
                    csv_data = st.session_state.gdf_analizado.drop(columns=['geometry']).to_csv(index=False)
                    csv_filename = f"analisis_forrajero_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                    st.download_button(
                        "📊 Exportar CSV",
                        csv_data,
                        csv_filename,
                        "text/csv",
                        key="exportar_csv"
                    )
                except Exception as e:
                    st.error(f"❌ Error exportando CSV: {e}")

            # HTML -> PDF / DOCX (col3)
            with col3:
                if st.button("📄 Generar Informe (HTML→PDF)", key="generar_pdf_html"):
                    with st.spinner("🔄 Generando informe..."):
                        try:
                            html = generar_informe_html(
                                st.session_state.gdf_analizado,
                                tipo_pastura,
                                peso_promedio,
                                carga_animal,
                                fecha_imagen,
                                st.session_state.mapa_detallado_bytes
                            )
                            # Intentar convertir a PDF
                            pdf_buf = generar_pdf_desde_html(html)
                            if pdf_buf is not None:
                                st.success("✅ PDF generado correctamente (wkhtmltopdf).")
                                st.download_button(
                                    "📥 Descargar Informe PDF",
                                    pdf_buf.getvalue(),
                                    f"informe_disponibilidad_forrajera_prv_{tipo_pastura}_{fecha_imagen.strftime('%Y%m')}.pdf",
                                    "application/pdf",
                                    key="descarga_pdf_html"
                                )
                                st.session_state.pdf_buffer = pdf_buf
                            else:
                                # Fallbacks: ofrecer HTML directo y DOCX si está disponible
                                st.warning("⚠️ No se encontró wkhtmltopdf o falló la conversión a PDF. Ofrezco HTML y DOCX como alternativas.")
                                st.download_button(
                                    "🔗 Descargar Informe (HTML)",
                                    html,
                                    f"informe_disponibilidad_forrajera_prv_{tipo_pastura}_{fecha_imagen.strftime('%Y%m')}.html",
                                    "text/html",
                                    key="descarga_html"
                                )
                                if DOCX_AVAILABLE:
                                    docx_buf = generar_docx_desde_html_simple(html)
                                    if docx_buf:
                                        st.download_button(
                                            "📘 Descargar Informe (DOCX)",
                                            docx_buf,
                                            f"informe_disponibilidad_forrajera_prv_{tipo_pastura}_{fecha_imagen.strftime('%Y%m')}.docx",
                                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            key="descarga_docx"
                                        )
                        except Exception as e:
                            st.error(f"❌ Error generando informe: {e}")

        # Resumen y tabla
        st.subheader("📊 RESUMEN DE RESULTADOS")
        col1, col2, col3, col4 = st.columns(4)
        try:
            biomasa_prom = st.session_state.gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        except Exception:
            biomasa_prom = 0
        with col1:
            st.metric("Biomasa Disponible Prom", f"{biomasa_prom:.0f} kg MS/ha")
        with col2:
            try:
                area_vegetacion = st.session_state.gdf_analizado[st.session_state.gdf_analizado['tipo_superficie'].isin(['VEGETACION_MODERADA', 'VEGETACION_DENSA'])]['area_ha'].sum()
            except Exception:
                area_vegetacion = 0
            st.metric("Área con Vegetación", f"{area_vegetacion:.1f} ha")
        with col3:
            try:
                area_suelo = st.session_state.gdf_analizado[st.session_state.gdf_analizado['tipo_superficie'].isin(['SUELO_DESNUDO', 'SUELO_PARCIAL'])]['area_ha'].sum()
            except Exception:
                area_suelo = 0
            st.metric("Área sin Vegetación", f"{area_suelo:.1f} ha")
        with col4:
            try:
                cobertura_prom = st.session_state.gdf_analizado['cobertura_vegetal'].mean()
            except Exception:
                cobertura_prom = 0
            st.metric("Cobertura Vegetal Prom", f"{cobertura_prom:.1%}")

        st.subheader("🔬 DETALLES POR SUB-LOTE")
        columnas_detalle = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'cobertura_vegetal',
                          'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']
        try:
            tabla_detalle = st.session_state.gdf_analizado[columnas_detalle].copy()
            tabla_detalle.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Cobertura',
                                   'Biomasa Disp (kg MS/ha)', 'EV/Ha', 'Días Permanencia']
            st.dataframe(tabla_detalle, use_container_width=True)
        except Exception:
            st.info("No hay detalles tabulares para mostrar.")

        return True

    except Exception as e:
        st.error(f"❌ Error en análisis forrajero realista: {e}")
        import traceback
        st.error(traceback.format_exc())
        return False

# -----------------------
# INTERFAZ PRINCIPAL
# -----------------------
st.markdown("### 📁 CARGAR DATOS DEL POTRERO")
gdf_cargado = None
if uploaded_file is not None:
    with st.spinner("Cargando y procesando archivo..."):
        try:
            if tipo_archivo == "Shapefile (ZIP)":
                gdf_cargado = cargar_shapefile_desde_zip(uploaded_file)
            else:
                gdf_cargado = cargar_kml(uploaded_file)
            if gdf_cargado is not None:
                st.session_state.gdf_cargado = gdf_cargado
                area_total = calcular_superficie(gdf_cargado).sum()
                st.success("✅ Potrero cargado!")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Polígonos", len(gdf_cargado))
                with col2:
                    st.metric("Área Total", f"{area_total:.1f} ha")
                with col3:
                    st.metric("Pastura", tipo_pastura)
                with col4:
                    st.metric("Satélite", fuente_satelital)

                if FOLIUM_AVAILABLE:
                    st.markdown("---")
                    st.markdown("### 🗺️ VISUALIZACIÓN DEL POTRERO")
                    mapa_interactivo = crear_mapa_interactivo(gdf_cargado, base_map_option)
                    if mapa_interactivo:
                        st_folium(mapa_interactivo, width=1200, height=500, returned_objects=[])
                        st.info("🔍 Puedes cambiar entre mapas base usando el control del mapa.")
                else:
                    st.warning("⚠️ Para ver el mapa interactivo con ESRI Satélite instala folium: `pip install folium streamlit-folium`")
        except Exception as e:
            st.error(f"❌ Error cargando archivo: {e}")

st.markdown("---")
st.markdown("### 🚀 ACCIÓN PRINCIPAL - DETECCIÓN REALISTA")
if st.session_state.gdf_cargado is not None:
    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO REALISTA", type="primary", use_container_width=True):
        with st.spinner("🔄 Ejecutando análisis forrajero completo..."):
            resultado = analisis_forrajero_completo_realista(
                st.session_state.gdf_cargado,
                tipo_pastura,
                peso_promedio,
                carga_animal,
                n_divisiones,
                fuente_satelital,
                fecha_imagen,
                nubes_max,
                umbral_ndvi_minimo,
                umbral_ndvi_optimo,
                sensibilidad_suelo
            )
            if resultado:
                st.balloons()
                st.success("🎉 ¡Análisis completado exitosamente!")
else:
    st.info("📁 Por favor, carga un archivo de potrero para comenzar el análisis")
