import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 1. CONFIGURACIÓN DE SEGURIDAD Y CONEXIÓN A GOOGLE SHEETS
# Definimos los permisos necesarios
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Conectamos usando los "Secrets" de Streamlit (donde pegaremos tu JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
client = gspread.authorize(creds)

# Conectamos con el nombre exacto de tu Google Sheet
# Asegúrate de que el nombre coincida exactamente con el que le pusiste en Drive
sheet = client.open("FlowPark_Valet_DB").sheet1

# 2. INTERFAZ DE STREAMLIT (PANTALLA DEL VALET)
st.set_page_config(page_title="Flow Park App", layout="centered")
st.title("🚗 Flow Park - Operativa VIP")
st.markdown("---")

st.subheader("Registrar Nuevo Ingreso")

# Formulario rápido para el Valet
with st.form("form_ingreso", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        ticket_id = st.text_input("N° Tarjeta Plástica", placeholder="Ej: 045")
    with col2:
        matricula = st.text_input("Matrícula", placeholder="Ej: SBA-1234").upper()
        
    st.markdown("**Servicios Adicionales:**")
    lavado = st.checkbox("🧼 Solicita Lavado")
    
    submit_ingreso = st.form_submit_button("✅ GUARDAR AUTO", use_container_width=True)
    
    if submit_ingreso:
        if ticket_id and matricula:
            # Capturamos la hora exacta
            hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            extra = "Lavado" if lavado else "Ninguno"
            
            # Preparamos la fila exacta para mandar al Google Sheet
            # Debe coincidir el orden con las columnas que armamos de la A a la H
            nueva_fila = [
                ticket_id,       # A: Ticket
                matricula,       # B: Matricula
                hora_actual,     # C: Hora_Ingreso
                "-",             # D: Hora_Salida
                "En Parking",    # E: Estado
                "-",             # F: Factura_Quinquela (Se llena después)
                extra,           # G: Servicios_Extras
                "0"              # H: Total_Cobrado
            ]
            
            # Escribimos los datos mágicamente en tu Excel en la nube
            sheet.append_row(nueva_fila)
            st.success(f"¡Matrícula {matricula} ingresada correctamente!")
        else:
            st.error("Por favor, ingresa el número de tarjeta y la matrícula.")