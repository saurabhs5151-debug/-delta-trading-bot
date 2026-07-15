import requests
import time
TOKEN = '8949470406:AAEGb6jPewHnGN1zB6B8xiTn5tcrnHLJuqs'
CHAT_ID = '8212188759'
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
  
