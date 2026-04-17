# modules/ia_integration.py
# ===============================
# MÓDULO DE INTEGRACIÓN CON IA (GROQ)
# Funciones para generar análisis técnicos basados en datos
# Siguiendo el formato del informe biomap.pdf
# ===============================

import streamlit as st
import pandas as pd
import numpy as np
import os
from groq import Groq

# === CONFIGURACIÓN DE GROQ ===
GROQ_API_KEY = None
client = None
available_models = [
    "llama-3.3-70b-versatile",   # Modelo principal (reemplaza al descontinuado llama3-70b-8192)
    "llama-3.1-8b-instant",      # Modelo rápido y eficiente
    "mixtral-8x7b-32768",        # Gran ventana de contexto
    "llama-3.1-70b-versatile",   # Versión estable de 70B
    "deepseek-r1-distill-llama-70b",  # Modelo de razonamiento
    "qwen-qwen2-7b-instruct"     # Alternativa ligera
]

# Intentar obtener la API key desde secrets de Streamlit o variables de entorno
if "GROQ_API_KEY" in st.secrets:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    st.success("✅ API key de Groq cargada desde secrets de Streamlit.")
else:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    if GROQ_API_KEY:
        st.success("✅ API key de Groq cargada desde variable de entorno.")
    else:
        st.error("⚠️ No se encontró la API Key de Groq. La IA no estará disponible.")

# Configurar Groq si la clave existe
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        # Prueba opcional de conectividad (comentada para evitar errores de modelo descontinuado)
        # Se puede descomentar usando un modelo válido si se desea verificar la conexión.
        # test_model = available_models[0]  # Usa el primer modelo de la lista actualizada
        # test_response = client.chat.completions.create(
        #     model=test_model,
        #     messages=[{"role": "user", "content": "Responde con OK"}],
        #     max_tokens=5
        # )
        # if test_response and test_response.choices[0].message.content:
        #     st.success(f"✅ Groq configurado correctamente. Modelos disponibles: {', '.join(available_models)}")
        # else:
        #     st.error("❌ La respuesta de prueba de Groq no fue válida.")
        #     client = None
        st.success(f"✅ Cliente Groq creado correctamente. Modelos disponibles: {', '.join(available_models)}")
    except Exception as e:
        st.error(f"❌ Error al configurar Groq: {e}")
        client = None

def get_groq_response(prompt, model_name="llama-3.3-70b-versatile", temperature=0.7):
    """
    Envía un prompt a Groq y retorna la respuesta de texto.
    """
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=2048  # Suficiente para análisis detallados
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"**Error al consultar Groq:** {str(e)}"

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
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    desglose = stats.get('desglose', {})
    desglose_str = "\n".join([f"   - {k}: {v:.2f} ton C/ha" for k, v in desglose.items()])
    
    # Calcular estadísticas adicionales
    carbono_promedio = stats['carbono_total_ton'] / stats['area_total_ha'] if stats['area_total_ha'] > 0 else 0
    rango_carbono = f"{stats.get('carbono_min', 0):.1f} - {stats.get('carbono_max', 0):.1f}"
    
    prompt = f"""
    Eres un experto en metodologías de carbono forestal (Verra VCS, IPCC) y en análisis de sistemas agrícolas. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado, concreto y cuantitativo sobre el almacenamiento de carbono. El análisis debe seguir el estilo del informe biomap.pdf: incluir comparaciones con rangos típicos de la literatura, mención al potencial de créditos de carbono y un lenguaje técnico preciso. No incluyas especulaciones; utiliza únicamente los valores proporcionados.

    **Datos del área:**
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Número de puntos de muestreo: {stats['num_puntos']}
    
    **Carbono:**
    - Carbono total almacenado: {stats['carbono_total_ton']:.0f} ton C
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Carbono promedio por hectárea: {carbono_promedio:.1f} ton C/ha
    - Rango de carbono en las muestras: {rango_carbono} ton C/ha
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    
    **Desglose de carbono por pools (ton C/ha):**
    {desglose_str}

    **Instrucciones para el análisis (estructura obligatoria):**

    1. **Interpretación del valor promedio de carbono por hectárea**  
       - Compara {carbono_promedio:.1f} ton C/ha con rangos típicos para el ecosistema "{stats['tipo_ecosistema']}" (ej. pastizal natural: 30-80, bosque seco: 60-120, cultivo anual: 20-50, silvopastoril: 50-100).  
       - Indica si el valor se encuentra por debajo, dentro o por encima del rango esperado, y qué implica en términos de potencial de secuestro.

    2. **Análisis de la distribución por pools de carbono**  
       - Identifica el pool dominante (biomasa aérea, raíces, suelo, necromasa).  
       - Explica qué indica esa distribución sobre el origen del carbono (vegetación vs. materia orgánica del suelo) y la estabilidad del reservorio.

    3. **Variabilidad espacial**  
       - Con base en el rango observado ({rango_carbono}), calcula el coeficiente de variación aproximado (rango/promedio) y comenta la heterogeneidad.  
       - Sugiere causas probables (microtopografía, manejo diferencial, fertilidad edáfica, densidad de cobertura).

    4. **Potencial para proyectos de carbono bajo estándar VCS (AFOLU)**  
       - Evalúa la adicionalidad: ¿el carbono actual representa una línea base baja o alta? ¿Qué prácticas adicionales podrían implementarse (reforestación, manejo de pasturas, sistemas agroforestales)?  
       - Estima el potencial de incremento anual (ton C/ha/año) basado en prácticas comunes para este ecosistema.  
       - Menciona la importancia de la permanencia y las salvaguardas ambientales.

    5. **Recomendaciones técnicas para mejorar la precisión en futuras mediciones**  
       - Número mínimo de puntos de muestreo recomendado según la variabilidad observada.  
       - Uso de sensores remotos (LiDAR, radar) para estimar biomasa aérea.  
       - Estandarización de profundidad de muestreo de suelo y densidad aparente.

    **Formato de respuesta:** Párrafos concisos, viñetas para listas, tono profesional. Evita introducciones genéricas ("Claro que sí", "Basado en los datos"). Ve directo al análisis.
    """
    return get_groq_response(prompt)

def generar_analisis_biodiversidad(df, stats):
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    # Calcular categoría de Shannon
    shannon = stats['shannon_promedio']
    if shannon < 1.0:
        cat = "Muy baja"
    elif shannon < 1.5:
        cat = "Baja"
    elif shannon < 2.0:
        cat = "Moderada"
    elif shannon < 2.5:
        cat = "Alta"
    else:
        cat = "Muy alta"
    
    prompt = f"""
    Eres un ecólogo experto en índices de diversidad (especialmente Shannon-Wiener) y en servicios ecosistémicos. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la biodiversidad. El análisis debe seguir el estilo del informe biomap.pdf: incluir categorización según escalas estándar, implicaciones ecológicas, comparación con otros sistemas y recomendaciones de manejo. Utiliza vocabulario técnico (riqueza, equitatividad, ensamblaje de especies, disimilitud beta). No especules.

    **Datos:**
    - Índice de Shannon (H') promedio: {shannon:.3f} → Categoría: {cat}
    - Rango del índice en las muestras: {stats.get('shannon_min', 0):.2f} - {stats.get('shannon_max', 0):.2f}
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Área total: {stats['area_total_ha']:.1f} ha
    - NDVI promedio: {stats['ndvi_promedio']:.3f} (rango: {stats.get('ndvi_min', 0):.2f} - {stats.get('ndvi_max', 0):.2f})
    - NDWI promedio: {stats['ndwi_promedio']:.3f} (rango: {stats.get('ndwi_min', 0):.2f} - {stats.get('ndwi_max', 0):.2f})

    **Instrucciones para el análisis (estructura obligatoria):**

    1. **Interpretación del valor de Shannon**  
       - Justifica la categoría "{cat}" según la escala estándar (H' <1 muy baja, 1-1.5 baja, 1.5-2 moderada, 2-2.5 alta, >2.5 muy alta).  
       - Relaciona este valor con la estructura del ecosistema: monocultivo, pastizal seminatural, bosque fragmentado, etc.

    2. **Implicaciones ecológicas y servicios ecosistémicos**  
       - Evalúa cómo este nivel de diversidad afecta: polinización, control biológico de plagas, ciclo de nutrientes, estabilidad de la red trófica, resistencia a invasiones.  
       - Menciona la relación entre diversidad baja y dependencia de insumos externos (fertilizantes, plaguicidas).

    3. **Comparación con valores típicos**  
       - Compara con rangos documentados para: monocultivos intensivos (H'≈0.5-1.0), sistemas agroecológicos (1.2-1.8), pastizales naturales (1.5-2.2), bosques tropicales (2.5-3.5).  
       - Indica si el ecosistema estudiado se asemeja a algún sistema de referencia.

    4. **Variabilidad espacial y correlación con índices espectrales**  
       - Analiza el rango de Shannon: ¿es homogéneo o heterogéneo? ¿El NDVI y NDWI muestran patrones similares?  
       - Calcula la relación aproximada entre NDVI y Shannon (basado en los promedios): ¿existe una tendencia positiva? ¿Las áreas más verdes o más húmedas albergan mayor diversidad?  
       - Interpreta el NDWI como proxy de disponibilidad hídrica y su influencia en la riqueza de especies.

    5. **Recomendaciones concretas para conservar o mejorar la biodiversidad**  
       - Basado en los valores actuales, propón medidas específicas:  
         * Creación de hábitats (franjas de flores, setos vivos, restauración de riberas).  
         * Diversificación de cultivos (policultivos, rotaciones, cultivos de cobertura).  
         * Manejo integrado de plagas (reducción de pesticidas, control biológico).  
         * Manejo del agua (charcas temporales, humedales).  
       - Justifica cada medida en función de los déficits observados (ej. bajo NDWI sugiere estrés hídrico que limita diversidad).

    **Formato:** Técnico, conciso, con viñetas donde sea útil. Evita introducciones genéricas.
    """
    return get_groq_response(prompt)

def generar_analisis_espectral(df, stats):
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    carbono_promedio = stats['carbono_total_ton'] / stats['area_total_ha'] if stats['area_total_ha'] > 0 else 0
    
    prompt = f"""
    Eres un especialista en teledetección y análisis espectral con énfasis en índices de vegetación (NDVI, NDWI, EVI, SAVI) y su relación con variables biofísicas. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto. El análisis debe seguir el estilo del informe biomap.pdf: interpretación de cada índice, análisis de variabilidad, correlaciones con carbono y biodiversidad, y conclusiones sobre el estado del ecosistema. Usa terminología precisa (reflectancia, bandas del infrarrojo cercano, contenido de agua en el dosel, estrés hídrico, actividad fotosintética).

    **Datos espectrales:**
    - NDVI promedio: {stats['ndvi_promedio']:.3f}
    - Rango de NDVI: {stats.get('ndvi_min', 0):.3f} - {stats.get('ndvi_max', 0):.3f}
    - NDWI promedio: {stats['ndwi_promedio']:.3f}
    - Rango de NDWI: {stats.get('ndwi_min', 0):.3f} - {stats.get('ndwi_max', 0):.3f}
    
    **Variables asociadas:**
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Carbono promedio: {carbono_promedio:.1f} ton C/ha
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}

    **Instrucciones para el análisis (estructura obligatoria):**

    1. **Interpretación del NDVI (Índice de Vegetación de Diferencia Normalizada)**  
       - Clasifica el valor {stats['ndvi_promedio']:.3f} según escalas estándar:  
         * <0.1: suelo desnudo/agua  
         * 0.1-0.3: vegetación escasa o estresada  
         * 0.3-0.6: vegetación moderada (pastizales, cultivos)  
         * 0.6-0.8: vegetación densa (bosques, cultivos vigorosos)  
         * >0.8: vegetación muy densa.  
       - Relaciona con la actividad fotosintética, fracción de cobertura vegetal y biomasa aérea.

    2. **Interpretación del NDWI (Índice de Agua de Diferencia Normalizada)**  
       - Clasifica el valor {stats['ndwi_promedio']:.3f}:  
         * Negativo (< -0.2): sequedad extrema, vegetación sin agua.  
         * -0.2 a 0: estrés hídrico moderado.  
         * 0 a 0.2: contenido de agua normal en vegetación.  
         * >0.2: alta humedad en dosel o cuerpos de agua.  
       - Explica cómo afecta al metabolismo vegetal y a la productividad primaria.

    3. **Variabilidad espacial (rangos observados)**  
       - Calcula el coeficiente de variación aproximado para NDVI y NDWI.  
       - Interpreta la heterogeneidad: ¿zonas contrastantes (pastoreo intensivo vs. áreas en descanso)? ¿Influencia topográfica o edáfica?  
       - Sugiere posibles causas: manchas de fertilidad, compactación, drenaje.

    4. **Correlaciones con carbono y biodiversidad**  
       - Relación NDVI-Carbono: con base en el promedio, ¿existe una tendencia positiva esperada? Si el NDVI es bajo, ¿puede explicar el carbono moderado?  
       - Relación NDVI-Shannon: ¿áreas más verdes (NDVI alto) presentan mayor diversidad? Justifica usando los valores dados.  
       - Relación NDWI-Shannon: ¿la disponibilidad hídrica (NDWI) se correlaciona con la riqueza de especies?

    5. **Conclusiones sobre el estado general del ecosistema**  
       - Integra los tres índices (NDVI, NDWI, más rango de variabilidad) para diagnosticar:  
         * Salud vegetal (vigor, estrés).  
         * Homogeneidad/heterogeneidad del paisaje.  
         * Potencial de recuperación ante perturbaciones.  
       - Propone umbrales críticos para monitoreo.

    **Formato:** Técnico, conciso, con viñetas para listas. No uses introducciones genéricas.
    """
    return get_groq_response(prompt)

def generar_analisis_forrajero(df, stats):
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    # Información de sublotes si está disponible
    sublotes_info = ""
    if 'sublotes' in stats and stats['sublotes']:
        sublotes_info = "**Sublotes estimados (primeros 5):**\n"
        for s in stats['sublotes'][:5]:
            sublotes_info += f"  - Sublote {s['sublote_id']}: área {s['area_ha']:.1f} ha, productividad {s['disponibilidad_kg_ms_ha']:.0f} kg MS/ha, forraje aprovechable {s['forraje_aprovechable_kg_ms']/1000:.1f} ton MS\n"
    
    productividad = stats.get('forraje_productividad_kg_ms_ha', 0)
    forraje_total = stats.get('forraje_aprovechable_ton', 0) * 1000  # kg
    ev_30d = stats.get('ev_recomendado', 0)
    ev_dia = ev_30d / 30 if ev_30d > 0 else 0
    # Capacidad de carga anual (EV/ha/año) asumiendo 365 días y eficiencia de pastoreo
    carga_anual = (ev_dia * 365) / stats['area_total_ha'] if stats['area_total_ha'] > 0 else 0
    
    prompt = f"""
    Eres un zootecnista experto en manejo de pastizales, producción forrajera y sistemas silvopastoriles. Con base en los siguientes datos de un área de estudio, genera un análisis técnico detallado y concreto sobre la disponibilidad forrajera y capacidad de carga. El análisis debe seguir el estilo del informe biomap.pdf: interpretación de la productividad, cálculo de carga animal, heterogeneidad espacial, recomendaciones de manejo rotacional y estrategias de resiliencia. Usa terminología precisa (materia seca (MS), eficiencia de pastoreo, período de descanso, carga instantánea, equivalentes vaca (EV), unidad animal (UA), sistema Voisin, pastoreo racional Voisin).

    **Datos del sistema:**
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Sistema forrajero asignado: {stats.get('sistema_forrajero', 'pastizal_natural')}
    
    **Producción forrajera:**
    - Productividad estimada: {productividad:.0f} kg MS/ha (materia seca por hectárea)
    - Forraje disponible total: {forraje_total:.0f} kg MS
    - Forraje aprovechable (eficiencia de pastoreo ~50%): {stats.get('forraje_aprovechable_ton', 0):.1f} ton MS
    - Equivalentes vaca (EV) por día: {ev_dia:.1f} EV/día
    - EV recomendados para 30 días: {ev_30d:.1f} EV
    - Capacidad de carga estimada: {carga_anual:.1f} EV/ha/año
    
    {sublotes_info}

    **Instrucciones para el análisis (estructura obligatoria):**

    1. **Interpretación de la productividad forrajera**  
       - Compara {productividad:.0f} kg MS/ha con rangos típicos:  
         * Pastizal natural degradado: <1000 kg MS/ha  
         * Pastizal natural mejorado: 1500-2500 kg MS/ha  
         * Pastura cultivada (pasto estrella, brachiaria): 3000-5000 kg MS/ha  
         * Silvopastoril intensivo: 4000-7000 kg MS/ha.  
       - Indica si el sistema actual es deficitario, adecuado o superavitario para la región.

    2. **Cálculo y análisis de la capacidad de carga**  
       - Explica cómo se obtiene la capacidad de carga (EV/ha/año) a partir de la productividad y la eficiencia de pastoreo.  
       - Compara el valor obtenido ({carga_anual:.1f} EV/ha/año) con estándares zonales (ej. 0.5-1.0 EV/ha/año para pastizal natural en secano, 2-3 EV para pasturas mejoradas).  
       - Evalúa si la carga actual es sostenible o si hay sobrepastoreo/subpastoreo.

    3. **Heterogeneidad espacial y manejo por sublotes**  
       - Analiza la variabilidad de productividad entre sublotes (si hay datos). Calcula el rango y el coeficiente de variación.  
       - Propone un diseño de potreros basado en la productividad: los más productivos para periodos de ocupación cortos, los menos productivos para descanso prolongado o mejoras.  
       - Menciona la importancia de la uniformidad del pastoreo.

    4. **Recomendaciones para maximizar la productividad forrajera sostenible**  
       - **Manejo del pastoreo:** rotación con períodos de ocupación de 1-3 días y descanso de 25-40 días según estación.  
       - **Mejoras de suelo:** fertilización nitrogenada (si aplica), encalado, incorporación de leguminosas (fijación de N).  
       - **Introducción de especies:** gramíneas mejoradas (ej. Megathyrsus maximus) y leguminosas forrajeras (Leucaena, Cratylia).  
       - **Sistemas silvopastoriles:** árboles dispersos para sombra y forraje adicional.

    5. **Plan de rotación sugerido**  
       - Basado en la productividad de los sublotes, define:  
         * Número de potreros (mínimo 8-12).  
         * Días de ocupación (2-3 días).  
         * Días de descanso (calculados como productividad × eficiencia / carga).  
       - Ejemplo numérico con los datos disponibles.

    6. **Estrategias de resiliencia climática**  
       - Almacenamiento de forraje (heno, ensilaje) para épocas secas.  
       - Bancos de proteína (leguminosas arbustivas).  
       - Manejo de la carga animal según disponibilidad estacional.

    **Formato:** Técnico, conciso, con viñetas y cálculos donde corresponda.
    """
    return get_groq_response(prompt)

def generar_recomendaciones_integradas(df, stats):
    if client is None:
        return "**IA no disponible.** La generación de análisis con IA requiere una API key de Groq válida. Configure la clave en los secrets de Streamlit o en la variable de entorno GROQ_API_KEY."
    
    carbono_promedio = stats['carbono_total_ton'] / stats['area_total_ha'] if stats['area_total_ha'] > 0 else 0
    productividad = stats.get('forraje_productividad_kg_ms_ha', 0)
    
    prompt = f"""
    Eres un consultor ambiental senior especializado en proyectos de carbono (VCS/CCB), biodiversidad y manejo ganadero sostenible. Con base en todos los datos proporcionados, genera un conjunto de recomendaciones integradas para el área de estudio. Las recomendaciones deben ser concretas, priorizadas, basadas en los datos y orientadas a la acción, siguiendo el estilo del informe biomap.pdf (estrategias de agricultura de conservación, mejora de biodiversidad, monitoreo, potencial de créditos de carbono y sinergias). Utiliza vocabulario técnico y evita especulaciones.

    **Datos integrados:**
    - Área total: {stats['area_total_ha']:.1f} ha
    - Tipo de ecosistema: {stats['tipo_ecosistema']}
    - Carbono total: {stats['carbono_total_ton']:.0f} ton C (promedio {carbono_promedio:.1f} ton C/ha)
    - CO₂ equivalente: {stats['co2_total_ton']:.0f} ton CO₂e
    - Índice de Shannon promedio: {stats['shannon_promedio']:.3f}
    - NDVI promedio: {stats['ndvi_promedio']:.3f}  (rango: {stats.get('ndvi_min', 0):.2f}-{stats.get('ndvi_max', 0):.2f})
    - NDWI promedio: {stats['ndwi_promedio']:.3f}  (rango: {stats.get('ndwi_min', 0):.2f}-{stats.get('ndwi_max', 0):.2f})
    - Productividad forrajera: {productividad:.0f} kg MS/ha
    - Forraje aprovechable total: {stats.get('forraje_aprovechable_ton', 0):.1f} ton MS
    - EV recomendado (30 días): {stats.get('ev_recomendado', 0):.1f} EV

    **Instrucciones para las recomendaciones (estructura obligatoria):**

    **A. Estrategias para maximizar el almacenamiento de carbono (Agricultura de Conservación y Regenerativa)**  
    Para cada práctica, indica el mecanismo de secuestro y una estimación de potencial de aumento (ton C/ha/año):
    1. Labranza cero o mínima → reduce mineralización del suelo.
    2. Cultivos de cobertura (gramíneas + leguminosas) → aporte de biomasa radical.
    3. Rotación de cultivos diversificada → mejora estructura del suelo.
    4. Agroforestería y sistemas silvopastoriles → incorporación de biomasa leñosa.
    5. Enmiendas orgánicas (compost, biochar) → estabilización de carbono.

    **B. Medidas para conservar o mejorar la biodiversidad**  
    Justifica cada medida en función de los valores de Shannon y NDVI/NDWI:
    1. Creación de hábitats (franjas de flores, setos vivos, restauración de riberas).
    2. Diversificación agrícola (policultivos, variedades locales).
    3. Manejo Integrado de Plagas (reducción de pesticidas, control biológico).
    4. Manejo del agua (charcas, humedales, cosecha de agua de lluvia).

    **C. Recomendaciones para el monitoreo regular y sistemático**  
    1. Frecuencia de mediciones de NDVI y NDWI (quincenal/mensual) con Sentinel-2 o Planet.
    2. Uso de otros índices: EVI (para vegetación densa), SAVI (para suelo desnudo), LST (estrés térmico).
    3. Mapeo de zonas de manejo homogéneas (clusterización de NDVI y topografía).
    4. Verificación en campo (ground truthing) con parcelas permanentes de 20×20 m.

    **D. Potencial para generación de créditos de carbono bajo estándar VCS (AFOLU)**  
    1. Enfoque metodológico: VM0017 (Adopción de prácticas agrícolas sostenibles) o VM0032 (Sistemas silvopastoriles).
    2. Adicionalidad: comparar línea base actual ({carbono_promedio:.1f} ton C/ha) con escenario proyecto (+X ton C/ha).
    3. Estimación de créditos anuales: supongamos un incremento de 0.5-2 ton C/ha/año → créditos de CO₂e por ha.
    4. Costos de verificación y mercado voluntario (precios actuales ~10-30 USD/tCO₂e).

    **E. Sinergias entre carbono, biodiversidad y producción forrajera**  
    - Explica cómo prácticas como sistemas silvopastoriles aumentan carbono (biomasa arbórea), mejoran biodiversidad (hábitat) y elevan productividad (sombra, leguminosas).  
    - Ejemplo concreto: introducción de Leucaena leucocephala en pasturas.

    **F. Próximos pasos para validar resultados y diseñar un proyecto**  
    1. Parcelas permanentes de muestreo (carbono, biodiversidad, forraje).
    2. Estudios de suelo detallados (textura, densidad aparente, carbono orgánico).
    3. Consulta con comunidades locales y actores clave (plan de salvaguardas).
    4. Preparación de PIN (Project Idea Note) para registro VCS.

    **Formato:** Estructura con letras (A, B, C...), viñetas, lenguaje técnico pero accesible. Evita introducciones genéricas.
    """
    return get_groq_response(prompt)
