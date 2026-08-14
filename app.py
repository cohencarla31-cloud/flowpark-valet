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

# --- LECTURA OPTIMIZADA ---
@st.cache_data(ttl=20)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], []
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

empleados, tarifas, extras, reg, q_data, clientes = obtener_datos()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- MÓDULO QUINQUELA (Cruce inteligente) ---
if menu == "🔔 Quinquela":
    st.subheader("Estado de Validaciones Quinquela")
    for q in reversed(q_data[1:]):
        pat_q = str(q[3]).upper().replace("-","").replace(" ","")
        tkt_q = str(q[2]).strip()
        
        # Buscar el auto en Registro para ver si existe y su estado
        auto_en_playa = next((r for r in reg[1:] if str(r[1]).upper().replace("-","") == pat_q and not r[3]), None)
        
        estado = "❌ No en playa"
        if auto_en_playa:
            estado = f"🟢 En playa (Tkt #{auto_en_playa[0]})"
            if auto_en_playa[0] != tkt_q:
                estado += " ⚠️ ¡Tarjeta de form no coincide!"
        
        st.success(f"🍽️ {q[1]} | 🚗 {q[3]} | Estado: {estado}")

# --- MÓDULO SALIDA (Con recuperación de celular) ---
elif menu == "📤 Salida":
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir auto:", [""] + [f"#{r[0]} - {r[1]}" for r in activos])
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "")
        datos = next(r for r in activos if r[0] == tkt)
        patente = datos[1]
        
        # Buscar celular en base de datos de clientes
        cel_encontrado = next((c[2] for c in clientes[1:] if c[0].upper().replace("-","") == patente.upper()), "598")
        cel = st.text_input("Celular:", value=cel_encontrado)
        
        if st.button("Generar Ticket"):
            # Lógica Quinquela: busca la última validación de esta patente
            tiene_q = any(q[3].upper().replace("-","") == patente.upper() for q in q_data[1:])
            # ... (cálculo y ticket igual al anterior) ...
            # (Aquí va la lógica de actualización de celda que ya funcionaba)
