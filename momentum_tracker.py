import pandas as pd
import yfinance as yf
from tqdm import tqdm
import datetime
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Stooq fallback (works on Railway / cloud where Yahoo Finance is blocked) ──
try:
    from pandas_datareader import data as pdr
    _STOOQ_OK = True
except ImportError:
    _STOOQ_OK = False

# Hard timeout for yfinance bulk call (seconds).
# If Yahoo Finance hangs or returns partial data within this window → use Stooq.
_YF_TIMEOUT_SEC = 30


def _robust_download(symbols: list, months: int = 14, task_id: str = None) -> pd.DataFrame:
    """
    Batched yfinance (30 tickers, 3s pause) → Stooq thread-pool fallback.
    Same batching strategy as nse_history_provider.py sector tracker.
    """
    end   = datetime.date.today()
    start = end - datetime.timedelta(days=30 * months)

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
                               period=f"{months}mo", interval="1d",
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

def process_file(file_path, task_id="v1"):
    print(f"\nProcessing {file_path}...")
    df = pd.read_csv(file_path)
    
    # Clean symbols
    df['Symbol'] = df['Symbol'].str.replace('"', '').str.strip()
    symbols = [f"{s}.NS" for s in df['Symbol'].tolist() if pd.notna(s)]
    
    # Momentum timeframes (for scoring - FROZEN at 10)
    timeframes = {
        '1w': 7, '2w': 14, '3w': 21, '4w': 28,
        '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
        '1y': 365
    }
    
    # Fetch data
    total = len(symbols)
    update_progress(task_id, 0, total, "downloading",
                    log=f"📂 Loaded {total} symbols from CSV — starting download")
    print(f"Fetching historical data for {total} symbols...")
    all_data = _robust_download(symbols, months=14, task_id=task_id)

    if all_data.empty:
        update_progress(task_id, 0, total, "error", "No data available (yfinance + Stooq both failed)",
                        log="❌ No data returned — check network / yfinance")
        print("Error: Could not fetch data.")
        return pd.DataFrame()

    results = []
    current_prices = all_data.iloc[-1]
    
    update_progress(task_id, 0, total, "analyzing",
                    log=f"✅ Data ready ({all_data.shape[1]} symbols) — calculating momentum scores")
    for i, symbol in enumerate(tqdm(symbols, desc="Analyzing Momentum")):
        try:
            if i % 50 == 0 and i > 0:
                update_progress(task_id, i, total, "analyzing",
                                log=f"🔍 Analyzed {i}/{total} stocks…")
            elif i % 10 == 0:
                update_progress(task_id, i, total, "analyzing")
            
            if symbol not in all_data.columns:
                continue
                
            curr_price = current_prices[symbol]
            if pd.isna(curr_price):
                continue
                
            row = {'Symbol': symbol.replace('.NS', ''), 'Current Price': round(float(curr_price), 2)}
            
            # 1. Calculate 1-Day Change (Not in Momentum Score)
            try:
                prev_price = all_data[symbol].iloc[-2]
                if pd.notna(prev_price) and prev_price != 0:
                    row['1d'] = round(((curr_price / prev_price) - 1) * 100, 2)
                else:
                    row['1d'] = "N/A"
            except:
                row['1d'] = "N/A"

            # 2. Calculate Momentum Score (FROZEN: 1w to 1y only)
            green_count = 0
            one_year_return = 0
            for label, days in timeframes.items():
                try:
                    target_date = all_data.index[-1] - datetime.timedelta(days=days)
                    price_then = all_data[symbol].asof(target_date)
                    if pd.notna(price_then) and price_then != 0:
                        ret = ((curr_price / price_then) - 1) * 100
                        val = round(float(ret), 2)
                        row[label] = val
                        if val > 0: green_count += 1
                        if label == '1y': one_year_return = val
                    else:
                        row[label] = "N/A"
                except:
                    row[label] = "N/A"
            
            # 3. Category Logic (FROZEN: 10-point scale)
            category = "Other"
            if one_year_return > 15:
                if green_count == 10:
                    category = "Pure Momentum (10/10)"
                elif green_count == 9:
                    category = "Strong (9/10)"
                elif green_count == 8:
                    category = "Improving (8/10)"
            
            row['Score'] = f"{green_count}/10"
            row['Category'] = category
            results.append(row)
        except Exception:
            continue
            
    return pd.DataFrame(results)

def generate_html(df, output_file="momentum_report.html"):
    if df.empty:
        print("No data to generate report.")
        return

    # Exact column order as requested: 1d next to 1w
    cols = ['Symbol', 'Category', 'Score', 'Current Price', '1d', '1w', '2w', '3w', '4w', '1m', '2m', '3m', '6m', '9m', '1y']
    df_display = df[cols]

    headers = "".join(f"<th>{col}</th>" for col in cols)
    rows = ""
    for _, row in df_display.iterrows():
        row_html = "<tr>"
        for i, col_name in enumerate(cols):
            val = row[col_name]
            cls = ""
            # Apply color to all percentage columns (Starting from index 4: 1d)
            if i >= 4 and isinstance(val, (int, float)):
                if val > 0: cls = "positive"
                elif val < 0: cls = "negative"
            
            if col_name == 'Category':
                if "Pure" in str(val): cls = "cat-pure"
                elif "Strong" in str(val): cls = "cat-strong"
                elif "Improving" in str(val): cls = "cat-improving"
                
            row_html += f'<td class="{cls}">{val}</td>'
        row_html += "</tr>"
        rows += row_html

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NSE Momentum Dashboard Pro</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css">
        <style>
            :root {{ --primary: #3182ce; --success: #2f855a; --danger: #c53030; }}
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f0f2f5; }}
            .container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            h2 {{ color: #1a202c; text-align: center; margin-bottom: 10px; }}
            .subtitle {{ text-align: center; color: #718096; margin-bottom: 25px; font-size: 0.9em; }}
            
            .filter-group {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 25px; flex-wrap: wrap; }}
            .filter-btn {{ padding: 10px 18px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.2s; background: #edf2f7; color: #4a5568; }}
            .filter-btn.active {{ background: var(--primary); color: white; }}
            
            .positive {{ color: var(--success) !important; font-weight: bold; }}
            .negative {{ color: var(--danger) !important; font-weight: bold; }}
            
            .cat-pure {{ background-color: #c6f6d5 !important; color: #22543d !important; font-weight: bold; }}
            .cat-strong {{ background-color: #bee3f8 !important; color: #2a4365 !important; font-weight: bold; }}
            .cat-improving {{ background-color: #feebc8 !important; color: #744210 !important; font-weight: bold; }}
            
            /* Clean Headers - No Messy Arrows */
            table.dataTable thead th {{ 
                background-color: #2d3748 !important; 
                color: white !important; 
                padding: 12px 10px !important; 
                border: none !important;
                position: relative;
                cursor: pointer;
            }}
            table.dataTable thead th.sorting:before, 
            table.dataTable thead th.sorting:after,
            table.dataTable thead th.sorting_asc:before,
            table.dataTable thead th.sorting_asc:after,
            table.dataTable thead th.sorting_desc:before,
            table.dataTable thead th.sorting_desc:after {{ display: none !important; }}
            
            table.dataTable thead th.sorting_asc {{ border-bottom: 3px solid #63b3ed !important; }}
            table.dataTable thead th.sorting_desc {{ border-bottom: 3px solid #63b3ed !important; }}
            
            table.dataTable thead th.sorting_asc::after {{ content: " ↑"; }}
            table.dataTable thead th.sorting_desc::after {{ content: " ↓"; }}
            
            table.dataTable tbody td {{ padding: 10px !important; border-bottom: 1px solid #edf2f7; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>NSE Momentum Dashboard Pro</h2>
            <div class="subtitle">Updated: {date} | 10-Point Score (1W-1Y) | 1D View Added</div>
            
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterTable('all', this)">All Stocks</button>
                <button class="filter-btn" onclick="filterTable('Pure', this)">🌟 Pure Momentum (10/10)</button>
                <button class="filter-btn" onclick="filterTable('Strong', this)">💪 Strong (9/10)</button>
                <button class="filter-btn" onclick="filterTable('Improving', this)">📈 Improving (8/10)</button>
            </div>

            <table id="momentumTable" class="display" style="width:100%">
                <thead><tr>{headers}</tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>

        <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
        <script src="https://cdn.datatables.net/fixedheader/3.2.2/js/dataTables.fixedHeader.min.js"></script>
        <script>
            let table;
            $(document).ready( function () {{
                table = $('#momentumTable').DataTable({{
                    "pageLength": 100,
                    "order": [[14, "desc"]], // Sort by 1 Year return
                    "scrollX": true,
                    "fixedHeader": true
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
    print(f"\nDashboard generated: {output_file}")

INPUT_FILES = [
    "market cap greater than 10000.csv",   # choice 0 → 10k Cap
    "market cap greater than 20000csv.csv", # choice 1 → 20k Cap
    "ind_nifty500list.csv",                 # choice 2 → Nifty 500
]
OUTPUT_FILES = [
    "momentum_report_v1_10k.html",
    "momentum_report_v1_20k.html",
    "momentum_report_v1_nifty500.html",
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

    task_id = f"v1_{choice}"
    if 0 <= choice < len(INPUT_FILES):
        selected_file = INPUT_FILES[choice]
        output_file   = OUTPUT_FILES[choice]
        label         = CHOICE_LABELS[choice]
        if os.path.exists(selected_file):
            print(f"Running V1 Analysis on {selected_file} ({label})...")
            results_df = process_file(selected_file, task_id)
            generate_html(results_df, output_file=output_file)
            update_progress(task_id, 100, 100, "completed",
                            log=f"✅ Done! Report saved → {output_file}")
        else:
            update_progress(task_id, 0, 0, "error", f"File {selected_file} not found")
            print(f"Error: {selected_file} not found.")
    else:
        print("Invalid choice index.")
