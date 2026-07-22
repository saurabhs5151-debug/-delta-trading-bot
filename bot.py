import time
import logging
from datetime import datetime
import pandas as pd
import ccxt
import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Error: {e}")

logging.basicConfig(filename='bot_log.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TradingBot:
    def __init__(self):
        self.symbols = ['BTC/USDT', 'ETH/USDT']
        self.today_date = datetime.now().date()
        self.daily_pnl = 0
        self.DAILY_LOSS_LIMIT = -100
        self.LEVERAGE = 5
        self.last_balance_check = 0
        self.cached_balance = 0
        self.active_trades = {}
        self.pending_entry = {}
        self.last_alert_time = {}
        self.last_alert_seconds = {}
        
        self.exchange = ccxt.delta({
            'apiKey': os.getenv("API_KEY", "YOUR_API_KEY"),
            'secret': os.getenv("SECRET_KEY", "YOUR_SECRET_KEY"),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

    def run(self):
        send_telegram("🟢 Bot Loop Started Successfully (2-Min Rate Alert Mode).")
        while True:
            try:
                if datetime.now().date() != self.today_date:
                    self.daily_pnl = 0
                    self.today_date = datetime.now().date()
                    self.save_trade_state()
                    send_telegram("📅 New Day - PnL Reset")

                if self.daily_pnl <= self.DAILY_LOSS_LIMIT:
                    if self.LEVERAGE != 5:
                        self.LEVERAGE = 5
                        send_telegram("⚠️ Daily Loss Limit Hit! Leverage → 5x")

                if time.time() - self.last_balance_check > 300:
                    self.cached_balance = self.get_balance()
                    self.last_balance_check = time.time()

                for symbol in self.symbols:
                    if self.is_volatile_news(symbol):
                        if symbol in self.active_trades:
                            self.emergency_exit(symbol)
                        continue

                    df_1m = self.fetch_indicators(symbol, '1m', limit=20)
                    if df_1m is None or len(df_1m) == 0:
                        continue

                    current_price = df_1m['close'].iloc[-1]

                    # हर 2 मिनट (120 सेकंड) में रेट अपडेट
                    now_time = time.time()
                    if symbol not in self.last_alert_seconds:
                        self.last_alert_seconds[symbol] = 0

                    if now_time - self.last_alert_seconds[symbol] >= 120:
                        self.last_alert_seconds[symbol] = now_time
                        send_telegram(f"📊 *{symbol} Price Update*: `{current_price:.2f}`")

                    last_ts = str(df_1m.index[-1])
                    if self.last_alert_time.get(symbol) != last_ts:
                        self.last_alert_time[symbol] = last_ts
                        signal = self.check_entry(df_1m)
                        if signal and symbol not in self.active_trades:
                            self.pending_entry[symbol] = {'signal': signal}
                            send_telegram(f"🔔 *Alert*: {symbol} Signal -> *{signal.upper()}*")

                    if self.pending_entry.get(symbol) and symbol not in self.active_trades:
                        df_5m = self.fetch_indicators(symbol, '5m', limit=50)
                        if df_5m is not None and len(df_5m) > 0:
                            signal_5m = self.check_entry(df_5m)
                            if signal_5m == self.pending_entry[symbol]['signal']:
                                price = df_5m['close'].iloc[-1]
                                atr = df_5m['atr'].iloc[-1]
                                lot = self.calculate_lot(symbol, price)
                                if lot > 0:
                                    side = 'buy' if signal_5m == 'long' else 'sell'
                                    order = self.place_order(symbol, side, lot, price)
                                    if order:
                                        sl_price = price - (atr * 1.0) if signal_5m == 'long' else price + (atr * 1.0)
                                        self.active_trades[symbol] = {
                                            'entry_price': price,
                                            'direction': signal_5m,
                                            'total_amount': lot,
                                            'remaining_amount': lot,
                                            'sl_price': sl_price,
                                            'atr': atr,
                                            'entry_time': datetime.now(),
                                            'stage': 0,
                                            'stall_triggered': False
                                        }
                                        self.pending_entry[symbol] = None
                                        self.save_trade_state()
                                        send_telegram(f"🎯 *Trade Executed ({symbol})*\nSide: *{side.upper()}*\nPrice: `{price}`\nSL: `{sl_price:.2f}`")

                for symbol in list(self.active_trades.keys()):
                    trade = self.active_trades[symbol]
                    df_price = self.fetch_indicators(symbol, '1m', limit=1)
                    if df_price is None or len(df_price) == 0:
                        continue
                    current = df_price['close'].iloc[-1]
                    
                    self.partial_book(symbol, trade, current)
                    self.update_trailing_sl(symbol, trade, current)
                    
                    if self.check_exit_conditions(symbol, trade):
                        self.emergency_exit(symbol)
                        continue
                        
                    if (trade['direction'] == 'long' and current <= trade['sl_price']) or (trade['direction'] == 'short' and current >= trade['sl_price']):
                        send_telegram(f"🛑 *SL Hit*: {symbol} @ `{current}`")
                        self.emergency_exit(symbol)
                        continue

                time.sleep(10)

            except KeyboardInterrupt:
                send_telegram("🛑 Bot stopped manually.")
                break
            except Exception as e:
                send_telegram(f"💥 *Critical error*: {e}")
                logging.error(f"Critical Loop Error: {e}")
                time.sleep(60)

    def get_balance(self):
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except:
            return 0

    def is_volatile_news(self, symbol):
        return False

    def fetch_indicators(self, symbol, timeframe, limit):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['atr'] = (df['high'] - df['low']).rolling(14).mean()
            return df
        except Exception as e:
            logging.error(f"Error fetching indicators for {symbol}: {e}")
            return None

    def check_entry(self, df):
        return None

    def calculate_lot(self, symbol, price):
        return 0.001

    def place_order(self, symbol, side, lot, price):
        try:
            return True
        except Exception as e:
            send_telegram(f"Order Error: {e}")
            return False

    def save_trade_state(self):
        pass

    def partial_book(self, symbol, trade, current_price):
        pass

    def update_trailing_sl(self, symbol, trade, current_price):
        pass

    def check_exit_conditions(self, symbol, trade):
        return False

    def emergency_exit(self, symbol):
        if symbol in self.active_trades:
            del self.active_trades[symbol]
            send_telegram(f"🛑 *Emergency Exit / Close*: {symbol}")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
