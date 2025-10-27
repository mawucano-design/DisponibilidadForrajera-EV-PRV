import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
from datetime import datetime

# Configuración básica de la página
st.set_page_config(
    page_title="🌱 Disponibilidad Forrajera",
    layout="wide",
    page_icon="🌱"
)

# Título principal
st.title("🌱 SISTEMA DE DISPONIBILIDAD FORRAJERA - EV PRV")
st.markdown("---")

# Sidebar simplificado
with st.sidebar:
    st.header("⚙️ CONFIGURACIÓN")
    
    tipo_pastura = st.selectbox(
        "Tipo de Pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 4, 16, 8)

# Parámetros forrajeros básicos
PARAMETROS = {
    'ALFALFA': {'MS_OPTIMO': 4000, 'CRECIMIENTO': 80},
    'RAYGRASS': {'MS_OPTIMO': 3500, 'CRECIMIENTO': 70},
    'FESTUCA': {'MS_OPTIMO': 3000, 'CRECIMIENTO': 50},
    'AGROPIRRO': {'MS_OPTIMO': 2800, 'CRECIMIENTO': 45},
    'PASTIZAL_NATURAL': {'MS_OPTIMO': 2500, 'CRECIMIENTO': 20}
}

# Función para generar datos de ejemplo
def generar_datos_ejemplo(n_subLotes, tipo_pastura):
    """Genera datos de ejemplo para demostración"""
    params = PARAMETROS[tipo_pastura]
    
    datos = []
    for i in range(1, n_subLotes + 1):
        # Simular variación espacial
        factor_calidad = 0.3 + (i / n_subLotes) * 0.5
        
        biomasa_ms_ha = params['MS_OPTIMO'] * factor_calidad
        biomasa_disponible = biomasa_ms_ha * 0.4  # 40% de utilización
        
        # Cálculo de EV/ha simplificado
        consumo_diario = 450 * 0.025  # 2.5% del peso vivo
        ev_ha = (biomasa_disponible / consumo_diario) / 30  # EV por hectárea
        
        datos.append({
            'SubLote': f"S{i}",
            'Area_ha': round(10 + np.random.uniform(-2, 2), 1),
            'Biomasa_kg_ms_ha': round(biomasa_ms_ha),
            'Biomasa_Disponible_kg_ms_ha': round(biomasa_disponible),
            'EV_ha': round(ev_ha, 2),
            'Dias_Permanencia': round(1 + (factor_calidad * 4), 1),
            'Categoria': 'ÓPTIMO' if factor_calidad > 0.7 else 
                        'BUENO' if factor_calidad > 0.5 else 
                        'ADECUADO' if factor_calidad > 0.3 else 'ALERTA'
        })
    
    return pd.DataFrame(datos)

# Función para crear gráfico simple
def crear_grafico_biomasa(df, tipo_pastura):
    """Crea un gráfico de barras de biomasa disponible"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    subLotes = df['SubLote']
    biomasa = df['Biomasa_Disponible_kg_ms_ha']
    
    # Crear colores según categoría
    colores = {
        'ÓPTIMO': '#1a9850',
        'BUENO': '#a6d96a', 
        'ADECUADO': '#fee08b',
        'ALERTA': '#fdae61'
    }
    
    barras = ax.bar(subLotes, biomasa, 
                   color=[colores[cat] for cat in df['Categoria']],
                   alpha=0.7)
    
    ax.set_title(f'🌱 BIOMASA DISPONIBLE POR SUB-LOTE\n{tipo_pastura}', 
                fontweight='bold', pad=20)
    ax.set_ylabel('Biomasa Disponible (kg MS/ha)')
    ax.set_xlabel('Sub-Lotes')
    ax.grid(True, alpha=0.3)
    
    # Añadir valores en las barras
    for barra, valor in zip(barras, biomasa):
        altura = barra.get_height()
        ax.text(barra.get_x() + barra.get_width()/2., altura + 20,
                f'{valor:.0f}', ha='center', va='bottom', fontweight='bold')
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    return fig

# INTERFAZ PRINCIPAL
st.header("📊 ANÁLISIS FORRAJERO SIMULADO")

# Botón para generar análisis
if st.button("🚀 GENERAR ANÁLISIS DEMO", type="primary", use_container_width=True):
    
    with st.spinner("Generando análisis forrajero..."):
        # Generar datos de ejemplo
        df_resultados = generar_datos_ejemplo(n_divisiones, tipo_pastura)
        
        # Mostrar métricas principales
        st.subheader("📈 MÉTRICAS PRINCIPALES")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            area_total = df_resultados['Area_ha'].sum()
            st.metric("Área Total", f"{area_total:.1f} ha")
        
        with col2:
            biomasa_prom = df_resultados['Biomasa_Disponible_kg_ms_ha'].mean()
            st.metric("Biomasa Promedio", f"{biomasa_prom:.0f} kg MS/ha")
        
        with col3:
            ev_total = (df_resultados['EV_ha'] * df_resultados['Area_ha']).sum()
            st.metric("Capacidad Total", f"{ev_total:.0f} EV")
        
        with col4:
            dias_prom = df_resultados['Dias_Permanencia'].mean()
            st.metric("Permanencia Prom", f"{dias_prom:.1f} días")
        
        # Mostrar gráfico
        st.subheader("📊 DISTRIBUCIÓN DE BIOMASA")
        fig = crear_grafico_biomasa(df_resultados, tipo_pastura)
        st.pyplot(fig)
        
        # Mostrar tabla de resultados
        st.subheader("📋 RESULTADOS DETALLADOS")
        st.dataframe(df_resultados, use_container_width=True)
        
        # Resumen ejecutivo
        st.subheader("💡 RESUMEN EJECUTIVO")
        
        distribucion = df_resultados['Categoria'].value_counts()
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Distribución de Categorías:**")
            for cat, count in distribucion.items():
                st.write(f"- **{cat}**: {count} sub-lotes")
        
        with col2:
            st.write("**Recomendaciones:**")
            if distribucion.get('ALERTA', 0) > 0:
                st.warning("⚠️ Algunas áreas requieren atención inmediata")
            else:
                st.success("✅ Condiciones generales favorables")

# Si no se ha generado análisis, mostrar instrucciones
else:
    st.info("""
    ## 🎯 BIENVENIDO AL SISTEMA DE DISPONIBILIDAD FORRAJERA
    
    **Para comenzar:**
    
    1. ⚙️ **Configura** los parámetros en el sidebar
    2. 🚀 **Haz click** en "GENERAR ANÁLISIS DEMO" 
    3. 📊 **Revisa** los resultados y recomendaciones
    
    ---
    
    **📈 Métricas que obtendrás:**
    - Biomasa disponible por sub-lote
    - Equivalentes Vaca (EV) de carga animal
    - Días de permanencia estimados
    - Recomendaciones de manejo
    
    *Sistema en modo demostración - Datos simulados*
    """)

# Pie de página
st.markdown("---")
st.markdown(
    "🌱 **Sistema de Disponibilidad Forrajera - EV PRV** | "
    "Modo Demo | "
    "Desarrollado para GitHub Cloud"
)
