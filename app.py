import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN Y DATOS ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

@st.cache_data(ttl=15)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    return [r[0] for r in conf[1:] if r[0]], {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}, {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}, registro, q_data, cli

empleados, tarifas, extras, reg, q_data, clientes = obtener_datos()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
emp = st.selectbox("Empleado:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# 1. INGRESO
if menu == "📥 Ingreso":
    pat = st.text_input("Patente:").upper().replace("-", "").replace(" ", "")
    tkt = st.text_input("N° Tarjeta:")
    cli = st.text_input("Nombre:")
    cel = st.text_input("Celular:", "598")
    if st.button("Registrar"):
        sh.worksheet("Registro").append_row([tkt, pat, hora_actual_uy(), "", f"Ingreso - {emp}", "", f"Cliente: {cli}", ""])
        st.success("✅ Ingresado")

# 2. ACTIVOS
elif menu == "📊 Activos":
    for r in reversed(reg[1:]):
        if not r[3] and r[0].upper() != "EXTRA": st.info(f"🎫 #{r[0]} | 🚗 {r[1]} | 🕒 {r[2]}")

# 3. MÓDULO QUINQUELA (Nuevo Formulario para Mozos)
elif menu == "🔔 Quinquela":
    st.subheader("🍽️ Validación Quinquela (Mozo)")
    
    # Filtramos solo tarjetas activas para el desplegable
    activos = [r[0] for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    
    mozo = st.text_input("Nombre del Mozo:")
    tkt_select = st.selectbox("Elegir Tarjeta en Playa:", [""] + activos)
    pat_q = st.text_input("Patente (Opcional):").upper()
    
    if st.button("Enviar Validación"):
        if mozo and tkt_select:
            sh.worksheet("Respuestas de formulario 1").append_row([hora_actual_uy(), mozo, tkt_select, pat_q])
            st.success("✅ Validación enviada al sistema")
        else: st.error("Faltan datos")

    st.divider()
    st.subheader("Historial de Validaciones")
    for q in reversed(q_data[1:]): st.write(f"🕒 {q[0]} | 🍽️ {q[1]} | 🎫 #{q[2]} | 🚗 {q[3]}")

# 4. EXTRAS
elif menu == "🍾 Extras":
    tkt = st.text_input("Tarjeta:")
    prod = st.selectbox("Extra:", list(extras.keys()))
    if st.button("Sumar"):
        for r in reg[1:]:
            if r[0].strip() == tkt.strip() and not r[3]:
                sh.worksheet("Registro").append_row(["EXTRA", r[1], hora_actual_uy(), "", f"Extra-{prod}", "EXTRA", prod, extras[prod]])
                st.success("✅ Extra cargado")
                break

# 5. SALIDA
elif menu == "📤 Salida":
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir:", [""] + [f"#{r[0]} - {r[1]}" for r in activos])
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "")
        datos = next(r for r in activos if r[0] == tkt)
        cel = st.text_input("Celular:", value="598")
        if st.button("Generar Ticket"):
            pat = datos[1]
            ing = datetime.strptime(datos[2], "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            tiene_q = any(q[2] == tkt for q in q_data[1:]) # Cruza por tarjeta, mucho más seguro
            # ... (cálculo y ticket igual) ...
            sh.worksheet("Registro").update_cell([i for i,r in enumerate(reg,1) if r[0]==tkt and not r[3]][0], 4, hora_actual_uy())
            st.success("✅ Salida registrada.")
