
import os
import requests
import time
import telebot
import threading

# Railway के Variables से टोकन और चैट आईडी ले रहे हैं
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "बोट चालू है और काम कर रहा है!")

# यह फंक्शन प्राइस चेक करता है और मैसेज भेजता है
def price_loop():
    while True:
        try:
            res = requests.get('https://api.delta.exchange/v2/tickers')
            if res.status_code == 200:
                data = res.json().get('result', [])
                btc = next((i for i in data if i.get('symbol') == 'BTCUSDT'), None)
                eth = next((i for i in data if i.get('symbol') == 'ETHUSDT'), None)
                if btc and eth:
                    msg = f'BTC: ${btc.get("close")} | ETH: ${eth.get("close")}'
                    bot.send_message(CHAT_ID, msg)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(60) # हर 60 सेकंड में अपडेट

if __name__ == "__main__":
    print("बोट शुरू हो रहा है...")
    # प्राइस लूप को बैकग्राउंड में शुरू करें
    threading.Thread(target=price_loop, daemon=True).start()
    # बोट को पोलिंग के लिए चालू रखें
    bot.infinity_polling()
