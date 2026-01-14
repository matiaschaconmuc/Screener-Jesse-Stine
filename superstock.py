import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import requests
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Stine Superstock Screener", layout="wide")

# --- DESCRIPCIÓN ---
st.title("🚀 Jesse Stine: Insider Buy Superstock Screener")
st.markdown("""
Esta herramienta busca acciones que cumplen con los criterios técnicos del libro de Jesse Stine:
* **Precios bajos:** Acciones baratas (generalmente < $15).
* **Bases planas:** Consolidaciones de varias semanas con poca volatilidad.
* **Explosión de volumen:** El "Grial" es un aumento masivo del volumen semanal (> 500%).
* **Cruce de SMA 30:** Precio superando la media móvil de 30 semanas.
""")

# --- SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Parámetros del Modelo")
    min_p = st.number_input("Precio Mínimo ($)", value=1.0)
    max_p = st.number_input("Precio Máximo ($)", value=15.0)
    min_vol = st.number_input("Vol. Semanal Mínimo", value=1000)
    rango_base_max = st.slider("Rango de Base Máximo (%)", 5, 40, 20)
    semanas_base = st.slider("Semanas de la Base", 10, 52, 30)
    
    st.divider()
    vol_super = st.slider("Multiplicador Vol. Diamante (x)", 2.0, 10.0, 5.0)
    vol_watch = st.slider("Multiplicador Vol. Watchlist (x)", 1.5, 5.0, 3.0)
    
    ejecutar = st.button("🚀 Ejecutar Screener", use_container_width=True)

# --- FUNCIONES DE APOYO ---
@st.cache_data
def obtener_universo():
    universo = set()
    headers = {'User-Agent': 'Mozilla/5.0'}
    # S&P 400 y 600
    urls = ["https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", 
            "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"]
    for url in urls:
        try:
            resp = requests.get(url, headers=headers)
            tablas = pd.read_html(io.StringIO(resp.text))
            for df in tablas:
                col = [c for c in df.columns if 'Symbol' in str(c) or 'Ticker' in str(c)]
                if col:
                    universo.update(df[col[0]].astype(str).str.replace('.', '-').tolist())
                    break
        except: pass
    return sorted([t for t in universo if str(t).isalpha() and len(str(t)) < 6])

def plot_stock(ticker, df):
    fig = go.Figure()
    # Velas
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                low=df['Low'], close=df['Close'], name="Precio"))
    # SMA 30
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_30'], line=dict(color='orange', width=2), name="SMA 30"))
    
    fig.update_layout(title=f"Gráfico Semanal: {ticker}", xaxis_rangeslider_visible=False, height=400)
    return fig

# --- EJECUCIÓN DEL SCREENER ---
if ejecutar:
    tickers = obtener_universo()
    st.info(f"📡 Universo cargado: {len(tickers)} acciones analizando...")
    
    superstocks = []
    watchlist = []
    progress_bar = st.progress(0)
    
    lote_size = 50
    for i in range(0, len(tickers), lote_size):
        lote = tickers[i:i+lote_size]
        progress_bar.progress(min((i + lote_size) / len(tickers), 1.0))
        
        try:
            data = yf.download(lote, period="2y", interval="1wk", group_by='ticker', progress=False)
            
            for ticker in lote:
                try:
                    df = data[ticker].dropna()
                    if len(df) < 51: continue

                    last_close = df['Close'].iloc[-1]
                    last_vol = df['Volume'].iloc[-1]

                    # Filtros básicos
                    if not (min_p <= last_close <= max_p) or last_vol < min_vol:
                        continue

                    # Análisis Técnico
                    df['SMA_30'] = df['Close'].rolling(window=30).mean()
                    avg_vol_previo = df['Volume'].iloc[-11:-1].mean()
                    
                    base_df = df.iloc[-(semanas_base + 1):-1]
                    rango_base = ((base_df['High'].max() - base_df['Low'].min()) / base_df['Low'].min()) * 100
                    
                    if rango_base > rango_base_max: continue

                    # Cruce SMA 30
                    c_sma = (last_close > df['SMA_30'].iloc[-1] and df['Close'].iloc[-2] <= df['SMA_30'].iloc[-2])
                    
                    if c_sma:
                        ratio_vol = last_vol / avg_vol_previo
                        res = {'Ticker': ticker, 'Precio': round(last_close, 2), 
                               'Base %': f"{rango_base:.1f}%", 'Vol_Multi': round(ratio_vol, 1), 'df': df}
                        
                        if ratio_vol >= vol_super:
                            superstocks.append(res)
                        elif ratio_vol >= vol_watch:
                            watchlist.append(res)
                except: continue
        except: continue
        time.sleep(0.5)

    # --- MOSTRAR RESULTADOS ---
    st.divider()
    
    # Categoría Diamante
    st.subheader("💎 Acciones Diamante (Superstocks)")
    if superstocks:
        df_diamante = pd.DataFrame(superstocks).drop(columns=['df'])
        st.table(df_diamante)
        for s in superstocks:
            st.plotly_chart(plot_stock(s['Ticker'], s['df']), use_container_width=True)
    else:
        st.write("No se encontraron Superstocks en este momento.")

    # Categoría Watchlist
    st.subheader("👀 Watchlist de Seguimiento")
    if watchlist:
        df_watch = pd.DataFrame(watchlist).drop(columns=['df'])
        st.table(df_watch)
        for w in watchlist:
            with st.expander(f"Ver gráfico de {w['Ticker']}"):
                st.plotly_chart(plot_stock(w['Ticker'], w['df']), use_container_width=True)
    else:
        st.write("No hay acciones en la lista de seguimiento.")
