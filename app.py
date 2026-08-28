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

def cargar_usuarios_desde_db():
    pins_dict = {}
    try:
        conf = sh.worksheet("Configuracion").get_all_values()
        for r in conf[1:]:
            if len(r) >= 3 and r[0].strip() and r[1].strip():
                nombre = r[0].strip()
                pin = str(r[1]).strip().replace(".0", "")
                rol = r[2].strip()
                pins_dict[pin] = {"nombre": nombre, "rol": rol}
    except Exception as e:
        print(f"Error leyendo configuración: {e}")
    
    if "1000" not in pins_dict:
        pins_dict["1000"] = {"nombre": "Rodrigo Bueno", "rol": "Admin"}
        
    return pins_dict

usuarios_pins = cargar_usuarios_desde_db()

if "usuario" not in st.session_state: st.session_state.usuario = None
if "rol" not in st.session_state: st.session_state.rol = None
if "pin_usado" not in st.session_state: st.session_state.pin_usado = ""
if "form_key_count" not in st.session_state: st.session_state.form_key_count = 0
if "exito_msg" not in st.session_state: st.session_state.exito_msg = ""
if "exito_wp" not in st.session_state: st.session_state.exito_wp = ""
if "cartel_salida_msg" not in st.session_state: st.session_state.cartel_salida_msg = ""
if "cartel_entrada_msg" not in st.session_state: st.session_state.cartel_entrada_msg = ""

if st.session_state.usuario is None:
    st.title("🔐 Acceso al Sistema - Parking El Globo")
    st.markdown("Ingrese sus datos de operador (Nombre y Cédula/PIN exactos):")
    
    nombre_ingresado = st.text_input("👤 Nombre y Apellido:")
    pin_ingresado = st.text_input("🔑 Cédula / PIN (Hasta 8 números):", type="password", max_chars=8)
    
    if st.button("Ingresar"):
        pin_clean = str(pin_ingresado).strip().replace(".0", "")
        nombre_clean = str(nombre_ingresado).strip().lower()
        
        if not nombre_clean or not pin_clean:
            st.error("⚠️ Debe completar obligatoriamente el nombre y la cédula/PIN.")
        else:
            # Validación estricta: El PIN debe coincidir con el usuario registrado en la base
            usuario_encontrado = None
            rol_encontrado = None
            
            # Caso especial Admin Maestro
            if pin_clean == "1000" or "rodrigo" in nombre_clean:
                usuario_encontrado = "Rodrigo Bueno"
                rol_encontrado = "Admin"
            elif pin_clean in usuarios_pins:
                datos_u = usuarios_pins[pin_clean]
                if nombre_clean in datos_u["nombre"].lower():
                    usuario_encontrado = datos_u["nombre"]
                    rol_encontrado = datos_u["rol"]
                else:
                    st.error("❌ El número de cédula/PIN no corresponde al nombre ingresado.")
            else:
                st.error("❌ Cédula o PIN no autorizado en el sistema.")
                
            if usuario_encontrado:
                st.session_state.usuario = usuario_encontrado
                st.session_state.rol = rol_encontrado
                st.session_state.pin_usado = pin_clean
                st.rerun()
    st.stop() 

# Blindaje absoluto para Rodrigo Bueno
if st.session_state.pin_usado == "1000" or "rodrigo" in str(st.session_state.usuario).lower():
    st.session_state.rol = "Admin"

st.sidebar.markdown(f"👤 **Usuario:** {st.session_state.usuario}")
st.sidebar.markdown(f"🛡️ **Rol:** {st.session_state.rol}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.usuario = None
    st.session_state.rol = None
    st.session_state.pin_usado = ""
    st.session_state.cartel_salida_msg = ""
    st.session_state.cartel_entrada_msg = ""
    st.rerun()
st.sidebar.divider()

@st.cache_data(ttl=60)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], [], [], [], [], [], []
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
    try: 
        ws_efectivo = sh.worksheet("Efectivo_Caja")
        efectivo_data = ws_efectivo.get_all_values()
    except: efectivo_data = []
    try: auditoria = sh.worksheet("Auditoria_LPR").get_all_values()
    except: auditoria = []
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, registro, q_data, cli, asistencia, mensualistas, stock, efectivo_data, auditoria

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, efectivo_data, auditoria_data = obtener_datos()
emp = st.session_state.usuario
es_admin_rodrigo = "rodrigo" in emp.lower() or st.session_state.rol == "Admin"

# MENÚ PRINCIPAL: RODRIGO NO TIENE PERSONAL, LOS VALETS SÍ
opciones_menu = []
if not es_admin_rodrigo and st.session_state.rol == "Valet":
    opciones_menu.append("⏰ Personal")

if st.session_state.rol in ["Admin", "Valet"] or es_admin_rodrigo:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🍔 Extras", "📤 Salida"])

if st.session_state.rol.startswith("Local_") or st.session_state.rol == "Admin" or es_admin_rodrigo:
    opciones_menu.append("✅ Validaciones")

if st.session_state.rol == "Admin" or es_admin_rodrigo:
    opciones_menu.append("📈 Reportes (Admin)")

menu = st.sidebar.radio("Módulo Principal", opciones_menu)

# ------------------------------------------
# INGRESO
# ------------------------------------------
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    k = st.session_state.form_key_count
    
    patentes_camara = [str(r[0]).strip().upper() for r in auditoria_data[1:] if len(r) > 0 and r[0] not in ["", "SIN_PATENTE", "ERROR_TOKEN", "ERROR_FATAL"]]
    patentes_frec = [str(rc[0]).strip().upper().replace("-", "").replace(" ", "") for rc in clientes[1:] if len(rc) > 0 and rc[0].strip()]
    patentes_unificadas = sorted(list(set(patentes_camara + patentes_frec)))

    st.markdown("**🔍 Identificar Vehículo (Use solo una línea):**")
    sel_pat_cam = st.selectbox("📷 1. Seleccionar Patente (Cámara y Clientes Frecuentes):", [""] + patentes_unificadas, key=f"cam_{k}")
    pat_manual = st.text_input("✍️ 2. Escribir Manualmente (Auto Nuevo):", key=f"man_{k}")
    
    if pat_manual.strip():
        pat_final = pat_manual.strip()
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
    cli_nom = st.text_input("👤 Nombre y Apellido (Obligatorio):", key=f"cli_{k}")
    cel = st.text_input("📱 Celular (Para comprobante):", key=f"cel_{k}")
    tipo_vehi = st.selectbox("🚙 Tipo de Vehículo:", ["Auto", "Camioneta"], key=f"veh_{k}")
    
    if st.button("✅ Registrar Ingreso"):
        cel_clean = str(cel).strip()
        if cel_clean.startswith("0"):
            cel_clean = cel_clean[1:]
            
        if not tkt or not pat_final or not cli_nom.strip():
            st.warning("⚠️ Debes completar obligatoriamente la Tarjeta PVC, la Patente y el Nombre y Apellido.")
        else:
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
# PERSONAL (CONTROL DE ASISTENCIA Y CAJA EN PESTAÑAS)
# ------------------------------------------
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Caja")
    
    if st.button("🔄 Actualizar Estado de Turno"):
        st.rerun()

    ultimo_estado = verificar_estado_empleado(emp, asistencia_data)
    st.info(f"👤 Empleado: **{emp}** | Estado actual: **{ultimo_estado}**")
    
    with st.expander("📋 Ver mi resumen de entradas y salidas recientes"):
        try:
            mis_asistencias = [r for r in asistencia_data[1:] if len(r) > 2 and str(r[1]).strip().lower() == str(emp).strip().lower()]
            if mis_asistencias:
                df_mis_asis = pd.DataFrame(mis_asistencias[-5:], columns=["Hora", "Empleado", "Acción", "Detalle"][:len(mis_asistencias[0])])
                st.dataframe(df_mis_asis, use_container_width=True)
            else:
                st.info("No hay registros recientes.")
        except:
            st.info("Sin registros.")

    st.divider()

    tab_entrada, tab_salida = st.tabs(["📥 ENTRADA", "📤 SALIDA"])
    
    # ==========================
    # PESTAÑA: ENTRADA
    # ==========================
    with tab_entrada:
        if ultimo_estado == "Entrada":
            st.info("ℹ️ Ya te encuentras con la **Entrada** registrada y activa en este turno.")
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU ENTRADA!**")
            
            if st.button("⏰ Registrar Entrada Ahora"):
                try:
                    hora_fichada = hora_actual_uy()
                    sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Entrada", "Fichado inicial"])
                    st.session_state.cartel_entrada_msg = f"✅ Su entrada se consignó correctamente a las {hora_fichada}, pero para que quede registrada de manera definitiva deberá previamente completar el inventario."
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar entrada: {e}")

            if st.session_state.cartel_entrada_msg != "":
                st.success(st.session_state.cartel_entrada_msg)

            st.markdown("### 📝 Inventario y Arqueo de Entrada")
            efectivo_caja = st.number_input("💵 Efectivo inicial en gaveta:", min_value=0, value=0, step=50, key="efectivo_entrada")
            
            st.markdown("📝 **Inventario inicial de productos:**")
            conteo_stock = {}
            for prod_nombre in list(extras.keys()):
                if "lavado" not in prod_nombre.lower():
                    conteo_stock[prod_nombre] = st.number_input(f"Stock físico [{prod_nombre}]:", min_value=0, value=0, step=1, key=f"inv_ent_{prod_nombre}")
                
            nota_stock = st.text_input("Observaciones (Opcional):", key="obs_entrada")
            
            if st.button("✅ Confirmar Inventario y Finalizar Entrada"):
                try:
                    hora_fichada = hora_actual_uy()
                    try: ws_ef = sh.worksheet("Efectivo_Caja")
                    except: ws_ef = sh.add_worksheet(title="Efectivo_Caja", rows="1000", cols="10")
                    ws_ef.append_row([hora_fichada, str(emp), "Entrada", int(efectivo_caja), f"Obs: {nota_stock}"])
                    
                    for prod, cant in conteo_stock.items():
                        sh.worksheet("Control_Stock").append_row([hora_fichada, f"Inv_Entrada_{prod}", int(cant), str(emp), ""])
                    st.success(f"✅ ¡Su entrada ya quedó registrada correctamente a las {hora_fichada} luego de realizar el inventario!")
                except Exception as e: st.error(f"Error al guardar inventario: {e}")

    # ==========================
    # PESTAÑA: SALIDA
    # ==========================
    with tab_salida:
        if ultimo_estado == "Salida":
            st.info("ℹ️ No tienes una entrada activa para registrar salida.")
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU SALIDA** (Previamente realice el inventario de stock y efectivo).")
            st.markdown("### 📤 Registrar Salida e Inventario Final")
            
            efectivo_caja_salida = st.number_input("💵 Efectivo final en gaveta (Arqueo de Cierre):", min_value=0, value=0, step=50, key="efectivo_salida")
            
            st.markdown("📝 **Inventario final de productos:**")
            conteo_stock_salida = {}
            for prod_nombre in list(extras.keys()):
                if "lavado" not in prod_nombre.lower():
                    conteo_stock_salida[prod_nombre] = st.number_input(f"Stock físico final [{prod_nombre}]:", min_value=0, value=0, step=1, key=f"inv_sal_{prod_nombre}")
                
            nota_salida = st.text_input("Observaciones de Cierre (Opcional):", key="obs_salida")
            
            if st.button("🚪 Registrar Salida Oficial"):
                try:
                    hora_fichada = hora_actual_uy()
                    try: ws_ef = sh.worksheet("Efectivo_Caja")
                    except: ws_ef = sh.add_worksheet(title="Efectivo_Caja", rows="1000", cols="10")
                    ws_ef.append_row([hora_fichada, str(emp), "Salida", int(efectivo_caja_salida), f"Obs: {nota_salida}"])
                    
                    for prod, cant in conteo_stock_salida.items():
                        sh.worksheet("Control_Stock").append_row([hora_fichada, f"Inv_Salida_{prod}", int(cant), str(emp), ""])
                    sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", f"Caja Cierre: ${efectivo_caja_salida} - Obs: {nota_salida}"])
                    
                    st.session_state.cartel_salida_msg = f"🚪 SU SALIDA, LUEGO DE HABER REALIZADO EL INVENTARIO, ES A LA HORA: {hora_fichada.split()[1]} Y FECHA: {hora_fichada.split()[0]}.\n👤 Empleado: {emp}\n💵 Efectivo Declarado en Gaveta: ${efectivo_caja_salida}"
                    st.rerun()
                except Exception as e: st.error(f"Error al registrar salida: {e}")

    # CARTEL DESTACADO DE SALIDA EXITOSA
    if st.session_state.cartel_salida_msg != "":
        st.success(st.session_state.cartel_salida_msg)
        if st.button("🔄 Aceptar y Finalizar"):
            st.session_state.cartel_salida_msg = ""
            st.rerun()

# ------------------------------------------
# REPORTES (ADMIN)
# ------------------------------------------
elif menu == "📈 Reportes (Admin)":
    st.subheader("📊 Panel de Ventas, Control y Auditoría")
    st.markdown("👋 ¡Hola **Rodrigo**! Aquí tenés el resumen completo de la operativa de tu estacionamiento.")
    
    st.markdown("### 🕒 Control de Asistencia y Horarios de Empleados")
    try:
        ws_asis = sh.worksheet("Asistencia")
        datos_asis = ws_asis.get_all_values()
        if len(datos_asis) > 1:
            df_asis = pd.DataFrame(datos_asis[1:], columns=["Hora", "Empleado", "Acción", "Detalle"])
            df_asis['Hora'] = pd.to_datetime(df_asis['Hora'], errors='coerce')
            df_asis = df_asis.sort_values(by='Hora', ascending=False)
            st.dataframe(df_asis.head(15), use_container_width=True)
        else:
            st.info("ℹ️ Aún no hay registros de asistencia.")
    except Exception as e:
        st.error(f"Error cargando asistencia: {e}")

    st.divider()

    st.markdown("### 💵 Auditoría de Caja y Efectivo Declarado (Pestaña Efectivo_Caja)")
    try:
        ws_ef = sh.worksheet("Efectivo_Caja")
        datos_ef = ws_ef.get_all_values()
        if len(datos_ef) > 1:
            df_ef = pd.DataFrame(datos_ef[1:], columns=["Fecha", "Empleado", "Tipo", "Monto", "Observaciones"])
            df_ef['Monto'] = pd.to_numeric(df_ef['Monto'], errors='coerce').fillna(0)
            st.dataframe(df_ef.tail(10), use_container_width=True)
            
            if len(df_ef) >= 2:
                ultimo_reg = df_ef.iloc[-1]
                penultimo_reg = df_ef.iloc[-2]
                if penultimo_reg['Tipo'] == "Salida" and ultimo_reg['Tipo'] == "Entrada":
                    dif = float(ultimo_reg['Monto']) - float(penultimo_reg['Monto'])
                    if dif != 0:
                        st.error(f"🚨 **ALERTA DE EFECTIVO:** Diferencia de caja de ${dif:+,.0f} entre el cierre de {penultimo_reg['Empleado']} (${penultimo_reg['Monto']}) y la apertura de {ultimo_reg['Empleado']} (${ultimo_reg['Monto']}).")
                    else:
                        st.success("✅ El efectivo de caja cuadra perfectamente entre turnos.")
        else:
            st.info("ℹ️ Aún no hay registros en la pestaña Efectivo_Caja.")
    except Exception as e:
        st.info("ℹ️ Asegúrate de tener creada la pestaña 'Efectivo_Caja' en tu Google Sheet.")

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
            
            filtro = st.radio("Filtro de tiempo:", ["Todo el historial", "Últimos 7 días", "Hoy"], horizontal=True)
            hoy_dt = datetime.utcnow() - timedelta(hours=3)
            if filtro == "Hoy": df = df[df['Hora'].dt.date == hoy_dt.date()]
            elif filtro == "Últimos 7 días": df = df[df['Hora'].dt.date >= (hoy_dt - timedelta(days=7)).date()]
                
            st.markdown("### 💰 Resumen Financiero")
            c1, c2, c3 = st.columns(3)
            c1.metric("Facturación Total", f"${df['Total'].sum():,.0f}")
            c2.metric("Por Estacionamiento", f"${df['Parking'].sum():,.0f}")
            c3.metric("Por Extras/Lavados", f"${df['Extras'].sum():,.0f}")
            
            st.markdown("### 🚗 Operativa")
            c4, c5 = st.columns(2)
            c4.metric("Vehículos Egresados", len(df))
            ticket_promedio = df['Total'].mean() if len(df) > 0 else 0
            c5.metric("Ticket Promedio", f"${ticket_promedio:,.0f}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.markdown("#### 👤 Rendimiento por Valet")
                if not df.empty:
                    df_op = df.groupby('Op')['Total'].sum().reset_index()
                    df_op.columns = ['Valet', 'Recaudación ($)']
                    st.dataframe(df_op.sort_values(by='Recaudación ($)', ascending=False), use_container_width=True)
            
            with col_b:
                st.markdown("#### 🏪 Uso de Validaciones")
                if not df.empty:
                    df_loc = df.groupby('Validación').size().reset_index(name='Cantidad de Autos')
                    st.dataframe(df_loc.sort_values(by='Cantidad de Autos', ascending=False), use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 📅 Detalle de Ventas por Día")
            if not df.empty:
                df['Fecha'] = df['Hora'].dt.date
                df_diario = df.groupby('Fecha', as_index=False).agg(
                    Autos=('Total', 'count'),
                    Parking=('Parking', 'sum'),
                    Extras=('Extras', 'sum'),
                    Total_Recaudado=('Total', 'sum')
                )
                df_diario.rename(columns={'Autos': 'Cant. Autos', 'Parking': 'Parking ($)', 'Extras': 'Extras ($)', 'Total_Recaudado': 'Total ($)'}, inplace=True)
                df_diario = df_diario.sort_values(by='Fecha', ascending=False)
                st.dataframe(df_diario, use_container_width=True)
                
        else:
            st.warning("⚠️ El panel de facturación está esperando la primera salida del día para generar gráficos.")
    except Exception as e:
        st.error(f"Error conectando con el historial: {e}")
