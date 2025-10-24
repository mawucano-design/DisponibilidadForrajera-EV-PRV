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
import json
import seaborn as sns
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - PARÁMETROS PERSONALIZABLES")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar (mantener igual tu código existente)
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
        
        # Parámetros avanzados en expander
        with st.expander("⚙️ Parámetros Avanzados"):
            col1, col2 = st.columns(2)
            with col1:
                factor_ndvi = st.number_input("Factor Biomasa NDVI:", min_value=500, max_value=5000, value=2000, step=100)
                factor_evi = st.number_input("Factor Biomasa EVI:", min_value=500, max_value=5000, value=2200, step=100)
                offset_biomasa = st.number_input("Offset Biomasa:", min_value=-2000, max_value=0, value=-300, step=50)
            
            with col2:
                umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.0, max_value=0.5, value=0.20, step=0.01, format="%.2f")
                umbral_bsi_suelo = st.number_input("Umbral BSI Suelo:", min_value=0.0, max_value=0.5, value=0.18, step=0.01, format="%.2f")
                penalizacion_suelo = st.number_input("Penalización Suelo:", min_value=0.0, max_value=1.0, value=0.75, step=0.05, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=72, value=48)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

    # NUEVO: GUARDAR/CARGAR CONFIGURACIÓN
    st.subheader("💾 Guardar/Cargar Configuración")
    
    if tipo_pastura == "PERSONALIZADO":
        # Guardar configuración actual
        config_data = {
            'ms_optimo': ms_optimo,
            'crecimiento_diario': crecimiento_diario,
            'consumo_porcentaje': consumo_porcentaje,
            'digestibilidad': digestibilidad,
            'proteina_cruda': proteina_cruda,
            'tasa_utilizacion': tasa_utilizacion,
            'factor_ndvi': factor_ndvi,
            'factor_evi': factor_evi,
            'offset_biomasa': offset_biomasa,
            'umbral_ndvi_suelo': umbral_ndvi_suelo,
            'umbral_bsi_suelo': umbral_bsi_suelo,
            'penalizacion_suelo': penalizacion_suelo
        }
        
        config_json = json.dumps(config_data, indent=2)
        st.download_button(
            "💾 Guardar Configuración",
            config_json,
            file_name="configuracion_pastura.json",
            mime="application/json",
            help="Descarga la configuración actual para usarla después"
        )
    
    # Cargar configuración
    uploaded_config = st.file_uploader("Cargar configuración (.json)", type=['json'], key="config_uploader")
    
    if uploaded_config is not None:
        try:
            config_cargada = json.load(uploaded_config)
            st.success("✅ Configuración cargada correctamente")
            st.info(f"MS Óptimo: {config_cargada.get('ms_optimo', 'N/A')} kg/ha")
        except Exception as e:
            st.error(f"❌ Error cargando configuración: {e}")

# PARÁMETROS FORRAJEROS BASE (mantener tu código existente)
PARAMETROS_FORRAJEROS_BASE = {
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
        'UMBRAL_NDVI_SUELO': 0.12,
        'UMBRAL_BSI_SUELO': 0.20,
        'UMBRAL_NDBI_SUELO': 0.08,
        'UMBRAL_NDVI_VEGETACION': 0.40,
        'FACTOR_COBERTURA_MAX': 0.98,
        'FACTOR_COBERTURA_MIN': 0.02,
        'PENALIZACION_SUELO': 0.90,
        'FACTOR_MSAVI2': 2600,
        'FACTOR_VARI': 800,
    },
    # ... (mantener el resto de tus parámetros base igual)
}

# FUNCIÓN PARA OBTENER PARÁMETROS (mantener tu código existente)
def obtener_parametros_pastura(tipo_pastura, config_personalizada=None):
    # ... (tu código existente)

# =============================================================================
# NUEVAS FUNCIONES DE VISUALIZACIÓN Y ANÁLISIS
# =============================================================================

def crear_visualizacion_regresion(gdf_analizado):
    """Crea análisis de regresión entre variables forrajeras"""
    try:
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        
        # 1. Regresión: NDVI vs Biomasa
        x_ndvi = gdf_analizado['ndvi'].values.reshape(-1, 1)
        y_biomasa = gdf_analizado['biomasa_disponible_kg_ms_ha'].values
        
        model_ndvi = LinearRegression()
        model_ndvi.fit(x_ndvi, y_biomasa)
        y_pred_ndvi = model_ndvi.predict(x_ndvi)
        r2_ndvi = r2_score(y_biomasa, y_pred_ndvi)
        
        axes[0,0].scatter(x_ndvi, y_biomasa, alpha=0.6, color='green')
        axes[0,0].plot(x_ndvi, y_pred_ndvi, color='red', linewidth=2)
        axes[0,0].set_xlabel('NDVI')
        axes[0,0].set_ylabel('Biomasa Disponible (kg MS/ha)')
        axes[0,0].set_title(f'Regresión NDVI vs Biomasa\nR² = {r2_ndvi:.3f}')
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Regresión: Cobertura vs Días Permanencia
        x_cobertura = gdf_analizado['cobertura_vegetal'].values.reshape(-1, 1)
        y_dias = gdf_analizado['dias_permanencia'].values
        
        model_cob = LinearRegression()
        model_cob.fit(x_cobertura, y_dias)
        y_pred_cob = model_cob.predict(x_cobertura)
        r2_cob = r2_score(y_dias, y_pred_cob)
        
        axes[0,1].scatter(x_cobertura, y_dias, alpha=0.6, color='blue')
        axes[0,1].plot(x_cobertura, y_pred_cob, color='red', linewidth=2)
        axes[0,1].set_xlabel('Cobertura Vegetal')
        axes[0,1].set_ylabel('Días de Permanencia')
        axes[0,1].set_title(f'Regresión Cobertura vs Días\nR² = {r2_cob:.3f}')
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Regresión: Biomasa vs EV/Ha
        x_biomasa = gdf_analizado['biomasa_disponible_kg_ms_ha'].values.reshape(-1, 1)
        y_ev = gdf_analizado['ev_ha'].values
        
        model_ev = LinearRegression()
        model_ev.fit(x_biomasa, y_ev)
        y_pred_ev = model_ev.predict(x_biomasa)
        r2_ev = r2_score(y_ev, y_pred_ev)
        
        axes[0,2].scatter(x_biomasa, y_ev, alpha=0.6, color='orange')
        axes[0,2].plot(x_biomasa, y_pred_ev, color='red', linewidth=2)
        axes[0,2].set_xlabel('Biomasa Disponible (kg MS/ha)')
        axes[0,2].set_ylabel('EV/Ha')
        axes[0,2].set_title(f'Regresión Biomasa vs EV/Ha\nR² = {r2_ev:.3f}')
        axes[0,2].grid(True, alpha=0.3)
        
        # 4. Regresión múltiple: Múltiples índices vs Biomasa
        X_multi = gdf_analizado[['ndvi', 'evi', 'savi', 'cobertura_vegetal']].values
        y_multi = gdf_analizado['biomasa_disponible_kg_ms_ha'].values
        
        model_multi = LinearRegression()
        model_multi.fit(X_multi, y_multi)
        y_pred_multi = model_multi.predict(X_multi)
        r2_multi = r2_score(y_multi, y_pred_multi)
        
        axes[1,0].scatter(y_multi, y_pred_multi, alpha=0.6, color='purple')
        axes[1,0].plot([y_multi.min(), y_multi.max()], [y_multi.min(), y_multi.max()], 'red', linewidth=2)
        axes[1,0].set_xlabel('Biomasa Real (kg MS/ha)')
        axes[1,0].set_ylabel('Biomasa Predicha (kg MS/ha)')
        axes[1,0].set_title(f'Regresión Múltiple: Índices vs Biomasa\nR² = {r2_multi:.3f}')
        axes[1,0].grid(True, alpha=0.3)
        
        # 5. Residuales
        residuals = y_multi - y_pred_multi
        axes[1,1].scatter(y_pred_multi, residuals, alpha=0.6, color='brown')
        axes[1,1].axhline(y=0, color='red', linestyle='--')
        axes[1,1].set_xlabel('Biomasa Predicha (kg MS/ha)')
        axes[1,1].set_ylabel('Residuales')
        axes[1,1].set_title('Análisis de Residuales')
        axes[1,1].grid(True, alpha=0.3)
        
        # 6. Coeficientes de regresión múltiple
        coef_names = ['NDVI', 'EVI', 'SAVI', 'Cobertura']
        coef_values = model_multi.coef_
        
        axes[1,2].barh(coef_names, coef_values, color='teal')
        axes[1,2].set_xlabel('Coeficiente de Regresión')
        axes[1,2].set_title('Importancia de Variables en Regresión Múltiple')
        axes[1,2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Crear dataframe con resultados de regresión
        resultados_regresion = pd.DataFrame({
            'Variable': ['NDVI', 'Cobertura', 'Biomasa', 'Múltiple'],
            'R²': [r2_ndvi, r2_cob, r2_ev, r2_multi],
            'Ecuación': [
                f"y = {model_ndvi.coef_[0]:.1f}x + {model_ndvi.intercept_:.1f}",
                f"y = {model_cob.coef_[0]:.1f}x + {model_cob.intercept_:.1f}",
                f"y = {model_ev.coef_[0]:.3f}x + {model_ev.intercept_:.3f}",
                f"Múltiple: {len(model_multi.coef_)} variables"
            ]
        })
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, resultados_regresion
        
    except Exception as e:
        st.error(f"Error en análisis de regresión: {str(e)}")
        return None, None

def crear_matriz_correlacion(gdf_analizado):
    """Crea matriz de correlación mejorada"""
    try:
        # Seleccionar variables numéricas para correlación
        variables_corr = [
            'ndvi', 'evi', 'savi', 'bsi', 'cobertura_vegetal', 
            'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia', 'area_ha'
        ]
        
        # Filtrar variables existentes
        variables_existentes = [var for var in variables_corr if var in gdf_analizado.columns]
        df_corr = gdf_analizado[variables_existentes]
        
        # Calcular matriz de correlación
        corr_matrix = df_corr.corr()
        
        # Crear visualización
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
        
        # Heatmap de correlación
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
        sns.heatmap(corr_matrix, mask=mask, annot=True, cmap='coolwarm', center=0,
                   square=True, ax=ax1, cbar_kws={"shrink": .8})
        ax1.set_title('Matriz de Correlación - Heatmap', fontsize=14, fontweight='bold')
        
        # Gráfico de barras de correlaciones con biomasa
        if 'biomasa_disponible_kg_ms_ha' in corr_matrix.columns:
            corr_biomasa = corr_matrix['biomasa_disponible_kg_ms_ha'].drop('biomasa_disponible_kg_ms_ha')
            colors = ['green' if x > 0 else 'red' for x in corr_biomasa]
            ax2.barh(corr_biomasa.index, corr_biomasa.values, color=colors, alpha=0.7)
            ax2.axvline(x=0, color='black', linestyle='-', alpha=0.3)
            ax2.set_xlabel('Coeficiente de Correlación')
            ax2.set_title('Correlación con Biomasa Disponible', fontsize=14, fontweight='bold')
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Crear tabla de correlaciones significativas
        correlaciones_significativas = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                corr_val = corr_matrix.iloc[i, j]
                if abs(corr_val) > 0.3:  # Solo correlaciones moderadas/altas
                    correlaciones_significativas.append({
                        'Variable 1': corr_matrix.columns[i],
                        'Variable 2': corr_matrix.columns[j],
                        'Correlación': round(corr_val, 3),
                        'Tipo': 'Fuerte Positiva' if corr_val > 0.7 else 
                               'Moderada Positiva' if corr_val > 0.3 else
                               'Moderada Negativa' if corr_val < -0.3 else
                               'Fuerte Negativa'
                    })
        
        df_corr_signif = pd.DataFrame(correlaciones_significativas)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, corr_matrix, df_corr_signif
        
    except Exception as e:
        st.error(f"Error en matriz de correlación: {str(e)}")
        return None, None, None

def crear_tabla_resultados_detallada(gdf_analizado):
    """Crea tabla detallada de resultados con estadísticas"""
    try:
        # Seleccionar columnas clave para el resumen
        columnas_resumen = [
            'id_subLote', 'area_ha', 'ndvi', 'cobertura_vegetal', 
            'tipo_superficie', 'biomasa_disponible_kg_ms_ha',
            'ev_ha', 'dias_permanencia', 'categoria_manejo'
        ]
        
        # Filtrar columnas existentes
        columnas_existentes = [col for col in columnas_resumen if col in gdf_analizado.columns]
        df_resumen = gdf_analizado[columnas_existentes].copy()
        
        # Calcular estadísticas por tipo de superficie
        if 'tipo_superficie' in df_resumen.columns:
            stats_por_tipo = df_resumen.groupby('tipo_superficie').agg({
                'area_ha': ['count', 'sum', 'mean'],
                'biomasa_disponible_kg_ms_ha': ['mean', 'std', 'min', 'max'],
                'dias_permanencia': ['mean', 'std']
            }).round(2)
            
            # Aplanar columnas multiindex
            stats_por_tipo.columns = ['_'.join(col).strip() for col in stats_por_tipo.columns.values]
            stats_por_tipo = stats_por_tipo.reset_index()
        
        # Estadísticas generales
        stats_generales = pd.DataFrame({
            'Métrica': [
                'Total Sub-Lotes', 'Área Total (ha)', 
                'Biomasa Promedio (kg MS/ha)', 'Días Permanencia Promedio',
                'EV/Ha Promedio', 'Cobertura Vegetal Promedio (%)'
            ],
            'Valor': [
                len(gdf_analizado),
                round(gdf_analizado['area_ha'].sum(), 1),
                round(gdf_analizado['biomasa_disponible_kg_ms_ha'].mean(), 1),
                round(gdf_analizado['dias_permanencia'].mean(), 1),
                round(gdf_analizado['ev_ha'].mean(), 2),
                round(gdf_analizado['cobertura_vegetal'].mean() * 100, 1)
            ]
        })
        
        return df_resumen, stats_por_tipo, stats_generales
        
    except Exception as e:
        st.error(f"Error creando tabla de resultados: {str(e)}")
        return None, None, None

def crear_dashboard_metricas(gdf_analizado):
    """Crea dashboard visual con las métricas principales"""
    try:
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        
        # 1. Distribución de biomasa
        axes[0,0].hist(gdf_analizado['biomasa_disponible_kg_ms_ha'], bins=15, alpha=0.7, color='green', edgecolor='black')
        axes[0,0].axvline(gdf_analizado['biomasa_disponible_kg_ms_ha'].mean(), color='red', linestyle='--', linewidth=2, label='Promedio')
        axes[0,0].set_xlabel('Biomasa Disponible (kg MS/ha)')
        axes[0,0].set_ylabel('Frecuencia')
        axes[0,0].set_title('Distribución de Biomasa Disponible')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Distribución de días de permanencia
        axes[0,1].hist(gdf_analizado['dias_permanencia'], bins=15, alpha=0.7, color='blue', edgecolor='black')
        axes[0,1].axvline(gdf_analizado['dias_permanencia'].mean(), color='red', linestyle='--', linewidth=2, label='Promedio')
        axes[0,1].set_xlabel('Días de Permanencia')
        axes[0,1].set_ylabel('Frecuencia')
        axes[0,1].set_title('Distribución de Días de Permanencia')
        axes[0,1].legend()
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Boxplot de biomasa por tipo de superficie
        if 'tipo_superficie' in gdf_analizado.columns:
            data_boxplot = []
            labels = []
            for tipo in gdf_analizado['tipo_superficie'].unique():
                data_boxplot.append(gdf_analizado[gdf_analizado['tipo_superficie'] == tipo]['biomasa_disponible_kg_ms_ha'])
                labels.append(tipo)
            
            axes[0,2].boxplot(data_boxplot, labels=labels)
            axes[0,2].set_ylabel('Biomasa Disponible (kg MS/ha)')
            axes[0,2].set_title('Biomasa por Tipo de Superficie')
            axes[0,2].tick_params(axis='x', rotation=45)
            axes[0,2].grid(True, alpha=0.3)
        
        # 4. Scatter: Área vs Biomasa
        axes[1,0].scatter(gdf_analizado['area_ha'], gdf_analizado['biomasa_disponible_kg_ms_ha'], alpha=0.6, color='orange')
        axes[1,0].set_xlabel('Área (ha)')
        axes[1,0].set_ylabel('Biomasa Disponible (kg MS/ha)')
        axes[1,0].set_title('Relación Área vs Biomasa')
        axes[1,0].grid(True, alpha=0.3)
        
        # 5. Distribución de categorías de manejo
        if 'categoria_manejo' in gdf_analizado.columns:
            counts = gdf_analizado['categoria_manejo'].value_counts()
            colors = ['red', 'orange', 'yellow', 'lightgreen', 'green']
            axes[1,1].pie(counts.values, labels=counts.index, autopct='%1.1f%%', colors=colors[:len(counts)])
            axes[1,1].set_title('Distribución de Categorías de Manejo')
        
        # 6. Evolución espacial (usando ID como proxy de ubicación)
        axes[1,2].plot(gdf_analizado['id_subLote'], gdf_analizado['biomasa_disponible_kg_ms_ha'], marker='o', linewidth=2, alpha=0.7)
        axes[1,2].set_xlabel('ID Sub-Lote')
        axes[1,2].set_ylabel('Biomasa Disponible (kg MS/ha)')
        axes[1,2].set_title('Variación de Biomasa por Sub-Lote')
        axes[1,2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
        
    except Exception as e:
        st.error(f"Error creando dashboard: {str(e)}")
        return None

# =============================================================================
# FUNCIÓN PRINCIPAL MEJORADA CON TODAS LAS VISUALIZACIONES
# =============================================================================

def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, config_personalizada=None):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # OBTENER PARÁMETROS (BASE O PERSONALIZADOS)
        params = obtener_parametros_pastura(tipo_pastura, config_personalizada)
        
        # MOSTRAR RESUMEN DE PARÁMETROS
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
        
        # PASO 1: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 2: CALCULAR ÍNDICES FORRAJEROS GEE MEJORADO
        st.subheader("🛰️ CALCULANDO ÍNDICES FORRAJEROS")
        with st.spinner("Ejecutando algoritmos con parámetros personalizados..."):
            indices_forrajeros = calcular_indices_forrajeros_gee(gdf_dividido, tipo_pastura, params)
        
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
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, params, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 4: CATEGORIZAR PARA RECOMENDACIONES
        def categorizar_forrajero(estado_forrajero, dias_permanencia):
            if estado_forrajero == 0 or dias_permanencia < 1:
                return "CRÍTICO"
            elif estado_forrajero == 1 or dias_permanencia < 2:
                return "ALERTA"
            elif estado_forrajero == 2 or dias_permanencia < 3:
                return "ADECUADO"
            elif estado_forrajero == 3:
                return "BUENO"
            else:
                return "ÓPTIMO"
        
        gdf_analizado['categoria_manejo'] = [
            categorizar_forrajero(row['estado_forrajero'], row['dias_permanencia']) 
            for idx, row in gdf_analizado.iterrows()
        ]
        
        # =============================================================================
        # NUEVO: SECCIÓN DE VISUALIZACIONES Y ANÁLISIS
        # =============================================================================
        
        st.subheader("📊 RESULTADOS DEL ANÁLISIS FORRAJERO")
        
        # Estadísticas principales
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sub-Lotes Analizados", len(gdf_analizado))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
            st.metric("Biomasa Disponible Prom", f"{biomasa_prom:.0f} kg MS/ha")
        with col4:
            dias_prom = gdf_analizado['dias_permanencia'].mean()
            st.metric("Permanencia Promedio", f"{dias_prom:.0f} días")
        
        # Pestañas para diferentes tipos de visualización
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "🗺️ MAPAS", "📈 REGRESIÓN", "🔗 CORRELACIÓN", 
            "📋 TABLAS", "📊 DASHBOARD", "📑 INFORME"
        ])
        
        with tab1:
            st.subheader("🗺️ Visualización de Mapas")
            
            col1, col2 = st.columns(2)
            with col1:
                # Mapa de productividad
                mapa_buf, titulo = crear_mapa_forrajero_gee(gdf_analizado, "PRODUCTIVIDAD", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
            
            with col2:
                # Mapa de días de permanencia
                mapa_buf, titulo = crear_mapa_forrajero_gee(gdf_analizado, "DIAS_PERMANENCIA", tipo_pastura)
                if mapa_buf:
                    st.image(mapa_buf, caption=f"Mapa de {titulo}", use_column_width=True)
            
            # Mapa de cobertura
            mapa_cobertura = crear_mapa_cobertura(gdf_analizado, tipo_pastura)
            if mapa_cobertura:
                st.image(mapa_cobertura, caption="Mapa de Cobertura Vegetal y Tipos de Superficie", use_column_width=True)
        
        with tab2:
            st.subheader("📈 Análisis de Regresión")
            
            # Análisis de regresión
            regresion_buf, resultados_regresion = crear_visualizacion_regresion(gdf_analizado)
            if regresion_buf:
                st.image(regresion_buf, caption="Análisis de Regresión entre Variables Forrajeras", use_column_width=True)
                
                # Mostrar resultados numéricos
                st.subheader("Resultados de Regresión")
                st.dataframe(resultados_regresion, use_container_width=True)
                
                # Interpretación
                st.info("""
                **Interpretación de R²:**
                - **0.8-1.0:** Correlación muy fuerte
                - **0.6-0.8:** Correlación fuerte  
                - **0.4-0.6:** Correlación moderada
                - **0.2-0.4:** Correlación débil
                - **<0.2:** Correlación muy débil o nula
                """)
        
        with tab3:
            st.subheader("🔗 Matriz de Correlación")
            
            # Matriz de correlación
            corr_buf, corr_matrix, corr_signif = crear_matriz_correlacion(gdf_analizado)
            if corr_buf:
                st.image(corr_buf, caption="Matriz de Correlación entre Variables", use_column_width=True)
                
                # Mostrar correlaciones significativas
                if not corr_signif.empty:
                    st.subheader("Correlaciones Significativas")
                    st.dataframe(corr_signif, use_container_width=True)
                
                # Mostrar matriz completa
                st.subheader("Matriz de Correlación Completa")
                st.dataframe(corr_matrix.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1), 
                           use_container_width=True)
        
        with tab4:
            st.subheader("📋 Tablas de Resultados Detallados")
            
            # Crear tablas de resultados
            df_resumen, stats_por_tipo, stats_generales = crear_tabla_resultados_detallada(gdf_analizado)
            
            if df_resumen is not None:
                st.subheader("Resumen por Sub-Lote")
                st.dataframe(df_resumen, use_container_width=True)
                
                # Estadísticas por tipo de superficie
                if stats_por_tipo is not None:
                    st.subheader("Estadísticas por Tipo de Superficie")
                    st.dataframe(stats_por_tipo, use_container_width=True)
                
                # Estadísticas generales
                if stats_generales is not None:
                    st.subheader("Estadísticas Generales")
                    st.dataframe(stats_generales, use_container_width=True)
                
                # Botón para descargar datos
                csv = df_resumen.to_csv(index=False)
                st.download_button(
                    "📥 Descargar Resultados Completos (CSV)",
                    csv,
                    file_name=f"resultados_forrajeros_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
        
        with tab5:
            st.subheader("📊 Dashboard de Métricas")
            
            # Dashboard visual
            dashboard_buf = crear_dashboard_metricas(gdf_analizado)
            if dashboard_buf:
                st.image(dashboard_buf, caption="Dashboard de Métricas Forrajeras", use_column_width=True)
        
        with tab6:
            st.subheader("📑 Informe Ejecutivo")
            
            # Resumen ejecutivo
            resumen = crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total, params)
            st.text_area("Resumen Ejecutivo", resumen, height=300)
            
            # Recomendaciones específicas
            st.subheader("🎯 Recomendaciones de Manejo")
            
            # Análisis de categorías
            if 'categoria_manejo' in gdf_analizado.columns:
                cats = gdf_analizado['categoria_manejo'].value_counts()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Lotes Óptimos/Buenos", f"{cats.get('ÓPTIMO', 0) + cats.get('BUENO', 0)}")
                    st.metric("Lotes en Alerta/Crítico", f"{cats.get('ALERTA', 0) + cats.get('CRÍTICO', 0)}")
                
                with col2:
                    st.metric("Lotes Adecuados", f"{cats.get('ADECUADO', 0)}")
                    st.metric("Tasa de Éxito", f"{(cats.get('ÓPTIMO', 0) + cats.get('BUENO', 0) + cats.get('ADECUADO', 0)) / len(gdf_analizado) * 100:.1f}%")
            
            # Recomendaciones basadas en análisis
            st.info("""
            **📋 RECOMENDACIONES BASADAS EN EL ANÁLISIS:**
            
            **✅ ACCIONES INMEDIATAS:**
            - Priorizar rotación en lotes con menos de 2 días de permanencia
            - Considerar suplementación en áreas críticas
            - Monitorear intensivamente lotes en categoría ALERTA
            
            **📅 PLANEACIÓN MEDIO PLAZO:**
            - Optimizar rotación usando el mapa de días de permanencia
            - Planificar resiembras en áreas de suelo desnudo
            - Ajustar carga animal según capacidad por sub-lote
            
            **🌱 MEJORAS ESTRATÉGICAS:**
            - Implementar manejo diferenciado por tipo de superficie
            - Usar análisis de correlación para optimizar prácticas
            - Establecer monitoreo continuo con mismos parámetros
            """)
        
        # MOSTRAR RESUMEN CON PARÁMETROS PERSONALIZADOS
        st.subheader("📋 RESUMEN EJECUTIVO PERSONALIZADO")
        
        total_ev_soportable = gdf_analizado['ev_soportable'].sum()
        dias_promedio = gdf_analizado['dias_permanencia'].mean()
        biomasa_total = gdf_analizado['biomasa_total_kg'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🏭 CAPACIDAD TOTAL", f"{total_ev_soportable:.0f} EV")
        with col2:
            st.metric("📅 PERMANENCIA PROMEDIO", f"{dias_promedio:.0f} días")
        with col3:
            st.metric("🌿 BIOMASA TOTAL", f"{biomasa_total/1000:.1f} ton MS")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis forrajero: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

# INTERFAZ PRINCIPAL (mantener igual)
if uploaded_zip:
    with st.spinner("Cargando potrero..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    
                    st.success(f"✅ **Potrero cargado:** {len(gdf)} polígono(s)")
                    
                    area_total = calcular_superficie(gdf).sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📊 INFORMACIÓN DEL POTRERO:**")
                        st.write(f"- Polígonos: {len(gdf)}")
                        st.write(f"- Área total: {area_total:.1f} ha")
                        st.write(f"- CRS: {gdf.crs}")
                    
                    with col2:
                        st.write("**🎯 CONFIGURACIÓN GANADERA:**")
                        st.write(f"- Pastura: {tipo_pastura}")
                        st.write(f"- Peso promedio: {peso_promedio} kg")
                        st.write(f"- Carga animal: {carga_animal} cabezas")
                        st.write(f"- Sub-lotes: {n_divisiones}")
                    
                    # Cargar configuración si se subió
                    config_personalizada = None
                    if uploaded_config is not None:
                        try:
                            config_personalizada = json.load(uploaded_config)
                            st.success("✅ Configuración personalizada cargada")
                        except Exception as e:
                            st.error(f"❌ Error cargando configuración: {e}")
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO PERSONALIZADO", type="primary"):
                        analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, config_personalizada)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero personalizado")
    
    with st.expander("ℹ️ INFORMACIÓN SOBRE PARÁMETROS PERSONALIZABLES"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO - PARÁMETROS PERSONALIZABLES**
        
        **🎯 NUEVA FUNCIONALIDAD: PARÁMETROS AJUSTABLES**
        
        **📊 PARÁMETROS FORRAJeros PERSONALIZABLES:**
        - **MS Óptimo:** Producción máxima de materia seca por hectárea
        - **Crecimiento Diario:** Tasa de crecimiento diario del forraje
        - **Consumo (% peso):** Porcentaje del peso vivo que consume cada animal
        - **Digestibilidad:** Porcentaje de digestibilidad del forraje
        - **Proteína Cruda:** Contenido de proteína del forraje
        - **Tasa Utilización:** Porcentaje de forraje que puede ser consumido
        
        **🛰️ PARÁMETROS SATELITALES AVANZADOS:**
        - **Factores de Biomasa:** Conversión de índices vegetación a biomasa
        - **Umbrales de Suelo:** Límites para detección de suelo desnudo
        - **Penalizaciones:** Ajustes por tipo de superficie
        
        **💾 GUARDAR/CARGAR CONFIGURACIONES:**
        - **Guardar:** Descarga configuración actual como archivo JSON
        - **Cargar:** Usa configuraciones guardadas para análisis repetitivos
        - **Compartir:** Intercambia configuraciones entre usuarios/regiones
        
        **🚀 BENEFICIOS:**
        - **Específico por región:** Ajusta parámetros a condiciones locales
        - **Flexibilidad:** Adapta a diferentes tipos de pasturas
        - **Consistencia:** Mantiene configuraciones para análisis comparativos
        - **Precisión:** Mejora resultados con datos locales reales
        """)
