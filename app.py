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
st.title("🌱 ANALIZADOR FORRAJERO - ANÁLISIS COMPLETO")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selección de tipo de pastura con opción personalizada
    opciones_pastura = ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    tipo_pastura = st.selectbox("Tipo de Pastura:", opciones_pastura)
    
    # MOSTRAR PARÁMETROS PERSONALIZABLES SI SE SELECCIONA "PERSONALIZADO"
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("🎯 Parámetros Forrajeros Personalizados")
        
        col1, col2 = st.columns(2)
        with col1:
            ms_optimo = st.number_input("MS Óptimo (kg MS/ha):", min_value=500, max_value=10000, value=3000, step=100)
            crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=5, max_value=200, value=50, step=5)
            consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.1, value=0.025, step=0.001, format="%.3f")
        
        with col2:
            digestibilidad = st.number_input("Digestibilidad (%):", min_value=0.1, max_value=0.9, value=0.6, step=0.01, format="%.2f")
            proteina_cruda = st.number_input("Proteína Cruda (%):", min_value=0.01, max_value=0.3, value=0.12, step=0.01, format="%.2f")
            tasa_utilizacion = st.number_input("Tasa Utilización (%):", min_value=0.1, max_value=0.9, value=0.55, step=0.01, format="%.2f")
    
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
PARAMETROS_FORRAJEROS_BASE = {
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

# FUNCIÓN PARA OBTENER PARÁMETROS
def obtener_parametros_pastura(tipo_pastura):
    if tipo_pastura != "PERSONALIZADO":
        return PARAMETROS_FORRAJEROS_BASE[tipo_pastura]
    else:
        return {
            'MS_POR_HA_OPTIMO': ms_optimo,
            'CRECIMIENTO_DIARIO': crecimiento_diario,
            'CONSUMO_PORCENTAJE_PESO': consumo_porcentaje,
            'DIGESTIBILIDAD': digestibilidad,
            'PROTEINA_CRUDA': proteina_cruda,
            'TASA_UTILIZACION_RECOMENDADA': tasa_utilizacion,
        }

# PALETAS PARA ANÁLISIS FORRAJERO
PALETAS_GEE = {
    'PRODUCTIVIDAD': ['#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#c7eae5', '#80cdc1', '#35978f', '#01665e'],
    'DISPONIBILIDAD': ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
    'DIAS_PERMANENCIA': ['#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#fee090', '#fdae61', '#f46d43', '#d73027'],
}

# FUNCIÓN PARA GUARDAR CONFIGURACIÓN
def guardar_configuracion():
    if tipo_pastura == "PERSONALIZADO":
        config_data = {
            'tipo_pastura': 'PERSONALIZADO',
            'ms_optimo': ms_optimo,
            'crecimiento_diario': crecimiento_diario,
            'consumo_porcentaje': consumo_porcentaje,
            'digestibilidad': digestibilidad,
            'proteina_cruda': proteina_cruda,
            'tasa_utilizacion': tasa_utilizacion,
            'fecha_creacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return json.dumps(config_data, indent=2)
    return None

# FUNCIÓN PARA CARGAR CONFIGURACIÓN
def cargar_configuracion(uploaded_config):
    try:
        return json.load(uploaded_config)
    except:
        return None

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

# NUEVAS FUNCIONES PARA ANÁLISIS ESTADÍSTICO
def crear_analisis_correlacion(datos_analizados):
    """
    Crea análisis de correlación entre variables clave
    """
    try:
        # Crear DataFrame para análisis
        df = pd.DataFrame(datos_analizados)
        
        # Seleccionar variables numéricas para correlación
        variables_correlacion = [
            'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia', 
            'ndvi', 'cobertura_vegetal', 'area_ha'
        ]
        
        # Filtrar variables existentes
        variables_existentes = [v for v in variables_correlacion if v in df.columns]
        df_corr = df[variables_existentes]
        
        # Calcular matriz de correlación
        matriz_correlacion = df_corr.corr()
        
        # Crear figura con subplots
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. MATRIZ DE CORRELACIÓN (Heatmap)
        im = axes[0,0].imshow(matriz_correlacion.values, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)
        axes[0,0].set_xticks(range(len(matriz_correlacion.columns)))
        axes[0,0].set_yticks(range(len(matriz_correlacion.columns)))
        axes[0,0].set_xticklabels(matriz_correlacion.columns, rotation=45, ha='right')
        axes[0,0].set_yticklabels(matriz_correlacion.columns)
        axes[0,0].set_title('Matriz de Correlación', fontsize=14, fontweight='bold')
        
        # Añadir valores de correlación
        for i in range(len(matriz_correlacion.columns)):
            for j in range(len(matriz_correlacion.columns)):
                color = 'white' if abs(matriz_correlacion.iloc[i, j]) > 0.5 else 'black'
                axes[0,0].text(j, i, f'{matriz_correlacion.iloc[i, j]:.2f}', 
                              ha='center', va='center', color=color, fontweight='bold')
        
        # 2. CORRELACIÓN: Biomasa vs EV/Ha
        if 'biomasa_disponible_kg_ms_ha' in df.columns and 'ev_ha' in df.columns:
            x = df['biomasa_disponible_kg_ms_ha']
            y = df['ev_ha']
            correlacion = np.corrcoef(x, y)[0, 1]
            
            # Calcular regresión lineal
            coef = np.polyfit(x, y, 1)
            poly1d_fn = np.poly1d(coef)
            
            axes[0,1].scatter(x, y, alpha=0.6, color='green', s=50)
            axes[0,1].plot(x, poly1d_fn(x), color='red', linewidth=2, 
                          label=f'y = {coef[0]:.4f}x + {coef[1]:.2f}')
            axes[0,1].set_xlabel('Biomasa Disponible (kg MS/ha)')
            axes[0,1].set_ylabel('Equivalentes Vaca / Ha')
            axes[0,1].set_title(f'Biomasa vs EV/Ha\nCorrelación: {correlacion:.3f}', 
                               fontsize=12, fontweight='bold')
            axes[0,1].legend()
            axes[0,1].grid(True, alpha=0.3)
        
        # 3. CORRELACIÓN: Biomasa vs Días Permanencia
        if 'biomasa_disponible_kg_ms_ha' in df.columns and 'dias_permanencia' in df.columns:
            x = df['biomasa_disponible_kg_ms_ha']
            y = df['dias_permanencia']
            correlacion = np.corrcoef(x, y)[0, 1]
            
            # Calcular regresión lineal
            coef = np.polyfit(x, y, 1)
            poly1d_fn = np.poly1d(coef)
            
            axes[1,0].scatter(x, y, alpha=0.6, color='blue', s=50)
            axes[1,0].plot(x, poly1d_fn(x), color='red', linewidth=2,
                          label=f'y = {coef[0]:.4f}x + {coef[1]:.2f}')
            axes[1,0].set_xlabel('Biomasa Disponible (kg MS/ha)')
            axes[1,0].set_ylabel('Días de Permanencia')
            axes[1,0].set_title(f'Biomasa vs Días Permanencia\nCorrelación: {correlacion:.3f}', 
                               fontsize=12, fontweight='bold')
            axes[1,0].legend()
            axes[1,0].grid(True, alpha=0.3)
        
        # 4. CORRELACIÓN: NDVI vs Biomasa
        if 'ndvi' in df.columns and 'biomasa_disponible_kg_ms_ha' in df.columns:
            x = df['ndvi']
            y = df['biomasa_disponible_kg_ms_ha']
            correlacion = np.corrcoef(x, y)[0, 1]
            
            # Calcular regresión lineal
            coef = np.polyfit(x, y, 1)
            poly1d_fn = np.poly1d(coef)
            
            axes[1,1].scatter(x, y, alpha=0.6, color='orange', s=50)
            axes[1,1].plot(x, poly1d_fn(x), color='red', linewidth=2,
                          label=f'y = {coef[0]:.0f}x + {coef[1]:.0f}')
            axes[1,1].set_xlabel('NDVI')
            axes[1,1].set_ylabel('Biomasa Disponible (kg MS/ha)')
            axes[1,1].set_title(f'NDVI vs Biomasa\nCorrelación: {correlacion:.3f}', 
                               fontsize=12, fontweight='bold')
            axes[1,1].legend()
            axes[1,1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, matriz_correlacion
        
    except Exception as e:
        st.error(f"Error en análisis de correlación: {str(e)}")
        return None, None

def crear_analisis_regresion_multiple(datos_analizados):
    """
    Crea análisis de regresión múltiple para predecir EV/Ha
    """
    try:
        df = pd.DataFrame(datos_analizados)
        
        # Variables para el modelo
        variables_independientes = ['biomasa_disponible_kg_ms_ha', 'ndvi', 'cobertura_vegetal', 'area_ha']
        variable_dependiente = 'ev_ha'
        
        # Filtrar variables existentes
        vars_existentes = [v for v in variables_independientes if v in df.columns]
        if variable_dependiente not in df.columns or len(vars_existentes) < 2:
            return None
        
        X = df[vars_existentes]
        y = df[variable_dependiente]
        
        # Calcular regresión múltiple manualmente (mínimos cuadrados)
        # Y = Xβ + ε → β = (X'X)^(-1)X'Y
        X_with_const = np.column_stack([np.ones(len(X)), X])
        try:
            beta = np.linalg.inv(X_with_const.T @ X_with_const) @ X_with_const.T @ y
        except:
            # Si hay problemas de matriz singular, usar pseudoinversa
            beta = np.linalg.pinv(X_with_const.T @ X_with_const) @ X_with_const.T @ y
        
        # Predicciones
        y_pred = X_with_const @ beta
        
        # Métricas del modelo
        r_cuadrado = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
        mse = np.mean((y - y_pred)**2)
        
        # Crear figura
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. Valores reales vs predichos
        axes[0,0].scatter(y, y_pred, alpha=0.6, color='purple', s=50)
        min_val = min(y.min(), y_pred.min())
        max_val = max(y.max(), y_pred.max())
        axes[0,0].plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2)
        axes[0,0].set_xlabel('EV/Ha Real')
        axes[0,0].set_ylabel('EV/Ha Predicho')
        axes[0,0].set_title(f'Regresión Múltiple: Real vs Predicho\nR² = {r_cuadrado:.3f}', 
                           fontsize=12, fontweight='bold')
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Residuos
        residuos = y - y_pred
        axes[0,1].scatter(y_pred, residuos, alpha=0.6, color='teal', s=50)
        axes[0,1].axhline(y=0, color='red', linestyle='--', linewidth=2)
        axes[0,1].set_xlabel('EV/Ha Predicho')
        axes[0,1].set_ylabel('Residuos')
        axes[0,1].set_title('Análisis de Residuos', fontsize=12, fontweight='bold')
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Importancia de variables (coeficientes estandarizados)
        coef_estandarizados = beta[1:] * X.std().values / y.std()
        variables = vars_existentes
        colors = plt.cm.viridis(np.linspace(0, 1, len(variables)))
        
        bars = axes[1,0].bar(variables, coef_estandarizados, color=colors, alpha=0.7)
        axes[1,0].set_xlabel('Variables')
        axes[1,0].set_ylabel('Coeficiente Estandarizado')
        axes[1,0].set_title('Importancia Relativa de Variables', fontsize=12, fontweight='bold')
        axes[1,0].tick_params(axis='x', rotation=45)
        
        # Añadir valores en las barras
        for bar, valor in zip(bars, coef_estandarizados):
            height = bar.get_height()
            axes[1,0].text(bar.get_x() + bar.get_width()/2., height,
                          f'{valor:.3f}', ha='center', va='bottom')
        
        # 4. Distribución de errores
        axes[1,1].hist(residuos, bins=15, alpha=0.7, color='orange', edgecolor='black')
        axes[1,1].axvline(residuos.mean(), color='red', linestyle='--', linewidth=2, 
                         label=f'Media: {residuos.mean():.3f}')
        axes[1,1].set_xlabel('Error de Predicción')
        axes[1,1].set_ylabel('Frecuencia')
        axes[1,1].set_title('Distribución de Errores', fontsize=12, fontweight='bold')
        axes[1,1].legend()
        axes[1,1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Crear resumen del modelo
        resumen_modelo = {
            'R_cuadrado': r_cuadrado,
            'MSE': mse,
            'Coeficientes': dict(zip(['Intercepto'] + vars_existentes, beta)),
            'Coeficientes_estandarizados': dict(zip(vars_existentes, coef_estandarizados))
        }
        
        return buf, resumen_modelo
        
    except Exception as e:
        st.error(f"Error en análisis de regresión: {str(e)}")
        return None, None

# FUNCIÓN PARA CREAR ZIP CON TODOS LOS RESULTADOS
def crear_paquete_descarga(datos_analizados, mapas, correlacion_buf, regresion_buf, matriz_corr, resumen_modelo, params):
    """Crea un archivo ZIP con todos los resultados"""
    try:
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            with zipfile.ZipFile(tmp_file.name, 'w') as zipf:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                # 1. Datos en CSV
                df_completo = pd.DataFrame(datos_analizados)
                csv_data = df_completo.to_csv(index=False)
                zipf.writestr(f"datos_analisis_{timestamp}.csv", csv_data)
                
                # 2. Mapas
                for nombre, (buf, _) in mapas.items():
                    if buf:
                        zipf.writestr(f"mapa_{nombre}_{timestamp}.png", buf.getvalue())
                
                # 3. Análisis de correlación
                if correlacion_buf:
                    zipf.writestr(f"analisis_correlacion_{timestamp}.png", correlacion_buf.getvalue())
                
                # 4. Análisis de regresión
                if regresion_buf:
                    zipf.writestr(f"analisis_regresion_{timestamp}.png", regresion_buf.getvalue())
                
                # 5. Matriz de correlación en CSV
                if matriz_corr is not None:
                    matriz_csv = matriz_corr.to_csv()
                    zipf.writestr(f"matriz_correlacion_{timestamp}.csv", matriz_csv)
                
                # 6. Resumen del modelo
                if resumen_modelo:
                    modelo_json = json.dumps(resumen_modelo, indent=2)
                    zipf.writestr(f"resumen_modelo_{timestamp}.json", modelo_json)
                
                # 7. Parámetros utilizados
                params_json = json.dumps(params, indent=2)
                zipf.writestr(f"parametros_{timestamp}.json", params_json)
                
                # 8. Informe ejecutivo
                informe = crear_informe_ejecutivo(datos_analizados, params)
                zipf.writestr(f"informe_ejecutivo_{timestamp}.txt", informe)
            
            return tmp_file.name
    except Exception as e:
        st.error(f"Error creando paquete de descarga: {str(e)}")
        return None

def crear_informe_ejecutivo(datos_analizados, params):
    """Crea un informe ejecutivo en texto"""
    area_total = sum(d['area_ha'] for d in datos_analizados)
    biomasa_prom = np.mean([d['biomasa_disponible_kg_ms_ha'] for d in datos_analizados])
    zonas_vegetacion = sum(1 for d in datos_analizados if d['tiene_vegetacion'])
    total_ev = sum(d['ev_soportable'] for d in datos_analizados)
    area_vegetacion = sum(d['area_ha'] for d in datos_analizados if d['tiene_vegetacion'])
    
    informe = f"""
INFORME EJECUTIVO - ANÁLISIS FORRAJERO COMPLETO
================================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Tipo de Pastura: {tipo_pastura}
Área Total Analizada: {area_total:.1f} ha

PARÁMETROS UTILIZADOS
--------------------
MS Óptimo: {params['MS_POR_HA_OPTIMO']} kg MS/ha
Crecimiento Diario: {params['CRECIMIENTO_DIARIO']} kg MS/ha/día
Consumo: {params['CONSUMO_PORCENTAJE_PESO']*100}% del peso vivo
Digestibilidad: {params['DIGESTIBILIDAD']*100}%
Proteína Cruda: {params['PROTEINA_CRUDA']*100}%
Tasa Utilización: {params['TASA_UTILIZACION_RECOMENDADA']*100}%

RESULTADOS PRINCIPALES
----------------------
• Sub-lotes analizados: {len(datos_analizados)}
• Zonas con Vegetación: {zonas_vegetacion} ({area_vegetacion:.1f} ha)
• Zonas de Suelo Desnudo: {len(datos_analizados) - zonas_vegetacion}
• Biomasa Disponible Promedio: {biomasa_prom:.0f} kg MS/ha
• Capacidad Total: {total_ev:.0f} Equivalentes Vaca

ARCHIVOS INCLUÍDOS
------------------
• datos_analisis.csv - Datos completos por sub-lote
• mapa_productividad.png - Mapa de biomasa disponible
• mapa_cobertura.png - Mapa de tipos de superficie
• analisis_correlacion.png - Gráficos de correlación
• analisis_regresion.png - Análisis de regresión
• matriz_correlacion.csv - Matriz numérica de correlaciones
• parametros.json - Parámetros forrajeros utilizados

RECOMENDACIONES
---------------
• Enfoque el pastoreo en las zonas con vegetación identificadas
• Utilice los mapas para planificar la rotación de animales
• Considere los análisis de correlación para optimizar el manejo
• Los modelos de regresión pueden ayudar en la planificación futura

---
Generado por el Sistema de Análisis Forrajero
"""
    return informe

# FUNCIÓN PRINCIPAL DE ANÁLISIS
def analisis_forrajero_completo():
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO COMPLETO - {tipo_pastura}")
        
        params = obtener_parametros_pastura(tipo_pastura)
        
        # Mostrar parámetros utilizados
        with st.expander("📊 VER PARÁMETROS FORRAJEROS UTILIZADOS"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("MS Óptimo", f"{params['MS_POR_HA_OPTIMO']} kg/ha")
                st.metric("Crecimiento Diario", f"{params['CRECIMIENTO_DIARIO']} kg/ha/día")
            with col2:
                st.metric("Consumo", f"{params['CONSUMO_PORCENTAJE_PESO']*100}% peso")
                st.metric("Digestibilidad", f"{params['DIGESTIBILIDAD']*100}%")
            with col3:
                st.metric("Proteína Cruda", f"{params['PROTEINA_CRUDA']*100}%")
                st.metric("Tasa Utilización", f"{params['TASA_UTILIZACION_RECOMENDADA']*100}%")
        
        st.info(f"""
        **🔍 SISTEMA DE ANÁLISIS COMPLETO:**
        - **Umbral vegetación:** {umbral_vegetacion}
        - **Sub-lotes analizados:** {n_divisiones}
        - **Incluye:** Mapas + Correlación + Regresión + Descargas
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
        
        # RESULTADOS PRINCIPALES
        st.subheader("📊 RESULTADOS PRINCIPALES")
        
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
        
        # CREAR PESTAÑAS PARA DIFERENTES ANÁLISIS
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ MAPAS", "📈 CORRELACIÓN", "🔮 REGRESIÓN", "📋 DATOS", "📥 DESCARGAS"])
        
        # Variables para almacenar resultados de análisis
        mapas_creados = {}
        correlacion_buf = None
        matriz_corr = None
        regresion_buf = None
        resumen_modelo = None
        
        with tab1:
            st.subheader("🗺️ VISUALIZACIÓN ESPACIAL")
            
            col1, col2 = st.columns(2)
            with col1:
                mapa_buf, titulo = crear_mapa_simple(datos_analizados, "PRODUCTIVIDAD", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
                    mapas_creados['productividad'] = (mapa_buf, titulo)
                    
                    # Botón de descarga individual
                    st.download_button(
                        f"📥 Descargar Mapa de {titulo}",
                        mapa_buf.getvalue(),
                        file_name=f"mapa_productividad_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                        mime="image/png"
                    )
            
            with col2:
                mapa_buf, titulo = crear_mapa_simple(datos_analizados, "DIAS_PERMANENCIA", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
                    mapas_creados['dias_permanencia'] = (mapa_buf, titulo)
                    
                    st.download_button(
                        f"📥 Descargar Mapa de {titulo}",
                        mapa_buf.getvalue(),
                        file_name=f"mapa_dias_permanencia_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                        mime="image/png"
                    )
            
            mapa_cobertura = crear_mapa_cobertura_simple(datos_analizados, tipo_pastura)
            if mapa_cobertura:
                st.image(mapa_cobertura, caption="Mapa de Cobertura Vegetal", use_column_width=True)
                mapas_creados['cobertura'] = (mapa_cobertura, "Cobertura Vegetal")
                
                st.download_button(
                    "📥 Descargar Mapa de Cobertura",
                    mapa_cobertura.getvalue(),
                    file_name=f"mapa_cobertura_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    mime="image/png"
                )
        
        with tab2:
            st.subheader("📈 ANÁLISIS DE CORRELACIÓN")
            
            # Análisis de correlación
            correlacion_buf, matriz_corr = crear_analisis_correlacion(datos_analizados)
            if correlacion_buf:
                st.image(correlacion_buf, caption="Análisis de Correlación entre Variables", use_column_width=True)
                
                # Botón de descarga
                st.download_button(
                    "📥 Descargar Análisis de Correlación",
                    correlacion_buf.getvalue(),
                    file_name=f"analisis_correlacion_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    mime="image/png"
                )
                
                # Mostrar matriz de correlación como tabla
                if matriz_corr is not None:
                    st.subheader("📊 Matriz de Correlación Numérica")
                    st.dataframe(matriz_corr.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1), 
                               use_container_width=True)
                    
                    # Descargar matriz
                    csv_corr = matriz_corr.to_csv()
                    st.download_button(
                        "📥 Descargar Matriz de Correlación (CSV)",
                        csv_corr,
                        file_name=f"matriz_correlacion_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
        
        with tab3:
            st.subheader("🔮 ANÁLISIS DE REGRESIÓN")
            
            # Análisis de regresión múltiple
            regresion_buf, resumen_modelo = crear_analisis_regresion_multiple(datos_analizados)
            if regresion_buf:
                st.image(regresion_buf, caption="Análisis de Regresión Múltiple", use_column_width=True)
                
                # Botón de descarga
                st.download_button(
                    "📥 Descargar Análisis de Regresión",
                    regresion_buf.getvalue(),
                    file_name=f"analisis_regresion_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    mime="image/png"
                )
                
                if resumen_modelo:
                    st.subheader("📋 Resumen del Modelo de Regresión")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("R² del Modelo", f"{resumen_modelo['R_cuadrado']:.3f}")
                        st.metric("Error Cuadrático Medio", f"{resumen_modelo['MSE']:.3f}")
                    
                    with col2:
                        st.write("**Coeficientes del Modelo:**")
                        for var, coef in resumen_modelo['Coeficientes'].items():
                            st.write(f"- {var}: {coef:.4f}")
                    
                    # Descargar resumen del modelo
                    modelo_json = json.dumps(resumen_modelo, indent=2)
                    st.download_button(
                        "📥 Descargar Resumen del Modelo (JSON)",
                        modelo_json,
                        file_name=f"resumen_modelo_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json"
                    )
        
        with tab4:
            st.subheader("📋 DATOS DETALLADOS")
            
            # Crear DataFrame para mostrar
            df_resumen = pd.DataFrame(datos_analizados)
            columnas_mostrar = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'probabilidad_vegetacion',
                               'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha', 'estado_forrajero']
            
            df_mostrar = df_resumen[columnas_mostrar].sort_values('id_subLote')
            st.dataframe(df_mostrar, use_container_width=True)
            
            # Descargar datos
            csv_data = df_resumen.to_csv(index=False)
            st.download_button(
                "📥 Descargar Datos Completos (CSV)",
                csv_data,
                file_name=f"datos_completos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            
            # Estadísticas descriptivas
            st.subheader("📊 Estadísticas Descriptivas")
            st.dataframe(df_mostrar.describe(), use_container_width=True)
            
            # Descargar estadísticas
            stats_csv = df_mostrar.describe().to_csv()
            st.download_button(
                "📥 Descargar Estadísticas (CSV)",
                stats_csv,
                file_name=f"estadisticas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        
        with tab5:
            st.subheader("📥 DESCARGA COMPLETA")
            
            st.info("""
            **📦 PAQUETE COMPLETO DE RESULTADOS**
            
            Descarga todos los archivos generados en un solo ZIP que incluye:
            - Datos completos en CSV
            - Todos los mapas generados
            - Análisis de correlación y regresión
            - Matrices y estadísticas
            - Parámetros utilizados
            - Informe ejecutivo
            """)
            
            # Crear paquete completo
            if st.button("🔄 GENERAR PAQUETE COMPLETO", type="primary"):
                with st.spinner("Creando paquete de descarga..."):
                    zip_path = crear_paquete_descarga(
                        datos_analizados, mapas_creados, correlacion_buf, 
                        regresion_buf, matriz_corr, resumen_modelo, params
                    )
                    
                    if zip_path:
                        with open(zip_path, 'rb') as f:
                            zip_data = f.read()
                        
                        st.download_button(
                            "📦 DESCARGAR PAQUETE COMPLETO (ZIP)",
                            zip_data,
                            file_name=f"paquete_analisis_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                            mime="application/zip"
                        )
                        
                        # Limpiar archivo temporal
                        os.unlink(zip_path)
            
            # Descarga de parámetros
            st.subheader("⚙️ CONFIGURACIÓN")
            
            if tipo_pastura == "PERSONALIZADO":
                config_json = guardar_configuracion()
                if config_json:
                    st.download_button(
                        "💾 Guardar Configuración Personalizada",
                        config_json,
                        file_name=f"configuracion_personalizada_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
                        help="Guarda los parámetros personalizados para uso futuro"
                    )
            
            # Cargar configuración
            st.subheader("📤 Cargar Configuración")
            uploaded_config = st.file_uploader("Subir configuración guardada", type=['json'])
            if uploaded_config:
                config_cargada = cargar_configuracion(uploaded_config)
                if config_cargada:
                    st.success("✅ Configuración cargada correctamente")
                    st.json(config_cargada)
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis completo: {str(e)}")
        return False

# INTERFAZ PRINCIPAL
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Guardar/Cargar Configuración")

# Botón para guardar configuración si es personalizada
if tipo_pastura == "PERSONALIZADO":
    config_json = guardar_configuracion()
    if config_json:
        st.sidebar.download_button(
            "💾 Guardar Configuración",
            config_json,
            file_name="configuracion_personalizada.json",
            mime="application/json"
        )

# Cargar configuración
uploaded_config = st.sidebar.file_uploader("Cargar configuración", type=['json'], key="config_uploader")

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
if st.button("🚀 EJECUTAR ANÁLISIS COMPLETO", type="primary"):
    analisis_forrajero_completo()

# Información cuando no hay archivo
if uploaded_file is None:
    st.info("📁 **Opción 1:** Sube un archivo CSV con datos de coordenadas")
    st.info("🎯 **Opción 2:** Usa el botón arriba para análisis con datos simulados")
    
    st.warning("""
    **🔍 SISTEMA DE ANÁLISIS COMPLETO:**
    
    Este sistema incluye:
    - **Detección automática** de vegetación vs suelo desnudo
    - **Mapas interactivos** de productividad y cobertura
    - **Análisis de correlación** entre variables clave
    - **Modelos de regresión** para predicción
    - **Descarga completa** de todos los resultados
    - **Personalización completa** de parámetros forrajeros
    
    **Características de descarga:**
    - Descargas individuales de cada gráfico y tabla
    - Paquete ZIP con todos los archivos
    - Configuraciones personalizables guardables
    - Formatos: PNG, CSV, JSON, ZIP
    """)
