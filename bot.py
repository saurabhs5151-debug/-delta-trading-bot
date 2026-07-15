import os
import telebot

# Railway के Variables से टोकन और चैट आईडी ले रहे हैं
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)

# यह फंक्शन बोट को चालू करने के लिए जरूरी है
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "बोट चालू है और काम कर रहा है!")

# यह लूप बोट को लगातार चालू रखता है
if __name__ == "__main__":
    print("बोट शुरू हो रहा है...")
    bot.infinity_polling()
