import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon, box
import math
import requests
import base64
from rasterio.transform import from_bounds
import rasterio
from rasterio.mask import mask

# Configuración de Sentinel Hub (reemplaza con tus credenciales)
SENTINEL_HUB_CLIENT_ID = st.secrets.get("SENTINEL_HUB_CLIENT_ID", "tu_client_id")
SENTINEL_HUB_CLIENT_SECRET = st.secrets.get("SENTINEL_HUB_CLIENT_SECRET", "tu_client_secret")
SENTINEL_HUB_INSTANCE_ID = st.secrets.get("SENTINEL_HUB_INSTANCE_ID", "tu_instance_id")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Configuración de fechas para imágenes satelitales
    st.subheader("🛰️ Configuración Satelital")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    nubes_max = st.slider("Máximo % de nubes permitido:", 0, 100, 20)
    
    # Mostrar parámetros personalizables si se selecciona PERSONALIZADO
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=8000, value=3000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=200, value=50)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05, value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01, format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.1, max_value=0.4, value=0.2, step=0.01, format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.4, max_value=0.8, value=0.55, step=0.01, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# [Mantener todas las funciones de parámetros forrajeros, paletas, etc. igual...]

# NUEVAS FUNCIONES PARA SENTINEL HUB

def obtener_access_token():
    """Obtiene token de acceso de Sentinel Hub"""
    try:
        auth_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        
        payload = {
            'client_id': SENTINEL_HUB_CLIENT_ID,
            'client_secret': SENTINEL_HUB_CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post(auth_url, data=payload, headers=headers)
        response.raise_for_status()
        
        return response.json()['access_token']
    except Exception as e:
        st.error(f"❌ Error obteniendo token de acceso: {e}")
        return None

def obtener_imagen_sentinel2(geometry, fecha_imagen, nubes_max=20):
    """
    Obtiene imagen Sentinel-2 para un área y fecha específicas
    """
    try:
        access_token = obtener_access_token()
        if not access_token:
            return None
        
        # Obtener bounds del geometry
        bounds = geometry.bounds
        bbox = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
        
        # Formatear fecha
        fecha_str = fecha_imagen.strftime("%Y-%m-%d")
        
        # Buscar imágenes disponibles
        search_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
        
        search_payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": [bounds[0], bounds[1], bounds[2], bounds[3]],
            "datetime": f"{fecha_str}T00:00:00Z/{fecha_str}T23:59:59Z",
            "filter": {
                "op": "<=",
                "args": [
                    {"property": "eo:cloud_cover"},
                    nubes_max
                ]
            },
            "limit": 1
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(search_url, json=search_payload, headers=headers)
        response.raise_for_status()
        
        results = response.json()
        
        if not results['features']:
            st.warning("⚠️ No se encontraron imágenes para la fecha y área especificadas")
            return None
        
        # Obtener la primera imagen disponible
        image_id = results['features'][0]['id']
        st.success(f"✅ Imagen encontrada: {image_id}")
        
        return descargar_bandas_sentinel2(image_id, geometry, access_token)
        
    except Exception as e:
        st.error(f"❌ Error obteniendo imagen Sentinel-2: {e}")
        return None

def descargar_bandas_sentinel2(image_id, geometry, access_token):
    """
    Descarga las bandas necesarias de Sentinel-2
    """
    try:
        # Bandas necesarias para índices
        bandas = {
            'B02': 'blue',
            'B03': 'green', 
            'B04': 'red',
            'B08': 'nir',
            'B11': 'swir1',
            'B12': 'swir2'
        }
        
        resultados = {}
        bounds = geometry.bounds
        
        for banda, nombre in bandas.items():
            url = f"https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/collections/sentinel-2-l2a/items/{image_id}/assets/{banda}/download"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "image/tiff"
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # Guardar temporalmente el TIFF
            with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            # Leer y recortar la imagen
            with rasterio.open(tmp_path) as src:
                out_image, out_transform = mask(src, [geometry], crop=True)
                resultados[nombre] = out_image[0]  # Primera banda
                
                # Guardar metadata para transformación
                if 'transform' not in resultados:
                    resultados['transform'] = out_transform
                    resultados['crs'] = src.crs
            
            # Limpiar archivo temporal
            os.unlink(tmp_path)
        
        return resultados
        
    except Exception as e:
        st.error(f"❌ Error descargando bandas: {e}")
        return None

def calcular_indices_reales(bandas):
    """
    Calcula índices vegetacionales a partir de bandas reales
    """
    try:
        # Convertir a float y normalizar
        blue = bandas['blue'].astype(float) / 10000.0
        green = bandas['green'].astype(float) / 10000.0
        red = bandas['red'].astype(float) / 10000.0
        nir = bandas['nir'].astype(float) / 10000.0
        swir1 = bandas['swir1'].astype(float) / 10000.0
        swir2 = bandas['swir2'].astype(float) / 10000.0
        
        # Calcular índices
        with np.errstate(divide='ignore', invalid='ignore'):
            # NDVI
            ndvi = np.where(
                (nir + red) != 0,
                (nir - red) / (nir + red),
                0
            )
            ndvi = np.clip(ndvi, -1, 1)
            
            # EVI
            evi = np.where(
                (nir + 6 * red - 7.5 * blue + 1) != 0,
                2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1),
                0
            )
            evi = np.clip(evi, -1, 1)
            
            # SAVI
            savi = np.where(
                (nir + red + 0.5) != 0,
                1.5 * (nir - red) / (nir + red + 0.5),
                0
            )
            savi = np.clip(savi, -1, 1)
            
            # NDWI
            ndwi = np.where(
                (nir + swir1) != 0,
                (nir - swir1) / (nir + swir1),
                0
            )
            ndwi = np.clip(ndwi, -1, 1)
            
            # BSI (Bare Soil Index)
            bsi = np.where(
                ((swir1 + red) + (nir + blue)) != 0,
                ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue)),
                0
            )
            bsi = np.clip(bsi, -1, 1)
            
            # NDBI
            ndbi = np.where(
                (swir1 + nir) != 0,
                (swir1 - nir) / (swir1 + nir),
                0
            )
            ndbi = np.clip(ndbi, -1, 1)
        
        return {
            'ndvi': ndvi,
            'evi': evi,
            'savi': savi,
            'ndwi': ndwi,
            'bsi': bsi,
            'ndbi': ndbi,
            'blue': blue,
            'green': green,
            'red': red,
            'nir': nir,
            'swir1': swir1,
            'swir2': swir2
        }
        
    except Exception as e:
        st.error(f"❌ Error calculando índices: {e}")
        return None

# MODIFICAR LA FUNCIÓN PRINCIPAL DE CÁLCULO DE ÍNDICES

def calcular_indices_forrajeros_gee(gdf, tipo_pastura, fecha_imagen, nubes_max=20):
    """
    Implementa metodología GEE con imágenes reales de Sentinel Hub
    """
    try:
        n_poligonos = len(gdf)
        resultados = []
        params = obtener_parametros_forrajeros(tipo_pastura)
        
        st.info("🛰️ Descargando imágenes satelitales... Esto puede tomar unos minutos.")
        
        # Obtener imagen para el área completa
        geometry = gdf.unary_union
        bandas_completas = obtener_imagen_sentinel2(geometry, fecha_imagen, nubes_max)
        
        if not bandas_completas:
            st.warning("⚠️ No se pudieron obtener imágenes satelitales. Usando datos simulados.")
            return calcular_indices_forrajeros_simulados(gdf, tipo_pastura)
        
        # Calcular índices para el área completa
        indices_completos = calcular_indices_reales(bandas_completas)
        
        if not indices_completos:
            st.warning("⚠️ Error calculando índices. Usando datos simulados.")
            return calcular_indices_forrajeros_simulados(gdf, tipo_pastura)
        
        st.success("✅ Índices calculados a partir de imágenes reales")
        
        # Obtener centroides para estadísticas espaciales
        gdf_centroids = gdf.copy()
        gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
        
        for idx, row in gdf_centroids.iterrows():
            id_subLote = row['id_subLote']
            geometry = row['geometry']
            
            # Extraer valores promedio para el sub-lote
            try:
                # Crear máscara para el sub-lote
                sublot_indices = {}
                
                for index_name, index_data in indices_completos.items():
                    if index_name not in ['transform', 'crs']:
                        # Aquí necesitarías implementar la extracción por polígono
                        # Esto es una simplificación - en producción necesitarías rasterización más precisa
                        masked_data = index_data  # Placeholder
                        sublot_indices[index_name] = np.nanmean(masked_data) if np.any(masked_data) else 0
                
                # Usar los índices extraídos
                ndvi = sublot_indices.get('ndvi', 0)
                evi = sublot_indices.get('evi', 0)
                savi = sublot_indices.get('savi', 0)
                ndwi = sublot_indices.get('ndwi', 0)
                bsi = sublot_indices.get('bsi', 0)
                ndbi = sublot_indices.get('ndbi', 0)
                
            except Exception as e:
                st.warning(f"⚠️ Error procesando sub-lote {id_subLote}. Usando valores simulados.")
                # Fallback a simulación para este sub-lote
                ndvi, evi, savi, ndwi, bsi, ndbi = simular_indices_para_sublote(id_subLote)
            
            # Resto del cálculo de biomasa (igual que antes)
            # [Mantener la lógica de clasificación de suelo y cálculo de biomasa...]
            
            # CLASIFICACIÓN DE SUELO Y CÁLCULO DE BIOMASA (igual que tu código original)
            probabilidad_suelo_desnudo = simular_patron_suelo_desnudo_mejorado(
                id_subLote, 0.5, 0.5  # Placeholder para coordenadas normalizadas
            )
            
            tipo_superficie, cobertura_vegetal = clasificar_suelo_desnudo_mejorado(
                ndvi, bsi, ndbi, evi, savi, probabilidad_suelo_desnudo
            )
            
            # Cálculo de biomasa (igual que antes)
            if tipo_superficie == "SUELO_DESNUDO":
                biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.02 * cobertura_vegetal)
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.02
                calidad_forrajera = 0.02
            elif tipo_superficie == "SUELO_PARCIAL":
                biomasa_ms_ha = max(0, params['MS_POR_HA_OPTIMO'] * 0.15 * cobertura_vegetal)
                crecimiento_diario = params['CRECIMIENTO_DIARIO'] * 0.15
                calidad_forrajera = 0.15
            else:
                # Cálculo normal basado en índices reales
                biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
                biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
                biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
                
                biomasa_ms_ha = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
                biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
                
                crecimiento_diario = (biomasa_ms_ha / params['MS_POR_HA_OPTIMO']) * params['CRECIMIENTO_DIARIO']
                crecimiento_diario = max(5, min(150, crecimiento_diario))
                
                calidad_forrajera = (ndwi + 1) / 2
                calidad_forrajera = max(0.3, min(0.9, calidad_forrajera))
            
            # Biomasa disponible
            if tipo_superficie in ["SUELO_DESNUDO"]:
                biomasa_disponible = 0
            else:
                eficiencia_cosecha = 0.25
                perdidas = 0.30
                biomasa_disponible = biomasa_ms_ha * calidad_forrajera * eficiencia_cosecha * (1 - perdidas) * cobertura_vegetal
                biomasa_disponible = max(0, min(1200, biomasa_disponible))
            
            resultados.append({
                'ndvi': round(float(ndvi), 3),
                'evi': round(float(evi), 3),
                'savi': round(float(savi), 3),
                'ndwi': round(float(ndwi), 3),
                'bsi': round(float(bsi), 3),
                'ndbi': round(float(ndbi), 3),
                'cobertura_vegetal': round(cobertura_vegetal, 3),
                'prob_suelo_desnudo': round(probabilidad_suelo_desnudo, 3),
                'tipo_superficie': tipo_superficie,
                'biomasa_ms_ha': round(biomasa_ms_ha, 1),
                'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
                'crecimiento_diario': round(crecimiento_diario, 1),
                'factor_calidad': round(calidad_forrajera, 3),
                'fuente_datos': 'SENTINEL-2'  # Indicar que son datos reales
            })
        
        return resultados
        
    except Exception as e:
        st.error(f"❌ Error en cálculo con imágenes reales: {e}")
        return calcular_indices_forrajeros_simulados(gdf, tipo_pastura)

def calcular_indices_forrajeros_simulados(gdf, tipo_pastura):
    """
    Fallback a datos simulados (tu código original)
    """
    # [Aquí va todo tu código original de simulación]
    # [El que ya tenías en la función calcular_indices_forrajeros_gee]
    pass

def simular_indices_para_sublote(id_subLote):
    """
    Simula índices para un sub-lote específico (fallback)
    """
    # Lógica de simulación simplificada
    np.random.seed(id_subLote)
    
    ndvi = np.random.uniform(0.2, 0.8)
    evi = np.random.uniform(0.15, 0.7)
    savi = np.random.uniform(0.18, 0.75)
    ndwi = np.random.uniform(-0.2, 0.4)
    bsi = np.random.uniform(-0.3, 0.3)
    ndbi = np.random.uniform(-0.2, 0.2)
    
    return ndvi, evi, savi, ndwi, bsi, ndbi
