import yfinance as yf
import pandas as pd
import time
import warnings
import requests
import io
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# 1. CONFIGURACIÓN Y SILENCIO DE LOGS
warnings.simplefilter(action='ignore', category=FutureWarning)
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# --- PARÁMETROS JESSE STINE ---
MIN_PRECIO, MAX_PRECIO = 0.5, 15.0
MIN_VOL_SEMANAL = 100000 
RANGO_BASE_MAX = 15       
SEMANAS_BASE = 20         
VOL_SUPERSTOCK = 5    # Diamantes (5x)
VOL_WATCHLIST = 3     # Vigilancia (3x)
LOTE_SIZE = 40        # Tamaño de lote seguro para Yahoo

# ----------------------------------------------------------------
# 2. OBTENCIÓN DE UNIVERSO (NASDAQ + S&P 400/600)
# ----------------------------------------------------------------
def obtener_universo():
    universo = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # A. NASDAQ
    try:
        url_nas = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
        df_n = pd.read_csv(url_nas, sep="|")
        universo.update(df_n[df_n['Test Issue'] == 'N']['Symbol'].dropna().astype(str).tolist())
    except: print("⚠️ Error cargando NASDAQ")

    # B. S&P 400 y 600 (Wikipedia)
    urls = ["https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"]
    for url in urls:
        try:
            resp = requests.get(url, headers=headers)
            tablas = pd.read_html(io.StringIO(resp.text))
            for df in tablas:
                col = [c for c in df.columns if 'Symbol' in str(c) or 'Ticker' in str(c)]
                if col:
                    universo.update(df[col[0]].astype(str).str.replace('.', '-').tolist())
                    break
        except: print(f"⚠️ Error cargando tabla de {url}")
    
    return sorted([t for t in universo if str(t).isalpha() and len(str(t)) < 6])

# ----------------------------------------------------------------
# 3. FUNCIÓN DE ENVÍO DE CORREO
# ----------------------------------------------------------------
def enviar_correo(archivo_excel, superstocks, watchlist):
    remitente = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PASS')
    
    if not remitente or not password:
        print("❌ Faltan las credenciales EMAIL_USER o EMAIL_PASS")
        return

    # Formatear tickers para TradingView (separados por comas)
    tv_super = ",".join([s['Ticker'] for s in superstocks])
    tv_watch = ",".join([w['Ticker'] for w in watchlist])

    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = remitente
    msg['Subject'] = f"📊 Reporte Stine: {len(superstocks)} Diamantes y {len(watchlist)} Watchlist"

    cuerpo = f"""
Hola Matias, resultados del escaneo semanal:

💎 DIAMANTES (Volumen > 5x):
{tv_super if tv_super else "Ninguno encontrado"}

👀 WATCHLIST (Volumen > 3x):
{tv_watch if tv_watch else "Ninguno encontrado"}

💡 TRUCO TRADINGVIEW:
Copia la lista de arriba y pégala en el buscador de TradingView para ver todos los gráficos.

Se adjunta el Excel con los detalles técnicos.
"""
    msg.attach(MIMEText(cuerpo, 'plain'))

    if os.path.exists(archivo_excel):
        with open(archivo_excel, "rb") as adjunto:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(adjunto.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {archivo_excel}")
            msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.send_message(msg)
        server.quit()
        print("📧 Correo enviado con éxito.")
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")

# ----------------------------------------------------------------
# 4. MOTOR PRINCIPAL
# ----------------------------------------------------------------
def ejecutar_screener():
    print("🚀 Iniciando Screener en la nube...")
    tickers = obtener_universo()
    total = len(tickers)
    
    superstocks = []
    watchlist = []
    start_time = time.time()

    for i in range(0, total, LOTE_SIZE):
        lote = tickers[i:i+LOTE_SIZE]
        try:
            data = yf.download(lote, period="2y", interval="1wk", group_by='ticker', 
                               auto_adjust=True, progress=False, threads=True)
            
            for ticker in lote:
                try:
                    df = data[ticker].dropna()
                    if len(df) < 51: continue

                    last_close = df['Close'].iloc[-1]
                    last_vol = df['Volume'].iloc[-1]

                    if not (MIN_PRECIO <= last_close <= MAX_PRECIO) or last_vol < MIN_VOL_SEMANAL:
                        continue

                    df['SMA_30'] = df['Close'].rolling(window=30).mean()
                    avg_vol_previo = df['Volume'].iloc[-11:-1].mean()
                    
                    base_df = df.iloc[-(SEMANAS_BASE + 1):-1]
                    rango_base = ((base_df['High'].max() - base_df['Low'].min()) / base_df['Low'].min()) * 100
                    
                    if rango_base > RANGO_BASE_MAX: continue

                    c_sma = (last_close > df['SMA_30'].iloc[-1] and df['Close'].iloc[-2] <= df['SMA_30'].iloc[-2])
                    
                    if c_sma:
                        ratio_vol = last_vol / avg_vol_previo
                        res = {'Ticker': ticker, 'Precio': round(last_close, 2), 
                               'Base %': f"{rango_base:.1f}%", 'Vol_Multi': round(ratio_vol, 1)}
                        
                        if ratio_vol >= VOL_SUPERSTOCK:
                            superstocks.append(res)
                        elif ratio_vol >= VOL_WATCHLIST:
                            watchlist.append(res)
                except: continue
            
            time.sleep(1) # Respiro para el servidor
            print(f"Procesado: {i+len(lote)}/{total}")

        except Exception: continue

    # Guardar y enviar
    archivo = "analisis_jesse_stine.xlsx"
    with pd.ExcelWriter(archivo) as writer:
        if superstocks: pd.DataFrame(superstocks).to_excel(writer, sheet_name='Superstocks', index=False)
        if watchlist: pd.DataFrame(watchlist).to_excel(writer, sheet_name='Watchlist', index=False)
    
    enviar_correo(archivo, superstocks, watchlist)
    print(f"🏁 Finalizado en {(time.time() - start_time)/60:.2f} min.")

if __name__ == "__main__":
    ejecutar_screener()