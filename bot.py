import ccxt
import pandas as pd
import os
import time
import json
import logging
import telebot
from datetime import datetime
from dotenv import load_dotenv

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# Configuration
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

telegram_bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# Path for server stability (Railway/Render)
STATE_FILE = '/tmp/trade_state.json' 

def send_telegram(message):
    if telegram_bot and CHAT_ID:
        try:
            telegram_bot.send_message(CHAT_ID, message)
        except Exception as e:
            logging.error(f"Telegram error: {e}")

class PrimeScalpBot:
    def __init__(self):
        self.exchange = ccxt.delta({
            'apiKey': API_KEY, 'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })
        self.symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']
        self.DAILY_LOSS_LIMIT = -600
        self.daily_pnl = 0
        self.today_date = datetime.now().date()
        self.active_trades = {}
        self.pending_entry = {}
        self.last_alert_time = {}
        self.load_trade_state()
        send_telegram("🚀 Prime Scalp - Digital Guardian Active")

    def load_trade_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                self.active_trades = data.get('trades', {})
                self.daily_pnl = data.get('daily_pnl', 0)

    def save_trade_state(self):
        with open(STATE_FILE, 'w') as f:
            json.dump({'trades': self.active_trades, 'daily_pnl': self.daily_pnl, 'date': str(self.today_date)}, f)

    def fetch_indicators(self, symbol, timeframe='5m', limit=100):
        try:
            bars = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            df['tema'] = df['close'].ewm(span=9, adjust=False).mean()
            return df
        except: return None

    def alert_system_1m(self, symbol):
        """नया: 1-मिनट अलर्ट सिस्टम"""
        df = self.fetch_indicators(symbol, '1m', limit=10)
        if df is not None and len(df) > 0:
            if df['close'].iloc[-1] > df['tema'].iloc[-1]: return "1m_BULLISH"
            if df['close'].iloc[-1] < df['tema'].iloc[-1]: return "1m_BEARISH"
        return None

    def run(self):
        while True:
            try:
                for symbol in self.symbols:
                    # 1-मिनट अलर्ट चेक
                    alert = self.alert_system_1m(symbol)
                    if alert:
                        logging.info(f"Alert {symbol}: {alert}")
                    
                    # मुख्य ट्रेडिंग लॉजिक यहाँ जारी रखें...
                    
                time.sleep(10)
            except Exception as e:
                logging.error(f"Loop Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = PrimeScalpBot()
    bot.run()
