# modules/ia_integration.py
import os
import pandas as pd
from typing import Dict
import google.generativeai as genai
import streamlit as st

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def _get_available_model():
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        models = genai.list_models()
        valid_models = [m for m in models if 'generateContent' in m.supported_generation_methods]
        if not valid_models:
            raise RuntimeError("No hay modelos Gemini que soporten generateContent.")
        model_names = [m.name for m in valid_models]
        print(f"Modelos Gemini disponibles: {model_names}")
        chosen_model = valid_models[0].name
        print(f"Usando modelo: {chosen_model}")
        return genai.GenerativeModel(chosen_model)
    except Exception as e:
        st.error(f"Error al listar modelos Gemini: {str(e)}")
        raise

def llamar_gemini(prompt: str, system_prompt: str = None, temperature: float = 0.3) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno")
    model = _get_available_model()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    try:
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=4096
            )
        )
        return response.text
    except Exception as e:
        print(f"Error en llamada a Gemini: {str(e)}")
        raise

def preparar_resumen(resultados: Dict) -> tuple:
    """Prepara un DataFrame resumen y estadísticas a partir de los resultados del análisis."""
    # Extraer puntos de muestreo
    puntos_carbono = resultados.get('puntos_carbono', [])
    puntos_biodiversidad = resultados.get('puntos_biodiversidad', [])
    puntos_ndvi = resultados.get('puntos_ndvi', [])
    puntos_ndwi = resultados.get('puntos_ndwi', [])
    
    # Crear DataFrame combinado
    data = []
    for i in range(min(len(puntos_carbono), len(puntos_biodiversidad), len(puntos_ndvi), len(puntos_ndwi))):
        data.append({
            'carbono_ton_ha': puntos_carbono[i]['carbono_ton_ha'],
            'indice_shannon': puntos_biodiversidad[i]['indice_shannon'],
            'ndvi': puntos_ndvi[i]['ndvi'],
            'ndwi': puntos_ndwi[i]['ndwi'],
            'precipitacion': puntos_carbono[i].get('precipitacion', 0),
            'tipo_vegetacion': resultados.get('tipo_ecosistema', 'N/A')
        })
    df = pd.DataFrame(data)
    
    stats = {
        'area_total_ha': resultados.get('area_total_ha', 0),
        'carbono_total_ton': resultados.get('carbono_total_ton', 0),
        'co2_total_ton': resultados.get('co2_total_ton', 0),
        'carbono_promedio_ha': resultados.get('carbono_promedio_ha', 0),
        'shannon_promedio': resultados.get('shannon_promedio', 0),
        'ndvi_promedio': resultados.get('ndvi_promedio', 0),
        'ndwi_promedio': resultados.get('ndwi_promedio', 0),
        'num_puntos': resultados.get('num_puntos', 0),
        'tipo_ecosistema': resultados.get('tipo_ecosistema', 'N/A'),
        'es_cultivo': resultados.get('es_cultivo', False)
    }
    return df, stats

def generar_analisis_carbono(df: pd.DataFrame, stats: Dict) -> str:
    system = "Eres un especialista en carbono forestal y metodologías Verra VCS. Proporciona un análisis técnico detallado."
    prompt = f"""
    Se ha realizado un análisis de carbono en un área de {stats['area_total_ha']:.1f} ha, tipo de ecosistema: {stats['tipo_ecosistema']}.
    Resultados:
    - Carbono total almacenado: {stats['carbono_total_ton']:,.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:,.0f} ton CO₂e
    - Carbono promedio por hectárea: {stats['carbono_promedio_ha']:.1f} ton C/ha
    - Número de puntos de muestreo: {stats['num_puntos']}

    Datos de muestra (primeras 10 filas):
    {df[['carbono_ton_ha', 'ndvi', 'precipitacion']].head(10).to_string()}

    Proporciona un análisis que incluya:
    1. Interpretación de los valores de carbono en el contexto del ecosistema.
    2. Comparación con rangos típicos para este tipo de vegetación.
    3. Potencial para proyectos de carbono (REDD+).
    4. Recomendaciones para mejorar la precisión de las estimaciones.
    """
    return llamar_gemini(prompt, system_prompt=system, temperature=0.3)

def generar_analisis_biodiversidad(df: pd.DataFrame, stats: Dict) -> str:
    system = "Eres un ecólogo experto en biodiversidad y el índice de Shannon. Proporciona un análisis técnico."
    prompt = f"""
    Se ha evaluado la biodiversidad en un área de {stats['area_total_ha']:.1f} ha, tipo de ecosistema: {stats['tipo_ecosistema']}.
    Resultados:
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}
    - Categoría: {'Cultivo' if stats['es_cultivo'] else 'Ecosistema natural'}

    Datos de muestra (primeras 10 filas):
    {df[['indice_shannon', 'ndvi', 'ndwi']].head(10).to_string()}

    Proporciona un análisis que incluya:
    1. Interpretación del valor de Shannon en el contexto del ecosistema.
    2. Comparación con valores esperados para este tipo de vegetación.
    3. Implicaciones para la conservación.
    4. Recomendaciones para mejorar la biodiversidad.
    """
    return llamar_gemini(prompt, system_prompt=system, temperature=0.3)

def generar_analisis_espectral(df: pd.DataFrame, stats: Dict) -> str:
    system = "Eres un especialista en teledetección aplicada a ecosistemas. Analiza los índices NDVI y NDWI."
    prompt = f"""
    Se han calculado índices espectrales en un área de {stats['area_total_ha']:.1f} ha.
    Resultados:
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}

    Datos de muestra:
    {df[['ndvi', 'ndwi', 'carbono_ton_ha', 'indice_shannon']].head(10).to_string()}

    Proporciona un análisis que incluya:
    1. Interpretación de los valores de NDVI y NDWI en relación con la salud de la vegetación y disponibilidad hídrica.
    2. Correlación con carbono y biodiversidad (si es evidente).
    3. Posibles causas de variabilidad espacial.
    4. Recomendaciones para el monitoreo.
    """
    return llamar_gemini(prompt, system_prompt=system, temperature=0.3)

def generar_recomendaciones_integradas(df: pd.DataFrame, stats: Dict) -> str:
    system = "Eres un asesor técnico senior en proyectos ambientales. Integra todos los análisis en recomendaciones prácticas."
    prompt = f"""
    Con base en los siguientes datos resumidos del área de estudio:
    - Área: {stats['area_total_ha']:.1f} ha
    - Ecosistema: {stats['tipo_ecosistema']}
    - Carbono total: {stats['carbono_total_ton']:,.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:,.0f} ton CO₂e
    - Índice de Shannon: {stats['shannon_promedio']:.3f}
    - NDVI: {stats['ndvi_promedio']:.3f}
    - NDWI: {stats['ndwi_promedio']:.3f}

    Proporciona un plan de manejo integrado que incluya:
    1. Estrategias para maximizar el almacenamiento de carbono.
    2. Medidas para conservar o mejorar la biodiversidad.
    3. Recomendaciones para el monitoreo con índices espectrales.
    4. Potencial para generar créditos de carbono (VCS).
    5. Priorización de acciones según urgencia/impacto.
    """
    return llamar_gemini(prompt, system_prompt=system, temperature=0.3)
