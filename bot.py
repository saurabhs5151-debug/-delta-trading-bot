import time
import json
import os
import logging
import requests  # टेलीग्राम मैसेज भेजने के लिए जरूरी
from datetime import datetime

# ==========================================
# 1. LOGGING & TELEGRAM CONFIG SETUP
# ==========================================
logging.basicConfig(
    filename='bot_log.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# टेलीग्राम बॉट टोकन और चैट आईडी यहाँ सेट करें
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # अपना बोट टोकन यहाँ डालें
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"      # अपनी चैट आईडी यहाँ डालें

def send_telegram_alert(message):
    """टेलीग्राम पर तुरंत लाइव अलर्ट भेजने का फंक्शन"""
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logging.warning("Telegram Token not set. Skipping telegram alert.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 *PRIME SCALP ALERT* 🚨\n\n{message}",
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if not response.ok:
            logging.error(f"Telegram alert failed: {response.text}")
    except Exception as e:
        logging.error(f"Telegram connection error: {e}")

# ==========================================
# 2. STATE PERSISTENCE (`trade_state.json`)
# ==========================================
STATE_FILE = 'trade_state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"State load error: {e}")
    return {
        "active_trade": None, 
        "daily_pnl": 0.0, 
        "partial_booked_25": False,
        "partial_booked_50": False,
        "current_sl": 0.0
    }

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"State save error: {e}")

# ==========================================
# 3. PRIME SCALP BOT ENGINE (WITH TELEGRAM)
# ==========================================
class PrimeScalpTelegramBot:
    def __init__(self):
        self.state = load_state()
        self.symbols = ["BTC/USD", "ETH/USD"]
        logging.info("Prime Scalp Bot initialized with Telegram Alerts.")

    def get_market_data(self, symbol):
        return {
            "score": 5,                 
            "adx": 22,                  
            "price": 65000.0,           
            "atr": 150.0,               
            "avg_atr": 140.0,           
            "is_big_candle": False,     
            "high_5m": 65200.0,         
            "low_5m": 64800.0,          
            "current_1m_close": 65050.0 
        }

    def check_news_killer(self, data):
        if data["atr"] >= (data["avg_atr"] * 2.0) or data["is_big_candle"]:
            msg = "NEWS KILLER TRIGGERED: ATR Spike or Big Candle! Flattening trade."
            logging.warning(msg)
            send_telegram_alert(msg)
            if self.state["active_trade"] is not None:
                self.flatten_trade("News Killer Emergency Exit")
            return True
        return False

    def get_market_regime_leverage(self, adx, daily_pnl):
        if daily_pnl <= -600.0:
            return 5  # Smart Throttle
        if adx > 25:
            return 25
        elif 20 <= adx <= 25:
            return 15
        else:
            return 5

    def calculate_lot(self, balance, leverage, price):
        if balance <= 0 or price <= 0:
            return 0.0
        return round((balance * leverage) / price, 6)

    def place_limit_order(self, symbol, lot, price):
        logging.info(f"PLACING LIMIT ORDER (Maker): Symbol={symbol}, Lot={lot}, Price={price}, postOnly=True")
        return True

    def flatten_trade(self, reason):
        msg = f"Trade Flattened/Closed. Reason: {reason}"
        logging.info(msg)
        send_telegram_alert(msg)
        self.state["active_trade"] = None
        self.state["partial_booked_25"] = False
        self.state["partial_booked_50"] = False
        self.state["current_sl"] = 0.0
        save_state(self.state)

    def manage_active_trade(self, data):
        trade = self.state["active_trade"]
        if not trade:
            return

        current_price = data["price"]
        entry_price = trade["entry_price"]
        atr = data["atr"]
        symbol = trade["symbol"]
        side = trade.get("side", "BUY")
        
        price_diff = (current_price - entry_price) if side == "BUY" else (entry_price - current_price)

        # Partial Booking 25% -> Breakeven
        if not self.state["partial_booked_25"] and price_diff >= (atr * 1.5):
            msg = f"Partial Booking 25% done for {symbol}. Moving SL to Breakeven."
            logging.info(msg)
            send_telegram_alert(msg)
            self.state["partial_booked_25"] = True
            self.state["current_sl"] = entry_price
            save_state(self.state)

        # Partial Booking 50% -> Trailing SL
        if not self.state["partial_booked_50"] and price_diff >= (atr * 2.5):
            msg = f"Partial Booking 50% done for {symbol}. Activating ATR x 2.0 Trailing SL."
            logging.info(msg)
            send_telegram_alert(msg)
            self.state["partial_booked_50"] = True
            save_state(self.state)

        # Trailing SL Update
        if self.state["partial_booked_50"]:
            if side == "BUY":
                new_trail_sl = current_price - (atr * 2.0)
                if new_trail_sl > self.state["current_sl"]:
                    self.state["current_sl"] = new_trail_sl
            else:
                new_trail_sl = current_price + (atr * 2.0)
                if new_trail_sl < self.state["current_sl"] or self.state["current_sl"] == 0.0:
                    self.state["current_sl"] = new_trail_sl
            save_state(self.state)

            if (side == "BUY" and current_price <= self.state["current_sl"]) or \
               (side == "SELL" and current_price >= self.state["current_sl"]):
                self.flatten_trade("Trailing SL Hit")
                return

        # Stalling Sensor
        stalling_range = atr * 1.5
        if abs(price_diff) < stalling_range:
            elapsed_active_min = (time.time() - trade["entry_time"]) / 60
            if 3 <= elapsed_active_min <= 5:
                if not self.state["partial_booked_25"]:
                    self.state["current_sl"] = entry_price
                    save_state(self.state)
            elif elapsed_active_min > 7:
                self.flatten_trade("Stalling Sensor Time Exit")
                return

        # Volatility Spike
        if data["current_1m_close"] > data["high_5m"] or data["current_1m_close"] < data["low_5m"]:
            self.flatten_trade("Volatility Spike Emergency Exit")
            return

        # Hard Time Exit (29 mins)
        elapsed_time = (time.time() - trade["entry_time"]) / 60
        if elapsed_time >= 29:
            self.flatten_trade("29 Mins Hard Time Exit")

    def run_trading_loop(self):
        logging.info("Starting 24/7 Prime Scalp Loop with Telegram Alerts...")
        send_telegram_alert("🟢 Prime Scalp Bot successfully started and running on AWS!")
        
        while True:
            try:
                for symbol in self.symbols:
                    data = self.get_market_data(symbol)

                    if self.check_news_killer(data):
                        time.sleep(10)
                        continue

                    if self.state["active_trade"] is not None:
                        self.manage_active_trade(data)
                    else:
                        if data["score"] < 4:
                            continue

                        balance = 100.0
                        leverage = self.get_market_regime_leverage(data["adx"], self.state["daily_pnl"])
                        lot = self.calculate_lot(balance, leverage, data["price"])

                        if lot <= 0:
                            continue

                        success = self.place_limit_order(symbol, lot, data["price"])
                        if success:
                            initial_sl = data["price"] - data["atr"]
                            self.state["active_trade"] = {
                                "symbol": symbol,
                                "side": "BUY",
                                "entry_price": data["price"],
                                "lot": lot,
                                "leverage": leverage,
                                "entry_time": time.time()
                            }
                            self.state["partial_booked_25"] = False
                            self.state["partial_booked_50"] = False
                            self.state["current_sl"] = initial_sl
                            save_state(self.state)
                            
                            # टेलीग्राम अलर्ट भेजना जब नया ट्रेड खुले
                            alert_msg = f"✅ *New Trade Executed*\nSymbol: {symbol}\nPrice: {data['price']}\nLeverage: {leverage}x\nLot: {lot}"
                            logging.info(alert_msg)
                            send_telegram_alert(alert_msg)

                # प्रत्येक 2 मिनट (120 सेकंड) में लूप चेक और लाइव स्टेटस अपडेट
                time.sleep(120)

            except Exception as e:
                err_msg = f"CRITICAL ERROR: {e}. Reconnecting in 10 secs..."
                logging.error(err_msg)
                send_telegram_alert(err_msg)
                time.sleep(10)

if __name__ == "__main__":
    bot = PrimeScalpTelegramBot()
    try:
        bot.run_trading_loop()
    except KeyboardInterrupt:
        logging.info("Bot manually stopped.")
    except Exception as e:
        logging.critical(f"Fatal exception: {e}")