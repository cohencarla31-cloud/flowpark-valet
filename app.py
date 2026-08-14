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
    "🍾 Venta de Extras y Stock", 
    "📤 Salida y Cómputo Final"
])

# ==========================================
# 1. INGRESO (Con memoria de clientes)
# ==========================================
if menu == "📥 Ingreso de Vehículo":
    st.subheader("Registro de Ingreso y Creación de Base de Clientes")
    
    patente_input = st.text_input("Matrícula del Vehículo (Ej: SDL567)")
    patente_limpia = patente_input.upper().replace("-", "").replace(" ", "") if patente_input else ""
    
    # Memoria inteligente: buscar si ya existe en clientes frecuentes
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

    tarjeta = st.text_input("N° de Tarjeta PVC (Ej: 045)")
    nombre_cliente = st.text_input("Nombre y Apellido del Cliente:", value=cliente_sugerido)
    celular = st.text_input("Celular del cliente (Ej: 59899123456):", value=celular_sugerido)
    tipo_cli = st.selectbox("Tipo de Cliente:", ["Estándar", "Mensualista VIP (Costo $0)"])
    tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Auto", "Camioneta"])
    
    if st.button("Registrar Ingreso"):
        if tarjeta and patente_limpia:
            hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            estado_texto = f"{tipo_cli} ({tipo_vehiculo}) - Op: {empleado_actual}"
            
            # Guardar en hoja Registro
            sh.worksheet("Registro").append_row([
                tarjeta, patente_limpia, hora_actual, "", 
                estado_texto, "", "", ""
            ])
            
            # Guardar / Actualizar en Clientes_Frecuentes (Matrícula | Cliente | Celular)
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
# 2. PANEL DE ALERTAS Y QUINQUELA (Con Sonido)
# ==========================================
elif menu == "🔔 Alertas y Panel Quinquela":
    st.subheader("🔔 Panel de Alertas y Validación de Salón en Vivo")
    
    try:
        registros = sh.worksheet("Registro").get_all_records()
        autos_activos = [r for r in registros if not r.get("Hora_Salida") and str(r.get("Ticket")) != "EXTRA"]
        
        # Consultar respuestas del formulario de Quinquela en tiempo real (usando el nombre exacto de tu hoja)
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
# 3. EXTRAS, CANTIDAD Y CONTROL DE STOCK
# ==========================================
elif menu == "🍾 Venta de Extras y Stock":
    st.subheader("Gestión de Consumibles (Upselling y Stock)")
    
    tarjeta_extra = st.text_input("N° de Tarjeta PVC del Vehículo:")
    extra_tipo = st.selectbox("Servicio o Producto:", list(dict_tarifas.keys()))
    cantidad = st.number_input("Cantidad:", min_value=1, value=1, step=1)
    
    precio_unitario = dict_tarifas.get(extra_tipo, 0)
    total_linea = precio_unitario * cantidad
    
    st.info(f"Precio unitario: ${precio_unitario} | **Total a sumar: ${total_linea}**")
    
    if st.button("Sumar Extra a la Cuenta"):
        if tarjeta_extra:
            try:
                registros = sh.worksheet("Registro").get_all_records()
                patente_encontrada = next((r['Matrícula'] for r in registros if str(r['Ticket']) == str(tarjeta_extra) and not r['Hora_Salida']), f"TARJETA_{tarjeta_extra}")
                
                hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Fila para la cuenta del cliente
                sh.worksheet("Registro").append_row([
                    "EXTRA", patente_encontrada, hora_actual, "", 
                    f"Extra ({empleado_actual})", "", f"{extra_tipo} x{cantidad} (${total_linea})", total_linea
                ])
                
                # Fila para auditoría y stock
                try:
                    sh.worksheet("Control_Stock").append_row([hora_actual, extra_tipo, cantidad, empleado_actual, patente_encontrada])
                except:
                    pass
                
                st.success(f"✅ Se agregaron {cantidad}x '{extra_tipo}' (${total_linea}) a la tarjeta #{tarjeta_extra} ({patente_encontrada}).")
            except Exception as ex:
                st.error(f"Error al registrar el extra: {ex}")
        else:
            st.warning("⚠️ Ingresa el número de tarjeta.")

# ==========================================
# 4. SALIDA Y TICKET OFICIAL CON LOGOS Y CÁLCULO
# ==========================================
elif menu == "📤 Salida y Cómputo Final":
    st.subheader("Cómputo de Egreso y Liquidación Automática")
    
    tarjeta_salida = st.text_input("N° de Tarjeta PVC a devolver:")
    celular = st.text_input("Celular del cliente para el Ticket (Ej: 59899123456):")
    
    if st.button("Calcular Salida y Generar Ticket"):
        if tarjeta_salida and celular:
            try:
                registros = sh.worksheet("Registro").get_all_records()
                fila_ingreso = next((r for r in registros if str(r.get("Ticket")) == str(tarjeta_salida) and not r.get("Hora_Salida")), None)
                
                if not fila_ingreso:
                    st.error("❌ No se encontró un vehículo activo con ese número de tarjeta.")
                else:
                    patente_limpia = fila_ingreso.get("Matrícula")
                    hora_ingreso_str = fila_ingreso.get("Hora_Ingreso")
                    estado_ingreso = str(fila_ingreso.get("Estado", ""))
                    es_mensualista = "Mensualista VIP" in estado_ingreso
                    
                    # Cálculo de tiempo
                    hora_ingreso = datetime.strptime(hora_ingreso_str, "%Y-%m-%d %H:%M:%S")
                    hora_salida = datetime.now()
                    minutos_totales = int((hora_salida - hora_ingreso).total_seconds() / 60)
                    
                    # Verificación de Quinquela
                    tiene_quinquela = False
                    if not es_mensualista and sh_quinquela:
                        try:
                            ws_q = sh_quinquela.worksheet("QUINQUELA - FLOW PARK")
                            patentes_q = [str(p).upper().replace("-", "").replace(" ", "") for p in ws_q.col_values(3)]
                            if patente_limpia in patentes_q:
                                tiene_quinquela = True
                        except:
                            pass
                    
                    # Cálculo de tarifas por tiempo
                    minutos_bonificados = 120 if tiene_quinquela else 0
                    minutos_a_cobrar = max(0, minutos_totales - minutos_bonificados)
                    
                    monto_estacionamiento = 0
                    if not es_mensualista and minutos_a_cobrar > 0:
                        monto_estacionamiento = (minutos_a_cobrar // 30 + 1) * 150

                    # Recopilar extras
                    extras_auto = [r for r in registros if r.get("Matrícula") == patente_limpia and str(r.get("Ticket")) == "EXTRA"]
                    
                    detalle_extras_txt = "\n".join([f"• {r.get('Estado')}" for r in extras_auto])
                    total_extras = sum([float(r.get("Precio", 0)) for r in extras_auto])
                    
                    total_a_pagar = 0 if es_mensualista else (monto_estacionamiento + total_extras)
                    
                    if es_mensualista:
                        desc_texto = "Cliente Mensualista VIP (Costo $0)."
                    elif tiene_quinquela:
                        desc_texto = "Incluye 2 horas libres de cortesía por Restaurante Quinquela."
                    else:
                        desc_texto = "Tarifa estándar aplicada."

                    # Mensaje oficial institucional adaptado
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
