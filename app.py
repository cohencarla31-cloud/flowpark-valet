import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import time
st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 10px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 15px 25px; border-radius: 8px; font-size: 18px; border: 2px solid #ddd; cursor: pointer; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    
    /* BLOQUEO DE PULL-TO-REFRESH Y SCROLL MÓVIL */
    html, body, [data-testid="stAppViewContainer"] {
        overscroll-behavior-y: none !important;
        -webkit-overflow-scrolling: touch;
    }
    
    /* Forzar visibilidad de la barra lateral en celulares */
    @media (max-width: 768px) {
        [data-testid="stSidebar"] {
            min-width: 260px !important;
            max-width: 260px !important;
        }
    }
    
    /* Ocultar botón de Full Page / Expandir de Streamlit */
    button[title="View fullscreen"], a[title="View fullscreen"], [data-testid="stDecoration"] {
        display: none !important;
    }
    
    /* Ocultar barra de herramientas y badge flotante inferior */
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    div[data-testid="stToolbar"] {display: none !important;}
    iframe[title="streamlitApp"] {display: none !important;}
    </style>
    
    <script>
    // Script de seguridad para eliminar cualquier enlace o botón de pantalla completa residual
    setTimeout(function() {
        const fullPageButtons = document.querySelectorAll('a[href*="embed=true"], button');
        fullPageButtons.forEach(el => {
            if (el.innerText && el.innerText.includes('Full page')) {
                el.style.display = 'none';
            }
        });
    }, 1000);
    </script>
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
    nombre_buscado = str(nombre_emp).strip().lower()
    for row in reversed(asistencia_rows[1:]):
        if len(row) > 2 and str(row[1]).strip().lower() == nombre_buscado:
            estado = str(row[2]).strip().capitalize()
            if estado in ["Entrada", "Fichaje", "Salida"]:
                return estado
    return "Salida"

@st.cache_data(ttl=300)
def cargar_usuarios_desde_db():
    pins_dict = {}
    try:
        conf = sh.worksheet("Configuracion").get_all_values()
        for r in conf[1:]:
            if len(r) >= 3 and r[0].strip() and r[1].strip():
                nombre = r[0].strip()
                pin = str(r[1]).strip()
                if "." in pin:
                    pin = pin.split(".")[0]
                rol = r[2].strip()
                pins_dict[pin] = {"nombre": nombre, "rol": rol}
    except Exception as e:
        pass
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
if "local_emp" not in st.session_state: st.session_state.local_emp = ""
if "local_estado" not in st.session_state: st.session_state.local_estado = ""
if "hora_fichaje_temporal" not in st.session_state: st.session_state.hora_fichaje_temporal = ""

if st.session_state.usuario is None:
    st.title("🔐 Acceso al Sistema - Parking El Globo")
    st.markdown("Ingrese sus datos de operador (Nombre y Cédula/PIN exactos):")
    
    nombre_ingresado = st.text_input("👤 Nombre y Apellido:")
    pin_ingresado = st.text_input("🔑 Cédula / PIN (Hasta 8 números):", type="password", max_chars=8)
    
    if st.button("Ingresar"):
        pin_clean = str(pin_ingresado).strip()
        if "." in pin_clean:
            pin_clean = pin_clean.split(".")[0]
        nombre_clean = str(nombre_ingresado).strip().lower()
        
        if not nombre_clean or not pin_clean:
            st.error("⚠️ Debe completar obligatoriamente el nombre y la cédula/PIN.")
        else:
            usuario_encontrado = None
            rol_encontrado = None
            
            if pin_clean in usuarios_pins:
                datos_u = usuarios_pins[pin_clean]
                nombre_bd = datos_u["nombre"].lower()
                if nombre_clean == nombre_bd or nombre_clean in nombre_bd or nombre_bd in nombre_clean or (pin_clean == "1000" and "rodrigo" in nombre_clean):
                    usuario_encontrado = datos_u["nombre"]
                    rol_encontrado = datos_u["rol"]
                else:
                    st.error("❌ El número de cédula/PIN no corresponde al nombre de usuario ingresado.")
            else:
                st.error("❌ Cédula o PIN no autorizado en el sistema.")
                
            if usuario_encontrado:
                st.session_state.usuario = usuario_encontrado
                st.session_state.rol = rol_encontrado
                st.session_state.pin_usado = pin_clean
                st.rerun()
    st.stop() 

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
    st.session_state.local_emp = ""
    st.session_state.local_estado = ""
    st.session_state.hora_fichaje_temporal = ""
    st.rerun()
st.sidebar.divider()

@st.cache_data(ttl=300)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], [], [], [], [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    reg = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    try: asistencia = sh.worksheet("Asistencia").get_all_values()
    except: asistencia = []
    try: mensualistas = sh.worksheet("Base_Mensualistas").get_all_values()
    except: mensualistas = []
    try: stock = sh.worksheet("Control_Stock").get_all_values()
    except: stock = []
    try: efectivo_data = sh.worksheet("Efectivo_Caja").get_all_values()
    except: efectivo_data = []
    try: auditoria = sh.worksheet("Auditoria_LPR").get_all_values()
    except: auditoria = []
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, reg, q_data, cli, asistencia, mensualistas, stock, efectivo_data, auditoria

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, efectivo_data, auditoria_data = obtener_datos()
emp = st.session_state.usuario
es_admin_rodrigo = "rodrigo" in emp.lower() or st.session_state.rol == "Admin"

ultimo_est_operador = verificar_estado_empleado(emp, asistencia_data)
if st.session_state.local_emp == emp and st.session_state.local_estado != "":
    ultimo_est_operador = st.session_state.local_estado

opciones_menu = []
if not es_admin_rodrigo and st.session_state.rol == "Valet":
    opciones_menu.append("⏰ Personal")

if (ultimo_est_operador in ["Entrada", "Fichaje"] and st.session_state.rol == "Valet") or es_admin_rodrigo:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🍔 Extras", "📤 Salida"])

if st.session_state.rol.startswith("Local_") or es_admin_rodrigo:
    opciones_menu.append("✅ Validaciones")

if es_admin_rodrigo:
    opciones_menu.append("📈 Reportes (Admin)")

menu = st.sidebar.radio("Módulo Principal", opciones_menu)

if st.session_state.rol == "Valet" and ultimo_est_operador == "Salida" and menu != "⏰ Personal":
    st.warning("⚠️ **¡ATENCIÓN! No olvides registrar tu ENTRADA en el módulo Personal para habilitar el sistema operativo.**")

def actualizar_stock_en_extras(producto_nombre, cantidad_vendida):
    try:
        ws_ex = sh.worksheet("Extras")
        rows = ws_ex.get_all_values()
        for idx, r in enumerate(rows[1:], start=2):
            if len(r) > 0 and str(r[0]).strip().lower() == str(producto_nombre).strip().lower():
                vendidos_actuales = float(r[3]) if r[3] and r[3] != "" else 0
                stock_actual = float(r[4]) if r[4] and r[4] != "" else 0
                nuevo_vendidos = vendidos_actuales + float(cantidad_vendida)
                nuevo_stock = stock_actual - float(cantidad_vendida)
                ws_ex.update_cell(idx, 4, nuevo_vendidos)
                ws_ex.update_cell(idx, 5, nuevo_stock)
                break
    except Exception as e:
        print(f"Error actualizando stock en Extras: {e}")

# ------------------------------------------
# INGRESO
# ------------------------------------------
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    k = st.session_state.form_key_count
    
    patentes_camara = [str(r[0]).strip().upper() for r in auditoria_data[1:] if len(r) > 0 and r[0] not in ["", "SIN_PATENTE", "ERROR_TOKEN", "ERROR_FATAL"]]
    patentes_frec = [str(rc[0]).strip().upper().replace("-", "").replace(" ", "") for rc in clientes[1:] if len(rc) > 0 and str(rc[0]).strip()]
    
    patentes_mensualistas = []
    nombres_mensualistas_map = {}
    try:
        for m in mensualistas_data[1:]:
            if len(m) > 0 and str(m[0]).strip():
                pat_m = str(m[0]).strip().upper().replace("-", "").replace(" ", "")
                patentes_mensualistas.append(pat_m)
                nom_m = str(m[1]).strip() if len(m) > 1 and str(m[1]).strip() else "Mensualista/Autorizado"
                nombres_mensualistas_map[pat_m] = nom_m
    except:
        pass

    patentes_unificadas = sorted(list(set(patentes_camara + patentes_frec + patentes_mensualistas)))

    st.markdown("**🔍 Identificar Vehículo (Use solo una línea):**")
    sel_pat_cam = st.selectbox("📷 1. Seleccionar Patente (Cámara, Frecuentes y Mensualistas):", [""] + patentes_unificadas, key=f"cam_{k}")
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
        if not nombre_sug and pat_final in nombres_mensualistas_map:
            nombre_sug = nombres_mensualistas_map[pat_final]

    if "ultima_patente" not in st.session_state:
        st.session_state.ultima_patente = ""
        
    if pat_final != st.session_state.ultima_patente:
        st.session_state.ultima_patente = pat_final
        st.session_state[f"cli_{k}"] = nombre_sug
        st.session_state[f"cel_{k}"] = cel_sug
                
    tkt = st.text_input("🎫 N° Tarjeta PVC (Opcional para Frecuentes/Mensualistas):", key=f"tkt_{k}")
    cli_nom = st.text_input("👤 Nombre y Apellido:", key=f"cli_{k}")
    cel = st.text_input("📱 Celular (Para comprobante):", key=f"cel_{k}")
    tipo_vehi = st.selectbox("🚙 Tipo de Vehículo:", ["Auto", "Camioneta"], key=f"veh_{k}")
    
    if st.button("✅ Registrar Ingreso"):
        cel_clean = str(cel).strip()
        if cel_clean.startswith("0"):
            cel_clean = cel_clean[1:]
            
        tkt_final = str(tkt).strip()
        if not tkt_final:
            tkt_final = f"FREC-{pat_final}"

        if not pat_final:
            st.warning("⚠️ Debes seleccionar o escribir obligatoriamente la Patente.")
        else:
            if any((str(r[0]).strip().lstrip("0") == tkt_final.lstrip("0") or str(r[1]).upper() == pat_final) and (len(r)>3 and (not r[3] or str(r[3]).lower() == "nan")) for r in reg[1:]):
                st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
            else:
                h_ing = hora_actual_uy()
                estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                sh.worksheet("Registro").append_row([tkt_final, pat_final, h_ing, "", estado_txt, "", 0, 0, 0])
                
                try: 
                    if cli_nom and not nombre_sug:
                        sh.worksheet("Clientes_Frecuentes").append_row([pat_final, cli_nom.strip().title(), cel_clean])
                except: pass
                
                msg_ingreso = f"*PARKING EL GLOBO - TICKET INGRESO*\n👤 Cliente: {cli_nom.strip().title() or 'Frecuente'}\n🚗 Vehículo: {pat_final}\n🎫 Tarjeta: #{tkt_final}\n🕒 Ingreso: {h_ing}\n¡Gracias por elegirnos!"
                
                st.session_state.exito_msg = f"✅ Ingreso registrado: {pat_final} | Tarjeta #{tkt_final}"
                st.session_state.exito_wp = f"[📲 Enviar Comprobante por WhatsApp](https://wa.me/{cel_clean}?text={urllib.parse.quote(msg_ingreso)})"
                
                st.session_state.form_key_count += 1
                st.session_state.ultima_patente = "" 
                obtener_datos.clear() 
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
        obtener_datos.clear()
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
                    obtener_datos.clear()
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
                actualizar_stock_en_extras(prod, cant)
                st.success(f"✅ Venta directa registrada: {cant}x {prod} por {emp}.")
                obtener_datos.clear()
            else:
                tkt = sel_auto.split(" - ")[0].replace("#", "").strip()
                patente_ext = sel_auto.split("Patente: ")[1].strip().upper()
                precio_unitario = extras.get(prod, 0)
                total_dinero_extra = precio_unitario * cant
                sh.worksheet("Control_Stock").append_row([fecha_act, prod, cant, emp, patente_ext])
                actualizar_stock_en_extras(prod, cant)
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        texto_actual = str(row[5]) if len(row)>5 and row[5] else ""
                        nuevo_texto = f"{texto_actual} | {cant}x {prod}".strip(" |")
                        sh.worksheet("Registro").update_cell(i, 6, nuevo_texto)
                        dinero_actual = float(row[7]) if len(row)>7 and row[7] else 0
                        sh.worksheet("Registro").update_cell(i, 8, dinero_actual + total_dinero_extra)
                        break
                st.success(f"✅ Extra cargado al Ticket #{tkt}: {cant}x {prod}")
                obtener_datos.clear()

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
            
            # --- BÚSQUEDA INTELIGENTE EN TODA LA FILA ---
            estado_mensual_encontrado = ""
            nombre_men = ""
            for m in mensualistas_data[1:]:
                if len(m) > 0 and str(m[0]).strip().upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                    texto_fila = " ".join([str(val) for val in m]).upper()
                    if "AUTORIZADO" in texto_fila:
                        estado_mensual_encontrado = "AUTORIZADO"
                    elif "DEUDA" in texto_fila or "DEUDOR" in texto_fila:
                        estado_mensual_encontrado = "DEUDOR"
                    else:
                        estado_mensual_encontrado = "AL DIA"
                    nombre_men = str(m[1]).strip() if len(m) > 1 else "Mensualista"
                    break
            
            if estado_mensual_encontrado == "AUTORIZADO":
                monto_estacionamiento = 0
                info_desc = f"✅ Vehículo AUTORIZADO ({nombre_men}). Sin costo de estadía."
                st.success(info_desc)
            elif estado_mensual_encontrado == "AL DIA":
                monto_estacionamiento = 0
                info_desc = f"✅ Mensualista AL DÍA ({nombre_men}). Sin costo de estadía."
                st.success(info_desc)
            elif estado_mensual_encontrado == "DEUDOR":
                monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val, tarifas)
                info_desc = f"🛑 ATENCIÓN: {nombre_men} registra DEUDA. Se aplicó cobro de estadía."
                st.error(info_desc)
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
                obtener_datos.clear() 
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
    
    if st.button("🔄 Actualizar Datos"):
        obtener_datos.clear()
        st.rerun()

    st.info(f"👤 Empleado: **{emp}** | Estado actual: **{ultimo_est_operador}**")
    
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
    
    with tab_entrada:
        if ultimo_est_operador == "Entrada":
            st.info("ℹ️ Ya te encuentras con la **Entrada** registrada y el inventario completado. Debes registrar tu salida al terminar el turno.")
            
        elif ultimo_est_operador == "Fichaje":
            st.success(st.session_state.get('cartel_entrada_msg', "✅ Su hora de entrada inicial ha sido guardada."))
            st.warning("⚠️ Recuerde: su turno no quedará sellado de manera definitiva hasta que complete el Inventario debajo.")
            
            with st.form("form_inventario_entrada"):
                st.markdown("### 📝 Inventario y Arqueo de Entrada")
                efectivo_caja = st.number_input("💵 Efectivo inicial en gaveta:", min_value=0, value=0, step=50)
                
                st.markdown("📝 **Inventario inicial de productos:**")
                conteo_stock = {}
                for prod_nombre in list(extras.keys()):
                    if "lavado" not in prod_nombre.lower():
                        conteo_stock[prod_nombre] = st.number_input(f"Stock físico [{prod_nombre}]:", min_value=0, value=0, step=1)
                    
                nota_stock = st.text_input("Observaciones (Opcional):")
                
                submit_entrada = st.form_submit_button("✅ Confirmar Inventario y Finalizar Entrada")
                
                if submit_entrada:
                    try:
                        hora_fichada_final = st.session_state.get("hora_fichaje_temporal", hora_actual_uy())
                        
                        sh.worksheet("Efectivo_Caja").append_row([hora_fichada_final, str(emp), "Entrada", int(efectivo_caja), f"Obs: {nota_stock}"])
                        
                        filas_stock = []
                        for prod, cant in conteo_stock.items():
                            filas_stock.append([hora_fichada_final, f"Inv_Entrada_{prod}", int(cant), str(emp), ""])
                        if filas_stock:
                            sh.worksheet("Control_Stock").append_rows(filas_stock)
                            
                        sh.worksheet("Asistencia").append_row([hora_fichada_final, str(emp), "Entrada", f"Caja Inicial: ${efectivo_caja}"])
                        
                        st.session_state.local_emp = emp
                        st.session_state.local_estado = "Entrada"
                        st.session_state.cartel_entrada_msg = ""
                        obtener_datos.clear()
                        st.success(f"✅ ¡Su entrada ya quedó registrada correctamente a las {hora_fichada_final} luego de realizar el inventario!")
                    except Exception as e: st.error(f"Error al guardar inventario: {e}")
                
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU ENTRADA!**")
            if st.button("⏰ Registrar Entrada Ahora"):
                try:
                    hora_fichada = hora_actual_uy()
                    sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Fichaje", "Fichado inicial esperando inventario"])
                    st.session_state.hora_fichaje_temporal = hora_fichada
                    st.session_state.local_emp = emp
                    st.session_state.local_estado = "Fichaje"
                    st.session_state.cartel_entrada_msg = f"✅ Su entrada se consignó correctamente a las {hora_fichada}. Pero para que quede registrada de manera definitiva deberá previamente completar el inventario."
                    obtener_datos.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al registrar entrada: {e}")

    with tab_salida:
        if ultimo_est_operador == "Salida":
            st.info("ℹ️ No tienes una entrada activa en este momento para registrar salida.")
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU SALIDA** (Realice el inventario de stock y arqueo final).")
            
            with st.form("form_inventario_salida"):
                st.markdown("### 📤 Registrar Salida e Inventario Final")
                
                efectivo_caja_salida = st.number_input("💵 Efectivo final en gaveta (Arqueo de Cierre):", min_value=0, value=0, step=50)
                
                st.markdown("📝 **Inventario final de productos:**")
                conteo_stock_salida = {}
                for prod_nombre in list(extras.keys()):
                    if "lavado" not in prod_nombre.lower():
                        conteo_stock_salida[prod_nombre] = st.number_input(f"Stock físico final [{prod_nombre}]:", min_value=0, value=0, step=1)
                    
                nota_salida = st.text_input("Observaciones de Cierre (Opcional):")
                
                submit_salida = st.form_submit_button("🚪 Registrar Salida Oficial")
                
                if submit_salida:
                    try:
                        hora_fichada = hora_actual_uy()
                        sh.worksheet("Efectivo_Caja").append_row([hora_fichada, str(emp), "Salida", int(efectivo_caja_salida), f"Obs: {nota_salida}"])
                        
                        filas_stock = []
                        for prod, cant in conteo_stock_salida.items():
                            filas_stock.append([hora_fichada, f"Inv_Salida_{prod}", int(cant), str(emp), ""])
                        if filas_stock:
                            sh.worksheet("Control_Stock").append_rows(filas_stock)
                        
                        sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", f"Caja Cierre: ${efectivo_caja_salida}"])
                        
                        st.session_state.local_emp = emp
                        st.session_state.local_estado = "Salida"
                        st.session_state.cartel_salida_msg = f"🚪 SU SALIDA FUE REGISTRADA CORRECTAMENTE A LA HORA: {hora_fichada.split()[1]} Y FECHA: {hora_fichada.split()[0]}.\n👤 Empleado: {emp}\n💵 Efectivo Declarado en Gaveta: ${efectivo_caja_salida}"
                        obtener_datos.clear() 
                        st.rerun()
                    except Exception as e: st.error(f"Error al registrar salida: {e}")

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
    
    # --- PANEL COMERCIAL: MENSUALISTAS Y MOROSIDAD (CORREGIDO Y ROBUSTO) ---
    st.markdown("### 📊 Control Comercial: Mensualistas y Autorizados")
    try:
        ws_men = sh.worksheet("Base_Mensualistas")
        datos_m = ws_men.get_all_values()
        if len(datos_m) > 1:
            total_comercial = len(datos_m) - 1
            total_autorizados = 0
            total_al_dia = 0
            lista_deudores = []
            
            for fila in datos_m[1:]:
                if not fila or not fila[0].strip():
                    continue
                mat = str(fila[0]).strip().upper()
                texto_fila_completo = " ".join([str(val).strip() for val in fila]).upper()
                
                if "AUTORIZADO" in texto_fila_completo:
                    total_autorizados += 1
                elif "DEUDA" in texto_fila_completo or "DEUDOR" in texto_fila_completo:
                    nombre_encontrado = str(fila[1]).strip() if len(fila) > 1 and str(fila[1]).strip() else "Sin nombre"
                    if "DEUDOR" in nombre_encontrado.upper() or "AL DIA" in nombre_encontrado.upper() or "AUTORIZADO" in nombre_encontrado.upper():
                        nombre_encontrado = str(fila[2]).strip() if len(fila) > 2 else "Sin nombre"
                    lista_deudores.append({"Matrícula": mat, "Nombre / Empresa": nombre_encontrado})
                else:
                    total_al_dia += 1

            total_deudores = len(lista_deudores)
            
            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            c_m1.metric(label="Total Registrados", value=total_comercial)
            c_m2.metric(label="✅ Pagos Al Día", value=total_al_dia)
            c_m3.metric(label="🛑 Morosos / Deuda", value=total_deudores, delta="- Deudores", delta_color="inverse")
            c_m4.metric(label="Autorizados", value=total_autorizados)
            
            if total_deudores > 0:
                st.error(f"⚠️ Hay {total_deudores} mensualista(s) con deuda pendiente:")
                df_deudores = pd.DataFrame(lista_deudores)
                st.dataframe(df_deudores, use_container_width=True, hide_index=True)
            else:
                st.success("¡Excelente estado de cuenta! No se registran deudores marcados en el sistema.")
        else:
            st.info("ℹ️ La pestaña Base_Mensualistas está vacía.")
    except Exception as e:
        st.info(f"ℹ️ Error leyendo la base de mensualistas: {e}")

    st.divider()

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

    st.markdown("### 💵 Auditoría de Caja y Efectivo (Control de Faltantes Entre Turnos)")
    try:
        ws_ef = sh.worksheet("Efectivo_Caja")
        datos_ef = ws_ef.get_all_values()
        if len(datos_ef) > 1:
            df_ef = pd.DataFrame(datos_ef[1:], columns=["Fecha", "Empleado", "Tipo", "Monto", "Observaciones"])
            df_ef['Monto'] = pd.to_numeric(df_ef['Monto'], errors='coerce').fillna(0)
            st.dataframe(df_ef.tail(10), use_container_width=True)
            
            if len(df_ef) >= 2:
                salidas = df_ef[df_ef['Tipo'] == "Salida"]
                entradas = df_ef[df_ef['Tipo'] == "Entrada"]
                if not salidas.empty and not entradas.empty:
                    ult_salida = salidas.iloc[-1]
                    ult_entrada = entradas.iloc[-1]
                    if pd.to_datetime(ult_entrada['Fecha']) > pd.to_datetime(ult_salida['Fecha']):
                        monto_cierre = float(ult_salida['Monto'])
                        monto_apertura = float(ult_entrada['Monto'])
                        dif = monto_apertura - monto_cierre
                        
                        if dif != 0:
                            st.error(f"🚨 **ALERTA DE EFECTIVO ENTRE TURNOS:** El empleado {ult_salida['Empleado']} cerró con **${monto_cierre:,.0f}**, pero {ult_entrada['Empleado']} abrió el turno con **${monto_apertura:,.0f}** (Diferencia: ${dif:+,.0f}).")
                        else:
                            st.success(f"✅ El efectivo declarado al abrir el turno por {ult_entrada['Empleado']} coincide exactamente con el cierre anterior de {ult_salida['Empleado']} (${monto_cierre:,.0f}).")
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
                st.markdown("### 👤 Rendimiento por Valet")
                if not df.empty:
                    df_op = df.groupby('Op')['Total'].sum().reset_index()
                    df_op.columns = ['Valet', 'Recaudación ($)']
                    st.dataframe(df_op.sort_values(by='Recaudación ($)', ascending=False), use_container_width=True)
            
            with col_b:
                st.markdown("### 🏪 Uso de Validaciones")
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
        
