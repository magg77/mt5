import time
import MetaTrader5 as mt5
import pandas as pd

"""
Este bot de trading automático para MetaTrader 5 sigue una estrategia basada en Bandas de Bollinger y una EMA de 200 períodos.
"""

# condiciones y operaciones en tendencia
    #Compra (BUY): Solo si el precio está por encima de la EMA 200 y toca la Banda de Bollinger inferior
    # Venta (SELL): Solo si el precio está por debajo de la EMA 200 y toca la Banda de Bollinger superior

# 📌 activos
SYMBOL = "XAUUSD"  # 🏦 Instrumento a operar

# Gestión de riesgo: Se ajusta el tamaño de lote en base al balance y riesgo
BALANCE = 20  # 💰 Balance en la cuenta demo
RISK_PERCENTAGE = 2  # % de riesgo por operación para calcular el porcentaje del lote
PIP_VALUE = 0.01  # Valor del pip en USD
MAX_ORDERS = 2  # 🛑 Máximo de órdenes abiertas permitidas

# Automatización de SL/TP: Se calcula dinámicamente en place_order.
STOP_LOSS_PIPS = 30  # ❌ Stop Loss global
TAKE_PROFIT_PIPS = 60  # ✅ Take Profit global

INTERVAL_SECONDS = 3  # ⏳ Tiempo de espera entre análisis
SLEEP_INTERVAL = 2  # ⏳ Tiempo de espera entre revisiones (segundos)
PROCESSING_TIME = 3600  # ⏳ Mantener análisis activo (1 hora en segundos)

TIMEFRAME = mt5.TIMEFRAME_M1  # ⏳ Timeframe a analizar (1 minuto)
BOLLINGER_PERIOD = 20  # 📊 Período para las Bandas de Bollinger
STD_MULTIPLIER = 2  # 📊 Factor para las desviaciones estándar
EMA_PERIOD = 200  # 📊 Período de la EMA para detectar tendencia
NUMBER_OF_CANDLES = 200 # Pedimos 200 velas para calcular EMA
VERIFY_BB = True # Verifica si el cuerpo o mecha de la vela toca las bandas de Bollinger antes de activar una orden.

TYPE_ORDER = "La orden solo se activa si el precio de cierre o la mecha toca la BB o el cuerpo de la vela toca la bb"

# 📌 Conectar a MetaTrader 5
if not mt5.initialize():
    print("❌ Error al conectar con MetaTrader 5")
    quit()
print("✅ Conectado a MetaTrader 5")

def get_bollinger_signal(symbol):
    start_time = time.time()
    while time.time() - start_time < PROCESSING_TIME:
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUMBER_OF_CANDLES)
        if rates is None:
            print("❌ Error obteniendo datos del mercado")
            return None
        
        df = pd.DataFrame(rates)
        df["SMA20"] = df["close"].rolling(window=BOLLINGER_PERIOD).mean()
        df["STD"] = df["close"].rolling(window=BOLLINGER_PERIOD).std()
        df["Upper_BB"] = df["SMA20"] + (df["STD"] * STD_MULTIPLIER)
        df["Lower_BB"] = df["SMA20"] - (df["STD"] * STD_MULTIPLIER)
        df["EMA200"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
        
        last_close = df["close"].iloc[-1]
        upper_bb = df["Upper_BB"].iloc[-1]
        lower_bb = df["Lower_BB"].iloc[-1]
        high = df["high"].iloc[-1]
        low = df["low"].iloc[-1]
        ema200 = df["EMA200"].iloc[-1]
        
        #print(f"📊 Último cierre: {last_close:.4f}, Máximo: {high:.4f}, Mínimo: {low:.4f}")
        #print(f"📊 BB Superior: {upper_bb:.4f}, BB Inferior: {lower_bb:.4f}, EMA200: {ema200:.4f}")
        
        if last_close >= upper_bb or high >= upper_bb:
            if last_close < ema200:
                print("⚠️ Tendencia bajista detectada, evitando compras")
                return None
            print("⚡ SELL detectado!")
            return "SELL"
        elif last_close <= lower_bb or low <= lower_bb:
            if last_close > ema200:
                print("⚠️ Tendencia alcista detectada, evitando ventas")
                return None
            print("⚡ BUY detectado!")
            return "BUY"
        else:
            print("⏳...")
        
        time.sleep(SLEEP_INTERVAL)
    return None

def place_order(symbol, order_type, lot_size):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ No se pudo obtener información de {symbol}")
        return
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"❌ No se pudo obtener el precio del símbolo {symbol}")
        return
    
    if order_type == "BUY":
        price = tick.ask
        sl = price - STOP_LOSS_PIPS * symbol_info.point
        tp = price + TAKE_PROFIT_PIPS * symbol_info.point
        order_type_mt5 = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl = price + STOP_LOSS_PIPS * symbol_info.point
        tp = price - TAKE_PROFIT_PIPS * symbol_info.point
        order_type_mt5 = mt5.ORDER_TYPE_SELL

    # 🔹 Validar y ajustar tamaño de lote
    lot_size = max(symbol_info.volume_min, min(symbol_info.volume_max, round(lot_size / symbol_info.volume_step) * symbol_info.volume_step))

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type_mt5,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 0,
        "comment": "Bollinger EMA Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Orden {order_type} ejecutada en {symbol} con {lot_size} lotes. TP: {tp}, SL: {sl}")
    else:
        print(f"❌ Error al ejecutar orden: {result.retcode}, {result.comment}")

while True:
    signal = get_bollinger_signal(SYMBOL)
    open_positions = mt5.positions_total()
    print(f"📊 Órdenes abiertas: {open_positions}/{MAX_ORDERS}")
    
    if open_positions < MAX_ORDERS and signal:
        lot_size = (BALANCE * RISK_PERCENTAGE / 100) / (STOP_LOSS_PIPS * PIP_VALUE)
        place_order(SYMBOL, signal, lot_size)
    else:
        print("⚠️ Máximo de órdenes alcanzado o sin señal válida, esperando...")
    
    time.sleep(INTERVAL_SECONDS)
