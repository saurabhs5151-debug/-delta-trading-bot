import requests
import time
import os  # os को इम्पोर्ट करना जरूरी है ताकि Railway के variables पढ़ सकें

# यहाँ हम कोड को बता रहे हैं कि डेटा Railway के Variables से लेना है
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

URL = f'https://api.telegram.org/bot{TOKEN}/'

while True:
    try:
        res = requests.get('https://api.delta.exchange/v2/tickers')
        if res.status_code == 200:
            data = res.json().get('result', [])
            
            btc = next((i for i in data if i.get('symbol') == 'BTCUSDT'), None)
            eth = next((i for i in data if i.get('symbol') == 'ETHUSDT'), None)
            
            if btc and eth:
                msg = f'BTC: ${btc.get("close")} | ETH: ${eth.get("close")}'
                requests.post(URL + 'sendMessage', json={'chat_id': CHAT_ID, 'text': msg})
    except:
        pass
    
    time.sleep(15)
