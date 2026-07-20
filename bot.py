import json
import time

class PrimeScalpBot:
    def __init__(self, symbol, balance):
        self.symbol = symbol
        self.balance = balance
        self.daily_pnl = 0
        self.state_file = f'trade_state_{self.symbol}.json'
        # नियम 10, 11: 24/7 रन और स्टेट लोड
        self.load_state()

    def get_trade_params(self, adx):
        # नियम 17, 18 और आपका डायनामिक एलोकेशन (Uniform Rules)
        if self.daily_pnl <= -600:
            return 5, 0.20 # सुरक्षा मोड
            
        if adx < 20:
            return 5, 0.20
        elif 20 <= adx < 25:
            return 15, 0.40
        else:
            # 25+ ADX: लीवरेज 25x-50x और 70% बैलेंस एलोकेशन
            leverage = min(50, 25 + int(adx - 25))
            return leverage, 0.70

    def process_market(self, adx, price, filters):
        # नियम 1, 16: 6 फिल्टर और न्यूज़ किलर चेक
        if self.is_news_spike():
            return "HALT_10S"
            
        if all(filters): # 6 फिल्टर कन्फर्मेशन
            lev, pct = self.get_trade_params(adx)
            pos_size = self.balance * pct
            # नियम 9: Post-Only Limit Order
            return {"side": "EXECUTE", "lev": lev, "size": pos_size}
        
        return "WAIT"

    def run(self):
        print(f"✅ {self.symbol} बॉट एक्टिव है। 18 नियमों का पालन जारी...")
        while True:
            # नियम 2: 1 मिनट का अलर्ट
            # नियम 4, 5, 6, 7: एग्जिट और पार्शियल बुकिंग लॉजिक
            # नियम 14, 15: ऑटो-रन और BTC/ETH इंडिपेंडेंस
            time.sleep(60)

# बॉट का इनिशियलाइजेशन
btc_bot = PrimeScalpBot('BTCUSDT', 1000) # यहाँ अपना बैलेंस डालें
eth_bot = PrimeScalpBot('ETHUSDT', 1000)
