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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_log.log"), logging.StreamHandler()]
)

load_dotenv()

# Configuration
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

telegram_bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def send_telegram(message):
    if telegram_bot and CHAT_ID:
        try:
            telegram_bot.send_message(CHAT_ID, message)
        except Exception as e:
            logging.error(f"Telegram error: {e}")

# ====== Pandas_ta import with fallback ======
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logging.warning("⚠️ pandas_ta not installed. Using basic EMA logic.")
    ta = type('obj', (object,), {'ema': lambda s, l: s.ewm(span=l, adjust=False).mean()})()

class PrimeScalpBot:
    def __init__(self):
        self.exchange = ccxt.delta({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })
        self.symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']
        self.BASE_LEVERAGE = 25
        self.MID_LEVERAGE = 15
        self.MIN_LEVERAGE = 5
        self.LEVERAGE = 25
        self.DAILY_LOSS_LIMIT = -600
        self.daily_pnl = 0
        self.today_date = datetime.now().date()
        self.active_trades = {}
        self.pending_entry = {}
        self.last_alert_time = {}
        self.cached_balance = 1000
        self.last_balance_check = 0
        self.load_trade_state()
        
        self.cached_balance = self.get_balance()
        self.last_balance_check = time.time()
        
        send_telegram("🚀 Prime Scalp - Digital Guardian Active")
        logging.info("🚀 Prime Scalp Active")

    def load_trade_state(self):
        if os.path.exists('trade_state.json'):
            try:
                with open('trade_state.json', 'r') as f:
                    data = json.load(f)
                    self.active_trades = data.get('trades', {})
                    self.daily_pnl = data.get('daily_pnl', 0)
                    self.today_date = datetime.strptime(data.get('date', str(datetime.now().date())), '%Y-%m-%d').date()
            except Exception as e:
                logging.error(f"Load state error: {e}")

    def save_trade_state(self):
        try:
            with open('trade_state.json', 'w') as f:
                json.dump({'trades': self.active_trades, 'daily_pnl': self.daily_pnl, 'date': str(self.today_date)}, f, indent=4)
        except Exception as e:
            logging.error(f"Save state error: {e}")

    def get_balance(self):
        try:
            bal = self.exchange.fetch_balance()
            return bal['total'].get('USD', bal['total'].get('USDT', 1000))
        except:
            return 1000

    def calculate_lot(self, symbol, price):
        raw = (self.cached_balance * 0.25 * self.LEVERAGE) / price
        return round(raw, 4) if 'BTC' in symbol else round(raw, 2)

    def fetch_indicators(self, symbol, timeframe='5m', limit=100):
        try:
            bars = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not bars or len(bars) == 0:
                return None
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df[~df.index.duplicated(keep='last')]
            df = df.sort_index()
            
            if PANDAS_TA_AVAILABLE:
                df['tema'] = ta.tema(df['close'], length=9)
                df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
                st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
                if st is not None and not st.empty:
                    df['st'] = st.iloc[:, 0]
                else:
                    df['st'] = 1
                df['rsi'] = ta.rsi(df['close'], length=7)
                adx_res = ta.adx(df['high'], df['low'], df['close'], length=20)
                if adx_res is not None and not adx_res.empty:
                    df['adx'] = adx_res.iloc[:, 0]
                else:
                    df['adx'] = 25
                df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=10)
                df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            else:
                df['tema'] = df['close'].ewm(span=9, adjust=False).mean()
                df['vwap'] = (df['high'] + df['low'] + df['close']) / 3
                df['st'] = 1
                df['rsi'] = 50
                df['adx'] = 25
                df['cmf'] = 0.1
                df['atr'] = (df['high'] - df['low']).rolling(14).mean()
            return df
        except Exception as e:
            logging.error(f"Indicator Error ({symbol}): {e}")
            return None

    def check_entry(self, df):
        if not PANDAS_TA_AVAILABLE or df is None or len(df) == 0:
            return None
        last = df.iloc[-1]
        
        # Safe extraction with None protection
        close = last.get('close')
        tema = last.get('tema')
        vwap = last.get('vwap')
        st = last.get('st', 1)
        rsi = last.get('rsi')
        adx = last.get('adx')
        cmf = last.get('cmf')
        
        if any(v is None for v in [close, tema, vwap, rsi, adx, cmf]):
            return None

        long_cond = (close > tema and close > vwap and st == 1 and rsi > 50 and adx > 20 and cmf > 0.05)
        short_cond = (close < tema and close < vwap and st == -1 and rsi < 50 and adx > 20 and cmf < -0.05)
        return 'long' if long_cond else 'short' if short_cond else None

    def place_order(self, symbol, side, amount, price):
        if amount <= 0:
            send_telegram(f"⚠️ LOT 0 - Balance low, skip ({symbol})")
            logging.warning(f"LOT 0 - Skip: {symbol}")
            return None
        try:
            order = self.exchange.create_limit_order(symbol, side, amount, price, params={'postOnly': True})
            time.sleep(5)
            status = self.exchange.fetch_order(order['id'], symbol)
            if status['status'] == 'open':
                self.exchange.cancel_order(order['id'], symbol)
                send_telegram(f"⚠️ Limit order not filled, cancelled: {symbol}")
                return None
            msg = f"✅ {side.upper()} {symbol} {amount} @ {price} (Leverage: {self.LEVERAGE}x)"
            send_telegram(msg)
            logging.info(msg)
            return order
        except Exception as e:
            send_telegram(f"❌ Order failed: {e}")
            logging.error(f"Order failed: {e}")
            return None

    def partial_book(self, symbol, trade, current_price):
        stage = trade.get('stage', 0)
        direction = trade['direction']
        entry = trade['entry_price']
        atr = trade.get('atr', 1)
        remaining = trade['remaining_amount']
        qty_total = trade['total_amount']

        if stage == 0:
            tp1 = entry + (atr * 1.5) if direction == 'long' else entry - (atr * 1.5)
            if (direction == 'long' and current_price >= tp1) or (direction == 'short' and current_price <= tp1):
                qty = round(qty_total * 0.25, 4 if 'BTC' in symbol else 2)
                if qty > 0 and qty <= remaining:
                    try:
                        self.exchange.create_market_order(symbol, 'sell' if direction == 'long' else 'buy', qty)
                        trade['stage'] = 1
                        trade['sl_price'] = entry
                        trade['remaining_amount'] -= qty
                        send_telegram(f"📈 25% Book: {symbol} @ {current_price}")
                        logging.info(f"25% Book: {symbol}")
                    except Exception as e:
                        logging.error(f"Book error: {e}")
        elif stage == 1:
            tp2 = entry + (atr * 2.5) if direction == 'long' else entry - (atr * 2.5)
            if (direction == 'long' and current_price >= tp2) or (direction == 'short' and current_price <= tp2):
                qty = round(qty_total * 0.50, 4 if 'BTC' in symbol else 2)
                if qty > 0 and qty <= remaining:
                    try:
                        self.exchange.create_market_order(symbol, 'sell' if direction == 'long' else 'buy', qty)
                        trade['stage'] = 2
                        trade['sl_price'] = entry + (atr * 2.0) if direction == 'long' else entry - (atr * 2.0)
                        trade['remaining_amount'] -= qty
                        send_telegram(f"📈 50% Book: {symbol} @ {current_price}")
                        logging.info(f"50% Book: {symbol}")
                    except Exception as e:
                        logging.error(f"Book error: {e}")

    def update_trailing_sl(self, symbol, trade, current_price):
        if trade.get('stage', 0) >= 2:
            atr = trade.get('atr', 1)
            if trade['direction'] == 'long':
                new_sl = current_price - (atr * 2.0)
                if new_sl > trade['sl_price']:
                    trade['sl_price'] = new_sl
            else:
                new_sl = current_price + (atr * 2.0)
                if new_sl < trade['sl_price']:
                    trade['sl_price'] = new_sl

    def is_volatile_news(self, symbol):
        if not PANDAS_TA_AVAILABLE:
            return False
        df_1m = self.fetch_indicators(symbol, '1m', limit=20)
        if df_1m is None or len(df_1m) < 10:
            return False
        latest_atr = df_1m['atr'].iloc[-1]
        avg_atr = df_1m['atr'].iloc[-10:-1].mean()
        if avg_atr > 0 and (latest_atr / avg_atr) > 2.0:
            return True
        candle_size = df_1m['high'].iloc[-1] - df_1m['low'].iloc[-1]
        if candle_size > (latest_atr * 1.5):
            return True
        return False

    def emergency_exit(self, symbol):
        if symbol in self.active_trades:
            trade = self.active_trades[symbol]
            try:
                df = self.fetch_indicators(symbol, '1m', limit=1)
                if df is not None and len(df) > 0:
                    current = df['close'].iloc[-1]
                    pnl = (current - trade['entry_price']) * trade['remaining_amount'] if trade['direction'] == 'long' else (trade['entry_price'] - current) * trade['remaining_amount']
                    self.daily_pnl += pnl
                    send_telegram(f"📊 Exit PnL: {pnl:.2f} | Day PnL: {self.daily_pnl:.2f} USD")
                    logging.info(f"Exit PnL: {pnl:.2f}")
                side = 'sell' if trade['direction'] == 'long' else 'buy'
                self.exchange.create_market_order(symbol, side, trade['remaining_amount'])
                send_telegram(f"🛑 Exit: {symbol}")
            except Exception as e:
                logging.error(f"Exit error: {e}")
            del self.active_trades[symbol]
            self.save_trade_state()

    def get_market_regime(self, symbol):
        if not PANDAS_TA_AVAILABLE:
            return self.LEVERAGE
        df = self.fetch_indicators(symbol, '5m', limit=50)
        if df is None or len(df) < 20:
            return self.LEVERAGE
        latest_adx = df['adx'].iloc[-1]
        if latest_adx is None:
            return self.LEVERAGE
        if latest_adx > 25:
            return self.BASE_LEVERAGE
        elif latest_adx < 20:
            return self.MIN_LEVERAGE
        else:
            return self.MID_LEVERAGE

    def check_exit_conditions(self, symbol, trade):
        elapsed = (datetime.now() - trade['entry_time']).total_seconds() / 60
        if elapsed >= 29:
            return 'exit'
        df_1m = self.fetch_indicators(symbol, '1m', limit=10)
        df_5m = self.fetch_indicators(symbol, '5m', limit=5)
        if df_1m is not None and df_5m is not None and len(df_1m) > 0 and len(df_5m) > 0:
            if df_1m['high'].iloc[-1] > df_5m['high'].max() or df_1m['low'].iloc[-1] < df_5m['low'].min():
                return 'emergency'
        if df_1m is not None and len(df_1m) >= 5:
            range_limit = 150 if 'BTC' in symbol else 7
            recent_range = df_1m['high'].iloc[-5:].max() - df_1m['low'].iloc[-5:].min()
            if recent_range <= range_limit:
                if not trade.get('stall_triggered'):
                    trade['stall_triggered'] = True
                    trade['stall_time'] = datetime.now()
                    trade['sl_price'] = trade['entry_price']
                    return 'breakeven'
                elif (datetime.now() - trade['stall_time']).total_seconds() > 120:
                    return 'exit'
        return None

    def run(self):
        while True:
            try:
                if datetime.now().date() != self.today_date:
                    self.daily_pnl = 0
                    self.today_date = datetime.now().date()
                    self.save_trade_state()
                    send_telegram("📅 New Day - PnL Reset")
                    logging.info("📅 New Day - PnL Reset")

                if self.daily_pnl <= self.DAILY_LOSS_LIMIT:
                    if self.LEVERAGE != 5:
                        self.LEVERAGE = 5
                        msg = f"⚠️ Daily Loss Limit Hit! Leverage → 5x (Bot continues)"
                        send_telegram(msg)
                        logging.warning(msg)

                if time.time() - self.last_balance_check > 300:
                    self.cached_balance = self.get_balance()
                    self.last_balance_check = time.time()
                    logging.info(f"💰 Balance: {self.cached_balance:.2f} USD | Lev: {self.LEVERAGE}x | PnL: {self.daily_pnl:.2f}")

                if self.daily_pnl > self.DAILY_LOSS_LIMIT and self.symbols:
                    new_l = self.get_market_regime(self.symbols[0])
                    if self.LEVERAGE != new_l:
                        self.LEVERAGE = new_l
                        msg = f"🧠 Market Regime: {self.LEVERAGE}x"
                        send_telegram(msg)
                        logging.info(msg)

                news_blocked = False
                for symbol in self.symbols:
                    if self.is_volatile_news(symbol):
                        news_blocked = True
                        if symbol in self.active_trades:
                            send_telegram(f"⚡ News Killer: {symbol} flattened")
                            self.emergency_exit(symbol)
                        self.pending_entry[symbol] = None
                if news_blocked:
                    time.sleep(10)
                    continue

                for symbol in self.symbols:
                    df_1m = self.fetch_indicators(symbol, '1m', limit=20)
                    if df_1m is None or len(df_1m) == 0:
                        continue
                    
                    last_ts = str(df_1m.index[-1])
                    if self.last_alert_time.get(symbol) != last_ts:
                        self.last_alert_time[symbol] = last_ts
                        signal = self.check_entry(df_1m)
                        if signal and symbol not in self.active_trades:
                            self.pending_entry[symbol] = {'signal': signal}
                            send_telegram(f"🔔 Alert: {symbol} {signal.upper()}")
                            logging.info(f"Alert: {symbol} {signal.upper()}")

                    if self.pending_entry.get(symbol) and symbol not in self.active_trades:
                        df_5m = self.fetch_indicators(symbol, '5m', limit=50)
                        if df_5m is not None and len(df_5m) > 0:
                            signal_5m = self.check_entry(df_5m)
                            if signal_5m == self.pending_entry[symbol]['signal']:
                                price = df_5m['close'].iloc[-1]
                                atr = df_5m.get('atr', pd.Series([1])).iloc[-1] if 'atr' in df_5m else 1
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
                                        msg = f"🎯 Entry: {symbol} @ {price} (Lev: {self.LEVERAGE}x)"
                                        send_telegram(msg)
                                        logging.info(msg)
                                else:
                                    send_telegram(f"⏳ LOT 0 - Waiting for balance")

                    if symbol in self.active_trades:
                        trade = self.active_trades[symbol]
                        df_price = self.fetch_indicators(symbol, '1m', limit=1)
                        if df_price is None or len(df_price) == 0:
                            continue
                        current = df_price['close'].iloc[-1]

                        self.partial_book(symbol, trade, current)
                        self.update_trailing_sl(symbol, trade, current)

                        exit_signal = self.check_exit_conditions(symbol, trade)
                        if exit_signal in ('emergency', 'exit'):
                            self.emergency_exit(symbol)
                            continue

                        if (trade['direction'] == 'long' and current <= trade['sl_price']) or (trade['direction'] == 'short' and current >= trade['sl_price']):
                            send_telegram(f"🛑 SL Hit: {symbol}")
                            logging.info(f"🛑 SL Hit: {symbol}")
                            self.emergency_exit(symbol)
                            continue

                time.sleep(10)

            except KeyboardInterrupt:
                send_telegram("🛑 Bot stopped manually.")
                logging.info("🛑 Bot stopped manually.")
                for sym in list(self.active_trades.keys()):
                    self.emergency_exit(sym)
                break
            except Exception as e:
                send_telegram(f"💥 Critical error: {e}")
                logging.error(f"Critical Loop Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = PrimeScalpBot()
    bot.run()
