
 # ========== Updated Loop (Price + Signal) ==========
def signal_loop():
    while True:
        try:
            # हम सीधे प्राइस पाने के लिए एक छोटा फंक्शन कॉल कर रहे हैं या get_signal का उपयोग कर रहे हैं
            btc_data = get_signal("BTCUSDT")
            eth_data = get_signal("ETHUSDT")
            
            # सिर्फ लाइव प्राइस के लिए एक अलग API कॉल (ताकि सिग्नल न होने पर भी प्राइस मिले)
            res = requests.get('https://api.delta.exchange/v2/tickers')
            ticker_data = res.json().get('result', [])
            btc_price = next((i['close'] for i in ticker_data if i['symbol'] == 'BTCUSDT'), "N/A")
            eth_price = next((i['close'] for i in ticker_data if i['symbol'] == 'ETHUSDT'), "N/A")

            msg = f"🕒 {datetime.now().strftime('%H:%M')} | Live Price\n"
            msg += f"BTC: ${btc_price} | ETH: ${eth_price}\n"

            # अगर सिग्नल मिलता है, तो उसे जोड़ें
            if btc_data:
                msg += f"\n🟢 *BTC Signal: {btc_data[0]}*\nVWAP: ${btc_data[2]:.2f} | TEMA: ${btc_data[3]:.2f}\nRSI: {btc_data[4]:.1f} | ADX: {btc_data[5]:.1f} | CMF: {btc_data[6]:.2f}\nSuperTrend: {btc_data[7]}"
            
            if eth_data:
                msg += f"\n\n🟢 *ETH Signal: {eth_data[0]}*\nVWAP: ${eth_data[2]:.2f} | TEMA: ${eth_data[3]:.2f}\nRSI: {eth_data[4]:.1f} | ADX: {eth_data[5]:.1f} | CMF: {eth_data[6]:.2f}\nSuperTrend: {eth_data[7]}"
            
            bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
            
        except Exception as e:
            print(f"Signal Error: {e}")
        time.sleep(60)
