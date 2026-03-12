# modules/ia_integration.py
# ===============================
# MÓDULO DE INTEGRACIÓN CON IA (GEMINI)
# Funciones para generar análisis técnicos basados en datos
# Siguiendo el formato del informe biomap.pdf
# ===============================

import streamlit as st
import pandas as pd
import numpy as np
import os
import google.generativeai as genai

# === CONFIGURACIÓN DE GEMINI ===
GEMINI_API_KEY = None
model = None

# Intentar obtener la API key desde secrets de Streamlit o variables de entorno
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    st.success("✅ API key de Gemini cargada desde secrets de Streamlit.")
else:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        st.success("✅ API key de Gemini cargada desde variable de entorno.")
    else:
        st.error("⚠️ No se encontró la API Key de Gemini. La IA no estará disponible.")

# Configurar Gemini si la clave existe
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Listar modelos disponibles para elegir uno adecuado
        modelos_disponibles = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                modelos_disponibles.append(m.name)
        st.info(f"Modelos disponibles para generateContent: {modelos_disponibles}")
        
        # Orden de preferencia de modelos
        preferencias = [
            'models/gemini-1.5-pro',
            'models/gemini-1.5-flash',
            'models/gemini-1.0-pro',
            'models/gemini-pro',
            'models/gemini-1.0-pro-latest',
            'models/gemini-1.5-pro-latest'
        ]
        modelo_elegido = None
        for pref in preferencias:
            if pref in modelos_disponibles:
                modelo_elegido = pref
                break
        if modelo_elegido is None and modelos_disponibles:
            # Si no hay preferencia, tomar el primero
            modelo_elegido = modelos_disponibles[0]
        
        if modelo_elegido:
            model = genai.GenerativeModel(modelo_elegido)
            st.success(f"✅ Gemini configurado correctamente (modelo: {modelo_elegido}).")
        else:
            st.error("❌ No se encontró ningún modelo que soporte generateContent.")
            model = None
    except Exception as e:
        st.error(f"❌ Error al configurar Gemini: {e}")
        model = None

def preparar_resumen(resultados):
    """
    Convierte el diccionario de resultados en un DataFrame y un resumen de estadísticas.
    """
    df = pd.DataFrame()
    stats = {}
    if resultados:
        stats['area_total_ha'] = resultados.get('area_total_ha', 0)
        stats['carbono_total_ton'] = resultados.get('carbono_total_ton', 0)
        stats['co2_total_ton'] = resultados.get('co2_total_ton', 0)
        stats['shannon_promedio'] = resultados.get('shannon_promedio', 0)
        stats['ndvi_promedio'] = resultados.get('ndvi_promedio', 0)
        stats['ndwi_promedio'] = resultados.get('ndwi_promedio', 0)
        stats['tipo_ecosistema'] = resultados.get('tipo_ecosistema', 'N/A')
        stats['num_puntos'] = resultados.get('num_puntos', 0)
        if 'analisis_forrajero' in resultados:
            forrajero = resultados['analisis_forrajero']
            stats['forraje_productividad_kg_ms_ha'] = forrajero['disponibilidad_forrajera']['productividad_kg_ms_ha']
            stats['forraje_aprovechable_ton'] = forrajero['disponibilidad_forrajera']['forraje_aprovechable_kg_ms'] / 1000
            stats['ev_recomendado'] = forrajero['equivalentes_vaca']['ev_recomendado']
            stats['sistema_forrajero'] = forrajero['sistema_forrajero']
            stats['sublotes'] = forrajero['sublotes']
        # Incluir desglose de carbono si existe
        if 'desglose_promedio' in resultados:
            stats['desglose'] = resultados['desglose_promedio']
        # Incluir algunos puntos de muestra para variabilidad
        if 'puntos_carbono' in resultados and len(resultados['puntos_carbono']) > 0:
            stats['carbono_min'] = min(p['carbono_ton_ha'] for p in resultados['puntos_carbono'])
            stats['carbono_max'] = max(p['carbono_ton_ha'] for p in resultados['puntos_carbono'])
        if 'puntos_biodiversidad' in resultados and len(resultados['puntos_biodiversidad']) > 0:
            stats['shannon_min'] = min(p['indice_shannon'] for p in resultados['puntos_biodiversidad'])
            stats['shannon_max'] = max(p['indice_shannon'] for p in resultados['puntos_biodiversidad'])
        if 'puntos_ndvi' in resultados and len(resultados['puntos_ndvi']) > 0:
            stats['ndvi_min'] = min(p['ndvi'] for p in resultados['puntos_ndvi'])
            stats['ndvi_max'] = max(p['ndvi'] for p in resultados['puntos_ndvi'])
        if 'puntos_ndwi' in resultados and len(resultados['puntos_ndwi']) > 0:
            stats['ndwi_min'] = min(p['ndwi'] for p in resultados['puntos_ndwi'])
            stats['ndwi_max'] = max(p['ndwi'] for p in resultados['puntos_ndwi'])
    return df, stats

def generar_analisis_carbono(df, stats):
    if model is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Gemini válida y un modelo disponible. Configure la clave en los secrets de Streamlit o en la variable de entorno GEMINI_API_KEY."
    
    desglose = stats.get('desglose', {})
    desglose_str = "\n".join([f"   - {k}: {v:.2f} ton C/ha" for k, v in desglose.items()])
    
    prompt = f"""
    Eres un experto en metodologías de carbono forestal (Verra VCS) y en análisis de sistemas agrícolas. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre el almacenamiento de carbono. El análisis debe seguir el estilo del informe proporcionado (biomap.pdf), incluyendo comparaciones con rangos típicos y mención al potencial de créditos de carbono. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Área total: {stats['area_total_ha']:.1f} hectáreas
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Carbono total almacenado: {stats['carbono_total_ton']:.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Carbono promedio por hectárea: {stats['carbono_total_ton']/stats['area_total_ha']:.1f} ton C/ha
    - Número de puntos de muestreo: {stats['num_puntos']}
    - Rango de carbono en las muestras: {stats.get('carbono_min', 0):.1f} - {stats.get('carbono_max', 0):.1f} ton C/ha
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - Desglose de carbono por pools (ton C/ha):
    {desglose_str}

    Proporciona:
    1. Interpretación del valor de carbono por hectárea en el contexto del ecosistema (cultivo, pastizal, bosque, etc.). Compara con rangos típicos para el mismo tipo de ecosistema y con otros ecosistemas de referencia (ej. bosques maduros, pastizales naturales).
    2. Análisis de la distribución por pools: ¿qué pool es el más significativo? ¿Qué indica esto sobre la naturaleza del carbono (biomasa aérea vs. suelo)?
    3. Variabilidad espacial observada en las muestras y posibles causas (microclima, fertilidad, densidad de siembra, etc.).
    4. Potencial para proyectos de carbono bajo estándar VCS, mencionando la adicionalidad y permanencia. ¿Qué prácticas podrían aumentar el secuestro?
    5. Recomendaciones para mejorar la precisión en futuras mediciones.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_biodiversidad(df, stats):
    if model is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Gemini válida y un modelo disponible. Configure la clave en los secrets de Streamlit o en la variable de entorno GEMINI_API_KEY."
    
    prompt = f"""
    Eres un ecólogo experto en índices de biodiversidad, especialmente el índice de Shannon. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la biodiversidad. El análisis debe seguir el estilo del informe proporcionado (biomap.pdf), incluyendo categorización, implicaciones ecológicas y comparaciones con otros sistemas. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}
    - Rango del índice en las muestras: {stats.get('shannon_min', 0):.2f} - {stats.get('shannon_max', 0):.2f}
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Área total: {stats['area_total_ha']:.1f} ha
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - Rango de NDVI: {stats.get('ndvi_min', 0):.2f} - {stats.get('ndvi_max', 0):.2f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}
    - Rango de NDWI: {stats.get('ndwi_min', 0):.2f} - {stats.get('ndwi_max', 0):.2f}

    Proporciona:
    1. Interpretación del valor de Shannon: ¿en qué categoría se encuentra (Muy baja, Baja, Moderada, Alta, Muy Alta) según la escala estándar y el contexto del ecosistema?
    2. Implicaciones ecológicas de este nivel de biodiversidad: servicios ecosistémicos (polinización, control biológico de plagas, salud del suelo, ciclo de nutrientes), resiliencia del ecosistema, dependencia de insumos externos.
    3. Comparación con valores típicos para el tipo de ecosistema (ej. monocultivos intensivos, sistemas agroecológicos, pastizales naturales, bosques templados/tropicales).
    4. Análisis de la variabilidad espacial: ¿qué indican los rangos observados de Shannon, NDVI y NDWI sobre la heterogeneidad del área?
    5. Recomendaciones concretas para conservar o mejorar la biodiversidad, basadas en los datos (ej. creación de hábitats, diversificación de cultivos, reducción de pesticidas).
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_espectral(df, stats):
    if model is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Gemini válida y un modelo disponible. Configure la clave en los secrets de Streamlit o en la variable de entorno GEMINI_API_KEY."
    
    prompt = f"""
    Eres un especialista en teledetección y análisis espectral. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre los índices espectrales. El análisis debe seguir el estilo del informe proporcionado (biomap.pdf), incluyendo interpretación de cada índice, variabilidad y correlaciones con otras variables. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - Rango de NDVI: {stats.get('ndvi_min', 0):.2f} - {stats.get('ndvi_max', 0):.2f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}
    - Rango de NDWI: {stats.get('ndwi_min', 0):.2f} - {stats.get('ndwi_max', 0):.2f}
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Carbono promedio: {stats['carbono_total_ton']/stats['area_total_ha']:.1f} ton C/ha
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}

    Proporciona:
    1. Interpretación del NDVI: ¿qué indica sobre la salud, densidad y actividad fotosintética de la vegetación? Compara con valores de referencia (ej. >0.6 = vegetación densa, 0.3-0.6 = moderada, <0.2 = escasa).
    2. Interpretación del NDWI: ¿qué indica sobre el contenido de agua en la vegetación y el suelo? Valores cercanos a cero o negativos indican sequedad; positivos, humedad. Relación con la precipitación estimada.
    3. Variabilidad espacial de ambos índices: ¿qué nos dice sobre la heterogeneidad del área (topografía, suelos, microclimas)?
    4. Correlación entre NDVI y carbono: ¿existe una tendencia positiva? ¿Qué implica esto para la capacidad de secuestro?
    5. Correlación entre NDVI/NDWI y biodiversidad (Shannon): ¿se observa alguna relación? ¿Las áreas más verdes o más húmedas son más diversas?
    6. Conclusiones sobre el estado general del ecosistema basado en estos índices.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_forrajero(df, stats):
    if model is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Gemini válida y un modelo disponible. Configure la clave en los secrets de Streamlit o en la variable de entorno GEMINI_API_KEY."
    
    # Información de sublotes si está disponible
    sublotes_info = ""
    if 'sublotes' in stats and stats['sublotes']:
        sublotes_info = "Sublotes estimados:\n"
        for s in stats['sublotes'][:5]:  # mostrar primeros 5
            sublotes_info += f"   - Sublote {s['sublote_id']}: área {s['area_ha']:.1f} ha, productividad {s['disponibilidad_kg_ms_ha']:.0f} kg MS/ha, forraje aprovechable {s['forraje_aprovechable_kg_ms']/1000:.1f} ton\n"
    
    prompt = f"""
    Eres un zootecnista experto en manejo de pastizales y producción forrajera. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la disponibilidad forrajera y capacidad de carga. El análisis debe seguir el estilo del informe proporcionado (biomap.pdf), incluyendo interpretación de la productividad, cálculo de equivalentes vaca, y recomendaciones de manejo. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Sistema forrajero asignado: {stats.get('sistema_forrajero', 'pastizal_natural')}
    - Productividad forrajera estimada: {stats.get('forraje_productividad_kg_ms_ha', 0):.0f} kg MS/ha
    - Forraje disponible total: {stats.get('forraje_aprovechable_ton', 0)*1000:.0f} kg MS
    - Forraje aprovechable (considerando eficiencia de pastoreo): {stats.get('forraje_aprovechable_ton', 0):.1f} ton MS
    - Equivalentes vaca (EV) por día: {stats.get('ev_recomendado', 0)/30*12:.1f} EV/día (estimado)
    - EV recomendados para 30 días: {stats.get('ev_recomendado', 0):.1f} EV
    {sublotes_info}

    Proporciona:
    1. Interpretación de la productividad forrajera en el contexto del sistema (pastizal natural, mejorado, silvopastoril, etc.). Compara con rangos típicos para la región y el tipo de vegetación.
    2. Cálculo de la capacidad de carga (EV/ha/año) basado en los datos. Explica cómo se obtiene y su significado.
    3. Análisis de la heterogeneidad espacial: ¿cómo varía la productividad entre sublotes? ¿Qué implica para el manejo del pastoreo?
    4. Recomendaciones para maximizar la productividad forrajera de manera sostenible:
       - Prácticas de manejo (rotación, días de ocupación/descanso, altura de pastoreo).
       - Mejoras en la fertilidad del suelo (fertilización, enmiendas orgánicas).
       - Introducción de especies forrajeras mejoradas o sistemas silvopastoriles.
    5. Plan de rotación sugerido, incluyendo tiempos de ocupación y descanso para cada sublote, basado en la productividad.
    6. Estrategias para aumentar la resiliencia del sistema frente a sequías o cambios climáticos.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_recomendaciones_integradas(df, stats):
    if model is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Gemini válida y un modelo disponible. Configure la clave en los secrets de Streamlit o en la variable de entorno GEMINI_API_KEY."
    
    prompt = f"""
    Eres un consultor ambiental senior especializado en proyectos de carbono, biodiversidad y manejo ganadero sostenible. Con base en todos los datos proporcionados, genera un conjunto de recomendaciones integradas para el área de estudio. Las recomendaciones deben ser concretas, basadas en los datos y orientadas a la acción, siguiendo el estilo del informe biomap.pdf (incluye estrategias de agricultura de conservación, mejora de biodiversidad, monitoreo y potencial de créditos de carbono). No incluyas especulaciones.

    Datos integrados:
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Carbono total: {stats['carbono_total_ton']:.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f} (categoría: según análisis previo)
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}
    - Productividad forrajera: {stats.get('forraje_productividad_kg_ms_ha', 0):.0f} kg MS/ha
    - Forraje aprovechable total: {stats.get('forraje_aprovechable_ton', 0):.1f} ton MS
    - EV recomendado (30 días): {stats.get('ev_recomendado', 0):.1f} EV

    Proporciona:

    A. Estrategias para maximizar el almacenamiento de carbono (basadas en Agricultura de Conservación y Regenerativa):
       1. Labranza cero o mínima.
       2. Cultivos de cobertura.
       3. Rotación de cultivos diversificada.
       4. Agroforestería y sistemas silvopastoriles.
       5. Enmiendas orgánicas (compost, biochar).
       Indica cómo cada práctica contribuye al secuestro de carbono y su potencial de aumento (ej. 0.5-2.0 ton C/ha/año).

    B. Medidas para conservar o mejorar la biodiversidad:
       1. Creación y restauración de hábitats (franjas de flores, setos vivos, restauración de riberas).
       2. Diversificación agrícola (policultivos, variedades locales).
       3. Manejo Integrado de Plagas (reducción de pesticidas, control biológico).
       4. Manejo del agua (charcas, humedales).
       Justifica cada medida en función del bajo índice de Shannon y los valores de NDVI/NDWI.

    C. Recomendaciones para el monitoreo regular y sistemático:
       1. Frecuencia de mediciones de NDVI y NDWI (quincenal/mensual).
       2. Uso de otros índices (EVI, SAVI, LST).
       3. Mapeo de zonas de manejo.
       4. Verificación en campo (ground truthing).

    D. Potencial para generación de créditos de carbono bajo estándar VCS:
       1. Enfoque en AFOLU.
       2. Adicionalidad: demostrar que las prácticas van más allá de lo habitual.
       3. Línea base de carbono actual ({stats['carbono_total_ton']:.0f} ton C) y emisiones asociadas.
       4. Estimación del potencial de créditos adicionales con las prácticas recomendadas.

    E. Sinergias entre carbono, biodiversidad y producción forrajera:
       - ¿Cómo las prácticas que aumentan el carbono también benefician la biodiversidad y la productividad forrajera?
       - Ejemplos concretos (ej. sistemas silvopastoriles, cultivos de cobertura).

    F. Próximos pasos para validar los resultados y diseñar un proyecto:
       - Parcelas permanentes de muestreo.
       - Estudios de suelo detallados.
       - Consulta con comunidades locales y actores clave.
    """
    response = model.generate_content(prompt)
    return response.text
