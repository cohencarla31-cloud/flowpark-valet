import streamlit as st
import gspread
import json

# Configuración de la conexión usando los secretos
creds_dict = st.secrets["gcp_service_account"]
client = gspread.service_account_from_dict(creds_dict)

# AQUÍ PEGUE EL LINK DE TU GOOGLE SHEET (el que termina en /edit)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jknI7amSqutxGT_WAIBNhD0vezFE2AueTEzP7q5Rb1c/edit?gid=0#gid=0"
sh = client.open_by_url(SHEET_URL)
worksheet = sh.sheet1 # Esto conecta con la primera pestaña

st.title("🚗 FlowPark - Valet Parking")

patente = st.text_input("Matrícula:")
propietario = st.text_input("Propietario:")

if st.button("Registrar"):
    worksheet.append_row([patente, propietario]) # Esto escribe en el Excel
    st.success("Guardado en la base de datos.")
