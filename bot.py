import os
import time
import ccxt
import pandas as pd
import pandas_ta as ta
import telebot

# बोट सेटअप
bot = telebot.TeleBot(os.environ.get('TELEGRAM_BOT_TOKEN'))
exchange = ccxt.delta({'apiKey': os.environ.get('API_KEY'), 'secret': os.environ.get('API_SECRET')})
active_trades = {}

def get_data(symbol):
    bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
    df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
    df['ema_9'] = ta.ema(df['c'], length=9)
    df['ema_21'] = ta.ema(df['c'], length=21)
    st = ta.supertrend(df['h'], df['l'], df['c'], length=10, multiplier=3)
    df['supertrend'] = st['SUPERT_10_3.0']
    df['adx'] = ta.adx(df['h'], df['l'], df['c'], length=14)['ADX_14']
    df['rsi'] = ta.rsi(df['c'], length=14)
    df['cmf'] = ta.cmf(df['h'], df['l'], df['c'], df['v'], length=20)
    df['atr'] = ta.atr(df['h'], df['l'], df['c'], length=14)
    return df

def calculate_lot(symbol, balance):
    price = exchange.fetch_ticker(symbol)['last']
    lot = (balance * 25) / price
    return max(1, min(10, round(lot, 2)))

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            # एग्जिट लॉजिक (29 मिनट बाद मार्केट ऑर्डर - टेकर)
            if symbol in active_trades:
                if (time.time() - active_trades[symbol]['time']) > 1740:
                    side = 'sell' if active_trades[symbol]['side'] == 'buy' else 'buy'
                    exchange.create_order(symbol, 'market', side, active_trades[symbol]['lot'])
                    del active_trades[symbol]
                    bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"⏱️ 29 मिनट पूरे, {symbol} मार्केट ऑर्डर से क्लोज किया।")
                continue

            # एंट्री लॉजिक (लिमिट ऑर्डर - मेकर)
            df = get_data(symbol)
            last = df.iloc[-1]
            price = last['c']
            
            is_buy = (last['adx'] > 25) and (last['rsi'] > 50) and (last['cmf'] > 0) and \
                     (last['ema_9'] > last['ema_21']) and (last['c'] > last['supertrend'])
            
            if is_buy and symbol not in active_trades:
                sl = price - (last['atr'] * 2)
                tp = price + (last['atr'] * 3)
                lot = calculate_lot(symbol, balance)
                
                # लिमिट ऑर्डर (मेकर ऑर्डर)
                exchange.create_order(symbol, 'limit', 'buy', lot, price, {'leverage': 25, 'stopLoss': sl, 'takeProfit': tp})
                active_trades[symbol] = {'time': time.time(), 'side': 'buy', 'lot': lot}
                bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"✅ {symbol} पर लिमिट ऑर्डर लगाया। SL: {round(sl,2)}, TP: {round(tp,2)}")
    except Exception as e:
        print(f"System Error: {e}")
    time.sleep(60)
