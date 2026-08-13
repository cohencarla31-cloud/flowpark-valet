import streamlit as st
import gspread
from datetime import datetime
import urllib.parse

# --- CONEXIÓN CON GOOGLE SHEETS ---
creds_dict = st.secrets["gcp_service_account"]
client = gspread.service_account_from_dict(creds_dict)

# 🔗 PEGA AQUÍ EL LINK DE TU GOOGLE SHEET ENTRE LAS COMILLAS
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jknI7amSqutxGT_WAIBNhD0vezFE2AueTEzP7q5Rb1c/edit?gid=844746886#gid=844746886"

sh = client.open_by_url(SHEET_URL)
ws = sh.sheet1

st.set_page_config(page_title="Flow Park App", layout="centered")
st.title("🚗 Flow Park - Operativa VIP")

# 1. Identificación del empleado operativo
empleado = st.selectbox("Selecciona tu usuario (Empleado):", ["Valet_1 (Tarde)", "Valet_2 (Noche)", "Encargado"])

# Menú principal basado en la arquitectura del ecosistema
menu = st.radio("Selecciona un módulo:", ["📥 Módulo 1: Recepción e Ingreso", "🍾 Módulo 2: Upselling (Bebidas/Lavados)", "🖨️ Módulo 4: Salida y Ticket WSP"])

if menu == "📥 Módulo 1: Recepción e Ingreso":
    st.subheader("Registro de Ingreso en Puerta")
    tarjeta = st.text_input("Número de Tarjeta PVC (ej: 045)")
    patente = st.text_input("Matrícula del Vehículo (ej: SBA-1234)")
    es_mensual = st.checkbox("¿Es un vehículo Mensualista VIP? (No paga estadía)")
    
    if st.button("Registrar Ingreso en Base"):
        if tarjeta and patente:
            tipo_cliente = "Mensualista VIP (Costo $0)" if es_mensual else "Visitante Estándar"
            # Envía los datos a Google Sheets
            ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), tarjeta, patente.upper(), "Ingreso", tipo_cliente, empleado])
            st.success(f"¡Vehículo {patente.upper()} vinculado a la tarjeta {tarjeta} y registrado por {empleado}!")
        else:
            st.warning("Por favor completa el número de tarjeta y la matrícula.")

elif menu == "🍾 Módulo 2: Upselling (Bebidas/Lavados)":
    st.subheader("Venta de Extras y Consumibles")
    patente_extra = st.text_input("Matrícula del vehículo al que se le asigna el extra")
    extra = st.selectbox("Servicio o Producto:", ["Lavado Premium de Carrocería", "Bebida / Gaseosa", "Agua Cortesia", "Paraguas"])
    precio = st.number_input("Precio ($ UYU):", min_value=0, value=250)
    
    if st.button("Sumar Extra a la Cuenta"):
        if patente_extra:
            ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), "N/A", patente_extra.upper(), f"Extra: {extra}", f"${precio}", empleado])
            st.success(f"Se registró '{extra}' por ${precio} para el auto {patente_extra.upper()}")
        else:
            st.warning("Debes indicar la matrícula del vehículo.")

elif menu == "🖨️ Módulo 4: Salida y Ticket WSP":
    st.subheader("Cómputo de Salida y Envío de Ticket")
    patente_salida = st.text_input("Matrícula que solicita egreso")
    celular = st.text_input("Celular del cliente para el Ticket (Ej: 59899123456)")
    
    if st.button("Generar Enlace de Ticket WhatsApp"):
        if patente_salida and celular:
            mensaje = f"Hola! Gracias por visitarnos en Distrito El Globo y Flow Park[cite: 2]. Su vehículo {patente_salida.upper()} ya está listo en rampa. ¡Buen viaje!"
            link_wsp = f"https://wa.me/{celular}?text={urllib.parse.quote(mensaje)}"
            
            ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), "N/A", patente_salida.upper(), "Salida y Ticket", "N/A", empleado])
            st.success("¡Ticket generado con éxito en el sistema!")
            st.markdown(f"### [📲 Haz clic aquí para enviar el Ticket por WhatsApp al cliente]({link_wsp})", unsafe_allow_html=True)
        else:
            st.warning("Ingresa la matrícula y el número de celular del cliente.")
