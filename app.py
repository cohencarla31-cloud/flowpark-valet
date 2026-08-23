import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 10px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 15px 25px; border-radius: 8px; font-size: 18px; border: 2px solid #ddd; cursor: pointer; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DE TELÉFONOS ---
TEL_PARKING_1 = "59895280412" 
TEL_PARKING_2 = "59893343092" 

# --- CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

# --- FUNCIONES MATEMÁTICAS Y DE HORA ---
def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

def obtener_validacion_local(patente, tkt, hora_ingreso_str, q_records):
    try:
        ingreso_dt = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
    except: return None
        
    pat_clean = patente.upper().replace("-", "").replace(" ", "")
    tkt_clean = str(tkt).strip().lstrip("0")
    
    for q in q_records[1:]:
        if len(q) < 4: continue
        q_time_str = str(q[0]).strip()
        q_tkt = str(q[2]).strip().lstrip("0")
        q_pat = str(q[3]).upper().replace("-", "").replace(" ", "")
        q_local = str(q[5]).strip() if len(q) > 5 else "Quinquela"
        
        try: q_dt = datetime.strptime(q_time_str, "%Y-%m-%d %H:%M:%S")
        except: continue
            
        if (q_tkt == tkt_clean or q_pat == pat_clean) and q_dt >= ingreso_dt:
            return q_local
    return None

def calcular_mejor_precio(minutos, es_camioneta, local_validacion, tarifas):
    tipo = "Camioneta" if es_camioneta else "Auto"
    if local_validacion == "Rodrigo Bueno": return 0
    descuento = 150 if local_validacion in ["Quinquela", "Number 18"] else 0
    m_cobro = max(0, minutos - descuento)
    if m_cobro <= 0: return 0
        
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    
    monto_hora = ((m_cobro - 1) // 60 + 1) * hora
    return min(monto_hora, promo if m_cobro > 60 else 99999, dia)

def verificar_estado_empleado(nombre_emp, asistencia_rows):
    for row in reversed(asistencia_rows[1:]):
        if len(row) > 2 and str(row[1]).strip().lower() == str(nombre_emp).strip().lower():
            return str(row[2]).strip().capitalize()
    return "Salida"


# ==========================================
# 1. SISTEMA DE LOGIN Y ROLES
# ==========================================
if "usuario" not in st.session_state:
    st.session_state.usuario = None
    st.session_state.rol = None

# Base de datos de contraseñas
usuarios_pins = {
    "1000": {"nombre": "Rodrigo", "rol": "Admin"},
    "2001": {"nombre": "Jony", "rol": "Valet"},
    "2002": {"nombre": "Matias", "rol": "Valet"},
    "2003": {"nombre": "Juan", "rol": "Valet"},
    "2004": {"nombre": "Raul", "rol": "Valet"},
    "3001": {"nombre": "Quinquela", "rol": "Local_Quinquela"},
    "3002": {"nombre": "Number 18", "rol": "Local_Number18"}
}

# Pantalla de bloqueo
if st.session_state.usuario is None:
    st.title("🔐 Acceso al Sistema - Flow Park")
    pin_ingresado = st.text_input("Ingrese su PIN de acceso:", type="password")
    
    if st.button("Ingresar"):
        if pin_ingresado in usuarios_pins:
            st.session_state.usuario = usuarios_pins[pin_ingresado]["nombre"]
            st.session_state.rol = usuarios_pins[pin_ingresado]["rol"]
            st.rerun() 
        else:
            st.error("❌ PIN incorrecto o no autorizado.")
    st.stop() 


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
if st.session_state.rol in ["Admin", "Valet"]:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🍔 Extras", "📤 Salida", "⏰ Personal"])

if st.session_state.rol.startswith("Local_") or st.session_state.rol == "Admin":
    opciones_menu.append("✅ Validaciones")

menu = st.sidebar.radio("Módulo Principal", opciones_menu)


# ==========================================
# 3. DESCARGA DE DATOS DESDE GOOGLE SHEETS
# ==========================================
@st.cache_data(ttl=15)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    try: asistencia = sh.worksheet("Asistencia").get_all_values()
    except: asistencia = []
    
    # NUEVO: Descarga de la base de mensualistas
    try: mensualistas = sh.worksheet("Base_Mensualistas").get_all_values()
    except: mensualistas = []
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    
    return empleados, tarifas, extras, registro, q_data, cli, asistencia, mensualistas

# Cargamos las variables, agregando mensualistas_data al final
empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data = obtener_datos()

# Variable de empleado
emp = st.session_state.usuario


# ==========================================
# 4. MÓDULOS DE LA APP
# ==========================================

# ------------------------------------------
# INGRESO (HÍBRIDO: LPR + MANUAL)
# ------------------------------------------
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")

    # --- SECCIÓN 1: INGRESOS POR CÁMARA (LPR) ---
    st.markdown("### 📷 Ingresos Automáticos (Cámara)")
    
    # Buscamos en el Excel los autos que entraron por cámara (dicen "LPR-") y aún no salieron
    ingresos_lpr = [r for r in reg[1:] if len(r) > 3 and str(r[0]).startswith("LPR-") and (not r[3] or str(r[3]).lower() == "nan")]
    
    if ingresos_lpr:
        st.info(f"🔔 Tienes {len(ingresos_lpr)} vehículo(s) detectado(s) por la cámara esperando validación de tarjeta.")
        
        opciones_lpr = [""] + [f"Patente: {r[1]} - Hora: {r[2]}" for r in ingresos_lpr]
        sel_lpr = st.selectbox("Seleccionar vehículo de la cámara:", opciones_lpr)
        
        if sel_lpr:
            pat_lpr = sel_lpr.split(" - ")[0].replace("Patente: ", "").strip()
            
            # El chofer/valet completa los datos físicos
            tkt_pvc_lpr = st.text_input("Asignar N° Tarjeta PVC al vehículo:")
            tipo_vehi_lpr = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"], key="tipo_lpr")
            
            if st.button("✅ Validar Ingreso de Cámara"):
                if tkt_pvc_lpr:
                    # Buscamos la fila en Google Sheets y la actualizamos
                    for i, row in enumerate(reg, start=1):
                        if row[1] == pat_lpr and str(row[0]).startswith("LPR-") and (not row[3] or str(row[3]).lower() == "nan"):
                            estado_txt = f"Estándar ({tipo_vehi_lpr}) - Op: {emp}"
                            # Reemplazamos el "LPR-MATRICULA" temporal por el ticket real de PVC
                            sh.worksheet("Registro").update_cell(i, 1, str(tkt_pvc_lpr).strip())
                            # Actualizamos el estado con el empleado y tipo de vehículo
                            sh.worksheet("Registro").update_cell(i, 5, estado_txt)
                            
                            st.success(f"✅ ¡Vehículo {pat_lpr} validado con éxito al Ticket #{tkt_pvc_lpr}!")
                            break
                else:
                    st.warning("⚠️ Debes ingresar el N° de Tarjeta PVC física para validar este ingreso.")
    else:
        st.success("✅ No hay ingresos de cámara pendientes por validar.")

    st.divider()

    # --- SECCIÓN 2: INGRESO MANUAL (PLAN B) ---
    st.markdown("### ✍️ Carga Manual (Plan B)")
    with st.expander("Abrir Carga Manual (Si falló la cámara)"):
        pat = st.text_input("Matrícula (Ej: SDL567):", key="in_pat").upper().replace("-", "").replace(" ", "")
        
        nombre_sug, cel_sug = "", "598"
        if pat:
            for rc in clientes[1:]:
                if len(rc) > 2 and str(rc[0]).upper().replace("-", "").replace(" ", "") == pat:
                    nombre_sug, cel_sug = rc[1], str(rc[2]).strip()
                    break
        
        tkt = st.text_input("N° Tarjeta PVC:")
        cli = st.text_input("Nombre Cliente:", value=nombre_sug)
        cel = st.text_input("Celular del cliente:", value=cel_sug)
        tipo_vehi = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
        
        if st.button("Registrar Ingreso Manual"):
            if tkt and pat:
                if any((r[0].strip().lstrip("0") == tkt.strip().lstrip("0") or r[1].upper() == pat) and (len(r)>3 and not r[3]) for r in reg[1:]):
                    st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
                else:
                    h_ing = hora_actual_uy()
                    estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                    # Guardado exacto de las 9 columnas: Ticket, Matricula, Hora_Ingreso, Hora_Salida, Estado, Detalle_Extras, Parking_Dinero, Extras_Dinero, Total_Cobrado
                    sh.worksheet("Registro").append_row([str(tkt).strip(), pat, h_ing, "", estado_txt, "", 0, 0, 0])
                    try: sh.worksheet("Clientes_Frecuentes").append_row([pat, cli, cel])
                    except: pass
                    
                    st.success(f"✅ Ingreso manual registrado: {pat} | Tarjeta #{tkt}")
                    msg_ingreso = f"*FLOW PARK - TICKET INGRESO*\n🚗 Vehículo: {pat}\n🎫 Tarjeta: #{tkt}\n🕒 Ingreso: {h_ing}\n¡Gracias {cli} por elegirnos!"
                    st.code(msg_ingreso)
                    st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel}?text={urllib.parse.quote(msg_ingreso)})")
            else:
                st.warning("Completa la tarjeta y la matrícula.")

# ------------------------------------------
# ACTIVOS
# ------------------------------------------
elif menu == "📊 Activos":
    st.subheader("Vehículos en Playa")
    for r in reversed(reg[1:]):
        if len(r) > 3:
            tkt = str(r[0]).strip()
            h_sal = str(r[3]).strip()
            if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
                pat = r[1]
                h_ing = r[2]
                local_val = obtener_validacion_local(pat, tkt, h_ing, q_data)
                tag_q = f" | 🍽️ **VALIDADO: {local_val.upper()}**" if local_val else ""
                st.info(f"🎫 Tarjeta #{tkt} | 🚗 {pat} | 🕒 Ingreso: {h_ing}{tag_q}")

# ------------------------------------------
# VALIDACIONES PRIVADAS
# ------------------------------------------
elif menu == "✅ Validaciones":
    st.subheader("Validación de Clientes de Locales")
    
    if st.session_state.rol == "Local_Quinquela":
        local_seleccionado = "Quinquela"
        st.info("🏪 Validando exclusivamente para: Quinquela")
    elif st.session_state.rol == "Local_Number18":
        local_seleccionado = "Number 18"
        st.info("🏪 Validando exclusivamente para: Number 18")
    else:
        local_seleccionado = st.selectbox("Seleccionar Local que valida:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
        
    activos_disponibles = []
    for r in reg[1:]:
        if len(r)>3:
            tkt = str(r[0]).strip()
            h_sal = str(r[3]).strip()
            if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                pat = r[1]
                h_ing = r[2]
                if not obtener_validacion_local(pat, tkt, h_ing, q_data):
                    activos_disponibles.append(r)
                    
    opciones_mozo = [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos_disponibles]
    seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa:", opciones_mozo)
    
    if local_seleccionado in ["Quinquela", "Number 18"]:
        mozo = st.text_input("Nombre del Mozo / Recepción:")
        factura = st.text_input("Últimos 4 dígitos de la factura:", max_chars=4)
    else:
        mozo = "Recepción RB"
        factura = "N/A"
        
    if st.button("Aplicar Validación y Avisar"):
        if seleccion_mozo:
            if local_seleccionado in ["Quinquela", "Number 18"] and (not mozo or len(factura) < 4):
                st.error("⚠️ Ingrese el nombre del mozo y los 4 dígitos de la factura.")
            else:
                tkt_val = seleccion_mozo.split(" - ")[0].replace("#", "").strip()
                pat_val = next((r[1] for r in activos_disponibles if r[0].strip() == tkt_val), "")
                
                try:
                    fecha_val = hora_actual_uy()
                    sh.worksheet("Respuestas de formulario 1").append_row([fecha_val, mozo, tkt_val, pat_val, factura, local_seleccionado])
                    st.success(f"✅ Se aplicó la validación de {local_seleccionado} al vehículo {pat_val.upper()} (Ticket #{tkt_val}).")
                    
                    msg_aviso = urllib.parse.quote(f"⚠️ *VALIDACIÓN*\n🚗 Vehículo: {pat_val} (Tkt #{tkt_val})\n🏪 Local: {local_seleccionado}\n👤 Validado por: {mozo}")
                    st.markdown("### 📲 Enviar alerta al Parking:")
                    st.markdown(f"[➡️ Teléfono 1]({f'https://wa.me/{TEL_PARKING_1}?text={msg_aviso}'})", unsafe_allow_html=True)
                    st.markdown(f"[➡️ Teléfono 2]({f'https://wa.me/{TEL_PARKING_2}?text={msg_aviso}'})", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.error("Selecciona un vehículo de la lista.")

# ------------------------------------------
# EXTRAS
# ------------------------------------------
elif menu == "🍔 Extras":
    st.subheader("Carga de Consumos y Extras")
    
    temp_activos = {}
    for r in reg[1:]:
        if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA" and not str(r[0]).startswith("LPR-"):
            temp_activos[r[0].strip()] = r
    activos = list(temp_activos.values())
    
    opciones_autos = ["🛒 VENTA DIRECTA (Sin Vehículo)"] + [f"#{r[0]} - Patente: {r[1]}" for r in activos]
    sel_auto = st.selectbox("Seleccionar vehículo o Venta Directa:", opciones_autos)
    
    lista_prods = [""] + list(extras.keys())
    prod = st.selectbox("Producto / Servicio extra:", lista_prods)
    cant = st.number_input("Cantidad:", min_value=1, step=1)
    
    if st.button("Registrar Extra"):
        if not prod:
            st.warning("Seleccione un producto.")
        else:
            fecha_act = hora_actual_uy()
            operador_actual = st.session_state.usuario 
            
            if sel_auto == "🛒 VENTA DIRECTA (Sin Vehículo)":
                sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, operador_actual, "VENTA DIRECTA"])
                st.success(f"✅ Venta directa registrada: {cant}x {prod} por {operador_actual}.")
            else:
                tkt = sel_auto.split(" - ")[0].replace("#", "").strip()
                patente_ext = sel_auto.split("Patente: ")[1].strip()
                
                precio_unitario = extras.get(prod, 0)
                total_dinero_extra = precio_unitario * cant
                
                sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, operador_actual, patente_ext])
                
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        texto_actual = str(row[5]) if len(row)>5 and row[5] else ""
                        nuevo_texto = f"{texto_actual} | {cant}x {prod}".strip(" |")
                        sh.worksheet("Registro").update_cell(i, 6, nuevo_texto)
                        
                        dinero_actual = float(row[7]) if len(row)>7 and row[7] else 0
                        sh.worksheet("Registro").update_cell(i, 8, dinero_actual + total_dinero_extra)
                        break
                st.success(f"✅ Extra cargado al Ticket #{tkt}: {cant}x {prod}")

# ------------------------------------------
# SALIDA (CON MENSUALISTAS)
# ------------------------------------------
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    
    with st.expander("🕒 Ver tickets emitidos en este turno"):
        try:
            try: ws_hist = sh.worksheet("Historial_Tickets")
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
            pass

    temp_activos = {}
    for r in reg[1:]:
        if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA" and not str(r[0]).startswith("LPR-"):
            temp_activos[r[0].strip()] = r
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
            
            es_camioneta = "Camioneta" in datos[4]
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            
            # --- NUEVA LÓGICA: DETECCIÓN DE MENSUALISTAS ---
            es_mensual = False
            nombre_men = ""
            
            for m in mensualistas_data[1:]:
                if len(m) >= 2 and str(m[0]).upper().replace("-", "").replace(" ", "") == patente:
                    if str(m[1]).strip().upper() == "ACTIVO":
                        es_mensual = True
                        nombre_men = str(m[2]).strip() if len(m) > 2 else "Mensualista"
                        break
            
            if es_mensual:
                monto_estacionamiento = 0
                info_desc = f"🌟 Vehículo Mensualista: {nombre_men} (Parking 100% Bonificado)."
            else:
                monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val, tarifas)
                if local_val == "Rodrigo Bueno": 
                    info_desc = "Estacionamiento 100% bonificado por Rodrigo Bueno."
                elif local_val: 
                    info_desc = f"Incluye cortesía por {local_val}."
                else: 
                    info_desc = "Tarifa estándar aplicada."
            
            total_extras = float(datos[7]) if len(datos) > 7 and datos[7] and datos[7] != "" else 0
            detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras consumidos."
            
            total_a_pagar = monto_estacionamiento + total_extras
            operador = st.session_state.usuario 
            
            texto_ticket = f"""*FLOW PARK - TICKET DE EGRESO*
---------------------------------
🚗 Vehículo: {patente} | Tkt: #{tkt}
🕒 Ingreso: {h_ingreso}
🕒 Salida:  {h_salida}
⏱️ Estadía total: {mins//60}h {mins%60}m
---------------------------------
📋 DETALLE:
{detalle_extras_txt}
Estacionamiento: ${monto_estacionamiento}
Total Extras: ${total_extras}
---------------------------------
💰 *TOTAL A PAGAR: ${total_a_pagar}*
ℹ️ {info_desc}
Op: {operador}
"""
            try:
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        sh.worksheet("Registro").update_cell(i, 4, h_salida)
                        sh.worksheet("Registro").update_cell(i, 7, float(monto_estacionamiento))
                        sh.worksheet("Registro").update_cell(i, 9, float(total_a_pagar))
                
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

# ------------------------------------------
# PERSONAL
# ------------------------------------------
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Asistencia")
    
    ultimo_estado = verificar_estado_empleado(emp, asistencia_data)
    st.info(f"👤 Empleado: **{emp}** | Estado actual: **{ultimo_estado}**")
    
    if ultimo_estado == "Entrada":
        accion = "Salida"
        st.warning("⚠️ Ya tienes entrada. Para finalizar el turno, completa el stock final.")
    else:
        accion = "Entrada"
        st.success("✅ Estás fuera de turno. Para ingresar, completa el stock inicial.")
    
    st.markdown("---")
    st.subheader(f"📝 Inventario de {accion}")
    
    conteo_stock = {}
    for prod_nombre in list(extras.keys()):
        conteo_stock[prod_nombre] = st.number_input(f"Stock físico actual [{prod_nombre}]:", min_value=0, value=0, step=1, key=f"stock_{accion}_{prod_nombre}")
        
    nota_stock = st.text_input("Observaciones (Opcional):")
    if st.button(f"Confirmar Stock y Registrar {accion}"):
        try:
            hora_fichada = hora_actual_uy()
            for index, (prod_nombre, cant) in enumerate(conteo_stock.items()):
                obs_a_guardar = nota_stock if index == 0 else ""
                sh.worksheet("Control_Stock").append_row([hora_fichada, f"Inventario_{accion}_{prod_nombre}", int(cant), str(emp), obs_a_guardar])
            
            texto_asistencia = f"Inventario {accion} completado - Obs: {nota_stock}" if nota_stock else f"Inventario {accion} completado"
            sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), accion, texto_asistencia])
            
            st.success(f"✅ ¡Inventario verificado y **{accion}** registrada para {emp}!")
        except Exception as e:
            st.error(f"Error al guardar: {e}")
