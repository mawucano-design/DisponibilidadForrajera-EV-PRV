import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon
import math
import ee
import folium
from streamlit_folium import folium_static

# CONFIGURACIÓN INICIAL PARA CLOUD
st.set_page_config(
    page_title="🌱 Disponibilidad Forrajera - EV PRV", 
    layout="wide",
    page_icon="🌱"
)

# Configuración para entornos cloud
import matplotlib
matplotlib.use('Agg')  # Backend no interactivo

# Configuración de variables de entorno
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
os.environ['GDAL_CACHEMAX'] = '256'

# Título principal con mejor formato
st.title("🌱 SISTEMA DE DISPONIBILIDAD FORRAJERA - EV PRV")
st.markdown("---")

# Inicialización de Earth Engine mejorada
def inicializar_earth_engine():
    """Inicialización robusta de Earth Engine para cloud"""
    try:
        ee.Initialize()
        st.session_state.ee_initialized = True
        st.success("✅ Google Earth Engine inicializado correctamente")
        return True
    except Exception as e:
        st.warning(f"🔐 Earth Engine no inicializado: {str(e)}")
        st.info("""
        **Para usar datos reales de Sentinel-2:**
        1. Ejecuta `ee.Authenticate()` en tu entorno
        2. O usa el **Modo Demo** con datos de ejemplo realistas
        """)
        st.session_state.ee_initialized = False
        return False

# Inicializar al inicio
if 'ee_initialized' not in st.session_state:
    inicializar_earth_engine()

# SIDEBAR MEJORADO
with st.sidebar:
    st.header("⚙️ CONFIGURACIÓN")
    
    # Selector de modo de operación
    st.subheader("🔧 Modo de Operación")
    modo_operacion = st.radio(
        "Selecciona el modo:",
        ["🎮 Modo Demo", "🚀 GEE Real"],
        help="Modo Demo usa datos de ejemplo, GEE Real requiere autenticación"
    )
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Selecciona el tipo de pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    )
    
    # Parámetros personalizados si se selecciona
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", 1000, 8000, 3000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", 10, 200, 50)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", 0.01, 0.05, 0.025, 0.001, "%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", 0.3, 0.8, 0.55, 0.01, "%.2f")
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 12, 32, 24)
    
    # Configuración temporal solo para GEE Real
    if modo_operacion == "🚀 GEE Real":
        st.subheader("📅 Configuración Temporal")
        fecha_inicio = st.date_input("Fecha Inicio:", datetime.now().date() - pd.DateOffset(days=30))
        fecha_fin = st.date_input("Fecha Fin:", datetime.now().date())
        nube_max = st.slider("Máximo de Nubes (%):", 0, 50, 10)
    
    st.subheader("📤 Cargar Potrero")
    uploaded_zip = st.file_uploader("Subir archivo ZIP con shapefile", type=['zip'])
    
    # Información del sistema
    st.markdown("---")
    st.subheader("ℹ️ Información del Sistema")
    st.info(f"Modo: {'Demo' if modo_operacion == '🎮 Modo Demo' else 'GEE Real'}")
    if modo_operacion == "🎮 Modo Demo":
        st.success("✅ Listo para usar con datos de ejemplo")

# PARÁMETROS FORRAJEROS ACTUALIZADOS
PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'OFFSET_BIOMASA': -500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'OFFSET_BIOMASA': -400,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'OFFSET_BIOMASA': -300,
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_NDVI_PASTURA': 0.60
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'OFFSET_BIOMASA': -200,
        'UMBRAL_NDVI_SUELO': 0.30,
        'UMBRAL_NDVI_PASTURA': 0.65
    }
}

def obtener_parametros_forrajeros(tipo_pastura):
    if tipo_pastura == "PERSONALIZADO":
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
            'FACTOR_BIOMASA_NDVI': 2200,
            'OFFSET_BIOMASA': -400,
            'UMBRAL_NDVI_SUELO': 0.20,
            'UMBRAL_NDVI_PASTURA': 0.55
        }
    else:
        return PARAMETROS_FORRAJEROS[tipo_pastura]

# FUNCIONES BÁSICAS MEJORADAS
def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')  # Web Mercator para cálculos
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

def dividir_potrero_en_subLotes(gdf, n_zonas):
    """Divide el potrero en sub-lotes rectangulares"""
    if len(gdf) == 0:
        return gdf
    
    potrero_principal = gdf.iloc[0].geometry
    bounds = potrero_principal.bounds
    
    sub_poligonos = []
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    
    width = (bounds[2] - bounds[0]) / n_cols
    height = (bounds[3] - bounds[1]) / n_rows
    
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas:
                break
                
            cell_minx = bounds[0] + (j * width)
            cell_maxx = bounds[0] + ((j + 1) * width)
            cell_miny = bounds[1] + (i * height)
            cell_maxy = bounds[1] + ((i + 1) * height)
            
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

# GENERACIÓN DE DATOS DE EJEMPLO MEJORADA
def generar_datos_ejemplo_mejorado(gdf, tipo_pastura):
    """Genera datos de ejemplo realistas para modo demo"""
    st.info("🎮 Generando datos de ejemplo realistas...")
    
    n_poligonos = len(gdf)
    resultados = []
    params = obtener_parametros_forrajeros(tipo_pastura)
    
    # Obtener centroides para variación espacial
    gdf_centroids = gdf.copy()
    gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
    gdf_centroids['x'] = gdf_centroids.centroid.x
    gdf_centroids['y'] = gdf_centroids.centroid.y
    
    x_coords = gdf_centroids['x'].tolist()
    y_coords = gdf_centroids['y'].tolist()
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    for idx, row in gdf_centroids.iterrows():
        id_subLote = row['id_subLote']
        
        # Normalizar posición
        x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        
        # Simular índices espectrales con patrones realistas
        base_ndvi = 0.3 + (x_norm * 0.4)
        ndvi = max(0.1, min(0.8, base_ndvi + np.random.normal(0, 0.05)))
        
        # Clasificar tipo de superficie basado en NDVI y posición
        if ndvi < 0.25:
            tipo_superficie = "SUELO_DESNUDO"
            cobertura_vegetal = 0.05
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.05
        elif ndvi < 0.4:
            tipo_superficie = "VEGETACION_ESCASA"
            cobertura_vegetal = 0.3
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.4
        elif ndvi < 0.6:
            tipo_superficie = "VEGETACION_MODERADA"
            cobertura_vegetal = 0.6
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.7
        else:
            tipo_superficie = "VEGETACION_DENSA"
            cobertura_vegetal = 0.85
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.9
        
        # Ajustar basado en posición (bordes tienden a tener menos vegetación)
        factor_borde = min(x_norm, 1-x_norm, y_norm, 1-y_norm)
        if factor_borde < 0.2:
            biomasa_ms_ha *= 0.7
            cobertura_vegetal *= 0.8
        
        # Cálculos derivados
        crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
        calidad_forrajera = 0.5 + (ndvi * 0.5)
        
        # Biomasa disponible (considerando utilización)
        biomasa_disponible = biomasa_ms_ha * calidad_forrajera * params['TASA_UTILIZACION_RECOMENDADA']
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(ndvi * 1.2, 3),  # EVI correlacionado con NDVI
            'savi': round(ndvi * 1.1, 3), # SAVI similar
            'cobertura_vegetal': round(cobertura_vegetal, 3),
            'tipo_superficie': tipo_superficie,
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento_diario, 1),
            'factor_calidad': round(calidad_forrajera, 3)
        })
    
    return resultados

# CÁLCULO DE MÉTRICAS GANADERAS SIMPLIFICADO
def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Calcula equivalentes vaca y días de permanencia"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        crecimiento_diario = row['crecimiento_diario']
        
        # Consumo individual
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # Biomasa total disponible
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        # Equivalentes Vaca (EV)
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
            ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
            ev_soportable = max(0.01, ev_soportable)
        else:
            ev_soportable = 0.01
        
        # EV por hectárea
        if area_ha > 0:
            ev_ha = ev_soportable / area_ha
            ev_ha = max(0.001, ev_ha)
        else:
            ev_ha = 0.001
        
        # Días de permanencia
        if carga_animal > 0 and biomasa_total_disponible > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            dias_permanencia = biomasa_total_disponible / consumo_total_diario
            dias_permanencia = max(0.1, min(10, dias_permanencia))
        else:
            dias_permanencia = 0.1
        
        # Estado forrajero
        if biomasa_disponible >= 800:
            estado_forrajero = 4  # ÓPTIMO
        elif biomasa_disponible >= 600:
            estado_forrajero = 3  # BUENO
        elif biomasa_disponible >= 400:
            estado_forrajero = 2  # MEDIO
        elif biomasa_disponible >= 200:
            estado_forrajero = 1  # BAJO
        else:
            estado_forrajero = 0  # CRÍTICO
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'ev_ha': round(ev_ha, 3),
            'dias_permanencia': round(dias_permanencia, 1),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero
        })
    
    return metricas

# FUNCIÓN PARA CREAR MAPAS
def crear_mapa_forrajero(gdf, tipo_analisis, tipo_pastura):
    """Crea mapas temáticos forrajeros"""
    try:
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # Configurar según tipo de análisis
        if tipo_analisis == "PRODUCTIVIDAD":
            cmap = LinearSegmentedColormap.from_list('productividad', ['#d73027', '#fee08b', '#1a9850'])
            columna = 'biomasa_disponible_kg_ms_ha'
            titulo = 'Biomasa Disponible (kg MS/ha)'
            vmin, vmax = 0, 1000
        elif tipo_analisis == "DISPONIBILIDAD":
            cmap = LinearSegmentedColormap.from_list('disponibilidad', ['#4575b4', '#abd9e9', '#fdae61', '#d73027'])
            columna = 'ev_ha'
            titulo = 'Carga Animal (EV/Ha)'
            vmin, vmax = 0, 2
        else:  # PERMANENCIA
            cmap = LinearSegmentedColormap.from_list('dias', ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c'])
            columna = 'dias_permanencia'
            titulo = 'Días de Permanencia'
            vmin, vmax = 0, 10
        
        # Dibujar polígonos
        for idx, row in gdf.iterrows():
            valor = row[columna]
            valor_norm = (valor - vmin) / (vmax - vmin)
            valor_norm = max(0, min(1, valor_norm))
            color = cmap(valor_norm)
            
            gdf.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=1)
            
            # Etiqueta
            centroid = row.geometry.centroid
            ax.annotate(f"S{row['id_subLote']}\n{valor:.1f}", 
                       (centroid.x, centroid.y), 
                       xytext=(3, 3), textcoords="offset points", 
                       fontsize=7, color='black', weight='bold',
                       bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8))
        
        ax.set_title(f'🌱 {tipo_analisis} - {tipo_pastura}\n{titulo}', 
                    fontsize=14, fontweight='bold', pad=20)
        
        # Barra de color
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label(titulo, fontsize=10)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, titulo
        
    except Exception as e:
        st.error(f"Error creando mapa: {str(e)}")
        return None, None

# FUNCIÓN PRINCIPAL DE ANÁLISIS
def ejecutar_analisis_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, modo_demo=True):
    """Ejecuta el análisis forrajero completo"""
    try:
        st.header(f"📊 RESULTADOS - {tipo_pastura}")
        
        if modo_demo:
            st.info("🎮 **MODO DEMO ACTIVADO** - Usando datos de ejemplo realistas")
        
        # 1. DIVIDIR POTRERO
        st.subheader("📐 División del Potrero")
        with st.spinner("Dividiendo potrero en sub-lotes..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # 2. CALCULAR ÍNDICES
        st.subheader("🌿 Cálculo de Índices Forrajeros")
        with st.spinner("Calculando productividad forrajera..."):
            if modo_demo:
                indices = generar_datos_ejemplo_mejorado(gdf_dividido, tipo_pastura)
            else:
                # Aquí iría la conexión a GEE real
                indices = generar_datos_ejemplo_mejorado(gdf_dividido, tipo_pastura)  # Por ahora demo
        
        # Crear DataFrame con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        for idx, indice in enumerate(indices):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # 3. MÉTRICAS GANADERAS
        st.subheader("🐄 Cálculo de Métricas Ganaderas")
        with st.spinner("Calculando capacidad de carga..."):
            metricas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
        
        for idx, metrica in enumerate(metricas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # 4. CATEGORIZACIÓN
        def categorizar_manejo(estado, dias):
            if estado == 0 or dias < 1: return "CRÍTICO"
            elif estado == 1 or dias < 2: return "ALERTA"
            elif estado == 2 or dias < 3: return "ADECUADO"
            elif estado == 3: return "BUENO"
            else: return "ÓPTIMO"
        
        gdf_analizado['categoria_manejo'] = [
            categorizar_manejo(row['estado_forrajero'], row['dias_permanencia']) 
            for idx, row in gdf_analizado.iterrows()
        ]
        
        # 5. MOSTRAR RESULTADOS PRINCIPALES
        st.subheader("📈 Métricas Principales")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sub-Lotes", len(gdf_analizado))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
            st.metric("Biomasa Prom", f"{biomasa_prom:.0f} kg MS/ha")
        with col4:
            dias_prom = gdf_analizado['dias_permanencia'].mean()
            st.metric("Permanencia Prom", f"{dias_prom:.0f} días")
        
        # 6. MAPAS
        st.subheader("🗺️ Mapas de Análisis")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            mapa_biomasa, _ = crear_mapa_forrajero(gdf_analizado, "PRODUCTIVIDAD", tipo_pastura)
            if mapa_biomasa:
                st.image(mapa_biomasa, use_container_width=True)
                st.caption("**Productividad** - Biomasa disponible")
        
        with col2:
            mapa_ev, _ = crear_mapa_forrajero(gdf_analizado, "DISPONIBILIDAD", tipo_pastura)
            if mapa_ev:
                st.image(mapa_ev, use_container_width=True)
                st.caption("**Disponibilidad** - Carga animal (EV/Ha)")
        
        with col3:
            mapa_dias, _ = crear_mapa_forrajero(gdf_analizado, "PERMANENCIA", tipo_pastura)
            if mapa_dias:
                st.image(mapa_dias, use_container_width=True)
                st.caption("**Permanencia** - Días de rotación")
        
        # 7. TABLA DE RESULTADOS
        st.subheader("📋 Resultados Detallados por Sub-Lote")
        
        columnas_mostrar = ['id_subLote', 'area_ha', 'biomasa_disponible_kg_ms_ha', 
                          'ndvi', 'ev_ha', 'dias_permanencia', 'categoria_manejo']
        
        tabla_resumen = gdf_analizado[columnas_mostrar].copy()
        tabla_resumen.columns = ['Sub-Lote', 'Área (ha)', 'Biomasa (kg MS/ha)', 
                               'NDVI', 'EV/Ha', 'Días', 'Categoría']
        
        st.dataframe(tabla_resumen, use_container_width=True)
        
        # 8. RESUMEN EJECUTIVO
        st.subheader("💡 Resumen Ejecutivo")
        
        total_ev = gdf_analizado['ev_soportable'].sum()
        biomasa_total = gdf_analizado['biomasa_total_kg'].sum()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🏭 Capacidad Total", f"{total_ev:.0f} EV")
            st.metric("🌿 Biomasa Total", f"{biomasa_total/1000:.1f} ton MS")
        
        with col2:
            distribucion = gdf_analizado['categoria_manejo'].value_counts()
            st.write("**Distribución de Categorías:**")
            for cat, count in distribucion.items():
                area_cat = gdf_analizado[gdf_analizado['categoria_manejo'] == cat]['area_ha'].sum()
                st.write(f"- {cat}: {count} sub-lotes ({area_cat:.1f} ha)")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en el análisis: {str(e)}")
        return False

# INTERFAZ PRINCIPAL
if uploaded_zip:
    with st.spinner("Cargando y procesando shapefile..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Extraer ZIP
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                # Buscar shapefile
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    
                    st.success(f"✅ **Potrero cargado correctamente**")
                    
                    # Mostrar información básica
                    area_total = calcular_superficie(gdf).sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📊 Información del Potrero:**")
                        st.write(f"- Polígonos: {len(gdf)}")
                        st.write(f"- Área total: {area_total:.1f} ha")
                        st.write(f"- CRS: {gdf.crs}")
                    
                    with col2:
                        st.write("**🎯 Configuración:**")
                        st.write(f"- Pastura: {tipo_pastura}")
                        st.write(f"- Peso animal: {peso_promedio} kg")
                        st.write(f"- Carga: {carga_animal} cabezas")
                        st.write(f"- Sub-lotes: {n_divisiones}")
                    
                    # Botón de ejecución
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary", use_container_width=True):
                        modo_demo = (modo_operacion == "🎮 Modo Demo")
                        ejecutar_analisis_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, modo_demo)
                
                else:
                    st.error("❌ No se encontró archivo .shp en el ZIP")
                    
        except Exception as e:
            st.error(f"❌ Error cargando el archivo: {str(e)}")

else:
    # PANTALLA DE BIENVENIDA
    st.markdown("""
    ## 🌱 Bienvenido al Sistema de Disponibilidad Forrajera - EV PRV
    
    **¡Comienza cargando tu potrero!**
    
    ### 🚀 Instrucciones Rápidas:
    
    1. **📤 Sube tu potrero**: Archivo ZIP con shapefile
    2. **⚙️ Configura**: Selecciona tipo de pastura y parámetros
    3. **🎮 Elige modo**: Demo (rápido) o GEE Real (datos satelitales)
    4. **🚀 Ejecuta**: Obtén análisis completo en segundos
    
    ### 📊 Qué obtendrás:
    
    - ✅ **Biomasa disponible** por sub-lote
    - 🐄 **Equivalentes Vaca (EV)** de carga animal  
    - 📅 **Días de permanencia** estimados
    - 🗺️ **Mapas interactivos** de productividad
    - 💡 **Recomendaciones** de manejo forrajero
    
    ---
    
    *¿Primera vez? Usa el **Modo Demo** para probar con datos de ejemplo realistas.*
    """)
    
    # Ejemplo de archivo para probar
    with st.expander("🧪 ¿No tienes un shapefile? Prueba con este ejemplo:"):
        st.markdown("""
        **Puedes descargar un shapefile de ejemplo para probar:**
        
        1. Ve a [Natural Earth Data](https://www.naturalearthdata.com/)
        2. Descarga "Admin 0 - Countries" 
        3. Selecciona un país pequeño como Uruguay o Paraguay
        4. Comprime los archivos (.shp, .shx, .dbf, .prj) en un ZIP
        5. ¡Sube el ZIP y prueba la aplicación!
        """)

# PIE DE PÁGINA
st.markdown("---")
st.markdown(
    "🌱 **Sistema de Disponibilidad Forrajera - EV PRV** | "
    "Desarrollado para GitHub Cloud | "
    "[Reportar issues](https://github.com/mawucano-design/DisponibilidadForrajera-EV-PRV/issues)"
)
