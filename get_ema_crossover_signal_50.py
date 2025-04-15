
# 0.01 = XAUUSD /   XAGUSD  /   USD/JPY
# 0.0001 = EUR/USD, GBP/USD

import MetaTrader5 as mt5
import time
import pandas as pd

# --- Configuración del bot ---
LOTES_POR_SIMBOLO = {
    "XAUUSD": 0.01
}
SYMBOLS = list(LOTES_POR_SIMBOLO.keys())

#orden
STOP_LOSS_PIPS = 2200
TAKE_PROFIT_PIPS = 10000

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

def init_mt5():
    """Inicializa la conexión con MetaTrader 5."""
    if not mt5.initialize():
        print("❌ No se pudo inicializar MetaTrader 5")
        quit()

'''
def close_all_positions():
    """Cierra todas las posiciones abiertas al iniciar el bot.
    positions = mt5.positions_get()
    if positions is None:
        print("⚠️ Error al obtener posiciones abiertas")
        return

    for pos in positions:
        # Selecciona el precio adecuado según el tipo de orden
        price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
        
        # Crea la solicitud de cierre
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 234000,
            "comment": "Cerrar posición al iniciar",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(request)
'''

def get_ema(data, period):
    """Calcula la media móvil exponencial (EMA) del cierre."""
    return data['close'].ewm(span=period, adjust=False).mean()

def get_valid_lot_size(symbol, raw_lot):
    """Devuelve el tamaño de lote válido según el símbolo."""
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"⚠️ No se encontró información del símbolo: {symbol}")
        return 0.01

    min_lot = symbol_info.volume_min
    max_lot = symbol_info.volume_max
    lot_step = symbol_info.volume_step

    # Ajusta el lote dentro de los límites
    lot = max(min_lot, min(raw_lot, max_lot))
    steps = round((lot - min_lot) / lot_step)
    return round(min_lot + steps * lot_step, 2)

def adjust_pips_to_minimum(symbol, pips):
    """Ajusta los pips al mínimo permitido por el bróker."""
    info = mt5.symbol_info(symbol)
    min_pips = (info.trade_stops_level or 10) / 10.0
    return max(pips, min_pips)

def place_order(symbol, lot, order_type, stop_loss_pips, take_profit_pips, data):
    """Coloca una orden de mercado con SL y TP."""
    info = mt5.symbol_info(symbol)
    if not info or not info.trade_tick_value:
        return

    if not info.visible and not mt5.symbol_select(symbol, True):
        return

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return

    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    point = info.point

    # Ajusta SL y TP según distancia mínima
    sl_pips = adjust_pips_to_minimum(symbol, stop_loss_pips)
    tp_pips = adjust_pips_to_minimum(symbol, take_profit_pips)

    sl = price - sl_pips * point if order_type == mt5.ORDER_TYPE_BUY else price + sl_pips * point
    tp = price + tp_pips * point if order_type == mt5.ORDER_TYPE_BUY else price - tp_pips * point

    # Valida que SL y TP estén suficientemente lejos
    min_stop_distance = (info.trade_stops_level or 10) * point
    if abs(price - sl) < min_stop_distance or abs(price - tp) < min_stop_distance:
        return

    # Crea la orden
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 234000,
        "comment": "Cruce EMA",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ Orden ejecutada en {symbol} ({'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'})")
        LAST_ORDER_INFO[symbol] = {
            "ticket": result.order,
            "timestamp": time.time(),
            "type": order_type,
            "open_price": price,
            "bar_time": data.iloc[-1]["time"]  # Guardamos el tiempo de la vela actual
        }

def verificar_y_mover_sl(symbol):
    if symbol not in LAST_ORDER_INFO:
        return

    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUMBER_OF_CANDLES)
    if rates is None:
        return

    data = pd.DataFrame(rates)
    last_bar_time = LAST_ORDER_INFO[symbol].get("bar_time", 0)
    past_bars = data[data['time'] > last_bar_time]

    if len(past_bars) < NUMBER_CANDLES_MOVE_STOPLOSS:
        print(f"⏳ Aún no han pasado 3 velas para mover el SL en {symbol}")
        return

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return

    for pos in positions:
        if pos.type == mt5.ORDER_TYPE_BUY and tick.bid > pos.price_open:
            new_sl = pos.price_open
        elif pos.type == mt5.ORDER_TYPE_SELL and tick.ask < pos.price_open:
            new_sl = pos.price_open
        else:
            continue    # No mover SL si aún no estamos en ganancia

        if abs(pos.sl - new_sl) < 0.0001:
            continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.tp,
            "symbol": symbol,
            "magic": pos.magic,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🔁 SL movido a BE en {symbol} (ticket: {pos.ticket})")


def process_symbol(symbol):
    """Procesa un símbolo individual: verifica cruce de EMA y opera."""
    if symbol not in LOTES_POR_SIMBOLO:
        print(f"⚠️ Símbolo no configurado: {symbol}")
        return

    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, NUMBER_OF_CANDLES)
    if rates is None or len(rates) < EMA_PERIOD:
        print(f"⚠️ Datos insuficientes para {symbol}")
        return

    data = pd.DataFrame(rates)
    data['EMA'] = get_ema(data, EMA_PERIOD)

    prev = data.iloc[-2]
    curr = data.iloc[-1]

    cross_above = prev['close'] < prev['EMA'] and curr['close'] > curr['EMA']
    cross_below = prev['close'] > prev['EMA'] and curr['close'] < curr['EMA']

    if not cross_above and not cross_below:
        print(f"🔍 Sin cruce en {symbol}")
        return

    order_type = mt5.ORDER_TYPE_BUY if cross_above else mt5.ORDER_TYPE_SELL
    positions = mt5.positions_get(symbol=symbol)
    same_side_open = any(p.type == order_type for p in positions)

    if same_side_open:
        print(f"⚠️ Ya hay una posición abierta en {symbol} en la misma dirección")
        return

    lot_config = LOTES_POR_SIMBOLO[symbol]
    lot_size = get_valid_lot_size(symbol, lot_config)
    print(f"🛒 Ejecutando orden en {symbol}: {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'} con lote {lot_size}")
    place_order(symbol, lot_size, order_type, STOP_LOSS_PIPS, TAKE_PROFIT_PIPS, data)

def main_loop():
    """Bucle principal que itera constantemente procesando todos los símbolos."""
    while True:
        for symbol in SYMBOLS:
            verificar_y_mover_sl(symbol)
            process_symbol(symbol)
            time.sleep(SLEEP_INTERVAL)
        time.sleep(INTERVAL_SECONDS)

# --- Punto de entrada ---
if __name__ == "__main__":
    try:
        init_mt5()
        #close_all_positions()
        main_loop()
    except KeyboardInterrupt:
        print("🚩 Bot detenido por el usuario.")
    finally:
        mt5.shutdown()