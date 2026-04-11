import os
import json
import time
import datetime
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

class UniversalEngine:
    def __init__(self):
        # Absolute paths to ensure it works on both local and Railway
        self.base_dir = os.path.join(os.path.dirname(__file__), '..')
        self.portfolio_files = {
            "core": os.path.join(self.base_dir, 'portfolio_stocks.json'),
            "momentum2": os.path.join(self.base_dir, 'portfolio_stocks2.json'),
        }
        self.cache_file = os.path.join(self.base_dir, 'portfolio_cache.json')

        print(f"🛠️ Engine Init: Cache Path -> {self.cache_file}")

        # Start background updater — every 5 minutes
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.update_cache, 'interval', minutes=5)
        self.scheduler.start()

        # Trigger first update immediately in background
        self.scheduler.add_job(self.update_cache, 'date',
                               run_date=datetime.datetime.now())

    # ──────────────────────────────────────────────────────────────
    # Public API — reads cache instantly, never blocks page load
    # ──────────────────────────────────────────────────────────────
    def get_market_quote(self, symbols):
        """Returns data from cache instantly (no yfinance call here)."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                if data:
                    return data
            except Exception as e:
                print(f"❌ Error reading cache: {e}")
        print("⚠️ Cache not ready yet — returning empty (background refresh in progress)")
        return {}

    def read_portfolio(self, portfolio_key):
        portfolio_file = self.portfolio_files.get(portfolio_key)
        if not portfolio_file or not os.path.exists(portfolio_file):
            return []
        try:
            with open(portfolio_file, 'r') as f:
                return json.load(f)
        except Exception:
            print(f"❌ Error: {os.path.basename(portfolio_file)} is empty or invalid.")
            return []

    def get_all_tracked_symbols(self):
        symbols, seen = [], set()
        for portfolio_key in self.portfolio_files:
            for stock in self.read_portfolio(portfolio_key):
                sym = stock.get('symbol')
                if sym and sym not in seen:
                    seen.add(sym)
                    symbols.append(sym)
        return symbols

    # ──────────────────────────────────────────────────────────────
    # Background cache refresh — BATCHED yfinance (fast, ~10 sec)
    # ──────────────────────────────────────────────────────────────
    def update_cache(self):
        t0 = datetime.datetime.now()
        print(f"🔄 Background Refresh Started at {t0.strftime('%H:%M:%S')}")

        raw_symbols = self.get_all_tracked_symbols()
        if not raw_symbols:
            print("📉 No stocks found in portfolio files")
            return

        # Normalise: ensure .NS suffix for NSE tickers
        yf_symbols = [s if s.endswith(".NS") else f"{s}.NS" for s in raw_symbols]
        sym_map    = {yf: raw for yf, raw in zip(yf_symbols, raw_symbols)}

        # ── Batched download (30 tickers, 3s pause, 45s timeout) ──
        _BATCH, _PAUSE, _TIMEOUT = 30, 3, 45
        batches     = [yf_symbols[i:i+_BATCH] for i in range(0, len(yf_symbols), _BATCH)]
        close_frames = []

        print(f"  {len(yf_symbols)} symbols → {len(batches)} batch(es)")
        for b_idx, batch in enumerate(batches, 1):
            print(f"  batch {b_idx}/{len(batches)} ({len(batch)} tickers)…", end=" ", flush=True)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(yf.download, batch,
                                      period="5d", interval="1d",
                                      progress=False, auto_adjust=True)
                    raw = fut.result(timeout=_TIMEOUT)

                close = raw["Close"] if "Close" in raw.columns else raw
                if hasattr(close, 'to_frame'):          # single-ticker → Series
                    close = close.to_frame(name=batch[0])
                close = close.dropna(how="all")
                got = [c for c in close.columns if close[c].dropna().shape[0] > 0]
                if got:
                    close_frames.append(close[got])
                    print(f"✓ {len(got)}")
                else:
                    print("✗ empty")
            except Exception as e:
                print(f"✗ {type(e).__name__}: {e}")

            if b_idx < len(batches):
                time.sleep(_PAUSE)

        if not close_frames:
            print("⚠️ No data received — cache NOT updated")
            return

        import pandas as pd
        all_close = pd.concat(close_frames, axis=1)
        all_close = all_close.loc[:, ~all_close.columns.duplicated()].sort_index()

        # Build quotes dict: ltp = last row, day_change vs previous close
        quotes = {}
        for yf_sym, raw_sym in sym_map.items():
            try:
                series = all_close[yf_sym].dropna()
                if series.empty:
                    continue
                ltp   = float(series.iloc[-1])
                prev  = float(series.iloc[-2]) if len(series) > 1 else ltp
                day_change = round(((ltp / prev) - 1) * 100, 2) if prev else 0.0
                quotes[raw_sym] = {"ltp": round(ltp, 2), "day_change": day_change}
            except Exception:
                pass

        # Atomic write
        tmp = self.cache_file + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(quotes, f)
        os.replace(tmp, self.cache_file)

        elapsed = (datetime.datetime.now() - t0).seconds
        print(f"✅ Cache updated — {len(quotes)}/{len(raw_symbols)} stocks in {elapsed}s "
              f"({datetime.datetime.now().strftime('%H:%M:%S')})")

# Singleton
engine = UniversalEngine()
