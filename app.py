# --- CARGA DE TARIFAS Y EXTRAS ---
def obtener_datos():
    try:
        # Tarifas para cálculo de estadía
        ws_tarifas = sh.worksheet("Tarifas")
        tarifas = {r["Servicio"]: {"Auto": r["Precio_Auto"], "Camioneta": r["Precio_Camioneta"]} for r in ws_tarifas.get_all_records()}
        
        # Extras para venta
        ws_extras = sh.worksheet("Extras")
        extras = {r["Producto"]: int(r["Precio"]) for r in ws_extras.get_all_records()}
        
        return tarifas, extras
    except:
        return {}, {"Lavado Premium": 500}

# En el módulo 4 (Extras), ahora accedes a:
tarifas, extras = obtener_datos()
extra_seleccionado = st.selectbox("Extra:", list(extras.keys()))
precio_extra = extras[extra_seleccionado]

# En el módulo 5 (Salida), la función de cálculo usa las 'tarifas':
def calcular_mejor_precio(minutos, es_camioneta, tiene_quinquela):
    tarifas, _ = obtener_datos()
    tipo = "Camioneta" if es_camioneta else "Auto"
    # ... resto de la lógica igual ...
