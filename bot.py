import os
import time
import ccxt
import pandas as pd
import pandas_ta as ta
import telebot

# 1. SETUP & CONFIGURATION
API_KEY = str(os.environ.get('API_KEY') or '').strip()
API_SECRET = str(os.environ.get('API_SECRET') or '').strip()
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

# Initialize Exchange
exchange = ccxt.delta({
    'apiKey': API_KEY, 
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': True
    },
    'headers': {'User-Agent': 'Mozilla/5.0'}
})

active_trades = {}

# 2. HELPER FUNCTIONS
def send_alert(msg):
    try:
        bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
    except:
        pass

def check_api():
    try:
        exchange.fetch_balance()
        return True
    except:
        return False

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        df['ema_9'] = ta.ema(df['c'], length=9)
        df['ema_21'] = ta.ema(df['c'], length=21)
        st = ta.supertrend(df['h'], df['l'], df['c'], length=10, multiplier=3)
        df['supertrend'] = st['SUPERT_10_3.0']
        df['adx'] = ta.adx(df['h'], df['l'], df['c'], length=14)['ADX_14']
        df['rsi'] = ta.rsi(df['c'], length=14)
        return df
    except:
        return None

def calculate_lot(symbol, balance):
    try:
        price = exchange.fetch_ticker(symbol)['last']
        lot = (balance * 25) / price
        min_lot = 0.001 if symbol == 'BTC/USDT' else 0.01
        return max(min_lot, round(lot, 3))
    except:
        return 0.001

# 3. MAIN TRADING LOOP
print("🚀 Prime Scalp Bot Started...")

while True:
    if not check_api():
        time.sleep(60)
        continue

    try:
        balance = exchange.fetch_balance()['USDT']['free']
        
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            # Exit Logic
            if symbol in active_trades:
                if (time.time() - active_trades[symbol]['time']) > 1740:
                    side = 'sell' if active_trades[symbol]['side'] == 'buy' else 'buy'
                    try:
                        exchange.create_order(symbol, 'market', side, active_trades[symbol]['lot'])
                        del active_trades[symbol]
                        send_alert(f"⏱️ {symbol} Closed.")
                    except: pass
                continue

            # Entry Logic
            df = get_data(symbol)
            if df is None: continue
            
            last = df.iloc[-1]
            is_buy = (last['adx'] > 25) and (last['rsi'] > 50) and (last['ema_9'] > last['ema_21']) and (last['c'] > last['supertrend'])
            is_sell = (last['adx'] > 25) and (last['rsi'] < 50) and (last['ema_9'] < last['ema_21']) and (last['c'] < last['supertrend'])

            if (is_buy or is_sell) and symbol not in active_trades:
                side = 'buy' if is_buy else 'sell'
                lot = calculate_lot(symbol, balance)
                try:
                    exchange.create_order(symbol, 'limit', side, lot, last['c'])
                    active_trades[symbol] = {'time': time.time(), 'side': side, 'lot': lot}
                    send_alert(f"✅ {symbol} {side.upper()} Entry!")
                except: pass

    except: pass
    time.sleep(60)
