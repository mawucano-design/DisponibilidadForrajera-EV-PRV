import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.plot import show
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import pandas as pd
import os

class ClasificadorPastizales:
    def __init__(self):
        self.colores_clases = {
            1: [0.8, 0.7, 0.6],  # Suelo desnudo - marrón claro
            2: [0.9, 0.8, 0.4],  # Suelo con cubierta rala - amarillo tierra
            3: [0.6, 0.8, 0.4],  # Pastizal natural - verde claro
            4: [0.3, 0.6, 0.2],  # Biomasa forrajera - verde medio
            5: [0.2, 0.4, 0.1]   # Vegetación densa - verde oscuro
        }
        
        self.nombres_clases = {
            1: "Suelo desnudo/rocoso",
            2: "Suelo con cubierta rala", 
            3: "Pastizal natural",
            4: "Biomasa forrajera",
            5: "Vegetación densa"
        }
    
    def cargar_poligono_kml(self, kml_path):
        """Carga el polígono KML del Parque Nacional Los Cardones"""
        gdf = gpd.read_file(kml_path)
        print(f"Polígono cargado: {gdf['NOMBRE'].iloc[0]}")
        print(f"Área: {gdf['Hectares'].iloc[0]:.2f} hectáreas")
        return gdf.geometry.iloc[0]
    
    def cargar_imagen_sentinel(self, imagen_path, poligono):
        """Carga y recorta imagen Sentinel-2 al polígono"""
        with rasterio.open(imagen_path) as src:
            imagen_recortada, transform = mask(src, [poligono], crop=True, all_touched=True)
            perfil = src.profile
            
        # Actualizar perfil con nueva transformación y dimensiones
        perfil.update({
            'height': imagen_recortada.shape[1],
            'width': imagen_recortada.shape[2],
            'transform': transform
        })
        
        print(f"Imagen cargada: {imagen_recortada.shape}")
        return imagen_recortada, transform, perfil
    
    def calcular_indices_espectrales(self, imagen):
        """Calcula índices espectrales para zonas áridas"""
        # Bandas Sentinel-2 (10m)
        blue = imagen[1].astype(float)   # B2
        green = imagen[2].astype(float)  # B3  
        red = imagen[3].astype(float)    # B4
        nir = imagen[7].astype(float)    # B8
        swir1 = imagen[11].astype(float) # B11 (20m resampleado)
        
        # Evitar división por cero
        epsilon = 1e-10
        
        # Índices principales
        ndvi = (nir - red) / (nir + red + epsilon)
        
        # SAVI con factor L ajustado para zonas áridas
        L = 0.3
        savi = ((nir - red) / (nir + red + L)) * (1 + L)
        
        # Índice de Suelo Desnudo (BSI)
        bsi = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue) + epsilon)
        
        # Índice de Estrés Hídrico (MSI)
        msi = swir1 / (nir + epsilon)
        
        # Índice de Vegetación Ajustado para Pastizales (GNDVI)
        gndvi = (nir - green) / (nir + green + epsilon)
        
        # Índice de Biomasa Forrajera Específico
        # Combina información de verdor y contenido de agua
        biomass_index = (ndvi * 0.6) + ((1 - msi) * 0.4)
        
        indices = {
            'ndvi': ndvi,
            'savi': savi,
            'bsi': bsi,
            'msi': msi,
            'gndvi': gndvi,
            'biomass_index': biomass_index,
            'bandas_originales': {
                'blue': blue,
                'green': green, 
                'red': red,
                'nir': nir,
                'swir1': swir1
            }
        }
        
        return indices
    
    def clasificar_umbrales_ajustados(self, indices):
        """Clasificación basada en umbrales ajustados para zonas áridas"""
        ndvi = indices['ndvi']
        savi = indices['savi']
        bsi = indices['bsi']
        msi = indices['msi']
        biomass_index = indices['biomass_index']
        
        # Inicializar matriz de clasificación
        clases = np.zeros(ndvi.shape, dtype=np.uint8)
        
        # Umbrales optimizados para Monte de Sierras y Bolsones
        # 1. Suelo desnudo/rocoso
        mascara_suelo = (ndvi < 0.15) & (bsi > 0.1) & (savi < 0.1)
        clases[mascara_suelo] = 1
        
        # 2. Suelo con cubierta rala (inicio de crecimiento)
        mascara_suelo_ralo = (ndvi >= 0.15) & (ndvi < 0.25) & (bsi > 0.05) & (biomass_index < 0.3)
        clases[mascara_suelo_ralo] = 2
        
        # 3. Pastizal natural
        mascara_pastizal = (ndvi >= 0.25) & (ndvi < 0.4) & (savi >= 0.15) & (biomass_index >= 0.3) & (biomass_index < 0.5)
        clases[mascara_pastizal] = 3
        
        # 4. Biomasa forrajera (cardones, arbustos forrajeros)
        mascara_biomasa = (ndvi >= 0.4) & (ndvi < 0.6) & (savi >= 0.25) & (biomass_index >= 0.5) & (msi < 0.8)
        clases[mascara_biomasa] = 4
        
        # 5. Vegetación densa (poco común en esta zona)
        mascara_densa = (ndvi >= 0.6) & (savi >= 0.35) & (biomass_index >= 0.7)
        clases[mascara_densa] = 5
        
        return clases
    
    def entrenar_modelo_ml(self, indices, mascara_entrenamiento=None):
        """Entrena modelo de Machine Learning para clasificación"""
        # Preparar características
        caracteristicas = np.stack([
            indices['ndvi'],
            indices['savi'], 
            indices['bsi'],
            indices['msi'],
            indices['gndvi'],
            indices['biomass_index'],
            indices['bandas_originales']['red'],
            indices['bandas_originales']['nir'],
            indices['bandas_originales']['swir1']
        ], axis=-1)
        
        # Si no hay máscara de entrenamiento, usar muestras aleatorias
        if mascara_entrenamiento is None:
            # Crear máscara basada en reglas simples para entrenamiento
            filas, cols = indices['ndvi'].shape
            mascara_entrenamiento = np.zeros((filas, cols), dtype=bool)
            
            # Muestrear aleatoriamente
            n_muestras = min(10000, filas * cols // 10)
            coord_muestras = np.random.choice(filas * cols, n_muestras, replace=False)
            mascara_entrenamiento.flat[coord_muestras] = True
        
        # Aplanar características y máscara
        X = caracteristicas.reshape(-1, caracteristicas.shape[-1])
        mascara_flat = mascara_entrenamiento.reshape(-1)
        
        # Filtrar solo píxeles de entrenamiento
        X_entrenamiento = X[mascara_flat]
        
        # Generar etiquetas iniciales basadas en reglas
        y_entrenamiento = self.clasificar_umbrales_ajustados(indices)
        y_entrenamiento = y_entrenamiento.reshape(-1)[mascara_flat]
        
        # Entrenar modelo Random Forest
        modelo = RandomForestClassifier(
            n_estimators=100,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            class_weight='balanced',  # Importante para clases desbalanceadas
            random_state=42,
            n_jobs=-1
        )
        
        modelo.fit(X_entrenamiento, y_entrenamiento)
        
        # Predecir en toda la imagen
        y_pred = modelo.predict(X)
        clasificacion_ml = y_pred.reshape(indices['ndvi'].shape)
        
        return clasificacion_ml, modelo
    
    def calcular_estadisticas(self, clasificacion, transform, poligono):
        """Calcula estadísticas de área por clase"""
        # Tamaño de píxel en metros
        pixel_area_m2 = abs(transform[0] * transform[4])
        pixel_area_hectareas = pixel_area_m2 / 10000
        
        # Contar píxeles por clase
        clases, conteos = np.unique(clasificacion, return_counts=True)
        
        estadisticas = {}
        total_pixeles = clasificacion.size
        
        print("\n" + "="*50)
        print("ESTADÍSTICAS DE CLASIFICACIÓN")
        print("="*50)
        
        for clase, conteo in zip(clases, conteos):
            area_hectareas = conteo * pixel_area_hectareas
            porcentaje = (conteo / total_pixeles) * 100
            
            estadisticas[clase] = {
                'area_hectareas': area_hectareas,
                'porcentaje': porcentaje,
                'pixeles': conteo
            }
            
            print(f"{self.nombres_clases[clase]:<25}: {area_hectareas:>8.1f} ha ({porcentaje:>5.1f}%)")
        
        area_total = sum([stats['area_hectareas'] for stats in estadisticas.values()])
        print(f"{'Área total':<25}: {area_total:>8.1f} ha")
        
        return estadisticas
    
    def visualizar_resultados(self, imagen, indices, clasificacion, estadisticas):
        """Visualiza resultados de la clasificación"""
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        
        # Imagen color natural
        rgb = np.stack([imagen[3], imagen[2], imagen[1]], axis=0)  # Red, Green, Blue
        rgb = np.clip(rgb / 3000, 0, 1)  # Escalar para visualización
        
        axes[0,0].imshow(np.transpose(rgb, (1, 2, 0)))
        axes[0,0].set_title('Imagen Color Natural (RGB)')
        axes[0,0].axis('off')
        
        # NDVI
        im1 = axes[0,1].imshow(indices['ndvi'], cmap='RdYlGn', vmin=-0.2, vmax=0.8)
        axes[0,1].set_title('NDVI')
        axes[0,1].axis('off')
        plt.colorbar(im1, ax=axes[0,1])
        
        # Biomasa Index
        im2 = axes[0,2].imshow(indices['biomass_index'], cmap='YlGn', vmin=0, vmax=1)
        axes[0,2].set_title('Índice de Biomasa Forrajera')
        axes[0,2].axis('off')
        plt.colorbar(im2, ax=axes[0,2])
        
        # BSI (Suelo desnudo)
        im3 = axes[1,0].imshow(indices['bsi'], cmap='YlOrBr', vmin=-0.5, vmax=0.5)
        axes[1,0].set_title('Índice de Suelo Desnudo (BSI)')
        axes[1,0].axis('off')
        plt.colorbar(im3, ax=axes[1,0])
        
        # Clasificación
        clasificacion_rgb = np.zeros((*clasificacion.shape, 3))
        for clase, color in self.colores_clases.items():
            mascara = clasificacion == clase
            for i in range(3):
                clasificacion_rgb[mascara, i] = color[i]
        
        axes[1,1].imshow(clasificacion_rgb)
        axes[1,1].set_title('Clasificación de Cobertura')
        axes[1,1].axis('off')
        
        # Leyenda
        axes[1,2].axis('off')
        leyenda_texto = "LEYENDA:\n\n"
        for clase, nombre in self.nombres_clases.items():
            porcentaje = estadisticas[clase]['porcentaje']
            leyenda_texto += f"█ {nombre} ({porcentaje:.1f}%)\n"
        
        axes[1,2].text(0.1, 0.9, leyenda_texto, transform=axes[1,2].transAxes,
                      fontsize=10, verticalalignment='top', fontfamily='monospace')
        
        plt.tight_layout()
        plt.show()
    
    def guardar_resultados(self, clasificacion, perfil, output_path):
        """Guarda la clasificación como GeoTIFF"""
        perfil_output = perfil.copy()
        perfil_output.update({
            'dtype': rasterio.uint8,
            'count': 1,
            'compress': 'lzw'
        })
        
        with rasterio.open(output_path, 'w', **perfil_output) as dst:
            dst.write(clasificacion.astype(rasterio.uint8), 1)
        
        print(f"Clasificación guardada en: {output_path}")
    
    def procesar_completo(self, kml_path, sentinel_path, output_dir="./resultados"):
        """Procesamiento completo del polígono"""
        
        # Crear directorio de resultados
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Cargar datos
        print("Cargando polígono KML...")
        poligono = self.cargar_poligono_kml(kml_path)
        
        print("Cargando imagen Sentinel-2...")
        imagen, transform, perfil = self.cargar_imagen_sentinel(sentinel_path, poligono)
        
        # 2. Calcular índices
        print("Calculando índices espectrales...")
        indices = self.calcular_indices_espectrales(imagen)
        
        # 3. Clasificación por umbrales
        print("Realizando clasificación por umbrales...")
        clasificacion_umbrales = self.clasificar_umbrales_ajustados(indices)
        
        # 4. Clasificación con Machine Learning
        print("Entrenando modelo de Machine Learning...")
        clasificacion_ml, modelo = self.entrenar_modelo_ml(indices)
        
        # 5. Calcular estadísticas
        print("Calculando estadísticas...")
        estadisticas_umbrales = self.calcular_estadisticas(clasificacion_umbrales, transform, poligono)
        estadisticas_ml = self.calcular_estadisticas(clasificacion_ml, transform, poligono)
        
        # 6. Visualizar
        print("Generando visualizaciones...")
        self.visualizar_resultados(imagen, indices, clasificacion_ml, estadisticas_ml)
        
        # 7. Guardar resultados
        output_path = os.path.join(output_dir, "clasificacion_pastizales.tif")
        self.guardar_resultados(clasificacion_ml, perfil, output_path)
        
        return {
            'clasificacion_umbrales': clasificacion_umbrales,
            'clasificacion_ml': clasificacion_ml,
            'estadisticas_umbrales': estadisticas_umbrales,
            'estadisticas_ml': estadisticas_ml,
            'indices': indices,
            'modelo': modelo
        }

# USO DEL CÓDIGO
if __name__ == "__main__":
    # Inicializar clasificador
    clasificador = ClasificadorPastizales()
    
    # Procesar
    resultados = clasificador.procesar_completo(
        kml_path="Poligono_PNLosCardones.kml",
        sentinel_path="sentinel2_10m.tif"  # Tu imagen Sentinel-2
    )
