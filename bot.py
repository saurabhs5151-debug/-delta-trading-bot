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
    'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
})

active_trades = {}

def send_alert(msg):
    try:
        bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        print(f"Telegram Sent: {msg}")
    except Exception as e:
        print(f"Telegram Error: {e}")

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
    except Exception as e:
        print(f"Data Error for {symbol}: {e}")
        return None

# 3. MAIN TRADING LOOP
print("🚀 BOT STARTED SUCCESSFULLY...")

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        print(f"💰 Current Balance: {balance}")
        
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            # Exit Logic
            if symbol in active_trades:
                if (time.time() - active_trades[symbol]['time']) > 1740:
                    side = 'sell' if active_trades[symbol]['side'] == 'buy' else 'buy'
                    exchange.create_order(symbol, 'market', side, active_trades[symbol]['lot'])
                    del active_trades[symbol]
                    send_alert(f"⏱️ {symbol} Trade Closed.")
                continue

            # Entry Logic
            df = get_data(symbol)
            if df is None: continue
            
            last = df.iloc[-1]
            print(f"📊 {symbol} | ADX: {last['adx']:.2f} | RSI: {last['rsi']:.2f}")

            is_buy = (last['adx'] > 25) and (last['rsi'] > 50) and (last['ema_9'] > last['ema_21']) and (last['c'] > last['supertrend'])
            is_sell = (last['adx'] > 25) and (last['rsi'] < 50) and (last['ema_9'] < last['ema_21']) and (last['c'] < last['supertrend'])

            if (is_buy or is_sell) and symbol not in active_trades:
                side = 'buy' if is_buy else 'sell'
                lot = 0.001 if symbol == 'BTC/USDT' else 0.01
                exchange.create_order(symbol, 'limit', side, lot, last['c'])
                active_trades[symbol] = {'time': time.time(), 'side': side, 'lot': lot}
                send_alert(f"✅ {symbol} {side.upper()} Entry!")

    except Exception as e:
        print(f"Loop Error: {e}")
        
    time.sleep(60)
