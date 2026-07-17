import os
import time
import ccxt
import pandas as pd
import pandas_ta as ta
import telebot

# ========== Setup ==========
API_KEY = str(os.environ.get('API_KEY') or '').strip()
API_SECRET = str(os.environ.get('API_SECRET') or '').strip()
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

# ========== Delta Exchange ==========
exchange = ccxt.delta({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': True
    },
    'headers': {
        'User-Agent': 'Mozilla/5.0'
    }
})

active_trades = {}

# ========== Helper Functions ==========
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
        df['atr'] = ta.atr(df['h'], df['l'], df['c'], length=14)
        df['cmf'] = ta.cmf(df['h'], df['l'], df['c'], df['v'], length=20)
        return df
    except Exception as e:
        print(f"Data Error: {e}")
        return None

def calculate_lot(symbol, balance, price, leverage=25):
    try:
        lot = (balance * leverage) / price
        # BTC/USDT और ETH/USDT के लिए न्यूनतम लॉट साइज
        min_lot = 0.001 if 'BTC' in symbol else 0.01
        return max(min_lot, round(lot, 3))
    except:
        return 0.001

def check_api():
    try:
        exchange.fetch_balance()
        return True
    except Exception as e:
        print(f"API Connection Check Failed: {e}")
        return False

# ========== Main Loop ==========
print("🚀 Prime Scalp Bot Started (Delta - Verified)...")

while True:
    if not check_api():
        time.sleep(30)
        continue

    try:
        balance = exchange.fetch_balance()['USDT']['free']
        
        # ✅ सिम्बल्स में स्लैश (/) का उपयोग किया गया है (Delta के लिए अनिवार्य)
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            
            # एग्जिट लॉजिक (29 मिनट)
            if symbol in active_trades:
                if (time.time() - active_trades[symbol]['time']) > 1740:
                    side = 'sell' if active_trades[symbol]['side'] == 'buy' else 'buy'
                    try:
                        exchange.create_order(symbol, 'market', side, active_trades[symbol]['lot'])
                        del active_trades[symbol]
                        send_alert(f"⏱️ {symbol} Closed.")
                    except Exception as e:
                        print(f"Exit Error: {e}")
                continue

            # एंट्री लॉजिक
            df = get_data(symbol)
            if df is None: continue
            
            last = df.iloc[-1]
            price = last['c']

            # प्राइस अलर्ट (हर मिनट)
            try:
                bot.send_message(CHAT_ID, f"📈 {symbol} | Price: {price} | ATR: {round(last['atr'], 2)} | CMF: {round(last['cmf'], 2)}")
            except: pass

            # एंट्री कंडीशंस (ADX + CMF + SuperTrend)
            is_buy = (last['adx'] > 25) and (last['cmf'] > 0) and (last['c'] > last['supertrend'])
            is_sell = (last['adx'] > 25) and (last['cmf'] < 0) and (last['c'] < last['supertrend'])

            if (is_buy or is_sell) and symbol not in active_trades:
                side = 'buy' if is_buy else 'sell'
                lot = calculate_lot(symbol, balance, price)
                
                try:
                    exchange.create_order(symbol, 'market', side, lot)
                    active_trades[symbol] = {'time': time.time(), 'side': side, 'lot': lot}
                    send_alert(f"✅ {symbol} {side.upper()} Entry! LOT: {lot}")
                except Exception as e:
                    print(f"Entry Error: {e}")

    except Exception as e:
        print(f"Loop Error: {e}")
        
    time.sleep(60)
