# AÑADIR AL INICIO DEL ARCHIVO, DESPUÉS DE LOS PARÁMETROS_FORRAJEROS_BASE

# RECOMENDACIONES DE GANADERÍA REGENERATIVA
RECOMENDACIONES_REGENERATIVAS = {
    'ALFALFA': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Sistema de pastoreo rotacional intensivo (PRV) - 1-3 días por potrero",
            "Integración con leguminosas nativas para fijación de nitrógeno",
            "Uso de biofertilizantes a base de microorganismos nativos",
            "Siembra de bancos de proteína con variedades nativas"
        ],
        'MANEJO_SUELO': [
            "Aplicación de compost de 2-3 ton/ha en épocas secas",
            "Uso de harinas de rocas para mineralización",
            "Inoculación con micorrizas para mejor absorción",
            "Coberturas vivas con tréboles y otras leguminosas"
        ],
        'BIODIVERSIDAD': [
            "Corredores biológicos con vegetación nativa",
            "Cercas vivas con especies multipropósito",
            "Rotación con cultivos de cobertura en épocas lluviosas",
            "Manejo integrado de plagas con control biológico"
        ],
        'AGUA_RETENCIÓN': [
            "Swales (zanjas de infiltración) en pendientes suaves",
            "Keyline design para manejo de aguas",
            "Mulching con residuos vegetales locales",
            "Sistemas de riego por goteo con agua de lluvia"
        ]
    },
    'RAYGRASS': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo ultra rápido - 12-24 horas por lote",
            "Descansos prolongados de 45-60 días entre pastoreos",
            "Mezcla con trébol blanco y rojo para fijación N",
            "Uso de gallinas después del pastoreo bovino"
        ],
        'MANEJO_SUELO': [
            "Aplicación de té de compost cada 30 días",
            "Mineralización con fosfatos naturales",
            "Inoculación con bacterias fijadoras",
            "Aporques para mejorar estructura del suelo"
        ],
        'BIODIVERSIDAD': [
            "Asociación con chicoria y plantago",
            "Bordes diversificados con plantas aromáticas",
            "Rotación con avena forrajera en invierno",
            "Manejo de altura de pastoreo (8-10 cm)"
        ],
        'AGUA_RETENCIÓN': [
            "Cosecha de agua de lluvia en microrepresas",
            "Puntos de bebederos móviles",
            "Sombras naturales con árboles nativos",
            "Cobertura permanente del suelo"
        ]
    },
    'FESTUCA': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo racional Voisin - 4-7 días por poteo",
            "Integración avícola después del pastoreo bovino",
            "Uso de árboles forrajeros (Leucaena, Moringa)",
            "Sistemas silvopastoriles intensivos"
        ],
        'MANEJO_SUELO': [
            "Aplicación de bokashi especializado",
            "Enmiendas con carbonatos naturales",
            "Inoculación con trichoderma",
            "Labranza cero con siembra directa"
        ],
        'BIODIVERSIDAD': [
            "Mezclas con pastos nativos adaptados",
            "Cercas vivas con gliricidia y eritrina",
            "Rotación con kikuyo en zonas altas",
            "Control mecánico de malezas selectivas"
        ],
        'AGUA_RETENCIÓN': [
            "Terrazas de absorción en laderas",
            "Sistemas de riego por aspersión eficiente",
            "Barreras vivas contra erosión",
            "Retención de humedad con mulching"
        ]
    },
    'AGROPIRRO': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo de precisión según biomasa disponible",
            "Integración con porcinos en lotes específicos",
            "Uso de abonos verdes entre rotaciones",
            "Sistemas agrosilvopastoriles"
        ],
        'MANEJO_SUELO': [
            "Aplicación de humus de lombriz",
            "Enmiendas con yeso agrícola",
            "Inoculación con azospirillum",
            "Coberturas muertas con paja"
        ],
        'BIODIVERSIDAD': [
            "Asociación con brachiaria en zonas bajas",
            "Plantas repelentes naturales en bordes",
            "Rotación con sorgo forrajero",
            "Manejo diferenciado por microclimas"
        ],
        'AGUA_RETENCIÓN': [
            "Zanjas de drenaje y retención",
            "Sistemas de sub-riego",
            "Cultivo en curvas a nivel",
            "Protección de fuentes hídricas"
        ]
    },
    'PASTIZAL_NATURAL': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Pastoreo holístico planificado",
            "Manejo adaptativo multipaddock",
            "Regeneración de pastos nativos",
            "Uso de herbívoros mixtos (ovinos, caprinos)"
        ],
        'MANEJO_SUELO': [
            "Regeneración con microorganismos eficientes",
            "Mineralización con rocas molidas locales",
            "Inoculación con hongos micorrízicos nativos",
            "Coberturas con especies pioneras"
        ],
        'BIODIVERSIDAD': [
            "Recuperación de bancos de semillas nativas",
            "Corredores de conectividad ecológica",
            "Manejo de carga animal según estacionalidad",
            "Protección de áreas de regeneración natural"
        ],
        'AGUA_RETENCIÓN': [
            "Restauración de quebradas y nacimientos",
            "Sistemas de cosecha de aguas lluvias",
            "Manejo de escorrentías con geomembranas",
            "Recarga de acuíferos con técnicas permaculturales"
        ]
    },
    'PERSONALIZADO': {
        'PRÁCTICAS_REGENERATIVAS': [
            "Diseño de sistema según condiciones específicas del terreno",
            "Monitoreo continuo con ajustes adaptativos",
            "Integración animal según recursos disponibles",
            "Planificación holística del manejo"
        ],
        'MANEJO_SUELO': [
            "Análisis de suelo para enmiendas específicas",
            "Regeneración según diagnóstico particular",
            "Uso de insumos locales disponibles",
            "Técnicas adaptadas a la topografía"
        ],
        'BIODIVERSIDAD': [
            "Selección de especies según microclimas",
            "Diseño de paisaje productivo diversificado",
            "Manejo de sucesión ecológica",
            "Conservación de germoplasma local"
        ],
        'AGUA_RETENCIÓN': [
            "Diseño hidrológico keyline adaptado",
            "Sistemas de captación y almacenamiento",
            "Manejo eficiente según disponibilidad hídrica",
            "Técnicas de retención específicas para el terreno"
        ]
    }
}

# FUNCIÓN PARA GENERAR PDF CON RECOMENDACIONES DE GANADERÍA REGENERATIVA
def generar_informe_pdf(gdf_analizado, tipo_pastura, peso_promedio, carga_animal, area_total, fecha_imagen, fuente_satelital):
    """Genera un informe PDF completo con análisis forrajero y recomendaciones de ganadería regenerativa"""
    
    try:
        # Crear buffer para el PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
        styles = getSampleStyleSheet()
        
        # Crear estilos personalizados
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.darkgreen,
            spaceAfter=30,
            alignment=1  # Centrado
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.darkblue,
            spaceAfter=12,
            spaceBefore=12
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.darkgreen,
            spaceAfter=8,
            spaceBefore=8
        )
        
        normal_style = styles['Normal']
        
        # Contenido del PDF
        story = []
        
        # Título principal
        story.append(Paragraph("INFORME DE ANÁLISIS FORRAJERO CON GANADERÍA REGENERATIVA", title_style))
        story.append(Spacer(1, 20))
        
        # Información general
        story.append(Paragraph("INFORMACIÓN GENERAL DEL ANÁLISIS", heading_style))
        info_data = [
            ["Tipo de Pastura:", tipo_pastura.replace('_', ' ').title()],
            ["Área Total Analizada:", f"{area_total:.2f} ha"],
            ["Peso Promedio Animal:", f"{peso_promedio} kg"],
            ["Carga Animal:", f"{carga_animal} cabezas"],
            ["Fuente Satelital:", fuente_satelital],
            ["Fecha de Imagen:", fecha_imagen.strftime("%d/%m/%Y")],
            ["Fecha de Generación:", datetime.now().strftime("%d/%m/%Y %H:%M")]
        ]
        
        info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightseagreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))
        
        # Estadísticas resumen del análisis
        story.append(Paragraph("ESTADÍSTICAS DEL ANÁLISIS FORRAJERO", heading_style))
        
        # Calcular estadísticas
        biomasa_promedio = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        ndvi_promedio = gdf_analizado['ndvi'].mean()
        cobertura_promedio = gdf_analizado['cobertura_vegetal'].mean()
        ev_total = gdf_analizado['ev_soportable'].sum()
        dias_promedio = gdf_analizado['dias_permanencia'].mean()
        
        # Distribución de tipos de superficie
        distribucion_superficie = gdf_analizado['tipo_superficie'].value_counts()
        superficie_texto = ", ".join([f"{k}: {v} sub-lotes" for k, v in distribucion_superficie.items()])
        
        stats_data = [
            ["Métrica", "Valor", "Interpretación"],
            ["Biomasa Disponible Promedio", f"{biomasa_promedio:.0f} kg MS/ha", "Alta" if biomasa_promedio > 2000 else "Media" if biomasa_promedio > 1000 else "Baja"],
            ["NDVI Promedio", f"{ndvi_promedio:.3f}", "Óptimo" if ndvi_promedio > 0.6 else "Moderado" if ndvi_promedio > 0.4 else "Bajo"],
            ["Cobertura Vegetal Promedio", f"{cobertura_promedio:.1%}", "Buena" if cobertura_promedio > 0.7 else "Regular" if cobertura_promedio > 0.4 else "Baja"],
            ["Equivalentes Vaca Totales", f"{ev_total:.1f} EV", f"Soportan {ev_total:.0f} animales"],
            ["Días Permanencia Promedio", f"{dias_promedio:.1f} días", "Adecuado" if dias_promedio > 3 else "Corto"],
            ["Distribución Superficie", superficie_texto, "Variabilidad del potrero"]
        ]
        
        stats_table = Table(stats_data, colWidths=[2.2*inch, 1.5*inch, 1.8*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 20))
        
        # Mapa estático del análisis
        story.append(PageBreak())
        story.append(Paragraph("MAPAS DE ANÁLISIS", heading_style))
        
        # Generar mapa estático para el PDF
        mapa_buffer = crear_mapa_detallado_vegetacion(gdf_analizado, tipo_pastura)
        if mapa_buffer:
            try:
                mapa_buffer.seek(0)
                img = Image(mapa_buffer, width=6*inch, height=4*inch)
                story.append(img)
                story.append(Spacer(1, 10))
                story.append(Paragraph("Figura 1: Mapa de Tipos de Superficie y Biomasa Disponible", normal_style))
            except Exception as e:
                story.append(Paragraph("Error al generar el mapa para el PDF", normal_style))
        
        story.append(Spacer(1, 20))
        
        # Tabla de resultados por sub-lote (primeras 10 zonas)
        story.append(Paragraph("RESULTADOS POR SUB-LOTE (PRIMERAS 10 ZONAS)", heading_style))
        
        # Preparar datos para tabla
        columnas_tabla = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
                         'biomasa_disponible_kg_ms_ha', 'ev_ha', 'dias_permanencia']
        
        df_tabla = gdf_analizado[columnas_tabla].head(10).copy()
        
        # Redondear valores
        df_tabla['area_ha'] = df_tabla['area_ha'].round(3)
        df_tabla['ndvi'] = df_tabla['ndvi'].round(3)
        df_tabla['biomasa_disponible_kg_ms_ha'] = df_tabla['biomasa_disponible_kg_ms_ha'].round(0)
        df_tabla['ev_ha'] = df_tabla['ev_ha'].round(3)
        df_tabla['dias_permanencia'] = df_tabla['dias_permanencia'].round(1)
        
        # Renombrar columnas para mejor visualización
        df_tabla.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 
                           'Biomasa Disp (kg MS/ha)', 'EV/Ha', 'Días Perm.']
        
        # Convertir a lista para la tabla
        table_data = [df_tabla.columns.tolist()]
        for _, row in df_tabla.iterrows():
            table_data.append(row.tolist())
        
        # Crear tabla
        zona_table = Table(table_data, colWidths=[0.6*inch, 0.6*inch, 1.2*inch, 0.5*inch, 1.0*inch, 0.5*inch, 0.6*inch])
        zona_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        story.append(zona_table)
        
        if len(gdf_analizado) > 10:
            story.append(Spacer(1, 5))
            story.append(Paragraph(f"* Mostrando 10 de {len(gdf_analizado)} sub-lotes totales. Consulte el archivo CSV para todos los datos.", 
                                 ParagraphStyle('Small', parent=normal_style, fontSize=8)))
        
        story.append(Spacer(1, 20))
        
        # RECOMENDACIONES DE GANADERÍA REGENERATIVA
        story.append(PageBreak())
        story.append(Paragraph("RECOMENDACIONES DE GANADERÍA REGENERATIVA", heading_style))
        
        # Determinar enfoque según análisis
        if biomasa_promedio < 1000:
            enfoque = "🚨 **ENFOQUE: REGENERACIÓN URGENTE** - Sistema degradado que requiere intervención inmediata"
        elif biomasa_promedio < 2000:
            enfoque = "✅ **ENFOQUE: MEJORA CONTINUA** - Sistema con potencial de mejora mediante prácticas regenerativas"
        else:
            enfoque = "🌟 **ENFOQUE: OPTIMIZACIÓN REGENERATIVA** - Sistema saludable, enfoque en mantenimiento y resiliencia"
        
        story.append(Paragraph(enfoque, normal_style))
        story.append(Spacer(1, 15))
        
        # Obtener recomendaciones específicas
        recomendaciones = RECOMENDACIONES_REGENERATIVAS.get(tipo_pastura, RECOMENDACIONES_REGENERATIVAS['PERSONALIZADO'])
        
        # Prácticas regenerativas
        story.append(Paragraph("🌱 **PRÁCTICAS REGENERATIVAS PRINCIPALES**", subheading_style))
        for rec in recomendaciones['PRÁCTICAS_REGENERATIVAS']:
            story.append(Paragraph(f"• {rec}", normal_style))
        
        story.append(Spacer(1, 10))
        
        # Manejo de suelo
        story.append(Paragraph("🟫 **MANEJO REGENERATIVO DEL SUELO**", subheading_style))
        for rec in recomendaciones['MANEJO_SUELO']:
            story.append(Paragraph(f"• {rec}", normal_style))
        
        story.append(Spacer(1, 10))
        
        # Biodiversidad
        story.append(Paragraph("🌳 **BIODIVERSIDAD Y CONECTIVIDAD ECOLÓGICA**", subheading_style))
        for rec in recomendaciones['BIODIVERSIDAD']:
            story.append(Paragraph(f"• {rec}", normal_style))
        
        story.append(Spacer(1, 10))
        
        # Agua y retención
        story.append(Paragraph("💧 **MANEJO REGENERATIVO DEL AGUA**", subheading_style))
        for rec in recomendaciones['AGUA_RETENCIÓN']:
            story.append(Paragraph(f"• {rec}", normal_style))
        
        story.append(Spacer(1, 20))
        
        # PLAN DE IMPLEMENTACIÓN REGENERATIVA
        story.append(Paragraph("📅 PLAN DE IMPLEMENTACIÓN REGENERATIVA", heading_style))
        
        planes = [
            ("INMEDIATO (0-30 días)", [
                "Diagnóstico participativo con equipo técnico",
                "Diseño inicial del sistema rotacional",
                "Preparación de insumos orgánicos locales",
                "Identificación de áreas prioritarias de intervención"
            ]),
            ("CORTO PLAZO (1-3 meses)", [
                "Implementación de primera rotación de pastoreo",
                "Establecimiento de coberturas vivas",
                "Aplicación de biofertilizantes",
                "Instalación de infraestructura básica (cercas, aguadas)"
            ]),
            ("MEDIANO PLAZO (3-12 meses)", [
                "Ajuste del sistema según monitoreo",
                "Diversificación con árboles y arbustos",
                "Implementación de cosecha de agua",
                "Capacitación del personal en prácticas regenerativas"
            ]),
            ("LARGO PLAZO (1-3 años)", [
                "Consolidación del sistema regenerativo",
                "Mejora genética del hato adaptada al sistema",
                "Comercialización diferenciada por valor agregado",
                "Réplica del modelo en otras áreas"
            ])
        ]
        
        for periodo, acciones in planes:
            story.append(Paragraph(f"<b>{periodo}:</b>", subheading_style))
            for accion in acciones:
                story.append(Paragraph(f"• {accion}", normal_style))
            story.append(Spacer(1, 5))
        
        story.append(Spacer(1, 20))
        
        # INDICADORES DE ÉXITO REGENERATIVO
        story.append(Paragraph("📊 INDICADORES DE ÉXITO REGENERATIVO", heading_style))
        
        indicadores_data = [
            ["Indicador", "Meta 6 meses", "Meta 12 meses", "Meta 24 meses"],
            ["Cobertura vegetal (%)", "> 60%", "> 75%", "> 85%"],
            ["Materia orgánica suelo", "+ 0.5%", "+ 1.0%", "+ 1.5%"],
            ["Infiltración agua (cm/h)", "+ 50%", "+ 100%", "+ 150%"],
            ["Diversidad especies", "+ 30%", "+ 60%", "+ 100%"],
            ["Costo alimentación/animal", "- 20%", "- 35%", "- 50%"],
            ["Ganancia peso diaria", "+ 15%", "+ 25%", "+ 35%"]
        ]
        
        indicadores_table = Table(indicadores_data, colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        indicadores_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(indicadores_table)
        
        story.append(Spacer(1, 20))
        
        # BENEFICIOS ESPERADOS
        story.append(Paragraph("🎯 BENEFICIOS ESPERADOS DEL SISTEMA REGENERATIVO", heading_style))
        
        beneficios = [
            ("🌿 Ambientales", [
                "Aumento de la biodiversidad local",
                "Mejora de la calidad del suelo y agua",
                "Secuestro de carbono en suelo y biomasa",
                "Reducción de la erosión y desertificación"
            ]),
            ("💰 Económicos", [
                "Reducción de costos en insumos externos",
                "Aumento de la productividad por hectárea",
                "Mejor valor comercial por calidad diferenciada",
                "Reducción de riesgos climáticos y de mercado"
            ]),
            ("👥 Sociales", [
                "Creación de empleo local calificado",
                "Mejora de la calidad de vida rural",
                "Fortalecimiento del conocimiento tradicional",
                "Desarrollo de capacidades locales"
            ])
        ]
        
        for categoria, items in beneficios:
            story.append(Paragraph(f"<b>{categoria}:</b>", subheading_style))
            for item in items:
                story.append(Paragraph(f"• {item}", normal_style))
            story.append(Spacer(1, 5))
        
        # Pie de página
        story.append(PageBreak())
        story.append(Paragraph("INFORMACIÓN ADICIONAL", heading_style))
        story.append(Paragraph("Este informe fue generado automáticamente por el Sistema de Análisis Forrajero con Ganadería Regenerativa.", normal_style))
        story.append(Paragraph("La ganadería regenerativa busca replicar los patrones de la naturaleza para crear sistemas productivos resilientes, diversos y económicamente viables.", normal_style))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Principios de la Ganadería Regenerativa:</b>", normal_style))
        story.append(Paragraph("1. Contexto - Entender el ecosistema local completo", normal_style))
        story.append(Paragraph("2. Planificación Holística - Integrar objetivos económicos, sociales y ambientales", normal_style))
        story.append(Paragraph("3. Pastoreo Planificado - Imitar los patrones de los herbívoros silvestres", normal_style))
        story.append(Paragraph("4. Cobertura del Suelo - Mantener el suelo siempre protegido", normal_style))
        story.append(Paragraph("5. Biodiversidad - Fomentar la diversidad de plantas y animales", normal_style))
        story.append(Paragraph("6. Ciclos de Nutrientes - Cerrar los ciclos de nutrientes localmente", normal_style))
        
        story.append(Spacer(1, 15))
        story.append(Paragraph("Para consultas técnicas o implementación de sistemas regenerativos, contacte con especialistas en ganadería regenerativa certificados.", normal_style))
        
        # Generar PDF
        doc.build(story)
        buffer.seek(0)
        
        return buffer
        
    except Exception as e:
        st.error(f"Error generando PDF: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return None

# AÑADIR ESTA PARTE EN LA SECCIÓN DE EXPORTACIÓN (después del GeoJSON y CSV)

def mostrar_seccion_exportacion_pdf():
    """Muestra la sección de exportación de PDF en la interfaz"""
    
    if st.session_state.gdf_analizado is not None:
        st.markdown("---")
        st.subheader("📄 GENERAR INFORME PDF COMPLETO")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.info("""
            **El informe PDF incluirá:**
            • Resumen ejecutivo del análisis
            • Estadísticas detalladas por sub-lote
            • Mapas de distribución de vegetación
            • Recomendaciones específicas de ganadería regenerativa
            • Plan de implementación por fases
            • Indicadores de éxito y beneficios esperados
            """)
        
        with col2:
            if st.button("🖨️ Generar Informe PDF", type="primary", use_container_width=True):
                with st.spinner("Generando informe PDF con recomendaciones regenerativas..."):
                    pdf_buffer = generar_informe_pdf(
                        st.session_state.gdf_analizado,
                        tipo_pastura,
                        peso_promedio,
                        carga_animal,
                        st.session_state.area_total,
                        fecha_imagen,
                        fuente_satelital
                    )
                    
                    if pdf_buffer:
                        st.download_button(
                            "📥 Descargar Informe PDF Completo",
                            pdf_buffer.getvalue(),
                            f"informe_regenerativo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            "application/pdf",
                            key="descarga_pdf"
                        )
                        st.success("✅ Informe PDF generado exitosamente!")
                    else:
                        st.error("❌ Error al generar el PDF")

# FINALMENTE, LLAMAR A LA FUNCIÓN EN LA INTERFAZ PRINCIPAL
# Buscar en el código donde está la sección de exportación y añadir:

# En la función principal, después de la exportación de GeoJSON y CSV, añadir:
mostrar_seccion_exportacion_pdf()
