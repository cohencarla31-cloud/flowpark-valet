import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    try: return client.open("FlowPark_Valet_DB")
    except: return None

sh = init_connection()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- LÓGICA DE TARIFA (Con 2h Quinquela gratis) ---
def calcular_mejor_precio(minutos, es_camioneta, tiene_quinquela):
    # Aplicar 2h (120 min) de descuento si tiene Quinquela
    minutos_cobro = max(0, minutos - (120 if tiene_quinquela else 0))
    
    # Precios
    hora = 110 if not es_camioneta else 140
    promo_4h = 330 if not es_camioneta else 420
    dia = 500 if not es_camioneta else 650
    
    # Cálculo: Compara hora vs promo vs día
    monto_hora = (minutos_cobro // 60 + 1) * hora
    monto_final = min(monto_hora, promo_4h if minutos_cobro > 60 else 99999, dia)
    return monto_final

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# 1. INGRESO (Validación Estricta)
if menu == "📥 Ingreso":
    patente = st.text_input("Matrícula (Ej: SDL567):").upper().replace("-", "").replace(" ", "")
    tarjeta = st.text_input("N° Tarjeta:")
    
    if st.button("Registrar Ingreso"):
        reg = sh.worksheet("Registro").get_all_records()
        # Verificar duplicados activos
        activo = any((str(r.get("Ticket")).strip() == tarjeta.strip() or 
                     str(r.get("Matricula", r.get("Matrícula"))).upper() == patente) 
                     and not r.get("Hora_Salida") for r in reg)
        
        if activo:
            st.error("❌ ¡Esa tarjeta o patente ya está en playa!")
        else:
            sh.worksheet("Registro").append_row([tarjeta, patente, hora_actual_uy(), "", "Ingreso", "", "Sin extras", ""])
            st.success(f"✅ Ingresado: {patente} | Tkt #{tarjeta}")
            st.code(f"*FLOW PARK*\n🚗 {patente}\n🎫 #{tarjeta}\n¡Bienvenido!")

# 2. PANEL ACTIVOS
elif menu == "📊 Activos":
    st.subheader("Autos en Playa")
    for r in sh.worksheet("Registro").get_all_records():
        if not r.get("Hora_Salida") and str(r.get("Ticket", "")).upper() != "EXTRA":
            st.info(f"🎫 Tkt #{r.get('Ticket')} | 🚗 {r.get('Matricula', r.get('Matrícula'))} | 🕒 Ingreso: {r.get('Hora_Ingreso')}")

# 3. QUINQUELA
elif menu == "🔔 Quinquela":
    for q in reversed(sh.worksheet("Respuestas de formulario 1").get_all_records()):
        st.success(f"🍽️ Mozo: {q.get('MOZO - NOMBRE')} | 🚗 {q.get('PATENTE')} | 🎫 #{q.get('NUMERO DE TARJETA')}")

# 4. EXTRAS
elif menu == "🍾 Extras":
    tarjeta = st.text_input("Tarjeta:")
    extra = st.selectbox("Extra:", ["Lavado Premium", "Bebida / Gaseosa", "Agua Cortesia", "Paraguas"])
    if st.button("Sumar Extra"):
        # Buscar el auto activo por tarjeta
        for r in sh.worksheet("Registro").get_all_records():
            if str(r.get("Ticket")).strip() == tarjeta.strip() and not r.get("Hora_Salida"):
                patente = r.get("Matricula", r.get("Matrícula"))
                sh.worksheet("Registro").append_row(["EXTRA", patente, hora_actual_uy(), "", f"Extra-{extra}", "EXTRA", extra, "0"])
                st.success(f"✅ {extra} agregado a {patente}.")
                break

# 5. SALIDA (Desplegable y Cálculo Inteligente)
elif menu == "📤 Salida":
    # Cargar activos para el desplegable
    activos = {f"Tkt #{r['Ticket']} - {r.get('Matricula', r.get('Matrícula'))}": r for r in sh.worksheet("Registro").get_all_records() if not r.get("Hora_Salida") and str(r.get("Ticket")).upper() != "EXTRA"}
    
    seleccion = st.selectbox("Elegir auto a retirar:", [""] + list(activos.keys()))
    if seleccion:
        r = activos[seleccion]
        tarjeta = str(r['Ticket'])
        patente = r.get("Matricula", r.get("Matrícula"))
        
        if st.button("Calcular y Cerrar Salida"):
            # Lógica Quinquela
            q_data = sh.worksheet("Respuestas de formulario 1").get_all_records()
            tiene_q = any(str(q.get("PATENTE")).upper().replace("-","") == patente.upper() for q in q_data)
            
            # Cálculo
            hora_ing = datetime.strptime(r.get("Hora_Ingreso"), "%Y-%m-%d %H:%M:%S")
            minutos = int((datetime.utcnow() - timedelta(hours=3) - hora_ing).total_seconds() / 60)
            monto = calcular_mejor_precio(minutos, "Camioneta" in r.get("Estado", ""), tiene_q)
            
            # Ticket
            texto = f"*FLOW PARK - TICKET EGRESO*\n🚗 {patente}\n⏱️ Estadía: {minutos//60}h {minutos%60}m\n💰 TOTAL: ${monto}\n{'*Beneficio Quinquela aplicado*' if tiene_q else ''}"
            st.code(texto)
            
            # Marcar salida
            idx = activos[seleccion]["_row"] if "_row" in activos[seleccion] else 0 # (Requiere ajuste en lógica de índices)
            sh.worksheet("Registro").update_cell(activos[seleccion]['_row_index'], 4, hora_actual_uy())
            st.success("✅ Salida registrada.")
