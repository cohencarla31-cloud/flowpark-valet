import streamlit as st
import gspread
from datetime import datetime, timedelta
import urllib.parse

# --- CONFIGURACIÓN DE GOOGLE SHEETS (Debes tener tu lógica de conexión aquí) ---
# conn = st.connection("gsheets", type=GSheetsConnection) 
# sh = gspread.service_account(...) 

def hora_actual_uy():
    return (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

# ... (Aquí irían tus funciones: obtener_validacion_local, calcular_mejor_precio, etc.)

menu = st.sidebar.radio("Menú", ["📥 Ingreso", "➕ Extras", "📤 Salida"])

# --- DATOS GENERALES ---
reg = sh.worksheet("Registro").get_all_values()
clientes = sh.worksheet("Clientes_Frecuentes").get_all_values()
q_data = sh.worksheet("Tarifas").get_all_values()

# ==========================================
# 1. INGRESO
# ==========================================
if menu == "📥 Ingreso":
    st.subheader("Ingreso de Vehículo")
    patente = st.text_input("Patente:").upper()
    mozo = st.selectbox("Operador:", ["Jony", "Matias", "Juan", "Raul"])
    if st.button("Registrar Ingreso"):
        nuevo_ticket = str(len(reg)) 
        sh.worksheet("Registro").append_row([nuevo_ticket, patente, hora_actual_uy(), "", f"Ingreso - Op: {mozo}", "", 0, 0])
        st.success("Ingresado!")

# ==========================================
# 2. EXTRAS
# ==========================================
elif menu == "➕ Extras":
    st.subheader("Sumar Extra a Vehículo")
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir auto:", [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos])
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        prod = st.text_input("Producto:")
        precio = st.number_input("Precio:", min_value=0)
        if st.button("Sumar Extra"):
            for i, row in enumerate(reg, start=1):
                if row[0].strip() == tkt:
                    actual_extras_dinero = float(row[7]) if row[7] else 0
                    actual_detalle = str(row[5]) if row[5] else ""
                    sh.worksheet("Registro").update_cell(i, 8, actual_extras_dinero + precio)
                    sh.worksheet("Registro").update_cell(i, 6, f"{actual_detalle} {prod} | ".strip())
                    st.success("Extra sumado.")
                    break

# ==========================================
# 5. SALIDA
# ==========================================
elif menu == "📤 Salida":
    st.subheader("Cómputo de Egreso y Ticket Final")
    activos = [r for r in reg[1:] if not r[3] and r[0].upper() != "EXTRA"]
    sel = st.selectbox("Elegir auto a retirar:", [""] + [f"#{r[0]} - Patente: {r[1]}" for r in activos])
    
    if sel:
        tkt = sel.split(" - ")[0].replace("#", "").strip()
        datos_auto = next(r for r in activos if r[0].strip() == tkt)
        patente = datos_auto[1]
        h_ingreso = datos_auto[2]
        
        if st.button("Calcular y Generar Salida"):
            h_salida = hora_actual_uy()
            ing = datetime.strptime(h_ingreso, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.utcnow() - timedelta(hours=3) - ing).total_seconds() / 60)
            
            # (Aquí tu lógica de calcular_mejor_precio ya existente)
            monto_estacionamiento = 110 # Ejemplo, usa tu función
            
            total_extras = float(datos_auto[7]) if datos_auto[7] else 0
            detalle_extras = datos_auto[5]
            total_a_pagar = monto_estacionamiento + total_extras
            
            texto_ticket = f"TOTAL A PAGAR: ${total_a_pagar} (Parking: ${monto_estacionamiento} + Extras: ${total_extras})"
            
            # Guardamos todo en la fila del auto
            for i, row in enumerate(reg, start=1):
                if row[0].strip() == tkt:
                    sh.worksheet("Registro").update_cell(i, 4, h_salida) # Hora salida
                    sh.worksheet("Registro").update_cell(i, 7, float(monto_estacionamiento)) # Parking
                    # El total de extras ya está en la col 8 (H) por el módulo Extras
                    break
            
            st.success("Datos guardados en Excel!")
            st.code(texto_ticket)
