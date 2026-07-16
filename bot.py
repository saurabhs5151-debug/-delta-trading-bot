
        import ccxt, pandas as pd, pandas_ta as ta, time, os

# एक्सचेंज कनेक्शन
exchange = ccxt.delta({'apiKey': os.environ.get('API_KEY'), 'secret': os.environ.get('API_SECRET')})

SYMBOLS = ['BTC/USDT', 'ETH/USDT'] 
active_positions = {}

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # 7 इंडिकेटर्स (Original Setup)
        df['vwap'] = ta.vwap(df['h'], df['l'], df['c'], df['v'])
        df['tema9'] = ta.tema(df['c'], length=9)
        # SuperTrend (Standard)
        st = ta.supertrend(df['h'], df['l'], df['c'], length=10, multiplier=3)
        df['st'] = st['SUPERT_10_3.0']
        df['rsi'] = ta.rsi(df['c'], length=14)
        df['adx'] = ta.adx(df['h'], df['l'], df['c'], length=14)['ADX_14']
        df['cmf'] = ta.cmf(df['h'], df['l'], df['c'], df['v'], length=20)
        
        return df.iloc[-1]
    except: return None

def run_bot():
    for symbol in SYMBOLS:
        data = get_data(symbol)
        if data is None: continue
        
        # 6 एंट्री कंडीशंस (Original Rules)
        is_buy = (data['c'] > data['vwap']) and (data['c'] > data['tema9']) and (data['st'] < data['c']) and (data['rsi'] > 50) and (data['adx'] > 25) and (data['cmf'] > 0)
        is_sell = (data['c'] < data['vwap']) and (data['c'] < data['tema9']) and (data['st'] > data['c']) and (data['rsi'] < 50) and (data['adx'] > 25) and (data['cmf'] < 0)

        if symbol not in active_positions:
            if is_buy or is_sell:
                side = 'buy' if is_buy else 'sell'
                print(f"Entry {side.upper()} on {symbol}")
                # यहाँ आर्डर प्लेसमेंट का कोड आएगा
                active_positions[symbol] = {'side': side}

while True:
    try: run_bot()
    except Exception as e: print(e)
    time.sleep(60)
