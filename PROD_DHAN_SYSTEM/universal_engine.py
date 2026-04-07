import os
import json
import time
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler

class UniversalEngine:
    def __init__(self, delay=0.5):
        self.delay = delay
        self.cache_file = os.path.join(os.path.dirname(__file__), '..', 'portfolio_cache.json')
        
        # Start background updater
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.update_cache, 'interval', minutes=5)
        self.scheduler.start()

    def get_market_quote(self, symbols):
        """Returns data from cache instantly."""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                try:
                    return json.load(f)
                except:
                    pass
        
        # If cache doesn't exist, trigger one update and return empty
        return {}

    def update_cache(self):
        """The actual fetching logic (runs in background)"""
        from PROD_DHAN_SYSTEM.master_dashboard import get_tracked_stocks
        stocks = get_tracked_stocks()
        if not stocks: return
        
        symbols = [s['symbol'] for s in stocks]
        quotes = {}
        print(f"🔄 Background Refresh: Fetching {len(symbols)} quotes...")
        
        for symbol in symbols:
            ticker_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            try:
                ticker = yf.Ticker(ticker_symbol)
                data = ticker.fast_info
                ltp = data.get('last_price')
                prev_close = data.get('previous_close')
                
                day_change = 0.0
                if ltp and prev_close:
                    day_change = round(((ltp / prev_close) - 1) * 100, 2)

                if ltp:
                    quotes[symbol] = {
                        "ltp": round(float(ltp), 2),
                        "day_change": day_change
                    }
            except:
                pass
            time.sleep(self.delay)

        with open(self.cache_file, 'w') as f:
            json.dump(quotes, f)
        print("✅ Cache updated successfully.")

# Singleton instance
engine = UniversalEngine(delay=0.5)
