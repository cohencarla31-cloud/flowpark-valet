import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- LECTURA OPTIMIZADA (Para evitar error 429) ---
@st.cache_data(ttl=30)
def obtener_datos_seguros():
    if not sh: return [], {}, {}, []
    
    # Leemos todo de una vez para minimizar llamadas a la API
    config = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    
    # Procesar empleados (asumiendo que están en col 1)
    empleados = [row[0] for row in config[1:] if row[0]]
    
    # Procesar Tarifas (Servicio, Precio_Auto, Precio_Camioneta)
    tarifas = {row[0]: {"Auto": int(row[1]), "Camioneta": int(row[2])} for row in tarifas_raw[1:] if row[0]}
    
    # Procesar Extras
    extras = {row[0]: int(row[1]) for row in extras_raw[1:] if row[0]}
    
    return empleados, tarifas, extras, registro

empleados, tarifas, extras, registro_raw = obtener_datos_seguros()

# --- LÓGICA TARIFA ---
def calcular_mejor_precio(minutos, es_camioneta, tiene_q):
    tipo = "Camioneta" if es_camioneta else "Auto"
    m_cobro = max(0, minutos - (120 if tiene_q else 0))
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    return min((m_cobro // 60 + 1) * hora, promo if m_cobro > 60 else 99999, dia)

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
empleado = st.selectbox("Empleado:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "📤 Salida"])

if menu == "📥 Ingreso":
    pat = st.text_input("Patente:").upper()
    tkt = st.text_input("N° Tarjeta:")
    if st.button("Ingresar"):
        sh.worksheet("Registro").append_row([tkt, pat, hora_actual_uy(), "", f"Ingreso - {empleado}", "", "", ""])
        st.success("✅ Ingresado")

elif menu == "📊 Activos":
    for row in reversed(registro_raw[1:]):
        if not row[3] and row[0].upper() != "EXTRA": # Si hora_salida (idx 3) está vacía
            st.info(f"🎫 #{row[0]} | 🚗 {row[1]} | 🕒 {row[2]}")

elif menu == "📤 Salida":
    activos = [row for row in registro_raw[1:] if not row[3] and row[0].upper() != "EXTRA"]
    seleccion = st.selectbox("Elegir:", [""] + [f"#{r[0]} - {r[1]}" for r in activos])
    
    if seleccion and st.button("Generar Salida"):
        tkt_buscar = seleccion.split(" - ")[0].replace("#", "")
        for i, row in enumerate(registro_raw, start=1):
            if row[0] == tkt_buscar and not row[3]:
                sh.worksheet("Registro").update_cell(i, 4, hora_actual_uy())
                st.success(f"✅ Salida registrada.")
                break
