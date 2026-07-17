import os
import time
import ccxt
import pandas as pd
import telebot

# ========== Setup ==========
API_KEY = str(os.environ.get('API_KEY') or '').strip()
API_SECRET = str(os.environ.get('API_SECRET') or '').strip()
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

exchange = ccxt.delta({
    'apiKey': API_KEY, 'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
})

def send_alert(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
    except Exception as e: print(f"Telegram Error: {e}")

def get_data(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        # Simple EMA calculation using Pandas
        df['ema_9'] = df['c'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['c'].ewm(span=21, adjust=False).mean()
        return df
    except Exception as e:
        print(f"Data Error: {e}")
        return None

# ========== Main Loop ==========
print("🚀 Prime Scalp Bot Running (Lightweight)...")

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            df = get_data(symbol)
            if df is None: continue
            
            last = df.iloc[-1]
            # Simple Logic: Price > EMA 9
            is_buy = last['c'] > last['ema_9']
            is_sell = last['c'] < last['ema_9']

            # Telegram status update every minute
            bot.send_message(CHAT_ID, f"📈 {symbol} | Price: {last['c']} | EMA9: {round(last['ema_9'], 2)}")
            time.sleep(2) # To avoid spamming Telegram API
            
    except Exception as e:
        print(f"Loop Error: {e}")
    
    time.sleep(60)
