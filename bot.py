import ccxt
import pandas as pd
import pandas_ta as ta
import os
import time

# एक्सचेंज कनेक्शन
exchange = ccxt.delta({
    'apiKey': os.environ.get('API_KEY'),
    'secret': os.environ.get('API_SECRET'),
})

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'GOLD/USDT', 'PEPE/USDT']
LEVERAGE = 25
CAPITAL_USAGE = 0.50 # 50% मार्जिन
MAX_HOLD_TIME = 1740 # 29 मिनट

# पोजीशन ट्रैक करने के लिए डिक्शनरी
active_positions = {}

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        df['rsi'] = ta.rsi(df['close'], length=6)
        df['ema9'] = ta.ema(df['close'], length=9)
        df['ema21'] = ta.ema(df['close'], length=21)
        adx_res = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_res['ADX_14']
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        return df.iloc[-1]
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def run_prime_scalp():
    for symbol in SYMBOLS:
        data = get_data(symbol)
        if data is None: continue
        
        print(f"[{symbol}] Price: {data['close']} | RSI: {data['rsi']:.2f}")

        # अगर पोजीशन पहले से खुली है (29 मिनट का चेक)
        if symbol in active_positions:
            if (time.time() - active_positions[symbol]['time']) > MAX_HOLD_TIME:
                print(f">>> 29 Min Limit Reached! Closing {symbol}...")
                exchange.create_order(symbol, 'limit', 'sell' if active_positions[symbol]['side'] == 'buy' else 'buy', active_positions[symbol]['qty'], data['close'])
                del active_positions[symbol]
            continue

        # एंट्री सिग्नल्स
        if data['close'] > data['vwap'] and data['ema9'] > data['ema21'] and data['adx'] > 25 and data['cmf'] > 0 and data['rsi'] > 50:
            qty = (exchange.fetch_balance()['total']['USDT'] * CAPITAL_USAGE * LEVERAGE) / data['close']
            exchange.create_order(symbol, 'limit', 'buy', qty, data['close'])
            active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'buy'}
            print(f">>> BUY Order Placed for {symbol}")

        elif data['close'] < data['vwap'] and data['ema9'] < data['ema21'] and data['adx'] > 25 and data['cmf'] < 0 and data['rsi'] < 50:
            qty = (exchange.fetch_balance()['total']['USDT'] * CAPITAL_USAGE * LEVERAGE) / data['close']
            exchange.create_order(symbol, 'limit', 'sell', qty, data['close'])
            active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'sell'}
            print(f">>> SELL Order Placed for {symbol}")

while True:
    run_prime_scalp()
    time.sleep(60)
