import streamlit as st
import gspread
from datetime import datetime
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

@st.cache_resource
def init_connections():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    sh_valet = client.open("FlowPark_Valet_DB")
    sh_quinquela = client.open_by_key("18ufUYyHmDbqAb74Cu2mS7i6L6JBRJZQyxoR10GBOwaM")
    return sh_valet, sh_quinquela

try:
    sh, sh_quinquela = init_connections()
    try:
        ws_config = sh.worksheet("Configuracion")
        empleados = ws_config.col_values(1)[1:] 
    except Exception:
        empleados = []
    if not empleados:
        empleados = ["Valet 1", "Valet 2", "Encargado"]

    # Cargar Tarifas y Extras desde Excel
    try:
        ws_tarifas = sh.worksheet("Tarifas_y_Extras")
        tarifas_data = ws_tarifas.get_all_records()
        dict_tarifas = {row['Servicio']: int(row['Precio']) for row in tarifas_data}
    except Exception:
        dict_tarifas = {"Lavado Premium": 350, "Bebida / Gaseosa": 100, "Agua Cortesía": 50, "Paraguas": 250}

except Exception as e:
    st.error(f"Error al conectar con las planillas: {e}")
    empleados = ["Valet 1", "Valet 2", "Encargado"]
    dict_tarifas = {"Lavado Premium": 350, "Bebida / Gaseosa": 100}

st.title("🚗 Flow Park - Operativa VIP")

empleado_actual = st.selectbox("👤 Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso de Vehículo", "🍾 Venta de Extras / Lavados", "📤 Salida y Ticket WSP"])

# ==========================================
# 1. INGRESO (Con opción Mensualista VIP)
# ==========================================
if menu == "📥 Ingreso de Vehículo":
    st.subheader("Registro de Ingreso en Puerta")
    with st.form("form_ingreso", clear_on_submit=True):
        tarjeta = st.text_input("N° de Tarjeta PVC (Ej: 45)")
        patente = st.text_input("Matrícula del Vehículo (Ej: SDL567)")
        tipo_cliente = st.selectbox("Tipo de Cliente:", ["Estándar", "Mensualista VIP (Costo $0)"])
        tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
        
        if st.form_submit_button("Registrar Ingreso"):
            if tarjeta and patente:
                patente_limpia = patente.upper().replace("-", "").replace(" ", "")
                hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                estado_registro = f"{tipo_cliente} ({tipo_vehiculo}) - {empleado_actual}"
                
                fila_datos = [tarjeta, patente_limpia, hora_actual, "", estado_registro, "", "", ""]
                sh.worksheet("Registro").append_row(fila_datos)
                st.success(f"✅ Ingreso registrado [{tipo_cliente}]: Tarjeta #{tarjeta} -> Patente {patente_limpia}")
            else:
                st.warning("⚠️ Completa tarjeta y matrícula.")

# ==========================================
# 2. EXTRAS (Basado en N° de Tarjeta)
# ==========================================
elif menu == "🍾 Venta de Extras / Lavados":
    st.subheader("Carga de Servicios Adicionales por Tarjeta")
    
    with st.form("form_extras", clear_on_submit=True):
        tarjeta_extra = st.text_input("N° de Tarjeta PVC del Vehículo:")
        extra_tipo = st.selectbox("Servicio o Producto:", list(dict_tarifas.keys()))
        
        precio_sugerido = dict_tarifas.get(extra_tipo, 0)
        precio_extra = st.number_input("Precio ($ UYU):", min_value=0, value=precio_sugerido)
        
        if st.form_submit_button("Sumar Extra a la Cuenta"):
            if tarjeta_extra:
                try:
                    registros = sh.worksheet("Registro").get_all_records()
                    patente_encontrada = ""
                    for r in registros:
                        if str(r.get("Ticket")) == str(tarjeta_extra) and not r.get("Hora_Salida"):
                            patente_encontrada = r.get("Matrícula")
                            break
                    
                    if not patente_encontrada:
                        patente_encontrada = f"TARJETA_{tarjeta_extra}"
                    
                    hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    fila_extra = ["EXTRA", patente_encontrada, hora_actual, "", f"Extra ({empleado_actual})", "", f"{extra_tipo} (${precio_extra})", precio_extra]
                    sh.worksheet("Registro").append_row(fila_extra)
                    
                    st.success(f"✅ '{extra_tipo}' (${precio_extra}) sumado a Tarjeta #{tarjeta_extra} (Patente: {patente_encontrada}).")
                except Exception as ex:
                    st.error(f"Error al buscar la tarjeta: {ex}")
            else:
                st.warning("⚠️ Ingresa el número de tarjeta.")

# ==========================================
# 3. SALIDA Y TICKET (Validación Mensualista + Quinquela)
# ==========================================
elif menu == "📤 Salida y Ticket WSP":
    st.subheader("Cómputo de Egreso por Tarjeta")
    
    with st.form("form_salida", clear_on_submit=True):
        tarjeta_salida = st.text_input("N° de Tarjeta PVC a devolver:")
        celular = st.text_input("Celular del cliente (Ej: 59899123456):")
        
        if st.form_submit_button("Generar Ticket y Enlace WSP"):
            if tarjeta_salida and celular:
                try:
                    registros = sh.worksheet("Registro").get_all_records()
                    patente_limpia = ""
                    es_mensualista = False
                    
                    for r in registros:
                        if str(r.get("Ticket")) == str(tarjeta_salida):
                            patente_limpia = r.get("Matrícula")
                            estado_actual = str(r.get("Estado", ""))
                            if "Mensualista VIP" in estado_actual:
                                es_mensualista = True
                            break
                    
                    if not patente_limpia:
                        patente_limpia = f"TARJETA_{tarjeta_salida}"

                    # Lógica de costos y mensajes
                    if es_mensualista:
                        descuento_txt = "¡Cliente Mensualista VIP (Costo $0)! Gracias por su preferencia."
                    else:
                        # Verificar Quinquela si no es mensualista
                        ws_q = sh_quinquela.worksheet("Form_Responses")
                        patentes_quinquela = [p.upper().replace("-", "").replace(" ", "") for p in ws_q.col_values(3)]
                        
                        if patente_limpia in patentes_quinquela:
                            descuento_txt = "¡Beneficio Quinquela aplicado (2 horas libres)!"
                        else:
                            descuento_txt = "Tarifa estándar aplicada."
                
                    texto_ticket = f"Hola! Gracias por visitar Distrito El Globo y Flow Park. Su vehículo {patente_limpia} (Tarjeta #{tarjeta_salida}) ya está en rampa. {descuento_txt} ¡Buen viaje!"
                    link_wsp = f"https://wa.me/{celular}?text={urllib.parse.quote(texto_ticket)}"
                    
                    st.success(f"✅ Egreso procesado para Tarjeta #{tarjeta_salida} ({patente_limpia}).")
                    st.markdown(f"### [📲 HAGA CLIC AQUÍ PARA ENVIAR EL TICKET POR WHATSAPP]({link_wsp})", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error al procesar la salida: {e}")
            else:
                st.warning("⚠️ Ingresa el número de tarjeta y celular.")
