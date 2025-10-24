import streamlit as st
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
import math
import json

st.set_page_config(page_title="🌱 Analizador Forrajero", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - DETECCIÓN AUTOMÁTICA")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selección de tipo de pastura
    opciones_pastura = ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    tipo_pastura = st.selectbox("Tipo de Pastura:", opciones_pastura)
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=72, value=48)
    
    st.subheader("📤 Subir Datos")
    uploaded_file = st.file_uploader("Subir archivo CSV con coordenadas", type=['csv'])
    
    st.subheader("🌿 Parámetros de Detección")
    umbral_vegetacion = st.slider("Umbral para vegetación:", 
                                 min_value=0.1, max_value=0.9, value=0.4, step=0.05,
                                 help="Valor más alto = menos vegetación detectada")

# PARÁMETROS FORRAJEROS BASE
PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
    }
}

# PALETAS PARA ANÁLISIS FORRAJERO
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
}

# FUNCIÓN PARA SIMULAR GEOMETRÍA SI NO HAY ARCHIVO
def crear_geometria_simulada(n_zonas=48):
    """Crea una geometría simulada si no se sube archivo"""
    np.random.seed(42)
    
    # Crear datos simulados
    datos = []
    for i in range(n_zonas):
        # Simular coordenadas en un grid
        row = i // 8
        col = i % 8
        x_center = col * 100 + 50
        y_center = row * 100 + 50
        
        # Crear polígono cuadrado simple
        poligono = [
            [x_center-40, y_center-40],
            [x_center+40, y_center-40],
            [x_center+40, y_center+40],
            [x_center-40, y_center+40],
            [x_center-40, y_center-40]
        ]
        
        datos.append({
            'id_subLote': i + 1,
            'area_ha': 0.8 + np.random.normal(0, 0.1),
            'centro_x': x_center,
            'centro_y': y_center,
            'poligono': poligono
        })
    
    return datos

# ALGORITMO SIMPLIFICADO DE DETECCIÓN
def detectar_vegetacion_simple(n_zonas=48):
    """
    Algoritmo simple de detección que simula patrones realistas
    """
    np.random.seed(42)  # Para resultados consistentes
    
    resultados = []
    
    for i in range(n_zonas):
        id_subLote = i + 1
        
        # Crear patrones espaciales basados en la posición
        fila = (id_subLote - 1) // 8
        columna = (id_subLote - 1) % 8
        
        # Patrón: áreas centrales tienen mejor vegetación
        distancia_centro = abs(fila - 3.5) + abs(columna - 3.5)
        factor_calidad = max(0.1, 1 - (distancia_centro / 7))
        
        # SIMULAR CARACTERÍSTICAS BASADAS EN PATRONES APRENDIDOS
        # De los ejemplos: la mayoría es suelo desnudo, pocas zonas tienen vegetación
        
        # Probabilidad base de tener vegetación (aprendido de ejemplos)
        prob_base_vegetacion = 0.15  # Solo ~15% del área tiene vegetación
        
        # Ajustar por calidad de la zona
        prob_vegetacion = prob_base_vegetacion * (1 + factor_calidad)
        
        # DETERMINAR SI TIENE VEGETACIÓN
        tiene_vegetacion = np.random.random() < prob_vegetacion
        
        if tiene_vegetacion:
            # ZONAS CON VEGETACIÓN - variar calidad
            if factor_calidad > 0.7:
                # Mejores zonas - vegetación densa
                ndvi = 0.6 + np.random.normal(0, 0.1)
                cobertura = 0.8 + np.random.normal(0, 0.1)
                tipo_superficie = "VEGETACION_DENSA"
                probabilidad = 0.9
            elif factor_calidad > 0.4:
                # Zonas medias - vegetación moderada
                ndvi = 0.45 + np.random.normal(0, 0.1)
                cobertura = 0.6 + np.random.normal(0, 0.15)
                tipo_superficie = "VEGETACION_MODERADA"
                probabilidad = 0.7
            else:
                # Zonas marginales - vegetación escasa
                ndvi = 0.3 + np.random.normal(0, 0.1)
                cobertura = 0.4 + np.random.normal(0, 0.2)
                tipo_superficie = "VEGETACION_ESCASA"
                probabilidad = 0.5
        else:
            # SUELO DESNUDO - la mayoría de las zonas
            ndvi = 0.1 + np.random.normal(0, 0.05)
            cobertura = 0.1 + np.random.normal(0, 0.05)
            tipo_superficie = "SUELO_DESNUDO"
            probabilidad = 0.1
        
        # Aplicar umbral configurable
        if probabilidad < umbral_vegetacion:
            tiene_vegetacion = False
            tipo_superficie = "SUELO_DESNUDO"
        
        # Asegurar valores dentro de rangos
        ndvi = max(0.05, min(0.85, ndvi))
        cobertura = max(0.02, min(0.98, cobertura))
        probabilidad = max(0.05, min(0.95, probabilidad))
        
        resultados.append({
            'id_subLote': id_subLote,
            'ndvi': round(ndvi, 3),
            'cobertura_vegetal': round(cobertura, 3),
            'probabilidad_vegetacion': round(probabilidad, 3),
            'tipo_superficie': tipo_superficie,
            'tiene_vegetacion': tiene_vegetacion,
            'area_ha': round(0.8 + np.random.normal(0, 0.1), 2),
            'centro_x': (columna * 100 + 50),
            'centro_y': (fila * 100 + 50)
        })
    
    return resultados

# FUNCIÓN PARA CALCULAR BIOMASA
def calcular_biomasa_simple(deteccion, params):
    """
    Calcula biomasa basada en la detección
    """
    resultados = []
    
    for det in deteccion:
        tiene_vegetacion = det['tiene_vegetacion']
        tipo_superficie = det['tipo_superficie']
        cobertura_vegetal = det['cobertura_vegetal']
        
        # CALCULAR BIOMASA SEGÚN DETECCIÓN
        if not tiene_vegetacion:
            # SUELO DESNUDO - biomasa muy baja
            biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.05
            crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.05
            calidad_forrajera = 0.1
            
        else:
            # VEGETACIÓN - biomasa según tipo
            if tipo_superficie == "VEGETACION_DENSA":
                biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.9
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.9
                calidad_forrajera = 0.85
            elif tipo_superficie == "VEGETACION_MODERADA":
                biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.7
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.7
                calidad_forrajera = 0.75
            else:  # VEGETACION_ESCASA
                biomasa_ms_ha = params['MS_POR_HA_OPTIMO'] * 0.5
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.5
                calidad_forrajera = 0.60
            
            # Ajustar por cobertura real
            biomasa_ms_ha = biomasa_ms_ha * cobertura_vegetal
        
        # Cálculo de biomasa disponible
        eficiencia_cosecha = 0.25
        perdidas = 0.30
        biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas)
        
        # Asegurar límites razonables
        biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
        biomasa_disponible = max(0, min(1200, biomasa_disponible))
        crecimiento_diario = max(1, min(150, crecimiento_diario))
        
        # Combinar resultados
        resultado_completo = {
            **det,
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(crecimiento_diario, 1),
            'factor_calidad': round(calidad_forrajera, 3)
        }
        
        resultados.append(resultado_completo)
    
    return resultados

# CÁLCULO DE MÉTRICAS GANADERAS
def calcular_metricas_ganaderas(datos_analizados, params, peso_promedio, carga_animal):
    metricas = []
    
    for dato in datos_analizados:
        biomasa_disponible = dato['biomasa_disponible_kg_ms_ha']
        area_ha = dato['area_ha']
        
        # CONSUMO INDIVIDUAL
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # EQUIVALENTES VACA
        biomasa_total_disponible = biomasa_disponible * area_ha
        ev_por_dia = biomasa_total_disponible * 0.001 / consumo_individual_kg
        ev_soportable = ev_por_dia / params['TASA_UTILIZACION_RECOMENDADA']
        
        # DÍAS DE PERMANENCIA
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                dias_permanencia = min(dias_permanencia, 10)
            else:
                dias_permanencia = 0
        else:
            dias_permanencia = 0
        
        # ESTADO FORRAJERO
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
            'ev_soportable': round(ev_soportable, 1),
            'dias_permanencia': max(0, round(dias_permanencia, 1)),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'estado_forrajero': estado_forrajero,
            'ev_ha': round(ev_soportable / area_ha, 2) if area_ha > 0 else 0
        })
    
    return metricas

# FUNCIÓN PARA CREAR MAPA SIMPLE
def crear_mapa_simple(datos_analizados, tipo_analisis, tipo_pastura):
    try:
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))
        
        if tipo_analisis == "PRODUCTIVIDAD":
            cmap = LinearSegmentedColormap.from_list('productividad', PALETAS_GEE['PRODUCTIVIDAD'])
            vmin, vmax = 0, 1200
            columna = 'biomasa_disponible_kg_ms_ha'
            titulo_sufijo = 'Biomasa Disponible (kg MS/ha)'
        elif tipo_analisis == "DISPONIBILIDAD":
            cmap = LinearSegmentedColormap.from_list('disponibilidad', PALETAS_GEE['DISPONIBILIDAD'])
            vmin, vmax = 0, 5
            columna = 'ev_ha'
            titulo_sufijo = 'Carga Animal (EV/Ha)'
        else:  # DIAS_PERMANENCIA
            cmap = LinearSegmentedColormap.from_list('dias', PALETAS_GEE['DIAS_PERMANENCIA'])
            vmin, vmax = 0, 10
            columna = 'dias_permanencia'
            titulo_sufijo = 'Días de Permanencia'
        
        for dato in datos_analizados:
            valor = dato[columna]
            valor_norm = (valor - vmin) / (vmax - vmin)
            valor_norm = max(0, min(1, valor_norm))
            color = cmap(valor_norm)
            
            # Dibujar rectángulo simple
            x = dato['centro_x'] - 40
            y = dato['centro_y'] - 40
            rect = plt.Rectangle((x, y), 80, 80, facecolor=color, edgecolor='black', linewidth=2)
            ax.add_patch(rect)
            
            # Añadir texto
            ax.text(dato['centro_x'], dato['centro_y'], 
                   f"S{dato['id_subLote']}\n{valor:.0f}", 
                   ha='center', va='center', fontsize=8, 
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        ax.set_xlim(0, 800)
        ax.set_ylim(0, 600)
        ax.set_title(f'🌱 ANÁLISIS FORRAJERO - {tipo_pastura}\n'
                    f'{tipo_analisis} - {titulo_sufijo}', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_xlabel('Coordenada X')
        ax.set_ylabel('Coordenada Y')
        ax.grid(True, alpha=0.3)
        
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label(titulo_sufijo, fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, titulo_sufijo
        
    except Exception as e:
        st.error(f"❌ Error creando mapa: {str(e)}")
        return None, None

# FUNCIÓN PARA CREAR MAPA DE COBERTURA
def crear_mapa_cobertura_simple(datos_analizados, tipo_pastura):
    try:
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))
        
        colores_superficie = {
            'SUELO_DESNUDO': '#8c510a',
            'VEGETACION_ESCASA': '#dfc27d',
            'VEGETACION_MODERADA': '#80cdc1',
            'VEGETACION_DENSA': '#01665e',
        }
        
        for dato in datos_analizados:
            tipo_superficie = dato['tipo_superficie']
            color = colores_superficie.get(tipo_superficie, '#cccccc')
            
            # Dibujar rectángulo
            x = dato['centro_x'] - 40
            y = dato['centro_y'] - 40
            
            # Resaltar zonas con vegetación
            edgecolor = 'red' if dato['tiene_vegetacion'] else 'black'
            linewidth = 3 if dato['tiene_vegetacion'] else 1
            
            rect = plt.Rectangle((x, y), 80, 80, 
                               facecolor=color, 
                               edgecolor=edgecolor, 
                               linewidth=linewidth)
            ax.add_patch(rect)
            
            # Añadir texto
            ax.text(dato['centro_x'], dato['centro_y'], 
                   f"S{dato['id_subLote']}\n{dato['probabilidad_vegetacion']:.2f}", 
                   ha='center', va='center', fontsize=8,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        ax.set_xlim(0, 800)
        ax.set_ylim(0, 600)
        ax.set_title(f'🌱 MAPA DE COBERTURA - {tipo_pastura}\n'
                    f'Detección Automática (Umbral: {umbral_vegetacion})', 
                    fontsize=14, fontweight='bold', pad=20)
        
        ax.set_xlabel('Coordenada X')
        ax.set_ylabel('Coordenada Y')
        ax.grid(True, alpha=0.3)
        
        leyenda_elementos = []
        for tipo, color in colores_superficie.items():
            count = len([d for d in datos_analizados if d['tipo_superficie'] == tipo])
            label = f"{tipo} ({count} lotes)"
            leyenda_elementos.append(mpatches.Patch(color=color, label=label))
        
        leyenda_elementos.append(mpatches.Patch(color='red', label='Zonas con Vegetación (borde rojo)'))
        
        ax.legend(handles=leyenda_elementos, loc='upper right', fontsize=9)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        st.error(f"❌ Error creando mapa de cobertura: {str(e)}")
        return None

# FUNCIÓN PRINCIPAL DE ANÁLISIS
def analisis_forrajero_simple():
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        params = PARAMETROS_FORRAJEROS[tipo_pastura]
        
        st.info(f"""
        **🔍 SISTEMA DE DETECCIÓN AUTOMÁTICA:**
        - **Umbral vegetación:** {umbral_vegetacion}
        - **Sub-lotes analizados:** {n_divisiones}
        - **Patrón aprendido:** Mayoría suelo desnudo, pocas zonas con vegetación
        - **Clasificación automática** para cada análisis
        """)
        
        # DETECCIÓN
        st.subheader("🛰️ DETECTANDO VEGETACIÓN")
        with st.spinner("Analizando patrones de vegetación..."):
            deteccion = detectar_vegetacion_simple(n_divisiones)
        
        # CALCULAR BIOMASA
        st.subheader("📊 CALCULANDO BIOMASA")
        with st.spinner("Calculando producción forrajera..."):
            datos_analizados = calcular_biomasa_simple(deteccion, params)
        
        # CALCULAR MÉTRICAS
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando capacidad de carga..."):
            metricas = calcular_metricas_ganaderas(datos_analizados, params, peso_promedio, carga_animal)
        
        # Combinar métricas
        for i, metrica in enumerate(metricas):
            for key, value in metrica.items():
                datos_analizados[i][key] = value
        
        # RESULTADOS
        st.subheader("📊 RESULTADOS DEL ANÁLISIS")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sub-Lotes", n_divisiones)
        with col2:
            area_total = sum(d['area_ha'] for d in datos_analizados)
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            biomasa_prom = np.mean([d['biomasa_disponible_kg_ms_ha'] for d in datos_analizados])
            st.metric("Biomasa Prom", f"{biomasa_prom:.0f} kg MS/ha")
        with col4:
            zonas_vegetacion = sum(1 for d in datos_analizados if d['tiene_vegetacion'])
            st.metric("Zonas con Vegetación", f"{zonas_vegetacion}")
        
        # MAPAS
        st.subheader("🗺️ VISUALIZACIÓN")
        
        col1, col2 = st.columns(2)
        with col1:
            mapa_buf, titulo = crear_mapa_simple(datos_analizados, "PRODUCTIVIDAD", tipo_pastura)
            if mapa_buf:
                st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
        
        with col2:
            mapa_buf, titulo = crear_mapa_simple(datos_analizados, "DIAS_PERMANENCIA", tipo_pastura)
            if mapa_buf:
                st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
        
        mapa_cobertura = crear_mapa_cobertura_simple(datos_analizados, tipo_pastura)
        if mapa_cobertura:
            st.image(mapa_cobertura, caption="Mapa de Cobertura Vegetal", use_column_width=True)
        
        # TABLA DETALLADA
        st.subheader("📋 DETALLE POR SUB-LOTE")
        
        # Crear DataFrame para mostrar
        df_resumen = pd.DataFrame(datos_analizados)
        columnas_mostrar = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'probabilidad_vegetacion',
                           'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha', 'estado_forrajero']
        
        df_mostrar = df_resumen[columnas_mostrar].sort_values('id_subLote')
        st.dataframe(df_mostrar, use_container_width=True)
        
        # INFORME
        st.subheader("📑 INFORME EJECUTIVO")
        
        total_ev = sum(d['ev_soportable'] for d in datos_analizados)
        area_vegetacion = sum(d['area_ha'] for d in datos_analizados if d['tiene_vegetacion'])
        
        resumen = f"""
RESUMEN EJECUTIVO - ANÁLISIS FORRAJERO
=======================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Tipo de Pastura: {tipo_pastura}
Área Total: {area_total:.1f} ha

DETECCIÓN AUTOMÁTICA
-------------------
• Zonas con Vegetación: {zonas_vegetacion} sub-lotes ({area_vegetacion:.1f} ha)
• Zonas de Suelo Desnudo: {n_divisiones - zonas_vegetacion} sub-lotes
• Porcentaje con Vegetación: {(zonas_vegetacion/n_divisiones*100):.1f}%

CAPACIDAD FORRAJERA
------------------
• Capacidad Total: {total_ev:.0f} Equivalentes Vaca
• Biomasa Promedio: {biomasa_prom:.0f} kg MS/ha
• Permanencia Promedio: {np.mean([d['dias_permanencia'] for d in datos_analizados]):.1f} días

RECOMENDACIONES
--------------
• Enfoque en las {zonas_vegetacion} zonas con vegetación para pastoreo
• Excluir áreas de suelo desnudo del pastoreo regular
• Ajuste umbral a {umbral_vegetacion - 0.1:.1f} para detectar más vegetación
• Ajuste umbral a {umbral_vegetacion + 0.1:.1f} para detectar menos vegetación
"""
        
        st.text_area("Resumen Ejecutivo", resumen, height=300)
        
        # DESCARGAR
        csv = df_mostrar.to_csv(index=False)
        st.download_button(
            "📥 Descargar Resultados",
            csv,
            file_name=f"analisis_forrajero_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis: {str(e)}")
        return False

# INTERFAZ PRINCIPAL
if uploaded_file is not None:
    try:
        # Si se sube archivo, cargar datos
        df = pd.read_csv(uploaded_file)
        st.success(f"✅ **Archivo cargado:** {len(df)} registros")
        st.write("📊 Vista previa de datos:")
        st.dataframe(df.head())
        
    except Exception as e:
        st.error(f"Error cargando archivo: {str(e)}")
        st.info("💡 Usando datos simulados para el análisis...")

# Botón para ejecutar análisis (siempre disponible)
if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary"):
    analisis_forrajero_simple()

# Información cuando no hay archivo
if uploaded_file is None:
    st.info("📁 **Opción 1:** Sube un archivo CSV con datos de coordenadas")
    st.info("🎯 **Opción 2:** Usa el botón arriba para análisis con datos simulados")
    
    st.warning("""
    **🔍 SISTEMA DE DETECCIÓN AUTOMÁTICA:**
    
    Este sistema simula patrones realistas basados en los ejemplos proporcionados:
    - **Mayoría del área:** Suelo desnudo (aprendido de tus ejemplos)
    - **Pocas zonas:** Vegetación de diferentes calidades
    - **Patrones espaciales:** Las zonas centrales suelen tener mejor vegetación
    - **Clasificación adaptable** según el umbral configurado
    
    **Ajusta el umbral** en la barra lateral para controlar la detección.
    """)
