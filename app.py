import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- ESTILOS CSS PARA BOTONES MÁS GRANDES ---
st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 10px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 15px 25px; border-radius: 8px; font-size: 18px; border: 2px solid #ddd; cursor: pointer; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    </style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DE TELÉFONOS DEL PARKING ---
TEL_PARKING_1 = "59893343092" # <- REEMPLAZA POR EL CELULAR 1 DEL PARKING
TEL_PARKING_2 = "59895280412" # <- REEMPLAZA POR EL CELULAR 2 DEL PARKING

# --- CONEXIÓN Y CACHÉ ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

@st.cache_data(ttl=15)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, registro, q_data, cli

empleados, tarifas, extras, reg, q_data, clientes = obtener_datos()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

def obtener_validacion_local(patente, tkt, hora_ingreso_str, q_records):
    try:
        ingreso_dt = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
    except: return None
        
    pat_clean = patente.upper().replace("-", "").replace(" ", "")
    tkt_clean = str(tkt).strip().lstrip("0")
    
    for q in q_records[1:]:
        if len(q) < 4: continue
        q_time_str = str(q[0]).strip()
        q_tkt = str(q[2]).strip().lstrip("0")
        q_pat = str(q[3]).upper().replace("-", "").replace(" ", "")
        
        # Leemos el local (si no existe, asumimos Quinquela por retrocompatibilidad)
        q_local = str(q[5]).strip() if len(q) > 5 else "Quinquela"
        
        try: q_dt = datetime.strptime(q_time_str, "%Y-%m-%d %H:%M:%S")
        except: continue
            
        if (q_tkt == tkt_clean or q_pat == pat_clean) and q_dt >= ingreso_dt:
            return q_local
    return None

def calcular_mejor_precio(minutos, es_camioneta, local_validacion):
    tipo = "Camioneta" if es_camioneta else "Auto"
    
    # Lógica Rodrigo Bueno (Gratis Total)
    if local_validacion == "Rodrigo Bueno":
        return 0
        
    # Lógica 2.5 horas (150 mins) para Quinquela y Number 18
    descuento = 150 if local_validacion in ["Quinquela", "Number 18"] else 0
    m_cobro = max(0, minutos - descuento)
    
    if m_cobro <= 0:
        return 0
        
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    
    monto_hora = ((m_cobro - 1) // 60 + 1) * hora
    return min(monto_hora, promo if m_cobro > 60 else 99999, dia)

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
emp = st.selectbox("Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Validaciones", "🍾 Extras", "📤 Salida", "⏰ Personal"])

# ==========================================
# 1. INGRESO
# ==========================================
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    pat = st.text_input("Matrícula (Ej: SDL567):", key="in_pat").upper().replace("-", "").replace(" ", "")
    
    # Autocompletado inteligente de Clientes Frecuentes
    nombre_sug, cel_sug = "", "598"
    if pat:
        for rc in clientes[1:]:
            if len(rc) > 2 and str(rc[0]).upper().replace("-", "").replace(" ", "") == pat:
                nombre_sug, cel_sug = rc[1], str(rc[2]).strip()
                break
    
    tkt = st.text_input("N° Tarjeta PVC:")
    cli = st.text_input("Nombre Cliente:", value=nombre_sug)
    cel = st.text_input("Celular del cliente:", value=cel_sug)
    tipo_vehi = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
    
    if st.button("Registrar Ingreso"):
        if tkt and pat:
            if any((r[0].strip().lstrip("0") == tkt.strip().lstrip("0") or r[1].upper() == pat) and not r[3] for r in reg[1:]):
                st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
            else:
                estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                sh.worksheet("Registro").append_row([str(tkt).strip(), pat, hora_actual_uy(), "", estado_txt, "", f"Cliente: {cli}", ""])
                try: sh.worksheet("Clientes_Frecuentes").append_row([pat, cli, cel])
                except: pass
                
                st.success(f"✅ Ingreso registrado: {pat} | Tarjeta #{tkt}")
                msg_ingreso = f"*FLOW PARK - TICKET INGRESO*\n🚗 Vehículo: {pat}\n🎫 Tarjeta: #{tkt}\n¡Gracias {cli} por elegirnos!"
                st.code(msg_ingreso)
                st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel}?text={urllib.parse.quote(msg_ingreso)})")
        else:
            st.warning("Completa la tarjeta y la matrícula.")

# ==========================================
# 2. ACTIVOS
# ==========================================
elif menu == "📊 Activos":
    st.subheader("Vehículos en Playa")
    for r in reversed(reg[1:]):
        tkt = str(r[0]).strip()
        h_sal = str(r[3]).strip()
        if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
            pat = r[1]
            h_ing = r[2]
            local_val = obtener_validacion_local(pat, tkt, h_ing, q_data)
            tag_q = f" | 🍽️ **VALIDADO: {local_val.upper()}**" if local_val else ""
            st.info(f"🎫 Tarjeta #{tkt} | 🚗 {pat} | 🕒 Ingreso: {h_ing}{tag_q}")

# ==========================================
# 3. VALIDACIONES (Locales)
# ==========================================
elif menu == "🔔 Validaciones":
    st.subheader("🍽️ Validación de Locales (Mozos)")
    
    activos_disponibles = []
    for r in reg[1:]:
        tkt = str(r[0]).strip()
        h_sal = str(r[3]).strip()
        if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
            pat = r[1]
            h_ing = r[2]
            if not obtener_validacion_local(pat, tkt, h_ing, q_data):
                activos_disponibles.append(r)
                
    opciones_mozo = [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos_disponibles]
    
    local_sel = st.selectbox("Seleccionar Local:", ["Quinquela", "Number 18", "Rodrigo Bueno"])
    mozo = st.text_input("Nombre del Mozo / Recepción:")
    seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa:", opciones_mozo)
    factura = st.text_input("Últimos 4 dígitos de la factura:", max_chars=4)
    
    if st.button("Enviar Validación y Avisar al Parking"):
        if mozo and seleccion_mozo:
            # Obliga a poner factura solo en Quinquela y Number 18
            if local_sel in ["Quinquela", "Number 18"] and len(factura) < 4:
                st.error("⚠️ Es obligatorio ingresar los últimos 4 dígitos de la factura para este local.")
            else:
                tkt_val = seleccion_mozo.split(" - ")[0].replace("#", "").strip()
                pat_val = next((r[1] for r in activos_disponibles if r[0].strip() == tkt_val), "")
                
                try:
                    # Guardado en Google Sheets [Hora, Mozo, Tkt, Patente, Factura, Local]
                    sh.worksheet("Respuestas de formulario 1").append_row([hora_actual_uy(), mozo, tkt_val, pat_val, factura, local_sel])
                    st.success(f"✅ Validación de {local_sel} registrada para Tarjeta #{tkt_val}.")
                    
                    # Generación de mensaje para enviar a los celulares del Parking
                    msg_aviso = urllib.parse.quote(f"⚠️ *VALIDACIÓN FLOW PARK*\n🚗 Vehículo: {pat_val} (Tkt #{tkt_val})\n🏪 Local: {local_sel}\n🧾 Factura: {factura}\n👤 Validado por: {mozo}")
                    
                    st.markdown("### 📲 Enviar alerta al equipo del Parking:")
                    st.markdown(f"[➡️ Avisar a Teléfono 1]({f'https://wa.me/{TEL_PARKING_1}?text={msg_aviso}'})", unsafe_allow_html=True)
                    st.markdown(f"[➡️ Avisar a Teléfono 2]({f'https://wa.me/{TEL_PARKING_2}?text={msg_aviso}'})", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error al conectar con la base de datos: {e}")
        else:
            st.error("Completa el nombre y selecciona un vehículo.")

    st.divider()
    st.subheader("Historial de Validaciones")
    for q in reversed(q_data[1:]):
        fac = str(q[4]) if len(q) > 4 else "N/A"
        loc = str(q[5]) if len(q) > 5 else "Quinquela"
        st.write(f"🕒 {q[0]} | 🏪 {loc} | 🍽️ Mozo: {q[1]} | 🧾 Fac: {fac} | 🎫 Tkt: #{q[2]} | 🚗 Pat: {q[3]}")

# ==========================================
# 4. EXTRAS (Con Validación de Stock estricta)
# ==========================================
elif menu == "🍾 Extras":
    st.subheader("Carga de Productos / Extras")
    
    activos_extras = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    opciones_extras = [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos_extras]
    
    sel_extra_veh = st.selectbox("Seleccionar Vehículo en Playa:", opciones_extras)
    
    # Obliga a elegir un producto dejando el primero en blanco
    lista_productos = [""] + list(extras.keys())
    prod = st.selectbox("Seleccionar Producto / Extra:", lista_productos)
    cantidad = st.number_input("Cantidad:", min_value=1, value=1, step=1)
    
    if prod:
        precio_unitario = extras.get(prod, 0)
        total_extra = precio_unitario * cantidad
        st.info(f"💵 Precio unitario: ${precio_unitario} | **Total a sumar: ${total_extra}**")
    else:
        total_extra = 0
    
    if st.button("Sumar Extra a la Cuenta"):
        tkt_elegido = sel_extra_veh.split(" - ")[0].replace("#", "").strip() if sel_extra_veh else ""
        
        if not tkt_elegido:
            st.warning("⚠️ Primero debes seleccionar un vehículo de la lista.")
        elif not prod:
            st.warning("⚠️ Debes seleccionar un Producto/Extra para poder sumarlo.")
        else:
            patente_encontrada = next((r[1] for r in reg[1:] if r[0].strip().lstrip("0") == tkt_elegido.lstrip("0") and not r[3]), "")
            
            if patente_encontrada:
                try:
                    sh.worksheet("Registro").append_row(["EXTRA", patente_encontrada, hora_actual_uy(), "", f"Extra - {prod}", "EXTRA", f"{prod} x{cantidad}", total_extra])
                    sh.worksheet("Control_Stock").append_row([hora_actual_uy(), str(prod), int(cantidad), str(emp), str(patente_encontrada)])
                    st.success(f"✅ Se agregó {prod} x{cantidad} (${total_extra}) al vehículo {patente_encontrada}.")
                except Exception as e:
                    st.error(f"⚠️ Error al guardar. Verifica que exista la pestaña 'Control_Stock'. Detalle: {e}")
            else:
                st.error("❌ No se encontró un vehículo activo con esa tarjeta.")

# ==========================================
# 5. SALIDA
# ==========================================
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir auto a retirar:", [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos])
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        datos = next(r for r in activos if r[0].strip() == tkt)
        patente = datos[1]
        h_ingreso = datos[2]
        
        cel_encontrado = next((str(c[2]).strip() for c in clientes[1:] if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.upper().replace("-", "").replace(" ", "")), "598")
        cel_salida = st.text_input("Celular del cliente para WhatsApp:", value=cel_encontrado)
        
        if st.button("Calcular y Generar Salida"):
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            es_camioneta = "Camioneta" in datos[4]
            monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val)
            
            extras_auto = [r for r in reg[1:] if str(r[0]).upper() == "EXTRA" and str(r[1]).upper() == patente.upper() and not r[3]]
            detalle_extras = "\n".join([f"• {r[6]} (${r[7]})" for r in extras_auto])
            total_extras = sum([float(r[7]) for r in extras_auto if r[7]])
            
            total_a_pagar = monto_estacionamiento + total_extras
            
            if local_val == "Rodrigo Bueno": info_desc = "Estacionamiento 100% bonificado por Rodrigo Bueno."
            elif local_val: info_desc = f"Incluye 2.5h libres de cortesía por {local_val}."
            else: info_desc = "Tarifa estándar aplicada."
            
            serv_str = str(datos[6])
            nombre_cliente = serv_str.split("Cliente: ")[1] if "Cliente: " in serv_str else "estimado cliente"
            
            texto_ticket = f"""*FLOW PARK - TICKET DE EGRESO*
---------------------------------
🚗 Vehículo: {patente} | Tarjeta: #{tkt}
⏱️ Estadía total: {mins//60}h {mins%60}m
---------------------------------
📋 DETALLE:
{detalle_extras if detalle_extras else "Sin extras consumidos."}
Estacionamiento: ${monto_estacionamiento}
Total Extras: ${total_extras}
---------------------------------
💰 *TOTAL A PAGAR: ${total_a_pagar}*
ℹ️ {info_desc}
---------------------------------
Gracias {nombre_cliente} por visitarnos. ¡Te esperamos nuevamente!
"""
            st.success("✅ ¡Cálculo y ticket generados con éxito!")
            st.code(texto_ticket)
            st.markdown(f"[📲 Enviar Ticket Final por WhatsApp](https://wa.me/{cel_salida}?text={urllib.parse.quote(texto_ticket)})")
            
            for i, row in enumerate(reg, start=1):
                if (row[0].strip() == tkt or (str(row[0]).upper() == "EXTRA" and str(row[1]).upper() == patente.upper())) and not row[3]:
                    sh.worksheet("Registro").update_cell(i, 4, hora_actual_uy())

# ==========================================
# 6. PERSONAL (Control de Asistencia)
# ==========================================
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Asistencia")
    accion = st.radio("Acción a registrar:", ["Entrada", "Salida"])
    
    if st.button("Registrar Fichada"):
        try:
            sh.worksheet("Asistencia").append_row([hora_actual_uy(), str(emp), accion])
            st.success(f"✅ Se registró la **{accion}** de {emp} correctamente a las {hora_actual_uy()}")
        except Exception as e:
            st.error(f"⚠️ Error. Asegúrate de tener creada una pestaña llamada 'Asistencia'. Detalle: {e}")
