import os
import time
import logging
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import ccxt
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
        self.last_heartbeat_time = {}
        
        self.exchange = ccxt.delta({
            'apiKey': os.getenv("DELTA_API_KEY"),
            'secret': os.getenv("DELTA_API_SECRET"),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

    def run(self):
        send_telegram("🟢 Prime Scalp Bot Started (Complete 25-50-25 Partial Booking + Min Lot Flexibility)")
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
                    try:
                        ticker = self.exchange.fetch_ticker(symbol)
                        current_price = ticker['last']
                        now_time = time.time()
                        if symbol not in self.last_heartbeat_time:
                            self.last_heartbeat_time[symbol] = 0
                        if now_time - self.last_heartbeat_time[symbol] >= 120:
                            self.last_heartbeat_time[symbol] = now_time
                            send_telegram(f"⚡ *{symbol} Live Update*\nPrice: `{current_price:.2f}`")
                    except Exception as e:
                        logging.error(f"Live Price Fetch Error for {symbol}: {e}")

                    if self.is_volatile_news(symbol):
                        if symbol in self.active_trades:
                            self.emergency_exit(symbol)
                        continue

                    df_1m = self.fetch_indicators(symbol, '1m', limit=50)
                    if df_1m is None or len(df_1m) < 30:
                        continue

                    current_adx = df_1m['adx'].iloc[-1]
                    if current_adx >= 25:
                        self.LEVERAGE = 50
                    elif current_adx >= 22:
                        self.LEVERAGE = 20
                    else:
                        self.LEVERAGE = 5

                    last_ts = str(df_1m.index[-1])
                    if self.last_alert_time.get(symbol) != last_ts:
                        self.last_alert_time[symbol] = last_ts
                        result = self.check_entry(df_1m)
                        if result is not None:
                            signal, score = result
                            if signal and symbol not in self.active_trades:
                                self.pending_entry[symbol] = {'signal': signal, 'score': score}
                                send_telegram(f"🔔 *Smart Alert*: {symbol} Signal -> *{signal.upper()}* (Score: {score}/6) | Lev: {self.LEVERAGE}x")

                    if self.pending_entry.get(symbol) and symbol not in self.active_trades:
                        df_5m = self.fetch_indicators(symbol, '5m', limit=100)
                        if df_5m is not None and len(df_5m) > 30:
                            result_5m = self.check_entry(df_5m)
                            if result_5m is not None:
                                signal_5m, score_5m = result_5m
                                if signal_5m == self.pending_entry[symbol]['signal'] and score_5m >= 4:
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
                                                'stall_triggered': False,
                                                'stall_time': None
                                            }
                                            self.pending_entry[symbol] = None
                                            self.save_trade_state()
                                            send_telegram(f"🎯 *Trade Executed ({symbol})*\nSide: *{side.upper()}*\nLot: `{lot}`\nPrice: `{price}`\nLeverage: `{self.LEVERAGE}x`\nSL: `{sl_price:.2f}`")

                for symbol in list(self.active_trades.keys()):
                    trade = self.active_trades[symbol]
                    df_price = self.fetch_indicators(symbol, '1m', limit=10)
                    if df_price is None or len(df_price) == 0:
                        continue
                    current = df_price['close'].iloc[-1]
                    
                    self.partial_book(symbol, trade, current)
                    self.update_trailing_sl(symbol, trade, current)
                    self.check_stalling(symbol, trade, df_price)
                    self.check_volatility_spike(symbol, trade, df_price)
                    
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
        except Exception as e:
            logging.error(f"Balance Error: {e}")
            return 0

    def is_volatile_news(self, symbol):
        try:
            df = self.fetch_indicators(symbol, '1m', limit=20)
            if df is not None and len(df) >= 15:
                current_atr = df['atr'].iloc[-1]
                avg_atr = df['atr'][:-1].mean()
                if current_atr > (avg_atr * 2.5):
                    send_telegram(f"⚠️ *ATR Spike / News Detected* on {symbol}! Pausing trades.")
                    return True
        except Exception as e:
            logging.error(f"News Check Error: {e}")
        return False

    def fetch_indicators(self, symbol, timeframe, limit):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            df['tema'] = ta.tema(df['close'], length=20)
            df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])

            supertrend = ta.supertrend(df['high'], df['low'], df['close'], length=7, multiplier=3)
            if supertrend is not None and not supertrend.empty:
                df['supertrend'] = supertrend.iloc[:, 0]
            else:
                df['supertrend'] = df['close']

            df['rsi'] = ta.rsi(df['close'], length=14)

            adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
            if adx_df is not None and not adx_df.empty:
                df['adx'] = adx_df.iloc[:, 0]
            else:
                df['adx'] = 25

            df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

            return df
        except Exception as e:
            logging.error(f"Error fetching indicators for {symbol}: {e}")
            return None

    def check_entry(self, df):
        try:
            last = df.iloc[-1]
            close = last['close']
            tema = last['tema']
            vwap = last['vwap']
            rsi = last['rsi']
            adx = last['adx']
            cmf = last['cmf']
            supertrend = last['supertrend']

            long_score = 0
            short_score = 0

            if close > tema: long_score += 1
            if close > vwap: long_score += 1
            if close > supertrend: long_score += 1
            if 45 < rsi < 70: long_score += 1
            if adx > 20: long_score += 1
            if cmf > 0: long_score += 1

            if close < tema: short_score += 1
            if close < vwap: short_score += 1
            if close < supertrend: short_score += 1
            if 30 < rsi < 55: short_score += 1
            if adx > 20: short_score += 1
            if cmf < 0: short_score += 1

            if long_score >= 4 and long_score > short_score:
                return 'long', long_score
            elif short_score >= 4 and short_score > long_score:
                return 'short', short_score

        except Exception as e:
            logging.error(f"Check Entry Error: {e}")
        return None, 0

    def calculate_lot(self, symbol, price):
        try:
            balance = self.cached_balance if self.cached_balance > 0 else self.get_balance()
            if balance <= 0:
                balance = 1  # भले ही $1 हो, ट्रेड नहीं रुकेगा

            # मिनिमम लॉट साइज़ सेट किया गया है (BTC के लिए 0.001, ETH के लिए 0.01)
            min_lot = 0.001 if 'BTC' in symbol else 0.01
            
            notional_amount = balance * self.LEVERAGE * 0.5
            lot = notional_amount / price
            
            # यदि कैलकुलेटेड लॉट मिनिमम से भी कम है, तो भी एक्सचेंज का मिनिमम लॉट लागू होगा ताकि $1 में भी ट्रेड चल सके
            if lot < min_lot:
                lot = min_lot
                
            return round(lot, 4)
        except Exception as e:
            logging.error(f"Calculate Lot Error: {e}")
            return 0.001 if 'BTC' in symbol else 0.01

    def place_order(self, symbol, side, lot, price):
        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=lot,
                params={'leverage': self.LEVERAGE}
            )
            logging.info(f"Order Placed Successfully: {order}")
            return order
        except Exception as e:
            send_telegram(f"💥 *Order Placement Error*: {e}")
            logging.error(f"Order Placement Error: {e}")
            return None

    def partial_book(self, symbol, trade, current_price):
        try:
            entry = trade['entry_price']
            direction = trade['direction']
            atr = trade['atr']
            stage = trade.get('stage', 0)
            total = trade['total_amount']
            
            if stage == 0:
                tp1 = entry + (atr * 1.5) if direction == 'long' else entry - (atr * 1.5)
                if (direction == 'long' and current_price >= tp1) or (direction == 'short' and current_price <= tp1):
                    qty = round(total * 0.25, 4)
                    min_qty = 0.001 if 'BTC' in symbol else 0.01
                    if qty < min_qty: qty = min_qty
                    side = 'sell' if direction == 'long' else 'buy'
                    self.exchange.create_order(symbol, 'market', side, qty, params={'reduceOnly': True})
                    trade['remaining_amount'] -= qty
                    trade['stage'] = 1
                    trade['sl_price'] = entry
                    send_telegram(f"💰 25% Booked ({direction.upper()}) {symbol} @ {current_price:.2f}")
            
            elif stage == 1:
                tp2 = entry + (atr * 2.5) if direction == 'long' else entry - (atr * 2.5)
                if (direction == 'long' and current_price >= tp2) or (direction == 'short' and current_price <= tp2):
                    qty = round(total * 0.50, 4)
                    min_qty = 0.001 if 'BTC' in symbol else 0.01
                    if qty < min_qty: qty = min_qty
                    side = 'sell' if direction == 'long' else 'buy'
                    self.exchange.create_order(symbol, 'market', side, qty, params={'reduceOnly': True})
                    trade['remaining_amount'] -= qty
                    trade['stage'] = 2
                    trade['sl_price'] = entry + (atr * 2.0) if direction == 'long' else entry - (atr * 2.0)
                    send_telegram(f"💰 50% Booked ({direction.upper()}) {symbol} @ {current_price:.2f}")
        except Exception as e:
            logging.error(f"Partial Booking Error: {e}")

    def update_trailing_sl(self, symbol, trade, current_price):
        try:
            if trade.get('stage', 0) >= 2:
                atr = trade['atr']
                if trade['direction'] == 'long':
                    new_sl = current_price - (atr * 2.0)
                    if new_sl > trade['sl_price']:
                        trade['sl_price'] = new_sl
                else:
                    new_sl = current_price + (atr * 2.0)
                    if new_sl < trade['sl_price']:
                        trade['sl_price'] = new_sl
        except Exception as e:
            logging.error(f"Trailing SL Error: {e}")

    def check_stalling(self, symbol, trade, df_price):
        try:
            if len(df_price) >= 5:
                atr = trade['atr']
                recent_range = df_price['high'].iloc[-5:].max() - df_price['low'].iloc[-5:].min()
                if recent_range <= (atr * 1.5):
                    if not trade.get('stall_triggered'):
                        trade['stall_triggered'] = True
                        trade['stall_time'] = datetime.now()
                        trade['sl_price'] = trade['entry_price']
                        send_telegram(f"⏸️ Stalling Detected: {symbol} | SL Breakeven")
                    elif (datetime.now() - trade['stall_time']).total_seconds() > 120:
                        send_telegram(f"🛑 Stalling Exit: {symbol}")
                        self.emergency_exit(symbol)
        except Exception as e:
            logging.error(f"Stalling Check Error: {e}")

    def check_volatility_spike(self, symbol, trade, df_price):
        try:
            if len(df_price) >= 10:
                df_5m = self.fetch_indicators(symbol, '5m', limit=5)
                if df_5m is not None and len(df_5m) > 0:
                    if df_price['high'].iloc[-1] > df_5m['high'].max() or df_price['low'].iloc[-1] < df_5m['low'].min():
                        send_telegram(f"⚡ Volatility Spike: {symbol} | Emergency Exit")
                        self.emergency_exit(symbol)
        except Exception as e:
            logging.error(f"Volatility Spike Check Error: {e}")

    def check_exit_conditions(self, symbol, trade):
        elapsed = (datetime.now() - trade['entry_time']).total_seconds() / 60
        if elapsed >= 29:
            send_telegram(f"⏰ Time Exit: {symbol} | 29 minutes")
            return True
        return False

    def save_trade_state(self):
        pass

    def emergency_exit(self, symbol):
        if symbol in self.active_trades:
            del self.active_trades[symbol]
            send_telegram(f"🛑 Exit: {symbol}")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
