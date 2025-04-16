
# 0.01 = XAUUSD /   XAGUSD  /   USD/JPY
# 0.0001 = EUR/USD, GBP/USD

import MetaTrader5 as mt5
import time
import pandas as pd
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
import requests

#path
MT5_PATH_B = "C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe"

# Reemplaza con tu token y chat_id de Telegram
TELEGRAM_TOKEN = '7794506489:AAHxx5nwReKHyrEPr8eNSXPfUBiFizgQkeY'
TELEGRAM_CHAT_ID = '7896485263'

# --- Configuración del bot ---
LOTES_POR_SIMBOLO = {
    "XAUUSD": 0.01
}
SYMBOLS = list(LOTES_POR_SIMBOLO.keys())

#orden
STOP_LOSS_PIPS = 4000
TAKE_PROFIT_PIPS = 4000

#tiempos
INTERVAL_SECONDS = 3
SLEEP_INTERVAL = 2
TIMEFRAME = mt5.TIMEFRAME_M1

#logica desicion
EMA_PERIOD = 50
NUMBER_OF_CANDLES = 5000

#mover stop loss dinamicamente a break-even
LAST_ORDER_INFO = {}  # Guarda el índice de vela y detalles de última orden por símbolo
NUMBER_CANDLES_MOVE_STOPLOSS = 3

PREV_TENDENCIA = {}

# Global para guardar la figura y los ejes
fig = None
ax1 = None
line1 = None
line2 = None

def init_mt5():
    """Inicializa la conexión con MetaTrader 5."""
    if not mt5.initialize(path=MT5_PATH_B):
        print("❌ No se pudo inicializar MetaTrader 5")
        quit()
    else:
        print(f"✅ MetaTrader 5 inicializado correctamente: {mt5.terminal_info()}")


def send_telegram_message(message: str):
    """Envía un mensaje a Telegram usando la API de Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    response = requests.post(url, data=payload)
    
    if response.status_code == 200:
        print("✅ Mensaje enviado a Telegram")
    else:
        print(f"❌ Error al enviar mensaje: {response.status_code}")
        

def init_plot():
    global fig, ax1, line1, line2
    plt.ion()  # Modo interactivo

    fig, ax1 = plt.subplots(figsize=(16, 6))
    line1, = ax1.plot([], [], label='Pendiente Rápida (EMA_slope)', alpha=0.7)
    line2, = ax1.plot([], [], label='Pendiente Lenta (Normalizada)', linestyle='--')

    ax1.axhline(0, color='gray', linestyle='dotted')
    ax1.set_title("Comparación de Pendientes de la EMA")
    ax1.legend()
    ax1.grid(True)
    plt.tight_layout()
    plt.show(block=False)

def update_plot(data):
    global fig, ax1, line1, line2

    x = pd.to_datetime(data['time'], unit='s')
    y1 = data['EMA_slope']
    y2 = data['EMA_slope_50_normalized']

    line1.set_data(x, y1)
    line2.set_data(x, y2)

    ax1.relim()
    ax1.autoscale_view()

    fig.canvas.draw()
    fig.canvas.flush_events()
    
    
def get_ema_and_slope(data: pd.DataFrame, period: int, slope_window: int = 50):
    data['EMA'] = data['close'].ewm(span=period, adjust=False).mean()
    
    data['EMA_slope'] = data['EMA'] - data['EMA'].shift(EMA_PERIOD)
    data['EMA_slope_50_normalized'] = data['EMA_slope'] / EMA_PERIOD
    
    return data


def evaluar_tendencia(row, prev_row, symbol=None, verbose=False):
    if pd.isna(row['EMA_slope']) or pd.isna(row['EMA_slope_50_normalized']):
        return 'Indefinida'

    cruce_precio_arriba = prev_row['close'] < prev_row['EMA'] and row['close'] > row['EMA']
    cruce_precio_abajo = prev_row['close'] > prev_row['EMA'] and row['close'] < row['EMA']

    cambio_pendiente_positiva = prev_row['EMA_slope'] < 0 and row['EMA_slope'] > 0
    cambio_pendiente_negativa = prev_row['EMA_slope'] > 0 and row['EMA_slope'] < 0

    if verbose:
        if cambio_pendiente_positiva:
            print("🔄 Cambio de pendiente: Negativa ➜ Positiva (posible cambio de tendencia al alza)")
        elif cambio_pendiente_negativa:
            print("🔄 Cambio de pendiente: Positiva ➜ Negativa (posible cambio de tendencia a la baja)")

    if row['EMA_slope'] > 0 and row['EMA_slope_50_normalized'] > 0:
        if verbose:
            if cruce_precio_arriba:
                print("🟢 Señal de COMPRA (cruce de precio sobre EMA detectado)")
                send_telegram_message(f"🟢 Señal de COMPRA: {symbol} - Cruce de precio sobre la EMA detectado.")
            else:
                print("🟢 Fuerte Subida, pero sin cruce de precio (esperar confirmación)")
        return 'Fuerte Subida'

    elif row['EMA_slope'] > 0 and row['EMA_slope_50_normalized'] <= 0:
        if verbose:
            print("🟡 Posible COMPRA")
        return 'Inicio Subida'

    elif row['EMA_slope'] < 0 and row['EMA_slope_50_normalized'] > 0:
        if verbose:
            print("🟠 Posible VENTA")
        return 'Divergencia Bajista'

    elif row['EMA_slope'] < 0 and row['EMA_slope_50_normalized'] < 0:
        if verbose:
            if cruce_precio_abajo:
                print("🔴 Señal de VENTA (cruce de precio bajo EMA detectado)")
                send_telegram_message(f"🔴 Señal de VENTA: {symbol} - Cruce de precio bajo la EMA detectado.")
            else:
                print("🔴 Bajada Clara, pero sin cruce de precio (esperar confirmación)")
        return 'Bajada Clara'

    else:
        if verbose:
            print("⚪️ Sin señal clara")
        return 'Indecisión'


def procesar_tendencias_y_ultima_fila(data, symbol):
    tendencias = []
    for i in range(len(data)):
        if i == 0:
            tendencias.append('Indefinida')
            continue

        row = data.iloc[i]
        prev_row = data.iloc[i - 1]
        verbose = i == len(data) - 1  # Solo imprimir para la última fila
        tendencia = evaluar_tendencia(row, prev_row, symbol, verbose=verbose)
        tendencias.append(tendencia)

    data['tendencia'] = tendencias
    ultima_fila = data.iloc[-1]

    if 'tendencia' not in ultima_fila or pd.isna(ultima_fila['tendencia']):
        print(f"⚠️ Tendencia no definida para {symbol}")
        return

    tendencia = ultima_fila['tendencia']
    slope = ultima_fila['EMA_slope']
    slope_normalized = ultima_fila['EMA_slope_50_normalized']
    hora = pd.to_datetime(ultima_fila['time'], unit='s')

    # Cambio de tendencia
    if symbol in PREV_TENDENCIA and PREV_TENDENCIA[symbol] != tendencia:
        print(f"\n🔄 Cambio de tendencia en {symbol}: {PREV_TENDENCIA[symbol]} ➡️ {tendencia}")
    PREV_TENDENCIA[symbol] = tendencia

    # Cruce de pendiente
    cruce_positivo = data['EMA_slope'].iloc[-2] < 0 and slope > 0
    cruce_negativo = data['EMA_slope'].iloc[-2] > 0 and slope < 0

    if cruce_positivo:
        print(f"⚡️ EMA_slope cruzó de negativa a positiva en {symbol}")
    elif cruce_negativo:
        print(f"⚡️ EMA_slope cruzó de positiva a negativa en {symbol}")

    # 🟢 Imprimir estado
    print(f"\n📈 [{hora}] {symbol}")
    print(f"➡️ Tendencia: {tendencia}")
    print(f"📊 EMA_slope: {slope:.5f}")
    print(f"📉 EMA_slope_50_normalized: {slope_normalized:.5f}")


def process_symbol(symbol):
    if symbol not in LOTES_POR_SIMBOLO:
        print(f"⚠️ Símbolo no configurado: {symbol}")
        return

    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUMBER_OF_CANDLES)
    if rates is None or len(rates) < EMA_PERIOD:
        print(f"⚠️ Datos insuficientes para {symbol}")
        return

    data = pd.DataFrame(rates)
    data = get_ema_and_slope(data, EMA_PERIOD, slope_window=50)

    # Procesar tendencias y última fila en una sola función
    procesar_tendencias_y_ultima_fila(data, symbol)

    update_plot(data)

    
def main_loop():
    
    print("🚀 Bot de trading corriendo... (Ctrl+C para detener)\n")
    
    init_plot()

    
    while True:
        for symbol in SYMBOLS:
            print("\n******************************************")
            print(f"➡️ Analizando símbolo: {symbol}")
            
            process_symbol(symbol)
            
            time.sleep(SLEEP_INTERVAL)
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        init_mt5()
        main_loop()
    except KeyboardInterrupt:
        print("🚩 Bot detenido por el usuario.")
    finally:
        mt5.shutdown()    
