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
# === Reemplazo de fpdf por reportlab ===
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
# =======================================

# Importaciones opcionales para folium con manejo de errores
try:
    import folium
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
if 'mapa_detallado_bytes' not in st.session_state:
    st.session_state.mapa_detallado_bytes = None
if 'pdf_generado' not in st.session_state:
    st.session_state.pdf_generado = False
if 'pdf_buffer' not in st.session_state:
    st.session_state.pdf_buffer = None

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    if FOLIUM_AVAILABLE:
        st.subheader("🗺️ Mapa Base")
        base_map_option = st.selectbox(
            "Seleccionar mapa base:",
            ["ESRI Satélite", "OpenStreetMap", "CartoDB Positron"],
            index=0,
            help="ESRI Satélite: Imágenes satelitales reales. OpenStreetMap: Mapa estándar. CartoDB: Mapa claro."
        )
    else:
        base_map_option = "ESRI Satélite"
    
    st.subheader("🛰️ Fuente de Datos Satelitales")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
        help="Sentinel-2: Mayor resolución (10m). Landsat: Cobertura global histórica."
    )
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now(),
        help="Selecciona la fecha para la imagen satelital"
    )
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)
    
    st.subheader("🌿 Parámetros de Detección de Vegetación")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo vegetación:", 0.05, 0.3, 0.15, 0.01,
                                  help="NDVI por debajo de este valor se considera suelo desnudo")
    umbral_ndvi_optimo = st.slider("Umbral NDVI vegetación óptima:", 0.4, 0.8, 0.6, 0.01,
                                  help="NDVI por encima de este valor se considera vegetación densa")
    sensibilidad_suelo = st.slider("Sensibilidad detección suelo:", 0.1, 1.0, 0.5, 0.1,
                                  help="Mayor valor = más estricto en detectar suelo desnudo")
    
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
    tipo_archivo = st.radio(
        "Formato del archivo:",
        ["Shapefile (ZIP)", "KML"],
        horizontal=True
    )
    if tipo_archivo == "Shapefile (ZIP)":
        uploaded_file = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    else:
        uploaded_file = st.file_uploader("Subir archivo KML del potrero", type=['kml'])

# =============================================================================
# FUNCIONES PARA CARGAR ARCHIVOS
# =============================================================================
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

# =============================================================================
# ✅ FUNCIÓN DE EXPORTACIÓN A PDF CON REPORTLAB (CORREGIDA)
# =============================================================================
def exportar_informe_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, mapa_detallado_bytes=None):
    """Exporta el análisis completo a PDF usando ReportLab"""
    try:
        # Verificar que tenemos datos
        if gdf_analizado is None or len(gdf_analizado) == 0:
            st.error("❌ No hay datos para generar el PDF")
            return None
            
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

        story = []
        
        # Título principal
        story.append(Paragraph("INFORME DE ANÁLISIS FORRAJERO", title_style))
        story.append(Spacer(1, 20))

        # Información general
        story.append(Paragraph("INFORMACIÓN GENERAL", heading_style))
        info_data = [
            ["Tipo de Pastura:", tipo_pastura],
            ["Carga Animal:", f"{carga_animal} cabezas"],
            ["Peso Promedio:", f"{peso_promedio} kg"],
            ["Fecha de Generación:", datetime.now().strftime("%d/%m/%Y %H:%M")]
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 3*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))

        # Estadísticas
        area_total = gdf_analizado['area_ha'].sum()
        biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        ndvi_prom = gdf_analizado['ndvi'].mean()
        dias_promedio = gdf_analizado['dias_permanencia'].mean()
        ev_total = gdf_analizado['ev_soportable'].sum()

        story.append(Paragraph("ESTADÍSTICAS DEL ANÁLISIS", heading_style))
        stats_data = [
            ["Estadística", "Valor"],
            ["Área Total", f"{area_total:.2f} ha"],
            ["Biomasa Disponible Prom.", f"{biomasa_prom:.0f} kg MS/ha"],
            ["NDVI Promedio", f"{ndvi_prom:.3f}"],
            ["Días de Permanencia Prom.", f"{dias_promedio:.1f}"],
            ["Equivalente Vaca Total", f"{ev_total:.1f} EV"]
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 20))

        # Mapa
        if mapa_detallado_bytes is not None:
            story.append(PageBreak())
            story.append(Paragraph("MAPA DE ANÁLISIS", heading_style))
            try:
                # Reiniciar el buffer del mapa
                mapa_detallado_bytes.seek(0)
                mapa_img = Image(mapa_detallado_bytes, width=6*inch, height=4*inch)
                story.append(mapa_img)
                story.append(Spacer(1, 10))
                story.append(Paragraph("Figura 1: Mapa de tipos de superficie y biomasa disponible.", normal_style))
            except Exception as e:
                story.append(Paragraph(f"Error al insertar el mapa: {str(e)}", normal_style))

        # Tabla de resultados por sub-lote (primeras 10)
        story.append(Spacer(1, 20))
        story.append(Paragraph("RESULTADOS POR SUB-LOTE (Primeras 10 filas)", heading_style))
        
        columnas_tabla = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha']
        df_tabla = gdf_analizado[columnas_tabla].head(10).copy()
        
        # Redondear valores
        df_tabla['area_ha'] = df_tabla['area_ha'].round(2)
        df_tabla['ndvi'] = df_tabla['ndvi'].round(3)
        df_tabla['biomasa_disponible_kg_ms_ha'] = df_tabla['biomasa_disponible_kg_ms_ha'].round(0)
        df_tabla['dias_permanencia'] = df_tabla['dias_permanencia'].round(1)
        df_tabla['ev_ha'] = df_tabla['ev_ha'].round(3)

        # Preparar datos para tabla
        table_data = [['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'Días', 'EV/Ha']]
        for _, row in df_tabla.iterrows():
            table_data.append([
                str(row['id_subLote']),
                f"{row['area_ha']:.2f}",
                row['tipo_superficie'],
                f"{row['ndvi']:.3f}",
                f"{row['biomasa_disponible_kg_ms_ha']:.0f}",
                f"{row['dias_permanencia']:.1f}",
                f"{row['ev_ha']:.3f}"
            ])

        result_table = Table(table_data, colWidths=[0.6*inch, 0.7*inch, 1.2*inch, 0.6*inch, 1.0*inch, 0.6*inch, 0.6*inch])
        result_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        story.append(result_table)

        # Recomendaciones
        story.append(PageBreak())
        story.append(Paragraph("RECOMENDACIONES FORRAJERAS", heading_style))
        
        # Análisis de recomendaciones basado en los resultados
        if biomasa_prom < 1000:
            recomendacion = "❌ CRÍTICO: Biomasa muy baja. Considerar suplementación y reducir carga animal."
        elif biomasa_prom < 2000:
            recomendacion = "⚠️ ALERTA: Biomasa moderada. Monitorear crecimiento y ajustar rotaciones."
        else:
            recomendacion = "✅ ÓPTIMO: Biomasa adecuada. Mantener manejo actual."
        
        story.append(Paragraph(f"<b>Estado General:</b> {recomendacion}", normal_style))
        story.append(Spacer(1, 10))
        
        # Recomendaciones específicas
        recomendaciones = [
            f"• Carga animal actual: {carga_animal} cabezas",
            f"• Equivalente Vaca soportable: {ev_total:.1f} EV",
            f"• Días de permanencia promedio: {dias_promedio:.1f} días",
            "• Realizar rotaciones según los días de permanencia por sub-lote",
            "• Monitorear crecimiento forrajero cada 15 días"
        ]
        
        for rec in recomendaciones:
            story.append(Paragraph(rec, normal_style))

        # Generar PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        st.error(f"❌ Error en exportar_informe_pdf: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return None

# =============================================================================
# CONFIGURACIÓN DE MAPAS BASE (se mantiene igual)
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
        bounds = gdf.total_bounds
        centroid = gdf.geometry.centroid.iloc[0]
        m = folium.Map(location=[centroid.y, centroid.x], tiles=None, control_scale=True)
        for map_name, config in BASE_MAPS_CONFIG.items():
            folium.TileLayer(
                tiles=config["tiles"], attr=config["attr"], name=config["name"], overlay=False, control=True
            ).add_to(m)
        selected_config = BASE_MAPS_CONFIG[base_map_name]
        folium.TileLayer(
            tiles=selected_config["tiles"], attr=selected_config["attr"], name=selected_config["name"], overlay=False, control=False
        ).add_to(m)
        folium.GeoJson(gdf.__geo_interface__, style_function=lambda x: {
            'fillColor': '#3388ff', 'color': 'blue', 'weight': 2, 'fillOpacity': 0.2
        }).add_to(m)
        folium.Marker(
            [centroid.y, centroid.x],
            popup=f"Centro del Potrero<br>Lat: {centroid.y:.4f}<br>Lon: {centroid.x:.4f}",
            tooltip="Centro del Potrero",
            icon=folium.Icon(color='green', icon='info-sign')
        ).add_to(m)
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        folium.LayerControl().add_to(m)
        return m

    def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"):
        if gdf_analizado is None or len(gdf_analizado) == 0:
            return None
        bounds = gdf_analizado.total_bounds
        centroid = gdf_analizado.geometry.centroid.iloc[0]
        m = folium.Map(location=[centroid.y, centroid.x], tiles=None, control_scale=True)
        for map_name, config in BASE_MAPS_CONFIG.items():
            folium.TileLayer(
                tiles=config["tiles"], attr=config["attr"], name=config["name"], overlay=False, control=True
            ).add_to(m)
        selected_config = BASE_MAPS_CONFIG[base_map_name]
        folium.TileLayer(
            tiles=selected_config["tiles"], attr=selected_config["attr"], name=selected_config["name"], overlay=False, control=False
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
            return {'fillColor': colores.get(tipo_superficie, '#3388ff'), 'color': 'black', 'weight': 1.5, 'fillOpacity': 0.6}

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
        <div style="position: fixed; bottom: 50px; left: 50px; width: 200px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <p><strong>Tipos de Superficie</strong></p>
        '''
        for tipo, color in colores_leyenda.items():
            legend_html += f'<p><i style="background:{color}; width:20px; height:20px; display:inline-block; margin-right:5px;"></i> {tipo}</p>'
        legend_html += '</div>'
        m.get_root().html.add_child(folium.Element(legend_html))
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        folium.LayerControl().add_to(m)
        return m

else:
    def crear_mapa_interactivo(gdf, base_map_name="ESRI Satélite"): return None
    def crear_mapa_analisis_interactivo(gdf_analizado, tipo_pastura, base_map_name="ESRI Satélite"): return None

# =============================================================================
# FUNCIÓN PARA EXPORTAR GEOJSON
# =============================================================================
def exportar_geojson(gdf_analizado, tipo_pastura):
    if gdf_analizado is None or len(gdf_analizado) == 0:
        return None
    try:
        gdf_export = gdf_analizado.copy()
        geojson_str = gdf_export.to_json()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analisis_forrajero_{tipo_pastura}_{timestamp}.geojson"
        return geojson_str, filename
    except Exception as e:
        st.error(f"❌ Error exportando GeoJSON: {str(e)}")
        return None, None

# =============================================================================
# PARÁMETROS FORRAJEROS Y FUNCIONES BÁSICAS (se mantienen igual)
# =============================================================================
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
    # ... (los demás parámetros se mantienen igual)
}

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

def calcular_superficie(gdf):
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

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
# ALGORITMOS DE DETECCIÓN DE VEGETACIÓN (se mantienen igual)
# =============================================================================
class DetectorVegetacionRealista:
    def __init__(self, umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
        self.umbral_ndvi_minimo = umbral_ndvi_minimo
        self.umbral_ndvi_optimo = umbral_ndvi_optimo
        self.sensibilidad_suelo = sensibilidad_suelo
        self.parametros_cientificos = {
            'ndvi_suelo_desnudo_max': 0.15,
            'ndvi_vegetacion_escasa_min': 0.15,
            'ndvi_vegetacion_escasa_max': 0.4,
            'ndvi_vegetacion_moderada_min': 0.4,
            'ndvi_vegetacion_moderada_max': 0.65,
            'ndvi_vegetacion_densa_min': 0.65,
            'bsi_suelo_min': 0.3,
            'ndbi_suelo_min': 0.1,
            'evi_vegetacion_min': 0.1,
            'savi_vegetacion_min': 0.1,
            'cobertura_suelo_desnudo_max': 0.1,
            'cobertura_vegetacion_escasa_min': 0.3,
        }

    def clasificar_vegetacion_realista(self, ndvi, evi, savi, bsi, ndbi, msavi2=None):
        # ... (implementación se mantiene igual)
        pass

    def calcular_biomasa_realista(self, ndvi, evi, savi, categoria_vegetacion, cobertura, params):
        # ... (implementación se mantiene igual)
        pass

def simular_patrones_reales_con_suelo(id_subLote, x_norm, y_norm, fuente_satelital):
    # ... (implementación se mantiene igual)
    pass

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    # ... (implementación se mantiene igual)
    pass

def calcular_indices_forrajeros_realista(gdf, tipo_pastura, fuente_satelital, fecha_imagen, nubes_max=20,
                                       umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    # ... (implementación se mantiene igual)
    pass

def crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura):
    # ... (implementación se mantiene igual)
    pass

def analisis_forrajero_completo_realista(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, 
                                       fuente_satelital, fecha_imagen, nubes_max,
                                       umbral_ndvi_minimo=0.15, umbral_ndvi_optimo=0.6, sensibilidad_suelo=0.5):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO REALISTA - {tipo_pastura}")
        st.success("🎯 **MODO DETECCIÓN REALISTA ACTIVADO** - Responde a suelo desnudo y condiciones reales")

        # ... (resto del análisis se mantiene igual hasta la sección de exportación)

        if st.session_state.gdf_analizado is not None:
            st.subheader("💾 EXPORTAR RESULTADOS")
            col1, col2, col3 = st.columns(3)
            
            # Columna 1: GeoJSON
            with col1:
                geojson_str, filename = exportar_geojson(st.session_state.gdf_analizado, tipo_pastura)
                if geojson_str:
                    st.download_button(
                        "📤 Exportar GeoJSON",
                        geojson_str,
                        filename,
                        "application/geo+json",
                        key="exportar_geojson"
                    )
            
            # Columna 2: CSV
            with col2:
                csv_data = st.session_state.gdf_analizado.drop(columns=['geometry']).to_csv(index=False)
                csv_filename = f"analisis_forrajero_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                st.download_button(
                    "📊 Exportar CSV",
                    csv_data,
                    csv_filename,
                    "text/csv",
                    key="exportar_csv"
                )
            
            # Columna 3: PDF - IMPLEMENTACIÓN SIMPLIFICADA Y FUNCIONAL
            with col3:
                # Botón único para generar y descargar PDF
                if st.button("📄 Generar y Descargar PDF", type="primary", key="generar_pdf"):
                    with st.spinner("🔄 Generando informe PDF..."):
                        try:
                            pdf_buffer = exportar_informe_pdf(
                                st.session_state.gdf_analizado,
                                tipo_pastura,
                                peso_promedio,
                                carga_animal,
                                st.session_state.mapa_detallado_bytes
                            )
                            
                            if pdf_buffer:
                                st.success("✅ PDF generado correctamente!")
                                
                                # Mostrar botón de descarga inmediatamente
                                st.download_button(
                                    label="📥 Descargar Informe PDF",
                                    data=pdf_buffer,
                                    file_name=f"informe_forrajero_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                    mime="application/pdf",
                                    key="descarga_pdf"
                                )
                            else:
                                st.error("❌ No se pudo generar el PDF")
                                
                        except Exception as e:
                            st.error(f"❌ Error generando PDF: {str(e)}")

        # ... (resto del análisis se mantiene igual)

    except Exception as e:
        st.error(f"❌ Error en análisis forrajero realista: {str(e)}")
        return False

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================
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
                st.success(f"✅ **Potrero cargado exitosamente!**")
                
                if FOLIUM_AVAILABLE:
                    st.markdown("---")
                    st.markdown("### 🗺️ VISUALIZACIÓN DEL POTRERO")
                    mapa_interactivo = crear_mapa_interactivo(gdf_cargado, base_map_option)
                    if mapa_interactivo:
                        st_folium(mapa_interactivo, width=1200, height=500, returned_objects=[])
        except Exception as e:
            st.error(f"❌ Error cargando archivo: {str(e)}")

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
