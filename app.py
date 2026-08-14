import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN A PLANILLA MAESTRA ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    try: 
        return client.open("FlowPark_Valet_DB")
    except Exception as e:
        st.error(f"❌ Error al conectar con la base de datos: {e}")
        return None

sh = init_connection()

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- CARGA DE DATOS (CONFIG, TARIFAS Y EXTRAS) ---
def obtener_datos():
    tarifas_default = {
        "Hora": {"Auto": 110, "Camioneta": 140}, 
        "Promo_4h": {"Auto": 330, "Camioneta": 420}, 
        "Dia_Completo": {"Auto": 500, "Camioneta": 650}
    }
    extras_default = {"Lavado Premium": 500, "Bebida / Gaseosa": 100, "Agua Cortesia": 50, "Paraguas": 300}
    empleados_default = ["Valet 1", "Valet 2", "Encargado"]

    if not sh:
        return empleados_default, tarifas_default, extras_default

    try:
        ws_config = sh.worksheet("Configuracion")
        empleados = [e for e in ws_config.col_values(1)[1:] if e]
        if not empleados: empleados = empleados_default
    except:
        empleados = empleados_default

    try:
        ws_tarifas = sh.worksheet("Tarifas")
        tarifas = {r["Servicio"]: {"Auto": int(r["Precio_Auto"]), "Camioneta": int(r["Precio_Camioneta"])} for r in ws_tarifas.get_all_records()}
    except:
        tarifas = tarifas_default

    try:
        ws_extras = sh.worksheet("Extras")
        extras = {str(r["Producto"]).strip(): int(r["Precio"]) for r in ws_extras.get_all_records() if str(r.get("Producto", "")).strip()}
    except:
        extras = extras_default

    return empleados, tarifas, extras

empleados, tarifas_globales, extras_globales = obtener_datos()

# --- LÓGICA DE TARIFA INTELIGENTE (Con 2h Quinquela gratis) ---
def calcular_mejor_precio(minutos, es_camioneta, tiene_quinquela):
    tipo = "Camioneta" if es_camioneta else "Auto"
    minutos_cobro = max(0, minutos - (120 if tiene_quinquela else 0))
    
    costo_hora = (minutos_cobro // 60 + 1) * tarifas_globales.get("Hora", {}).get(tipo, 110)
    costo_promo = tarifas_globales.get("Promo_4h", {}).get(tipo, 330) if minutos_cobro > 60 else 99999
    costo_dia = tarifas_globales.get("Dia_Completo", {}).get(tipo, 500)
    
    return min(costo_hora, costo_promo, costo_dia)

# --- INTERFAZ PRINCIPAL ---
st.title("🚗 Flow Park - Operativa VIP")
if not sh: st.stop()

empleado_actual = st.selectbox("👤 Empleado a cargo:", empleados)
menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🍾 Extras", "📤 Salida"])

# ==========================================
# 1. INGRESO + TICKET
# ==========================================
if menu == "📥 Ingreso":
    st.subheader("Registro de Ingreso")
    patente = st.text_input("Matrícula (Ej: SDL567):", key="in_pat").upper().replace("-", "").replace(" ", "")
    
    # Autocompletado desde Clientes_Frecuentes
    nombre_sug, celular_sug = "", "598"
    if patente and sh:
        try:
            for rc in sh.worksheet("Clientes_Frecuentes").get_all_records():
                if str(rc.get("Matrícula", rc.get("Matricula", ""))).upper().replace("-", "").replace(" ", "") == patente:
                    nombre_sug = rc.get("Cliente", "")
                    celular_sug = str(rc.get("Celular", "")).strip() or "598"
                    break
        except: pass
    
    tarjeta = st.text_input("N° Tarjeta PVC:")
    nombre_cli = st.text_input("Nombre Cliente:", value=nombre_sug)
    cel_cli = st.text_input("Celular del cliente:", value=celular_sug)
    tipo_vehi = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
    
    if st.button("Registrar Ingreso"):
        if tarjeta and patente:
            try:
                reg = sh.worksheet("Registro").get_all_records()
                activo = any((str(r.get("Ticket")).strip().lstrip("0") == str(tarjeta).strip().lstrip("0") or 
                             str(r.get("Matricula", r.get("Matrícula"))).upper() == patente) 
                             and not str(r.get("Hora_Salida", "")).strip() for r in reg)
                
                if activo:
                    st.error("❌ ¡Esa tarjeta o patente ya se encuentra activa en playa!")
                else:
                    estado_txt = f"Estándar ({tipo_vehi}) - Op: {empleado_actual}"
                    sh.worksheet("Registro").append_row([str(tarjeta).strip(), patente, hora_actual_uy(), "", estado_txt, "", f"Cliente: {nombre_cli}", ""])
                    
                    try:
                        sh.worksheet("Clientes_Frecuentes").append_row([patente, nombre_cli, cel_cli])
                    except: pass
                    
                    st.success(f"✅ Ingreso registrado: {patente} | Tarjeta #{tarjeta}")
                    texto_wsp = f"*FLOW PARK - TICKET INGRESO*\n🚗 Vehículo: {patente}\n🎫 Tarjeta: #{tarjeta}\n¡Gracias por elegirnos!"
                    st.code(texto_wsp)
                    st.markdown(f"[📲 Enviar Ticket por WhatsApp](https://wa.me/{cel_cli}?text={urllib.parse.quote(texto_wsp)})")
            except Exception as e:
                st.error(f"Error al registrar: {e}")
        else:
            st.warning("Completa la tarjeta y la matrícula.")

# ==========================================
# 2. PANEL ACTIVOS
# ==========================================
elif menu == "📊 Activos":
    st.subheader("Vehículos en Playa")
    try:
        for r in reversed(sh.worksheet("Registro").get_all_records()):
            tkt = str(r.get("Ticket", ""))
            h_sal = str(r.get("Hora_Salida", "")).strip()
            if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
                st.info(f"🎫 Tarjeta #{tkt} | 🚗 {r.get('Matricula', r.get('Matrícula'))} | 🕒 Ingreso: {r.get('Hora_Ingreso')}")
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")

# ==========================================
# 3. QUINQUELA (Local)
# ==========================================
elif menu == "🔔 Quinquela":
    st.subheader("Validaciones del Salón Quinquela")
    try:
        for q in reversed(sh.worksheet("Respuestas de formulario 1").get_all_records()):
            marca_t = q.get("Marca temporal", q.get("Timestamp", "Hora no registrada"))
            mozo = q.get('MOZO - NOMBRE', 'Mozo')
            pat = q.get('PATENTE', '')
            tkt = q.get('NUMERO DE TARJETA', '')
            st.success(f"🕒 {marca_t} | 🍽️ Mozo: {mozo} | 🚗 Patente: {pat} | 🎫 Tarjeta: #{tkt}")
    except Exception as e:
        st.info("No hay registros o la pestaña de respuestas no está conectada aún.")

# ==========================================
# 4. EXTRAS
# ==========================================
elif menu == "🍾 Extras":
    st.subheader("Carga de Productos / Extras")
    tarjeta_extra = st.text_input("N° de Tarjeta PVC del vehículo:")
    extra_seleccionado = st.selectbox("Seleccionar Producto / Extra:", list(extras_globales.keys()))
    cantidad = st.number_input("Cantidad:", min_value=1, value=1, step=1)
    
    precio_unitario = extras_globales.get(extra_seleccionado, 0)
    total_extra = precio_unitario * cantidad
    st.info(f"Precio unitario: ${precio_unitario} | **Total: ${total_extra}**")
    
    if st.button("Sumar Extra a la Cuenta"):
        if tarjeta_extra:
            try:
                registros = sh.worksheet("Registro").get_all_records()
                t_clean = str(tarjeta_extra).strip().lstrip("0")
                patente_encontrada = ""
                for r in registros:
                    if str(r.get("Ticket", "")).strip().lstrip("0") == t_clean and not str(r.get("Hora_Salida", "")).strip():
                        patente_encontrada = r.get("Matricula", r.get("Matrícula"))
                        break
                
                if patente_encontrada:
                    sh.worksheet("Registro").append_row(["EXTRA", patente_encontrada, hora_actual_uy(), "", f"Extra - Tarjeta #{tarjeta_extra}", "EXTRA", f"{extra_seleccionado} x{cantidad}", total_extra])
                    try:
                        sh.worksheet("Control_Stock").append_row([hora_actual_uy(), extra_seleccionado, cantidad, empleado_actual, patente_encontrada])
                    except: pass
                    st.success(f"✅ Se agregó {extra_seleccionado} x{cantidad} (${total_extra}) al vehículo {patente_encontrada}.")
                else:
                    st.error("❌ No se encontró un vehículo activo con esa tarjeta.")
            except Exception as e:
                st.error(f"Error al registrar extra: {e}")
        else:
            st.warning("Ingresa el número de tarjeta.")

# ==========================================
# 5. SALIDA (Cálculo Inteligente y Ticket Final)
# ==========================================
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    
    # Selector inteligente filtrando solo activos
    registros_salida = sh.worksheet("Registro").get_all_records()
    activos_opciones = []
    mapa_activos = {}
    
    for r in registros_salida:
        tkt = str(r.get("Ticket", "")).strip()
        h_sal = str(r.get("Hora_Salida", "")).strip()
        if tkt.upper() != "EXTRA" and (not h_sal or h_sal.lower() == "nan"):
            pat = r.get("Matricula", r.get("Matrícula", "S/D"))
            etiqueta = f"Tarjeta #{tkt} - Patente: {pat}"
            if etiqueta not in mapa_activos:
                activos_opciones.append(etiqueta)
                mapa_activos[etiqueta] = tkt

    tarjeta_a_retirar = ""
    if activos_opciones:
        seleccion = st.selectbox("🚗 Seleccionar Vehículo Activo en Playa:", ["-- Seleccionar del listado --"] + activos_opciones)
        if seleccion != "-- Seleccionar del listado --":
            tarjeta_a_retirar = mapa_activos[seleccion]
    
    tarjeta_manual = st.text_input("O ingresa N° de Tarjeta PVC manualmente:", value=tarjeta_a_retirar)
    cel_salida = st.text_input("Celular del cliente para WhatsApp:", value="598")
    
    if st.button("Calcular y Generar Salida"):
        t_buscar = tarjeta_manual.strip().lstrip("0")
        if t_buscar:
            try:
                ws_reg = sh.worksheet("Registro")
                all_rows = ws_reg.get_all_records()
                
                fila_encontrada_idx = None
                datos_auto = None
                
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
                    serv_str = str(datos_auto.get("Servicios_Extras", ""))
                    nombre_cliente_ticket = serv_str.split("Cliente: ")[1] if "Cliente: " in serv_str else "Estimado cliente"
                    
                    hora_ing = datetime.strptime(datos_auto.get("Hora_Ingreso"), "%Y-%m-%d %H:%M:%S")
                    minutos = int((datetime.utcnow() - timedelta(hours=3) - hora_ing).total_seconds() / 60)
                    
                    # Verificación Quinquela local (última validación registrada para esa patente)
                    tiene_q = False
                    try:
                        q_data = sh.worksheet("Respuestas de formulario 1").get_all_records()
                        for q in reversed(q_data):
                            pat_q = str(q.get("PATENTE", "")).upper().replace("-","").replace(" ","")
                            if pat_q == patente.upper().replace("-","").replace(" ",""):
                                tiene_q = True
                                break
                    except:
                        tiene_q = False
                    
                    # Cálculo automático de estadía restando las 2h si tiene Quinquela
                    es_camioneta = "Camioneta" in datos_auto.get("Estado", "")
                    monto_estacionamiento = calcular_mejor_precio(minutos, es_camioneta, tiene_q)
                    
                    # Sumar extras pendientes
                    extras_auto = [r for r in all_rows if str(r.get("Ticket", "")).upper() == "EXTRA" and str(r.get("Matrícula", r.get("Matricula", ""))).upper() == patente.upper() and not str(r.get("Hora_Salida", "")).strip()]
                    detalle_extras = "\n".join([f"• {r.get('Servicios_Extras')} (${r.get('Total_Cobrado')})" for r in extras_auto])
                    total_extras = sum([float(r.get("Total_Cobrado", 0)) for r in extras_auto])
                    
                    total_a_pagar = monto_estacionamiento + total_extras
                    info_desc = "Incluye 2h libres de cortesía por Quinquela." if tiene_q else "Tarifa estándar aplicada."
                    
                    # Generar Ticket de Egreso personalizado
                    texto_ticket = f"""*FLOW PARK - TICKET DE EGRESO*
---------------------------------
🚗 Vehículo: {patente} | Tarjeta: #{t_buscar}
⏱️ Estadía total: {minutos//60}h {minutos%60}m
---------------------------------
📋 DETALLE:
{detalle_extras if detalle_extras else "Sin extras consumidos."}
Estacionamiento: ${monto_estacionamiento}
Total Extras: ${total_extras}
---------------------------------
💰 *TOTAL A PAGAR: ${total_a_pagar}*
ℹ️ {info_desc}
---------------------------------
Gracias {nombre_cliente_ticket} por visitarnos. ¡Te esperamos nuevamente!
"""
                    st.success("✅ ¡Cálculo y ticket generados con éxito!")
                    st.code(texto_ticket)
                    st.markdown(f"[📲 Enviar Ticket Final por WhatsApp](https://wa.me/{cel_salida}?text={urllib.parse.quote(texto_ticket)})")
                    
                    # Registrar salida en Google Sheets
                    ws_reg.update_cell(fila_encontrada_idx, 4, hora_actual_uy())
                    for idx_ex, r_ex in enumerate(all_rows, start=2):
                        if str(r_ex.get("Ticket", "")).upper() == "EXTRA" and str(r_ex.get("Matrícula", r_ex.get("Matricula", ""))).upper() == patente.upper() and not str(r_ex.get("Hora_Salida", "")).strip():
                            ws_reg.update_cell(idx_ex, 4, hora_actual_uy())
                            
            except Exception as e:
                st.error(f"Error al procesar salida: {e}")
        else:
            st.warning("⚠️ Selecciona o ingresa una tarjeta válida.")
