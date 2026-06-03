import streamlit as st
import pandas as pd
import datetime
import pyRofex
import warnings
import logging

warnings.filterwarnings("ignore", category=UserWarning)

# --- 1. CONFIGURACIÓN DE LA APP ---
st.set_page_config(page_title="Gestor de Cartera - Juan", layout="wide")
st.title("📊 Gestor de Préstamo de Valores")
st.markdown("Control de deuda, inyección de liquidez y proyección de cierre.")

# --- 2. LÓGICA DE CONEXIÓN A BRIO VALORES ---
BRIO_USER = "wenvest" 
BRIO_PASS = "H73VD9dF_" # <-- PONE TU PASS ACÁ
CUENTA_COMITENTE = "31221" 

@st.cache_resource
def conectar_brio():
    try:
        url_brio = "https://api.briovalores.xoms.com.ar/"
        ws_brio = "wss://api.briovalores.xoms.com.ar/"
        pyRofex._set_environment_parameter("url", url_brio, pyRofex.Environment.LIVE)
        pyRofex._set_environment_parameter("ws", ws_brio, pyRofex.Environment.LIVE)
        
        pyRofex.initialize(user=BRIO_USER, password=BRIO_PASS, account=CUENTA_COMITENTE, environment=pyRofex.Environment.LIVE)
        return True
    except Exception as e:
        st.error(f"❌ Error al conectar con el broker: {e}")
        return False

def obtener_precio_pyrofex(ticker):
    try:
        entradas = [pyRofex.MarketDataEntry.LAST, pyRofex.MarketDataEntry.CLOSING_PRICE, pyRofex.MarketDataEntry.SETTLEMENT_PRICE]
        data = pyRofex.get_market_data(ticker=ticker, entries=entradas)
        if data and data['status'] == 'OK':
            m_data = data.get('marketData', {})
            for entry in ['LA', 'CL', 'SE']:
                if entry in m_data and m_data[entry] is not None:
                    precio = m_data[entry].get('price', 0)
                    if precio and precio > 0: return precio
        return 0.0
    except Exception:
        return 0.0

conexion_exitosa = conectar_brio()

# --- 3. BASE DE DATOS Y ESTADO DE SESIÓN ---
@st.cache_data
def cargar_flujos():
    try:
        df = pd.read_csv("flujos_mercado.csv", sep=";", decimal=",")
        df['FECHA DE PAGO'] = pd.to_datetime(df['FECHA DE PAGO'], format="%d/%m/%Y")
        return df
    except:
        try:
            df = pd.read_csv("flujos_mercado.csv", sep=",", decimal=".")
            df['FECHA DE PAGO'] = pd.to_datetime(df['FECHA DE PAGO'], format="%d/%m/%Y")
            return df
        except Exception as e:
            st.error("No se pudo leer el archivo CSV. Verificá que se llame 'flujos_mercado.csv'.")
            return pd.DataFrame()

df_flujos = cargar_flujos()

cartera_original = {
    "AE38": 859.00, "AL29": 479.00, "AL30": 5191.00, "AL35": 21.00,
    "GD29": 648.00, "GD30": 1033.00, "GD35": 504.00, "GD38": 313.00, "GD41": 63.00,
    "CLI1O": 881.00, "CLSIO": 4216.00, "MR35O": 433.00, "MR39O": 1299.00, "SNEBO": 1150.00
}

tickers_mep = {
    "AE38": "AE38D", "AL29": "AL29D", "AL30": "AL30D", "AL35": "AL35D",
    "GD29": "GD29D", "GD30": "GD30D", "GD35": "GD35D", "GD38": "GD38D", "GD41": "GD41D",
    "CLI1O": "CLI1D", "CLSIO": "CLSID", "MR35O": "MR35D", "MR39O": "MR39D", "SNEBO": "SNEBD"
}

# --- INICIALIZACIÓN DE LA MEMORIA DE LA APP ---
if 'adelantos_vn' not in st.session_state:
    st.session_state['adelantos_vn'] = {ticker: 0.0 for ticker in cartera_original.keys()}
    
if 'gastos_hundidos' not in st.session_state:
    st.session_state['gastos_hundidos'] = 0.0

if 'cupones_saldados' not in st.session_state:
    st.session_state['cupones_saldados'] = [] # Acá guardamos los IDs de los pagos ya realizados

# --- 4. MÓDULO INTERACTIVO DE ADELANTOS ---
st.divider()
st.subheader("💵 Inyección de Liquidez Mensual (Achicar Capital)")

col_usd, col_tick, col_btn = st.columns([1, 1, 2])
with col_usd:
    usd_disponibles = st.number_input("Dólares disponibles para adelantar", min_value=0.0, step=50.0, value=300.0)
with col_tick:
    ticker_elegido = st.selectbox("¿Qué deuda querés cancelar con esto?", list(cartera_original.keys()))
with col_btn:
    st.write("") 
    if st.button("🛒 Ejecutar Compra y Achicar Deuda", type="primary"):
        if conexion_exitosa and usd_disponibles > 0:
            ticker_dolar = tickers_mep[ticker_elegido]
            ticker_rofex = f"MERV - XMEV - {ticker_dolar} - 24HS"
            precio_hoy = obtener_precio_pyrofex(ticker_rofex)
            
            if precio_hoy > 0:
                vn_comprados = (usd_disponibles / precio_hoy) * 100
                st.session_state['adelantos_vn'][ticker_elegido] += vn_comprados
                st.success(f"✅ ¡Operación exitosa! Con USD {usd_disponibles:,.2f} recompraste **{vn_comprados:,.2f} nominales** de {ticker_elegido}. Ya se descontaron de tu saldo.")
            else:
                st.error("No hay cotización en el mercado para ese activo en este momento.")

# --- 5. TABLA RESUMEN DE LA DEUDA ---
st.write("### 📋 Resumen de tu Deuda Actual")

fecha_hoy_pd = pd.to_datetime(datetime.date.today())
flujos_pasados_hoy = df_flujos[df_flujos['FECHA DE PAGO'] <= fecha_hoy_pd] if not df_flujos.empty else pd.DataFrame()

cartera_juan_actualizada = {}
filas_resumen = []

for ticker, vn_inicial in cartera_original.items():
    if not flujos_pasados_hoy.empty and ticker in flujos_pasados_hoy['TICKER'].values:
        amort_auto = flujos_pasados_hoy[flujos_pasados_hoy['TICKER'] == ticker]['AMORTIZACION'].sum()
    else:
        amort_auto = 0.0
        
    adelantos = st.session_state['adelantos_vn'][ticker]
    saldo_vivo = max(0, vn_inicial - amort_auto - adelantos)
    cartera_juan_actualizada[ticker] = saldo_vivo
    
    filas_resumen.append({
        "Activo": ticker,
        "Deuda Inicial (VN)": vn_inicial,
        "Amortizado Solo (VN)": amort_auto,
        "Tus Adelantos (VN)": adelantos,
        "SALDO RESTANTE (VN)": saldo_vivo
    })

df_resumen = pd.DataFrame(filas_resumen)
st.dataframe(
    df_resumen.style.format({
        "Deuda Inicial (VN)": "{:,.2f}",
        "Amortizado Solo (VN)": "{:,.2f}",
        "Tus Adelantos (VN)": "{:,.2f}",
        "SALDO RESTANTE (VN)": "{:,.2f}"
    }),
    use_container_width=True
)

# --- 6. AGENDA DE PAGOS Y COSTOS HUNDIDOS ---
st.divider()
st.subheader("🔔 Agenda de Vencimientos (Costo de Mantenimiento)")

def registrar_pago(renta, id_pago):
    st.session_state['gastos_hundidos'] += renta
    st.session_state['cupones_saldados'].append(id_pago)

# Panel de Costos Hundidos (Dinero quemado)
st.info(f"🔥 **Costo Hundido Acumulado:** Hasta el momento llevás pagados **USD {st.session_state['gastos_hundidos']:,.2f}** en concepto de mantenimiento de deuda durante esta sesión.")

if not df_flujos.empty:
    # Filtramos pagos futuros y le creamos un ID único a cada cupón
    flujos_futuros = df_flujos[df_flujos['FECHA DE PAGO'] >= fecha_hoy_pd].copy()
    flujos_futuros['ID_PAGO'] = flujos_futuros['TICKER'] + "_" + flujos_futuros['FECHA DE PAGO'].dt.strftime('%Y-%m-%d')
    
    # Excluimos los cupones que Juan ya marcó como pagados
    flujos_pendientes = flujos_futuros[~flujos_futuros['ID_PAGO'].isin(st.session_state['cupones_saldados'])].sort_values(by='FECHA DE PAGO')

    if not flujos_pendientes.empty:
        # Buscamos cuál es la fecha más próxima
        fecha_prox = flujos_pendientes['FECHA DE PAGO'].min()
        
        # Filtramos TODOS los pagos que caen en esa misma fecha
        pagos_del_dia = flujos_pendientes[flujos_pendientes['FECHA DE PAGO'] == fecha_prox]
        
        st.warning(f"📅 **Día de Cobro Múltiple:** El {fecha_prox.strftime('%d/%m/%Y')} vencen los siguientes activos:")
        
        # Armamos un bloque visual para cada bono que vence ese día
        for index, pago in pagos_del_dia.iterrows():
            ticker_prox = pago['TICKER']
            id_pago_actual = pago['ID_PAGO']
            
            deuda_original = cartera_original.get(ticker_prox, 1)
            saldo_actual = cartera_juan_actualizada.get(ticker_prox, 0)
            ratio_deuda = saldo_actual / deuda_original if deuda_original > 0 else 0
            
            renta_a_pagar = pago['RENTA'] * ratio_deuda
            amort_a_pagar = pago['AMORTIZACION'] * ratio_deuda
            
            with st.container():
                st.write(f"🔹 **{ticker_prox}**")
                col_m1, col_m2, col_btn_pago = st.columns([1, 1, 2])
                with col_m1:
                    st.metric(label="Renta (Se suma al Costo Hundido)", value=f"${renta_a_pagar:,.2f}")
                with col_m2:
                    st.metric(label="Amortización (Devolución de Capital)", value=f"${amort_a_pagar:,.2f}")
                with col_btn_pago:
                    st.write("")
                    st.button(
                        f"💸 Registrar Pago {ticker_prox}", 
                        key=f"btn_pago_{id_pago_actual}", 
                        on_click=registrar_pago, 
                        args=(renta_a_pagar, id_pago_actual)
                    )
                st.markdown("---") # Linea separadora entre bonos
    else:
        st.success("🎉 ¡No tenés pagos pendientes en tu agenda!")


# --- 7. SIMULADOR DE CIERRE FINAL ---
st.divider()
st.subheader("📅 Proyección de Cierre Total")
st.write("¿Cuánto te costaría liquidar hoy mismo (o en una fecha futura) la totalidad de tu saldo restante?")

fecha_corte = st.date_input("Elegí una fecha para cancelar todo", value=fecha_hoy_pd.date())
fecha_corte_pd = pd.to_datetime(fecha_corte)

if not df_flujos.empty and conexion_exitosa:
    if st.button("Ejecutar Simulación de Cierre", type="primary"):
        with st.spinner("Consultando cotizaciones en vivo vía pyRofex..."):
            
            costo_total_recompra = 0.0
            renta_futura_a_pagar = 0.0
            amort_futura_a_pagar = 0.0
            resultados = []
            
            for ticker, saldo_vivo_hoy in cartera_juan_actualizada.items():
                
                # Proyectamos flujos desde HOY hasta el CORTE, excluyendo los ya pagados
                flujos_proy = df_flujos[(df_flujos['TICKER'] == ticker) & 
                                        (df_flujos['FECHA DE PAGO'] > fecha_hoy_pd) & 
                                        (df_flujos['FECHA DE PAGO'] <= fecha_corte_pd)].copy()
                
                if not flujos_proy.empty:
                    flujos_proy['ID_PAGO'] = flujos_proy['TICKER'] + "_" + flujos_proy['FECHA DE PAGO'].dt.strftime('%Y-%m-%d')
                    flujos_proy = flujos_proy[~flujos_proy['ID_PAGO'].isin(st.session_state['cupones_saldados'])]
                
                deuda_original = cartera_original.get(ticker, 1)
                ratio_deuda = saldo_vivo_hoy / deuda_original if deuda_original > 0 else 0
                
                amort_pagada_proyectada = flujos_proy['AMORTIZACION'].sum() * ratio_deuda if not flujos_proy.empty else 0.0
                renta_pagada_proyectada = flujos_proy['RENTA'].sum() * ratio_deuda if not flujos_proy.empty else 0.0
                
                renta_futura_a_pagar += renta_pagada_proyectada
                amort_futura_a_pagar += amort_pagada_proyectada
                
                nominales_residuales = max(0, saldo_vivo_hoy - amort_pagada_proyectada)
                
                if nominales_residuales > 0:
                    ticker_dolar = tickers_mep[ticker]
                    ticker_rofex = f"MERV - XMEV - {ticker_dolar} - 24HS"
                    precio_mercado = obtener_precio_pyrofex(ticker_rofex)
                    
                    costo_cierre = (nominales_residuales / 100) * precio_mercado
                    costo_total_recompra += costo_cierre
                    
                    resultados.append({
                        "Ticker": ticker,
                        "Nominales Finales": nominales_residuales,
                        "Precio Cierre (USD)": precio_mercado,
                        "Costo Recompra (USD)": costo_cierre,
                        "Renta en el Camino": renta_pagada_proyectada,
                        "Amort. en el Camino": amort_pagada_proyectada
                    })

            if resultados:
                desembolso_futuro = costo_total_recompra + renta_futura_a_pagar + amort_futura_a_pagar
                
                st.success("✅ Simulación de cierre proyectada con éxito.")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("1️⃣ Recompra al Corte", f"${costo_total_recompra:,.2f}")
                m2.metric("2️⃣ Amort. Proyectada", f"${amort_futura_a_pagar:,.2f}")
                m3.metric("3️⃣ Renta Proyectada", f"${renta_futura_a_pagar:,.2f}")
                m4.metric("🔥 DESEMBOLSO TOTAL", f"${desembolso_futuro:,.2f}")
                
                df_res = pd.DataFrame(resultados)
                st.dataframe(
                    df_res.style.format({
                        "Nominales Finales": "{:,.2f}", 
                        "Precio Cierre (USD)": "${:,.2f}", 
                        "Costo Recompra (USD)": "${:,.2f}",
                        "Renta en el Camino": "${:,.2f}",
                        "Amort. en el Camino": "${:,.2f}"
                    }), 
                    use_container_width=True
                )