import yfinance as yf
import time
import datetime

class UniversalEngine:
    """
    Free and reliable market data engine using yfinance 
    with a built-in throttle for maximum stability.
    """
    def __init__(self, delay=0.5):
        self.delay = delay # Throttle delay in seconds

    def get_market_quote(self, symbols):
        """
        Fetch LTP for symbols one by one with a delay.
        """
        quotes = {}
        print(f"🔄 Universal Engine: Fetching {len(symbols)} quotes with {self.delay}s delay...")
        
        for symbol in symbols:
            # Standardize symbol for NSE if needed
            ticker_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            
            try:
                # Fetch only the latest price (period=1d, interval=1m)
                ticker = yf.Ticker(ticker_symbol)
                data = ticker.fast_info
                
                # Use fast_info for minimal latency
                ltp = data.get('last_price')
                
                if ltp:
                    quotes[symbol] = round(float(ltp), 2)
                    # print(f"✅ {symbol}: {quotes[symbol]}")
                else:
                    # Fallback for manual data check
                    hist = ticker.history(period="1d", interval="1m")
                    if not hist.empty:
                        quotes[symbol] = round(float(hist['Close'].iloc[-1]), 2)
            except Exception as e:
                print(f"⚠️ Warning: Could not fetch {symbol}: {e}")
            
            # THE IMPORTANT BIT: The 0.5s Throttle
            time.sleep(self.delay)

        return quotes

# Singleton instance
engine = UniversalEngine(delay=0.5)
