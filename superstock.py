import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
import requests
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Stine Superstock Screener", layout="wide")

# --- DESCRIPCIÓN Y METODOLOGÍA (RESTAURADA) ---
st.title("🚀 Jesse Stine: Insider Buy Superstock Screener")

with st.expander("📖 Ver Metodología y Parámetros del Screener", expanded=True):
    st.markdown("""
    Esta herramienta busca acciones que cumplen con los criterios técnicos descritos por **Jesse Stine** en su libro *Insider Buy Superstocks*. 
    El objetivo es detectar el **"Punto de Inflexión"** donde una acción rompe una base de consolidación con un volumen masivo.

    ### 🛠️ ¿Qué estamos buscando?
    1.  **Precio bajo ($1 - $15):** Stine se enfoca en acciones de pequeña capitalización donde el crecimiento puede ser explosivo.
    2.  **Base Plana (Consolidación):** La acción debe haber estado "dormida" en un rango estrecho (ej. < 20%) durante varias semanas.
    3.  **El "Grial" (Explosión de Volumen):** Buscamos un aumento de volumen semanal de al menos **500% (5x)** respecto a la media. Esto indica una entrada institucional masiva.
    4.  **Cruce de SMA 30:** El precio debe cerrar por encima de la Media Móvil de 30 semanas, señalando el inicio de una nueva tendencia alcista.
    """)

# --- SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración del Modelo")
    min_p = st.number_input("Precio Mínimo ($)", value=1.0, step=0.5)
    max_p = st.number_input("Precio Máximo ($)", value=15.0, step=0.5)
    min_vol = st.number_input("Vol. Semanal Mínimo", value=1000)
    
    st.divider()
    st.subheader("Análisis Técnico")
    rango_base_max = st.slider("Rango de Base Máximo (%)", 5, 50, 20, help="Máxima variación permitida en la base de consolidación.")
    semanas_base = st.slider("Semanas de la Base", 10, 52, 30)
    
    st.divider()
    st.subheader("Filtros de Volumen")
    vol_super = st.slider("Multiplicador Diamante (x)", 2.0, 10.0, 5.0, help="Múltiplo de volumen para categoría Diamante.")
    vol_watch = st.slider("Multiplicador Watchlist (x)", 1.5, 5.0, 3.0)
    
    ejecutar = st.button("🚀 Ejecutar Screener", use_container_width=True)

# --- FUNCIONES DE APOYO ---
def obtener_universo():
    universo = set()
    headers = {'User-Agent': 'Mozilla/5.0'}
    # 1. Nasdaq
    try:
        url_nas = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
        df_n = pd.read_csv(url_nas, sep="|")
        universo.update(df_n[df_n['Test Issue'] == 'N']['Symbol'].dropna().astype(str).tolist())
    except: pass
    
    # 2. S&P 400 y 600
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
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                low=df['Low'], close=df['Close'], name="Precio"))
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_30'], line=dict(color='orange', width=2), name="SMA 30"))
    fig.update_layout(title=f"Gráfico Semanal: {ticker}", xaxis_rangeslider_visible=False, template="plotly_white", height=450)
    fig.update_xaxes(title="Semanas")
    fig.update_yaxes(title="Precio ($)")
    return fig

# --- MOTOR DEL SCREENER ---
if ejecutar:
    tickers = obtener_universo()
    st.info(f"📡 Analizando un universo de {len(tickers)} acciones. Por favor, espera...")
    
    superstocks = []
    watchlist = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    lote_size = 40 
    for i in range(0, len(tickers), lote_size):
        lote = tickers[i:i+lote_size]
        progress_val = min((i + lote_size) / len(tickers), 1.0)
        progress_bar.progress(progress_val)
        status_text.text(f"Escaneando: {lote[0]}... ({int(progress_val*100)}%)")
        
        try:
            data = yf.download(lote, period="2y", interval="1wk", group_by='ticker', 
                               auto_adjust=True, progress=False)
            
            for ticker in lote:
                try:
                    df = data[ticker].dropna() if len(lote) > 1 else data.dropna()
                    if len(df) < 51: continue

                    last_close = df['Close'].iloc[-1]
                    last_vol = df['Volume'].iloc[-1]

                    if not (min_p <= last_close <= max_p) or last_vol < min_vol:
                        continue

                    df['SMA_30'] = df['Close'].rolling(window=30).mean()
                    avg_vol_previo = df['Volume'].iloc[-11:-1].mean()
                    
                    base_df = df.iloc[-(semanas_base + 1):-1]
                    rango_base = ((base_df['High'].max() - base_df['Low'].min()) / base_df['Low'].min()) * 100
                    
                    if rango_base > rango_base_max: continue

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
        time.sleep(0.1)

    status_text.success("✅ Análisis completado.")

    # --- VISUALIZACIÓN DE RESULTADOS ---
    st.divider()
    m1, m2 = st.columns(2)
    m1.metric("💎 Acciones Diamante", len(superstocks))
    m2.metric("👀 En Watchlist", len(watchlist))

    if superstocks:
        st.subheader("🏆 CATEGORÍA DIAMANTE (Potenciales Superstocks)")
        st.dataframe(pd.DataFrame(superstocks).drop(columns=['df']), use_container_width=True)
        for s in superstocks:
            st.plotly_chart(plot_stock(s['Ticker'], s['df']), use_container_width=True)

    if watchlist:
        st.subheader("👀 WATCHLIST / SEGUIMIENTO")
        st.dataframe(pd.DataFrame(watchlist).drop(columns=['df']), use_container_width=True)
        for w in watchlist:
            with st.expander(f"Ver análisis gráfico de {w['Ticker']}"):
                st.plotly_chart(plot_stock(w['Ticker'], w['df']), use_container_width=True)
    
    if not superstocks and not watchlist:
        st.warning("No se han encontrado acciones que cumplan los criterios en este momento.")
