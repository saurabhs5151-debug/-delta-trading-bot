def run(self):
    last_alert_seconds = 0
    send_telegram("🟢 Bot Loop Started Successfully.")
    while True:
        try:
            if datetime.now().date() != self.today_date:
                self.daily_pnl = 0
                self.today_date = datetime.now().date()
                self.save_trade_state()
                send_telegram("📅 New Day - PnL Reset")
            if self.daily_pnl <= self.DAILY_LOSS_LIMIT:
                if self.LEVERAGE != 5:
                    self.LEVERAGE = 5
                    send_telegram("⚠️ Daily Loss Limit Hit! Leverage → 5x")
            if time.time() - self.last_balance_check > 300:
                self.cached_balance = self.get_balance()
                self.last_balance_check = time.time()
            for symbol in self.symbols:
                if self.is_volatile_news(symbol):
                    if symbol in self.active_trades:
                        self.emergency_exit(symbol)
                    continue
                df_1m = self.fetch_indicators(symbol, '1m', limit=20)
                if df_1m is None or len(df_1m) == 0:
                    continue
                current_price = df_1m['close'].iloc[-1]
                if time.time() - last_alert_seconds >= 60:
                    last_alert_seconds = time.time()
                    send_telegram(f"📊 {symbol} Price: {current_price:.2f}")
                last_ts = str(df_1m.index[-1])
                if self.last_alert_time.get(symbol) != last_ts:
                    self.last_alert_time[symbol] = last_ts
                    signal = self.check_entry(df_1m)
                    if signal and symbol not in self.active_trades:
                        self.pending_entry[symbol] = {'signal': signal}
                        send_telegram(f"🔔 Alert: {symbol} {signal.upper()}")
                if self.pending_entry.get(symbol) and symbol not in self.active_trades:
                    df_5m = self.fetch_indicators(symbol, '5m', limit=50)
                    if df_5m is not None and len(df_5m) > 0:
                        signal_5m = self.check_entry(df_5m)
                        if signal_5m == self.pending_entry[symbol]['signal']:
                            price = df_5m['close'].iloc[-1]
                            atr = df_5m['atr'].iloc[-1]
                            lot = self.calculate_lot(symbol, price)
                            if lot > 0:
                                side = 'buy' if signal_5m == 'long' else 'sell'
                                order = self.place_order(symbol, side, lot, price)
                                if order:
                                    sl_price = price - (atr * 1.0) if signal_5m == 'long' else price + (atr * 1.0)
                                    self.active_trades[symbol] = {
                                        'entry_price': price,
                                        'direction': signal_5m,
                                        'total_amount': lot,
                                        'remaining_amount': lot,
                                        'sl_price': sl_price,
                                        'atr': atr,
                                        'entry_time': datetime.now(),
                                        'stage': 0,
                                        'stall_triggered': False
                                    }
                                    self.pending_entry[symbol] = None
                                    self.save_trade_state()
                                    send_telegram(f"🎯 Entry: {symbol} @ {price}")
            for symbol in self.symbols:
                if symbol in self.active_trades:
                    trade = self.active_trades[symbol]
                    df_price = self.fetch_indicators(symbol, '1m', limit=1)
                    if df_price is None or len(df_price) == 0:
                        continue
                    current = df_price['close'].iloc[-1]
                    self.partial_book(symbol, trade, current)
                    self.update_trailing_sl(symbol, trade, current)
                    if self.check_exit_conditions(symbol, trade):
                        self.emergency_exit(symbol)
                        continue
                    if (trade['direction'] == 'long' and current <= trade['sl_price']) or (trade['direction'] == 'short' and current >= trade['sl_price']):
                        send_telegram(f"🛑 SL Hit: {symbol}")
                        self.emergency_exit(symbol)
                        continue
            time.sleep(10)
        except KeyboardInterrupt:
            send_telegram("🛑 Bot stopped manually.")
            break
        except Exception as e:
            send_telegram(f"💥 Critical error: {e}")
            logging.error(f"Critical Loop Error: {e}")
            time.sleep(60)