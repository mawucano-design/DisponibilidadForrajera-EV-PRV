# modules/ia_integration.py
# ===============================
# MÓDULO DE INTEGRACIÓN CON IA (GEMINI)
# Funciones para generar análisis técnicos basados en datos
# ===============================

import streamlit as st
import pandas as pd
import numpy as np
import os
import google.generativeai as genai

# Configurar Gemini
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')  # o el modelo que prefieras
else:
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
        # Crear un DataFrame básico con puntos de muestreo
        if 'puntos_carbono' in resultados:
            df = pd.DataFrame(resultados['puntos_carbono'])
    return df, stats

def generar_analisis_carbono(df, stats):
    if model is None:
        return "IA no disponible. Configure la API key de Gemini."
    prompt = f"""
    Eres un experto en metodologías de carbono forestal (Verra VCS). Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre el almacenamiento de carbono. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Área total: {stats['area_total_ha']:.1f} hectáreas
    - Carbono total almacenado: {stats['carbono_total_ton']:.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Número de puntos de muestreo: {stats['num_puntos']}
    - NDVI promedio: {stats['ndvi_promedio']:.3f}

    Proporciona:
    1. Interpretación del valor de carbono por hectárea (calculado a partir de los datos).
    2. Comparación con valores de referencia para el tipo de ecosistema (bosques tropicales, cultivos, etc.).
    3. Potencial para proyectos de carbono bajo estándar VCS, mencionando la adicionalidad y permanencia.
    4. Recomendaciones para mejorar la precisión en futuras mediciones.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_biodiversidad(df, stats):
    if model is None:
        return "IA no disponible. Configure la API key de Gemini."
    prompt = f"""
    Eres un ecólogo experto en índices de biodiversidad. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la biodiversidad utilizando el índice de Shannon. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Área total: {stats['area_total_ha']:.1f} ha
    - NDVI promedio: {stats['ndvi_promedio']:.3f}

    Proporciona:
    1. Interpretación del valor de Shannon (categoría: Muy baja, Baja, Moderada, Alta, Muy Alta) según el ecosistema.
    2. Implicaciones ecológicas de este nivel de biodiversidad (servicios ecosistémicos, resiliencia).
    3. Recomendaciones concretas para conservar o mejorar la biodiversidad en el área.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_espectral(df, stats):
    if model is None:
        return "IA no disponible. Configure la API key de Gemini."
    prompt = f"""
    Eres un especialista en teledetección y análisis espectral. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre los índices espectrales. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}
    - Tipo de ecosistema: {stats['tipo_ecosistema']}

    Proporciona:
    1. Interpretación del NDVI: qué indica sobre la salud y densidad de la vegetación.
    2. Interpretación del NDWI: qué indica sobre el contenido de agua en la vegetación y suelo.
    3. Relación entre ambos índices y su relevancia para el manejo del área.
    4. Posibles causas de los valores observados (estrés hídrico, degradación, etc.) basadas en los datos.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_analisis_forrajero(df, stats):
    if model is None:
        return "IA no disponible. Configure la API key de Gemini."
    prompt = f"""
    Eres un zootecnista experto en manejo de pastizales y producción forrajera. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la disponibilidad forrajera y capacidad de carga. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    Datos:
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Sistema forrajero asignado: {stats.get('sistema_forrajero', 'No especificado')}
    - Productividad forrajera estimada: {stats.get('forraje_productividad_kg_ms_ha', 0):.0f} kg MS/ha
    - Forraje aprovechable total: {stats.get('forraje_aprovechable_ton', 0):.1f} ton MS
    - Equivalentes vaca recomendados (30 días): {stats.get('ev_recomendado', 0):.1f} EV

    Proporciona:
    1. Interpretación de la productividad forrajera en el contexto del sistema (pastizal natural, mejorado, etc.).
    2. Cálculo de la capacidad de carga (EV/ha/año) basado en los datos.
    3. Recomendaciones para el manejo del pastoreo (rotación, días de ocupación/descanso) que maximicen la sostenibilidad.
    4. Sugerencias para mejorar la productividad forrajera (fertilización, especies, etc.) si aplica.
    """
    response = model.generate_content(prompt)
    return response.text

def generar_recomendaciones_integradas(df, stats):
    if model is None:
        return "IA no disponible. Configure la API key de Gemini."
    prompt = f"""
    Eres un consultor ambiental senior especializado en proyectos de carbono, biodiversidad y manejo ganadero sostenible. Con base en todos los datos proporcionados, genera un conjunto de recomendaciones integradas para el área de estudio. Las recomendaciones deben ser concretas, basadas en los datos y orientadas a la acción. No incluyas especulaciones.

    Datos integrados:
    - Área total: {stats['area_total_ha']:.1f} ha
    - Carbono total: {stats['carbono_total_ton']:.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Índice de Shannon: {stats['shannon_promedio']:.3f}
    - NDVI: {stats['ndvi_promedio']:.3f}
    - NDWI: {stats['ndwi_promedio']:.3f}
    - Productividad forrajera: {stats.get('forraje_productividad_kg_ms_ha', 0):.0f} kg MS/ha
    - EV recomendado: {stats.get('ev_recomendado', 0):.1f} EV

    Proporciona:
    1. Recomendaciones para potenciar el secuestro de carbono (prácticas agrícolas/forestales).
    2. Recomendaciones para conservar o mejorar la biodiversidad.
    3. Recomendaciones para el manejo ganadero sostenible (rotación, carga animal, etc.).
    4. Sinergias posibles entre carbono, biodiversidad y producción forrajera.
    5. Próximos pasos para validar los resultados (monitoreo, parcelas permanentes, etc.).
    """
    response = model.generate_content(prompt)
    return response.text
