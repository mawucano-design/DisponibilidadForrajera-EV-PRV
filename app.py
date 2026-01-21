# -----------------------
# EXPORTAR DATOS - Versión simplificada y robusta
# -----------------------
st.markdown("---")
st.markdown("### 💾 EXPORTAR DATOS")

# Primero, los botones de descarga directa (que no requieren procesamiento adicional)
st.markdown("#### 📤 Descargas Directas")
col1, col2, col3 = st.columns(3)

# Botón 1: GeoJSON
with col1:
    if st.button("🌐 Exportar GeoJSON", use_container_width=True, key="btn_geojson"):
        try:
            geojson_str = gdf_sub.to_json()
            st.download_button(
                label="📥 Descargar GeoJSON",
                data=geojson_str,
                file_name=f"analisis_avanzado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.geojson",
                mime="application/geo+json",
                key="dl_geojson"
            )
        except Exception as e:
            st.error(f"Error al generar GeoJSON: {e}")

# Botón 2: CSV
with col2:
    if st.button("📊 Exportar CSV", use_container_width=True, key="btn_csv"):
        try:
            csv_data = gdf_sub.drop(columns=['geometry']).copy()
            # Agregar datos climáticos y de suelo al CSV
            if datos_clima:
                for key, value in datos_clima.items():
                    if key != 'datos_crudos':
                        csv_data[f'clima_{key}'] = value
            if datos_suelo:
                for key, value in datos_suelo.items():
                    if key not in ['detalles', 'fuente']:
                        csv_data[f'suelo_{key}'] = value
            
            csv_bytes = csv_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar CSV",
                data=csv_bytes,
                file_name=f"analisis_avanzado_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                key="dl_csv"
            )
        except Exception as e:
            st.error(f"Error al generar CSV: {e}")

# Botón 3: Resumen TXT
with col3:
    if st.button("📄 Exportar Resumen", use_container_width=True, key="btn_txt"):
        try:
            resumen_text = f"""RESUMEN DE ANÁLISIS FORRAJERO
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Tipo de Pastura: {tipo_pastura}
Área Total: {dashboard_metrics['area_total']:.1f} ha
Biomasa Promedio: {dashboard_metrics['biomasa_promedio']:.0f} kg MS/ha
EV Total Soportable: {dashboard_metrics['ev_total']:.1f}
NDVI Promedio: {dashboard_metrics['ndvi_promedio']:.3f}
Días de Permanencia: {dashboard_metrics['dias_promedio']:.1f} días
"""
            st.download_button(
                label="📥 Descargar Resumen",
                data=resumen_text,
                file_name=f"resumen_analisis_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                key="dl_txt"
            )
        except Exception as e:
            st.error(f"Error al generar resumen: {e}")

# Sección para el informe DOCX
st.markdown("---")
st.markdown("#### 📑 Informe DOCX Completo")

if DOCX_AVAILABLE:
    col_gen, col_dl = st.columns(2)
    
    with col_gen:
        if st.button("🔄 Generar Informe DOCX", 
                    use_container_width=True,
                    type="primary",
                    key="btn_generar_docx"):
            
            with st.spinner("Generando informe completo. Esto puede tomar unos segundos..."):
                informe_buffer = generar_informe_completo(
                    gdf_sub, datos_clima, datos_suelo, tipo_pastura,
                    carga_animal, peso_promedio, dashboard_metrics,
                    fecha_imagen, n_divisiones, params
                )
                
                if informe_buffer:
                    st.session_state.informe_generado = informe_buffer
                    st.session_state.informe_disponible = True
                    st.success("✅ Informe generado correctamente. Ya puedes descargarlo.")
                else:
                    st.error("❌ No se pudo generar el informe. Revisa los datos.")
    
    with col_dl:
        if st.session_state.get('informe_disponible', False):
            st.download_button(
                label="📥 Descargar Informe DOCX",
                data=st.session_state.informe_generado,
                file_name=f"informe_completo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="dl_docx"
            )
        else:
            st.info("👈 Primero genera el informe usando el botón de la izquierda")
else:
    st.warning("⚠️ Para generar informes DOCX, instala python-docx: `pip install python-docx`")
