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
TEL_PARKING_1 = "59899123456" # <- REEMPLAZA POR EL CELULAR 1
TEL_PARKING_2 = "59899654321" # <- REEMPLAZA POR EL CELULAR 2

# --- CONEXIÓN Y CACHÉ ---
@st.cache_resource
def init_connection():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    return client.open("FlowPark_Valet_DB")

sh = init_connection()

@st.cache_data(ttl=15)
def obtener_datos():
    if not sh: return [], {}, {}, [], [], [], []
    conf = sh.worksheet("Configuracion").get_all_values()
    tarifas_raw = sh.worksheet("Tarifas").get_all_values()
    extras_raw = sh.worksheet("Extras").get_all_values()
    registro = sh.worksheet("Registro").get_all_values()
    q_data = sh.worksheet("Respuestas de formulario 1").get_all_values()
    cli = sh.worksheet("Clientes_Frecuentes").get_all_values()
    
    try:
        asistencia = sh.worksheet("Asistencia").get_all_values()
    except:
        asistencia = []
    
    empleados = [r[0] for r in conf[1:] if r[0]]
    tarifas = {r[0]: {"Auto": int(r[1]), "Camioneta": int(r[2])} for r in tarifas_raw[1:] if r[0]}
    extras = {r[0]: int(r[1]) for r in extras_raw[1:] if r[0]}
    return empleados, tarifas, extras, registro, q_data, cli, asistencia

empleados, tarifas, extras, reg, q_data, clientes, asistencia_data = obtener_datos()

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
        q_local = str(q[5]).strip() if len(q) > 5 else "Quinquela"
        
        try: q_dt = datetime.strptime(q_time_str, "%Y-%m-%d %H:%M:%S")
        except: continue
            
        if (q_tkt == tkt_clean or q_pat == pat_clean) and q_dt >= ingreso_dt:
            return q_local
    return None

def calcular_mejor_precio(minutos, es_camioneta, local_validacion):
    tipo = "Camioneta" if es_camioneta else "Auto"
    if local_validacion == "Rodrigo Bueno": return 0
    descuento = 150 if local_validacion in ["Quinquela", "Number 18"] else 0
    m_cobro = max(0, minutos - descuento)
    if m_cobro <= 0: return 0
        
    hora = tarifas.get("Hora", {}).get(tipo, 110)
    promo = tarifas.get("Promo_4h", {}).get(tipo, 330)
    dia = tarifas.get("Dia_Completo", {}).get(tipo, 500)
    
    monto_hora = ((m_cobro - 1) // 60 + 1) * hora
    return min(monto_hora, promo if m_cobro > 60 else 99999, dia)

def verificar_estado_empleado(nombre_emp, asistencia_rows):
    for row in reversed(asistencia_rows[1:]):
        if len(row) > 2 and str(row[1]).strip().lower() == str(nombre_emp).strip().lower():
            return str(row[2]).strip().capitalize()
    return "Salida"

# --- INTERFAZ ---
st.title("🚗 Flow Park - Operativa VIP")

lista_empleados_op = [""] + empleados
emp = st.selectbox("Empleado a cargo:", lista_empleados_op)

menu = st.radio("Módulo:", ["📥 Ingreso", "📊 Activos", "🔔 Quinquela", "🔔 Number 18", "🔔 Rodrigo Bueno", "🍾 Extras", "📤 Salida", "⏰ Personal"])

if not emp and menu != "⏰ Personal":
    st.warning("⚠️ Por favor, seleccione el empleado a cargo antes de operar.")
    st.stop()

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
                h_ing = hora_actual_uy()
                estado_txt = f"Estándar ({tipo_vehi}) - Op: {emp}"
                # Estructura limpia: Ticket, Matrícula, Ingreso, Salida, Estado, Detalle_Extras, Parking_Dinero, Extras_Dinero
                sh.worksheet("Registro").append_row([str(tkt).strip(), pat, h_ing, "", estado_txt, "", 0, 0])
                try: sh.worksheet("Clientes_Frecuentes").append_row([pat, cli, cel])
                except: pass
                
                st.success(f"✅ Ingreso registrado: {pat} | Tarjeta #{tkt}")
                msg_ingreso = f"*FLOW PARK - TICKET INGRESO*\n🚗 Vehículo: {pat}\n🎫 Tarjeta: #{tkt}\n🕒 Ingreso: {h_ing}\n¡Gracias {cli} por elegirnos!"
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
elif menu in ["🔔 Quinquela", "🔔 Number 18", "🔔 Rodrigo Bueno"]:
    local_actual = menu.replace("🔔 ", "")
    st.subheader(f"🍽️ Validación - {local_actual}")
    
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
    seleccion_mozo = st.selectbox("Seleccionar Vehículo en Playa:", opciones_mozo)
    
    if local_actual in ["Quinquela", "Number 18"]:
        mozo = st.text_input("Nombre del Mozo / Recepción:")
        factura = st.text_input("Últimos 4 dígitos de la factura:", max_chars=4)
    else:
        mozo = "Recepción RB"
        factura = "N/A"

    if st.button("Enviar Validación y Avisar al Parking"):
        if seleccion_mozo:
            if local_actual in ["Quinquela", "Number 18"] and (not mozo or len(factura) < 4):
                st.error("⚠️ Es obligatorio ingresar el nombre del mozo y los últimos 4 dígitos de la factura.")
            else:
                tkt_val = seleccion_mozo.split(" - ")[0].replace("#", "").strip()
                pat_val = next((r[1] for r in activos_disponibles if r[0].strip() == tkt_val), "")
                
                try:
                    sh.worksheet("Respuestas de formulario 1").append_row([hora_actual_uy(), mozo, tkt_val, pat_val, factura, local_actual])
                    st.success(f"✅ Validación de {local_actual} registrada para Tarjeta #{tkt_val}.")
                    
                    msg_aviso = urllib.parse.quote(f"⚠️ *VALIDACIÓN FLOW PARK*\n🚗 Vehículo: {pat_val} (Tkt #{tkt_val})\n🏪 Local: {local_actual}\n🧾 Factura: {factura}\n👤 Validado por: {mozo}")
                    
                    st.markdown("### 📲 Enviar alerta al equipo del Parking:")
                    st.markdown(f"[➡️ Avisar a Teléfono 1]({f'https://wa.me/{TEL_PARKING_1}?text={msg_aviso}'})", unsafe_allow_html=True)
                    st.markdown(f"[➡️ Avisar a Teléfono 2]({f'https://wa.me/{TEL_PARKING_2}?text={msg_aviso}'})", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error al conectar con la base de datos: {e}")
        else:
            st.error("Selecciona un vehículo de la lista.")

    st.divider()
    st.subheader(f"Historial de Validaciones - {local_actual}")
    for q in reversed(q_data[1:]):
        loc = str(q[5]) if len(q) > 5 else "Quinquela"
        if loc == local_actual:
            fac = str(q[4]) if len(q) > 4 else "N/A"
            if local_actual == "Rodrigo Bueno":
                st.write(f"🕒 {q[0]} | 🎫 Tkt: #{q[2]} | 🚗 Pat: {q[3]}")
            else:
                st.write(f"🕒 {q[0]} | 🍽️ Mozo: {q[1]} | 🧾 Fac: {fac} | 🎫 Tkt: #{q[2]} | 🚗 Pat: {q[3]}")

# ==========================================
# 4. EXTRAS
# ==========================================
elif menu == "🍾 Extras":
    st.subheader("Carga de Productos / Extras")
    
    activos_extras = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    opciones_extras = [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos_extras]
    
    sel_extra_veh = st.selectbox("Seleccionar Vehículo en Playa:", opciones_extras)
    
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
                    # Buscamos la fila del auto en el Excel para acumular el extra en LA MISMA FILA
                    for i, row in enumerate(reg, start=1):
                        if row[0].strip().lstrip("0") == tkt_elegido.lstrip("0") and (not row[3] or row[3].lower() == "nan"):
                            # Columna H (8) es Extras_Dinero. Sumamos al valor anterior si ya tenía.
                            actual_extras_dinero = float(row[7]) if len(row) > 7 and row[7] and row[7] != "" else 0
                            nuevo_extras_dinero = actual_extras_dinero + total_extra
                            
                            # Columna F (6) es Detalle_Extras. Acumulamos el texto.
                            actual_detalle = str(row[5]) if len(row) > 5 and row[5] else ""
                            nuevo_detalle = f"{actual_detalle} | {prod} x{cantidad}".strip(" | ")
                            
                            sh.worksheet("Registro").update_cell(i, 8, float(nuevo_extras_dinero))
                            sh.worksheet("Registro").update_cell(i, 6, nuevo_detalle)
                            break
                    
                    # Registramos el movimiento en el stock físico de los empleados
                    sh.worksheet("Control_Stock").append_row([hora_actual_uy(), str(prod), int(cantidad), str(emp), str(patente_encontrada)])
                    st.success(f"✅ Se agregó {prod} x{cantidad} (${total_extra}) al vehículo {patente_encontrada}.")
                except Exception as e:
                    st.error(f"⚠️ Error al guardar. Detalle: {e}")
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
            h_salida = hora_actual_uy()
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            
            local_val = obtener_validacion_local(patente, tkt, h_ingreso, q_data)
            es_camioneta = "Camioneta" in datos[4]
            monto_estacionamiento = calcular_mejor_precio(mins, es_camioneta, local_val)
            
            # Como los extras ya se sumaron en la columna H (índice 7) al cargarlos, los leemos de la fila del auto
            total_extras = float(datos[7]) if len(datos) > 7 and datos[7] and datos[7] != "" else 0
            detalle_extras_txt = str(datos[5]) if len(datos) > 5 and datos[5] else "Sin extras consumidos."
            
            total_a_pagar = monto_estacionamiento + total_extras
            
            if local_val == "Rodrigo Bueno": info_desc = "Estacionamiento 100% bonificado por Rodrigo Bueno."
            elif local_val: info_desc = f"Incluye 2.5h libres de cortesía por {local_val}."
            else: info_desc = "Tarifa estándar aplicada."
            
            serv_str = str(datos[6])
            nombre_cliente = serv_str.split("Cliente: ")[1] if "Cliente: " in serv_str else "estimado cliente"
            operador = datos[4].split("Op: ")[1] if "Op: " in datos[4] else "Desconocido"
            
            texto_ticket = f"""*FLOW PARK - TICKET DE EGRESO*
---------------------------------
🚗 Vehículo: {patente} | Tarjeta: #{tkt}
🕒 Ingreso: {h_ingreso}
🕒 Salida:  {h_salida}
⏱️ Estadía total: {mins//60}h {mins%60}m
---------------------------------
📋 DETALLE:
{detalle_extras_txt}
Estacionamiento: ${monto_estacionamiento}
Total Extras: ${total_extras}
---------------------------------
💰 *TOTAL A PAGAR: ${total_a_pagar}*
ℹ️ {info_desc}
---------------------------------
Gracias {nombre_cliente} por visitarnos. ¡Te esperamos nuevamente!
"""
            # Actualización limpia en Google Sheets (Usando 'row' correctamente)
            try:
                for i, row in enumerate(reg, start=1):
                    if row[0].strip() == tkt and (not row[3] or row[3].lower() == "nan"):
                        sh.worksheet("Registro").update_cell(i, 4, h_salida) # Hora Salida (Col D)
                        sh.worksheet("Registro").update_cell(i, 7, float(monto_estacionamiento)) # Parking Dinero (Col G)
                        break
            except Exception as e:
                st.warning(f"Aviso de sincronización: {e}")

            st.success("✅ ¡Cálculo y ticket generados con éxito!")
            st.code(texto_ticket)
            st.markdown(f"[📲 Enviar Ticket Final por WhatsApp](https://wa.me/{cel_salida}?text={urllib.parse.quote(texto_ticket)})")
# ==========================================
# 6. PERSONAL (Control de Asistencia con Tiempos Diferenciados)
# ==========================================
elif menu == "⏰ Personal":
    st.subheader("Control de Horarios y Asistencia")
    
    if not emp:
        st.warning("⚠️ Selecciona primero el empleado a cargo en la parte superior de la página.")
    else:
        ultimo_estado = verificar_estado_empleado(emp, asistencia_data)
        
        st.info(f"👤 Empleado: **{emp}** | Estado actual según registros: **{ultimo_estado}**")
        
        if ultimo_estado == "Entrada":
            accion_permitida = "Salida"
            st.warning("⚠️ Ya tienes una entrada registrada. Para finalizar tu turno, completa el stock final y registra tu Salida.")
        else:
            accion_permitida = "Entrada"
            st.success("✅ Estás fuera de turno. Para registrar tu Entrada, completa el stock inicial.")

        accion = st.radio("Acción a registrar:", [accion_permitida])
        
        st.markdown("---")
        st.subheader(f"📝 Control de Stock ({'Inicial' if accion == 'Entrada' else 'Final'}) Requerido")
        
        if accion == "Entrada":
            st.info("💡 *Nota de Entrada:* Al confirmar, tu hora de ingreso real será el momento en que abriste este módulo (respetando el tiempo que te llevó hacer el inventario).")
        else:
            st.info("💡 *Nota de Salida:* Al ser parte de tus tareas, tu hora de salida final quedará registrada exactamente en el momento en que confirmes este inventario de cierre.")
        
        conteo_stock = {}
        for prod_nombre in list(extras.keys()):
            conteo_stock[prod_nombre] = st.number_input(f"Cantidad física actual de [{prod_nombre}]:", min_value=0, value=0, step=1, key=f"stock_{accion}_{prod_nombre}")
            
        nota_stock = st.text_input("Observaciones del stock (Opcional):")

        if st.button(f"Confirmar Stock y Registrar {accion}"):
            try:
                hora_fichada = hora_actual_uy()
            
                # 1. Guardar el reporte de stock en Control_Stock
                for prod_nombre, cant in conteo_stock.items():
                    sh.worksheet("Control_Stock").append_row([hora_fichada, f"Inventario_{accion}_{prod_nombre}", int(cant), str(emp), nota_stock])
                
                # 2. Registrar la asistencia en la pestaña 'Asistencia'
                sh.worksheet("Asistencia").append_row([hora_fichada, str(emp), accion, f"Inventario {accion} completado"])
                
                st.success(f"✅ ¡Inventario {'inicial' if accion == 'Entrada' else 'final'} verificado y **{accion}** registrada correctamente para {emp} a las {hora_fichada}!")
            except Exception as e:
                st.error(f"⚠️ Error al guardar en Google Sheets. Verifica que existan las pestañas 'Asistencia' y 'Control_Stock'. Detalle: {e}")
