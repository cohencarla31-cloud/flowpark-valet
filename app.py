import streamlit as st
import gspread
from datetime import datetime
import urllib.parse

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Flow Park - Valet & Gerencia", layout="centered")

# --- CONEXIÓN SEGURA CON GOOGLE SHEETS ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    # 🔗 REEMPLAZA ESTE LINK POR EL DE TU GOOGLE SHEET MAESTRO
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1jknI7amSqutxGT_WAIBNhD0vezFE2AueTEzP7q5Rb1c/edit?gid=1498869870#gid=1498869870"
    return client.open_by_url(SHEET_URL)

try:
    sh = init_connection()
    # Cargar datos dinámicos desde las pestañas del Excel
    ws_config = sh.worksheet("Configuracion")
    empleados = ws_config.col_values(1)[1:] # Salta la cabecera
    if not empleados:
        empleados = ["Valet 1", "Valet 2", "Encargado"] # Fallback por seguridad
except Exception as e:
    st.error(f"Error al conectar con Google Sheets o leer pestañas: {e}")
    empleados = ["Valet 1", "Valet 2", "Encargado"]

st.title("🚗 Flow Park - Operativa VIP")

# --- SELECTOR DE EMPLEADO DINÁMICO ---
empleado_actual = st.selectbox("👤 Selecciona tu usuario (Empleado):", empleados)

# --- MENÚ PRINCIPAL ---
menu = st.radio("Selecciona una opción operativa:", ["📥 Ingreso de Vehículo", "🍾 Venta de Extras / Lavados", "📤 Salida y Ticket WSP"])

# ==========================================
# MÓDULO 1: INGRESO DE VEHÍCULOS
# ==========================================
if menu == "📥 Ingreso de Vehículo":
    st.subheader("Registro de Ingreso en Puerta")
    
    # Uso de st.form para limpiar campos automáticamente al enviar
    with st.form("form_ingreso", clear_on_submit=True):
        tarjeta = st.text_input("N° de Tarjeta PVC (Ej: 045)")
        patente = st.text_input("Matrícula del Vehículo (Ej: SBA-1234)")
        tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
        
        submitted_ingreso = st.form_submit_button("Registrar Ingreso")
        
        if submitted_ingreso:
            if tarjeta and patente:
                # Estandarización de matrícula (Mayúsculas, sin guiones ni espacios)
                patente_limpia = patente.upper().replace("-", "").replace(" ", "")
                hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Columnas de tu Excel: [Ticket, Matricula, Hora_Ingreso, Hora_Salida, Estado, Factura_Quinquela, Servicios_Extras, Total_Cobrado]
                fila_datos = [
                    tarjeta, 
                    patente_limpia, 
                    hora_actual, 
                    "",               # Hora_Salida (vacía al ingresar)
                    f"Ingresado ({tipo_vehiculo}) - Op: {empleado_actual}", 
                    "",               # Factura_Quinquela
                    "",               # Servicios_Extras
                    ""                # Total_Cobrado (calculado por fórmula en Excel)
                ]
                
                ws_registro = sh.worksheet("Registro")
                ws_registro.append_row(fila_datos)
                
                st.success(f"✅ ¡Vehículo {patente_limpia} vinculado a tarjeta {tarjeta} con éxito!")
                
                # Mensaje de bienvenida simulado por WhatsApp
                mensaje_wsp = f"Hola! Bienvenido a Distrito El Globo. Su vehículo {patente_limpia} ha sido ingresado correctamente bajo la tarjeta #{tarjeta}."
                st.info(f"📋 Datos listos para el sistema. Operador a cargo: {empleado_actual}")
            else:
                st.warning("⚠️ Por favor completa el número de tarjeta y la matrícula.")

# ==========================================
# MÓDULO 2: EXTRAS Y LAVADOS
# ==========================================
elif menu == "🍾 Venta de Extras / Lavados":
    st.subheader("Carga de Servicios Adicionales")
    
    with st.form("form_extras", clear_on_submit=True):
        patente_extra = st.text_input("Matrícula del Vehículo:")
        extra_tipo = st.selectbox("Servicio o Producto:", ["Lavado Premium de Carrocería", "Bebida / Gaseosa", "Agua Cortesía", "Paraguas"])
        precio_extra = st.number_input("Precio ($ UYU):", min_value=0, value=250)
        
        submitted_extra = st.form_submit_button("Sumar Extra a la Cuenta")
        
        if submitted_extra:
            if patente_extra:
                patente_limpia = patente_extra.upper().replace("-", "").replace(" ", "")
                hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Registramos el extra como una línea de consumo asociada
                fila_extra = [
                    "EXTRA", 
                    patente_limpia, 
                    hora_actual, 
                    "", 
                    f"Extra por {empleado_actual}", 
                    "", 
                    f"{extra_tipo} (${precio_extra})", 
                    precio_extra
                ]
                
                ws_registro = sh.worksheet("Registro")
                ws_registro.append_row(fila_extra)
                
                st.success(f"✅ Se registró '{extra_tipo}' por ${precio_extra} para el vehículo {patente_limpia}.")
            else:
                st.warning("⚠️ Debes indicar la matrícula del vehículo.")

# ==========================================
# MÓDULO 3: SALIDA Y TICKET WSP
# ==========================================
elif menu == "📤 Salida y Ticket WSP":
    st.subheader("Cómputo de Egreso y Envío de Ticket")
    
    with st.form("form_salida", clear_on_submit=True):
        patente_salida = st.text_input("Matrícula que solicita egreso:")
        celular = st.text_input("Celular del cliente para el Ticket (Ej: 59899123456):")
        
        submitted_salida = st.form_submit_button("Generar Ticket y Enlace WSP")
        
        if submitted_salida:
            if patente_salida and celular:
                patente_limpia = patente_salida.upper().replace("-", "").replace(" ", "")
                hora_salida = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Generador de enlace de WhatsApp automatizado
                texto_ticket = f"Hola! Gracias por visitar Distrito El Globo y Flow Park. Su vehículo {patente_limpia} ya se encuentra listo en rampa. ¡Buen viaje!"
                link_wsp = f"https://wa.me/{celular}?text={urllib.parse.quote(texto_ticket)}"
                
                st.success(f"✅ Egreso procesado para {patente_limpia} por {empleado_actual}.")
                st.markdown(f"### [📲 HAGA CLIC AQUÍ PARA ENVIAR EL TICKET POR WHATSAPP AL CLIENTE]({link_wsp})", unsafe_allow_html=True)
            else:
                st.warning("⚠️ Ingresa la matrícula y el número de celular.")
