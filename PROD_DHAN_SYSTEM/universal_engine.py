import os
import json
import time
import datetime
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler

class UniversalEngine:
    def __init__(self, delay=0.5):
        self.delay = delay
        # Absolute paths to ensure it works on both local and Railway
        self.base_dir = os.path.join(os.path.dirname(__file__), '..')
        self.portfolio_files = {
            "core": os.path.join(self.base_dir, 'portfolio_stocks.json'),
            "momentum2": os.path.join(self.base_dir, 'portfolio_stocks2.json'),
        }
        self.cache_file = os.path.join(self.base_dir, 'portfolio_cache.json')
        
        print(f"🛠️ Engine Init: Cache Path -> {self.cache_file}")

        # Start background updater
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.update_cache, 'interval', minutes=5)
        self.scheduler.start()
        
        # TRIGGER FIRST UPDATE IMMEDIATELY IN BACKGROUND
        self.scheduler.add_job(self.update_cache, 'date', run_date=datetime.datetime.now())

    def get_market_quote(self, symbols):
        """Returns data from cache instantly."""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                try:
                    data = json.load(f)
                    if data:
                        return data
                except Exception as e:
                    print(f"❌ Error reading cache: {e}")
        
        print("⚠️ Cache file not found or empty yet...")
        return {}

    def read_portfolio(self, portfolio_key):
        portfolio_file = self.portfolio_files.get(portfolio_key)
        if not portfolio_file or not os.path.exists(portfolio_file):
            return []
        with open(portfolio_file, 'r') as f:
            try:
                return json.load(f)
            except:
                print(f"❌ Error: {os.path.basename(portfolio_file)} is empty or invalid.")
                return []

    def get_all_tracked_symbols(self):
        symbols = []
        seen = set()
        for portfolio_key in self.portfolio_files:
            for stock in self.read_portfolio(portfolio_key):
                symbol = stock.get('symbol')
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    symbols.append(symbol)
        return symbols

    def update_cache(self):
        """The actual fetching logic (runs in background)"""
        print(f"🔄 Background Refresh Started at {datetime.datetime.now().strftime('%H:%M:%S')}")

        symbols = self.get_all_tracked_symbols()
        if not symbols:
            print("📉 No stocks found in portfolio files")
            return
        quotes = {}
        
        for symbol in symbols:
            ticker_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            try:
                ticker = yf.Ticker(ticker_symbol)
                # Use faster method first
                data = ticker.fast_info
                ltp = data.get('last_price')
                prev_close = data.get('previous_close')
                
                # If fast_info is empty, try history
                if not ltp:
                    hist = ticker.history(period="2d")
                    if not hist.empty:
                        ltp = hist['Close'].iloc[-1]
                        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else ltp

                if ltp:
                    day_change = 0.0
                    if prev_close:
                        day_change = round(((ltp / prev_close) - 1) * 100, 2)
                    
                    quotes[symbol] = {
                        "ltp": round(float(ltp), 2),
                        "day_change": day_change
                    }
                    print(f"  ✅ Fetched {symbol}: {ltp}")
                else:
                    print(f"  ⚠️ No price found for {symbol}")
            except Exception as e:
                print(f"  ❌ Error fetching {symbol}: {e}")
            
            time.sleep(self.delay)

        # Save to cache
        with open(self.cache_file, 'w') as f:
            json.dump(quotes, f)
        
        print(f"✅ Cache updated successfully with {len(quotes)} stocks at {datetime.datetime.now().strftime('%H:%M:%S')}")

# Singleton instance
engine = UniversalEngine(delay=0.5)
