import streamlit as st
import gspread
from datetime import datetime
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN A PLANILLAS ---
@st.cache_resource
def init_connections():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    
    # Planilla principal
    try:
        sh_valet = client.open("FlowPark_Valet_DB")
    except Exception as e:
        st.error(f"❌ Error al abrir la planilla principal: {e}")
        sh_valet = None

    # Planilla Quinquela
    try:
        sh_quinquela = client.open_by_key("18ufUYyHmDbqAb74Cu2mS7i6L6JBRJZQyxoR10GBOwaM")
    except Exception:
        sh_quinquela = None
        
    return sh_valet, sh_quinquela

sh, sh_quinquela = init_connections()

# --- CARGA DE DATOS INICIALES ---
empleados = ["Valet 1", "Valet 2", "Encargado"]
if sh:
    try:
        ws_config = sh.worksheet("Configuracion")
        empleados_db = ws_config.col_values(1)[1:] 
        if empleados_db: empleados = empleados_db
    except: pass

dict_tarifas = {"Lavado Premium": 350, "Bebida / Gaseosa": 100, "Agua Cortesía": 50, "Paraguas": 250}
if sh:
    try:
        ws_tarifas = sh.worksheet("Tarifas_y_Extras")
        tarifas_data = ws_tarifas.get_all_records()
        dict_tarifas = {row['Servicio']: int(row['Precio']) for row in tarifas_data}
    except: pass

st.title("🚗 Flow Park - Operativa VIP")
if not sh: st.stop()

empleado_actual = st.selectbox("👤 Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso de Vehículo", "🍾 Venta de Extras / Lavados", "📤 Salida y Ticket WSP"])

# ==========================================
# 1. INGRESO
# ==========================================
if menu == "📥 Ingreso de Vehículo":
    st.subheader("Registro de Ingreso")
    tarjeta = st.text_input("N° de Tarjeta PVC")
    patente = st.text_input("Matrícula")
    celular = st.text_input("Celular del cliente (para ticket)")
    tipo_cli = st.selectbox("Tipo de Cliente:", ["Estándar", "Mensualista VIP (Costo $0)"])
    
    if st.button("Registrar Ingreso"):
        if tarjeta and patente:
            patente_limpia = patente.upper().replace("-", "").replace(" ", "")
            hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sh.worksheet("Registro").append_row([tarjeta, patente_limpia, hora_actual, "", f"{tipo_cli} - {empleado_actual}", "", "", ""])
            st.success("✅ Ingreso registrado.")
            
            if celular:
                texto = f"Bienvenido a Flow Park! Vehículo {patente_limpia} registrado. Hora: {hora_actual}."
                st.markdown(f"[📲 Enviar Ticket de Ingreso](https://wa.me/{celular}?text={urllib.parse.quote(texto)})")

# ==========================================
# 2. EXTRAS
# ==========================================
elif menu == "🍾 Venta de Extras / Lavados":
    st.subheader("Carga de Extras")
    tarjeta_extra = st.text_input("N° de Tarjeta PVC")
    extra_tipo = st.selectbox("Servicio:", list(dict_tarifas.keys()))
    precio_extra = st.number_input("Precio ($ UYU):", value=dict_tarifas.get(extra_tipo, 0))
    
    if st.button("Sumar Extra"):
        try:
            reg = sh.worksheet("Registro").get_all_records()
            patente_e = next((r['Matrícula'] for r in reg if str(r['Ticket']) == str(tarjeta_extra) and not r['Hora_Salida']), "DESCONOCIDO")
            sh.worksheet("Registro").append_row(["EXTRA", patente_e, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", f"Extra ({empleado_actual})", "", f"{extra_tipo} (${precio_extra})", precio_extra])
            st.success(f"✅ {extra_tipo} sumado a {patente_e}.")
        except Exception as e: st.error(f"Error: {e}")

# ==========================================
# 3. SALIDA Y TICKET DETALLADO
# ==========================================
elif menu == "📤 Salida y Ticket WSP":
    st.subheader("Computo de Egreso")
    tarjeta_salida = st.text_input("N° de Tarjeta PVC a devolver")
    celular = st.text_input("Celular del cliente")
    
    if st.button("Generar Ticket Detallado"):
        try:
            reg = sh.worksheet("Registro").get_all_records()
            fila = next((r for r in reg if str(r['Ticket']) == str(tarjeta_salida)), None)
            patente_limpia = fila['Matrícula']
            es_mensual = "Mensualista VIP" in str(fila.get("Estado", ""))
            
            # Recopilar extras
            extras = [r for r in reg if r['Matrícula'] == patente_limpia and r['Ticket'] == "EXTRA"]
            detalle = "\n".join([f"- {r['Estado']} (${r['Precio']})" for r in extras])
            total = sum([float(r['Precio']) for r in extras])
            
            descuento = "¡Mensualista VIP (Costo $0)!" if es_mensual else "Tarifa estándar."
            if not es_mensual and sh_quinquela:
                patentes_q = [p.upper().replace("-", "").replace(" ", "") for p in sh_quinquela.worksheet("Form_Responses").col_values(3)]
                if patente_limpia in patentes_q: descuento = "¡Beneficio Quinquela (2h libres)!"
            
            msg = f"*FLOW PARK - TICKET EGRESO*\nVehículo: {patente_limpia}\nServicios:\n{detalle if detalle else 'Sin extras'}\nTotal Extras: ${total}\nEstado: {descuento}"
            st.success("✅ Ticket generado")
            st.markdown(f"[📲 Enviar Ticket a WhatsApp](https://wa.me/{celular}?text={urllib.parse.quote(msg)})")
        except Exception as e: st.error(f"Error al calcular: {e}")
