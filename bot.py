import ccxt, pandas as pd, pandas_ta as ta, os, json, logging, telebot, time
from datetime import datetime
from dotenv import load_dotenv

# सेटअप
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
load_dotenv()
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class PrimeScalpBot:
    def __init__(self):
        self.exchange = ccxt.delta({'apiKey': os.getenv('API_KEY'), 'secret': os.getenv('API_SECRET'), 'enableRateLimit': True, 'options': {'defaultType': 'future'}})
        self.symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']
        self.state = {'trades': {}}
        self.load_state()

    def send_telegram(self, msg):
        try: bot.send_message(CHAT_ID, msg)
        except: pass

    def load_state(self):
        if os.path.exists('trade_state.json'):
            with open('trade_state.json', 'r') as f: self.state = json.load(f)

    def save_state(self):
        with open('trade_state.json', 'w') as f: json.dump(self.state, f, indent=4)

    def fetch_indicators(self, symbol):
        bars = self.exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df['tema'] = ta.tema(df['close'], length=9)
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['vol'])
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        df['st'] = st['SUPERT_10_3.0']
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['vol'], length=20)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        return df

    def is_news_spike(self, symbol):
        df = self.fetch_indicators(symbol)
        return df['atr'].iloc[-1] > (df['atr'].iloc[-10:-1].mean() * 2.0)

    def check_filters(self, df):
        last = df.iloc[-1]
        long = (last['close'] > last['tema']) and (last['close'] > last['vwap']) and (last['st'] < last['close']) and (last['rsi'] > 50) and (last['adx'] > 20) and (last['cmf'] > 0.05)
        short = (last['close'] < last['tema']) and (last['close'] < last['vwap']) and (last['st'] > last['close']) and (last['rsi'] < 50) and (last['adx'] > 20) and (last['cmf'] < -0.05)
        return 'long' if long else 'short' if short else None

    def manage_trade(self, symbol, trade, df):
        curr = df['close'].iloc[-1]
        atr = df['atr'].iloc[-1]
        entry = trade['entry_price']
        
        # 1. टाइम एग्जिट (29 मिनट)
        if (datetime.now() - datetime.fromisoformat(trade['entry_time'])).total_seconds() > 1740:
            self.send_telegram(f"⏳ {symbol} Time Exit Reached! Closing final 25% at {curr}.")
            self.execute_exit(symbol, "Time Exit (29m - Final 25%)")
            return

        # 2. पहली 25% बुकिंग (ATR * 1.5)
        if trade['stage'] == 0:
            tp1 = (entry + (atr * 1.5)) if trade['side'] == 'long' else (entry - (atr * 1.5))
            if (trade['side'] == 'long' and curr >= tp1) or (trade['side'] == 'short' and curr <= tp1):
                self.partial_order(symbol, 0.25)
                trade['stage'] = 1
                trade['sl_price'] = entry
                self.send_telegram(f"✅ {symbol} 25% Booked. SL Breakeven set at {entry}")
                self.save_state()

        # 3. दूसरी 50% बुकिंग (ATR * 2.5)
        elif trade['stage'] == 1:
            tp2 = (entry + (atr * 2.5)) if trade['side'] == 'long' else (entry - (atr * 2.5))
            if (trade['side'] == 'long' and curr >= tp2) or (trade['side'] == 'short' and curr <= tp2):
                self.partial_order(symbol, 0.50)
                trade['stage'] = 2
                trade['sl_price'] = (entry + (atr * 2.0)) if trade['side'] == 'long' else (entry - (atr * 2.0))
                self.send_telegram(f"🚀 {symbol} 50% Booked. SL Trailing at {trade['sl_price']}")
                self.save_state()

    def partial_order(self, symbol, pct):
        trade = self.state['trades'][symbol]
        qty = round(trade['total_amount'] * pct, 4)
        side = 'sell' if trade['side'] == 'long' else 'buy'
        self.exchange.create_market_order(symbol, side, qty)
        trade['remaining_amount'] -= qty

    def execute_exit(self, symbol, reason):
        trade = self.state['trades'][symbol]
        side = 'sell' if trade['side'] == 'long' else 'buy'
        self.exchange.create_market_order(symbol, side, trade['remaining_amount'])
        del self.state['trades'][symbol]
        self.save_state()

    def run(self):
        last_heartbeat = 0
        while True:
            # 2 मिनट का हार्टबीट अलर्ट
            if time.time() - last_heartbeat >= 120:
                try:
                    ticker = self.exchange.fetch_ticker(self.symbols[0])
                    self.send_telegram(f"🕒 Bot Heartbeat | {self.symbols[0]}: {ticker['last']}")
                    last_heartbeat = time.time()
                except: pass

            for symbol in self.symbols:
                if self.is_news_spike(symbol): continue
                df = self.fetch_indicators(symbol)
                
                if symbol not in self.state['trades']:
                    signal = self.check_filters(df)
                    if signal:
                        price = df['close'].iloc[-1]
                        lot = 0.01 
                        self.exchange.create_order(symbol, 'limit', 'buy' if signal == 'long' else 'sell', lot, price, {'postOnly': True})
                        self.state['trades'][symbol] = {'side': signal, 'entry_price': price, 'total_amount': lot, 'remaining_amount': lot, 'stage': 0, 'entry_time': datetime.now().isoformat()}
                        self.send_telegram(f"⚡ {signal.upper()} Entry {symbol} @ {price}")
                else:
                    self.manage_trade(symbol, self.state['trades'][symbol], df)
            time.sleep(10)

if __name__ == "__main__":
    PrimeScalpBot().run()
