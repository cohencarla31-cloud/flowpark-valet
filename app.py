import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

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

# --- VERIFICADOR INTELIGENTE DE QUINQUELA POR SESIÓN ---
def verificar_quinquela(patente, tkt, hora_ingreso_str, q_records):
    try:
        ingreso_dt = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
    except:
        return False
        
    pat_clean = patente.upper().replace("-", "").replace(" ", "")
    tkt_clean = str(tkt).strip().lstrip("0")
    
    for q in q_records[1:]:
        if len(q) < 4: continue
        q_time_str, q_tkt, q_pat = str(q[0]).strip(), str(q[2]).strip().lstrip("0"), str(q[3]).upper().replace("-", "").replace(" ", "")
        try:
            q_dt = datetime.strptime(q_time_str, "%Y-%m-%d %H:%M:%S")
        except:
            continue
            
        # El beneficio aplica si coincide la tarjeta o patente Y la validación ocurrió DESPUÉS del ingreso actual
        if (q_tkt == tkt_clean or q_pat == pat_clean) and q_dt >= ingreso_dt:
            return True
    return False

def calcular_mejor_precio(minutos, es_camioneta, tiene_q):
    tipo = "Camioneta" if es_camioneta else "Auto"
    m_cobro = max(0, minutos - (120 if tiene_q else 0))
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    return min((m_cobro // 60 + 1) * hora, promo if m_cobro > 60 else 99999, dia)

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
emp = st.selectbox("Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# ==========================================
# 1. INGRESO
# ==========================================
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    pat = st.text_input("Matrícula (Ej: SDL567):", key="in_pat").upper().replace("-", "").replace(" ", "")
    
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
                try:
                    sh.worksheet("Clientes_Frecuentes").append_row([pat, cli, cel])
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
            es_q = verificar_quinquela(pat, tkt, h_ing, q_data)
            tag_q = " | 🍽️ **VALIDADO POR QUINQUELA**" if es_q else ""
            st.info(f"🎫 Tarjeta #{tkt} | 🚗 {pat} | 🕒 Ingreso: {h_ing}{tag_q}")

# ==========================================
# 3. QUINQUELA
# ==========================================
elif menu == "🔔 Quinquela":
    st.subheader("🍽️ Validación Quinquela (Salón)")
    
    # Solo muestra vehículos activos que NO hayan sido validados en esta sesión actual
    activos_disponibles = []
    for r in reg[1:]:
        tkt = str(r[0]).strip()
        h_sal = str(r[3]).strip()
        if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
            pat = r[1]
            h_ing = r[2]
            if not verificar_quinquela(pat, tkt, h_ing, q_data):
                activos_disponibles.append(r)
                
    opciones_mozo = [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos_disponibles]
    
    mozo = st.text_input("Nombre del Mozo:")
    seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa:", opciones_mozo)
    
    if st.button("Enviar Validación Quinquela"):
        if mozo and seleccion_mozo:
            tkt_val = seleccion_mozo.split(" - ")[0].replace("#", "").strip()
            pat_val = next((r[1] for r in activos_disponibles if r[0].strip() == tkt_val), "")
            
            sh.worksheet("Respuestas de formulario 1").append_row([hora_actual_uy(), mozo, tkt_val, pat_val])
            st.success(f"✅ Validación registrada para Tarjeta #{tkt_val}. ¡Actualiza la página para ver los cambios!")
        else:
            st.error("Completa el nombre del mozo y selecciona un vehículo.")

    st.divider()
    st.subheader("Historial de Validaciones")
    for q in reversed(q_data[1:]):
        st.write(f"🕒 {q[0]} | 🍽️ Mozo: {q[1]} | 🎫 Tarjeta: #{q[2]} | 🚗 Patente: {q[3]}")

# ==========================================
# 4. EXTRAS
# ==========================================
elif menu == "🍾 Extras":
    st.subheader("Carga de Productos / Extras")
    tkt_extra = st.text_input("N° de Tarjeta PVC del vehículo:")
    prod = st.selectbox("Seleccionar Producto / Extra:", list(extras.keys()))
    cantidad = st.number_input("Cantidad:", min_value=1, value=1, step=1)
    
    precio_unitario = extras.get(prod, 0)
    total_extra = precio_unitario * cantidad
    st.info(f"💵 Precio unitario: ${precio_unitario} | **Total a sumar: ${total_extra}**")
    
    if st.button("Sumar Extra a la Cuenta"):
        if tkt_extra:
            patente_encontrada = ""
            for r in reg[1:]:
                if r[0].strip().lstrip("0") == tkt_extra.strip().lstrip("0") and not r[3]:
                    patente_encontrada = r[1]
                    break
            
            if patente_encontrada:
                sh.worksheet("Registro").append_row(["EXTRA", patente_encontrada, hora_actual_uy(), "", f"Extra - {prod}", "EXTRA", f"{prod} x{cantidad}", total_extra])
                st.success(f"✅ Se agregó {prod} x{cantidad} (${total_extra}) al vehículo {patente_encontrada}.")
            else:
                st.error("❌ No se encontró un vehículo activo con esa tarjeta.")
        else:
            st.warning("Ingresa el número de tarjeta.")

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
        
        cel_encontrado = "598"
        for c in clientes[1:]:
            if len(c) > 2 and str(c[0]).upper().replace("-", "").replace(" ", "") == patente.upper().replace("-", "").replace(" ", ""):
                cel_encontrado = str(c[2]).strip() or "598"
                break
                
        cel_salida = st.text_input("Celular del cliente para WhatsApp:", value=cel_encontrado)
        
        if st.button("Calcular y Generar Salida"):
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            
            # Verificación de Quinquela vinculada a la sesión actual
            tiene_q = verificar_quinquela(patente, tkt, h_ingreso, q_data)
            
            es_camioneta = "Camioneta" in datos[4]
            monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, tiene_q)
            
            extras_auto = [r for r in reg[1:] if str(r[0]).upper() == "EXTRA" and str(r[1]).upper() == patente.upper() and not r[3]]
            detalle_extras = "\n".join([f"• {r[6]} (${r[7]})" for r in extras_auto])
            total_extras = sum([float(r[7]) for r in extras_auto if r[7]])
            
            total_a_pagar = monto_estacionamiento + total_extras
            info_desc = "Incluye 2h libres de cortesía por Quinquela." if tiene_q else "Tarifa estándar aplicada."
            
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
                if row[0].strip() == tkt and not row[3] and row[0].upper() != "EXTRA":
                    sh.worksheet("Registro").update_cell(i, 4, hora_actual_uy())
            for i, row in enumerate(reg, start=1):
                if str(row[0]).upper() == "EXTRA" and str(row[1]).upper() == patente.upper() and not row[3]:
                    sh.worksheet("Registro").update_cell(i, 4, hora_actual_uy())
