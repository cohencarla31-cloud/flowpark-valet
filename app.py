import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- 1. CONEXIÓN Y CACHÉ ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

@st.cache_data(ttl=30)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], []
    # Leemos todo de una vez para evitar error 429
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    quinquela = sh.worksheet("Respuestas de formulario 1").get_all_values()
    clientes = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, registro, quinquela, clientes

empleados, tarifas, extras, reg, q_data, clientes_data = obtener_datos()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

def calcular_mejor_precio(minutos, es_camioneta, tiene_q):
    tipo = "Camioneta" if es_camioneta else "Auto"
    m_cobro = max(0, minutos - (120 if tiene_q else 0))
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    return min((m_cobro // 60 + 1) * hora, promo if m_cobro > 60 else 99999, dia)

# --- 2. INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
emp = st.selectbox("Empleado:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# INGRESO
if menu == "📥 Ingreso":
    pat = st.text_input("Matrícula:", key="in_pat").upper().replace("-", "").replace(" ", "")
    # Autocompletado
    nombre_sug, cel_sug = "", "598"
    for r in clientes_data[1:]:
        if r[0].upper().replace("-", "").replace(" ", "") == pat:
            nombre_sug, cel_sug = r[1], r[2]
    
    tkt = st.text_input("N° Tarjeta:")
    cli = st.text_input("Nombre Cliente:", value=nombre_sug)
    cel = st.text_input("Celular:", value=cel_sug)
    
    if st.button("Registrar"):
        if any((r[0].strip() == tkt.strip() or r[1].upper() == pat) and not r[3] for r in reg[1:]):
            st.error("❌ ¡Auto ya está en playa!")
        else:
            sh.worksheet("Registro").append_row([tkt, pat, hora_actual_uy(), "", f"Ingreso - {emp}", "", f"Cliente: {cli}", ""])
            sh.worksheet("Clientes_Frecuentes").append_row([pat, cli, cel])
            st.success("✅ Ingresado")
            st.code(f"*FLOW PARK*\n🚗 {pat}\n🎫 #{tkt}\n¡Gracias {cli}!")

# ACTIVOS
elif menu == "📊 Activos":
    for r in reversed(reg[1:]):
        if not r[3] and r[0].upper() != "EXTRA": st.info(f"🎫 #{r[0]} | 🚗 {r[1]} | 🕒 {r[2]}")

# QUINQUELA
elif menu == "🔔 Quinquela":
    for q in reversed(q_data[1:]): st.success(f"🕒 {q[0]} | 🍽️ {q[1]} | 🚗 {q[3]} | 🎫 #{q[2]}")

# EXTRAS
elif menu == "🍾 Extras":
    tkt = st.text_input("Tarjeta:")
    prod = st.selectbox("Extra:", list(extras.keys()))
    if st.button("Sumar"):
        for r in reg[1:]:
            if r[0].strip() == tkt.strip() and not r[3]:
                sh.worksheet("Registro").append_row(["EXTRA", r[1], hora_actual_uy(), "", f"Extra-{prod}", "EXTRA", prod, extras[prod]])
                st.success("✅ Extra cargado")
                break

# SALIDA
elif menu == "📤 Salida":
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir auto:", [""] + [f"#{r[0]} - {r[1]}" for r in activos])
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "")
        datos = next(r for r in activos if r[0] == tkt)
        cel = st.text_input("Celular:", value="598")
        if st.button("Generar Ticket"):
            pat, ing = datos[1], datetime.strptime(datos[2], "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            tiene_q = any(q[3].upper().replace("-","") == pat.upper() for q in q_data[1:])
            monto = calcular_mejor_precio(mins, "Camioneta" in datos[4], tiene_q)
            msg = f"*FLOW PARK - EGRESO*\n🚗 {pat}\n⏱️ Estadía: {mins//60}h {mins%60}m\n💰 TOTAL: ${monto}\n\n¡Gracias {datos[6].split('Cliente: ')[-1]}, te esperamos!"
            st.code(msg)
            for i, row in enumerate(reg, start=1):
                if row[0] == tkt and not row[3]:
                    sh.worksheet("Registro").update_cell(i, 4, hora_actual_uy())
                    break
