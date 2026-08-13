import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.title("🚗 FlowPark - Valet Parking")
st.write("Control de ingresos y salidas en puerta.")

# Formulario simple para el valet
patente = st.text_input("Matrícula / Patente del Vehículo:")
propietario = st.text_input("Nombre del Propietario / Invitado:")
accion = st.radio("Acción:", ["Ingresa a Playa", "Se Retira (Aviso Mesa)"])

if st.button("Registrar Operación"):
    if patente:
        st.success(f"¡Vehículo {patente} registrado con éxito!")
    else:
        st.warning("Por favor, ingresa al menos la patente.")
