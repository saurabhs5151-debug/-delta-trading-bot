import ccxt, pandas as pd, pandas_ta as ta, time, os, telebot

# सेटिंग्स
exchange = ccxt.delta({'apiKey': os.environ.get('API_KEY'), 'secret': os.environ.get('API_SECRET')})
bot = telebot.TeleBot(os.environ.get('TELEGRAM_BOT_TOKEN'))
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

SYMBOLS = ['BTC/USDT', 'ETH/USDT']
active_positions = {}

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # 7 इंडिकेटर्स
        df['vwap'] = ta.vwap(df['h'], df['l'], df['c'], df['v'])
        df['tema9'] = ta.tema(df['c'], length=9)
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
        
        # 6 एंट्री शर्तें
        is_buy = (data['c'] > data['vwap']) and (data['c'] > data['tema9']) and (data['st'] < data['c']) and (data['rsi'] > 50) and (data['adx'] > 25) and (data['cmf'] > 0)
        is_sell = (data['c'] < data['vwap']) and (data['c'] < data['tema9']) and (data['st'] > data['c']) and (data['rsi'] < 50) and (data['adx'] > 25) and (data['cmf'] < 0)

        if symbol not in active_positions:
            if is_buy or is_sell:
                side = 'BUY' if is_buy else 'SELL'
                msg = f"🚀 Prime Scalp Signal: {symbol} | {side} @ {data['c']:.2f}"
                bot.send_message(CHAT_ID, msg)
                active_positions[symbol] = {'side': side}

while True:
    try: run_bot()
    except Exception as e: print(e)
    time.sleep(60)

        