import ccxt, pandas as pd, pandas_ta as ta, time, telebot, os

# Telegram और Exchange Setup
bot = telebot.TeleBot(os.environ.get('TELEGRAM_BOT_TOKEN'))
exchange = ccxt.delta({'apiKey': os.environ.get('API_KEY'), 'secret': os.environ.get('API_SECRET')})

def get_data(symbol):
    bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
    df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
    
    # 1. इंडिकेटर कैलकुलेशन
    df['ema_9'] = ta.ema(df['c'], length=9)
    df['ema_21'] = ta.ema(df['c'], length=21)
    st = ta.supertrend(df['h'], df['l'], df['c'], length=10, multiplier=3)
    df['supertrend'] = st['SUPERT_10_3.0']
    df['adx'] = ta.adx(df['h'], df['l'], df['c'], length=14)['ADX_14']
    df['rsi'] = ta.rsi(df['c'], length=14)
    df['cmf'] = ta.cmf(df['h'], df['l'], df['c'], df['v'], length=20)
    df['atr'] = ta.atr(df['h'], df['l'], df['c'], length=14)
    return df

def trade_logic():
    for symbol in ['BTC/USDT', 'ETH/USDT']:
        try:
            df = get_data(symbol)
            last = df.iloc[-1]
            price = last['c']
            
            # 2. नियम लागू करना
            is_buy = (last['adx'] > 25) and (last['rsi'] > 50) and (last['cmf'] > 0) and \
                     (last['ema_9'] > last['ema_21']) and (last['c'] > last['supertrend'])
                     
            is_sell = (last['adx'] > 25) and (last['rsi'] < 50) and (last['cmf'] < 0) and \
                      (last['ema_9'] < last['ema_21']) and (last['c'] < last['supertrend'])

            # 3. लॉट साइज और लेवरेज (1-10 लॉट, 25x)
            balance = exchange.fetch_balance()['USDT']['free']
            lot_size = min(10, max(1, int((balance * 25) / price)))
            
            if is_buy or is_sell:
                side = 'buy' if is_buy else 'sell'
                sl = price - (last['atr'] * 2) if is_buy else price + (last['atr'] * 2)
                tp = price + (last['atr'] * 4) if is_buy else price - (last['atr'] * 4)
                
                params = {'leverage': 25, 'stopLoss': sl, 'takeProfit': tp}
                exchange.create_order(symbol, 'market', side, lot_size, params=params)
                bot.send_message(os.environ.get('TELEGRAM_CHAT_ID'), f"✅ ट्रेड लिया गया: {side.upper()} {symbol}\nलॉट: {lot_size}\nSL: {sl:.2f}\nTP: {tp:.2f}")

        except Exception as e:
            print(f"Error in {symbol}: {e}")

# 4. क्रैश-प्रूफ वॉचडॉग लूप
while True:
    try:
        trade_logic()
    except Exception as e:
        print(f"Watchdog Alert: {e}")
    time.sleep(60) # 1 मिनट का अंतराल
