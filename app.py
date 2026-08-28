import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 10px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 15px 25px; border-radius: 8px; font-size: 18px; border: 2px solid #ddd; cursor: pointer; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    </style>
""", unsafe_allow_html=True)

TEL_PARKING_1 = "59895280412" 
TEL_PARKING_2 = "59893343092" 

@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

def obtener_validacion_local(patente, tkt, hora_ingreso_str, q_records):
    try: ingreso_dt = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
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

# Inicialización de la memoria del sistema (Blindada)
if "usuario" not in st.session_state: st.session_state.usuario = None
if "rol" not in st.session_state: st.session_state.rol = None
if "pin_usado" not in st.session_state: st.session_state.pin_usado = ""
if "form_key_count" not in st.session_state: st.session_state.form_key_count = 0
if "exito_msg" not in st.session_state: st.session_state.exito_msg = ""
if "exito_wp" not in st.session_state: st.session_state.exito_wp = ""

usuarios_pins = {
    "1000": {"nombre": "Rodrigo", "rol": "Admin"},
    "2001": {"nombre": "Jony", "rol": "Valet"},
    "2002": {"nombre": "Matias", "rol": "Valet"},
    "2003": {"nombre": "Juan", "rol": "Valet"},
    "2004": {"nombre": "Raul", "rol": "Valet"},
    "3001": {"nombre": "Quinquela", "rol": "Local_Quinquela"},
    "3002": {"nombre": "Number 18", "rol": "Local_Number18"}
}

if st.session_state.usuario is None:
    st.title("🔐 Acceso al Sistema")
    pin_ingresado = st.text_input("Ingrese su PIN de acceso:", type="password")
    if st.button("Ingresar"):
        if pin_ingresado in usuarios_pins:
            st.session_state.usuario = usuarios_pins[pin_ingresado]["nombre"]
            st.session_state.rol = usuarios_pins[pin_ingresado]["rol"]
            st.session_state.pin_usado = pin_ingresado
            st.rerun() 
        else:
            st.error("❌ PIN incorrecto o no autorizado.")
    st.stop() 

st.sidebar.markdown(f"👤 **Usuario:** {st.session_state.usuario}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.usuario = None
    st.session_state.rol = None
    st.session_state.pin_usado = ""
    st.rerun()
st.sidebar.divider()

opciones_menu = []
if st.session_state.rol in ["Admin", "Valet"]:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🍔 Extras", "📤 Salida", "⏰ Personal"])

if st.session_state.rol.startswith("Local_") or st.session_state.rol == "Admin":
    opciones_menu.append("✅ Validaciones")

# --- REGLA ESTRICTA: SOLO PIN "1000" Y USUARIO "Rodrigo" (RODRIGO BUENO) ---
if st.session_state.pin_usado == "1000" and st.session_state.usuario == "Rodrigo":
    opciones_menu.append("📈 Reportes (Admin)")

menu = st.sidebar.radio("Módulo Principal", opciones_menu)

@st.cache_data(ttl=60)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], [], [], [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    try: asistencia = sh.worksheet("Asistencia").get_all_values()
    except: asistencia = []
    try: mensualistas = sh.worksheet("Base_Mensualistas").get_all_values()
    except: mensualistas = []
    try: stock = sh.worksheet("Control_Stock").get_all_values()
    except: stock = []
    try: auditoria = sh.worksheet("Auditoria_LPR").get_all_values()
    except: auditoria = []
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, registro, q_data, cli, asistencia, mensualistas, stock, auditoria

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, auditoria_data = obtener_datos()
emp = st.session_state.usuario

# ------------------------------------------
# INGRESO
# ------------------------------------------
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    k = st.session_state.form_key_count
    
    patentes_recientes = []
    for r in auditoria_data[1:]:
        if len(r) > 0 and r[0] not in ["", "SIN_PATENTE", "ERROR_TOKEN", "ERROR_FATAL"]:
            patentes_recientes.append(str(r[0]).upper())
    patentes_recientes = list(dict.fromkeys(patentes_recientes))[-15:]
    patentes_recientes.reverse() 
    
    lista_frec = []
    for rc in clientes[1:]:
        if len(rc) > 0 and rc[0].strip():
            p_cl = str(rc[0]).upper().replace("-", "").replace(" ", "")
            n_cl = str(rc[1]).strip() if len(rc) > 1 else ""
            mostrar = f"{p_cl} - {n_cl}" if n_cl else p_cl
            lista_frec.append(mostrar)
    lista_frec = sorted(list(set(lista_frec)))

    st.markdown("**🔍 Identificar Vehículo (Use solo una línea):**")
    sel_pat_cam = st.selectbox("📷 1. Desde la Cámara (Más reciente primero):", [""] + patentes_recientes, key=f"cam_{k}")
    sel_pat_frec = st.selectbox("⭐ 2. Buscar Cliente Frecuente (A-Z por Patente):", [""] + lista_frec, key=f"frec_{k}")
    pat_manual = st.text_input("✍️ 3. Escribir Manualmente (Auto Nuevo):", key=f"man_{k}")
    
    if pat_manual.strip():
        pat_final = pat_manual.strip()
    elif sel_pat_frec:
        pat_final = sel_pat_frec.split(" - ")[0].strip()
    elif sel_pat_cam:
        pat_final = sel_pat_cam
    else:
        pat_final = ""
        
    pat_final = pat_final.upper().replace("-", "").replace(" ", "")
    st.divider()

    nombre_sug, cel_sug = "", "598"
    if pat_final:
        for rc in clientes[1:]:
            if len(rc) > 2 and str(rc[0]).upper().replace("-", "").replace(" ", "") == pat_final:
                nombre_sug, cel_sug = str(rc[1]).strip(), str(rc[2]).strip()
                break

    if "ultima_patente" not in st.session_state:
        st.session_state.ultima_patente = ""
        
    if pat_final != st.session_state.ultima_patente:
        st.session_state.ultima_patente = pat_final
        st.session_state[f"cli_{k}"] = nombre_sug
        st.session_state[f"cel_{k}"] = cel_sug
                
    tkt = st.text_input("🎫 N° Tarjeta PVC:", key=f"tkt_{k}")
    cli_nom = st.text_input("👤 Nombre y Apellido:", key=f"cli_{k}")
    cel = st.text_input("📱 Celular (Para comprobante):", key=f"cel_{k}")
    tipo_vehi = st.selectbox("🚙 Tipo de Vehículo:", ["Auto", "Camioneta"], key=f"veh_{k}")
    
    if st.button("✅ Registrar Ingreso"):
        cel_clean = str(cel).strip()
        if cel_clean.startswith("0"):
            cel_clean = cel_clean[1:]
            
        if tkt and pat_final and cli_nom.strip():
            if any((str(r[0]).strip().lstrip("0") == str(tkt).strip().lstrip("0") or str(r[1]).upper() == pat_final) and (len(r)>3 and (not r[3] or str(r[3]).lower() == "nan")) for r in reg[1:]):
                st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
            else:
                h_ing = hora_actual_uy()
                estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                sh.worksheet("Registro").append_row([str(tkt).strip(), pat_final, h_ing, "", estado_txt, "", 0, 0, 0])
                
                try: 
                    if cli_nom and not nombre_sug:
                        sh.worksheet("Clientes_Frecuentes").append_row([pat_final, cli_nom.strip().title(), cel_clean])
                except: pass
                
                msg_ingreso = f"*PARKING EL GLOBO - TICKET INGRESO*\n👤 Cliente: {cli_nom.strip().title()}\n🚗 Vehículo: {pat_final}\n🎫 Tarjeta: #{tkt}\n🕒 Ingreso: {h_ing}\n¡Gracias por elegirnos!"
                
                st.session_state.exito_msg = f"✅ Ingreso registrado: {pat_final} | Tarjeta #{tkt}"
                st.session_state.exito_wp = f"[📲 Enviar Comprobante por WhatsApp](https://wa.me/{cel_clean}?text={urllib.parse.quote(msg_ingreso)})"
                
                st.session_state.form_key_count += 1
                st.session_state.ultima_patente = "" 
                st.rerun()
        else:
            st.warning("⚠️ Completa la tarjeta, la matrícula y el nombre y apellido.")

    if st.session_state.exito_msg != "":
        st.success(st.session_state.exito_msg)
        st.markdown(st.session_state.exito_wp, unsafe_allow_html=True)
        st.session_state.exito_msg = ""
        st.session_state.exito_wp = ""

# ------------------------------------------
# ACTIVOS
# ------------------------------------------
elif menu == "📊 Activos":
    st.subheader("Vehículos en Playa")
    if st.button("🔄 Refrescar Playa"):
        st.rerun()
        
    for r in reversed(reg[1:]):
        if len(r) > 3:
            tkt = str(r[0]).strip()
            h_sal = str(r[3]).strip()
            if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                pat = str(r[1]).upper()
                h_ing = r[2]
                local_val = obtener_validacion_local(pat, tkt, h_ing, q_data)
                tag_q = f" | 🍽️ **VALIDADO: {local_val.upper()}**" if local_val else ""
                st.info(f"🎫 Tarjeta #{tkt} | 🚗 {pat} | 🕒 Ingreso: {h_ing}{tag_q}")

# ------------------------------------------
# VALIDACIONES PRIVADAS
# ------------------------------------------
elif menu == "✅ Validaciones":
    st.subheader("Validación de Locales")
    if st.session_state.rol == "Local_Quinquela":
        local_seleccionado = "Quinquela"
    elif st.session_state.rol == "Local_Number18":
        local_seleccionado = "Number 18"
    else:
        local_seleccionado = st.selectbox("Seleccionar Local que valida:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
        
    activos_disponibles = []
    for r in reg[1:]:
        if len(r)>3:
            tkt = str(r[0]).strip()
            h_sal = str(r[3]).strip()
            if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                pat = str(r[1]).upper()
                h_ing = r[2]
                if not obtener_validacion_local(pat, tkt, h_ing, q_data):
                    activos_disponibles.append(r)
                    
    activos_disponibles = sorted(activos_disponibles, key=lambda r: int(str(r[0]).strip()) if str(r[0]).strip().isdigit() else 999999)
    opciones_mozo = [f"#{r[0]} - Patente: {r[1].upper()}" for r in activos_disponibles]
    seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa (Ordenado por Ticket):", [""] + opciones_mozo)
    
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
                pat_val = next((r[1].upper() for r in activos_disponibles if r[0].strip() == tkt_val), "")
                try:
                    fecha_val = hora_actual_uy()
                    sh.worksheet("Respuestas de formulario 1").append_row([fecha_val, mozo, tkt_val, pat_val, factura, local_seleccionado])
                    st.success(f"✅ Se aplicó la validación de {local_seleccionado} al vehículo {pat_val}.")
                    
                    msg_aviso = urllib.parse.quote(f"⚠️ *NUEVA VALIDACIÓN*\n🚗 Vehículo: {pat_val} (Tkt #{tkt_val})\n🏪 Local: {local_seleccionado}\n👤 Mozo: {mozo}")
                    st.markdown("### 📲 Avisar a los Valets:")
                    st.markdown(f"[➡️ Notificar al Celular 1]({f'https://wa.me/{TEL_PARKING_1}?text={msg_aviso}'})", unsafe_allow_html=True)
                    st.markdown(f"[➡️ Notificar al Celular 2]({f'https://wa.me/{TEL_PARKING_2}?text={msg_aviso}'})", unsafe_allow_html=True)
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
            
    activos = sorted(list(temp_activos.values()), key=lambda r: int(str(r[0]).strip()) if str(r[0]).strip().isdigit() else 999999)
    opciones_autos = ["🛒 VENTA DIRECTA (Sin Vehículo)"] + [f"#{r[0]} - Patente: {str(r[1]).upper()}" for r in activos]
    
    sel_auto = st.selectbox("Seleccionar vehículo (Ordenado por Ticket):", opciones_autos)
    
    lista_prods = [""] + list(extras.keys())
    prod = st.selectbox("Producto / Servicio extra:", lista_prods)
    cant = st.number_input("Cantidad:", min_value=1, step=1)
    
    if st.button("Registrar Extra"):
        if not prod: st.warning("Seleccione un producto.")
        else:
            fecha_act = hora_actual_uy()
            if sel_auto == "🛒 VENTA DIRECTA (Sin Vehículo)":
                sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, emp, "VENTA DIRECTA"])
                st.success(f"✅ Venta directa registrada: {cant}x {prod} por {emp}.")
            else:
                tkt = sel_auto.split(" - ")[0].replace("#", "").strip()
                patente_ext = sel_auto.split("Patente: ")[1].strip().upper()
                precio_unitario = extras.get(prod, 0)
                total_dinero_extra = precio_unitario * cant
                sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, emp, patente_ext])
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
# SALIDA
# ------------------------------------------
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    temp_activos = {}
    for r in reg[1:]:
        if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA" and not str(r[0]).startswith("LPR-"):
            temp_activos[r[0].strip()] = r
            
    activos = sorted(list(temp_activos.values()), key=lambda r: int(str(r[0]).strip()) if str(r[0]).strip().isdigit() else 999999)
    lista_salida_ordenada = [f"#{r[0]} - Patente: {str(r[1]).upper()}" for r in activos]
    
    sel = st.selectbox("Elegir auto a retirar (Ordenado por Ticket):", [""] + lista_salida_ordenada)
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        datos = next(r for r in activos if r[0].strip() == tkt)
        patente = str(datos[1]).upper()
        h_ingreso = datos[2]
        
        nombre_cliente_encontrado = "Cliente"
        cel_encontrado = "598"
        for c in clientes[1:]:
            if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                nombre_cliente_encontrado = str(c[1]).strip()
                cel_encontrado = str(c[2]).strip()
                break
                
        cel_salida = st.text_input("Celular del cliente para WhatsApp:", value=cel_encontrado)
        obs_salida = st.text_input("Observaciones de Salida (Opcional):")
        
        if st.button("Calcular y Generar Salida"):
            h_salida = hora_actual_uy()
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            es_camioneta = "Camioneta" in datos[4]
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            
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
                info_desc = f"🌟 Cuenta Mensualista: {nombre_men} (Parking 100% Bonificado)."
            else:
                monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val, tarifas)
                if local_val == "Rodrigo Bueno": info_desc = "Estacionamiento 100% libre por Rodrigo Bueno."
                elif local_val: info_desc = f"Incluye cortesía de 2.5 hs por {local_val}."
                else: info_desc = "Tarifa estándar aplicada."
            
            total_extras = float(datos[7]) if len(datos) > 7 and datos[7] and datos[7] != "" else 0
            detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras consumidos."
            total_a_pagar = monto_estacionamiento + total_extras
            
            texto_ticket = f"""*PARKING EL GLOBO - TICKET DE EGRESO*
---------------------------------
👤 Cliente: {nombre_cliente_encontrado}
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
Op: {emp}

¡Gracias por elegirnos!"""

            try:
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        sh.worksheet("Registro").update_cell(i, 4, h_salida)
                        sh.worksheet("Registro").update_cell(i, 7, float(monto_estacionamiento))
                        sh.worksheet("Registro").update_cell(i, 9, float(total_a_pagar))
                try: ws_h = sh.worksheet("Historial_Tickets")
                except: ws_h = sh.add_worksheet(title="Historial_Tickets", rows="1000", cols="10")
                ws_h.append_row([
                    h_salida, emp, patente, f"#{tkt}", float(monto_estacionamiento), 
                    float(total_extras), float(total_a_pagar), 
                    obs_salida if obs_salida else "-", 
                    local_val if local_val else "Ninguna"
                ])
            except Exception as e: st.warning(f"Error: {e}")
            st.success("✅ ¡Ticket registrado con éxito!")
            with st.expander("🔍 Ver comprobante", expanded=True): st.code(texto_ticket)
            
            cel_salida_clean = str(cel_salida).strip()
            if cel_salida_clean.startswith("0"):
                cel_salida_clean = cel_salida_clean[1:]
                
            st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_salida_clean}?text={urllib.parse.quote(texto_ticket)})")

# ------------------------------------------
# PERSONAL Y REPORTES
# ------------------------------------------
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Caja")
    ultimo_estado = verificar_estado_empleado(emp, asistencia_data)
    st.info(f"👤 Empleado: **{emp}** | Estado actual: **{ultimo_estado}**")
    accion = "Salida" if ultimo_estado == "Entrada" else "Entrada"
    accion_elegida = st.radio("Acción a registrar:", [accion])
    
    st.subheader(f"💵 Arqueo de Efectivo ({'Inicial' if accion_elegida == 'Entrada' else 'Final'})")
    efectivo_caja = st.number_input(f"Efectivo en gaveta:", min_value=0, value=0, step=50, key=f"efectivo_{accion_elegida}")
    
    st.subheader(f"📝 Inventario de Productos")
    conteo_stock = {}
    for prod_nombre in list(extras.keys()):
        conteo_stock[prod_nombre] = st.number_input(f"Stock físico [{prod_nombre}]:", min_value=0, value=0, step=1)
        
    nota_stock = st.text_input("Observaciones (Opcional):")
    if st.button(f"Registrar {accion_elegida}"):
        try:
            hora_fichada = hora_actual_uy()
            tipo_mov = "Fondo_Fijo_Entrada" if accion_elegida == "Entrada" else "Cierre_Caja_Salida"
            sh.worksheet("Control_Stock").append_row([hora_fichada, tipo_mov, int(efectivo_caja), str(emp), f"Obs: {nota_stock}"])
            for idx, (prod, cant) in enumerate(conteo_stock.items()):
                sh.worksheet("Control_Stock").append_row([hora_fichada, f"Inv_{accion_elegida}_{prod}", int(cant), str(emp), ""])
            sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), accion_elegida, f"Caja: ${efectivo_caja}"])
            st.success(f"✅ **{accion_elegida}** registrada correctamente para el personal!")
        except Exception as e: st.error(f"Error al guardar: {e}")

elif menu == "📈 Reportes (Admin)":
    st.subheader("📊 Panel de Ventas y Auditoría")
    st.info("🔒 Módulo de acceso exclusivo para Administración.")
    
    st.markdown("### 💵 Auditoría de Caja (Fondo Fijo)")
    movimientos_caja = [r for r in stock_data if len(r) > 2 and r[1] in ["Fondo_Fijo_Entrada", "Cierre_Caja_Salida"]]
    if len(movimientos_caja) >= 2:
        ultimo = movimientos_caja[-1]
        penultimo = movimientos_caja[-2]
        if ultimo[1] == "Fondo_Fijo_Entrada" and penultimo[1] == "Cierre_Caja_Salida":
            plata_mañana, plata_noche = int(ultimo[2]), int(penultimo[2])
            c1, c2 = st.columns(2)
            c1.metric(f"Cierre Noche ({penultimo[3]})", f"${plata_noche}")
            c2.metric(f"Apertura Mañana ({ultimo[3]})", f"${plata_mañana}")
            if plata_mañana != plata_noche:
                st.error(f"🚨 ALERTA: Diferencia de caja de ${plata_mañana - plata_noche}.")
            else:
                st.success("✅ La caja cuadró perfectamente.")
        else: st.info("Esperando próximo cierre y apertura para comparar.")
    else: st.info("No hay suficientes movimientos de caja.")

    st.divider()

    st.markdown("### 📷 Auditoría: Cámaras LPR vs. Valets")
    hoy_str = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")
    
    autos_camara = [str(r[0]).strip().upper() for r in auditoria_data[1:] if len(r) > 1 and hoy_str in r[1]]
    autos_camara = [p for p in autos_camara if p not in ["", "SIN_PATENTE", "ERROR_TOKEN", "ERROR_FATAL"]]
    
    patentes_activas_playa = []
    for r in reg[1:]:
        if len(r) > 3:
            tkt = str(r[0]).strip()
            h_sal = str(r[3]).strip()
            if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                patentes_activas_playa.append(str(r[1]).strip().upper())

    fugas = []
    for patente_camara in autos_camara:
        if patente_camara not in patentes_activas_playa:
            fugas.append(patente_camara)
            
    if len(autos_camara) == 0:
        st.info("ℹ️ La cámara aún no ha registrado ingresos en el día de hoy.")
    elif fugas:
        st.error(f"🚨 ATENCIÓN: La cámara detectó {len(set(fugas))} vehículo(s) que ingresaron pero no tienen ticket activo en playa.")
        st.write("Patentes sin registrar:", ", ".join(set(fugas)))
    else:
        st.success("✅ Perfecto. Todos los vehículos detectados por la cámara tienen su ticket activo correspondiente.")

    st.divider()

    try:
        ws_hist = sh.worksheet("Historial_Tickets")
        datos_hist = ws_hist.get_all_values()
        if len(datos_hist) > 1 and "Total" in datos_hist[0]:
            df = pd.DataFrame(datos_hist[1:], columns=datos_hist[0])
            df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
            df['Parking'] = pd.to_numeric(df['Parking'], errors='coerce').fillna(0)
            df['Extras'] = pd.to_numeric(df['Extras'], errors='coerce').fillna(0)
            df['Hora'] = pd.to_datetime(df['Hora'], errors='coerce')
            
            filtro = st.radio("Filtro de tiempo:", ["Hoy", "Últimos 7 días", "Todo el historial"], horizontal=True)
            hoy_dt = datetime.utcnow() - timedelta(hours=3)
            if filtro == "Hoy": df = df[df['Hora'].dt.date == hoy_dt.date()]
            elif filtro == "Últimos 7 días": df = df[df['Hora'].dt.date >= (hoy_dt - timedelta(days=7)).date()]
                
            st.markdown("### 💰 Resumen")
            c1, c2, c3 = st.columns(3)
            c1.metric("Facturación", f"${df['Total'].sum():,.0f}")
            c2.metric("Parking", f"${df['Parking'].sum():,.0f}")
            c3.metric("Extras", f"${df['Extras'].sum():,.0f}")
            
            st.markdown("---")
            if not df.empty:
                df['Fecha'] = df['Hora'].dt.date
                df_diario = df.groupby('Fecha', as_index=False).agg(Autos=('Total', 'count'), Parking=('Parking', 'sum'), Extras=('Extras', 'sum'), Total_Recaudado=('Total', 'sum'))
                st.dataframe(df_diario.sort_values(by='Fecha', ascending=False), use_container_width=True)
        else: st.warning("⚠️ Esperando la primera salida para generar reportes.")
    except Exception as e: st.error(f"Error conectando con historial: {e}")
