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

# PARÁMETROS FORRAJEROS POR TIPO DE PASTURA
PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,  # 3% del peso vivo
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45
    }
}

# [Mantener todas las funciones anteriores igual hasta calcular_metricas_ganaderas...]

# CÁLCULO DE MÉTRICAS GANADERAS - CORREGIDO
def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """
    Calcula equivalentes vaca y días de permanencia - VERSIÓN CORREGIDA
    """
    params = PARAMETROS_FORRAJEROS[tipo_pastura]
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_ms_ha']
        area_ha = row['area_ha']
        crecimiento_diario = row['crecimiento_diario']
        
        # 1. CONSUMO INDIVIDUAL CORREGIDO (kg MS/animal/día)
        # Basado en porcentaje del peso vivo
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # 2. EQUIVALENTES VACA (EV)
        # Capacidad de carga instantánea del sub-lote
        biomasa_total_disponible = biomasa_disponible * area_ha
        ev_soportable = biomasa_total_disponible / consumo_individual_kg
        
        # 3. DÍAS DE PERMANENCIA - FÓRMULA CORREGIDA
        if carga_animal > 0:
            # Consumo total diario del rodeo
            consumo_total_diario = carga_animal * consumo_individual_kg
            
            # Biomasa disponible para consumo (considerando tasa de utilización recomendada)
            biomasa_utilizable = biomasa_total_disponible * params['TASA_UTILIZACION_RECOMENDADA']
            
            # Cálculo realista de días de permanencia
            if consumo_total_diario > 0:
                dias_permanencia = biomasa_utilizable / consumo_total_diario
            else:
                dias_permanencia = 0
                
            # Ajustar por crecimiento durante el período de pastoreo
            # Considerar que el crecimiento compensa parte del consumo
            if dias_permanencia > 0:
                crecimiento_total_periodo = crecimiento_diario * area_ha * dias_permanencia * 0.3  # Factor de eficiencia
                dias_ajustados = (biomasa_utilizable + crecimiento_total_periodo) / consumo_total_diario
                dias_permanencia = min(dias_ajustados, dias_permanencia * 1.2)  # Límite máximo del 20% de ajuste
        else:
            dias_permanencia = 0
        
        # 4. TASA DE UTILIZACIÓN REAL
        if carga_animal > 0 and biomasa_total_disponible > 0:
            consumo_potencial_diario = carga_animal * consumo_individual_kg
            tasa_utilizacion = min(1.0, consumo_potencial_diario / (biomasa_total_disponible * params['TASA_UTILIZACION_RECOMENDADA']))
        else:
            tasa_utilizacion = 0
        
        # 5. OFERTA FORRAJERA (kg MS/EV/día) - importante para validación
        if ev_soportable > 0:
            oferta_forrajera = biomasa_total_disponible / ev_soportable
        else:
            oferta_forrajera = 0
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 1),
            'dias_permanencia': max(0, round(dias_permanencia, 1)),  # Evitar valores negativos
            'tasa_utilizacion': round(tasa_utilizacion, 3),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'oferta_forrajera': round(oferta_forrajera, 1),
            'biomasa_utilizable': round(biomasa_utilizable, 1)
        })
    
    return metricas

# FUNCIÓN DE VALIDACIÓN PARA VERIFICAR CORRELACIÓN
def validar_correlacion_datos(gdf_analizado):
    """
    Valida la correlación entre variables forrajeras
    """
    try:
        # Calcular correlaciones
        correlaciones = gdf_analizado[['biomasa_ms_ha', 'ev_soportable', 'dias_permanencia', 'area_ha']].corr()
        
        # Crear gráfico de validación
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # Scatter plot: Biomasa vs Días permanencia
        axes[0,0].scatter(gdf_analizado['biomasa_ms_ha'], gdf_analizado['dias_permanencia'], alpha=0.6)
        axes[0,0].set_xlabel('Biomasa (kg MS/ha)')
        axes[0,0].set_ylabel('Días Permanencia')
        axes[0,0].set_title('Biomasa vs Días Permanencia')
        
        # Scatter plot: EV vs Días permanencia
        axes[0,1].scatter(gdf_analizado['ev_soportable'], gdf_analizado['dias_permanencia'], alpha=0.6)
        axes[0,1].set_xlabel('EV Soportable')
        axes[0,1].set_ylabel('Días Permanencia')
        axes[0,1].set_title('EV vs Días Permanencia')
        
        # Scatter plot: Biomasa vs EV
        axes[1,0].scatter(gdf_analizado['biomasa_ms_ha'], gdf_analizado['ev_soportable'], alpha=0.6)
        axes[1,0].set_xlabel('Biomasa (kg MS/ha)')
        axes[1,0].set_ylabel('EV Soportable')
        axes[1,0].set_title('Biomasa vs EV Soportable')
        
        # Heatmap de correlaciones
        im = axes[1,1].imshow(correlaciones.values, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)
        axes[1,1].set_xticks(range(len(correlaciones.columns)))
        axes[1,1].set_yticks(range(len(correlaciones.columns)))
        axes[1,1].set_xticklabels(correlaciones.columns, rotation=45)
        axes[1,1].set_yticklabels(correlaciones.columns)
        axes[1,1].set_title('Matriz de Correlación')
        
        # Añadir valores de correlación
        for i in range(len(correlaciones.columns)):
            for j in range(len(correlaciones.columns)):
                axes[1,1].text(j, i, f'{correlaciones.iloc[i, j]:.2f}', 
                              ha='center', va='center', color='white' if abs(correlaciones.iloc[i, j]) > 0.5 else 'black')
        
        plt.tight_layout()
        
        # Convertir a imagen
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, correlaciones
        
    except Exception as e:
        st.error(f"Error en validación de correlación: {str(e)}")
        return None, None

# MODIFICAR LA FUNCIÓN PRINCIPAL PARA INCLUIR VALIDACIÓN
def analisis_forrajero_completo(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # [Mantener código anterior igual hasta después de mostrar los resultados...]
        
        # DESPUÉS DE MOSTRAR LOS RESULTADOS PRINCIPALES, AÑADIR VALIDACIÓN
        st.subheader("🔍 VALIDACIÓN DE CORRELACIONES")
        
        with st.spinner("Validando consistencia de datos..."):
            mapa_validacion, correlaciones = validar_correlacion_datos(gdf_analizado)
        
        if mapa_validacion:
            st.image(mapa_validacion, use_container_width=True)
            
            # Mostrar matriz de correlación
            st.write("**📊 Matriz de Correlación:**")
            st.dataframe(correlaciones.style.background_gradient(cmap='coolwarm', vmin=-1, vmax=1))
            
            # Análisis de correlaciones clave
            corr_biomasa_dias = correlaciones.loc['biomasa_ms_ha', 'dias_permanencia']
            corr_ev_dias = correlaciones.loc['ev_soportable', 'dias_permanencia']
            
            col1, col2 = st.columns(2)
            with col1:
                if corr_biomasa_dias > 0.7:
                    st.success(f"✅ Alta correlación Biomasa-Días: {corr_biomasa_dias:.3f}")
                elif corr_biomasa_dias > 0.4:
                    st.warning(f"⚠️ Correlación moderada Biomasa-Días: {corr_biomasa_dias:.3f}")
                else:
                    st.error(f"❌ Baja correlación Biomasa-Días: {corr_biomasa_dias:.3f}")
            
            with col2:
                if corr_ev_dias > 0.7:
                    st.success(f"✅ Alta correlación EV-Días: {corr_ev_dias:.3f}")
                elif corr_ev_dias > 0.4:
                    st.warning(f"⚠️ Correlación moderada EV-Días: {corr_ev_dias:.3f}")
                else:
                    st.error(f"❌ Baja correlación EV-Días: {corr_ev_dias:.3f}")

        # [Mantener el resto del código igual...]

# [Mantener el resto del código sin cambios...]
