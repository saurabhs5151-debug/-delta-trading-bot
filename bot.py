
import os
import requests
import time
import telebot
import threading
from datetime import datetime

# ========== Railway Variables ==========
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

# ========== Start Command ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🚀 *Prime Scalp Bot Active!*\n\n✅ TEMA + VWAP + RSI + ADX + CMF + SuperTrend – सबके Signals आएंगे।")

# ========== OHLCV Data ==========
def get_ohlcv(symbol):
    try:
        url = f"https://api.delta.exchange/v2/ohlcv?symbol={symbol}&resolution=5m&limit=100"
        res = requests.get(url)
        if res.status_code == 200:
            return res.json().get('result', [])
    except Exception as e:
        print(f"OHLCV Error: {e}")
    return []

# ========== Indicators ==========
def calculate_tema(data, length=9):
    closes = [c[4] for c in data]
    if len(closes) < length * 3:
        return closes[-1]
    
    # EMA1
    ema1 = []
    alpha = 2 / (length + 1)
    ema1.append(closes[0])
    for price in closes[1:]:
        ema1.append(price * alpha + ema1[-1] * (1 - alpha))
    
    # EMA2
    ema2 = []
    ema2.append(ema1[0])
    for val in ema1[1:]:
        ema2.append(val * alpha + ema2[-1] * (1 - alpha))
    
    # EMA3
    ema3 = []
    ema3.append(ema2[0])
    for val in ema2[1:]:
        ema3.append(val * alpha + ema3[-1] * (1 - alpha))
    
    # TEMA = 3*EMA1 - 3*EMA2 + EMA3
    if len(closes) >= length * 3:
        return 3 * ema1[-1] - 3 * ema2[-1] + ema3[-1]
    return closes[-1]

def calculate_vwap(data):
    if not data:
        return 0
    total_price_volume = 0
    total_volume = 0
    for c in data:
        high, low, close, volume = c[2], c[3], c[4], c[5]
        typical = (high + low + close) / 3
        total_price_volume += typical * volume
        total_volume += volume
    return total_price_volume / total_volume if total_volume != 0 else 0

def calculate_rsi(prices, length=14):
    if len(prices) < length + 1:
        return 50
    gains, losses = 0, 0
    for i in range(1, length + 1):
        diff = prices[-i] - prices[-i-1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain, avg_loss = gains / length, losses / length
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_adx(data, length=14):
    if len(data) < length + 1:
        return 0
    tr_list, dm_plus, dm_minus = [], [], []
    for i in range(1, len(data)):
        high, low, prev_high, prev_low = data[i][2], data[i][3], data[i-1][2], data[i-1][3]
        tr = max(high - low, abs(high - prev_high), abs(low - prev_low))
        tr_list.append(tr)
        dm_plus.append(max(0, (high - prev_high) - (prev_low - low)))
        dm_minus.append(max(0, (prev_low - low) - (high - prev_high)))
    atr = sum(tr_list[-length:]) / length
    if atr == 0:
        return 0
    di_plus = (sum(dm_plus[-length:]) / length) / atr * 100
    di_minus = (sum(dm_minus[-length:]) / length) / atr * 100
    dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) != 0 else 0
    return dx

def calculate_cmf(data, length=20):
    cmf_sum, volume_sum = 0, 0
    for c in data[-length:]:
        high, low, close, volume = c[2], c[3], c[4], c[5]
        if high - low == 0:
            continue
        mfm = ((close - low) - (high - close)) / (high - low)
        cmf_sum += mfm * volume
        volume_sum += volume
    return cmf_sum / volume_sum if volume_sum != 0 else 0

# ========== Prime Scalp Signal ==========
def get_signal(symbol):
    data = get_ohlcv(symbol)
    if not data or len(data) < 30:
        return None

    closes = [c[4] for c in data]
    current_price = closes[-1]

    # सभी Indicators
    vwap = calculate_vwap(data)
    rsi = calculate_rsi(closes)
    adx = calculate_adx(data)
    cmf = calculate_cmf(data)
    tema = calculate_tema(data)

    # SuperTrend (Simplified)
    atr = 0
    for i in range(1, min(15, len(data))):
        high, low = data[i][2], data[i][3]
        prev_high, prev_low = data[i-1][2], data[i-1][3]
        prev_close = data[i-1][4]
        atr += max(high - low, abs(high - prev_high), abs(low - prev_low))
    atr = atr / min(15, len(data))
    supertrend = "GREEN" if current_price > (vwap + atr * 0.5) else "RED"

    # Prime Scalp - 6 Conditions
    if current_price > vwap and rsi > 50 and adx > 25 and cmf > 0 and supertrend == "GREEN" and current_price > tema:
        return "BUY", current_price, vwap, tema, rsi, adx, cmf, supertrend
    elif current_price < vwap and rsi < 50 and adx > 25 and cmf < 0 and supertrend == "RED" and current_price < tema:
        return "SELL", current_price, vwap, tema, rsi, adx, cmf, supertrend
    return None

# ========== Loop ==========
def signal_loop():
    while True:
        try:
            btc = get_signal("BTCUSDT")
            eth = get_signal("ETHUSDT")
            msg = f"📊 *Prime Scalp Signals*\n🕒 {datetime.now().strftime('%H:%M')}\n"
            if btc:
                msg += f"\n🟢 *BTC*: ${btc[1]:.2f} | {btc[0]}\nVWAP: ${btc[2]:.2f} | TEMA: ${btc[3]:.2f}\nRSI: {btc[4]:.1f} | ADX: {btc[5]:.1f} | CMF: {btc[6]:.2f}\nSuperTrend: {btc[7]}"
            if eth:
                msg += f"\n\n🟢 *ETH*: ${eth[1]:.2f} | {eth[0]}\nVWAP: ${eth[2]:.2f} | TEMA: ${eth[3]:.2f}\nRSI: {eth[4]:.1f} | ADX: {eth[5]:.1f} | CMF: {eth[6]:.2f}\nSuperTrend: {eth[7]}"
            if btc or eth:
                bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        except Exception as e:
            print(f"Signal Error: {e}")
        time.sleep(60)

# ========== Run ==========
if __name__ == "__main__":
    print("🚀 Prime Scalp Bot is Running...")
    threading.Thread(target=signal_loop, daemon=True).start()
    bot.infinity_polling()