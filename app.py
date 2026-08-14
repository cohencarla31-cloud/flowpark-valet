import streamlit as st
import gspread
from datetime import datetime
import urllib.parse

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Flow Park - Valet & Gerencia", layout="centered")

# --- CONEXIÓN SEGURA CON GOOGLE SHEETS ---
@st.cache_resource
def init_connections():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    
    # 1. Tu Planilla Maestra de Valet abierta por su nombre exacto en Drive
    sh_valet = client.open("FlowPark_Valet_DB")
    
    # 2. Planilla del Formulario de Quinquela
    id_quinquela = "18ufUYyHmDbqAb74Cu2mS7i6L6JBRJZQyxoR10GBOwaM"
    sh_quinquela = client.open_by_key(id_quinquela)
    
    return sh_valet, sh_quinquela

try:
    sh, sh_quinquela = init_connections()
    
    # Cargar empleados desde la pestaña 'Configuracion' de tu Excel
    ws_config = sh.worksheet("Configuracion")
    empleados = ws_config.col_values(1)[1:] 
    if not empleados:
        empleados = ["Valet 1", "Valet 2", "Encargado"]
except Exception as e:
    st.error(f"Error al conectar con las planillas: {e}")
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
    
    with st.form("form_ingreso", clear_on_submit=True):
        tarjeta = st.text_input("N° de Tarjeta PVC (Ej: 045)")
        patente = st.text_input("Matrícula del Vehículo (Ej: SBA-1234)")
        tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
        
        submitted_ingreso = st.form_submit_button("Registrar Ingreso")
        
        if submitted_ingreso:
            if tarjeta and patente:
                patente_limpia = patente.upper().replace("-", "").replace(" ", "")
                hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Columnas de tu Excel de Registro
                fila_datos = [
                    tarjeta, 
                    patente_limpia, 
                    hora_actual, 
                    "",               
                    f"Ingresado ({tipo_vehiculo}) - Op: {empleado_actual}", 
                    "",               
                    "",               
                    ""                
                ]
                
                ws_registro = sh.worksheet("Registro")
                ws_registro.append_row(fila_datos)
                
                st.success(f"✅ ¡Vehículo {patente_limpia} vinculado a tarjeta {tarjeta} con éxito!")
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
                
                # Verificación automática en la planilla de Quinquela
                try:
                    ws_q = sh_quinquela.worksheet("Form_Responses")
                    # Traemos todas las patentes registradas por los mozos (Columna C)
                    patentes_quinquela = [p.upper().replace("-", "").replace(" ", "") for p in ws_q.col_values(3)]
                    
                    if patente_limpia in patentes_quinquela:
                        descuento_txt = "¡Beneficio Quinquela aplicado (2 horas libres)!"
                    else:
                        descuento_txt = "Estándar (Sin validación de salón)."
                except Exception:
                    descuento_txt = "No se pudo verificar Quinquela en línea."
                
                # Generador de enlace de WhatsApp automatizado
                texto_ticket = f"Hola! Gracias por visitar Distrito El Globo y Flow Park. Su vehículo {patente_limpia} ya se encuentra listo en rampa. {descuento_txt} ¡Buen viaje!"
                link_wsp = f"https://wa.me/{celular}?text={urllib.parse.quote(texto_ticket)}"
                
                st.success(f"✅ Egreso procesado para {patente_limpia} por {empleado_actual}.")
                st.info(f"ℹ️ Estado de salón: {descuento_txt}")
                st.markdown(f"### [📲 HAGA CLIC AQUÍ PARA ENVIAR EL TICKET POR WHATSAPP AL CLIENTE]({link_wsp})", unsafe_allow_html=True)
            else:
                st.warning("⚠️ Ingresa la matrícula y el número de celular.")
