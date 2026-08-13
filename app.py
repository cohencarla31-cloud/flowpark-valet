import streamlit as st
import gspread
from datetime import datetime

# Conexión con Google Sheets
creds_dict = st.secrets["gcp_service_account"]
client = gspread.service_account_from_dict(creds_dict)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jknI7amSqutxGT_WAIBNhD0vezFE2AueTEzP7q5Rb1c/edit?gid=0#gid=0"
sh = client.open_by_url(SHEET_URL)
ws = sh.sheet1

st.set_page_config(page_title="Flow Park App", layout="centered")
st.title("🚗 Flow Park - Operativa VIP")

# --- Módulo 1: Recepción ---
with st.expander("📥 Registrar Ingreso"):
    tarjeta = st.text_input("Número de Tarjeta (ej. 045)")
    patente = st.text_input("Matrícula (SBA-1234)")
    if st.button("Registrar Ingreso"):
        ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), tarjeta, patente, "Ingreso", ""])
        st.success(f"Vehículo {patente} asociado a tarjeta {tarjeta}")

# --- Módulo 2 y 3: Upselling y Liquidación ---
with st.expander("🛠️ Extras y Lavados"):
    patente_extra = st.text_input("Matrícula para extras")
    extra = st.selectbox("Servicio:", ["Lavado Premium", "Gaseosa", "Agua", "Paraguas"])
    if st.button("Sumar Extra"):
        ws.append_row([datetime.now().strftime("%H:%M"), patente_extra, "Extra", extra])
        st.success(f"Agregado: {extra}")

# --- Módulo 4: Ticket y WhatsApp ---
with st.expander("🖨️ Ticket y Salida"):
    celular = st.text_input("Celular del cliente (598...)")
    if st.button("Enviar Ticket por WhatsApp"):
        msg = f"Hola, gracias por visitar Distrito El Globo. Su ticket Flow Park está listo."
        link_wsp = f"https://wa.me/{celular}?text={msg}"
        st.markdown(f"[Hacer clic aquí para enviar ticket vía WhatsApp]({link_wsp})")
