# ==========================================
# 1. SISTEMA DE LOGIN Y ROLES
# ==========================================
if "usuario" not in st.session_state:
    st.session_state.usuario = None
    st.session_state.rol = None

# Base de datos de PINs (Tú administras esto, Rodrigo)
# "Valet" = Cajeros | "Local_..." = Restaurantes | "Admin" = Rodrigo
usuarios_pins = {
    "1000": {"nombre": "Rodrigo", "rol": "Admin"},
    "2001": {"nombre": "Jony", "rol": "Valet"},
    "2002": {"nombre": "Matias", "rol": "Valet"},
    "2003": {"nombre": "Juan", "rol": "Valet"},
    "2004": {"nombre": "Raul", "rol": "Valet"},
    "3001": {"nombre": "Quinquela", "rol": "Local_Quinquela"},
    "3002": {"nombre": "Number 18", "rol": "Local_Number18"}
}

# Pantalla de bloqueo si no han iniciado sesión
if st.session_state.usuario is None:
    st.title("🔐 Acceso al Sistema - Flow Park")
    pin_ingresado = st.text_input("Ingrese su PIN de acceso:", type="password")
    
    if st.button("Ingresar"):
        if pin_ingresado in usuarios_pins:
            st.session_state.usuario = usuarios_pins[pin_ingresado]["nombre"]
            st.session_state.rol = usuarios_pins[pin_ingresado]["rol"]
            st.experimental_rerun()
        else:
            st.error("❌ PIN incorrecto o no autorizado.")
    st.stop() # Detiene la ejecución para que no vean nada más sin loguearse

# ==========================================
# 2. BARRA LATERAL Y MENÚ DINÁMICO
# ==========================================
st.sidebar.markdown(f"👤 **Usuario:** {st.session_state.usuario}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.usuario = None
    st.session_state.rol = None
    st.rerun()
st.sidebar.divider()

# Construir menú según el rol
opciones_menu = []

# Los Valets y el Admin ven las opciones de parking
if st.session_state.rol in ["Admin", "Valet"]:
    opciones_menu.extend(["📥 Ingreso", "📤 Salida", "🍔 Extras", "⏰ Personal"])

# Los Locales y el Admin ven Validaciones
if st.session_state.rol.startswith("Local_") or st.session_state.rol == "Admin":
    opciones_menu.append("✅ Validaciones")

menu = st.sidebar.radio("Menú Principal", opciones_menu)

# (Aquí asumimos que ya leíste tus datos de Google Sheets en variables como 'reg', 'clientes', etc.)
# Ejemplo de lectura (asegúrate de tener esto en tu código):
# ws_reg = sh.worksheet("Registro")
# reg = ws_reg.get_all_values()

# ==========================================
# 3. MÓDULO: EXTRAS (Con Venta Directa)
# ==========================================
if menu == "🍔 Extras":
    st.subheader("Carga de Consumos y Extras")
    
    # Filtramos activos
    activos = [r for r in reg[1:] if len(r)>3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA"]
    
    # NUEVO: Opción de venta sin auto
    opciones_autos = ["🛒 VENTA DIRECTA (Sin Vehículo)"] + [f"#{r[0]} - Patente: {r[1]}" for r in activos]
    
    sel_auto = st.selectbox("Seleccionar vehículo o Venta Directa:", opciones_autos)
    
    try:
        extras_data = sh.worksheet("Extras").get_all_values()
        lista_prods = [x[0] for x in extras_data[1:] if x[0]]
    except:
        lista_prods = ["Lavado Premium", "Bebida / Gaseosa", "Agua Cortesia"]
        
    prod = st.selectbox("Producto / Servicio extra:", lista_prods)
    cant = st.number_input("Cantidad:", min_value=1, step=1)
    
    if st.button("Registrar Extra"):
        fecha_act = hora_actual_uy()
        operador_actual = st.session_state.usuario # Toma el nombre automáticamente del Login
        
        if sel_auto == "🛒 VENTA DIRECTA (Sin Vehículo)":
            # Guarda solo en Control de Stock (Venta de mostrador)
            sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, operador_actual, "VENTA DIRECTA"])
            st.success(f"✅ Venta directa registrada: {cant}x {prod} cobrado por {operador_actual}.")
        
        else:
            # Venta asociada a un vehículo (Se suma al ticket final)
            tkt = sel_auto.split(" - ")[0].replace("#", "").strip()
            patente_ext = sel_auto.split("Patente: ")[1].strip()
            
            # Buscar precio en la pestaña Extras
            precio_unitario = 0
            for row in extras_data[1:]:
                if row[0] == prod:
                    precio_unitario = float(row[1]) if len(row)>1 and row[1] else 0
                    break
            total_dinero_extra = precio_unitario * cant
            
            # Guardar en Control de Stock
            sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, operador_actual, patente_ext])
            
            # Actualizar Registro
            for i, row in enumerate(reg, start=1):
                if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                    # Actualizar texto descriptivo en Col F (índice 5)
                    texto_actual = str(row[5]) if len(row)>5 and row[5] else ""
                    nuevo_texto = f"{texto_actual} | {cant}x {prod}".strip(" |")
                    sh.worksheet("Registro").update_cell(i, 6, nuevo_texto)
                    
                    # Sumar dinero en Col H (índice 7)
                    dinero_actual = float(row[7]) if len(row)>7 and row[7] else 0
                    sh.worksheet("Registro").update_cell(i, 8, dinero_actual + total_dinero_extra)
                    break
            st.success(f"✅ Extra cargado al Ticket #{tkt}: {cant}x {prod}")

# ==========================================
# 4. MÓDULO: SALIDA
# ==========================================
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    
    with st.expander("🕒 Ver tickets emitidos en este turno"):
        try:
            try:
                ws_hist = sh.worksheet("Historial_Tickets")
            except:
                ws_hist = sh.add_worksheet(title="Historial_Tickets", rows="1000", cols="10")
                ws_hist.append_row(["Hora", "Op", "Patente", "Ticket", "Parking", "Extras", "Total", "Obs", "Validación"])
            
            registros_hist = ws_hist.get_all_values()
            hoy = datetime.now().strftime("%Y-%m-%d")
            tickets_del_dia = [r for r in registros_hist[1:] if len(r) > 0 and hoy in r[0]]
            
            if tickets_del_dia:
                df_hist = pd.DataFrame(tickets_del_dia, columns=["Hora", "Op", "Patente", "Ticket", "Parking", "Extras", "Total", "Obs", "Validación"])
                st.dataframe(df_hist)
            else:
                st.info("No hay tickets emitidos todavía hoy.")
        except Exception as e:
            st.warning(f"Aviso del visor: {e}")

    temp_activos = {}
    for r in reg[1:]:
        if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA":
            tkt_key = r[0].strip()
            temp_activos[tkt_key] = r
    activos = list(temp_activos.values())

    sel = st.selectbox("Elegir auto a retirar:", [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos])
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        datos = next(r for r in activos if r[0].strip() == tkt)
        patente = datos[1]
        h_ingreso = datos[2]
        
        cel_encontrado = next((str(c[2]).strip() for c in clientes[1:] if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.upper().replace("-", "").replace(" ", "")), "598")
        cel_salida = st.text_input("Celular del cliente para WhatsApp:", value=cel_encontrado)
        obs_salida = st.text_input("Observaciones de Salida (Opcional):")
        
        if st.button("Calcular y Generar Salida"):
            h_salida = hora_actual_uy()
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            
            # Calcula validación
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            es_camioneta = "Camioneta" in datos[4]
            monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val)
            
            total_extras = float(datos[7]) if len(datos) > 7 and datos[7] and datos[7] != "" else 0
            detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras consumidos."
            
            total_a_pagar = monto_estacionamiento + total_extras
            
            if local_val == "Rodrigo Bueno": info_desc = "Estacionamiento 100% bonificado por Rodrigo Bueno."
            elif local_val: info_desc = f"Incluye cortesía por {local_val}."
            else: info_desc = "Tarifa estándar aplicada."
            
            operador = st.session_state.usuario # Toma el operador del login activo
            
            texto_ticket = f"""*FLOW PARK - EGRESO*
🚗 {patente} | Tkt: #{tkt}
🕒 Ing: {h_ingreso}
🕒 Sal: {h_salida}
⏱️ Estadía: {mins//60}h {mins%60}m
📋 DETALLE:
{detalle_extras_txt}
Parking: ${monto_estacionamiento} | Extras: ${total_extras}
💰 *TOTAL: ${total_a_pagar}*
ℹ️ {info_desc}
Op: {operador}
"""
            try:
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        sh.worksheet("Registro").update_cell(i, 4, h_salida)
                        sh.worksheet("Registro").update_cell(i, 7, float(monto_estacionamiento))
                
                try: ws_h = sh.worksheet("Historial_Tickets")
                except: ws_h = sh.add_worksheet(title="Historial_Tickets", rows="1000", cols="10")
                
                ws_h.append_row([
                    h_salida, operador, patente, f"#{tkt}", float(monto_estacionamiento), 
                    float(total_extras), float(total_a_pagar), 
                    obs_salida if obs_salida else "-", 
                    local_val if local_val else "Ninguna"
                ])
                
            except Exception as e:
                st.warning(f"Error de sincronización: {e}")

            st.success("✅ ¡Ticket registrado con éxito!")
            with st.expander("🔍 Ver comprobante", expanded=True): st.code(texto_ticket)
            st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_salida}?text={urllib.parse.quote(texto_ticket)})")

# ==========================================
# 5. MÓDULO: VALIDACIONES PRIVADAS
# ==========================================
elif menu == "✅ Validaciones":
    st.subheader("Validación de Clientes de Locales")
    
    # Restricción de vista según el Rol
    if st.session_state.rol == "Local_Quinquela":
        local_seleccionado = "Quinquela"
        st.info("🏪 Validando exclusivamente para: Quinquela")
    elif st.session_state.rol == "Local_Number18":
        local_seleccionado = "Number 18"
        st.info("🏪 Validando exclusivamente para: Number 18")
    else:
        # Rodrigo (Admin) puede elegir a nombre de quién validar
        local_seleccionado = st.selectbox("Seleccionar Local que valida:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
        
    pat_val = st.text_input("Patente del cliente a validar:")
    tkt_val = st.text_input("Número de Ticket:")
    
    if st.button("Aplicar Validación"):
        # Lógica para registrar la validación en Google Sheets (Respuestas de formulario 1)
        fecha_val = hora_actual_uy()
        sh.worksheet("Respuestas de formulario 1").append_row([fecha_val, pat_val, local_seleccionado, f"#{tkt_val}", "Aprobado por App"])
        st.success(f"✅ Se aplicó la validación de {local_seleccionado} al vehículo {pat_val.upper()} (Ticket #{tkt_val}).")

# ==========================================
# 6. MÓDULOS DE INGRESO Y PERSONAL (Deja tus bloques originales aquí)
# ==========================================
elif menu == "📥 Ingreso":
    st.info("Aquí va tu bloque original de Ingreso.")
    # (Pega aquí tu código de Ingreso)

elif menu == "⏰ Personal":
    st.info("Aquí va tu bloque original de Personal.")
    # (Pega aquí tu código de Personal)
