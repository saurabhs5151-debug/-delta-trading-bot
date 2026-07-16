import ccxt, pandas as pd, pandas_ta as ta, time, telebot, os

# कॉन्फ़िगरेशन
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
    # 25x लेवरेज के साथ बैलेंस का उपयोग
    # यह लॉजिक सुनिश्चित करता है कि 100 से 1,00,000 के बीच बोट रुके नहीं
    price = exchange.fetch_ticker(symbol)['last']
    lot = (balance * 25) / price
    return max(1, min(10, round(lot, 2))) # 1 से 10 लॉट की सीमा

while True:
    try:
        balance = exchange.fetch_balance()['USDT']['free']
        for symbol in ['BTC/USDT', 'ETH/USDT']:
            
            # 1. एग्जिट नियम: 29 मिनट (1740 सेकंड)
            if symbol in active_trades:
                if (time.time() - active_trades[symbol]['time']) > 1740:
                    side = 'sell' if active_trades[symbol]['side'] == 'buy' else 'buy'
                    exchange.create_order(symbol, 'market', side, active_trades[symbol]['lot'])
                    del active_trades[symbol]
                    bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"⏱️ 29 मिनट पूर्ण, {symbol} क्लोज किया।")
                continue

            # 2. इंडिकेटर्स एनालिसिस
            df = get_data(symbol)
            last = df.iloc[-1]
            price = last['c']
            
            # लाइव अपडेट
            bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"📈 {symbol} | Price: {price} | Status: Monitoring")

            # 3. एंट्री कंडीशन्स
            is_buy = (last['adx'] > 25) and (last['rsi'] > 50) and (last['cmf'] > 0) and \
                     (last['ema_9'] > last['ema_21']) and (last['c'] > last['supertrend'])
            
            if is_buy and symbol not in active_trades:
                sl = price - (last['atr'] * 2)
                tp = price + (last['atr'] * 3)
                lot = calculate_lot(symbol, balance)
                
                # लिमिट ऑर्डर (Maker)
                exchange.create_order(symbol, 'limit', 'buy', lot, price, {'leverage': 25, 'stopLoss': sl, 'takeProfit': tp})
                active_trades[symbol] = {'time': time.time(), 'side': 'buy', 'lot': lot}
                bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"✅ {symbol} पर लिमिट बाय लगाई। SL: {round(sl,2)}, TP: {round(tp,2)}")

    except Exception as e:
        print(f"System Error: {e}")
    
    time.sleep(60) # 1 मिनट का लूप
