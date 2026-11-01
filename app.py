# --- MÓDULO ÚNICO DE CONCILIACIÓN POS (OCA) Y AUDITORÍA DIARIA ---
        st.markdown("---")
        st.markdown("### 💳 Conciliación Bancaria y POS (OCA)")
        st.info("💡 **Auditoría Definitiva:** Cruza toda la facturación histórica de la App contra todos los cupones reales de OCA, día por día.")
        
        if st.button("🔄 Ejecutar Auditoría Completa (App vs OCA)"):
            oca_client_id = st.secrets.get("oca_client_id", "")
            oca_secret = st.secrets.get("oca_secret_key", "")
            
            if not oca_client_id or not oca_secret:
                st.warning("🔑 **Falta la Key de OCA:** Asegurate de haber guardado oca_client_id y oca_secret_key en los Secrets de Streamlit.")
            else:
                st.toast("Descargando historial de OCA...", icon="📡")
                
                try:
                    # 1. CONEXIÓN A OCA (Solo 2 consultas, 100% seguro)
                    url_base = "https://api.ocacomercios.oca.com.uy"
                    url_signin = f"{url_base}/api/signin"
                    url_cupones = f"{url_base}/api/v3/companies/218844290012/transactions"
                    
                    headers_base = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    
                    payload = {"id_key": oca_client_id, "secret_key": oca_secret}
                    res_token = requests.post(url_signin, json=payload, headers=headers_base)
                    json_token = res_token.json()
                    
                    if isinstance(json_token, str):
                        st.error(f"🛑 Error Signin: {json_token}")
                        st.stop()
                        
                    token = json_token.get("data", {}).get("id_token", "")
                    if not token:
                        st.error("🛑 OCA no mandó el Token.")
                        st.stop()
                    
                    headers_auth = headers_base.copy()
                    headers_auth["Authorization"] = f"Bearer {token}"
                    params = {"fechaDesde": "2026-10-01", "fechaHasta": hoy_dt.strftime("%Y-%m-%d")} 
                    
                    res_datos = requests.get(url_cupones, headers=headers_auth, params=params)
                    res_json = res_datos.json()
                    
                    # ---- MODO RAYOS X (DEBUG) ----
                    with st.expander("🛠️ RAYOS X: Ver qué datos exactos está mandando OCA (Hacé clic acá)"):
                        st.json(res_json)
                    # ------------------------------
                    
                    if isinstance(res_json, str):
                        st.error(f"🛑 Error Transacciones: {res_json}")
                        st.stop()
                        
                    data_cupones = res_json.get("data", [])
                    df_oca_diario = pd.DataFrame(columns=['Fecha', 'Cobrado_OCA'])
                    
                    if isinstance(data_cupones, list) and len(data_cupones) > 0:
                        df_oca = pd.DataFrame(data_cupones)
                        # Buscamos columnas comunes, pero si OCA usa otra, la veremos en los Rayos X
                        col_monto = next((c for c in df_oca.columns if c.lower() in ["monto", "importe", "amount", "total", "neto"]), None)
                        col_fecha_oca = next((c for c in df_oca.columns if c.lower() in ["fecha", "date", "fechaoperacion", "fechacupon"]), None)
                        
                        if col_monto and col_fecha_oca:
                            df_oca[col_monto] = pd.to_numeric(df_oca[col_monto], errors='coerce').fillna(0)
                            df_oca['Fecha'] = df_oca[col_fecha_oca].astype(str).str[:10]
                            df_oca_diario = df_oca.groupby('Fecha')[col_monto].sum().reset_index()
                            df_oca_diario.columns = ['Fecha', 'Cobrado_OCA']
                        else:
                            st.warning("La API respondió, pero tiene columnas desconocidas. Por favor pasame captura de los 'Rayos X'.")
                            
                    # 2. PROCESAMIENTO DE LA APP (Día a Día - Usando datos puros)
                    df_facturacion_app = pd.DataFrame()
                    if len(historial_data) > 1:
                        # Convertimos a DataFrame el historial puro, sin importar filtros de arriba
                        headers_h = historial_data[0]
                        max_cols_h = max(len(r) for r in historial_data)
                        padded_h = [r + [""] * (max_cols_h - len(r)) for r in historial_data[1:]]
                        df_h_puro = pd.DataFrame(padded_h, columns=[f"Col_{i}" if i >= len(headers_h) else headers_h[i] for i in range(max_cols_h)])
                        
                        if 'Total' in df_h_puro.columns and 'Hora' in df_h_puro.columns:
                            df_h_puro['Total'] = pd.to_numeric(df_h_puro['Total'], errors='coerce').fillna(0)
                            df_h_puro['Hora_dt'] = pd.to_datetime(df_h_puro['Hora'], errors='coerce')
                            df_h_puro = df_h_puro.dropna(subset=['Hora_dt'])
                            df_h_puro['Fecha'] = df_h_puro['Hora_dt'].dt.strftime('%Y-%m-%d')
                            
                            df_facturacion_app = df_h_puro.groupby('Fecha')['Total'].sum().reset_index()
                            df_facturacion_app.columns = ['Fecha', 'Facturado_App']
                    
                    # Ventas Kiosco Puras
                    if len(stock_data) > 1:
                        padded_stk = [r + [""] * (8 - len(r)) for r in stock_data[1:]]
                        df_s_puro = pd.DataFrame(padded_stk, columns=["Fecha", "Producto", "Cantidad", "Empleado", "Patente", "Precio_U", "Total", "Fecha_Corta"])
                        df_s_puro = df_s_puro[~df_s_puro['Producto'].str.startswith('Inv_')]
                        
                        if not df_s_puro.empty:
                            df_s_puro['Total'] = pd.to_numeric(df_s_puro['Total'], errors='coerce').fillna(0)
                            df_s_puro['Fecha_dt'] = pd.to_datetime(df_s_puro['Fecha'], errors='coerce')
                            df_s_puro = df_s_puro.dropna(subset=['Fecha_dt'])
                            df_s_puro['Fecha'] = df_s_puro['Fecha_dt'].dt.strftime('%Y-%m-%d')
                            df_kiosco_diario = df_s_puro.groupby('Fecha')['Total'].sum().reset_index()
                            df_kiosco_diario.columns = ['Fecha', 'Ventas_Kiosco']
                            
                            if not df_facturacion_app.empty:
                                df_facturacion_app = pd.merge(df_facturacion_app, df_kiosco_diario, on='Fecha', how='outer').fillna(0)
                                df_facturacion_app['Facturado_App'] = df_facturacion_app['Facturado_App'] + df_facturacion_app['Ventas_Kiosco']
                            else:
                                df_facturacion_app = df_kiosco_diario.rename(columns={'Ventas_Kiosco': 'Facturado_App'})

                    # Efectivo de Caja Puro
                    df_efectivo_diario = pd.DataFrame()
                    if len(efectivo_data) > 1:
                        df_ef_puro = pd.DataFrame(efectivo_data[1:], columns=["Fecha", "Empleado", "Tipo", "Monto", "Observaciones"][:len(efectivo_data[0])])
                        if 'Monto' in df_ef_puro.columns:
                            df_ef_puro['Monto'] = pd.to_numeric(df_ef_puro['Monto'], errors='coerce').fillna(0)
                            df_ef_puro['Fecha_dt'] = pd.to_datetime(df_ef_puro['Fecha'], errors='coerce')
                            df_ef_puro = df_ef_puro.dropna(subset=['Fecha_dt'])
                            df_ef_puro['Fecha_Corta'] = df_ef_puro['Fecha_dt'].dt.strftime('%Y-%m-%d')
                            
                            resultados_caja = []
                            for fecha_d, grupo in df_ef_puro.groupby('Fecha_Corta'):
                                caja_apertura = float(grupo[grupo['Tipo'] == "Entrada"].iloc[0]['Monto']) if not grupo[grupo['Tipo'] == "Entrada"].empty else 0
                                caja_cierre = float(grupo[grupo['Tipo'] == "Salida"].iloc[-1]['Monto']) if not grupo[grupo['Tipo'] == "Salida"].empty else 0
                                total_gastos = grupo[grupo['Tipo'] == "Gasto"]['Monto'].sum()
                                
                                efectivo_neto = (caja_cierre - caja_apertura) + total_gastos if caja_cierre > 0 else 0
                                resultados_caja.append({'Fecha': fecha_d, 'Efectivo_Gaveta': efectivo_neto})
                                
                            df_efectivo_diario = pd.DataFrame(resultados_caja)

                    # 3. EL CRUCE MAESTRO
                    if not df_facturacion_app.empty:
                        df_maestro = df_facturacion_app.copy()
                        
                        if not df_efectivo_diario.empty:
                            df_maestro = pd.merge(df_maestro, df_efectivo_diario, on='Fecha', how='outer').fillna(0)
                        else:
                            df_maestro['Efectivo_Gaveta'] = 0
                            
                        if not df_oca_diario.empty:
                            df_maestro = pd.merge(df_maestro, df_oca_diario, on='Fecha', how='outer').fillna(0)
                        else:
                            df_maestro['Cobrado_OCA'] = 0
                            
                        df_maestro['Facturado_App'] = df_maestro['Facturado_App'].fillna(0)
                        
                        # Calculamos esperado (evitando negativos)
                        df_maestro['Esperado_en_POS'] = df_maestro['Facturado_App'] - df_maestro['Efectivo_Gaveta']
                        df_maestro['Esperado_en_POS'] = df_maestro['Esperado_en_POS'].apply(lambda x: max(0, x))
                        
                        df_maestro['Diferencia_Final'] = df_maestro['Cobrado_OCA'] - df_maestro['Esperado_en_POS']
                        
                        def estado_auditoria(dif):
                            if dif == 0: return "✅ Cuadra Perfecto"
                            elif dif > 0: return f"🔵 Posnet Sobra (+${dif:,.0f})"
                            else: return f"🔴 Posnet Faltan (${dif:,.0f})"
                            
                        df_maestro['Estado'] = df_maestro['Diferencia_Final'].apply(estado_auditoria)
                        
                        df_mostrar = df_maestro[['Fecha', 'Facturado_App', 'Efectivo_Gaveta', 'Esperado_en_POS', 'Cobrado_OCA', 'Estado']].copy()
                        df_mostrar.columns = ['Día', 'Facturado App', 'Efectivo Caja Neto', 'Debería estar en POS', 'Real Cobrado OCA', 'Estado de Auditoría']
                        
                        for col in ['Facturado App', 'Efectivo Caja Neto', 'Debería estar en POS', 'Real Cobrado OCA']:
                            df_mostrar[col] = df_mostrar[col].apply(lambda x: f"${x:,.0f}")
                            
                        df_mostrar = df_mostrar.sort_values('Día', ascending=False)
                        
                        st.markdown("#### 📅 Auditoría de Cierre X/Z (Día a Día)")
                        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
                        
                    else:
                        st.warning("No hay facturación registrada en la App para auditar todavía.")
                    
                except Exception as e:
                    st.error(f"Error interno procesando la auditoría: {e}")
