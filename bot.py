import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os

# 1. एक्सचेंज कनेक्शन
exchange = ccxt.delta({
    'apiKey': os.environ.get('API_KEY'),
    'secret': os.environ.get('API_SECRET'),
})

# सेटिंग्स
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'GOLD/USDT', 'PEPE/USDT']
LEVERAGE = 25
CAPITAL_USAGE = 0.50
MAX_HOLD_TIME = 1740  # 29 मिनट
active_positions = {}

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # इंडिकेटर्स
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        df['rsi'] = ta.rsi(df['close'], length=6)
        df['ema9'] = ta.ema(df['close'], length=9)
        df['ema21'] = ta.ema(df['close'], length=21)
        adx_res = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_res['ADX_14']
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
        
        return df.iloc[-1]
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def run_prime_scalp():
    for symbol in SYMBOLS:
        # 29 मिनट का टाइम चेक
        if symbol in active_positions:
            if (time.time() - active_positions[symbol]['time']) > MAX_HOLD_TIME:
                print(f">>> 29 Min Limit Reached! Closing {symbol}...")
                # यहाँ पोजीशन क्लोज करने का लॉजिक है
                exchange.create_order(symbol, 'market', 'sell' if active_positions[symbol]['side'] == 'buy' else 'buy', active_positions[symbol]['qty'])
                del active_positions[symbol]
                continue

        data = get_data(symbol)
        if data is None: continue

        # एंट्री सिग्नल्स
        if symbol not in active_positions:
            # BUY
            if data['close'] > data['vwap'] and data['ema9'] > data['ema21'] and data['adx'] > 25 and data['cmf'] > 0 and data['rsi'] > 50:
                balance = exchange.fetch_balance()['total']['USDT']
                qty = (balance * CAPITAL_USAGE * LEVERAGE) / data['close']
                exchange.create_order(symbol, 'market', 'buy', qty)
                active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'buy'}
                print(f">>> BUY Order Placed for {symbol}")

            # SELL
            elif data['close'] < data['vwap'] and data['ema9'] < data['ema21'] and data['adx'] > 25 and data['cmf'] < 0 and data['rsi'] < 50:
                balance = exchange.fetch_balance()['total']['USDT']
                qty = (balance * CAPITAL_USAGE * LEVERAGE) / data['close']
                exchange.create_order(symbol, 'market', 'sell', qty)
                active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'sell'}
                print(f">>> SELL Order Placed for {symbol}")

# मुख्य लूप (Infinite Loop)
print("Bot Started...")
while True:
    run_prime_scalp()
    time.sleep(60) # हर 1 मिनट में चेक करेगा
