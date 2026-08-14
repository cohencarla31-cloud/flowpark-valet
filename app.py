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
    minutos_cobro = max(0, minutos - (120 if tiene_quinquela else 0))
    hora = 110 if not es_camioneta else 140
    promo_4h = 330 if not es_camioneta else 420
    dia = 500 if not es_camioneta else 650
    
    monto_hora = (minutos_cobro // 60 + 1) * hora
    monto_final = min(monto_hora, promo_4h if minutos_cobro > 60 else 99999, dia)
    return monto_final

# --- CARGA DE DATOS ---
empleados = ["Valet 1", "Valet 2", "Encargado"]
if sh:
    try: empleados = [e for e in sh.worksheet("Configuracion").col_values(1)[1:] if e]
    except: pass

st.title("🚗 Flow Park - Operativa VIP")
empleado_actual = st.selectbox("👤 Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# 1. INGRESO
if menu == "📥 Ingreso":
    patente = st.text_input("Matrícula (Ej: SDL567):").upper().replace("-", "").replace(" ", "")
    tarjeta = st.text_input("N° Tarjeta:")
    nombre_cli = st.text_input("Nombre del Cliente:")
    cel_cli = st.text_input("Celular del cliente:", value="598")
    
    if st.button("Registrar Ingreso"):
        if tarjeta and patente:
            reg = sh.worksheet("Registro").get_all_records()
            activo = any((str(r.get("Ticket")).strip() == tarjeta.strip() or 
                         str(r.get("Matricula", r.get("Matrícula"))).upper() == patente) 
                         and not r.get("Hora_Salida") for r in reg)
            
            if activo:
                st.error("❌ ¡Esa tarjeta o patente ya está en playa!")
            else:
                sh.worksheet("Registro").append_row([tarjeta, patente, hora_actual_uy(), "", f"Ingreso - {empleado_actual}", "", f"Cliente: {nombre_cli}", ""])
                try: sh.worksheet("Clientes_Frecuentes").append_row([patente, nombre_cli, cel_cli])
                except: pass
                
                st.success(f"✅ Ingreso: {patente} | Tarjeta #{tarjeta}")
                texto = f"*FLOW PARK - TICKET INGRESO*\n🚗 Vehículo: {patente}\n🎫 Tarjeta: #{tarjeta}\n¡Gracias {nombre_cli} por elegirnos!"
                st.code(texto)
                st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_cli}?text={urllib.parse.quote(texto)})")
        else: st.error("Completa campos obligatorios.")

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
        for r in sh.worksheet("Registro").get_all_records():
            if str(r.get("Ticket")).strip() == tarjeta.strip() and not r.get("Hora_Salida"):
                patente = r.get("Matricula", r.get("Matrícula"))
                sh.worksheet("Registro").append_row(["EXTRA", patente, hora_actual_uy(), "", f"Extra-{extra}", "EXTRA", extra, "0"])
                st.success(f"✅ {extra} agregado a {patente}.")
                break

# 5. SALIDA (Corregido y optimizado)
elif menu == "📤 Salida":
    st.subheader("Selección de Vehículo a Retirar")
    
    # Cargamos registros para armar el desplegable con los activos
    registros_salida = sh.worksheet("Registro").get_all_records()
    activos_opciones = []
    mapa_activos = {}
    
    for r in registros_salida:
        tkt = str(r.get("Ticket", "")).strip()
        h_sal = str(r.get("Hora_Salida", "")).strip()
        if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
            pat = r.get("Matricula", r.get("Matrícula", "S/D"))
            etiqueta = f"Tarjeta #{tkt} - Patente: {pat}"
            activos_opciones.append(etiqueta)
            mapa_activos[etiqueta] = tkt

    tarjeta_a_retirar = ""
    if activos_opciones:
        seleccion = st.selectbox("🚗 Seleccionar de la lista de playa:", ["-- Seleccionar vehículo --"] + activos_opciones)
        if seleccion != "-- Seleccionar vehículo --":
            tarjeta_a_retirar = mapa_activos[seleccion]
    
    tarjeta_manual = st.text_input("O ingresa N° de Tarjeta manualmente:", value=tarjeta_a_retirar)
    cel_cli = st.text_input("Celular para enviar Ticket de Egreso:", value="598")
    
    if st.button("Calcular y Cerrar Salida"):
        t_buscar = tarjeta_manual.strip().lstrip("0")
        if t_buscar:
            try:
                ws_reg = sh.worksheet("Registro")
                all_rows = ws_reg.get_all_records()
                
                fila_encontrada_idx = None
                datos_auto = None
                
                # Buscamos la fila exacta recorriendo desde la fila 2
                for idx, row in enumerate(all_rows, start=2):
                    t_val = str(row.get("Ticket", "")).strip().lstrip("0")
                    h_sal = str(row.get("Hora_Salida", "")).strip()
                    if t_val == t_buscar and (not h_sal or h_sal.lower() == "nan") and row.get("Ticket") != "EXTRA":
                        fila_encontrada_idx = idx
                        datos_auto = row
                        break
                
                if not datos_auto or not fila_encontrada_idx:
                    st.error("❌ No se encontró un vehículo activo con esa tarjeta.")
                else:
                    patente = datos_auto.get("Matricula", datos_auto.get("Matrícula"))
                    hora_ing = datetime.strptime(datos_auto.get("Hora_Ingreso"), "%Y-%m-%d %H:%M:%S")
                    minutos = int((datetime.utcnow() - timedelta(hours=3) - hora_ing).total_seconds() / 60)
                    
                    # Chequear Quinquela
                    try:
                        q_data = sh.worksheet("Respuestas de formulario 1").get_all_records()
                        tiene_q = any(str(q.get("PATENTE", "")).upper().replace("-","").replace(" ","") == patente.upper() for q in q_data)
                    except:
                        tiene_q = False
                    
                    # Calcular precio
                    es_camioneta = "Camioneta" in datos_auto.get("Estado", "")
                    monto = calcular_mejor_precio(minutos, es_camioneta, tiene_q)
                    
                    # Mostrar Ticket
                    texto = f"*FLOW PARK - TICKET EGRESO*\n🚗 Vehículo: {patente}\n⏱️ Estadía: {minutos//60}h {minutos%60}m\n💰 TOTAL: ${monto}\n{'_Beneficio Quinquela aplicado (2h gratis)_' if tiene_q else ''}"
                    st.code(texto)
                    st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_cli}?text={urllib.parse.quote(texto)})")
                    
                    # Actualizar celda de salida de forma segura usando el índice exacto
                    ws_reg.update_cell(fila_encontrada_idx, 4, hora_actual_uy())
                    st.success(f"✅ ¡Salida registrada con éxito para la tarjeta #{t_buscar}!")
                    
            except Exception as e:
                st.error(f"Error al procesar la salida: {e}")
        else:
            st.warning("⚠️ Selecciona o ingresa una tarjeta válida.")
