
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
import seaborn as sns
from scipy import stats
import base64

st.set_page_config(page_title="🌱 Analizador Forrajero", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - ANÁLISIS COMPLETO AVANZADO")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Selección de tipo de pastura
    opciones_pastura = ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    tipo_pastura = st.selectbox("Tipo de Pastura:", opciones_pastura)
    
    # Parámetros forrajeros personalizados
    st.subheader("🌿 Parámetros Forrajeros")
    
    if tipo_pastura == "PERSONALIZADO":
        ms_optimo = st.number_input("MS por Ha Óptimo (kg):", min_value=500, max_value=8000, value=3000, step=100)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=5, max_value=200, value=50, step=5)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.1, value=0.025, step=0.005, format="%.3f")
        digestibilidad = st.number_input("Digestibilidad:", min_value=0.1, max_value=0.9, value=0.6, step=0.05, format="%.2f")
        proteina_cruda = st.number_input("Proteína Cruda:", min_value=0.05, max_value=0.3, value=0.12, step=0.01, format="%.2f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.05, format="%.2f")
    else:
        # Mostrar parámetros actuales para referencia
        params_base = {
            'ALFALFA': {'MS_POR_HA_OPTIMO': 4000, 'CRECIMIENTO_DIARIO': 80, 'CONSUMO_PORCENTAJE_PESO': 0.03},
            'RAYGRASS': {'MS_POR_HA_OPTIMO': 3500, 'CRECIMIENTO_DIARIO': 70, 'CONSUMO_PORCENTAJE_PESO': 0.028},
            'FESTUCA': {'MS_POR_HA_OPTIMO': 3000, 'CRECIMIENTO_DIARIO': 50, 'CONSUMO_PORCENTAJE_PESO': 0.025},
            'AGROPIRRO': {'MS_POR_HA_OPTIMO': 2800, 'CRECIMIENTO_DIARIO': 45, 'CONSUMO_PORCENTAJE_PESO': 0.022},
            'PASTIZAL_NATURAL': {'MS_POR_HA_OPTIMO': 2500, 'CRECIMIENTO_DIARIO': 20, 'CONSUMO_PORCENTAJE_PESO': 0.020}
        }
        
        if tipo_pastura in params_base:
            st.info(f"**Parámetros actuales:**")
            st.write(f"MS Óptimo: {params_base[tipo_pastura]['MS_POR_HA_OPTIMO']} kg/ha")
            st.write(f"Crecimiento: {params_base[tipo_pastura]['CRECIMIENTO_DIARIO']} kg/día")
            st.write(f"Consumo: {params_base[tipo_pastura]['CONSUMO_PORCENTAJE_PESO']*100}% peso vivo")
    
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

# Actualizar parámetros si es personalizado
if tipo_pastura == "PERSONALIZADO":
    PARAMETROS_FORRAJEROS['PERSONALIZADO'] = {
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

# NUEVAS FUNCIONES PARA ANÁLISIS ESTADÍSTICO MEJORADO
def crear_analisis_correlacion_completo(datos_analizados):
    """
    Crea análisis de correlación completo con más métricas
    """
    try:
        # Crear DataFrame para análisis
        df = pd.DataFrame(datos_analizados)
        
        # Seleccionar variables numéricas para correlación
        variables_correlacion = [
            'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia', 
            'ndvi', 'cobertura_vegetal', 'area_ha', 'biomasa_ms_ha',
            'crecimiento_diario', 'factor_calidad'
        ]
        
        # Filtrar variables existentes
        variables_existentes = [v for v in variables_correlacion if v in df.columns]
        df_corr = df[variables_existentes]
        
        # Calcular matriz de correlación
        matriz_correlacion = df_corr.corr()
        
        # Calcular p-valores para correlaciones
        p_values = np.zeros((len(variables_existentes), len(variables_existentes)))
        for i in range(len(variables_existentes)):
            for j in range(len(variables_existentes)):
                if i != j:
                    corr, p_val = stats.pearsonr(df_corr.iloc[:, i], df_corr.iloc[:, j])
                    p_values[i, j] = p_val
                else:
                    p_values[i, j] = 0
        
        # Crear figura con subplots
        fig, axes = plt.subplots(2, 2, figsize=(18, 14))
        
        # 1. MATRIZ DE CORRELACIÓN (Heatmap mejorado)
        mask = np.triu(np.ones_like(matriz_correlacion, dtype=bool))
        sns.heatmap(matriz_correlacion, mask=mask, annot=True, cmap='coolwarm', 
                   center=0, square=True, linewidths=0.5, 
                   cbar_kws={"shrink": 0.8}, ax=axes[0,0])
        axes[0,0].set_title('Matriz de Correlación (Triangular)', fontsize=14, fontweight='bold')
        
        # 2. CORRELACIÓN: Biomasa vs EV/Ha con intervalo de confianza
        if 'biomasa_disponible_kg_ms_ha' in df.columns and 'ev_ha' in df.columns:
            x = df['biomasa_disponible_kg_ms_ha']
            y = df['ev_ha']
            correlacion = np.corrcoef(x, y)[0, 1]
            
            # Calcular regresión lineal con intervalo de confianza
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            line = slope * x + intercept
            
            axes[0,1].scatter(x, y, alpha=0.6, color='green', s=60)
            axes[0,1].plot(x, line, color='red', linewidth=2, 
                          label=f'y = {slope:.4f}x + {intercept:.2f}\nR² = {r_value**2:.3f}')
            
            # Añadir intervalo de confianza
            confidence = 0.95
            n = len(x)
            dof = n - 2
            t_value = stats.t.ppf((1 + confidence) / 2, dof)
            conf_interval = t_value * std_err * np.sqrt(1/n + (x - x.mean())**2 / np.sum((x - x.mean())**2))
            
            axes[0,1].fill_between(x, line - conf_interval, line + conf_interval, 
                                 alpha=0.3, color='red', label=f'{int(confidence*100)}% IC')
            
            axes[0,1].set_xlabel('Biomasa Disponible (kg MS/ha)')
            axes[0,1].set_ylabel('Equivalentes Vaca / Ha')
            axes[0,1].set_title(f'Biomasa vs EV/Ha\nCorrelación: {correlacion:.3f} (p = {p_value:.4f})', 
                               fontsize=12, fontweight='bold')
            axes[0,1].legend()
            axes[0,1].grid(True, alpha=0.3)
        
        # 3. CORRELACIÓN MÚLTIPLE: Matriz de dispersión
        if len(variables_existentes) >= 3:
            variables_para_pairplot = variables_existentes[:4]  # Tomar primeras 4 variables
            try:
                # Crear pairplot simplificado
                from pandas.plotting import scatter_matrix
                scatter_matrix(df[variables_para_pairplot], alpha=0.6, ax=axes[1,0], diagonal='hist')
                axes[1,0].set_title('Matriz de Dispersión - Variables Principales', 
                                   fontsize=12, fontweight='bold')
            except:
                # Fallback si hay error
                axes[1,0].text(0.5, 0.5, 'Matriz de dispersión no disponible', 
                              ha='center', va='center', transform=axes[1,0].transAxes)
                axes[1,0].set_title('Matriz de Dispersión', fontsize=12, fontweight='bold')
        
        # 4. CORRELACIONES SIGNIFICATIVAS
        axes[1,1].axis('off')
        correlaciones_significativas = []
        
        for i in range(len(matriz_correlacion.columns)):
            for j in range(i+1, len(matriz_correlacion.columns)):
                corr_val = matriz_correlacion.iloc[i, j]
                p_val = p_values[i, j]
                
                if abs(corr_val) > 0.3:  # Mostrar correlaciones moderadas y fuertes
                    significancia = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
                    correlaciones_significativas.append({
                        'Variables': f"{matriz_correlacion.columns[i]} - {matriz_correlacion.columns[j]}",
                        'Correlación': corr_val,
                        'p-valor': p_val,
                        'Significancia': significancia
                    })
        
        # Ordenar por valor absoluto de correlación
        correlaciones_significativas.sort(key=lambda x: abs(x['Correlación']), reverse=True)
        
        # Crear tabla en el subplot
        if correlaciones_significativas:
            table_data = []
            for corr in correlaciones_significativas[:8]:  # Mostrar top 8
                table_data.append([
                    corr['Variables'],
                    f"{corr['Correlación']:.3f}",
                    f"{corr['p-valor']:.4f}",
                    corr['Significancia']
                ])
            
            tabla = axes[1,1].table(cellText=table_data,
                                  colLabels=['Variables', 'Correlación', 'p-valor', 'Sig.'],
                                  loc='center',
                                  cellLoc='center')
            tabla.auto_set_font_size(False)
            tabla.set_fontsize(9)
            tabla.scale(1, 1.5)
            axes[1,1].set_title('Correlaciones Significativas', fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, matriz_correlacion, p_values, correlaciones_significativas
        
    except Exception as e:
        st.error(f"Error en análisis de correlación completo: {str(e)}")
        return None, None, None, None

def crear_analisis_regresion_multiple_completo(datos_analizados):
    """
    Crea análisis de regresión múltiple completo
    """
    try:
        df = pd.DataFrame(datos_analizados)
        
        # Variables para el modelo
        variables_independientes = [
            'biomasa_disponible_kg_ms_ha', 'ndvi', 'cobertura_vegetal', 
            'area_ha', 'crecimiento_diario', 'factor_calidad'
        ]
        variable_dependiente = 'ev_ha'
        
        # Filtrar variables existentes
        vars_existentes = [v for v in variables_independientes if v in df.columns]
        if variable_dependiente not in df.columns or len(vars_existentes) < 2:
            return None, None
        
        X = df[vars_existentes]
        y = df[variable_dependiente]
        
        # Calcular regresión múltiple
        X_with_const = np.column_stack([np.ones(len(X)), X])
        try:
            beta = np.linalg.inv(X_with_const.T @ X_with_const) @ X_with_const.T @ y
        except:
            beta = np.linalg.pinv(X_with_const.T @ X_with_const) @ X_with_const.T @ y
        
        # Predicciones
        y_pred = X_with_const @ beta
        
        # Métricas del modelo
        r_cuadrado = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
        mse = np.mean((y - y_pred)**2)
        rmse = np.sqrt(mse)
        mae = np.mean(np.abs(y - y_pred))
        
        # Estadísticas adicionales
        n = len(y)
        p = len(vars_existentes)
        r_cuadrado_ajustado = 1 - (1 - r_cuadrado) * (n - 1) / (n - p - 1)
        
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
        
        # 2. Residuos vs Predichos
        residuos = y - y_pred
        axes[0,1].scatter(y_pred, residuos, alpha=0.6, color='teal', s=50)
        axes[0,1].axhline(y=0, color='red', linestyle='--', linewidth=2)
        axes[0,1].set_xlabel('EV/Ha Predicho')
        axes[0,1].set_ylabel('Residuos')
        axes[0,1].set_title(f'Análisis de Residuos\nMAE = {mae:.3f}', fontsize=12, fontweight='bold')
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
                          f'{valor:.3f}', ha='center', va='bottom', fontsize=8)
        
        # 4. Distribución de errores con curva normal
        axes[1,1].hist(residuos, bins=15, alpha=0.7, color='orange', edgecolor='black', density=True)
        
        # Añadir curva normal
        x_norm = np.linspace(residuos.min(), residuos.max(), 100)
        y_norm = stats.norm.pdf(x_norm, residuos.mean(), residuos.std())
        axes[1,1].plot(x_norm, y_norm, 'r-', linewidth=2, label='Distribución Normal')
        
        axes[1,1].axvline(residuos.mean(), color='red', linestyle='--', linewidth=2, 
                         label=f'Media: {residuos.mean():.3f}')
        axes[1,1].set_xlabel('Error de Predicción')
        axes[1,1].set_ylabel('Densidad')
        axes[1,1].set_title('Distribución de Errores', fontsize=12, fontweight='bold')
        axes[1,1].legend()
        axes[1,1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Crear resumen del modelo completo
        resumen_modelo = {
            'R_cuadrado': r_cuadrado,
            'R_cuadrado_ajustado': r_cuadrado_ajustado,
            'MSE': mse,
            'RMSE': rmse,
            'MAE': mae,
            'Coeficientes': dict(zip(['Intercepto'] + vars_existentes, beta)),
            'Coeficientes_estandarizados': dict(zip(vars_existentes, coef_estandarizados)),
            'Ecuacion': f"EV/Ha = {beta[0]:.4f} + " + " + ".join([f"{beta[i+1]:.4f}*{var}" for i, var in enumerate(vars_existentes)])
        }
        
        return buf, resumen_modelo
        
    except Exception as e:
        st.error(f"Error en análisis de regresión completo: {str(e)}")
        return None, None

# FUNCIONES PARA DESCARGAR ARCHIVOS
def get_table_download_link(df, filename, link_text):
    """Genera un link para descargar un DataFrame como CSV"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{link_text}</a>'
    return href

def get_image_download_link(buf, filename, link_text):
    """Genera un link para descargar una imagen"""
    b64 = base64.b64encode(buf.getvalue()).decode()
    href = f'<a href="data:image/png;base64,{b64}" download="{filename}">{link_text}</a>'
    return href

def crear_zip_descarga(datos_analizados, mapas, graficos, tipo_pastura):
    """Crea un archivo ZIP con todos los resultados"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        # Agregar datos CSV
        df_completo = pd.DataFrame(datos_analizados)
        csv_data = df_completo.to_csv(index=False)
        zip_file.writestr(f"datos_analisis_{tipo_pastura}_{timestamp}.csv", csv_data)
        
        # Agregar imágenes
        for nombre, (buf, descripcion) in mapas.items():
            if buf:
                zip_file.writestr(f"mapa_{nombre}_{timestamp}.png", buf.getvalue())
        
        for nombre, (buf, descripcion) in graficos.items():
            if buf:
                zip_file.writestr(f"grafico_{nombre}_{timestamp}.png", buf.getvalue())
        
        # Agregar resumen en texto
        resumen = f"""
RESUMEN EJECUTIVO - ANÁLISIS FORRAJERO COMPLETO
================================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Tipo de Pastura: {tipo_pastura}
Sub-lotes analizados: {len(datos_analizados)}
Umbral de vegetación: {umbral_vegetacion}

ARCHIVOS INCLUIDOS:
------------------
- datos_analisis_*.csv: Datos completos del análisis
- mapa_*.png: Mapas de productividad y cobertura
- grafico_*.png: Gráficos de correlación y regresión

PARÁMETROS UTILIZADOS:
---------------------
Peso promedio animal: {peso_promedio} kg
Carga animal: {carga_animal} cabezas
Número de divisiones: {n_divisiones}
        """
        zip_file.writestr(f"resumen_analisis_{timestamp}.txt", resumen)
    
    zip_buffer.seek(0)
    return zip_buffer

# FUNCIÓN PRINCIPAL DE ANÁLISIS MEJORADA
def analisis_forrajero_completo_avanzado():
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO COMPLETO AVANZADO - {tipo_pastura}")
        
        params = PARAMETROS_FORRAJEROS[tipo_pastura]
        
        # Mostrar parámetros utilizados
        st.subheader("⚙️ PARÁMETROS CONFIGURADOS")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write("**Forrajeros:**")
            st.write(f"- MS Óptimo: {params['MS_POR_HA_OPTIMO']} kg/ha")
            st.write(f"- Crecimiento: {params['CRECIMIENTO_DIARIO']} kg/día")
            st.write(f"- Consumo: {params['CONSUMO_PORCENTAJE_PESO']*100}% peso")
        
        with col2:
            st.write("**Ganaderos:**")
            st.write(f"- Peso: {peso_promedio} kg")
            st.write(f"- Carga: {carga_animal} cab.")
            st.write(f"- Divisiones: {n_divisiones}")
        
        with col3:
            st.write("**Detección:**")
            st.write(f"- Umbral: {umbral_vegetacion}")
            st.write(f"- Digestibilidad: {params['DIGESTIBILIDAD']}")
            st.write(f"- Proteína: {params['PROTEINA_CRUDA']*100}%")
        
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
        
        # Diccionarios para almacenar archivos para descarga
        mapas_descarga = {}
        graficos_descarga = {}
        
        with tab1:
            st.subheader("🗺️ VISUALIZACIÓN ESPACIAL")
            
            col1, col2 = st.columns(2)
            with col1:
                mapa_buf, titulo = crear_mapa_simple(datos_analizados, "PRODUCTIVIDAD", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
                    mapas_descarga['productividad'] = (mapa_buf, titulo)
            
            with col2:
                mapa_buf, titulo = crear_mapa_simple(datos_analizados, "DIAS_PERMANENCIA", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
                    mapas_descarga['dias_permanencia'] = (mapa_buf, titulo)
            
            mapa_cobertura = crear_mapa_cobertura_simple(datos_analizados, tipo_pastura)
            if mapa_cobertura:
                st.image(mapa_cobertura, caption="Mapa de Cobertura Vegetal", use_column_width=True)
                mapas_descarga['cobertura'] = (mapa_cobertura, "Cobertura Vegetal")
        
        with tab2:
            st.subheader("📈 ANÁLISIS DE CORRELACIÓN COMPLETO")
            
            # Análisis de correlación completo
            with st.spinner("Calculando correlaciones..."):
                correlacion_buf, matriz_corr, p_values, corr_significativas = crear_analisis_correlacion_completo(datos_analizados)
            
            if correlacion_buf:
                st.image(correlacion_buf, caption="Análisis Completo de Correlación", use_column_width=True)
                graficos_descarga['correlacion_completa'] = (correlacion_buf, "Análisis de Correlación")
                
                # Mostrar matriz de correlación como tabla
                if matriz_corr is not None:
                    st.subheader("📊 Matriz de Correlación Numérica")
                    st.dataframe(matriz_corr.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1), 
                               use_container_width=True)
                    
                    # Interpretación de correlaciones
                    st.subheader("💡 Interpretación de Correlaciones Significativas")
                    
                    if corr_significativas:
                        df_corr_sig = pd.DataFrame(corr_significativas)
                        st.dataframe(df_corr_sig, use_container_width=True)
                        
                        st.info("""
                        **Significado de los símbolos de significancia:**
                        - *** p < 0.001 (Altamente significativo)
                        - **  p < 0.01 (Muy significativo)  
                        - *   p < 0.05 (Significativo)
                        - Sin símbolo: p >= 0.05 (No significativo)
                        """)
        
        with tab3:
            st.subheader("🔮 ANÁLISIS DE REGRESIÓN MÚLTIPLE")
            
            # Análisis de regresión múltiple completo
            with st.spinner("Calculando modelo de regresión..."):
                regresion_buf, resumen_modelo = crear_analisis_regresion_multiple_completo(datos_analizados)
            
            if regresion_buf:
                st.image(regresion_buf, caption="Análisis de Regresión Múltiple Completo", use_column_width=True)
                graficos_descarga['regresion_multiple'] = (regresion_buf, "Regresión Múltiple")
                
                if resumen_modelo:
                    st.subheader("📋 Resumen del Modelo de Regresión")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("R² del Modelo", f"{resumen_modelo['R_cuadrado']:.3f}")
                        st.metric("R² Ajustado", f"{resumen_modelo['R_cuadrado_ajustado']:.3f}")
                        st.metric("Error Cuadrático Medio", f"{resumen_modelo['MSE']:.3f}")
                    
                    with col2:
                        st.metric("RMSE", f"{resumen_modelo['RMSE']:.3f}")
                        st.metric("MAE", f"{resumen_modelo['MAE']:.3f}")
                        st.write("**Ecuación del Modelo:**")
                        st.code(resumen_modelo['Ecuacion'])
                    
                    # Mostrar coeficientes
                    st.subheader("📊 Coeficientes del Modelo")
                    coef_df = pd.DataFrame({
                        'Variable': list(resumen_modelo['Coeficientes'].keys()),
                        'Coeficiente': list(resumen_modelo['Coeficientes'].values()),
                        'Coeficiente_Estandarizado': [None] + list(resumen_modelo['Coeficientes_estandarizados'].values())
                    })
                    st.dataframe(coef_df, use_container_width=True)
                    
                    st.write("**Interpretación:**")
                    st.info("""
                    - **R²**: Proporción de la variabilidad en EV/Ha explicada por el modelo
                    - **R² Ajustado**: R² corregido por el número de variables
                    - **RMSE**: Error cuadrático medio (en las unidades de EV/Ha)
                    - **MAE**: Error absoluto medio (menos sensible a outliers)
                    - **Coeficientes estandarizados**: Permiten comparar importancia relativa entre variables
                    """)
        
        with tab4:
            st.subheader("📋 DATOS DETALLADOS")
            
            # Crear DataFrame para mostrar
            df_resumen = pd.DataFrame(datos_analizados)
            columnas_mostrar = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'probabilidad_vegetacion',
                               'biomasa_disponible_kg_ms_ha', 'dias_permanencia', 'ev_ha', 'estado_forrajero']
            
            df_mostrar = df_resumen[columnas_mostrar].sort_values('id_subLote')
            st.dataframe(df_mostrar, use_container_width=True)
            
            # Estadísticas descriptivas
            st.subheader("📊 Estadísticas Descriptivas")
            st.dataframe(df_mostrar.describe(), use_container_width=True)
            
            # Matriz de correlación numérica
            if 'matriz_correlacion' in locals():
                st.subheader("🔗 Matriz de Correlación Numérica")
                st.dataframe(matriz_corr, use_container_width=True)
        
        with tab5:
            st.subheader("📥 DESCARGAS COMPLETAS")
            
            st.info("💡 **Descarga todos los resultados del análisis en formato ZIP**")
            
            # Crear archivo ZIP
            zip_buffer = crear_zip_descarga(datos_analizados, mapas_descarga, graficos_descarga, tipo_pastura)
            
            # Botón de descarga ZIP
            st.download_button(
                label="📦 Descargar TODO (ZIP)",
                data=zip_buffer,
                file_name=f"analisis_completo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
                type="primary"
            )
            
            st.markdown("---")
            st.subheader("📁 Descargas Individuales")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**📊 Datos:**")
                # Datos completos
                df_completo = pd.DataFrame(datos_analizados)
                csv = df_completo.to_csv(index=False)
                st.download_button(
                    "📥 Descargar Datos Completos (CSV)",
                    csv,
                    file_name=f"datos_analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
                
                # Matriz de correlación
                if 'matriz_corr' in locals():
                    csv_corr = matriz_corr.to_csv()
                    st.download_button(
                        "📥 Matriz de Correlación (CSV)",
                        csv_corr,
                        file_name=f"matriz_correlacion_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                st.write("**🖼️ Mapas y Gráficos:**")
                # Descargas individuales de imágenes
                for nombre, (buf, descripcion) in {**mapas_descarga, **graficos_descarga}.items():
                    if buf:
                        st.download_button(
                            f"📥 {descripcion}",
                            buf.getvalue(),
                            file_name=f"{nombre}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                            mime="image/png"
                        )
        
        # INFORME FINAL
        st.subheader("📑 INFORME EJECUTIVO COMPLETO")
        
        total_ev = sum(d['ev_soportable'] for d in datos_analizados)
        area_vegetacion = sum(d['area_ha'] for d in datos_analizados if d['tiene_vegetacion'])
        dias_promedio = np.mean([d['dias_permanencia'] for d in datos_analizados])
        
        resumen = f"""
RESUMEN EJECUTIVO - ANÁLISIS COMPLETO AVANZADO
===============================================
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
• Permanencia Promedio: {dias_promedio:.1f} días

ANÁLISIS ESTADÍSTICO
-------------------
• Correlaciones significativas identificadas: {len(corr_significativas) if 'corr_significativas' in locals() else 'N/A'}
• Modelo de regresión desarrollado con R²: {resumen_modelo['R_cuadrado']:.3f if resumen_modelo else 'N/A'}
• Análisis de significancia estadística completo

RECOMENDACIONES
--------------
• Enfoque en las {zonas_vegetacion} zonas con vegetación para pastoreo
• Utilice los análisis de correlación para optimizar el manejo
• Considere el modelo de regresión para planificación futura
• Revise las descargas para documentación completa
"""
        
        st.text_area("Resumen Ejecutivo", resumen, height=350)
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis completo: {str(e)}")
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
if st.button("🚀 EJECUTAR ANÁLISIS COMPLETO AVANZADO", type="primary"):
    analisis_forrajero_completo_avanzado()

# Información cuando no hay archivo
if uploaded_file is None:
    st.info("📁 **Opción 1:** Sube un archivo CSV con datos de coordenadas")
    st.info("🎯 **Opción 2:** Usa el botón arriba para análisis con datos simulados")
    
    st.warning("""
    **🔍 SISTEMA DE ANÁLISIS COMPLETO AVANZADO:**
    
    Este sistema incluye:
    - **Parámetros forrajeros personalizables**
    - **Detección automática** de vegetación vs suelo desnudo
    - **Mapas interactivos** de productividad y cobertura
    - **Análisis de correlación completo** con significancia estadística
    - **Modelos de regresión múltiple** para predicción
    - **Descargas completas** en formato ZIP
    - **Informes ejecutivos** detallados
    
    **Características nuevas:**
    - Configuración personalizada de parámetros forrajeros
    - Matriz de correlación con p-valores y significancia
    - Análisis de regresión con métricas completas (R², RMSE, MAE)
    - Descarga de todos los mapas, gráficos y datos
    - Informe estadístico completo
    """)
