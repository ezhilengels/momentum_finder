import pandas as pd
import yfinance as yf
from tqdm import tqdm
import datetime
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import buffett
import config

# ── Stooq fallback (works on Railway / cloud where Yahoo Finance is blocked) ──
try:
    from pandas_datareader import data as pdr
    _STOOQ_OK = True
except ImportError:
    _STOOQ_OK = False


def _robust_download(symbols: list, years: int = 6, task_id: str = None) -> pd.DataFrame:
    """
    Batched yfinance (30 tickers, 3s pause) → Stooq thread-pool fallback.
    Same batching strategy as nse_history_provider.py sector tracker.
    """
    end   = datetime.date.today()
    start = end - datetime.timedelta(days=365 * years)

    _BATCH   = 30   # tickers per yfinance call
    _PAUSE   = 3    # seconds between batches (throttle)
    _TIMEOUT = 45   # per-batch hard timeout

    batches    = [symbols[i:i+_BATCH] for i in range(0, len(symbols), _BATCH)]
    all_frames = []
    yf_ok = yf_fail = 0

    msg = f"⏬ yfinance: {len(symbols)} symbols → {len(batches)} batches (30/batch, 3s pause)"
    print(f"  {msg}")
    if task_id: _append_log(task_id, msg)

    for b_idx, batch in enumerate(batches, 1):
        print(f"  batch {b_idx:>2}/{len(batches)} ({len(batch)}) …", end=" ", flush=True)
        try:
            with ThreadPoolExecutor(max_workers=1) as _p:
                _f = _p.submit(yf.download, batch,
                               period=f"{years}y", interval="1d",
                               progress=False, auto_adjust=True)
                raw = _f.result(timeout=_TIMEOUT)
            close = raw["Close"] if "Close" in raw.columns else raw
            if isinstance(close, pd.Series):
                close = close.to_frame(name=batch[0])
            close = close.dropna(how="all")
            got = [c for c in close.columns if close[c].dropna().shape[0] > 0]
            if got:
                all_frames.append(close[got])
                yf_ok += len(got)
                print(f"✓ {len(got)}")
            else:
                yf_fail += len(batch)
                print("✗ empty")
        except Exception as e:
            yf_fail += len(batch)
            print(f"✗ {type(e).__name__}")
        if task_id and (b_idx % 5 == 0 or b_idx == len(batches)):
            _append_log(task_id, f"⏬ Batch {b_idx}/{len(batches)} done — ✓{yf_ok} fetched so far")
        if b_idx < len(batches):
            time.sleep(_PAUSE)

    summary = f"yfinance done: ✓{yf_ok} ✗{yf_fail} / {len(symbols)}"
    print(f"  [yfinance] total ✓{yf_ok} ✗{yf_fail}")
    if task_id: _append_log(task_id, summary)

    if all_frames:
        merged = pd.concat(all_frames, axis=1)
        merged = merged.loc[:, ~merged.columns.duplicated()]
        if merged.shape[1] >= max(1, len(symbols) * 0.5):
            return merged.sort_index()
        msg = f"⚠️ yfinance low coverage ({merged.shape[1]}/{len(symbols)}) → Stooq fallback"
        print(f"  {msg}")
        if task_id: _append_log(task_id, msg)

    if not _STOOQ_OK:
        print("  [Stooq] pandas-datareader not installed — no fallback")
        if task_id: _append_log(task_id, "❌ No fallback (install pandas-datareader)")
        return pd.DataFrame()

    msg = f"🔄 Stooq fallback: {len(symbols)} symbols, 20 workers …"
    print(f"  {msg}")
    if task_id: _append_log(task_id, msg)
    results: dict = {}
    ok = fail = 0

    def _fetch_one(sym):
        try:
            df = pdr.DataReader(sym, "stooq", start=start, end=end)
            if df is not None and not df.empty and "Close" in df.columns:
                s = df["Close"].rename(sym).sort_index()
                s.index = pd.to_datetime(s.index).normalize()
                return sym, s.dropna()
        except Exception:
            pass
        return sym, None

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_one, s): s for s in symbols}
        done = 0
        for fut in as_completed(futures):
            sym, series = fut.result()
            done += 1
            if series is not None and not series.empty:
                results[sym] = series
                ok += 1
            else:
                fail += 1
            if done % 50 == 0 or done == len(symbols):
                pct = int(done / len(symbols) * 100)
                bar = ("█" * (pct // 5)).ljust(20)
                print(f"\r  [Stooq] [{bar}] {pct:3d}%  ✓{ok} ✗{fail}", end="", flush=True)
            time.sleep(0.05)

    print(f"\n  [Stooq] ✓{ok}/{len(symbols)}")
    if not results:
        return pd.DataFrame()
    df = pd.concat(results.values(), axis=1)
    return df.loc[:, ~df.columns.duplicated()].sort_index()

def _read_progress_file():
    pf = "progress.json"
    if os.path.exists(pf):
        try:
            with open(pf, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_progress_file(data):
    pf = "progress.json"
    with open(pf, "w") as f:
        json.dump(data, f)

def update_progress(task_id, current, total, status="running", error=None, log=None):
    data = _read_progress_file()
    existing = data.get(task_id, {})
    logs = existing.get("logs", [])
    if log:
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        logs.append(f"[{ts}] {log}")
        logs = logs[-10:]
    data[task_id] = {
        "current": current,
        "total": total,
        "status": status,
        "error": error,
        "time": datetime.datetime.now().strftime('%H:%M:%S'),
        "logs": logs,
    }
    _write_progress_file(data)

def _append_log(task_id, msg):
    """Append a log line without changing current/total/status."""
    data = _read_progress_file()
    existing = data.get(task_id, {})
    logs = existing.get("logs", [])
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    logs.append(f"[{ts}] {msg}")
    logs = logs[-10:]
    existing["logs"] = logs
    data[task_id] = existing
    _write_progress_file(data)

def get_fundamental_data(ticker_obj, current_price):
    """Fetch data needed for buffett.py valuation."""
    try:
        info = ticker_obj.info
        
        # Financials for TTM values
        # Note: yfinance can be flaky with financials, we use .info as fallback
        net_profit = info.get('netIncomeToCommon')
        eps = info.get('trailingEps')
        shares = info.get('sharesOutstanding')
        beta = info.get('beta') or 1.0
        
        # For Depreciation and Capex, we often need the cashflow statement
        # This is the slow part, so we try-except it
        depreciation = 0
        capex = 0
        try:
            cf = ticker_obj.cashflow
            if not cf.empty:
                # Look for Depreciation and Capital Expenditure in rows
                if 'Depreciation' in cf.index:
                    depreciation = abs(cf.loc['Depreciation'].iloc[0])
                if 'Capital Expenditure' in cf.index:
                    capex = abs(cf.loc['Capital Expenditure'].iloc[0])
                elif 'Capital Expenditures' in cf.index:
                    capex = abs(cf.loc['Capital Expenditures'].iloc[0])
        except:
            pass

        data = {
            "net_profit_ttm": net_profit,
            "depreciation_ttm": depreciation,
            "capex_ttm": capex,
            "shares_outstanding": shares,
            "eps_ttm": eps,
            "cmp": current_price,
            "eps_growth_5y": info.get('earningsQuarterlyGrowth', 0.06),
            "beta": beta,
            "cash": info.get('totalCash', 0),
            "total_debt": info.get('totalDebt', 0)
        }
        return data
    except Exception:
        return None

def process_file(file_path, task_id="v3"):
    print(f"\nProcessing {file_path} (V3 Ultimate Value + Momentum)...")
    df = pd.read_csv(file_path)
    
    df['Symbol'] = df['Symbol'].str.replace('"', '').str.strip()
    symbols = [f"{s}.NS" for s in df['Symbol'].tolist() if pd.notna(s)]
    
    timeframes = {
        '1w': 7, '2w': 14, '3w': 21, '4w': 28,
        '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
        '1y': 365, '2y': 730, '3y': 1095, '4y': 1460, '5y': 1825
    }
    
    total = len(symbols)
    update_progress(task_id, 0, total, "downloading",
                    log=f"📂 Loaded {total} symbols from CSV — starting download")
    print(f"Fetching 6 years of historical data for {total} symbols...")
    all_data = _robust_download(symbols, years=6, task_id=task_id)

    if all_data.empty:
        update_progress(task_id, 0, total, "error", "No price data (yfinance + Stooq both failed)",
                        log="❌ No data returned — check network / yfinance")
        print("Error: Could not fetch price data.")
        return pd.DataFrame()

    results = []
    current_prices = all_data.iloc[-1]
    
    # We use yf.Tickers for fundamental data
    tickers_dict = yf.Tickers(" ".join(symbols)).tickers
    
    update_progress(task_id, 0, total, "analyzing",
                    log=f"✅ Data ready ({all_data.shape[1]} symbols) — running V3 deep analysis")
    for i, symbol in enumerate(tqdm(symbols, desc="V3 Deep Analysis")):
        try:
            if i % 50 == 0 and i > 0:
                update_progress(task_id, i, total, "analyzing",
                                log=f"🔍 Analyzed {i}/{total} stocks…")
            elif i % 2 == 0:
                update_progress(task_id, i, total, "analyzing")
            
            if symbol not in all_data.columns:
                continue
                
            curr_price = current_prices[symbol]
            if pd.isna(curr_price):
                continue
            
            row = {'Symbol': symbol.replace('.NS', ''), 'Current Price': round(float(curr_price), 2)}
            
            # 1. Momentum Logic (V2)
            green_count = 0
            returns = {}
            for label, days in timeframes.items():
                target_date = all_data.index[-1] - datetime.timedelta(days=days)
                price_then = all_data[symbol].asof(target_date)
                if pd.notna(price_then) and price_then != 0:
                    ret = round(((curr_price / price_then) - 1) * 100, 2)
                    row[label] = ret
                    returns[label] = ret
                    if ret > 0: green_count += 1
                else:
                    row[label] = "N/A"
            
            # 2. Buffett Valuation Logic (New in V3)
            ticker_obj = tickers_dict[symbol]
            fund_data = get_fundamental_data(ticker_obj, curr_price)
            
            buffett_yield = "N/A"
            iv = "N/A"
            price_to_iv = "N/A"
            
            if fund_data:
                valuation = buffett.calculate(fund_data)
                if valuation.get('valid'):
                    buffett_yield = valuation.get('earnings_yield', "N/A")
                    iv = valuation.get('iv', "N/A")
                    if iv and iv > 0:
                        price_to_iv = round(curr_price / iv, 2)

            row['BuffettYield (%)'] = buffett_yield
            row['IV'] = iv
            row['Price/IV'] = price_to_iv
            row['Score'] = f"{green_count}/14"
            
            # 3. Super Category Logic
            category = "Other"
            is_growth = (returns.get('1y') or 0) > 15
            is_cheap = isinstance(buffett_yield, (int, float)) and buffett_yield > 7.0
            
            if green_count == 14 and is_cheap:
                category = "💎 Value-Momentum King"
            elif green_count >= 12 and price_to_iv != "N/A" and price_to_iv < 1.1:
                category = "🚀 GARP (Growth @ Reason. Price)"
            elif green_count == 14:
                category = "🔥 Pure Momentum"
            elif green_count >= 10:
                category = "📈 Strong"
            elif isinstance(buffett_yield, (int, float)) and buffett_yield > 10:
                category = "💰 Deep Value"
                
            row['Category'] = category
            results.append(row)
            
        except Exception as e:
            # print(f"Error processing {symbol}: {e}")
            continue
            
    return pd.DataFrame(results)

def generate_html(df, output_file="momentum_report_v3.html"):
    if df.empty:
        print("No data to generate report.")
        return

    # Dynamic columns ordering
    cols = ['Symbol', 'Category', 'Score', 'BuffettYield (%)', 'Price/IV', 'IV', 'Current Price']
    momentum_cols = ['1w', '2w', '3w', '4w', '1m', '2m', '3m', '6m', '9m', '1y', '2y', '3y', '4y', '5y']
    df = df[cols + momentum_cols]

    headers = "".join(f"<th>{col}</th>" for col in df.columns)
    rows = ""
    for _, row in df.iterrows():
        row_html = "<tr>"
        for i, col_name in enumerate(df.columns):
            val = row[col_name]
            cls = ""
            
            # Momentum colors (index 7 onwards)
            if i >= 7 and isinstance(val, (int, float)):
                if val > 0: cls = "positive"
                elif val < 0: cls = "negative"
            
            # Buffett Yield colors
            if col_name == 'BuffettYield (%)' and isinstance(val, (int, float)):
                if val > 7.5: cls = "positive"
                elif val < 3: cls = "negative"
            
            # Price/IV colors
            if col_name == 'Price/IV' and isinstance(val, (int, float)):
                if val < 0.8: cls = "positive"
                elif val > 1.5: cls = "negative"

            # Category highlighting
            if col_name == 'Category':
                if "King" in str(val): cls = "cat-king"
                elif "GARP" in str(val): cls = "cat-garp"
                elif "Deep" in str(val): cls = "cat-value"
                
            row_html += f'<td class="{cls}">{val}</td>'
        row_html += "</tr>"
        rows += row_html

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NSE Ultimate Dashboard (V3: Value + Momentum)</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedcolumns/4.0.2/css/fixedColumns.dataTables.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f4f7f6; }}
            .container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
            h2 {{ color: #2c3e50; text-align: center; margin-bottom: 5px; }}
            .subtitle {{ text-align: center; color: #7f8c8d; margin-bottom: 30px; }}
            
            .filter-group {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 25px; flex-wrap: wrap; }}
            .filter-btn {{ padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; background: #dfe6e9; color: #2d3436; transition: 0.3s; }}
            .filter-btn.active {{ background: #0984e3; color: white; }}
            
            .positive {{ color: #27ae60 !important; font-weight: bold; }}
            .negative {{ color: #d63031 !important; font-weight: bold; }}
            
            .cat-king {{ background-color: #dff9fb !important; color: #0984e3 !important; font-weight: bold; border: 2px solid #0984e3; }}
            .cat-garp {{ background-color: #e3f2fd !important; color: #1565c0 !important; font-weight: bold; }}
            .cat-value {{ background-color: #f1f8e9 !important; color: #33691e !important; font-weight: bold; }}
            
            table.dataTable thead th {{ background-color: #2d3436 !important; color: white !important; position: relative; cursor: pointer; }}
            
            /* Show only one arrow for sorting */
            table.dataTable thead th.sorting:before, 
            table.dataTable thead th.sorting:after,
            table.dataTable thead th.sorting_asc:before,
            table.dataTable thead th.sorting_asc:after,
            table.dataTable thead th.sorting_desc:before,
            table.dataTable thead th.sorting_desc:after {{ display: none !important; }}
            
            table.dataTable thead th.sorting_asc::after {{ content: " ↑"; }}
            table.dataTable thead th.sorting_desc::after {{ content: " ↓"; }}
            
            /* Freeze Symbol Column */
            th:first-child, td:first-child {{ position: sticky; left: 0; background-color: #fff !important; z-index: 10; border-right: 2px solid #dfe6e9 !important; }}
            th:first-child {{ z-index: 11; background-color: #2d3436 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>NSE Ultimate Dashboard (V3)</h2>
            <div class="subtitle">Value (Buffett Model) + Multi-Year Momentum | Updated: {date}</div>
            
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterTable('all', this)">All Stocks</button>
                <button class="filter-btn" onclick="filterTable('King', this)">💎 Value-Momentum King</button>
                <button class="filter-btn" onclick="filterTable('GARP', this)">🚀 GARP</button>
                <button class="filter-btn" onclick="filterTable('Deep', this)">💰 Deep Value</button>
                <button class="filter-btn" onclick="filterTable('Pure', this)">🔥 Pure Momentum</button>
            </div>

            <table id="ultimateTable" class="display nowrap" style="width:100%">
                <thead>
                    <tr>
                        {headers}
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>

        <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
        <script src="https://cdn.datatables.net/fixedheader/3.2.2/js/dataTables.fixedHeader.min.js"></script>
        <script>
            let table;
            $(document).ready( function () {{
                table = $('#ultimateTable').DataTable({{
                    "pageLength": 100,
                    "order": [[2, "desc"]], // Sort by Score
                    "scrollX": true,
                    "fixedHeader": true,
                    "fixedColumns": {{
                        left: 1
                    }}
                }});
            }} );

            function filterTable(category, btn) {{
                $('.filter-btn').removeClass('active');
                $(btn).addClass('active');
                if (category === 'all') {{
                    table.column(1).search('').draw();
                }} else {{
                    table.column(1).search(category).draw();
                }}
            }}
        </script>
    </body>
    </html>
    """.format(date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), headers=headers, rows=rows)
    
    with open(output_file, "w") as f:
        f.write(html_template)
    print(f"\nDashboard V3 generated: {output_file}")

INPUT_FILES = [
    "market cap greater than 10000.csv",   # choice 0 → 10k Cap
    "market cap greater than 20000csv.csv", # choice 1 → 20k Cap
    "ind_nifty500list.csv",                 # choice 2 → Nifty 500
]
OUTPUT_FILES = [
    "momentum_report_v3_10k.html",
    "momentum_report_v3_20k.html",
    "momentum_report_v3_nifty500.html",
]
CHOICE_LABELS = ["10k Cap", "20k Cap", "Nifty 500"]

if __name__ == "__main__":
    import sys
    # Default to 20000 (index 1) if no argument provided
    choice = 1
    if len(sys.argv) > 1:
        try:
            choice = int(sys.argv[1])
        except:
            pass

    task_id = f"v3_{choice}"
    if 0 <= choice < len(INPUT_FILES):
        selected_file = INPUT_FILES[choice]
        output_file   = OUTPUT_FILES[choice]
        label         = CHOICE_LABELS[choice]
        if os.path.exists(selected_file):
            print(f"Running V3 Analysis on {selected_file} ({label})...")
            results_df = process_file(selected_file, task_id)
            generate_html(results_df, output_file=output_file)
            update_progress(task_id, 100, 100, "completed",
                            log=f"✅ Done! Report saved → {output_file}")
        else:
            update_progress(task_id, 0, 0, "error", f"File {selected_file} not found")
            print(f"Error: {selected_file} not found.")
    else:
        print("Invalid choice index.")
