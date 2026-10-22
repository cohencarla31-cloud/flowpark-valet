import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import time
import math

# ==========================================
# CONFIGURACIÓN DE HORARIOS SEMANALES (En horas)
# 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado, 6=Domingo
# ==========================================
HORARIO_SEMANAL = {
    "John Casavieja": {0: 8.5, 1: 8.5, 2: 8.5, 3: 8.5, 4: 8.5, 5: 0.0, 6: 0.0},
    "Rodrigo Golarte": {0: 8.5, 1: 8.5, 2: 8.5, 3: 8.5, 4: 8.5, 5: 0.0, 6: 0.0},
    "Andres Quintana": {0: 5.0, 1: 4.0, 2: 9.0, 3: 4.0, 4: 5.0, 5: 8.0, 6: 0.0},
    "Lucas Tuzio": {0: 4.0, 1: 5.0, 2: 0.0, 3: 5.0, 4: 4.0, 5: 5.0, 6: 5.0}
}
# ==========================================

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

# NÚMEROS DE LA RAMPA
TEL_PARKING_1 = "59897818770" 
TEL_PARKING_2 = "59896185562" 

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
    try: ingreso_dt = pd.to_datetime(hora_ingreso_str)
    except: return None
    
    pat_clean = str(patente).upper().replace("-", "").replace(" ", "")
    tkt_clean = str(tkt).strip().lstrip("0")
    
    for q in reversed(q_records): 
        if len(q) < 3: continue 
        
        q_time_str = str(q[0]).strip()
        q_tkt = str(q[2]).strip().lstrip("0") if len(q) > 2 else ""
        q_pat = str(q[3]).upper().replace("-", "").replace(" ", "") if len(q) > 3 else ""
        q_local = str(q[5]).strip() if len(q) > 5 else "Quinquela"
        
        try: q_dt = pd.to_datetime(q_time_str)
        except: continue
        
        match_tkt = (q_tkt == tkt_clean) and (tkt_clean != "")
        match_pat = (q_pat == pat_clean) and (pat_clean != "")
        
        if match_tkt or match_pat:
            if q_dt >= (ingreso_dt - timedelta(minutes=5)):
                return q_local
    return None

def calcular_mejor_precio(minutos, tipo_vehi, local_validacion, tarifas, tipo_lavado="Ninguno", tarifa_fija_override=0):
    v_lavado_ext = tarifas.get("Lavado Exterior", {}).get(tipo_vehi, 350)
    v_lavado_comp = tarifas.get("Lavado Completo", {}).get(tipo_vehi, 500)
    p_2h_lavado = tarifas.get("Promo 2 Horas + Lavado", {}).get(tipo_vehi, 600)
    p_4h_lavado = tarifas.get("Promo 4 Horas + Lavado", {}).get(tipo_vehi, 720)
    p_8h_lavado = tarifas.get("Promo 8 Horas + Lavado", {}).get(tipo_vehi, 880)

    if tarifa_fija_override > 0:
        costo_base = tarifa_fija_override
        if tipo_lavado == "Ninguno": return costo_base
        elif "Exterior" in tipo_lavado: return costo_base + v_lavado_ext
        else: return costo_base + v_lavado_comp

    if local_validacion in ["Rodrigo Bueno", "N18", "Quinquela 100%"]:
        if tipo_lavado == "Ninguno": return 0
        elif "Exterior" in tipo_lavado: return v_lavado_ext
        elif "Completo" in tipo_lavado or "Promo" in tipo_lavado: return v_lavado_comp
        else: return 0

    descuento = 180 if local_validacion == "Quinquela" else 0
    m_cobro = max(0, minutos - descuento)

    if m_cobro <= 0 and tipo_lavado == "Ninguno": return 0

    v_hora = tarifas.get("Hora", {}).get(tipo_vehi, 110)
    v_promo4h = tarifas.get("Promo_4h", {}).get(tipo_vehi, 330)
    tarifas_8h = tarifas.get("Promo_8h")
    if not tarifas_8h: tarifas_8h = tarifas.get("Dia_Completo", {})
    v_promo8h = tarifas_8h.get(tipo_vehi, 550)
    v_promo24h = tarifas.get("Promo_24h", {}).get(tipo_vehi, 1300)

    def costo_solo_tiempo(mins):
        if mins <= 0: return 0
        if mins <= 60: return v_hora
        
        bloques_24h = mins // 1440
        restante_24h = mins % 1440
        
        costo = bloques_24h * v_promo24h
        bloques_8h = restante_24h // 480
        restante = restante_24h % 480
        costo += bloques_8h * v_promo8h
        
        fracciones_media = math.ceil(restante / 30)
        if restante <= 240:
            costo_restante = fracciones_media * (v_hora / 2.0)
            costo += min(costo_restante, v_promo4h)
        else:
            frac_encima_de_4 = math.ceil((restante - 240) / 30)
            costo_restante = v_promo4h + frac_encima_de_4 * (v_hora / 2.0)
            costo += min(costo_restante, v_promo8h)
            
        return int(costo)

    costo_base = costo_solo_tiempo(m_cobro)

    if tipo_lavado == "Ninguno": return costo_base
    elif "Exterior" in tipo_lavado: return costo_base + v_lavado_ext
    elif "Completo" in tipo_lavado or "Promo" in tipo_lavado:
        if m_cobro <= 0: return v_lavado_comp
        costo_normal = costo_base + v_lavado_comp
        
        if m_cobro <= 480:
            if m_cobro <= 120: return min(costo_normal, p_2h_lavado)
            elif m_cobro <= 240: return min(costo_normal, p_4h_lavado)
            else: return min(costo_normal, p_8h_lavado)
        else:
            return min(costo_normal, p_8h_lavado + costo_solo_tiempo(m_cobro - 480))
    else: return 0

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
    except Exception as e: return None

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
if "salida_tkt_procesado" not in st.session_state: st.session_state.salida_tkt_procesado = ""

if st.session_state.usuario is None and "pin" in st.query_params:
    pin_q = st.query_params["pin"]
    usuarios_pins = cargar_usuarios_desde_db()
    if usuarios_pins and pin_q in usuarios_pins:
        datos_u = usuarios_pins[pin_q]
        st.session_state.usuario = datos_u["nombre"]
        st.session_state.rol = datos_u["rol"]
        st.session_state.pin_usado = pin_q

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
                st.query_params["pin"] = pin_clean
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
    st.session_state.salida_tkt_procesado = ""
    st.query_params.clear()
    st.rerun()
st.divider()

@st.cache_data(ttl=120, show_spinner=False)
def obtener_datos():
    if not sh: raise Exception("Sin conexión con Google Sheets.")
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
    val_app_data = data_dict.get("Validaciones_App", [])
    cli = data_dict.get("Clientes_Frecuentes", [])
    asistencia = data_dict.get("Asistencia", [])
    mensualistas = data_dict.get("Base_Mensualistas", [])
    stock = data_dict.get("Control_Stock", [])
    efectivo_data = data_dict.get("Efectivo_Caja", [])
    auditoria = data_dict.get("Auditoria_LPR", [])
    eventos = data_dict.get("Eventos", [])
    historial = data_dict.get("Historial_Tickets", [])
    lista_inv = data_dict.get("Lista de invitados", data_dict.get("Lista_Invitados", []))
    anulaciones = data_dict.get("Auditoria_Anulaciones", [])
    
    empleados = [r[0] for r in conf[1:] if len(r)>0 and r[0]]
    
    tarifas = {str(r[0]).strip(): {
        "Auto": int(r[1]) if len(r)>1 and str(r[1]).strip().isdigit() else 0, 
        "Camioneta": int(r[2]) if len(r)>2 and str(r[2]).strip().isdigit() else 0,
        "Moto": int(r[3]) if len(r)>3 and str(r[3]).strip().isdigit() else 0
    } for r in tarifas_raw[1:] if len(r) > 0 and r[0].strip()}
    
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if len(r)>0 and r[0]}
    
    return empleados, tarifas, extras, reg, q_data, cli, asistencia, mensualistas, stock, efectivo_data, auditoria, eventos, historial, lista_inv, extras_raw, val_app_data, anulaciones

try:
    resultado_datos = obtener_datos()
    empleados, tarifas, extras, reg, q_data, clientes, asistencia_data, mensualistas_data, stock_data, efectivo_data, auditoria_data, eventos_data, historial_data, lista_invitados_data, extras_raw, val_app_data, anulaciones_data = resultado_datos
except Exception as e:
    error_detectado = str(e)
    st.markdown("### 📡 Enlace pausado por seguridad")
    if "429" in error_detectado or "Quota" in error_detectado or "limit" in error_detectado.lower():
        st.warning("⏱️ **Límite Anti-Spam de Google activado:** Hiciste varias actualizaciones muy rápido. Por favor, **esperá 60 segundos exactos** y luego tocá el botón de reconectar.")
    else:
        st.error(f"⚠️ Error interno detectado: {error_detectado}")
        st.warning("🔄 Hubo un pequeño corte de conexión con el Excel de Google. Esperá unos segundos y reintentá.")
    if st.button("🔄 Reconectar Ahora"):
        obtener_datos.clear()
        st.rerun()
    st.stop()


hoy_str_global = hora_actual_uy().split()[0]
q_data_rows = q_data[1:] if len(q_data) > 1 else []
val_app_rows = []
if len(val_app_data) > 0:
    primera_celda = str(val_app_data[0][0]).strip()
    if primera_celda.startswith("202"): val_app_rows = val_app_data
    else: val_app_rows = val_app_data[1:] if len(val_app_data) > 1 else []

val_combinadas = q_data_rows + val_app_rows
val_hoy_global = [q for q in val_combinadas if len(q) >= 3 and str(q[0]).startswith(hoy_str_global)]

if "cant_val_hoy" not in st.session_state: st.session_state.cant_val_hoy = len(val_hoy_global)
elif len(val_hoy_global) > st.session_state.cant_val_hoy:
    if st.session_state.rol == "Valet" or st.session_state.rol == "Admin":
        ultimo_local_notif = str(val_hoy_global[-1][5]).upper() if len(val_hoy_global[-1]) > 5 else "UN LOCAL"
        st.toast(f"🚨 ¡NUEVA VALIDACIÓN DE {ultimo_local_notif}!", icon="🔔")
    st.session_state.cant_val_hoy = len(val_hoy_global)

datos_mensualistas_map = {}
patentes_mensualistas = []
try:
    for idx_m, m in enumerate(mensualistas_data):
        if idx_m == 0: continue
        if len(m) > 0 and str(m[0]).strip():
            pat_m = str(m[0]).strip().upper().replace("-", "").replace(" ", "")
            patentes_mensualistas.append(pat_m)
            nom_m = str(m[1]).strip() if len(m) > 1 and str(m[1]).strip() else "Mensualista/Autorizado"
            estado_m = str(m[2]).strip().upper() if len(m) > 2 else ""
            tel_m = str(m[3]).strip() if len(m) > 3 else ""
            bene_m = str(m[4]).strip().upper() if len(m) > 4 else ""
            cupos_m = int(str(m[5]).strip()) if len(m) > 5 and str(m[5]).strip().isdigit() else 1
            comentario_m = str(m[6]).strip() if len(m) > 6 else ""
            acumulados_m = int(str(m[7]).strip()) if len(m) > 7 and str(m[7]).strip().isdigit() else 0
            
            datos_mensualistas_map[pat_m] = {
                "nombre": nom_m, "estado": estado_m, "telefono": tel_m, 
                "beneficio": bene_m, "cupos": cupos_m, "comentario": comentario_m,
                "acumulados": acumulados_m, "fila_excel": idx_m + 1
            }
except Exception as e: pass

emp = st.session_state.usuario
es_admin = st.session_state.rol == "Admin"

ultimo_est_operador = verificar_estado_empleado(emp, asistencia_data)
if st.session_state.local_emp == emp and st.session_state.local_estado != "":
    ultimo_est_operador = st.session_state.local_estado

st.markdown("### 📍 Menú Principal")
opciones_menu = []
if not es_admin and st.session_state.rol == "Valet": opciones_menu.append("⏰ Personal")
if (ultimo_est_operador in ["Entrada", "Fichaje"] and st.session_state.rol == "Valet") or es_admin:
    opciones_menu.extend(["📥 Ingreso", "📊 Activos", "🧽 Lavadero", "🍔 Extras", "📤 Salida", "✅ Validaciones"])
if st.session_state.rol and st.session_state.rol.startswith("Local_"): opciones_menu.append("✅ Validaciones")
if es_admin: opciones_menu.append("📈 Reportes")
if st.session_state.rol: opciones_menu.append("📖 Ayuda")

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
                vendidos_actuales = float(r[4]) if len(r)>4 and str(r[4]).strip() != "" else 0
                stock_inicial = float(r[2]) if len(r)>2 and str(r[2]).strip() != "" else 0
                compras = float(r[3]) if len(r)>3 and str(r[3]).strip() != "" else 0
                
                nuevo_vendidos = vendidos_actuales + float(cantidad_vendida)
                nuevo_stock = stock_inicial + compras - nuevo_vendidos
                
                ws_ex.update_cells([
                    gspread.Cell(row=idx, col=5, value=nuevo_vendidos),
                    gspread.Cell(row=idx, col=6, value=nuevo_stock)
                ])
                break
    except Exception as e: pass

def actualizar_arqueo_en_extras(conteo_dict, empleado, fecha_str):
    try:
        ws_ex = sh.worksheet("Extras")
        rows = ws_ex.get_all_values()
        for idx, r in enumerate(rows[1:], start=2):
            if len(r) > 0:
                prod = str(r[0]).strip()
                if prod in conteo_dict:
                    cant_fisica = int(conteo_dict[prod])
                    stock_actual_calc = float(r[5]) if len(r)>5 and str(r[5]).strip() != "" else 0
                    diferencia = cant_fisica - stock_actual_calc
                    ws_ex.update_cells([
                        gspread.Cell(row=idx, col=8, value=cant_fisica),
                        gspread.Cell(row=idx, col=9, value=diferencia),
                        gspread.Cell(row=idx, col=11, value=fecha_str),
                        gspread.Cell(row=idx, col=12, value=empleado)
                    ])
    except Exception as e: pass


if menu == "⏰ Personal":
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

    ahora = datetime.utcnow() - timedelta(hours=3)
    hora_f = ahora.hour + ahora.minute / 60.0

    es_hora_apertura = (6.0 <= hora_f < 13.0) or (14.75 <= hora_f < 22.0)
    es_hora_cierre = (15.5 <= hora_f < 18.0) or (hora_f >= 23.0) or (hora_f < 3.0)

    ya_hicieron_apertura = False
    ya_hicieron_cierre = False
    usr_que_abrio = ""
    usr_que_cerro = ""

    for r in reversed(efectivo_data):
        if len(r) >= 3:
            try:
                dt_caja = datetime.strptime(str(r[0]), "%Y-%m-%d %H:%M:%S")
                diff_horas = (ahora - dt_caja).total_seconds() / 3600.0
                tipo = str(r[2])
                usr = str(r[1])
                
                if diff_horas < 6.0:
                    if tipo == "Entrada" and not ya_hicieron_apertura:
                        ya_hicieron_apertura = True
                        usr_que_abrio = usr
                    elif tipo == "Salida" and not ya_hicieron_cierre:
                        ya_hicieron_cierre = True
                        usr_que_cerro = usr
            except:
                pass

    tab_entrada, tab_salida = st.tabs(["📥 ENTRADA", "📤 SALIDA"])
    
    with tab_entrada:
        if ultimo_est_operador == "Entrada":
            st.info("ℹ️ Ya te encuentras con la **Entrada** registrada y tu horario activado. Debes registrar tu salida al terminar el turno.")
            
        elif ultimo_est_operador == "Fichaje":
            if es_hora_apertura:
                if ya_hicieron_apertura and usr_que_abrio != emp:
                    st.success(f"🤝 **¡Turno Abierto!** Tu compañero **{usr_que_abrio}** ya realizó el arqueo de inicio de este turno. Podés registrar tu entrada directamente.")
                    if st.button("⚡ Registrar Entrada Rápida", use_container_width=True):
                        if st.session_state.local_estado == "Entrada":
                            st.warning("⚠️ Su entrada ya fue procesada.")
                        else:
                            hora_fichada_final = st.session_state.hora_fichaje_temporal if st.session_state.hora_fichaje_temporal else hora_actual_uy()
                            sh.worksheet("Asistencia").append_row([hora_fichada_final, str(emp), "Entrada", f"Entrada conjunta con {usr_que_abrio}"])
                            st.session_state.local_emp = emp
                            st.session_state.local_estado = "Entrada"
                            st.session_state.cartel_entrada_msg = ""
                            obtener_datos.clear()
                            time.sleep(1)
                            st.rerun()
                else:
                    st.warning("📝 **Apertura de Turno**\nSos el primero del turno. Es obligatorio realizar el arqueo de caja y stock.")
                    with st.form("form_inventario_entrada"):
                        st.markdown("### 📝 Arqueo de Entrada")
                        efectivo_caja = st.number_input("💵 Efectivo inicial en gaveta:", min_value=0, value=0, step=50)
                        
                        st.markdown("📝 **Inventario inicial de productos:**")
                        conteo_stock = {}
                        for prod_nombre in list(extras.keys()):
                            if "lavado" not in prod_nombre.lower():
                                conteo_stock[prod_nombre] = st.number_input(f"Stock físico [{prod_nombre}]:", min_value=0, value=0, step=1)
                            
                        nota_stock = st.text_input("Observaciones (Opcional):")
                        submit_entrada = st.form_submit_button("✅ Confirmar Inventario de Turno")
                        
                        if submit_entrada:
                            if st.session_state.local_estado == "Entrada":
                                st.warning("⚠️ Su entrada ya fue procesada.")
                            else:
                                try:
                                    hora_fichada_final = st.session_state.hora_fichaje_temporal if st.session_state.hora_fichaje_temporal else hora_actual_uy()
                                    sh.worksheet("Efectivo_Caja").append_row([hora_fichada_final, str(emp), "Entrada", int(efectivo_caja), f"Obs: {nota_stock}"])
                                    
                                    filas_stock = []
                                    for prod, cant in conteo_stock.items():
                                        filas_stock.append([hora_fichada_final, f"Inv_Entrada_{prod}", int(cant), str(emp), "", 0, 0, hora_fichada_final.split()[0]])
                                    if filas_stock: sh.worksheet("Control_Stock").append_rows(filas_stock)
                                    
                                    actualizar_arqueo_en_extras(conteo_stock, str(emp), hora_fichada_final.split()[0])
                                        
                                    sh.worksheet("Asistencia").append_row([hora_fichada_final, str(emp), "Entrada", f"Caja Inicial: ${efectivo_caja}"])
                                    
                                    st.session_state.local_emp = emp
                                    st.session_state.local_estado = "Entrada"
                                    st.session_state.cartel_entrada_msg = ""
                                    obtener_datos.clear()
                                    st.success(f"✅ ¡Su entrada ya quedó registrada correctamente a las {hora_fichada_final} luego de realizar el inventario!")
                                except Exception as e: st.error(f"Error al guardar inventario: {e}")
            else:
                st.info("⚡ **Horario de Refuerzo / Apoyo**\nEstás ingresando en un horario intermedio (fuera de las aperturas principales). No es necesario realizar arqueo.")
                if st.button("⚡ Registrar Entrada (Sin Arqueo)", use_container_width=True):
                    if st.session_state.local_estado == "Entrada":
                        st.warning("⚠️ Su entrada ya fue procesada.")
                    else:
                        hora_fichada_final = st.session_state.hora_fichaje_temporal if st.session_state.hora_fichaje_temporal else hora_actual_uy()
                        sh.worksheet("Asistencia").append_row([hora_fichada_final, str(emp), "Entrada", "Ingreso de Refuerzo / Apoyo"])
                        st.session_state.local_emp = emp
                        st.session_state.local_estado = "Entrada"
                        st.session_state.cartel_entrada_msg = ""
                        obtener_datos.clear()
                        time.sleep(1)
                        st.rerun()
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU ENTRADA!**")
            if st.button("⏰ Iniciar Fichaje de Entrada"):
                try:
                    hora_fichada = hora_actual_uy()
                    sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Fichaje", "Fichado inicial esperando proceso"])
                    st.session_state.hora_fichaje_temporal = hora_fichada
                    st.session_state.local_emp = emp
                    st.session_state.local_estado = "Fichaje"
                    st.session_state.cartel_entrada_msg = f"✅ Su entrada se consignó correctamente a las {hora_fichada}. Pero para que quede registrada de manera definitiva deberá completarla debajo."
                    obtener_datos.clear()
                    st.rerun()
                except Exception as e: st.error(f"Error al registrar entrada: {e}")

    with tab_salida:
        if ultimo_est_operador == "Salida":
            st.info("ℹ️ No tienes una entrada activa en este momento para registrar salida.")
        else:
            st.warning("⚠️ **RECUERDE REGISTRAR SU SALIDA**")
            
            if es_hora_cierre:
                if ya_hicieron_cierre and usr_que_cerro != emp:
                    st.success(f"🤝 **¡Turno Cerrado!** Tu compañero **{usr_que_cerro}** ya realizó el arqueo de cierre general. Podés registrar tu salida directamente.")
                    if st.button("⚡ Registrar Salida Rápida", use_container_width=True):
                        if st.session_state.local_estado == "Salida":
                            st.warning("⚠️ Su salida ya fue procesada.")
                        else:
                            hora_fichada = hora_actual_uy()
                            sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", f"Salida conjunta con {usr_que_cerro}"])
                            st.session_state.local_emp = emp
                            st.session_state.local_estado = "Salida"
                            st.session_state.cartel_salida_msg = f"🚪 SALIDA REGISTRADA A LAS {hora_fichada.split()[1]}. (Cierre conjunto con {usr_que_cerro})."
                            obtener_datos.clear()
                            st.rerun()
                else:
                    st.warning("📝 **Cierre de Turno**\nSos el encargado de realizar el recuento de caja y stock para cerrar este turno.")
                    with st.form("form_inventario_salida"):
                        st.markdown("### 📤 Arqueo Final")
                        efectivo_caja_salida = st.number_input("💵 Efectivo final en gaveta:", min_value=0, value=0, step=50)
                        
                        st.markdown("📝 **Inventario final de productos:**")
                        conteo_stock_salida = {}
                        for prod_nombre in list(extras.keys()):
                            if "lavado" not in prod_nombre.lower():
                                conteo_stock_salida[prod_nombre] = st.number_input(f"Stock físico final [{prod_nombre}]:", min_value=0, value=0, step=1)
                            
                        nota_salida = st.text_input("Observaciones de Cierre (Opcional):")
                        submit_salida = st.form_submit_button("🚪 Registrar Cierre Oficial")
                        
                        if submit_salida:
                            if st.session_state.local_estado == "Salida":
                                st.warning("⚠️ Su salida ya fue procesada.")
                            else:
                                try:
                                    hora_fichada = hora_actual_uy()
                                    sh.worksheet("Efectivo_Caja").append_row([hora_fichada, str(emp), "Salida", int(efectivo_caja_salida), f"Obs: {nota_salida}"])
                                    
                                    filas_stock = []
                                    for prod, cant in conteo_stock_salida.items():
                                        filas_stock.append([hora_fichada, f"Inv_Salida_{prod}", int(cant), str(emp), "", 0, 0, hora_fichada.split()[0]])
                                    if filas_stock: sh.worksheet("Control_Stock").append_rows(filas_stock)
                                    
                                    actualizar_arqueo_en_extras(conteo_stock_salida, str(emp), hora_fichada.split()[0])
                                    
                                    sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", f"Caja Cierre: ${efectivo_caja_salida}"])
                                    
                                    st.session_state.local_emp = emp
                                    st.session_state.local_estado = "Salida"
                                    st.session_state.cartel_salida_msg = f"🚪 SU SALIDA FUE REGISTRADA CORRECTAMENTE A LA HORA: {hora_fichada.split()[1]} Y FECHA: {hora_fichada.split()[0]}.\n👤 Empleado: {emp}\n💵 Efectivo Declarado en Gaveta: ${efectivo_caja_salida}"
                                    obtener_datos.clear() 
                                    st.rerun()
                                except Exception as e: st.error(f"Error al registrar salida: {e}")
            else:
                st.info("⚡ **Salida de Refuerzo / Intermedia**\nEstás terminando tu horario de apoyo o intermedio. Tu compañero se encargará del cierre de caja al finalizar el turno principal.")
                if st.button("⚡ Registrar Salida (Sin Arqueo)", use_container_width=True):
                    if st.session_state.local_estado == "Salida":
                        st.warning("⚠️ Su salida ya fue procesada.")
                    else:
                        hora_fichada = hora_actual_uy()
                        sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), "Salida", "Salida de Refuerzo / Apoyo"])
                        st.session_state.local_emp = emp
                        st.session_state.
