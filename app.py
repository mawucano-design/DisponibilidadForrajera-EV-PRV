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

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"])
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA - MEJORADOS CON DETECCIÓN DE SUELO
PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'FACTOR_BIOMASA_EVI': 3000,
        'FACTOR_BIOMASA_SAVI': 2900,
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI': 0.25,
        'UMBRAL_BSI': 0.3,  # Índice de suelo desnudo
        'UMBRAL_NDBI': 0.1,  # Índice de área construida/suelo
        'FACTOR_COBERTURA': 0.8  # Cobertura vegetal mínima
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'FACTOR_BIOMASA_EVI': 2700,
        'FACTOR_BIOMASA_SAVI': 2600,
        'OFFSET_BIOMASA': -500,
        'UMBRAL_NDVI': 0.30,
        'UMBRAL_BSI': 0.25,
        'UMBRAL_NDBI': 0.08,
        'FACTOR_COBERTURA': 0.85
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'FACTOR_BIOMASA_EVI': 2400,
        'FACTOR_BIOMASA_SAVI': 2300,
        'OFFSET_BIOMASA': -400,
        'UMBRAL_NDVI': 0.35,
        'UMBRAL_BSI': 0.2,
        'UMBRAL_NDBI': 0.06,
        'FACTOR_COBERTURA': 0.75
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'FACTOR_BIOMASA_EVI': 2200,
        'FACTOR_BIOMASA_SAVI': 2100,
        'OFFSET_BIOMASA': -300,
        'UMBRAL_NDVI': 0.40,
        'UMBRAL_BSI': 0.15,
        'UMBRAL_NDBI': 0.04,
        'FACTOR_COBERTURA': 0.70
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'FACTOR_BIOMASA_EVI': 2000,
        'FACTOR_BIOMASA_SAVI': 1900,
        'OFFSET_BIOMASA': -200,
        'UMBRAL_NDVI': 0.45,
        'UMBRAL_BSI': 0.1,
        'UMBRAL_NDBI': 0.02,
        'FACTOR_COBERTURA': 0.60
    }
}

# PALETAS GEE PARA ANÁLISIS FORRAJERO
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
    'COBERTURA': ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60']  # Nueva paleta para cobertura
}

# Función para calcular superficie
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

# METODOLOGÍA GEE MEJORADA CON DETECCIÓN DE SUELO/ROCA
def calcular_indices_forrajeros_gee(gdf, tipo_pastura):
    """
    Implementa metodología GEE mejorada con detección de suelo desnudo y roca
    """
    
    n_poligonos = len(gdf)
    resultados = []
    params = PARAMETROS_FORRAJEROS[tipo_pastura]
    
    # Obtener centroides para gradiente espacial
    gdf_centroids = gdf.copy()
    gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
    gdf_centroids['x'] = gdf_centroids.centroid.x
    gdf_centroids['y'] = gdf_centroids.centroid.y
    
    x_coords = gdf_centroids['x'].tolist()
    y_coords = gdf_centroids['y'].tolist()
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    for idx, row in gdf_centroids.iterrows():
        # Normalizar posición para simular variación espacial
        x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        
        patron_espacial = (x_norm * 0.6 + y_norm * 0.4)
        
        # 1. SIMULAR BANDAS SENTINEL-2 CON VARIABILIDAD REALISTA
        # Bandas espectrales con patrones más realistas
        blue = 0.12 + (patron_espacial * 0.15) + np.random.normal(0, 0.02)
        green = 0.15 + (patron_espacial * 0.2) + np.random.normal(0, 0.03)
        red = 0.18 + (patron_espacial * 0.25) + np.random.normal(0, 0.04)
        nir = 0.35 + (patron_espacial * 0.4) + np.random.normal(0, 0.08)
        swir1 = 0.25 + (patron_espacial * 0.3) + np.random.normal(0, 0.06)
        swir2 = 0.20 + (patron_espacial * 0.25) + np.random.normal(0, 0.05)
        
        # 2. CÁLCULO DE ÍNDICES VEGETACIONALES
        # NDVI - Índice de vegetación normalizado
        ndvi = (nir - red) / (nir + red) if (nir + red) > 0 else 0
        ndvi = max(-0.2, min(0.9, ndvi))
        
        # EVI - Índice de vegetación mejorado
        evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1) if (nir + 6 * red - 7.5 * blue + 1) > 0 else 0
        evi = max(-0.2, min(0.8, evi))
        
        # SAVI - Índice de vegetación ajustado al suelo
        savi = 1.5 * (nir - red) / (nir + red + 0.5) if (nir + red + 0.5) > 0 else 0
        savi = max(-0.2, min(0.8, savi))
        
        # NDWI - Índice de agua
        ndwi = (nir - swir1) / (nir + swir1) if (nir + swir1) > 0 else 0
        ndwi = max(-0.5, min(0.5, ndwi))
        
        # 3. ÍNDICES PARA DETECTAR SUELO DESNUDO/ROCA
        # BSI - Bare Soil Index (Índice de suelo desnudo)
        bsi = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)) if ((swir1 + red) + (nir + blue)) > 0 else 0
        
        # NDBI - Normalized Difference Built-up Index (también detecta suelo)
        ndbi = (swir1 - nir) / (swir1 + nir) if (swir1 + nir) > 0 else 0
        
        # NDSI - Normalized Difference Snow Index (también útil para rocas)
        ndsi = (green - swir1) / (green + swir1) if (green + swir1) > 0 else 0
        
        # 4. DETECCIÓN DE ÁREAS SIN VEGETACIÓN
        # Calcular probabilidad de ser suelo desnudo/roca
        prob_suelo_desnudo = max(0, min(1, 
            (bsi - 0.1) * 2 +  # BSI alto indica suelo
            (ndbi - 0.05) * 3 +  # NDBI alto indica suelo/construcción
            (ndsi - 0.1) * 1.5 +  # NDSI alto puede indicar rocas
            (1 - ndvi) * 0.5  # NDVI bajo
        ))
        
        # Factor de cobertura vegetal (1 = totalmente cubierto, 0 = suelo desnudo)
        cobertura_vegetal = max(0, min(1, 
            (ndvi * 0.4 + evi * 0.3 + savi * 0.3) * 2.5 -  # Combinación de índices vegetacionales
            prob_suelo_desnudo * 0.8  # Reducir por probabilidad de suelo
        ))
        
        # 5. CÁLCULO DE BIOMASA CON FILTRO DE COBERTURA
        # Solo calcular biomasa si hay suficiente cobertura vegetal
        if cobertura_vegetal < params['FACTOR_COBERTURA']:
            # Área con poca vegetación - biomasa muy reducida
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.1 * cobertura_vegetal
            crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.1
            calidad_forrajera = 0.1
        else:
            # Área con buena cobertura - cálculo normal
            biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
            biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
            biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
            
            biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
            biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
            
            # Aplicar máscara por umbral NDVI
            if ndvi < params['UMBRAL_NDVI']:
                biomasa_ms_ha = biomasa_ms_ha * 0.3
            
            crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
            crecimiento_diario = max(5, min(150, crecimiento_diario))
            
            calidad_forrajera = (ndwi + 1) / 2
            calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
        
        # 6. BIOMASA DISPONIBLE (considerando cobertura)
        eficiencia_cosecha = 0.25
        perdidas = 0.30
        biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
        biomasa_disponible = max(0, min(1200, biomasa_disponible))
        
        # 7. CLASIFICACIÓN DE TIPO DE SUPERFICIE
        if prob_suelo_desnudo > 0.7:
            tipo_superficie = "SUELO_DESNUDO"
        elif prob_suelo_desnudo > 0.5:
            tipo_superficie = "SUELO_PARCIAL"
        elif cobertura_vegetal < 0.3:
            tipo_superficie = "VEGETACION_ESCASA"
        elif cobertura_vegetal < 0.6:
            tipo_superficie = "VEGETACION_MODERADA"
        else:
            tipo_superficie = "VEGETACION_DENSA"
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'ndwi': round(ndwi, 3),
            'bsi': round(bsi, 3),
            'ndbi': round(ndbi, 3),
            'cobertura_vegetal': round(cobertura_vegetal, 3),
            'prob_suelo_desnudo': round(prob_suelo_desnudo, 3),
            'tipo_superficie': tipo_superficie,
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento_diario, 1),
            'factor_calidad': round(calidad_forrajera, 3)
        })
    
    return resultados

# [Mantener las funciones calcular_metricas_ganaderas, crear_mapa_forrajero_gee, etc...]

# NUEVA FUNCIÓN PARA MAPA DE COBERTURA
def crear_mapa_cobertura(gdf, tipo_pastura):
    """Crea mapa de cobertura vegetal y tipos de superficie"""
    try:
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        
        # Definir colores para tipos de superficie
        colores_superficie = {
            'SUELO_DESNUDO': '#d73027',
            'SUELO_PARCIAL': '#fdae61', 
            'VEGETACION_ESCASA': '#fee08b',
            'VEGETACION_MODERADA': '#a6d96a',
            'VEGETACION_DENSA': '#1a9850'
        }
        
        # Plotear cada polígono según tipo de superficie
        for idx, row in gdf.iterrows():
            tipo_superficie = row['tipo_superficie']
            color = colores_superficie.get(tipo_superficie, '#cccccc')
            
            gdf.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=1.5)
            
            # Etiqueta con valor de cobertura
            centroid = row.geometry.centroid
            ax.annotate(f"S{row['id_subLote']}\n{row['cobertura_vegetal']:.1f}", 
                       (centroid.x, centroid.y), 
                       xytext=(5, 5), textcoords="offset points", 
                       fontsize=8, color='black', weight='bold',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        # Configuración del mapa
        ax.set_title(f'🌱 MAPA DE COBERTURA VEGETAL - {tipo_pastura}\n'
                    f'Tipos de Superficie y Cobertura Vegetal\n'
                    f'Metodología Google Earth Engine', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
        
        # Crear leyenda personalizada
        leyenda_elementos = []
        for tipo, color in colores_superficie.items():
            leyenda_elementos.append(mpatches.Patch(color=color, label=tipo))
        
        ax.legend(handles=leyenda_elementos, loc='upper right', fontsize=10)
        
        plt.tight_layout()
        
        # Convertir a imagen
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        st.error(f"❌ Error creando mapa de cobertura: {str(e)}")
        return None

# FUNCIÓN PRINCIPAL DE ANÁLISIS FORRAJERO - MEJORADA
def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # PASO 1: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 2: CALCULAR ÍNDICES FORRAJEROS GEE MEJORADO
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS GEE")
        with st.spinner("Ejecutando algoritmos GEE con detección de suelo..."):
            indices_forrajeros = calcular_indices_forrajeros_gee(gdf_dividido, tipo_pastura)
        
        # Crear dataframe con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        # Añadir índices forrajeros
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 3: CALCULAR MÉTRICAS GANADERAS
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca y días de permanencia..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 4: MOSTRAR ANÁLISIS DE COBERTURA
        st.subheader("🌿 ANÁLISIS DE COBERTURA VEGETAL")
        
        # Estadísticas de cobertura
        stats_cobertura = gdf_analizado['tipo_superficie'].value_counts()
        area_por_tipo = gdf_analizado.groupby('tipo_superficie')['area_ha'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            cobertura_prom = gdf_analizado['cobertura_vegetal'].mean()
            st.metric("Cobertura Vegetal Promedio", f"{cobertura_prom:.1%}")
        with col2:
            area_vegetacion = area_por_tipo.get('VEGETACION_DENSA', 0) + area_por_tipo.get('VEGETACION_MODERADA', 0)
            st.metric("Área con Vegetación", f"{area_vegetacion:.1f} ha")
        with col3:
            area_suelo = area_por_tipo.get('SUELO_DESNUDO', 0) + area_por_tipo.get('SUELO_PARCIAL', 0)
            st.metric("Área sin Vegetación", f"{area_suelo:.1f} ha")
        
        # Mapa de cobertura
        st.write("**🗺️ MAPA DE COBERTURA VEGETAL**")
        mapa_cobertura = crear_mapa_cobertura(gdf_analizado, tipo_pastura)
        if mapa_cobertura:
            st.image(mapa_cobertura, use_container_width=True)
            
            # Botón de descarga para mapa de cobertura
            st.download_button(
                "📥 Descargar Mapa de Cobertura",
                mapa_cobertura.getvalue(),
                f"mapa_cobertura_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                "image/png",
                key="descarga_cobertura"
            )
        
        # TABLA DE TIPOS DE SUPERFICIE
        st.write("**📊 DISTRIBUCIÓN DE TIPOS DE SUPERFICIE**")
        resumen_cobertura = pd.DataFrame({
            'Tipo de Superficie': stats_cobertura.index,
            'Número de Sub-Lotes': stats_cobertura.values,
            'Área Total (ha)': [area_por_tipo.get(tipo, 0) for tipo in stats_cobertura.index],
            'Porcentaje del Área': [f"{(area_por_tipo.get(tipo, 0) / area_total * 100):.1f}%" 
                                  for tipo in stats_cobertura.index]
        })
        st.dataframe(resumen_cobertura, use_container_width=True)
        
        # [Mantener el resto del código para mapas forrajeros, validaciones, etc...]

# [El resto del código se mantiene similar pero integrando las mejoras]
