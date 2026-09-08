import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import time
import math

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 8px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 10px 15px; border-radius: 8px; font-size: 16px; border: 2px solid #ddd; cursor: pointer; margin: 2px; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    
    div.stButton > button[kind="primary"], div.stButton > button { font-weight: bold; }

    html, body, [data-testid="stAppViewContainer"] {
        overscroll-behavior-y: none !important;
        -webkit-overflow-scrolling: touch;
    }
    
    [data-testid="stMainBlockContainer"] { padding-bottom: 120px !important; }
    
    [data-testid="stSidebar"], [data-testid="collapsedControl"], footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] {
        display: none !important; visibility: hidden !important;
    }
    </style>
    
    <script>
    const borrarFullscreen = () => {
        const elementos = document.querySelectorAll('a, button, div, span');
        elementos.forEach(el => {
            if (el.innerText && (el.innerText.includes('Fullscreen') || el.innerText.includes('Built with Streamlit'))) {
                let contenedor = el.closest('div[style*="position"]') || el.parentElement;
                if (contenedor) { contenedor.style.display = 'none'; }
                el.style.display = 'none';
            }
        });
    };
    setInterval(borrarFullscreen, 300);

    setTimeout(() => {
        const inputsPass = document.querySelectorAll('input[type="password"]');
        inputsPass.forEach(inp => { inp.setAttribute('autocomplete', 'new-password'); });
    }, 1000);

    setInterval(() => {
        fetch(window.location.href, { method: 'HEAD' }).catch(() => {});
    }, 20000);
    </script>
""", unsafe_allow_html=True)

TEL_PARKING_1 = "59895280412" 
TEL_PARKING_2 = "59893343092" 

@st.cache_resource
def init_connection():
    for intento in range(3):
        try:
            creds_dict = st.secrets["gcp_service_account"]
            client = gspread.service_account_from_dict(creds_dict)
            return client.open("FlowPark_Valet_DB")
        except Exception as e:
            if intento == 2:
                st.error("⚠️ Error crítico de conexión. Por favor, recargue la página.")
                st.stop()
            time.sleep(1)

sh = init_connection()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

def obtener_validacion_local(patente, tkt, hora_ingreso_str, q_records):
    try: ingreso_dt = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
    except: return None
    pat_clean = patente.upper().replace("-", "").replace(" ", "")
    tkt_clean = str(tkt).replace("#", "").strip().lstrip("0")
    for q in q_records[1:]:
        if len(q) < 4: continue
        q_time_str = str(q[0]).strip()
        q_tkt = str(q[2]).replace("#", "").strip().lstrip("0")
        q_pat = str(q[3]).upper().replace("-", "").replace(" ", "")
        q_local = str(q[5]).strip() if len(q) > 5 else "Quinquela"
        try: q_dt = datetime.strptime(q_time_str, "%Y-%m-%d %H:%M:%S")
        except: continue
        if (q_tkt == tkt_clean or q_pat == pat_clean) and q_dt >= ingreso_dt:
            return q_local
    return None

def calcular_mejor_precio(minutos, tipo_vehi, local_validacion, tarifas, tipo_lavado="Ninguno"):
    if local_validacion in ["Rodrigo Bueno", "Number 18"]: m_cobro = 0
    else:
        descuento = 150 if local_validacion == "Quinquela" else 0
        m_cobro = max(0, minutos - descuento)

    if m_cobro <= 0 and tipo_lavado == "Ninguno": return 0

    v_hora = tarifas.get("Hora", {}).get(tipo_vehi, 110)
    v_promo4h = tarifas.get("Promo_4h", {}).get(tipo_vehi, 330)
    v_dia = tarifas.get("Dia_Completo", {}).get(tipo_vehi, 550)
    v_lavado_ext = tarifas.get("Lavado_Exterior", {}).get(tipo_vehi, 350)
    v_lavado_comp = tarifas.get("Lavado_Completo", {}).get(tipo_vehi, 500)
    p_2h_lavado = tarifas.get("Promo_2h_Lavado", {}).get(tipo_vehi, 600)
    p_4h_lavado = tarifas.get("Promo_4h_Lavado", {}).get(tipo_vehi, 720)
    p_8h_lavado = tarifas.get("Promo_8h_Lavado", {}).get(tipo_vehi, 880)

    def costo_solo_tiempo(mins):
        if mins <= 0: return 0
        dias = mins // 480
        restante = mins % 480
        costo = dias * v_dia
        if restante <= 240: costo += min(math.ceil(restante/60) * v_hora, v_promo4h)
        else: costo += min(v_promo4h + math.ceil((restante-240)/60) * v_hora, v_dia)
        return costo

    costo_base = costo_solo_tiempo(m_cobro)

    if tipo_lavado == "Ninguno": return costo_base
    elif "Exterior" in tipo_lavado: return costo_base + v_lavado_ext
    elif "Completo" in tipo_lavado:
        if m_cobro <= 0: return v_lavado_comp
        costo_normal = costo_base + v_lavado_comp
        dias = m_cobro // 480
        rest_mins = m_cobro % 480
        costo_dias = dias * v_dia
        if rest_mins <= 120: mejor_combo = min(costo_solo_tiempo(rest_mins) + v_lavado_comp, p_2h_lavado)
        elif rest_mins <= 240: mejor_combo = min(costo_solo_tiempo(rest_mins) + v_lavado_comp, p_4h_lavado)
        else: mejor_combo = min(costo_solo_tiempo(rest_mins) + v_lavado_comp, p_8h_lavado)
        if dias == 0: return min(costo_normal, mejor_combo)
        else: return costo_dias + mejor_combo
    else: return 0

def verificar_estado_empleado(nombre_emp, asistencia_rows):
    nombre_buscado = str(nombre_emp).strip().lower()
    for row in reversed(asistencia_rows[1:]):
        if len(row) > 2 and str(row[1]).strip().lower() == nombre_buscado:
            estado = str(row[2]).strip().capitalize()
            if estado in ["Entrada", "Fichaje", "Salida"]: return estado
    return "Salida"

@st.cache_data(ttl=60, show_spinner=False)
def cargar_usuarios_desde_db():
    pins_dict = {}
    try:
        conf = sh.worksheet("Configuracion").get_all_values()
        for r in conf[1:]:
            if len(r) >= 3 and str(r[0]).strip() and str(r[1]).strip():
                pins_dict[str(r[1]).strip().lstrip("'")] = {"nombre": str(r[0]).strip(), "rol": str(r[2]).strip()}
    except: pass
    if "1000" not in pins_dict: pins_dict["1000"] = {"nombre": "Rodrigo Bueno", "rol": "Admin"}
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
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.title("🔐 Acceso al Sistema - Parking El Globo")
    
    with st.expander("📖 **¿Cómo funciona el sistema? (Guía Rápida)**", expanded=False):
        st.markdown("""
        **Paso 1: Fichar Entrada ⏰**
        * Al llegar, logueate y andá al módulo **Personal**.
        * Hacé clic en "Registrar Entrada", contá el dinero de la caja, cargá el stock físico y confirmá.
        
        **Paso 2: Operativa 🚗**
        * **📥 Ingreso:** Anotá la patente y enviá el comprobante al cliente.
        * **✅ Validaciones:** Si los locales Quinquela o Nro 18 aplican un descuento, se mostrará en los activos.
        
        **Paso 3: Cobro y Salida 📤**
        * Andá a **Salida**, buscá el auto, y el sistema calculará automáticamente el mejor precio.
        * Al finalizar el turno, volvé a **Personal** para registrar tu Salida con el conteo final de caja.
        """)
    
    st.markdown("Ingrese su clave numérica para iniciar el turno:")
    
    pin_ingresado = st.text_input("🔑 PIN de Seguridad:", type="password")
    
    if st.button("Ingresar"):
        time.sleep(1) # Breve pausa anti-spam
        
        pin_clean = str(pin_ingresado).strip()
        
        if not pin_clean:
            st.error("⚠️ Debe ingresar su clave.")
        else:
            # Busca la clave directamente en la base de datos sin importar el largo
            if pin_clean in usuarios_pins:
                datos_u = usuarios_pins[pin_clean]
                st.session_state.usuario = datos_u["nombre"]
                st.session_state.rol = datos_u["rol"]
                st.session_state.pin_usado = pin_clean
                st.rerun()
            else:
                st.error("❌ Clave incorrecta o no autorizada en el sistema.")
    st.stop()
    
    if st.button("Ingresar"):
        pin_clean = str(pin_ingresado).strip().lstrip("'")
        if not pin_clean: st.error("⚠️ Debe ingresar su clave.")
        elif pin_clean in usuarios_pins:
            st.session_state.usuario = usuarios_pins[pin_clean]["nombre"]
            st.session_state.rol = usuarios_pins[pin_clean]["rol"]
            st.session_state.pin_usado = pin_clean
            st.rerun()
        else: st.error("❌ Clave incorrecta.")
    st.stop() 

if st.session_state.pin_usado == "1000" or "rodrigo" in str(st.session_state.usuario).lower():
    st.session_state.rol = "Admin"

st.markdown("<br>", unsafe_allow_html=True)
c_user, c_out = st.columns([3, 1])
c_user.markdown(f"👤 **{st.session_state.usuario}** | 🛡️ {st.session_state.rol}")
if c_out.button("🚪 Salir"):
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()
st.divider()

@st.cache_data(ttl=60, show_spinner=False)
def obtener_datos():
    for intento in range(3):
        try:
            if not sh: return [], {}, {}, [], [], [], [], [], [], [], [], [], []
            todas_las_hojas = {ws.title: ws for ws in sh.worksheets()}
            
            def get_data(nombre):
                return todas_las_hojas[nombre].get_all_values() if nombre in todas_las_hojas else []

            conf = get_data("Configuracion")
            tarifas_raw = get_data("Tarifas")
            extras_raw = get_data("Extras")
            reg = get_data("Registro")
            q_data = get_data("Respuestas de formulario 1")
            cli = get_data("Clientes_Frecuentes")
            asistencia = get_data("Asistencia")
            mensualistas = get_data("Base_Mensualistas")
            stock = get_data("Control_Stock")
            efectivo_data = get_data("Efectivo_Caja")
            eventos = get_data("Eventos")
            historial = get_data("Historial_Tickets")
            lista_inv = get_data("Lista_Invitados")
            
            empleados = [r[0] for r in conf[1:] if r[0]]
            tarifas = {str(r[0]).strip(): {"Auto": int(r[1]) if len(r)>1 and str(r[1]).strip().isdigit() else 0, 
                                           "Camioneta": int(r[2]) if len(r)>2 and str(r[2]).strip().isdigit() else 0} 
                       for r in tarifas_raw[1:] if len(r) > 0 and r[0].strip()}
            extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
            
            return empleados, tarifas, extras, reg, q_data, cli, asistencia, mensualistas, stock, efectivo_data, eventos, historial, lista_inv
        except Exception as e:
            if intento == 2: return [], {}, {}, [], [], [], [], [], [], [], [], [], []
            time.sleep(1.5)

resultado_datos = obtener_datos()
if not resultado_datos[0] and st.session_state.rol != "Admin":
    st.warning("🔄 Hubo un pequeño corte de conexión. Recargue la página en unos segundos.")
    st.stop()

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, efectivo_data, eventos_data, historial_data, lista_inv_data = resultado_datos
emp = st.session_state.usuario
es_admin_rodrigo = "rodrigo" in emp.lower() or st.session_state.rol == "Admin"

ultimo_est_operador = verificar_estado_empleado(emp, asistencia_data)
if st.session_state.local_emp == emp and st.session_state.local_estado != "":
    ultimo_est_operador = st.session_state.local_estado

st.markdown("### 📍 Menú Principal")
opciones_menu = []
if not es_admin_rodrigo and st.session_state.rol == "Valet": opciones_menu.append("⏰ Personal")
if (ultimo_est_operador in ["Entrada", "Fichaje"] and st.session_state.rol == "Valet") or es_admin_rodrigo:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🍔 Extras", "📤 Salida"])
if (st.session_state.rol and st.session_state.rol.startswith("Local_")) or es_admin_rodrigo: opciones_menu.append("✅ Validaciones")
if es_admin_rodrigo: opciones_menu.append("📈 Reportes")

if not opciones_menu:
    st.error("⚠️ No tienes permisos activos. Ve al módulo Personal para registrar tu Entrada.")
    opciones_menu = ["⏰ Personal"] 

menu = st.radio("Navegación:", opciones_menu, horizontal=True, label_visibility="collapsed")
st.divider()

if st.session_state.rol == "Valet" and ultimo_est_operador == "Salida" and menu != "⏰ Personal":
    st.warning("⚠️ **¡ATENCIÓN! No olvides registrar tu ENTRADA para habilitar el sistema.**")

def actualizar_stock_en_extras(producto_nombre, cantidad_vendida):
    try:
        ws_ex = sh.worksheet("Extras")
        rows = ws_ex.get_all_values()
        for idx, r in enumerate(rows[1:], start=2):
            if len(r) > 0 and str(r[0]).strip().lower() == str(producto_nombre).strip().lower():
                vendidos_actuales = float(r[3]) if r[3] and r[3] != "" else 0
                stock_actual = float(r[4]) if r[4] and r[4] != "" else 0
                ws_ex.update_cell(idx, 4, vendidos_actuales + float(cantidad_vendida))
                ws_ex.update_cell(idx, 5, stock_actual - float(cantidad_vendida))
                break
    except: pass

# ------------------------------------------
# INGRESO
# ------------------------------------------
if menu == "📥 Ingreso":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Registro de Ingreso")
    if c_head2.button("🔄 Refrescar", key="ref_ing"):
        obtener_datos.clear()
        st.rerun()

    k = st.session_state.form_key_count
    hoy_str = hora_actual_uy().split()[0]
    
    patentes_frec = [str(rc[0]).strip().upper().replace("-", "").replace(" ", "") for rc in clientes[1:] if len(rc) > 0 and str(rc[0]).strip()]
    
    patentes_mensualistas = []
    datos_mensualistas_map = {}
    for m in mensualistas_data[1:]:
        if len(m) > 0 and str(m[0]).strip():
            pat_m = str(m[0]).strip().upper().replace("-", "").replace(" ", "")
            patentes_mensualistas.append(pat_m)
            datos_mensualistas_map[pat_m] = {
                "nombre": str(m[1]).strip() if len(m) > 1 and str(m[1]).strip() else "Mensualista/Autorizado",
                "estado": str(m[2]).strip().upper() if len(m) > 2 else "",
                "telefono": str(m[3]).strip() if len(m) > 3 else "",
                "beneficio": str(m[4]).strip().upper() if len(m) > 4 else ""
            }

    invitados_hoy_map = {}
    for inv in lista_inv_data[1:]:
        if len(inv) >= 4 and str(inv[0]).strip() == hoy_str:
            pat_inv = str(inv[3]).strip().upper().replace("-", "").replace(" ", "")
            invitados_hoy_map[pat_inv] = {"nombre": str(inv[2]).strip(), "evento": str(inv[1]).strip()}

    patentes_unificadas = sorted(list(set(patentes_frec + patentes_mensualistas)))
    sel_pat_cam = st.selectbox("📷 1. Patente Frecuente / Mensualista:", [""] + patentes_unificadas, key=f"cam_{k}")
    pat_manual = st.text_input("✍️ 2. Ingreso Manual (Auto Nuevo):", key=f"man_{k}")
    
    pat_final = (pat_manual.strip() if pat_manual.strip() else sel_pat_cam).upper().replace("-", "").replace(" ", "")
    st.divider()

    nombre_sug, cel_sug = "", "598"
    es_deudor, es_invitado_vip = False, False
    evento_vip_sug = ""
    
    if pat_final:
        if pat_final in invitados_hoy_map:
            es_invitado_vip = True
            nombre_sug = invitados_hoy_map[pat_final]["nombre"]
            evento_vip_sug = invitados_hoy_map[pat_final]["evento"]
            
        if pat_final in datos_mensualistas_map:
            datos_m = datos_mensualistas_map[pat_final]
            if not nombre_sug: nombre_sug = datos_m["nombre"]
            if datos_m["telefono"]: cel_sug = datos_m["telefono"]
            estado_visual = datos_m["estado"]
            if estado_visual == "DEUDOR": es_deudor = True
            elif estado_visual in ["AL DIA", "AUTORIZADO"]:
                st.success(f"💳 **Vehículo Registrado ({estado_visual})** a nombre de: {nombre_sug}")
            bene = datos_m.get("beneficio", "")
            if "LAVADO" in bene: st.info(f"💦 **Aviso: Cuenta con: {bene}**")
                
        for rc in clientes[1:]:
            if len(rc) > 2 and str(rc[0]).upper().replace("-", "").replace(" ", "") == pat_final:
                if not nombre_sug: nombre_sug = str(rc[1]).strip()
                cel_sug = str(rc[2]).strip()
                break

        if es_invitado_vip:
            st.success(f"🌟 **¡INVITADO VIP HOY!** Evento: {evento_vip_sug} | Nombre: {nombre_sug}")

    if "ultima_patente" not in st.session_state: st.session_state.ultima_patente = ""
    if pat_final != st.session_state.ultima_patente:
        st.session_state.ultima_patente = pat_final
        st.session_state[f"cli_{k}"] = nombre_sug
        st.session_state[f"cel_{k}"] = cel_sug
                
    tkt = st.text_input("🎫 N° Tarjeta PVC (OBLIGATORIO para clientes estándar):", key=f"tkt_{k}")
    cli_nom = st.text_input("👤 Nombre y Apellido:", key=f"cli_{k}")
    cel = st.text_input("📱 Celular:", key=f"cel_{k}")
    tipo_vehi = st.selectbox("🚙 Vehículo:", ["Auto", "Camioneta"], key=f"veh_{k}")
    
    eventos_hoy = []
    cupos_evento = {}
    for ev in eventos_data[1:]:
        if len(ev) >= 3 and str(ev[0]).strip() == hoy_str:
            nombre_ev = str(ev[1]).strip()
            eventos_hoy.append(nombre_ev)
            try: cupos_evento[nombre_ev] = int(ev[2])
            except: cupos_evento[nombre_ev] = 999

    opciones_eventos = [""] + eventos_hoy
    idx_evento = opciones_eventos.index(evento_vip_sug) if (es_invitado_vip and evento_vip_sug in opciones_eventos) else 0

    evento_sel = ""
    if eventos_hoy:
        evento_sel = st.selectbox("🎟️ Evento VIP:", opciones_eventos, index=idx_evento, key=f"evt_{k}")
        if evento_sel:
            autos_en_evento = sum(1 for r in reg[1:] if len(r) > 4 and f"Evento: {evento_sel}" in str(r[4]) and hoy_str in str(r[2]))
            if autos_en_evento >= cupos_evento[evento_sel]:
                st.warning(f"⚠️ Cupo superado para '{evento_sel}'. ({autos_en_evento} ingresados).")
            else: st.info(f"✅ Cupo: {autos_en_evento} / {cupos_evento[evento_sel]}")

    texto_deuda_completo = ""
    if es_deudor:
        st.error(f"🚨 **¡ATENCIÓN! El mensualista {cli_nom or nombre_sug} REGISTRA DEUDA.**")
        saludo = f"Buen día {(cli_nom or nombre_sug).strip().title()},"
        texto_deuda_completo = f"{saludo} le informamos que aún no se ha registrado su pago (multa 5% cada 5 días)."
    
    if st.button("✅ Registrar Ingreso"):
        cel_clean = str(cel).strip()
        if cel_clean.startswith("0"): cel_clean = cel_clean[1:]
        tkt_final = str(tkt).strip()
        
        # SISTEMA DE VALIDACIÓN OBLIGATORIA Y SIGLAS CLARAS
        if not tkt_final: 
            if evento_sel:
                prefijo = "EV-"
                max_num = 0
                for r_val in reg[1:]:
                    t_val = str(r_val[0]).strip().upper()
                    if t_val.startswith(prefijo) and t_val.replace(prefijo, "").isdigit():
                        max_num = max(max_num, int(t_val.replace(prefijo, "")))
                for h_val in historial_data[1:]:
                    if len(h_val) > 3:
                        t_val = str(h_val[3]).replace("#", "").strip().upper()
                        if t_val.startswith(prefijo) and t_val.replace(prefijo, "").isdigit():
                            max_num = max(max_num, int(t_val.replace(prefijo, "")))
                tkt_final = f"{prefijo}{max_num + 1}"
                
            elif pat_final in datos_mensualistas_map:
                estado_m = datos_mensualistas_map[pat_final]["estado"]
                prefijo = "AUT-" if estado_m == "AUTORIZADO" else "MEN-"
                max_num = 0
                for r_val in reg[1:]:
                    t_val = str(r_val[0]).strip().upper()
                    if t_val.startswith(prefijo) and t_val.replace(prefijo, "").isdigit():
                        max_num = max(max_num, int(t_val.replace(prefijo, "")))
                for h_val in historial_data[1:]:
                    if len(h_val) > 3:
                        t_val = str(h_val[3]).replace("#", "").strip().upper()
                        if t_val.startswith(prefijo) and t_val.replace(prefijo, "").isdigit():
                            max_num = max(max_num, int(t_val.replace(prefijo, "")))
                tkt_final = f"{prefijo}{max_num + 1}"
                
            else:
                st.error("⚠️ DATOS INCOMPLETOS: Debes ingresar el N° de Tarjeta PVC obligatoriamente para vehículos estándar.")
                st.stop()

        if not pat_final: st.warning("⚠️ Patente obligatoria.")
        else:
            pat_clean = pat_final.replace("-", "").replace(" ", "").upper()
            tkt_clean = tkt_final.replace("#", "").strip().lstrip("0").upper()
            
            vehiculo_activo = any((str(r[0]).replace("#","").strip().lstrip("0").upper() == tkt_clean or str(r[1]).replace("-","").replace(" ","").upper() == pat_clean) and (not str(r[3]).strip() or str(r[3]).lower() == "nan") for r in reg[1:] if len(r) > 3)

            if vehiculo_activo: st.error("❌ ¡Tarjeta o patente activa en playa!")
            else:
                try:
                    h_ing = hora_actual_uy()
                    estado_txt = f"Evento: {evento_sel} ({tipo_vehi}) - Op: {emp}" if evento_sel else f"Estándar ({tipo_vehi}) - Op: {emp}"
                    
                    sh.worksheet("Registro").append_row([tkt_final, pat_final, h_ing, "", estado_txt, "", 0, 0, 0])
                    
                    if cli_nom and not nombre_sug and pat_final not in datos_mensualistas_map:
                        sh.worksheet("Clientes_Frecuentes").append_row([pat_final, cli_nom.strip().title(), cel_clean])
                    
                    if pat_final in datos_mensualistas_map and cel_clean and cel_clean != "598" and not datos_mensualistas_map[pat_final]["telefono"]:
                        ws_men = sh.worksheet("Base_Mensualistas")
                        for idx, m_row in enumerate(mensualistas_data):
                            if len(m_row) > 0 and str(m_row[0]).strip().upper().replace("-", "").replace(" ", "") == pat_final:
                                ws_men.update_cell(idx + 1, 4, cel_clean)
                                break
                    
                    msg_ingreso = f"*PARKING EL GLOBO - INGRESO*\n👤 Cliente: {cli_nom.strip().title() or nombre_sug or 'Frecuente'}\n🚗 Vehículo: {pat_final}\n🎫 Tarjeta: #{tkt_final}\n🕒 Ingreso: {h_ing}"
                    if evento_sel: msg_ingreso += f"\n🎟️ *Invitado:* {evento_sel}"
                    if es_deudor: msg_ingreso += f"\n\n⚠️ *DEUDA PENDIENTE:*\n{texto_deuda_completo}"
                    
                    st.session_state.exito_msg = f"✅ Ingreso: {pat_final} | Tkt #{tkt_final}"
                    st.session_state.exito_wp = f"[📲 Enviar Comprobante](https://wa.me/{cel_clean}?text={urllib.parse.quote(msg_ingreso)})"
                    st.session_state.form_key_count += 1
                    st.session_state.ultima_patente = "" 
                    obtener_datos.clear() 
                    st.rerun()
                except Exception as e: st.error(f"❌ Error DB: {e}")

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
        if len(r) > 3 and str(r[0]).upper() != "EXTRA" and not str(r[0]).startswith("LPR-") and (not str(r[3]).strip() or str(r[3]).lower() == "nan"):
            pat, h_ing, tkt = str(r[1]).upper(), r[2], str(r[0]).strip()
            local_val = obtener_validacion_local(pat, tkt, h_ing, q_data)
            st.info(f"🎫 #{tkt} | 🚗 {pat} | 🕒 {h_ing}" + (f" | 🍽️ **VALIDADO: {local_val.upper()}**" if local_val else ""))

# ------------------------------------------
# VALIDACIONES PRIVADAS
# ------------------------------------------
elif menu == "✅ Validaciones":
    st.subheader("Validación de Locales")
    local_seleccionado = st.session_state.rol.replace("Local_", "") if st.session_state.rol.startswith("Local_") else st.selectbox("Local:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
        
    activos_disponibles = [r for r in reg[1:] if len(r)>3 and r[0].upper() != "EXTRA" and not r[0].startswith("LPR-") and (not r[3].strip() or r[3].lower()=="nan") and not obtener_validacion_local(r[1], r[0], r[2], q_data)]
    activos_disponibles.sort(key=lambda x: int(''.join(filter(str.isdigit, x[0])) or 999999))
    
    seleccion_mozo = st.selectbox("Vehículo:", [""] + [f"#{r[0]} - Patente: {r[1].upper()}" for r in activos_disponibles])
    mozo = st.text_input("Mozo:") if local_seleccionado == "Quinquela" else f"Recepción {local_seleccionado}"
    factura = st.text_input("Últimos 4 dígitos factura:", max_chars=4) if local_seleccionado == "Quinquela" else "N/A"
        
    if st.button("Aplicar Validación y Avisar") and seleccion_mozo:
        if local_seleccionado == "Quinquela" and (not mozo or len(factura) < 4): st.error("⚠️ Faltan datos.")
        else:
            tkt_val = seleccion_mozo.split(" - ")[0].replace("#", "").strip()
            pat_val = next((r[1].upper() for r in activos_disponibles if r[0].strip() == tkt_val), "")
            try:
                sh.worksheet("Respuestas de formulario 1").append_row([hora_actual_uy(), mozo, tkt_val, pat_val, factura, local_seleccionado])
                msg_aviso = urllib.parse.quote(f"⚠️ *VALIDACIÓN*\n🚗 {pat_val} (Tkt #{tkt_val})\n🏪 {local_seleccionado}\n👤 {mozo}")
                st.success(f"✅ Validación aplicada.")
                st.markdown(f"[➡️ Notificar Cel 1](https://wa.me/{TEL_PARKING_1}?text={msg_aviso}) | [➡️ Notificar Cel 2](https://wa.me/{TEL_PARKING_2}?text={msg_aviso})", unsafe_allow_html=True)
                obtener_datos.clear()
            except Exception as e: st.error(f"Error: {e}")

# ------------------------------------------
# EXTRAS
# ------------------------------------------
elif menu == "🍔 Extras":
    st.subheader("Carga de Extras")
    activos = sorted([r for r in reg[1:] if len(r)>3 and (not r[3] or r[3].lower()=='nan') and r[0].upper()!="EXTRA" and not r[0].startswith("LPR-")], key=lambda x: int(''.join(filter(str.isdigit, x[0])) or 999999))
    sel_auto = st.selectbox("Vehículo:", ["🛒 VENTA DIRECTA (Sin Vehículo)"] + [f"#{r[0]} - Patente: {str(r[1]).upper()}" for r in activos])
    
    prod = st.selectbox("Extra:", [""] + list(extras.keys()))
    cant = st.number_input("Cantidad:", min_value=1, step=1)
    
    if prod:
        subtotal = extras.get(prod, 0) * cant
        st.info(f"💰 Subtotal a cobrar: **${subtotal}**")
    
    if st.button("Registrar Extra") and prod:
        fecha_act = hora_actual_uy()
        try:
            ws_stock = sh.worksheet("Control_Stock")
            if sel_auto == "🛒 VENTA DIRECTA (Sin Vehículo)":
                ws_stock.append_row([fecha_act, prod, cant, emp, "VENTA DIRECTA"])
                actualizar_stock_en_extras(prod, cant)
                st.success(f"✅ Venta directa: {cant}x {prod}.")
            else:
                tkt = sel_auto.split(" - ")[0].replace("#", "").strip()
                patente_ext = sel_auto.split("Patente: ")[1].strip().upper()
                ws_stock.append_row([fecha_act, prod, cant, emp, patente_ext])
                actualizar_stock_en_extras(prod, cant)
                ws_reg = sh.worksheet("Registro")
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).replace("#", "").strip() == tkt and (not row[3] or str(row[3]).lower() == "nan"):
                        nuevo_texto = f"{str(row[5]) if len(row)>5 and row[5] else ''} | {cant}x {prod}".strip(" |")
                        ws_reg.update_cell(i, 6, nuevo_texto)
                        ws_reg.update_cell(i, 8, (float(row[7]) if len(row)>7 and row[7] else 0) + (extras.get(prod, 0) * cant))
                        break
                st.success(f"✅ Extra cargado al #{tkt}.")
            obtener_datos.clear()
        except Exception as e: st.error("Error.")

# ------------------------------------------
# SALIDA
# ------------------------------------------
elif menu == "📤 Salida":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Ticket Final")
    if c_head2.button("🔄 Refrescar", key="ref_sal"):
        obtener_datos.clear()
        st.rerun()

    activos = sorted([r for r in reg[1:] if len(r)>3 and (not r[3] or r[3].lower()=='nan') and r[0].upper()!="EXTRA" and not r[0].startswith("LPR-")], key=lambda x: int(''.join(filter(str.isdigit, x[0])) or 999999))
    sel = st.selectbox("Vehículo a retirar:", [""] + [f"#{r[0]} - Patente: {str(r[1]).upper()}" for r in activos])
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        datos = next(r for r in activos if r[0].strip() == tkt)
        patente, h_ingreso, tipo_vehi = str(datos[1]).upper(), datos[2], "Camioneta" if "Camioneta" in str(datos[4]) else "Auto"
        
        nombre_cliente, cel_salida, beneficio = "Cliente", "598", ""
        for c in clientes[1:]:
            if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                nombre_cliente, cel_salida = str(c[1]).strip(), str(c[2]).strip()
                break
                
        for m in mensualistas_data[1:]:
            if len(m) > 0 and str(m[0]).upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                if len(m)>1 and m[1].strip(): nombre_cliente = str(m[1]).strip()
                if len(m)>3 and m[3].strip(): cel_salida = str(m[3]).strip()
                if len(m)>4 and m[4].strip(): beneficio = str(m[4]).strip()
                break
                
        cel_salida = st.text_input("Celular:", value=cel_salida)
        obs_salida = st.text_input("Observaciones:")
        if "LAVADO" in beneficio.upper(): st.info(f"💦 **Beneficio Mensualista: {beneficio}**")
            
        lavado_opcion = st.selectbox("🧼 Lavado:", ["Ninguno", "Lavado Exterior (Cobrar)", "Lavado Completo (Cobrar / Aplica Promos)", "Lavado Incluido (Plan Mensualista)"])
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🧮 CALCULAR EGRESO", type="primary", use_container_width=True):
            h_salida = hora_actual_uy()
            mins = int((datetime.utcnow() - timedelta(hours=3) - datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60)
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            
            es_evento = "Evento:" in str(datos[4])
            nombre_ev = str(datos[4]).split("Evento: ")[1].split(" (")[0] if es_evento else ""
            
            estado_mensual, nombre_men = "", ""
            for m in mensualistas_data[1:]:
                if len(m) > 0 and str(m[0]).strip().upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                    texto = " ".join([str(val) for val in m]).upper()
                    estado_mensual = "AUTORIZADO" if "AUTORIZADO" in texto else ("DEUDOR" if "DEUD" in texto else "AL DIA")
                    nombre_men = str(m[1]).strip() if len(m) > 1 else "Mensualista"
                    break
            
            if es_evento:
                monto = 0
                info_desc = f"🎟️ Evento VIP: {nombre_ev}. Parking $0."
                st.success(info_desc)
            elif estado_mensual in ["AUTORIZADO", "AL DIA"]:
                monto = tarifas.get("Lavado_Exterior", {}).get(tipo_vehi, 350) if "Exterior (Cobrar)" in lavado_opcion else (tarifas.get("Lavado_Completo", {}).get(tipo_vehi, 500) if "Completo" in lavado_opcion else 0)
                info_desc = f"✅ Mensualista. Parking $0." + (f" Se cobra lavado." if monto > 0 else "")
                st.success(info_desc)
            elif estado_mensual == "DEUDOR":
                monto = 0
                info_desc = f"🛑 Mensualista con DEUDA."
                st.warning(info_desc)
            else:
                monto = calcular_mejor_precio(mins, tipo_vehi, local_val, tarifas, lavado_opcion)
                info_desc = f"100% libre por {local_val}." if local_val in ["Rodrigo Bueno", "Number 18"] else ("Cortesía 2.5h Quinquela" if local_val == "Quinquela" else "Tarifa estándar calculada.")
            
            total_extras = float(datos[7]) if len(datos) > 7 and datos[7] else 0
            detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras."
            if lavado_opcion != "Ninguno": detalle_extras_txt = f"{detalle_extras_txt} | 🧼 {lavado_opcion.split(' (')[0]}".strip(" |")
            total_a_pagar = monto + total_extras
            
            texto_ticket = f"""*TICKET EGRESO*\n🚗 {patente} | Tkt: #{tkt}\n🕒 Ingreso: {h_ingreso}\n🕒 Salida: {h_salida}\n⏱️ Estadía: {mins//60}h {mins%60}m\n\n📋 DETALLE:\n{detalle_extras_txt}\nEstacionamiento/Lavado: ${monto}\nExtras: ${total_extras}\n\n💰 *TOTAL: ${total_a_pagar}*\nOp: {emp}"""

            try:
                ws_reg = sh.worksheet("Registro")
                tkt_salida_clean = tkt.replace("#", "").strip().lstrip("0").upper()
                for i, row in enumerate(reg, start=1):
                    if str(row[0]).replace("#", "").strip().lstrip("0").upper() == tkt_salida_clean and (not row[3] or str(row[3]).lower() == "nan"):
                        ws_reg.update_cell(i, 4, h_salida)
                        ws_reg.update_cell(i, 7, float(monto))
                        ws_reg.update_cell(i, 9, float(total_a_pagar))
                        break
                
                local_val_guardar = f"Evento: {nombre_ev}" if es_evento else (local_val if local_val else "Ninguna")
                try: ws_h = sh.worksheet("Historial_Tickets")
                except: ws_h = sh.add_worksheet(title="Historial_Tickets", rows="1000", cols="10")
                ws_h.append_row([h_salida, emp, patente, f"#{tkt}", float(monto), float(total_extras), float(total_a_pagar), obs_salida if obs_salida else "-", local_val_guardar])
                
                obtener_datos.clear() 
                st.success("✅ ¡Ticket registrado!")
                with st.expander("🔍 Ver comprobante", expanded=True): st.code(texto_ticket)
                cel = str(cel_salida).strip().lstrip("0")
                st.markdown(f"[📲 Enviar Ticket](https://wa.me/{cel}?text={urllib.parse.quote(texto_ticket)})")
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🏁 TERMINAR", type="primary", use_container_width=True): st.rerun()
            except Exception as e: st.error(f"❌ Error: {e}")

# ------------------------------------------
# PERSONAL Y REPORTES
# ------------------------------------------
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Caja")
    if st.button("🔄 Actualizar"):
        obtener_datos.clear()
        st.rerun()

    st.info(f"👤 {emp} | Estado: **{ultimo_est_operador}**")
    tab_entrada, tab_salida = st.tabs(["📥 ENTRADA", "📤 SALIDA"])
    
    with tab_entrada:
        if ultimo_est_operador == "Entrada": st.info("ℹ️ Entrada activa.")
        elif ultimo_est_operador == "Fichaje":
            st.success("Complete Inventario.")
            with st.form("form_inv_ent"):
                efectivo = st.number_input("💵 Caja inicial:", value=0, step=50)
                submit = st.form_submit_button("✅ Finalizar Entrada")
                if submit:
                    try:
                        hora = st.session_state.get("hora_fichaje_temporal", hora_actual_uy())
                        sh.worksheet("Efectivo_Caja").append_row([hora, emp, "Entrada", int(efectivo), ""])
                        sh.worksheet("Asistencia").append_row([hora, emp, "Entrada", f"Caja: ${efectivo}"])
                        st.session_state.local_estado = "Entrada"
                        obtener_datos.clear()
                        st.success("✅ Guardado.")
                    except: st.error("Error.")
        else:
            if st.button("⏰ Registrar Entrada"):
                hora = hora_actual_uy()
                sh.worksheet("Asistencia").append_row([hora, emp, "Fichaje", "Esperando inventario"])
                st.session_state.local_estado = "Fichaje"
                obtener_datos.clear()
                st.rerun()

    with tab_salida:
        if ultimo_est_operador == "Salida": st.info("ℹ️ No hay entrada activa.")
        else:
            with st.form("form_inv_sal"):
                efectivo = st.number_input("💵 Arqueo Final:", value=0, step=50)
                submit = st.form_submit_button("🚪 Registrar Salida")
                if submit:
                    try:
                        hora = hora_actual_uy()
                        sh.worksheet("Efectivo_Caja").append_row([hora, emp, "Salida", int(efectivo), ""])
                        sh.worksheet("Asistencia").append_row([hora, emp, "Salida", f"Cierre: ${efectivo}"])
                        st.session_state.local_estado = "Salida"
                        st.session_state.cartel_salida_msg = "🚪 SALIDA REGISTRADA."
                        obtener_datos.clear() 
                        st.rerun()
                    except: st.error("Error.")
    if st.session_state.cartel_salida_msg != "":
        st.success(st.session_state.cartel_salida_msg)
        if st.button("🔄 Aceptar"):
            st.session_state.cartel_salida_msg = ""
            st.rerun()

elif menu == "📈 Reportes":
    st.subheader("📊 Panel de Ventas, Control y Auditoría")
    
    st.markdown("### 📊 Control Comercial: Mensualistas y Autorizados")
    try:
        ws_men = sh.worksheet("Base_Mensualistas")
        datos_m = ws_men.get_all_values()
        if len(datos_m) > 1:
            total_comercial = len(datos_m) - 1
            total_autorizados, total_al_dia = 0, 0
            lista_deudores = []
            
            for fila in datos_m[1:]:
                if not fila or not fila[0].strip(): continue
                mat = str(fila[0]).strip().upper()
                texto_fila_completo = " ".join([str(val).strip() for val in fila]).upper()
                
                if "AUTORIZADO" in texto_fila_completo: total_autorizados += 1
                elif "DEUDA" in texto_fila_completo or "DEUDOR" in texto_fila_completo:
                    nombre_encontrado = str(fila[1]).strip() if len(fila) > 1 and str(fila[1]).strip() else "Sin nombre"
                    if "DEUDOR" in nombre_encontrado.upper() or "AL DIA" in nombre_encontrado.upper() or "AUTORIZADO" in nombre_encontrado.upper():
                        nombre_encontrado = str(fila[2]).strip() if len(fila) > 2 else "Sin nombre"
                    lista_deudores.append({"Matrícula": mat, "Nombre / Empresa": nombre_encontrado})
                else: total_al_dia += 1

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
            else: st.success("¡Excelente estado de cuenta! No se registran deudores marcados en el sistema.")
        else: st.info("ℹ️ La pestaña Base_Mensualistas está vacía.")
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
        else: st.info("ℹ️ Aún no hay registros de asistencia.")
    except Exception as e: st.error(f"Error cargando asistencia: {e}")

    st.divider()

    st.markdown("### 💵 Auditoría de Caja y Efectivo")
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
        else: st.info("ℹ️ Aún no hay registros en la pestaña Efectivo_Caja.")
    except Exception as e: st.info("ℹ️ Asegúrate de tener creada la pestaña 'Efectivo_Caja' en tu Google Sheet.")

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
                st.markdown("### 🏪 Uso de Validaciones (Locales)")
                if not df.empty:
                    df_validaciones = df[~df['Validación'].str.startswith('Evento:', na=False)]
                    df_loc = df_validaciones.groupby('Validación').size().reset_index(name='Cantidad de Autos')
                    st.dataframe(df_loc.sort_values(by='Cantidad de Autos', ascending=False), use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 🎟️ Asistencia a Eventos")
            
            st.markdown("#### 🟢 Actualmente en Playa (Ingresados)")
            activos_eventos = []
            for r_ev in reg[1:]:
                if len(r_ev) > 4 and "Evento:" in str(r_ev[4]) and (not r_ev[3] or str(r_ev[3]).lower() == "nan"):
                    ev_name = str(r_ev[4]).split("Evento: ")[1].split(" (")[0]
                    activos_eventos.append({"Evento": ev_name, "Patente": str(r_ev[1]).upper(), "Ticket": f"#{r_ev[0]}", "Hora Ingreso": r_ev[2]})
            
            if activos_eventos:
                st.dataframe(pd.DataFrame(activos_eventos), use_container_width=True)
            else:
                st.info("No hay vehículos de eventos actualmente en el estacionamiento.")

            st.markdown("#### 🏁 Egresados (Finalizados)")
            if not df.empty:
                df_evts = df[df['Validación'].str.startswith('Evento:', na=False)].copy()
                if not df_evts.empty:
                    df_ev_grouped = df_evts.groupby('Validación').size().reset_index(name='Invitados')
                    df_ev_grouped['Validación'] = df_ev_grouped['Validación'].str.replace("Evento: ", "")
                    df_ev_grouped.columns = ['Evento', 'Invitados (Egresados)']
                    st.dataframe(df_ev_grouped.sort_values(by='Invitados (Egresados)', ascending=False), use_container_width=True)
                else:
                    st.info("Aún no han egresado invitados de eventos en el período seleccionado.")
            
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
        else: st.warning("⚠️ El panel de facturación está esperando la primera salida del día para generar gráficos.")
    except Exception as e:
        st.error(f"Error conectando con el historial: {e}")
