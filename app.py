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
    
    html, body, [data-testid="stAppViewContainer"] {
        overscroll-behavior-y: none !important;
        -webkit-overflow-scrolling: touch;
    }
    
    [data-testid="stMainBlockContainer"] {
        padding-bottom: 120px !important;
    }
    
    [data-testid="stSidebar"], [data-testid="collapsedControl"], footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
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

    setInterval(() => {
        fetch(window.location.href, { method: 'HEAD' }).catch(() => {});
    }, 20000);
    </script>
""", unsafe_allow_html=True)

TEL_PARKING_1 = "59895280412" 
TEL_PARKING_2 = "59893343092" 

@st.cache_resource
def init_connection():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        client = gspread.service_account_from_dict(creds_dict)
        return client.open("FlowPark_Valet_DB")
    except Exception as e:
        st.error("⚠️ Error crítico de conexión con la base de datos. Por favor, avise al administrador.")
        st.stop()

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

def calcular_mejor_precio(minutos, tipo_vehi, local_validacion, tarifas, tipo_lavado="Ninguno"):
    if local_validacion in ["Rodrigo Bueno", "Number 18"]:
        return 0

    descuento = 150 if local_validacion == "Quinquela" else 0
    m_cobro = max(0, minutos - descuento)

    if m_cobro <= 0 and tipo_lavado == "Ninguno": return 0

    v_hora = tarifas.get("Hora", {}).get(tipo_vehi, 110)
    v_promo4h = tarifas.get("Promo_4h", {}).get(tipo_vehi, 330)
    
    tarifas_8h = tarifas.get("Promo_8h")
    if not tarifas_8h: tarifas_8h = tarifas.get("Dia_Completo", {})
    v_promo8h = tarifas_8h.get(tipo_vehi, 550)

    v_lavado_ext = tarifas.get("Lavado Exterior", {}).get(tipo_vehi, 350)
    v_lavado_comp = tarifas.get("Lavado Completo", {}).get(tipo_vehi, 500)
    p_2h_lavado = tarifas.get("Promo 2 Horas + Lavado", {}).get(tipo_vehi, 600)
    p_4h_lavado = tarifas.get("Promo 4 Horas + Lavado", {}).get(tipo_vehi, 720)
    p_8h_lavado = tarifas.get("Promo 8 Horas + Lavado", {}).get(tipo_vehi, 880)

    def costo_solo_tiempo(mins):
        if mins <= 0: return 0
        
        bloques_8h = mins // 480
        restante = mins % 480
        
        costo = bloques_8h * v_promo8h
        horas_extra = math.ceil(restante / 60)
        
        if restante <= 240:
            costo += min(horas_extra * v_hora, v_promo4h)
        else:
            horas_por_encima_de_4 = math.ceil((restante - 240) / 60)
            costo += min(v_promo4h + horas_por_encima_de_4 * v_hora, v_promo8h)
            
        return costo

    costo_base = costo_solo_tiempo(m_cobro)

    if tipo_lavado == "Ninguno":
        return costo_base
    elif "Exterior" in tipo_lavado:
        return costo_base + v_lavado_ext
    elif "Completo" in tipo_lavado or "Promo" in tipo_lavado:
        if m_cobro <= 0: return v_lavado_comp
        
        costo_normal = costo_base + v_lavado_comp
        
        if m_cobro <= 120:
            return min(costo_normal, p_2h_lavado)
        elif m_cobro <= 240:
            return min(costo_normal, p_4h_lavado)
        elif m_cobro <= 480:
            return min(costo_normal, p_8h_lavado)
        else:
            return p_8h_lavado + costo_solo_tiempo(m_cobro - 480)
    else:
        return 0

def verificar_estado_empleado(nombre_emp, asistencia_rows):
    nombre_buscado = str(nombre_emp).strip().lower()
    for row in reversed(asistencia_rows[1:]):
        if len(row) > 2 and str(row[1]).strip().lower() == nombre_buscado:
            estado = str(row[2]).strip().capitalize()
            if estado in ["Entrada", "Fichaje", "Salida"]:
                return estado
    return "Salida"

@st.cache_data(ttl=60, show_spinner=False)
def cargar_usuarios_desde_db():
    pins_dict = {}
    try:
        conf = sh.worksheet("Configuracion").get_all_values()
        for r in conf[1:]:
            if len(r) >= 3 and r[0].strip() and r[1].strip():
                nombre = r[0].strip()
                pin = str(r[1]).strip()
                rol = r[2].strip()
                pins_dict[pin] = {"nombre": nombre, "rol": rol}
        return pins_dict
    except Exception as e:
        return None

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

if "salida_procesada" not in st.session_state: st.session_state.salida_procesada = False
if "salida_ticket" not in st.session_state: st.session_state.salida_ticket = ""
if "salida_wp" not in st.session_state: st.session_state.salida_wp = ""

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
        * **✅ Validaciones:** Si los locales aplican un descuento, se mostrará en los activos.
        
        **Paso 3: Cobro y Salida 📤**
        * Andá a **Salida**, buscá el auto, y el sistema calculará automáticamente el precio o aplicará eventos/mensualidades.
        * Al finalizar el turno, volvé a **Personal** para registrar tu Salida.
        """)
    
    st.markdown("Ingrese su clave numérica para iniciar el turno:")
    pin_ingresado = st.text_input("🔑 PIN de Seguridad:", type="password")
    
    if st.button("Ingresar"):
        time.sleep(0.5)
        pin_clean = str(pin_ingresado).strip()
        
        if not pin_clean:
            st.error("⚠️ Debe ingresar su clave.")
        else:
            usuarios_pins = cargar_usuarios_desde_db()
            if usuarios_pins is None:
                st.warning("⏳ Enlace asegurando conexión con Google. Por favor, espere 15 segundos y vuelva a dar 'Ingresar'.")
            elif pin_clean in usuarios_pins:
                datos_u = usuarios_pins[pin_clean]
                st.session_state.usuario = datos_u["nombre"]
                st.session_state.rol = datos_u["rol"]
                st.session_state.pin_usado = pin_clean
                st.rerun()
            else:
                st.error("❌ Clave incorrecta o no autorizada en el sistema.")
    st.stop() 

st.markdown("<br>", unsafe_allow_html=True)
c_user, c_out = st.columns([3, 1])
c_user.markdown(f"👤 **{st.session_state.usuario}** | 🛡️ {st.session_state.rol}")
if c_out.button("🚪 Salir"):
    st.session_state.usuario = None
    st.session_state.rol = None
    st.session_state.pin_usado = ""
    st.session_state.cartel_salida_msg = ""
    st.session_state.cartel_entrada_msg = ""
    st.session_state.local_emp = ""
    st.session_state.local_estado = ""
    st.session_state.hora_fichaje_temporal = ""
    st.session_state.salida_procesada = False
    st.rerun()
st.divider()

@st.cache_data(ttl=120, show_spinner=False)
def obtener_datos():
    try:
        if not sh: return [], {}, {}, [], [], [], [], [], [], [], [], [], [], []
        hojas = sh.worksheets()
        titulos = [h.title for h in hojas]
        batch = sh.values_batch_get(titulos)
        
        data_dict = {}
        for idx, vr in enumerate(batch.get('valueRanges', [])):
            nombre_hoja = titulos[idx]
            data_dict[nombre_hoja] = vr.get('values', [])

        conf = data_dict.get("Configuracion", [])
        tarifas_raw = data_dict.get("Tarifas", [])
        extras_raw = data_dict.get("Extras", [])
        reg = data_dict.get("Registro", [])
        q_data = data_dict.get("Respuestas de formulario 1", [])
        cli = data_dict.get("Clientes_Frecuentes", [])
        asistencia = data_dict.get("Asistencia", [])
        mensualistas = data_dict.get("Base_Mensualistas", [])
        stock = data_dict.get("Control_Stock", [])
        efectivo_data = data_dict.get("Efectivo_Caja", [])
        auditoria = data_dict.get("Auditoria_LPR", [])
        eventos = data_dict.get("Eventos", [])
        historial = data_dict.get("Historial_Tickets", [])
        lista_inv = data_dict.get("Lista de invitados", data_dict.get("Lista_Invitados", []))
        
        empleados = [r[0] for r in conf[1:] if len(r)>0 and r[0]]
        tarifas = {str(r[0]).strip(): {"Auto": int(r[1]) if len(r)>1 and str(r[1]).strip().isdigit() else 0, 
                                       "Camioneta": int(r[2]) if len(r)>2 and str(r[2]).strip().isdigit() else 0} 
                   for r in tarifas_raw[1:] if len(r) > 0 and r[0].strip()}
        extras = {r[0]: int(r[1]) for r in extras_raw[1:] if len(r)>0 and r[0]}
        
        st.session_state.ultimo_error_db = ""
        return empleados, tarifas, extras, reg, q_data, cli, asistencia, mensualistas, stock, efectivo_data, auditoria, eventos, historial, lista_inv
    except Exception as e:
        st.session_state.ultimo_error_db = str(e)
        return [], {}, {}, [], [], [], [], [], [], [], [], [], [], []

resultado_datos = obtener_datos()

if not resultado_datos[0] and st.session_state.rol != "Admin":
    error_detectado = st.session_state.get("ultimo_error_db", "")
    st.markdown("### 📡 Enlace pausado por seguridad")
    if "429" in error_detectado or "Quota" in error_detectado or "limit" in error_detectado.lower():
        st.warning("⏱️ **Límite Anti-Spam de Google activado:** Hiciste varias actualizaciones muy rápido. Por favor, **esperá 60 segundos exactos** y luego tocá el botón de reconectar.")
    else:
        st.warning("🔄 Hubo un pequeño corte de conexión con el Excel de Google. Esperá unos segundos y reintentá.")
        
    if st.button("🔄 Reconectar Ahora"):
        obtener_datos.clear()
        st.rerun()
    st.stop()

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, efectivo_data, auditoria_data, eventos_data, historial_data, lista_invitados_data = resultado_datos

hoy_str_global = hora_actual_uy().split()[0]
val_hoy_global = [q for q in q_data[1:] if len(q) >= 4 and str(q[0]).startswith(hoy_str_global)]

if "cant_val_hoy" not in st.session_state:
    st.session_state.cant_val_hoy = len(val_hoy_global)
elif len(val_hoy_global) > st.session_state.cant_val_hoy:
    if st.session_state.rol == "Valet" or st.session_state.rol == "Admin":
        st.toast("🚨 ¡NUEVA VALIDACIÓN DE LOCAL RECIBIDA!", icon="🔔")
    st.session_state.cant_val_hoy = len(val_hoy_global)

datos_mensualistas_map = {}
patentes_mensualistas = []
try:
    for m in mensualistas_data[1:]:
        if len(m) > 0 and str(m[0]).strip():
            pat_m = str(m[0]).strip().upper().replace("-", "").replace(" ", "")
            patentes_mensualistas.append(pat_m)
            nom_m = str(m[1]).strip() if len(m) > 1 and str(m[1]).strip() else "Mensualista/Autorizado"
            estado_m = str(m[2]).strip().upper() if len(m) > 2 else ""
            tel_m = str(m[3]).strip() if len(m) > 3 else ""
            bene_m = str(m[4]).strip().upper() if len(m) > 4 else ""
            cupos_m = int(str(m[5]).strip()) if len(m) > 5 and str(m[5]).strip().isdigit() else 1
            datos_mensualistas_map[pat_m] = {"nombre": nom_m, "estado": estado_m, "telefono": tel_m, "beneficio": bene_m, "cupos": cupos_m}
except Exception as e:
    pass

emp = st.session_state.usuario
es_admin = st.session_state.rol == "Admin"

ultimo_est_operador = verificar_estado_empleado(emp, asistencia_data)
if st.session_state.local_emp == emp and st.session_state.local_estado != "":
    ultimo_est_operador = st.session_state.local_estado

st.markdown("### 📍 Menú Principal")
opciones_menu = []

if not es_admin and st.session_state.rol == "Valet":
    opciones_menu.append("⏰ Personal")

if (ultimo_est_operador in ["Entrada", "Fichaje"] and st.session_state.rol == "Valet") or es_admin:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🧽 Lavadero", "🍔 Extras", "📤 Salida", "✅ Validaciones"])

if st.session_state.rol and st.session_state.rol.startswith("Local_"):
    opciones_menu.append("✅ Validaciones")

if es_admin:
    opciones_menu.append("📈 Reportes")

if st.session_state.rol:
    opciones_menu.append("📖 Ayuda")

if not opciones_menu:
    st.error("⚠️ No tienes permisos activos o no has marcado tu Entrada. Ve al módulo Personal para habilitar el sistema.")
    opciones_menu = ["⏰ Personal", "📖 Ayuda"] 

menu = st.radio("Navegación:", opciones_menu, horizontal=True, label_visibility="collapsed")
st.divider()

if st.session_state.rol == "Valet" and menu != "📖 Ayuda":
    if ultimo_est_operador == "Salida":
        st.error("🚨 **¡ALERTA MÁXIMA! NO HAS REGISTRADO TU ENTRADA.**\n\nDebes ir obligatoriamente a la pestaña **'Personal'** y hacer tu inventario inicial. Si no lo hacés, estás operando de forma incorrecta.")
    elif ultimo_est_operador == "Fichaje":
        st.warning("⚠️ **¡ATENCIÓN! ENTRADA INCOMPLETA.**\n\nTocaste el botón de entrar pero no completaste la plata y el stock. Ve a **'Personal'** y finalizá el inventario.")
    elif ultimo_est_operador == "Entrada":
        st.info("⏰ **RECORDATORIO CONSTANTE:**\n\nAl finalizar tu turno, **¡NO TE VAYAS SIN MARCAR TU SALIDA!** Debes ir a la pestaña **'Personal'** y declarar la caja para cerrar correctamente.")

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
        pass

# ------------------------------------------
# INGRESO
# ------------------------------------------
if menu == "📥 Ingreso":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Registro de Ingreso")
    if c_head2.button("🔄 Refrescar Datos", key="ref_ing"):
        obtener_datos.clear()
        st.rerun()

    k = st.session_state.form_key_count
    hoy_str = hora_actual_uy().split()[0]
    mes_actual_str = hora_actual_uy()[:7]
    
    invitados_hoy_map = {}
    nombres_invitados_map = {}
    patentes_invitados = []
    
    for row in lista_invitados_data[1:]:
        if len(row) >= 3:
            fecha_inv = str(row[0]).strip()
            if fecha_inv == hoy_str:
                evt_inv = str(row[1]).strip()
                pat_inv = str(row[2]).strip().upper().replace("-", "").replace(" ", "")
                if pat_inv:
                    invitados_hoy_map[pat_inv] = evt_inv
                    patentes_invitados.append(pat_inv)
                    if len(row) > 3 and str(row[3]).strip():
                        nombres_invitados_map[pat_inv] = str(row[3]).strip()
    
    patentes_camara = [str(r[0]).strip().upper() for r in auditoria_data[1:] if len(r) > 0 and r[0] not in ["", "SIN_PATENTE", "ERROR_TOKEN", "ERROR_FATAL"]]
    patentes_frec = [str(rc[0]).strip().upper().replace("-", "").replace(" ", "") for rc in clientes[1:] if len(rc) > 0 and str(rc[0]).strip()]
    
    patentes_unificadas = sorted(list(set(patentes_camara + patentes_frec + patentes_mensualistas + patentes_invitados)))

    st.markdown("**🔍 Identificar Vehículo (Use solo una línea):**")
    sel_pat_cam = st.selectbox("📷 1. Seleccionar Patente (Cámara, Frecuentes y Mensualistas):", [""] + patentes_unificadas, key=f"cam_{k}")
    pat_manual = st.text_input("✍️ 2. Escribir Manualmente (Auto Nuevo):", key=f"man_{k}")
    
    if pat_manual.strip(): pat_final = pat_manual.strip()
    elif sel_pat_cam: pat_final = sel_pat_cam
    else: pat_final = ""
        
    pat_final = pat_final.upper().replace("-", "").replace(" ", "")
    st.divider()

    nombre_sug, cel_sug = "", "598"
    es_deudor = False
    excede_cupo_mensual = False
    lavados_usados = 0
    lavados_permitidos = 0
    
    if pat_final:
        for rc in clientes[1:]:
            if len(rc) > 2 and str(rc[0]).upper().replace("-", "").replace(" ", "") == pat_final:
                nombre_sug, cel_sug = str(rc[1]).strip(), str(rc[2]).strip()
                break
                
        if pat_final in nombres_invitados_map and not nombre_sug:
            nombre_sug = nombres_invitados_map[pat_final]
                
        if pat_final in datos_mensualistas_map:
            datos_m = datos_mensualistas_map[pat_final]
            nombre_sug = datos_m["nombre"]
            if datos_m["telefono"]:
                cel_sug = datos_m["telefono"]
            
            estado_visual = datos_m["estado"]
            cupos_cliente = datos_m["cupos"]
            autos_en_playa = 0
            
            for r_act in reg[1:]:
                if len(r_act) > 3 and (not r_act[3] or str(r_act[3]).lower() == "nan") and str(r_act[0]).strip().upper() != "EXTRA":
                    pat_activa = str(r_act[1]).strip().upper()
                    if pat_activa in datos_mensualistas_map and datos_mensualistas_map[pat_activa]["nombre"] == nombre_sug:
                        autos_en_playa += 1
                        
            if autos_en_playa >= cupos_cliente:
                excede_cupo_mensual = True
                st.error(f"🚨 **¡ATENCIÓN! {nombre_sug} tiene un cupo de {cupos_cliente} vehículo(s) y ya hay {autos_en_playa} adentro.** Este auto que entra DEBERÁ ABONAR ESTADÍA.")
            else:
                if estado_visual == "DEUDOR":
                    es_deudor = True
                elif estado_visual in ["AL DIA", "AUTORIZADO"]:
                    st.success(f"💳 **Vehículo Mensualista ({estado_visual})** registrado a nombre de: {nombre_sug}")
                
            bene = datos_m.get("beneficio", "")
            
            if "LAVADO" in bene:
                if "2 LAVADO" in bene or ("2" in bene and "LAVADO" in bene): lavados_permitidos = 2
                else: lavados_permitidos = 1
                
                for h in historial_data[1:]:
                    if len(h) > 7 and str(h[0]).startswith(mes_actual_str) and str(h[2]).upper().replace("-","").replace(" ","") == pat_final:
                        if "Lavado Beneficio Usado" in str(h[7]):
                            lavados_usados += 1
                            
                if not excede_cupo_mensual:
                    if lavados_usados >= lavados_permitidos:
                        st.warning(f"⚠️ **Atención Lavadero:** Este Mensualista ya usó sus {lavados_permitidos} lavado(s) de este mes. (Aplicar beneficio solo si tiene lavados acumulados de meses anteriores, sino cobrar).")
                    else:
                        st.info(f"💦 **Beneficio Activo:** Cuenta con {lavados_permitidos} lavado(s) al mes. Lleva usados: **{lavados_usados}**.")

    if "ultima_patente" not in st.session_state: st.session_state.ultima_patente = ""
        
    if pat_final != st.session_state.ultima_patente:
        st.session_state.ultima_patente = pat_final
        st.session_state[f"cli_{k}"] = nombre_sug
        st.session_state[f"cel_{k}"] = cel_sug
                
    tkt = st.text_input("🎫 N° Tarjeta PVC (Opcional - Se generará uno automático si se deja en blanco):", key=f"tkt_{k}")
    cli_nom = st.text_input("👤 Nombre y Apellido:", key=f"cli_{k}")
    cel = st.text_input("📱 Celular (Para comprobante / aviso):", key=f"cel_{k}")
    tipo_vehi = st.selectbox("🚙 Tipo de Vehículo:", ["Auto", "Camioneta"], key=f"veh_{k}")
    
    st.markdown("---")
    solicita_lavado = st.checkbox("🧽 **¿El cliente solicita servicio de Lavado ahora?**", key=f"wash_{k}")
    st.markdown("---")

    eventos_hoy = []
    cupos_evento = {}
    for ev in eventos_data[1:]:
        if len(ev) >= 3 and str(ev[0]).strip() == hoy_str:
            nombre_ev = str(ev[1]).strip()
            eventos_hoy.append(nombre_ev)
            try: cupos_evento[nombre_ev] = int(ev[2])
            except: cupos_evento[nombre_ev] = 999

    evento_sel_default_idx = 0
    if eventos_hoy and pat_final in invitados_hoy_map:
        evt_sugerido = invitados_hoy_map[pat_final]
        opciones_evt = [""] + eventos_hoy
        if evt_sugerido in opciones_evt:
            evento_sel_default_idx = opciones_evt.index(evt_sugerido)
            st.success(f"🌟 **¡Invitado VIP en lista!** Asignado automáticamente a: **{evt_sugerido}**")

    evento_sel = ""
    if eventos_hoy:
        evento_sel = st.selectbox("🎟️ Ingreso por Evento (Opcional):", [""] + eventos_hoy, index=evento_sel_default_idx, key=f"evt_{k}")
        if evento_sel:
            autos_en_evento = sum(1 for r in reg[1:] if len(r) > 4 and f"Evento: {evento_sel}" in str(r[4]) and hoy_str in str(r[2]))
            if autos_en_evento >= cupos_evento[evento_sel]:
                st.warning(f"⚠️ ¡ATENCIÓN! Se superó el cupo de {cupos_evento[evento_sel]} lugares para '{evento_sel}'. (Van {autos_en_evento} autos).")
            else:
                st.info(f"✅ Cupo disponible para '{evento_sel}': {autos_en_evento} / {cupos_evento[evento_sel]} autos ingresados.")

    texto_deuda_completo = ""
    if es_deudor and not excede_cupo_mensual:
        st.error(f"🚨 **¡ATENCIÓN! El mensualista {cli_nom or nombre_sug} REGISTRA DEUDA.**")
        nombre_cliente = cli_nom.strip().title() if cli_nom else nombre_sug.strip().title()
        saludo = f"Buen día {nombre_cliente}," if nombre_cliente and nombre_cliente != "Cliente" else "Buen día,"
        texto_deuda_completo = f"{saludo} desde Parking El Globo le informamos que aún no se ha registrado su pago y que el estacionamiento se paga del 1 al 10, aplicándose, a partir de esa fecha un 5% cada 5 días de multa."
        
        cel_pantalla = str(cel).strip()
        if cel_pantalla == "" or cel_pantalla == "598":
            st.warning("⚠️ Escribí el celular del cliente arriba para que el aviso de deuda se adjunte al comprobante.")
    
    if st.button("✅ Registrar Ingreso"):
        cel_clean = str(cel).strip()
        if cel_clean.startswith("0"): cel_clean = cel_clean[1:]
            
        tkt_final = str(tkt).strip()
        
        if not tkt_final: 
            if evento_sel:
                prefijo_evento = f"EV{evento_sel.replace(' ', '').upper()}"
                max_ev = 0
                for r_val in reg[1:]:
                    t_val = str(r_val[0]).strip().upper()
                    if t_val.startswith(prefijo_evento):
                        num_part = t_val.replace(prefijo_evento, "")
                        if num_part.isdigit(): max_ev = max(max_ev, int(num_part))
                for h_val in historial_data[1:]:
                    if len(h_val) > 3:
                        t_val = str(h_val[3]).replace("#", "").strip().upper()
                        if t_val.startswith(prefijo_evento):
                            num_part = t_val.replace(prefijo_evento, "")
                            if num_part.isdigit(): max_ev = max(max_ev, int(num_part))
                
                tkt_final = f"{prefijo_evento}{max_ev + 1}"
            else:
                max_t = 1000 
                for r_val in reg[1:]:
                    t_val = str(r_val[0]).strip().upper()
                    if t_val.startswith("MEN-"):
                        num_part = t_val.replace("MEN-", "")
                        if num_part.isdigit(): max_t = max(max_t, int(num_part))
                    elif t_val.isdigit():
                        max_t = max(max_t, int(t_val))
                for h_val in historial_data[1:]:
                    if len(h_val) > 3:
                        t_val = str(h_val[3]).replace("#", "").strip().upper()
                        if t_val.startswith("MEN-"):
                            num_part = t_val.replace("MEN-", "")
                            if num_part.isdigit(): max_t = max(max_t, int(num_part))
                        elif t_val.isdigit():
                            max_t = max(max_t, int(t_val))
                
                if pat_final in datos_mensualistas_map and not excede_cupo_mensual:
                    tkt_final = f"MEN-{max_t + 1}"
                else:
                    tkt_final = str(max_t + 1)

        if not pat_final:
            st.warning("⚠️ Debes seleccionar o escribir obligatoriamente la Patente.")
        else:
            if any((str(r[0]).strip().lstrip("0") == tkt_final.lstrip("0") or str(r[1]).upper() == pat_final) and (len(r)>3 and (not r[3] or str(r[3]).lower() == "nan")) for r in reg[1:]):
                st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
            else:
                try:
                    h_ing = hora_actual_uy()
                    estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                    if evento_sel:
                        estado_txt = f"Evento: {evento_sel} ({tipo_vehi}) - Op: {emp}"
                        
                    if excede_cupo_mensual:
                        estado_txt += " [EXCEDE CUPO]"
                        
                    if solicita_lavado:
                        estado_txt += " | 🧽 LAVADO PENDIENTE"

                    sh.worksheet("Registro").append_row([tkt_final, pat_final, h_ing, "", estado_txt, "", 0, 0, 0])
                    
                    if cli_nom and not nombre_sug and pat_final not in datos_mensualistas_map:
                        sh.worksheet("Clientes_Frecuentes").append_row([pat_final, cli_nom.strip().title(), cel_clean])
                    
                    if pat_final in datos_mensualistas_map and cel_clean and cel_clean != "598" and not datos_mensualistas_map[pat_final]["telefono"]:
                        for idx, m_row in enumerate(mensualistas_data):
                            if len(m_row) > 0 and str(m_row[0]).strip().upper().replace("-", "").replace(" ", "") == pat_final:
                                sh.worksheet("Base_Mensualistas").update_cell(idx + 1, 4, cel_clean)
                                break
                    
                    msg_ingreso = f"*PARKING EL GLOBO - TICKET INGRESO*\n👤 Cliente: {cli_nom.strip().title() or nombre_sug or 'Frecuente'}\n🚗 Vehículo: {pat_final}\n🎫 Tarjeta: #{tkt_final}\n🕒 Ingreso: {h_ing}"
                    if evento_sel:
                        msg_ingreso += f"\n🎟️ *Invitado Especial:* {evento_sel}"
                    if es_deudor and not excede_cupo_mensual and texto_deuda_completo:
                        msg_ingreso += f"\n\n⚠️ *AVISO DE PAGO PENDIENTE:*\n{texto_deuda_completo}"
                    if solicita_lavado:
                        msg_ingreso += "\n\n🧽 *Servicio de Lavado Solicitado*"
                        
                    msg_ingreso += "\n\n¡Gracias por elegirnos!"
                    
                    st.session_state.exito_msg = f"✅ Ingreso registrado: {pat_final} | Tarjeta #{tkt_final}"
                    st.session_state.exito_wp = f"[📲 Enviar Comprobante por WhatsApp](https://wa.me/{cel_clean}?text={urllib.parse.quote(msg_ingreso)})"
                    
                    st.session_state.form_key_count += 1
                    st.session_state.ultima_patente = "" 
                    obtener_datos.clear() 
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al intentar guardar en la base de datos: {e}")

if st.session_state.exito_msg != "":
    st.success(st.session_state.exito_msg)
    st.markdown(st.session_state.exito_wp, unsafe_allow_html=True)
    st.session_state.exito_msg = ""
    st.session_state.exito_wp = ""

# ------------------------------------------
# ACTIVOS Y CORRECCIÓN DE PATENTES
# ------------------------------------------
elif menu == "📊 Activos":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Vehículos en Playa")
    if c_head2.button("🔄 Refrescar Playa", key="ref_activos"):
        obtener_datos.clear()
        st.rerun()
        
    # NUEVO: TABS PARA VER ACTIVOS O EL HISTORIAL DE HOY
    tab_activos, tab_historial_valet = st.tabs(["🚗 Vehículos Activos", "🏁 Salidas de Hoy (Valets)"])
    
    with tab_activos:
        activos_lista = []
        for r in reversed(reg[1:]):
            if len(r) > 3:
                tkt = str(r[0]).strip()
                h_sal = str(r[3]).strip()
                if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                    pat = str(r[1]).upper()
                    h_ing = r[2]
                    local_val = obtener_validacion_local(pat, tkt, h_ing, q_data)
                    tag_q = f" | 🍽️ **VALIDADO: {local_val.upper()}**" if local_val else ""
                    tag_lavado = " | 🧽 **LAVADO PENDIENTE**" if "LAVADO PENDIENTE" in str(r[4]) else (" | ✨ **LAVADO TERMINADO**" if "LAVADO TERMINADO" in str(r[4]) else "")
                    
                    activos_lista.append(r)
                    st.info(f"🎫 Tarjeta #{tkt} | 🚗 {pat} | 🕒 Ingreso: {h_ing}{tag_q}{tag_lavado}")

        if activos_lista:
            st.divider()
            with st.expander("✏️ Corregir Patente (Error de Tipeo)", expanded=False):
                st.markdown("Si cargaste mal una patente al ingresar, buscala en la lista y escribí la correcta.")
                opciones_corregir = [f"#{r[0]} - Patente actual: {r[1]}" for r in activos_lista]
                auto_a_corregir = st.selectbox("Seleccionar vehículo a corregir:", [""] + opciones_corregir)
                patente_corregida = st.text_input("Escribir la patente CORRECTA:").upper().replace("-", "").replace(" ", "")
                
                if st.button("Guardar Corrección"):
                    if auto_a_corregir and patente_corregida:
                        tkt_corregir = auto_a_corregir.split(" - ")[0].replace("#", "").strip()
                        try:
                            for idx, row in enumerate(reg):
                                if str(row[0]).strip() == tkt_corregir and (len(row) <= 3 or not row[3] or str(row[3]).lower() == "nan"):
                                    sh.worksheet("Registro").update_cell(idx + 1, 2, patente_corregida)
                                    st.success(f"✅ ¡Patente corregida exitosamente a {patente_corregida}!")
                                    obtener_datos.clear()
                                    time.sleep(1)
                                    st.rerun()
                                    break
                        except Exception as e:
                            st.error("Hubo un error al guardar la corrección.")
                    else:
                        st.warning("Seleccioná un auto y escribí la patente nueva.")

    with tab_historial_valet:
        hoy_str = hora_actual_uy().split()[0]
        salidas_hoy = []
        for h in historial_data[1:]:
            if len(h) >= 7 and str(h[0]).startswith(hoy_str):
                hora_salida = str(h[0]).split()[1][:5]
                op = str(h[1])
                pat = str(h[2]).upper()
                tkt = str(h[3])
                try: total_num = float(str(h[6]).replace(',', '.'))
                except: total_num = 0
                salidas_hoy.append({"Hora": hora_salida, "Patente": pat, "Ticket": tkt, "Cobro ($)": f"${total_num:,.0f}", "Valet": op})
        
        if salidas_hoy:
            st.dataframe(pd.DataFrame(salidas_hoy).sort_values("Hora", ascending=False), use_container_width=True)
        else:
            st.info("Aún no hay vehículos retirados en el día de hoy.")

# ------------------------------------------
# LAVADERO
# ------------------------------------------
elif menu == "🧽 Lavadero":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Panel de Lavadero")
    if c_head2.button("🔄 Refrescar", key="ref_lav"):
        obtener_datos.clear()
        st.rerun()
        
    mes_actual_str = hora_actual_uy()[:7]
    autos_para_lavar = []
    autos_terminados = []
    mensualistas_con_lavado = []
    
    for r in reg[1:]:
        if len(r) > 4:
            tkt = str(r[0]).strip()
            pat = str(r[1]).strip().upper()
            h_ing = r[2]
            h_sal = str(r[3]).strip()
            estado = str(r[4])
            
            if tkt.upper() != "EXTRA" and not tkt.startswith("LPR-") and (not h_sal or h_sal.lower() == "nan"):
                if "LAVADO PENDIENTE" in estado: 
                    autos_para_lavar.append(r)
                elif "LAVADO TERMINADO" in estado: 
                    autos_terminados.append(r)
                else:
                    if pat in datos_mensualistas_map:
                        bene = datos_mensualistas_map[pat]["beneficio"].upper()
                        if "LAVADO" in bene:
                            if "2 LAVADO" in bene or ("2" in bene and "LAVADO" in bene): lav_perm = 2
                            else: lav_perm = 1
                            
                            lav_usados = 0
                            for h in historial_data[1:]:
                                if len(h) > 7 and str(h[0]).startswith(mes_actual_str) and str(h[2]).upper().replace("-","").replace(" ","") == pat:
                                    if "Lavado Beneficio Usado" in str(h[7]):
                                        lav_usados += 1
                            
                            if lav_usados < lav_perm:
                                mensualistas_con_lavado.append({
                                    "patente": pat, 
                                    "tkt": tkt, 
                                    "nombre": datos_mensualistas_map[pat]["nombre"], 
                                    "usados": lav_usados, 
                                    "permitidos": lav_perm, 
                                    "ingreso": h_ing,
                                    "estado_txt": estado,
                                    "idx_reg": reg.index(r) 
                                })
                
    st.markdown("### 🔴 Pendientes de Lavado (Solicitados en Puerta)")
    if not autos_para_lavar:
        st.success("¡Excelente! No hay autos esperando lavado.")
    else:
        for auto in autos_para_lavar:
            c1, c2 = st.columns([3, 1])
            tkt = str(auto[0]).strip()
            pat = str(auto[1]).upper()
            
            badge = ""
            if pat in datos_mensualistas_map and "LAVADO" in datos_mensualistas_map[pat]["beneficio"].upper():
                badge = " 🎁 [Mensualista con Beneficio]"
                
            c1.error(f"🚗 **{pat}** {badge} | Tkt #{tkt} | Ingresó: {auto[2].split()[1]}")
            if c2.button("✅ Marcar Terminado", key=f"lav_{tkt}"):
                try:
                    for idx, row in enumerate(reg):
                        if str(row[0]).strip() == tkt and (len(row) <= 3 or not row[3] or str(row[3]).lower() == "nan"):
                            nuevo_estado = str(row[4]).replace(" | 🧽 LAVADO PENDIENTE", " | ✨ LAVADO TERMINADO")
                            sh.worksheet("Registro").update_cell(idx + 1, 5, nuevo_estado)
                            st.toast("¡Lavado marcado como terminado!")
                            obtener_datos.clear()
                            time.sleep(1)
                            st.rerun()
                            break
                except:
                    st.error("Error al actualizar estado.")
                    
    st.markdown("### 🟢 Lavados Terminados en Playa")
    if not autos_terminados:
        st.info("Ningún lavado terminado pendiente de salida.")
    else:
        for auto in autos_terminados:
            st.success(f"✨ **{str(auto[1]).upper()}** | Tkt #{str(auto[0]).strip()} - Listo para entregar.")

    st.markdown("---")
    st.markdown("### 🎁 Mensualistas Estacionados (Con Lavado a Favor)")
    st.markdown("Estos vehículos están en la playa y tienen lavados gratis disponibles este mes. El Valet no los marcó en la puerta, pero podés lavarlos si lo desean.")
    if not mensualistas_con_lavado:
        st.info("No hay mensualistas con lavados a favor estacionados en este momento.")
    else:
        for m in mensualistas_con_lavado:
            c_m1, c_m2 = st.columns([3, 1])
            c_m1.info(f"👤 **{m['nombre']}** | 🚗 **{m['patente']}** (Tkt #{m['tkt']})\n\nDisponibles: **{m['permitidos'] - m['usados']}** (Usó {m['usados']} de {m['permitidos']}) | Ingresó: {m['ingreso'].split()[1]}")
            if c_m2.button("➕ Lavar Ahora", key=f"add_lav_{m['tkt']}"):
                try:
                    nuevo_estado_m = str(m["estado_txt"]) + " | 🧽 LAVADO PENDIENTE"
                    sh.worksheet("Registro").update_cell(m["idx_reg"] + 1, 5, nuevo_estado_m)
                    st.toast(f"Vehículo {m['patente']} agregado a la cola de lavado.")
                    obtener_datos.clear()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error("Error al agregar a la cola.")

# ------------------------------------------
# VALIDACIONES (FORMULARIO Y PANEL)
# ------------------------------------------
elif menu == "✅ Validaciones":
    
    if st.session_state.rol.startswith("Local_") or es_admin:
        st.subheader("Cargar Validación de Local")
        
        if st.session_state.rol == "Local_Quinquela": local_seleccionado = "Quinquela"
        elif st.session_state.rol == "Local_Number18": local_seleccionado = "Number 18"
        else: local_seleccionado = st.selectbox("Seleccionar Local que valida:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
            
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
                        
        def get_sort_key(r):
            val = str(r[0]).strip()
            nums = ''.join(filter(str.isdigit, val))
            return int(nums) if nums else 999999
            
        activos_disponibles = sorted(activos_disponibles, key=get_sort_key)
        opciones_mozo = [f"#{r[0]} - Patente: {r[1].upper()}" for r in activos_disponibles]
        
        with st.expander("➕ Cargar Nueva Validación", expanded=True):
            seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa (Ordenado por Ticket):", [""] + opciones_mozo)
            
            if local_seleccionado in ["Quinquela", "Number 18"]:
                mozo = st.text_input("Nombre del Mozo / Recepción:")
                factura = st.text_input("Últimos 4 dígitos de la factura:", max_chars=4)
            else:
                mozo = "Gerente de Operaciones"
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
                            
                            etiqueta_autoriza = f"Mozo: {mozo}" if local_seleccionado in ["Quinquela", "Number 18"] else f"Autoriza: {mozo}"
                            msg_aviso = urllib.parse.quote(f"⚠️ *NUEVA VALIDACIÓN*\n🚗 Vehículo: {pat_val} (Tkt #{tkt_val})\n🏪 Local: {local_seleccionado}\n👤 {etiqueta_autoriza}")
                            st.markdown("### 📲 Avisar a los Valets por WhatsApp:")
                            st.markdown(f"[➡️ Mandar a Varios Contactos a la vez (Elegir en lista)]({f'https://api.whatsapp.com/send?text={msg_aviso}'})")
                            st.markdown(f"[➡️ Mandar solo al Celular 1]({f'https://wa.me/{TEL_PARKING_1}?text={msg_aviso}'})")
                            st.markdown(f"[➡️ Mandar solo al Celular 2]({f'https://wa.me/{TEL_PARKING_2}?text={msg_aviso}'})")
                            obtener_datos.clear()
                        except Exception as e:
                            st.error(f"Error al conectar con Google Sheets: {e}")
                else:
                    st.error("Selecciona un vehículo de la lista.")

    st.markdown("---")

    if st.session_state.rol == "Valet" or es_admin:
        c_head1, c_head2 = st.columns([3, 1])
        c_head1.subheader("🔔 Historial de Validaciones del Día")
        if c_head2.button("🔄 Refrescar Panel", key="ref_panel_val"):
            obtener_datos.clear()
            st.rerun()
            
        if not val_hoy_global:
            st.info("Aún no hay validaciones registradas por los locales en el día de hoy.")
        else:
            for val in reversed(val_hoy_global):
                try:
                    hora_val = str(val[0]).split()[1][:5]
                    local_v = str(val[5]) if len(val)>5 else "Local"
                    pat_v = str(val[3]).upper()
                    tkt_v = str(val[2]).strip()
                    mozo_v = str(val[1]).strip()
                    etiqueta_historial = f"Mozo: {mozo_v}" if local_v in ["Quinquela", "Number 18"] else f"Autoriza: {mozo_v}"
                    st.success(f"⏰ {hora_val} | 🏪 **{local_v}** | 🚗 Patente: **{pat_v}** (Tkt #{tkt_v}) - {etiqueta_historial}")
                except:
                    pass

# ------------------------------------------
# EXTRAS
# ------------------------------------------
elif menu == "🍔 Extras":
    st.subheader("Carga de Consumos y Extras")
    st.info("ℹ️ IMPORTANTE: Los Lavados se cobran directamente en la sección SALIDA para calcular mejor las promociones.")
    temp_activos = {}
    for r in reg[1:]:
        if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA" and not str(r[0]).startswith("LPR-"):
            temp_activos[r[0].strip()] = r
            
    def get_sort_key(r):
        val = str(r[0]).strip()
        nums = ''.join(filter(str.isdigit, val))
        return int(nums) if nums else 999999
        
    activos = sorted(list(temp_activos.values()), key=get_sort_key)
    opciones_autos = ["🛒 VENTA DIRECTA (Sin Vehículo)"] + [f"#{r[0]} - Patente: {str(r[1]).upper()}" for r in activos]
    
    sel_auto = st.selectbox("Seleccionar vehículo (Ordenado por Ticket):", opciones_autos)
    
    lista_prods = [""] + list(extras.keys())
    prod = st.selectbox("Producto / Servicio extra:", lista_prods)
    cant = st.number_input("Cantidad:", min_value=1, step=1)
    
    if st.button("Registrar Extra"):
        if not prod: st.warning("Seleccione un producto.")
        else:
            fecha_act = hora_actual_uy()
            try:
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
            except Exception as e:
                st.error("Hubo un error cargando el extra. Intente nuevamente.")

# ------------------------------------------
# SALIDA Y COBRO INTELIGENTE
# ------------------------------------------
elif menu == "📤 Salida":
    c_head1, c_head2 = st.columns([3, 1])
    c_head1.subheader("Cómputo de Egreso y Ticket Final")
    if c_head2.button("🔄 Refrescar Datos", key="ref_sal"):
        obtener_datos.clear()
        st.session_state.salida_procesada = False
        st.rerun()

    if st.session_state.salida_procesada:
        st.success("✅ ¡Vehículo retirado y ticket generado con éxito!")
        with st.expander("🔍 Ver comprobante de Egreso", expanded=True): 
            st.code(st.session_state.salida_ticket)
        st.markdown(st.session_state.salida_wp, unsafe_allow_html=True)
        st.divider()
        if st.button("✅ Terminar y Atender Siguiente Vehículo", use_container_width=True):
            st.session_state.salida_procesada = False
            st.rerun()
    
    else:
        mes_actual_str = hora_actual_uy()[:7]
        temp_activos = {}
        for r in reg[1:]:
            if len(r) > 3 and (not r[3] or str(r[3]).lower() == 'nan') and r[0].upper() != "EXTRA" and not str(r[0]).startswith("LPR-"):
                temp_activos[r[0].strip()] = r
                
        def get_sort_key_patente(r):
            return str(r[1]).upper()
            
        activos = sorted(list(temp_activos.values()), key=get_sort_key_patente)
        
        lista_salida_ordenada = [f"🚗 {str(r[1]).upper()} - Tkt: #{r[0]}" for r in activos]
        
        st.markdown("Elegir auto a retirar *(Podés hacer clic y escribir la patente para buscar más rápido)*:")
        sel = st.selectbox("Buscar por Patente:", [""] + lista_salida_ordenada, label_visibility="collapsed")
        
        if sel:
            tkt = sel.split(" - Tkt: #")[1].strip()
            datos = next(r for r in activos if r[0].strip() == tkt)
            patente = str(datos[1]).upper()
            h_ingreso = datos[2]
            
            tipo_vehi = "Auto"
            if len(datos) > 4 and "Camioneta" in str(datos[4]): tipo_vehi = "Camioneta"
            
            estado_txt = str(datos[4]) if len(datos) > 4 else ""
            excede_cupo_flag = "[EXCEDE CUPO]" in estado_txt.upper()
            pidio_lavado_flag = "LAVADO PENDIENTE" in estado_txt.upper() or "LAVADO TERMINADO" in estado_txt.upper()
            
            nombre_cliente_encontrado = "Cliente"
            cel_encontrado = "598"
            
            for c in clientes[1:]:
                if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.replace("-", "").replace(" ", ""):
                    nombre_cliente_encontrado = str(c[1]).strip()
                    cel_encontrado = str(c[2]).strip()
                    break
                    
            beneficio_encontrado = ""
            estado_mensual_encontrado = ""
            lavados_usados = 0
            lavados_permitidos = 0
            
            if patente in datos_mensualistas_map:
                datos_m = datos_mensualistas_map[patente]
                nombre_cliente_encontrado = datos_m["nombre"]
                if datos_m["telefono"]: cel_encontrado = datos_m["telefono"]
                beneficio_encontrado = datos_m["beneficio"]
                estado_mensual_encontrado = datos_m["estado"]
                
                if "LAVADO" in beneficio_encontrado.upper():
                    if "2 LAVADO" in beneficio_encontrado.upper() or ("2" in beneficio_encontrado and "LAVADO" in beneficio_encontrado.upper()): lavados_permitidos = 2
                    else: lavados_permitidos = 1
                    
                    for h in historial_data[1:]:
                        if len(h) > 7 and str(h[0]).startswith(mes_actual_str) and str(h[2]).upper().replace("-","").replace(" ","") == patente:
                            if "Lavado Beneficio Usado" in str(h[7]):
                                lavados_usados += 1
                
            cel_salida = st.text_input("Celular del cliente para WhatsApp:", value=cel_encontrado)
            obs_salida = st.text_input("Observaciones de Salida (Opcional):")
            
            if estado_mensual_encontrado and "LAVADO" in beneficio_encontrado.upper() and not excede_cupo_flag:
                st.info(f"💦 **Este Mensualista cuenta con: {beneficio_encontrado}** (Usados este mes: {lavados_usados} de {lavados_permitidos})")
                
            if pidio_lavado_flag:
                if estado_mensual_encontrado and "LAVADO" in beneficio_encontrado.upper() and not excede_cupo_flag:
                    st.warning("🧽 **¡ATENCIÓN LAVADERO!** Este vehículo se lavó. Como es Mensualista con beneficio, seleccioná abajo si lo **descontás del plan** o si se lo **cobrás**.")
                else:
                    st.error("🧽 **¡ATENCIÓN LAVADERO!** Este vehículo se lavó en esta estadía y NO tiene plan de lavados. **RECORDÁ COBRARLO** seleccionando la opción correcta abajo.")
                    
            opciones_lavado_disponibles = ["Ninguno", "Lavado Exterior", "Lavado Completo", "Promo 2 Horas + Lavado", "Promo 4 Horas + Lavado", "Promo 8 Horas + Lavado"]
            
            if estado_mensual_encontrado and "LAVADO" in beneficio_encontrado.upper() and not excede_cupo_flag:
                opciones_lavado_disponibles.insert(1, "Lavado Incluido (Plan Mensualista)")
                
            opcion_por_defecto = 0
            if pidio_lavado_flag:
                if estado_mensual_encontrado and "LAVADO" in beneficio_encontrado.upper() and not excede_cupo_flag:
                    if lavados_permitidos > lavados_usados:
                        opcion_por_defecto = 1 # Selecciona "Lavado Incluido"
                    else:
                        opcion_por_defecto = 3 # Sugiere "Lavado Completo" para cobrarlo puro
                else:
                    opcion_por_defecto = 2 # Sugiere "Lavado Completo" por defecto para clientes estandar
                    
            lavado_opcion = st.selectbox("🧼 Servicio de Lavado a procesar en esta salida:", opciones_lavado_disponibles, index=opcion_por_defecto)
            
            if lavado_opcion == "Lavado Incluido (Plan Mensualista)" and lavados_usados >= lavados_permitidos:
                st.warning("⚠️ **Nota:** El sistema registra que ya gastó su cupo de este mes. Se está aplicando el lavado gratis asumiendo que tiene uno ACUMULADO de un mes anterior.")
            
            if st.button("Calcular y Generar Salida"):
                h_salida = hora_actual_uy()
                ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
                mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
                local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
                
                es_evento = "Evento:" in estado_txt
                nombre_evento_salida = ""
                monto_excedente_local = 0
                
                if es_evento:
                    nombre_evento_salida = estado_txt.split("Evento: ")[1].split(" (")[0].replace(" [EXCEDE CUPO]", "").strip()
                    hora_fin_str = ""
                    fecha_ev = ""
                    for ev in eventos_data[1:]:
                        if len(ev) >= 4 and str(ev[1]).strip() == nombre_evento_salida:
                            fecha_ev = str(ev[0]).strip()
                            hora_fin_str = str(ev[3]).strip()
                            break
                    
                    if hora_fin_str:
                        try:
                            ev_fecha_dt = datetime.strptime(fecha_ev, "%Y-%m-%d")
                            h_m = hora_fin_str.split(":")
                            hora_f = int(h_m[0])
                            min_f = int(h_m[1])
                            
                            if hora_f < 10:
                                ev_fecha_dt += timedelta(days=1)
                                
                            ev_fin_dt = ev_fecha_dt.replace(hour=hora_f, minute=min_f)
                            salida_dt = datetime.strptime(h_salida, "%Y-%m-%d %H:%M:%S")
                            
                            if salida_dt > ev_fin_dt:
                                mins_extra = int((salida_dt - ev_fin_dt).total_seconds() / 60)
                                monto_excedente_local = calcular_mejor_precio(mins_extra, tipo_vehi, "Ninguna", tarifas)
                        except:
                            pass
                
                if es_evento:
                    monto_estacionamiento = 0
                    info_desc = f"🎟️ Invitado VIP Evento: {nombre_evento_salida}. Sin costo de estadía."
                    
                elif estado_mensual_encontrado in ["AUTORIZADO", "AL DIA"] and not excede_cupo_flag:
                    monto_lavado = 0
                    if lavado_opcion == "Lavado Exterior":
                        monto_lavado = tarifas.get("Lavado Exterior", {}).get(tipo_vehi, 350)
                    elif lavado_opcion == "Lavado Completo" or "Promo" in lavado_opcion:
                        monto_lavado = tarifas.get("Lavado Completo", {}).get(tipo_vehi, 500)
                        
                    monto_estacionamiento = monto_lavado
                    info_desc = f"✅ Vehículo Mensualista ({nombre_cliente_encontrado}). Parking $0."
                    if monto_lavado > 0: info_desc += f" Se cobra extra: {lavado_opcion.split(' (')[0]}."
                    elif "Incluido" in lavado_opcion: info_desc += " Lavado descontado de su plan mensual."
                    
                elif estado_mensual_encontrado == "DEUDOR" and not excede_cupo_flag:
                    monto_estacionamiento = 0
                    nombre_cliente = nombre_cliente_encontrado.strip().title()
                    saludo = f"Buen día {nombre_cliente}," if nombre_cliente and nombre_cliente != "Cliente" else "Buen día,"
                    texto_deuda_completo = f"{saludo} desde Parking El Globo le informamos que aún no se ha registrado su pago y que el estacionamiento se paga del 1 al 10, aplicándose, a partir de esa fecha un 5% cada 5 días de multa."
                    info_desc = f"🛑 Mensualista con DEUDA ({nombre_cliente_encontrado}). Costo de estadía $0.\n\n⚠️ *AVISO DE PAGO PENDIENTE:*\n{texto_deuda_completo}"
                    
                else:
                    monto_estacionamiento = calcular_mejor_precio(mins, tipo_vehi, local_val, tarifas, lavado_opcion)
                    if local_val in ["Rodrigo Bueno", "Number 18"]: 
                        info_desc = f"Estacionamiento 100% libre por {local_val}."
                    elif local_val == "Quinquela": 
                        info_desc = f"Incluye cortesía de 2.5 hs por {local_val}."
                    else: 
                        if excede_cupo_flag:
                            info_desc = "⚠️ Tarifa cobrada por exceder el cupo simultáneo del plan mensual. "
                        else:
                            info_desc = ""
                        
                        if "Promo" in lavado_opcion: info_desc += "Tarifa de promoción calculada automáticamente."
                        elif lavado_opcion != "Ninguno": info_desc += "Tarifa estándar + Lavado cobrado."
                        else: info_desc += "Tarifa estándar aplicada."
                
                total_extras = float(datos[7]) if len(datos) > 7 and datos[7] and datos[7] != "" else 0
                detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras de kiosco."
                
                obs_salida_final = obs_salida if obs_salida else "-"
                if lavado_opcion != "Ninguno":
                    nom_lavado = lavado_opcion.split(" (")[0]
                    if detalle_extras_txt == "Sin extras de kiosco.": detalle_extras_txt = f"🧼 {nom_lavado}"
                    else: detalle_extras_txt += f" | 🧼 {nom_lavado}"
                    
                    if lavado_opcion == "Lavado Incluido (Plan Mensualista)":
                        obs_salida_final += " | Lavado Beneficio Usado"
                    
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
Estacionamiento y Servicios: ${monto_estacionamiento}
Total Extras (Kiosco): ${total_extras}
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
                    
                    local_val_guardar = f"Evento: {nombre_evento_salida}" if es_evento else (local_val if local_val else "Ninguna")
                    
                    try: ws_h = sh.worksheet("Historial_Tickets")
                    except: 
                        ws_h = sh.add_worksheet(title="Historial_Tickets", rows="1000", cols="10")
                        ws_h.append_row(["Hora", "Op", "Patente", "Ticket", "Parking", "Extras", "Total", "Obs", "Validación", "Excedente_Local"])
                    
                    ws_h.append_row([
                        h_salida, emp, patente, f"#{tkt}", float(monto_estacionamiento), 
                        float(total_extras), float(total_a_pagar), 
                        obs_salida_final.strip(" | -"), 
                        local_val_guardar,
                        float(monto_excedente_local) 
                    ])
                    obtener_datos.clear() 
                    
                    cel_salida_clean = str(cel_salida).strip()
                    if cel_salida_clean.startswith("0"): cel_salida_clean = cel_salida_clean[1:]
                    link_wp = f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_salida_clean}?text={urllib.parse.quote(texto_ticket)})"
                    
                    st.session_state.salida_procesada = True
                    st.session_state.salida_ticket = texto_ticket
                    st.session_state.salida_wp = link_wp
                    st.rerun()
                    
                except Exception as e: 
                    st.error(f"❌ Ocurrió un error al registrar la salida. Intente de nuevo. Detalle: {e}")

# ------------------------------------------
# PERSONAL Y CAJA (INVENTARIOS COLABORATIVOS)
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
            else: st.info("No hay registros recientes.")
        except: st.info("Sin registros.")

    st.divider()

    ultimo_registro_caja = efectivo_data[-1] if len(efectivo_data) > 1 else None
    hab_entrada_rap = False
    hab_salida_rap = False
    usr_caja = ""
    h_caja = ""
    
    if ultimo_registro_caja and len(ultimo_registro_caja) >= 3:
        h_caja = str(ultimo_registro_caja[0])
        usr_caja = str(ultimo_registro_caja[1])
        tipo_caja = str(ultimo_registro_caja[2])
        try:
            dt_caja = datetime.strptime(h_caja, "%Y-%m-%d %H:%M:%S")
            now = datetime.utcnow() - timedelta(hours=3)
            diff_mins = (now - dt_caja).total_seconds() / 60
            
            if tipo_caja == "Entrada" and diff_mins < 180: 
                hab_entrada_rap = True
            elif tipo_caja == "Salida" and diff_mins < 120: 
                hab_salida_rap = True
        except:
            pass

    tab_entrada, tab_salida = st.tabs(["📥 ENTRADA", "📤 SALIDA"])
    
    with tab_entrada:
        if ultimo_est_operador == "Entrada":
            st.info("ℹ️ Ya te encuentras con la **Entrada** registrada y el inventario completado. Debes registrar tu salida al terminar el turno.")
            
        elif ultimo_est_operador == "Fichaje":
            st.success(st.session_state.get('cartel_entrada_msg', "✅ Su hora de entrada inicial ha sido guardada."))
            
            if hab_entrada_rap and usr_caja != emp:
                st.success(f"🤝 **¡Compañerismo!** Tu compañero **{usr_caja}** ya realizó el conteo de la plata y el stock a las {h_caja.split()[1]}. Podés registrar tu entrada sin tener que contarlo de nuevo.")
                if st.button("⚡ Confirmar Entrada Rápida"):
                    if st.session_state.local_estado == "Entrada":
                        st.warning("⚠️ Su entrada ya fue procesada.")
                    else:
                        hora_fichada_final = st.session_state.hora_fichaje_temporal if st.session_state.hora_fichaje_temporal else hora_actual_uy()
                        sh.worksheet("Asistencia").append_row([hora_fichada_final, str(emp), "Entrada", f"Entrada conjunta con {usr_caja}"])
                        st.session_state.local_emp = emp
                        st.session_state.local_estado = "Entrada"
                        st.session_state.cartel_entrada_msg = ""
                        obtener_datos.clear()
                        time.sleep(1)
                        st.rerun()
            else:
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
                        if st.session_state.local_estado == "Entrada":
                            st.warning("⚠️ Su entrada ya fue procesada.")
                        else:
                            try:
                                hora_fichada_final = st.session_state.hora_fichaje_temporal if st.session_state.hora_fichaje_temporal else hora_actual_uy()
                                sh.worksheet("Efectivo_Caja").append_row([hora_fichada_final, str(emp), "Entrada", int(efectivo_caja), f"Obs: {nota_stock}"])
                                
                                filas_stock = []
                                for prod, cant in conteo_stock.items():
                                    filas_stock.append([hora_fichada_final, f"Inv_Entrada_{prod}", int(cant), str(emp), ""])
                                if filas_stock: sh.worksheet("Control_Stock").append_rows(filas_stock)
                                    
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
                except Exception as e: st.error(f"Error al registrar entrada: {e}")

    with tab_salida:
        if ultimo_est_operador == "Salida":
            st.info("ℹ️ No tienes una entrada activa en este momento para registrar salida.")
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU SALIDA** (Realice el inventario de stock y arqueo final).")
            
            if hab_salida_rap and usr_caja != emp:
                st.success(f"🤝 **¡Compañerismo!** Tu compañero **{usr_caja}** ya realizó el recuento de cierre general a las {h_caja.split()[1]}. Podés registrar tu salida directamente.")
                if st.button("⚡ Confirmar Salida Rápida"):
                    if st.session_state.local_estado == "Salida":
                        st.warning("⚠️ Su salida ya fue procesada.")
                    else:
                        hora_fichada = hora_actual_uy()
                        sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", f"Salida conjunta con {usr_caja}"])
                        st.session_state.local_emp = emp
                        st.session_state.local_estado = "Salida"
                        st.session_state.cartel_salida_msg = f"🚪 SALIDA REGISTRADA A LAS {hora_fichada.split()[1]}. (Cierre conjunto con {usr_caja})."
                        obtener_datos.clear()
                        st.rerun()
            else:
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
                        if st.session_state.local_estado == "Salida":
                            st.warning("⚠️ Su salida ya fue procesada.")
                        else:
                            try:
                                hora_fichada = hora_actual_uy()
                                sh.worksheet("Efectivo_Caja").append_row([hora_fichada, str(emp), "Salida", int(efectivo_caja_salida), f"Obs: {nota_salida}"])
                                
                                filas_stock = []
                                for prod, cant in conteo_stock_salida.items():
                                    filas_stock.append([hora_fichada, f"Inv_Salida_{prod}", int(cant), str(emp), ""])
                                if filas_stock: sh.worksheet("Control_Stock").append_rows(filas_stock)
                                
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
elif menu == "📈 Reportes":
    st.subheader("📊 Panel de Ventas, Control y Auditoría")
    st.markdown("👋 ¡Hola **Rodrigo**! Aquí tenés el resumen completo de la operativa de tu estacionamiento.")
    
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
        else: st.info("ℹ️ Aún no hay registros en la pestaña Efectivo_Caja.")
    except Exception as e: st.info("ℹ️ Asegúrate de tener creada la pestaña 'Efectivo_Caja' en tu Google Sheet.")

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
        if patente_camara not in patentes_activas_playa: fugas.append(patente_camara)
            
    if len(autos_camara) == 0: st.info("ℹ️ La cámara aún no ha registrado ingresos en el día de hoy.")
    elif fugas:
        st.error(f"🚨 ATENCIÓN: La cámara detectó {len(set(fugas))} vehículo(s) que ingresaron pero no tienen ticket activo en playa.")
        st.write("Patentes sin registrar:", ", ".join(set(fugas)))
    else: st.success("✅ Perfecto. Todos los vehículos detectados por la cámara tienen su ticket activo correspondiente.")

    st.divider()

    try:
        ws_hist = sh.worksheet("Historial_Tickets")
        datos_hist = ws_hist.get_all_values()
        if len(datos_hist) > 1 and "Total" in datos_hist[0]:
            headers = datos_hist[0]
            max_cols = max(len(row) for row in datos_hist)
            while len(headers) < max_cols:
                headers.append(f"Col_{len(headers)+1}")
                
            df = pd.DataFrame(datos_hist[1:], columns=headers)
            df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
            df['Parking'] = pd.to_numeric(df['Parking'], errors='coerce').fillna(0)
            df['Extras'] = pd.to_numeric(df['Extras'], errors='coerce').fillna(0)
            df['Hora'] = pd.to_datetime(df['Hora'], errors='coerce')
            
            if len(df.columns) > 9:
                df['Excedente_Local'] = pd.to_numeric(df.iloc[:, 9], errors='coerce').fillna(0)
            else:
                df['Excedente_Local'] = 0
            
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
                    ev_name = str(r_ev[4]).split("Evento: ")[1].split(" (")[0].replace(" [EXCEDE CUPO]", "").strip()
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
                    
            df_excedentes = df[df['Excedente_Local'] > 0]
            if not df_excedentes.empty:
                st.markdown("#### 💰 Excedentes de Horario a Facturar a Locales")
                df_exc_grouped = df_excedentes.groupby('Validación')['Excedente_Local'].sum().reset_index()
                df_exc_grouped.columns = ['Evento / Local', 'Monto a Facturar ($)']
                df_exc_grouped['Evento / Local'] = df_exc_grouped['Evento / Local'].str.replace("Evento: ", "")
                st.dataframe(df_exc_grouped.sort_values(by='Monto a Facturar ($)', ascending=False), use_container_width=True)
            
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

# ------------------------------------------
# MANUAL Y AYUDA INTERACTIVA
# ------------------------------------------
elif menu == "📖 Ayuda":
    st.subheader("📖 Manual de Operaciones - FlowPark VIP")
    
    st.markdown("""
    Este manual explica el funcionamiento del estacionamiento, los roles de cada integrante y los procedimientos obligatorios.
    
    ---
    
    ### 👥 1. PERFILES DE USUARIO
    El sistema detecta automáticamente tu rol según el PIN de 4 dígitos:
    *   **🛡️ Administrador (Admin):** Tiene acceso total. Puede ver la pestaña **📈 Reportes** (Recaudación, cobros a locales, auditoría de cámaras y deudas).
    *   **🚗 Valet:** Perfil operativo. Tiene acceso a Personal, Ingreso, Activos, Lavadero, Extras, Validaciones y Salida.
    *   **🏪 Local (Quinquela / Number 18):** Solo ven la pantalla de **✅ Validaciones** para aplicar descuentos.
    
    ---
    
    ### ⏰ 2. MÓDULO PERSONAL: FICHAJE Y CAJA (🚨 SÚPER IMPORTANTE 🚨)
    **Todo Valet TIENE LA OBLIGACIÓN de utilizar este módulo al llegar y al irse.**
    *   **📥 Al Iniciar el Turno (ENTRADA):** Ir a la pestaña **⏰ Personal**, ingresar el dinero físico de la gaveta y el stock inicial. Hacer clic en "Confirmar Inventario". **Si no lo haces, la app mostrará un cartel ROJO.**
    *   **📤 Al Finalizar el Turno (SALIDA):** Ir nuevamente a **⏰ Personal**. Ingresar el recuento final de billetes y productos. Tocar "Registrar Salida Oficial".
    *   **⚡ Fichajes Rápidos:** Si llegás a trabajar o te vas al mismo tiempo que otro compañero, ¡no tienen que contar el stock dos veces! El que lo hace primero guarda el registro de la caja, y a vos te aparecerá un botón de **Entrada Rápida / Salida Rápida** para fichar tu horario en un segundo.
    
    ---
    
    ### 🎫 3. IDENTIFICACIÓN VISUAL (TICKETS Y PATENTES)
    El sistema asigna letras al número de ticket (tarjeta) para reconocer clientes rápidamente:
    *   **`MEN-`** Mensualistas y Autorizados (Ej: *MEN-1051*).
    *   **`EV[Nombre]`** Invitados a un Evento VIP (Ej: *EVSEDAL1*).
    *   **Solo Números:** Cliente Estándar (Ej: *1052*).
    
    ---
    
    ### 🏢 4. CLIENTES MENSUALIZADOS Y AUTORIZADOS
    Al tipear la patente, la app muestra un aviso de color:
    *   **🟢 Al Día / Autorizado:** El auto pasa directo. Cobro en la salida: $0.
    *   **🔴 Cliente Deudor:** Alerta roja en pantalla. Al salir se le cobra $0 en caja, pero el sistema le enviará por WhatsApp un **Aviso de Deuda**.
    *   **🚨 Control de Cupos (Límite de autos):** Si una persona paga 1 cochera pero registró 2 patentes. El primer auto pasa gratis. Si llega el segundo auto, el sistema alerta: *"Ya hay 1 auto adentro. Este vehículo DEBE ABONAR ESTADÍA"*.
    
    ---
    
    ### 🧽 5. MÓDULO DE LAVADERO INTEGRADO
    *   **El Ingreso:** El Valet debe preguntar si desea lavado y marcar la casilla `🧽 Solicita Lavado`.
    *   **Control Inteligente de Mensualistas:** Si el mensualista tiene "1 Lavado" incluido por mes y ya lo gastó, la app avisa: *"Ya gastó su cupo del mes"*. Podés usar uno acumulado si tiene, o cobrarlo.
    *   **Panel de Lavadero:** En la pestaña **🧽 Lavadero**, los chicos ven qué autos lavar. También les avisa si hay un Mensualista con lavados gratis en la playa para que vayan a ofrecerle. Cuando terminan, tocan "Marcar Terminado".
    *   **Salida (Cobro):** El Valet selecciona qué lavado le hizo. La app decide si lo descuenta del plan mensual o si se lo cobra aplicando promos.
    
    ---
    
    ### 🎉 6. EVENTOS VIP Y LISTA DE INVITADOS
    *   **Auto-Completado:** Escribí la patente. Si está en la lista de hoy, el sistema llena el nombre y selecciona el evento solo.
    *   **Control de Cupo:** Si el evento contrató 20 lugares y llega el 21, la app avisa el exceso de cupo.
    *   **El Reloj Invisible:** A los invitados VIP **nunca se les cobra dinero** ($0). Pero si el evento terminaba a las 03:00 AM y retiran el auto a las 10:00 AM, el sistema factura esas horas extras al Organizador del evento internamente.
    
    ---
    
    ### ✏️ 7. CORRECCIÓN DE PATENTES (ERRORES DE TIPEO)
    Si escribiste mal una patente (ej: `ABC124` en vez de `ABC123`):
    1. Ir a la pestaña **📊 Activos**.
    2. Bajar hasta el panel **"✏️ Corregir Patente"**.
    3. Seleccionar el auto mal cargado y escribir la patente correcta.
    
    ---
    
    ### 🗺️ 8. DIAGRAMA OPERATIVO DEL VALET
    """)
    
    st.code("""
    [ 🔐 Ingresa PIN de 4 Dígitos ]
      │
      ▼
    [ ⏰ Pestaña 'Personal' ] ──► Ficha ENTRADA y cuenta la caja inicial.
      │
      ├─────────────────────────────────────────────────┐
      │                                                 │
    [ 📥 INGRESO ]                                      [ 🧽 LAVADERO ] 
      │                                                 │
      ├─ Escribe Patente                                ├─ Revisa autos pendientes
      ├─ ¿Es Mensualista? ──► Revisa Deuda/Cupos        ├─ Revisa Mensualistas estacionados
      ├─ ¿Es Evento VIP?  ──► Autocompleta datos        ├─ Lava el auto
      ├─ ¿Pide Lavado?    ──► Tilda la casilla          ├─ Toca "Marcar Terminado"
      ▼                                                 │
    [ Envía Ticket WP ]                                 │
      │                                                 │
      ├─────────────────────────────────────────────────┘
      │
    [ 📤 SALIDA Y COBRO ]
      │
      ├─ Escribe la Patente para buscar fácil
      ├─ Agrega Extras (kiosco) o tipo de Lavado
      ├─ Cobra (O pasa gratis si es VIP/Mensualista)
      ▼
    [ Envía Comprobante de Pago WP y toca TERMINAR ]
      │
      ▼
    [ ⏰ Pestaña 'Personal' ] ──► Ficha SALIDA y cuenta la caja final.
    """, language="text")
