import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Flow Park - Operativa VIP", layout="centered")

# --- CONEXIÓN A PLANILLAS ---
@st.cache_resource
def init_connections():
    creds_dict = st.secrets["gcp_service_account"]
    client = gspread.service_account_from_dict(creds_dict)
    
    try:
        sh_valet = client.open("FlowPark_Valet_DB")
    except Exception as e:
        st.error(f"❌ Error al abrir la planilla principal: {e}")
        sh_valet = None

    try:
        sh_quinquela = client.open_by_key("18ufUYyHmDbqAb74Cu2mS7i6L6JBRJZQyxoR10GBOwaM")
    except Exception:
        sh_quinquela = None
        
    return sh_valet, sh_quinquela

sh, sh_quinquela = init_connections()

# --- HORA LOCAL URUGUAY (UTC -3) ---
def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# --- CARGA DE DATOS INICIALES ---
empleados = ["Valet 1", "Valet 2", "Encargado"]
if sh:
    try:
        ws_config = sh.worksheet("Configuracion")
        empleados_db = ws_config.col_values(1)[1:] 
        if empleados_db: empleados = [e for e in empleados_db if e]
    except: pass

dict_tarifas = {"Lavado Premium": 500, "Bebida / Gaseosa": 100, "Agua Cortesia": 50, "Paraguas": 300}
if sh:
    try:
        ws_tarifas = sh.worksheet("Tarifas_y_Extras")
        tarifas_data = ws_tarifas.get_all_records()
        dict_tarifas = {str(row['Servicio']).strip(): int(row['Precio']) for row in tarifas_data if str(row['Servicio']).strip()}
    except: pass

st.title("🚗 Flow Park - Operativa VIP")
if not sh: st.stop()

empleado_actual = st.selectbox("👤 Empleado a cargo:", empleados)
menu = st.radio("Módulo:", [
    "📥 Ingreso de Vehículo", 
    "🔔 Alertas y Panel Quinquela", 
    "🍾 Venta y Corrección de Extras", 
    "📤 Salida y Cómputo Final"
])

# ==========================================
# 1. INGRESO
# ==========================================
if menu == "📥 Ingreso de Vehículo":
    st.subheader("Registro de Ingreso y Creación de Base de Clientes")
    
    patente_input = st.text_input("Matrícula del Vehículo (Ej: SDL567)", key="ing_patente")
    patente_limpia = patente_input.upper().replace("-", "").replace(" ", "") if patente_input else ""
    
    cliente_sugerido = ""
    celular_sugerido = ""
    if patente_limpia and sh:
        try:
            ws_cli = sh.worksheet("Clientes_Frecuentes")
            for rc in ws_cli.get_all_records():
                if str(rc.get("Matrícula")).upper().replace("-", "").replace(" ", "") == patente_limpia:
                    cliente_sugerido = rc.get("Cliente", "")
                    celular_sugerido = str(rc.get("Celular", ""))
                    break
        except:
            pass

    tarjeta = st.text_input("N° de Tarjeta PVC (Ej: 045)", key="ing_tarjeta")
    nombre_cliente = st.text_input("Nombre y Apellido del Cliente:", value=cliente_sugerido, key="ing_nombre")
    celular = st.text_input("Celular del cliente (Ej: 59899123456):", value=celular_sugerido, key="ing_celular")
    tipo_cli = st.selectbox("Tipo de Cliente:", ["Estándar", "Mensualista VIP (Costo $0)"], key="ing_tipo")
    tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"], key="ing_vehi")
    
    if st.button("Registrar Ingreso"):
        if tarjeta and patente_limpia:
            hora_act = hora_actual_uy()
            estado_texto = f"{tipo_cli} ({tipo_vehiculo}) - Op: {empleado_actual}"
            
            registros = sh.worksheet("Registro").get_all_records()
            t_clean = str(tarjeta).strip().lstrip("0")
            activo_existente = any(str(r.get("Ticket")).strip().lstrip("0") == t_clean and not r.get("Hora_Salida") for r in registros)
            
            if activo_existente:
                st.error(f"❌ La tarjeta #{tarjeta} ya tiene un vehículo activo asignado.")
            else:
                sh.worksheet("Registro").append_row([
                    str(tarjeta).strip(), patente_limpia, hora_act, "", 
                    estado_texto, "", "", ""
                ])
                
                try:
                    ws_cli = sh.worksheet("Clientes_Frecuentes")
                    rows_cli = ws_cli.get_all_records()
                    existe = any(str(r.get("Matrícula")).upper().replace("-", "").replace(" ", "") == patente_limpia for r in rows_cli)
                    if not existe and nombre_cliente:
                        ws_cli.append_row([patente_limpia, nombre_cliente, celular])
                except:
                    pass

                st.success(f"✅ Ingreso registrado: Patente {patente_limpia} | Tarjeta #{tarjeta} | Cliente: {nombre_cliente or 'No especificado'}")
                
                if celular:
                    texto_wsp = f"¡Bienvenido a Distrito El Globo y Flow Park! Su vehículo {patente_limpia} ha sido registrado con éxito. Tarjeta #{tarjeta}. ¡Gracias por confiar en nosotros!"
                    st.markdown(f"[📲 Enviar Ticket de Ingreso por WhatsApp](https://wa.me/{celular}?text={urllib.parse.quote(texto_wsp)})")
        else:
            st.warning("⚠️ Completa al menos el número de tarjeta y la matrícula.")

# ==========================================
# 2. PANEL DE ALERTAS Y QUINQUELA
# ==========================================
elif menu == "🔔 Alertas y Panel Quinquela":
    st.subheader("🔔 Panel de Alertas y Validación de Salón en Vivo")
    
    try:
        registros = sh.worksheet("Registro").get_all_records()
        autos_activos = [r for r in registros if not r.get("Hora_Salida") and str(r.get("Ticket")) != "EXTRA"]
        
        patentes_quinquela = []
        if sh_quinquela:
            try:
                ws_q = sh_quinquela.worksheet("QUINQUELA - FLOW PARK")
                patentes_quinquela = [str(p).upper().replace("-", "").replace(" ", "") for p in ws_q.col_values(3)]
            except:
                pass

        if autos_activos:
            hay_validados = any(str(a.get("Matrícula")).upper().replace("-", "").replace(" ", "") in patentes_quinquela for a in autos_activos)
            
            if hay_validados:
                st.markdown('<audio autoplay><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg"></audio>', unsafe_allow_html=True)
                st.warning("🚨 **¡ALERTA DE SALÓN!** Hay vehículos con **Validación Quinquela** listos en rampa[cite: 1].")

            for auto in autos_activos:
                pat = str(auto.get("Matrícula"))
                tkt = auto.get("Ticket")
                ing = auto.get("Hora_Ingreso")
                
                es_validado = pat.upper().replace("-", "").replace(" ", "") in patentes_quinquela
                
                if es_validado:
                    st.markdown(f"""
                    <div style="padding: 12px; border: 2px solid #28a745; border-radius: 8px; background-color: #d4edda; margin-bottom: 10px;">
                        🚗 <b>Matrícula:</b> {pat} &nbsp;|&nbsp; 🎫 <b>Tarjeta:</b> #{tkt} &nbsp;|&nbsp; 🕒 <b>Ingreso:</b> {ing} <br><br>
                        <span style="background-color: #28a745; color: white; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 14px;">✔ VALIDADO QUINQUELA (2h libres)</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="padding: 10px; border: 1px solid #ccc; border-radius: 8px; background-color: #f8f9fa; margin-bottom: 10px;">
                        🚗 <b>Matrícula:</b> {pat} &nbsp;|&nbsp; 🎫 <b>Tarjeta:</b> #{tkt} &nbsp;|&nbsp; 🕒 <b>Ingreso:</b> {ing} <br>
                        <span style="color: #6c757d;">Estado: Estándar</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No hay vehículos estacionados activos en este momento.")
    except Exception as e:
        st.error(f"Error al cargar el panel de alertas: {e}")

# ==========================================
# 3. EXTRAS Y CORRECCIÓN
# ==========================================
elif menu == "🍾 Venta y Corrección de Extras":
    st.subheader("Gestión y Corrección de Consumibles")
    
    sub_menu = st.radio("Acción:", ["➕ Sumar Extra", "❌ Anular / Borrar Extra Cargado Por Error"], key="sub_menu_extras")
    
    if sub_menu == "➕ Sumar Extra":
        tarjeta_extra = st.text_input("N° de Tarjeta PVC del Vehículo:", key="ext_tarjeta")
        extra_tipo = st.selectbox("Servicio o Producto:", list(dict_tarifas.keys()), key="ext_tipo")
        cantidad = st.number_input("Cantidad:", min_value=1, value=1, step=1, key="ext_cant")
        
        precio_unitario = dict_tarifas.get(extra_tipo, 0)
        total_linea = precio_unitario * cantidad
        
        st.info(f"Precio unitario: ${precio_unitario} | **Total a sumar: ${total_linea}**")
        
        if st.button("Sumar Extra a la Cuenta"):
            if tarjeta_extra:
                try:
                    registros = sh.worksheet("Registro").get_all_records()
                    t_clean = str(tarjeta_extra).strip().lstrip("0")
                    fila_activa = next((r for r in registros if str(r.get("Ticket")).strip().lstrip("0") == t_clean and not r.get("Hora_Salida")), None)
                    
                    if not fila_activa:
                        st.error(f"❌ No se encontró un vehículo activo con la tarjeta #{tarjeta_extra}.")
                    else:
                        patente_encontrada = fila_activa.get("Matrícula")
                        hora_act = hora_actual_uy()
                        
                        # GUARDAMOS USANDO EL NÚMERO DE TARJETA REAL PARA QUE LA SALIDA LO TOME AUTOMÁTICAMENTE
                        sh.worksheet("Registro").append_row([
                            str(tarjeta_extra).strip(), 
                            patente_encontrada, 
                            hora_act, 
                            "", 
                            f"Extra - Op: {empleado_actual}", 
                            "EXTRA", 
                            f"{extra_tipo} x{cantidad}", 
                            total_linea
                        ])
                        
                        try:
                            sh.worksheet("Control_Stock").append_row([hora_act, extra_tipo, cantidad, empleado_actual, patente_encontrada])
                        except:
                            pass
                        
                        st.success(f"✅ Se agregaron {cantidad}x '{extra_tipo}' (${total_linea}) a la tarjeta #{tarjeta_extra} ({patente_encontrada}).")
                except Exception as ex:
                    st.error(f"Error al registrar el extra: {ex}")
            else:
                st.warning("⚠️ Ingresa el número de tarjeta.")
                
    else:
        st.markdown("### ❌ Anular un extra cargado por error")
        tarjeta_anular = st.text_input("N° de Tarjeta PVC para revisar extras:", key="anular_tarjeta")
        if tarjeta_anular:
            try:
                ws_reg = sh.worksheet("Registro")
                all_rows = ws_reg.get_all_records()
                t_clean = str(tarjeta_anular).strip().lstrip("0")
                
                fila_ingreso = next((r for r in all_rows if str(r.get("Ticket")).strip().lstrip("0") == t_clean and not r.get("Hora_Salida")), None)
                
                if fila_ingreso:
                    patente_auto = fila_ingreso.get("Matrícula")
                    st.info(f"Vehículo vinculado: **{patente_auto}** (Tarjeta #{tarjeta_anular})")
                    
                    extras_activos = []
                    for idx, r in enumerate(all_rows, start=2):
                        if str(r.get("Ticket")).strip().lstrip("0") == t_clean and str(r.get("Factura_Quinquela")) == "EXTRA" and not r.get("Hora_Salida"):
                            extras_activos.append((idx, r.get("Servicios_Extras"), r.get("Total_Cobrado"), r.get("Hora_Ingreso")))
                    
                    if extras_activos:
                        st.write("Selecciona el extra que deseas **eliminar/anular**:")
                        for idx, desc, precio, hora in extras_activos:
                            col1, col2 = st.columns([3, 1])
                            col1.text(f"[{hora}] {desc} - ${precio}")
                            if col2.button("🗑️ Borrar", key=f"del_{idx}"):
                                ws_reg.delete_rows(idx)
                                st.success(f"¡Extra eliminado correctamente! Recarga la página.")
                                st.rerun()
                    else:
                        st.info("No se encontraron extras cargados para este vehículo.")
                else:
                    st.error("No se encontró un vehículo activo con ese número de tarjeta.")
            except Exception as e:
                st.error(f"Error al buscar extras: {e}")

# ==========================================
# 4. SALIDA Y TICKET OFICIAL
# ==========================================
elif menu == "📤 Salida y Cómputo Final":
    st.subheader("Cómputo de Egreso y Liquidación Automática")
    
    tarjeta_salida = st.text_input("N° de Tarjeta PVC a devolver:", key="salida_tarjeta")
    
    celular_sugerido = ""
    patente_encontrada_auto = ""
    if tarjeta_salida and sh:
        try:
            t_clean = str(tarjeta_salida).strip().lstrip("0")
            registros_temp = sh.worksheet("Registro").get_all_records()
            for r in registros_temp:
                if str(r.get("Ticket")).strip().lstrip("0") == t_clean and not r.get("Hora_Salida") and str(r.get("Factura_Quinquela")) != "EXTRA":
                    patente_encontrada_auto = r.get("Matrícula")
                    break
            
            if patente_encontrada_auto:
                ws_cli = sh.worksheet("Clientes_Frecuentes")
                for rc in ws_cli.get_all_records():
                    if str(rc.get("Matrícula")).upper().replace("-", "").replace(" ", "") == patente_encontrada_auto.upper().replace("-", "").replace(" ", ""):
                        celular_sugerido = str(rc.get("Celular", ""))
                        break
        except:
            pass

    celular = st.text_input("Celular del cliente para el Ticket:", value=celular_sugerido, key="salida_celular")
    if patente_encontrada_auto:
        st.info(f"🚗 Vehículo vinculado detectado automáticamente: **{patente_encontrada_auto}**")

    if st.button("Calcular Salida y Generar Ticket"):
        if tarjeta_salida and celular:
            try:
                registros = sh.worksheet("Registro").get_all_records()
                t_clean = str(tarjeta_salida).strip().lstrip("0")
                
                # Buscar la fila de ingreso (excluyendo los extras)
                fila_ingreso = next((r for r in registros if str(r.get("Ticket")).strip().lstrip("0") == t_clean and not r.get("Hora_Salida") and str(r.get("Factura_Quinquela")) != "EXTRA"), None)
                
                if not fila_ingreso:
                    st.error("❌ No se encontró un vehículo activo con ese número de tarjeta.")
                else:
                    patente_limpia = fila_ingreso.get("Matrícula")
                    hora_ingreso_str = fila_ingreso.get("Hora_Ingreso")
                    estado_ingreso = str(fila_ingreso.get("Estado", ""))
                    es_mensualista = "Mensualista VIP" in estado_ingreso
                    
                    hora_ingreso = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
                    hora_salida = datetime.utcnow() - timedelta(hours=3) # Hora local Uruguay
                    minutos_totales = int((hora_salida - hora_ingreso).total_seconds() / 60)
                    
                    tiene_quinquela = False
                    if not es_mensualista and sh_quinquela:
                        try:
                            ws_q = sh_quinquela.worksheet("QUINQUELA - FLOW PARK")
                            patentes_q = [str(p).upper().replace("-", "").replace(" ", "") for p in ws_q.col_values(3)]
                            if patente_limpia in patentes_q:
                                tiene_quinquela = True
                        except:
                            pass
                    
                    minutos_bonificados = 120 if tiene_quinquela else 0
                    minutos_a_cobrar = max(0, minutos_totales - minutos_bonificados)
                    
                    monto_estacionamiento = 0
                    if not es_mensualista and minutos_a_cobrar > 0:
                        monto_estacionamiento = (minutos_a_cobrar // 30 + 1) * 150

                    # Buscar todos los extras de esta tarjeta exacta que aún no tienen salida
                    extras_auto = [r for r in registros if str(r.get("Ticket")).strip().lstrip("0") == t_clean and str(r.get("Factura_Quinquela")) == "EXTRA" and not r.get("Hora_Salida")]
                    
                    detalle_extras_txt = "\n".join([f"• {r.get('Servicios_Extras')} (${r.get('Total_Cobrado')})" for r in extras_auto])
                    total_extras = sum([float(r.get("Total_Cobrado", 0)) for r in extras_auto])
                    
                    total_a_pagar = 0 if es_mensualista else (monto_estacionamiento + total_extras)
                    
                    if es_mensualista:
                        desc_texto = "Cliente Mensualista VIP (Costo $0)."
                    elif tiene_quinquela:
                        desc_texto = "Incluye 2 horas libres de cortesía por Restaurante Quinquela."
                    else:
                        desc_texto = "Tarifa estándar aplicada."

                    texto_ticket = f"""
*FLOW PARK - TICKET DE EGRESO*
---------------------------------
🚗 Vehículo: {patente_limpia} | Tarjeta: #{tarjeta_salida}
⏱️ Tiempo total de estadía: {minutos_totales // 60}h {minutos_totales % 60}m
---------------------------------
📋 DETALLE DE CONSUMOS Y TARIFAS:
{detalle_extras_txt if detalle_extras_txt else "Sin extras consumidos."}
Estacionamiento excedente: ${monto_estacionamiento}
Total Extras: ${total_extras}
---------------------------------
💰 *TOTAL A ABONAR: ${total_a_pagar}*
ℹ️ {desc_texto}
---------------------------------
Flow Park le agradece por visitar Distrito El Globo y Restaurante Quinquela. ¡Buen viaje!
"""
                    st.success("✅ ¡Cálculo de egreso realizado con éxito!")
                    st.code(texto_ticket, language="markdown")
                    
                    link_wsp = f"https://wa.me/{celular}?text={urllib.parse.quote(texto_ticket)}"
                    st.markdown(f"### [📲 HAGA CLIC AQUÍ PARA ENVIAR EL TICKET POR WHATSAPP]({link_wsp})", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error al procesar la salida: {e}")
        else:
            st.warning("⚠️ Ingresa el número de tarjeta y el celular del cliente.")
