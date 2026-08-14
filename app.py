import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

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

# --- LÓGICA DE CÁLCULO ---
def calcular_mejor_precio(minutos, es_camioneta, tiene_quinquela):
    # Descuento de 120 min si tiene Quinquela
    minutos_cobro = max(0, minutos - (120 if tiene_quinquela else 0))
    hora = 110 if not es_camioneta else 140
    promo_4h = 330 if not es_camioneta else 420
    dia = 500 if not es_camioneta else 650
    monto_hora = (minutos_cobro // 60 + 1) * hora
    return min(monto_hora, promo_4h if minutos_cobro > 60 else 99999, dia)

# --- MÓDULO INGRESO ---
if menu == "📥 Ingreso":
    patente = st.text_input("Matrícula:", key="in_pat").upper().replace("-", "").replace(" ", "")
    nombre_cli = st.text_input("Nombre Cliente:", key="in_nom")
    cel_cli = st.text_input("Celular:", value="598", key="in_cel")
    
    # Autocompletar al escribir la patente
    if patente and not nombre_cli:
        for rc in sh.worksheet("Clientes_Frecuentes").get_all_records():
            if str(rc.get("Matrícula", "")).upper().replace("-", "").replace(" ", "") == patente:
                st.session_state["in_nom"] = rc.get("Cliente", "")
                st.session_state["in_cel"] = str(rc.get("Celular", "")).strip()
    
    # ... resto del registro ...

# --- MÓDULO SALIDA ---
elif menu == "📤 Salida":
    st.subheader("Salida de Vehículo")
    reg = sh.worksheet("Registro").get_all_records()
    activos = [r for r in reg if not r.get("Hora_Salida") and str(r.get("Ticket")).upper() != "EXTRA"]
    
    seleccion = st.selectbox("Elegir:", [""] + [f"Tkt #{r['Ticket']} - {r.get('Matrícula', r.get('Matricula'))}" for r in activos])
    
    if seleccion:
        tkt_sel = seleccion.split(" - ")[0].replace("Tkt #", "")
        datos = next(r for r in activos if str(r.get("Ticket")) == tkt_sel)
        
        # Recuperar nombre/cel del registro
        nombre = datos.get("Servicios_Extras", "").replace("Cliente: ", "")
        cel = st.text_input("Celular:", value="598") # Aquí podrías buscar en Clientes_Frecuentes si quisieras
        
        if st.button("Generar Ticket"):
            patente = datos.get("Matrícula", datos.get("Matricula"))
            
            # Quinquela check (Buscar en fecha más reciente)
            q_data = sh.worksheet("Respuestas de formulario 1").get_all_records()
            val_quinquela = next((q for q in reversed(q_data) if str(q.get("PATENTE")).upper().replace("-","") == patente.upper()), None)
            
            hora_ing = datetime.strptime(datos.get("Hora_Ingreso"), "%Y-%m-%d %H:%M:%S")
            minutos = int((datetime.utcnow() - timedelta(hours=3) - hora_ing).total_seconds() / 60)
            
            monto = calcular_mejor_precio(minutos, "Camioneta" in datos.get("Estado", ""), val_quinquela is not None)
            
            texto = f"*FLOW PARK - TICKET EGRESO*\n🚗 Vehículo: {patente}\n⏱️ Estadía: {minutos//60}h {minutos%60}m\n💰 TOTAL: ${monto}\n\n¡Gracias {nombre}, por visitarnos! Te esperamos nuevamente."
            st.code(texto)
            # Marcar salida...
