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

SYMBOLS = ['BTC/USDT', 'ETH/USDT'] 
LEVERAGE = 25
CAPITAL_USAGE = 0.50
MAX_HOLD_TIME = 1740 
active_positions = {}

def get_data(symbol):
    try:
        # डेटा फेच करने का प्रयास
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        if bars is None or len(bars) == 0:
            print(f"[{symbol}] डेटा खाली मिला (No data).")
            return None
            
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
        print(f"Error fetching data for {symbol}: {e}")
        return None

def run_prime_scalp():
    print(f"--- {time.strftime('%H:%M:%S')} | हार्टबीट: बोट चेक कर रहा है ---")
    for symbol in SYMBOLS:
        if symbol in active_positions:
            if (time.time() - active_positions[symbol]['time']) > MAX_HOLD_TIME:
                print(f">>> 29 Min Limit reached! Closing {symbol}...")
                side = 'sell' if active_positions[symbol]['side'] == 'buy' else 'buy'
                exchange.create_order(symbol, 'market', side, active_positions[symbol]['qty'])
                del active_positions[symbol]
                continue

        data = get_data(symbol)
        if data is None or data.isnull().any():
            continue

        # इंडिकेटर वैल्यूज प्रिंट करना (डिबगिंग के लिए)
        print(f"[{symbol}] Price: {data['close']:.2f} | RSI: {data['rsi']:.2f} | ADX: {data['adx']:.2f}")

        if symbol not in active_positions:
            # BUY लॉजिक
            if data['close'] > data['vwap'] and data['ema9'] > data['ema21'] and data['adx'] > 25 and data['cmf'] > 0 and data['rsi'] > 50:
                print(f"[{symbol}] एंट्री कंडीशन मैच: BUY")
                try:
                    balance = exchange.fetch_balance()['total']['USDT']
                    qty = (balance * CAPITAL_USAGE * LEVERAGE) / data['close']
                    exchange.create_order(symbol, 'market', 'buy', qty)
                    active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'buy'}
                except Exception as e:
                    print(f"Order Error: {e}")

            # SELL लॉजिक
            elif data['close'] < data['vwap'] and data['ema9'] < data['ema21'] and data['adx'] > 25 and data['cmf'] < 0 and data['rsi'] < 50:
                print(f"[{symbol}] एंट्री कंडीशन मैच: SELL")
                try:
                    balance = exchange.fetch_balance()['total']['USDT']
                    qty = (balance * CAPITAL_USAGE * LEVERAGE) / data['close']
                    exchange.create_order(symbol, 'market', 'sell', qty)
                    active_positions[symbol] = {'time': time.time(), 'qty': qty, 'side': 'sell'}
                except Exception as e:
                    print(f"Order Error: {e}")

# मुख्य लूप
print("Bot Started Successfully...")
while True:
    try:
        run_prime_scalp()
    except Exception as e:
        print(f"Critical Loop Error: {e}")
    time.sleep(60) 
