import os
import json
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory, jsonify

# Ensure the current directory is in the path for imports
sys.path.append(os.path.dirname(__file__))
from universal_engine import engine

app = Flask(__name__)

# Paths to frozen assets in the root folder
ROOT_DIR = os.path.join(os.path.dirname(__file__), '..')
PROGRESS_FILE = os.path.join(ROOT_DIR, 'progress.json')

# ── Ensure required runtime directories exist (Railway ephemeral FS) ──────────
for _d in ["output", "cache", os.path.join("cache", "sector_tracker")]:
    os.makedirs(os.path.join(ROOT_DIR, _d), exist_ok=True)

# Initialize progress file
if not os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({}, f)

PORTFOLIOS = [
    ("core", "Core Portfolio"),
    ("momentum2", "Momentum2"),
]

_STALE_MINUTES = 30   # tasks older than this are treated as dead

def _is_stale(task_time_str: str) -> bool:
    """Return True if task's HH:MM:SS timestamp is > _STALE_MINUTES ago."""
    try:
        now   = datetime.now()
        t     = datetime.strptime(task_time_str, "%H:%M:%S").replace(
                    year=now.year, month=now.month, day=now.day)
        diff  = (now - t).total_seconds()
        # Handle midnight rollover: if diff is negative, add 24h
        if diff < 0:
            diff += 86400
        return diff > _STALE_MINUTES * 60
    except Exception:
        return True   # unparseable → treat as stale


def read_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    with open(PROGRESS_FILE, "r") as f:
        try:
            data = json.load(f)
        except Exception:
            return {}

    # Mark any stuck "downloading/analyzing" tasks that are stale as interrupted
    changed = False
    for task_id, task in data.items():
        if task.get("status") in ("downloading", "analyzing", "running"):
            if _is_stale(task.get("time", "")):
                task["status"]  = "error"
                task["error"]   = "Process interrupted (stale)"
                changed = True

    if changed:
        try:
            with open(PROGRESS_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    return data

def get_portfolio_data(portfolio_key):
    """Fetch live data using Universal Engine (yfinance)"""
    stocks = engine.read_portfolio(portfolio_key)
    if not stocks: return []
    
    symbols = [s['symbol'] for s in stocks]
    quotes = engine.get_market_quote(symbols)
    
    results = []
    for s in stocks:
        symbol = s['symbol']
        fixed_val = float(s['fixed_value'])
        
        # Safely get data from engine output
        data = quotes.get(symbol, {})
        cmp = data.get("ltp", "N/A")
        day_change = data.get("day_change", 0.0)
        
        pl_percent = 0.0
        if isinstance(cmp, (int, float)):
            pl_percent = round(((cmp - fixed_val) / fixed_val) * 100, 2)
            
        results.append({
            "symbol": symbol,
            "fixed_value": fixed_val,
            "cmp": cmp,
            "day_change": day_change,
            "pl_percent": pl_percent
        })
    return results

def summarize_portfolio(portfolio):
    total_pl = [s['pl_percent'] for s in portfolio if isinstance(s['pl_percent'], (int, float))]
    avg_pl = round(sum(total_pl) / len(total_pl), 2) if total_pl else 0

    total_day = [s['day_change'] for s in portfolio if isinstance(s['day_change'], (int, float))]
    avg_day = round(sum(total_day) / len(total_day), 2) if total_day else 0

    return {
        "count": len(portfolio),
        "avg_pl": avg_pl,
        "avg_day": avg_day,
    }

@app.route("/")
def index():
    try:
        portfolios = []
        combined = []
        for key, label in PORTFOLIOS:
            portfolio = get_portfolio_data(key)
            portfolios.append({
                "key": key,
                "label": label,
                "table_id": f"{key}Table",
                "rows": portfolio,
                "summary": summarize_portfolio(portfolio),
            })
            combined.extend(portfolio)

        combined_summary = summarize_portfolio(combined)

        return render_template_string(HTML_TEMPLATE, 
                                     portfolios=portfolios, 
                                     portfolio_table_ids=[p["table_id"] for p in portfolios],
                                     avg_pl=combined_summary["avg_pl"], 
                                     avg_day=combined_summary["avg_day"],
                                     current_tab='portfolio', 
                                     now=datetime.now(),
                                     selected_run=request.args.get('run', ''))
    except Exception as e:
        return f"<html><body><h1>⚠️ Dashboard Error</h1><p>{str(e)}</p><a href='/'>Try Refreshing</a></body></html>"

@app.route("/report/<version>")
def view_report(version):
    """Serve the most recently generated report for the given version (v1/v2/v3)."""
    import glob
    # Look for per-choice files first (newest wins), fallback to legacy single file
    pattern = os.path.join(ROOT_DIR, f"momentum_report_{version}_*.html")
    candidates = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if candidates:
        return send_from_directory(ROOT_DIR, os.path.basename(candidates[0]))
    # Legacy fallback
    legacy = "momentum_report.html" if version == "v1" else f"momentum_report_{version}.html"
    legacy_path = os.path.join(ROOT_DIR, legacy)
    if os.path.exists(legacy_path):
        return send_from_directory(ROOT_DIR, legacy)
    return f"<html><body style='font-family:sans-serif;padding:40px'>" \
           f"<h2>📊 No {version.upper()} report yet</h2>" \
           f"<p>Run an analysis from the dashboard first.</p>" \
           f"<p><a href='/'>← Back to Portfolio</a></p></body></html>"

@app.route("/report/<version>/<choice>")
def view_report_choice(version, choice):
    """Serve a specific choice report: /report/v2/10k, /report/v2/20k, /report/v2/nifty500"""
    filename = f"momentum_report_{version}_{choice}.html"
    full_path = os.path.join(ROOT_DIR, filename)
    if os.path.exists(full_path):
        return send_from_directory(ROOT_DIR, filename)
    return f"<html><body style='font-family:sans-serif;padding:40px'>" \
           f"<h2>Report not found</h2><p>{filename} hasn't been generated yet.</p>" \
           f"<p><a href='/'>← Back</a></p></body></html>"

@app.route("/sector")
def view_sector():
    """Serve the latest sector tracker HTML report."""
    import glob, os
    output_dir = os.path.join(ROOT_DIR, "output")
    reports = sorted(glob.glob(os.path.join(output_dir, "sector_report_*.html")), reverse=True)
    if reports:
        return send_from_directory(output_dir, os.path.basename(reports[0]))
    return "<html><body style='font-family:sans-serif;padding:40px'>" \
           "<h2>📊 Sector Report Not Yet Generated</h2>" \
           "<p>Run the sector tracker first: <code>python sector_tracker_v2.py --mode eod</code></p>" \
           "<p><a href='/'>← Back to Portfolio</a></p></body></html>"

@app.route("/run_sector", methods=["POST"])
def run_sector():
    sector_path = os.path.join(ROOT_DIR, 'sector_tracker_v2.py')
    subprocess.Popen([sys.executable, sector_path, '--mode', 'eod'], cwd=ROOT_DIR)
    return redirect(url_for('index'))

@app.route("/api/progress")
def progress_api():
    return jsonify(read_progress())

@app.route("/run_v1/<choice>", methods=["POST"])
def run_v1(choice):
    v1_path = os.path.join(ROOT_DIR, 'momentum_tracker.py')
    subprocess.Popen([sys.executable, v1_path, choice], cwd=ROOT_DIR)
    return redirect(url_for('index', run=f'v1_{choice}'))

@app.route("/run_v2/<choice>", methods=["POST"])
def run_v2(choice):
    v2_path = os.path.join(ROOT_DIR, 'momentum_tracker_v2.py')
    subprocess.Popen([sys.executable, v2_path, choice], cwd=ROOT_DIR)
    return redirect(url_for('index', run=f'v2_{choice}'))

@app.route("/run_v3/<choice>", methods=["POST"])
def run_v3(choice):
    v3_path = os.path.join(ROOT_DIR, 'momentum_tracker_v3.py')
    subprocess.Popen([sys.executable, v3_path, choice], cwd=ROOT_DIR)
    return redirect(url_for('index', run=f'v3_{choice}'))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Master Portfolio | Terminal</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-light: #eff6ff;
            --primary-soft: #dbeafe;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --success: #10b981;
            --danger: #ef4444;
            --border: #e2e8f0;
            --nav-bg: #0f172a;
            --panel-tint: rgba(255,255,255,0.78);
        }

        body { 
            font-family: 'Inter', sans-serif; 
            margin: 0; 
            background:
                radial-gradient(circle at top left, rgba(37, 99, 235, 0.10), transparent 28%),
                radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 22%),
                linear-gradient(180deg, #f8fbff 0%, #f5f7fb 55%, #eef4f9 100%);
            color: var(--text-main);
            -webkit-font-smoothing: antialiased;
        }
        
        /* Premium Top Nav */
        .top-nav { 
            background: linear-gradient(135deg, #0f172a 0%, #111c38 55%, #172554 100%);
            color: white; 
            padding: 0 40px; 
            height: 70px;
            display: flex; 
            align-items: center; 
            justify-content: space-between; 
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 18px 35px -20px rgba(15, 23, 42, 0.95);
            border-bottom: 1px solid rgba(148, 163, 184, 0.14);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 800;
            font-size: 20px;
            letter-spacing: -0.025em;
        }

        .nav-links { display: flex; height: 100%; margin-left: 40px; }
        
        .nav-btn { 
            display: flex;
            align-items: center;
            padding: 0 24px; 
            color: #94a3b8; 
            cursor: pointer; 
            text-decoration: none; 
            font-size: 14px; 
            font-weight: 600;
            transition: all 0.2s;
            border-bottom: 3px solid transparent;
        }

        .nav-btn:hover { color: white; background: rgba(255,255,255,0.07); }
        .nav-btn.active { 
            color: white; 
            border-bottom: 3px solid var(--primary);
            background: linear-gradient(to bottom, transparent, rgba(37, 99, 235, 0.16));
        }
        
        .main { padding: 32px 40px; max-width: 1600px; margin: 0 auto; }
        
        /* Dashboard Summary Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,255,255,0.86));
            backdrop-filter: blur(10px);
            padding: 22px;
            border-radius: 20px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 20px 45px -32px rgba(15, 23, 42, 0.45);
        }
        .stat-label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-value { font-size: 24px; font-weight: 800; margin-top: 8px; letter-spacing: -0.03em; }

        /* Control Grid for Analysis Buttons */
        .control-grid { /* 4 equal columns: V1 V2 V3 Sector */
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 32px;
        }
        .control-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,255,255,0.88));
            backdrop-filter: blur(12px);
            padding: 24px;
            border-radius: 24px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            text-align: center;
            box-shadow: 0 28px 50px -38px rgba(15, 23, 42, 0.42);
        }
        .control-card h3 { margin: 0 0 16px 0; font-size: 16px; font-weight: 800; color: #1e293b; letter-spacing: -0.02em; }
        .btn-stack { display: flex; flex-direction: column; gap: 10px; }
        
        .btn-run {
            width: 100%;
            padding: 14px 12px;
            border: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.22s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            color: white;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), 0 14px 24px -18px rgba(15, 23, 42, 0.9);
        }
        .btn-v1 { background: linear-gradient(135deg, #64748b, #475569); }
        .btn-v2 { background: linear-gradient(135deg, #334155, #0f172a); }
        .btn-v3 { background: linear-gradient(135deg, #3b82f6, #1d4ed8); }
        .btn-run:hover { transform: translateY(-2px); filter: brightness(1.06); }
        .btn-run:disabled {
            cursor: not-allowed;
            opacity: 0.5;
            transform: none !important;
            filter: grayscale(0.2);
            box-shadow: none;
        }

        .run-lock-banner {
            margin-bottom: 20px;
            padding: 14px 18px;
            border-radius: 16px;
            border: 1px solid #bfdbfe;
            background: linear-gradient(90deg, rgba(219, 234, 254, 0.88), rgba(248, 250, 252, 0.96));
            color: #1e3a8a;
            font-size: 14px;
            font-weight: 700;
            display: none;
        }
        .run-lock-banner.visible {
            display: block;
        }

        .progress-panel {
            margin-top: 14px;
            padding: 14px;
            border-radius: 18px;
            background: linear-gradient(180deg, #fbfdff, #f3f7fc);
            border: 1px solid rgba(148, 163, 184, 0.18);
            text-align: left;
        }
        .progress-label {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .progress-copy {
            font-size: 13px;
            font-weight: 600;
            color: #334155;
            margin-bottom: 8px;
            min-height: 18px;
        }
        .progress-track {
            display: none;   /* hidden by default; JS shows it only when running/complete */
            width: 100%;
            height: 12px;
            border-radius: 999px;
            background: #dbe4f1;
            overflow: hidden;
        }
        .progress-fill {
            width: 0%;
            height: 100%;
            background: linear-gradient(90deg, #34d399, #16a34a);
            transition: width 0.35s ease;
        }
        .progress-meta {
            margin-top: 8px;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            gap: 8px;
        }

        /* Live terminal log box */
        .log-box {
            margin-top: 10px;
            background: #0f172a;
            border-radius: 10px;
            padding: 8px 10px;
            max-height: 110px;
            overflow-y: auto;
            display: none;           /* hidden when idle */
            font-family: 'Menlo', 'Consolas', monospace;
            font-size: 11px;
            line-height: 1.6;
            color: #94a3b8;
        }
        .log-box.active { display: block; }
        .log-line { white-space: pre-wrap; word-break: break-all; }
        .log-line:last-child { color: #34d399; }  /* last line highlighted green */

        /* Modern Card Styling */
        .card { 
            background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(255,255,255,0.88)); 
            backdrop-filter: blur(12px);
            padding: 32px; 
            border-radius: 24px; 
            box-shadow: 0 28px 55px -40px rgba(15, 23, 42, 0.46);
            border: 1px solid rgba(148, 163, 184, 0.18); 
        }

        .header-flex {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
        }

        h1 { font-size: 24px; font-weight: 800; margin: 0; color: var(--text-main); letter-spacing: -0.025em; }
        
        .positive { color: var(--success) !important; }
        .negative { color: var(--danger) !important; }
        
        .badge {
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .badge-live { background: #ecfdf5; color: #059669; border: 1px solid #d1fae5; box-shadow: inset 0 1px 0 rgba(255,255,255,0.8); }

        .btn-primary {
            background: var(--primary);
            color: white;
            padding: 10px 18px;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
            white-space: nowrap;
        }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 15px rgba(37, 99, 235, 0.3); }

        .run-group {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        /* DataTables Custom Polish */
        table.dataTable { border: none !important; margin: 20px 0 !important; }
        table.dataTable thead th { 
            background: #f8fbff !important; 
            color: var(--text-muted) !important; 
            font-weight: 700 !important;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.1em;
            padding: 18px 16px !important;
            border-bottom: 2px solid var(--border) !important;
            text-align: left !important;
            background-image: none !important;
            background-repeat: no-repeat !important;
        }
        
        /* Show only one arrow for sorting */
        table.dataTable thead th.sorting:before, 
        table.dataTable thead th.sorting:after,
        table.dataTable thead th.sorting_asc:before,
        table.dataTable thead th.sorting_asc:after,
        table.dataTable thead th.sorting_desc:before,
        table.dataTable thead th.sorting_desc:after { display: none !important; }
        table.dataTable thead th.sorting,
        table.dataTable thead th.sorting_asc,
        table.dataTable thead th.sorting_desc {
            background-image: none !important;
        }
        
        table.dataTable thead th.sorting_asc::after { content: " ↑"; color: var(--primary); font-size: 14px; }
        table.dataTable thead th.sorting_desc::after { content: " ↓"; color: var(--primary); font-size: 14px; }

        table.dataTable tbody td { 
            padding: 16px !important; 
            border-bottom: 1px solid #eef2f7 !important;
            font-size: 14px;
            font-weight: 500;
        }
        table.dataTable tbody tr:hover { background-color: #f7faff !important; cursor: pointer; }

        iframe { 
            width: 100%; 
            height: calc(100vh - 130px); 
            border: none; 
            border-radius: 24px; 
            background: white; 
            box-shadow: 0 30px 55px -42px rgba(15, 23, 42, 0.5);
        }

        .symbol-tag {
            background: linear-gradient(180deg, #eef4ff, #e0ecff);
            color: var(--primary);
            padding: 6px 10px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 13px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
        }
        .holdings-tabs {
            display: inline-flex;
            gap: 10px;
            padding: 6px;
            border-radius: 16px;
            background: #edf4ff;
            border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .holdings-tab {
            border: none;
            background: transparent;
            color: #475569;
            padding: 10px 16px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .holdings-tab.active {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: white;
            box-shadow: 0 12px 24px -18px rgba(37, 99, 235, 0.9);
        }
        .holdings-panel { display: none; }
        .holdings-panel.active { display: block; }
        .mini-summary {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 16px;
            margin-bottom: 8px;
        }
        .mini-chip {
            padding: 8px 12px;
            border-radius: 999px;
            background: #f8fbff;
            border: 1px solid rgba(148, 163, 184, 0.18);
            color: #64748b;
            font-size: 12px;
            font-weight: 700;
        }
        .empty-state {
            padding: 20px;
            border-radius: 18px;
            background: #f8fbff;
            border: 1px dashed rgba(148, 163, 184, 0.35);
            color: #64748b;
            font-weight: 600;
            margin-top: 18px;
        }
    </style>
</head>
<body>
    <nav class="top-nav">
        <div style="display: flex; align-items: center;">
            <div class="brand">
                <div style="background: var(--primary); width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white;">📈</div>
                <span>TERMINAL v4</span>
            </div>
            <div class="nav-links">
                <a href="/" class="nav-btn {{ 'active' if current_tab == 'portfolio' else '' }}">Portfolio</a>
                <a href="/report/v1" target="view_frame" class="nav-btn">V1 Core</a>
                <a href="/report/v2" target="view_frame" class="nav-btn">V2 Alpha</a>
                <a href="/report/v3" target="view_frame" class="nav-btn">V3 Ultimate</a>
                <a href="/sector" target="view_frame" class="nav-btn">📊 Sectors</a>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 24px;">
            <div id="clock" style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #94a3b8; font-size: 14px;">{{ now.strftime('%H:%M:%S') }}</div>
            <div class="badge badge-live">● System Active</div>
        </div>
    </nav>
    
    <div class="main">
        <div id="portfolio-view">
            <div class="run-lock-banner" id="run-lock-banner">Analysis running. All run buttons are temporarily disabled.</div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Average P&L</div>
                    <div class="stat-value {{ 'positive' if avg_pl > 0 else 'negative' }}">
                        {{ '+' if avg_pl > 0 }}{{ avg_pl }}%
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Day Change</div>
                    <div class="stat-value {{ 'positive' if avg_day > 0 else 'negative' }}">
                        {{ '+' if avg_day > 0 }}{{ avg_day }}%
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Account Health</div>
                    <div class="stat-value" style="color: var(--primary);">EXCELLENT</div>
                </div>
            </div>

            <div class="control-grid">
                <!-- V1 Controls -->
                <div class="control-card">
                    <h3>⚡ V1 CORE SCOUT</h3>
                    <div class="btn-stack">
                        <form action="/run_v1/0" method="POST"><button type="submit" class="btn-run btn-v1">10k Cap</button></form>
                        <form action="/run_v1/1" method="POST"><button type="submit" class="btn-run btn-v1">20k Cap</button></form>
                        <form action="/run_v1/2" method="POST"><button type="submit" class="btn-run btn-v1" style="background:#1e293b">Nifty 500</button></form>
                    </div>
                    <div class="progress-panel" id="panel-v1">
                        <div class="progress-label">Run Status</div>
                        <div class="progress-copy" id="copy-v1">Idle</div>
                        <div class="progress-track"><div class="progress-fill" id="fill-v1"></div></div>
                        <div class="progress-meta">
                            <span id="pct-v1">0%</span>
                            <span id="time-v1">No recent run</span>
                        </div>
                        <div class="log-box" id="log-v1"></div>
                    </div>
                </div>
                <!-- V2 Controls -->
                <div class="control-card">
                    <h3>🔍 V2 ALPHA TRACKER</h3>
                    <div class="btn-stack">
                        <form action="/run_v2/0" method="POST"><button type="submit" class="btn-run btn-v2">10k Cap</button></form>
                        <form action="/run_v2/1" method="POST"><button type="submit" class="btn-run btn-v2">20k Cap</button></form>
                        <form action="/run_v2/2" method="POST"><button type="submit" class="btn-run btn-v2" style="background:#0f172a">Nifty 500</button></form>
                    </div>
                    <div class="progress-panel" id="panel-v2">
                        <div class="progress-label">Run Status</div>
                        <div class="progress-copy" id="copy-v2">Idle</div>
                        <div class="progress-track"><div class="progress-fill" id="fill-v2"></div></div>
                        <div class="progress-meta">
                            <span id="pct-v2">0%</span>
                            <span id="time-v2">No recent run</span>
                        </div>
                        <div class="log-box" id="log-v2"></div>
                    </div>
                </div>
                <!-- V3 Controls -->
                <div class="control-card">
                    <h3>🚀 V3 ULTIMATE BOT</h3>
                    <div class="btn-stack">
                        <form action="/run_v3/0" method="POST"><button type="submit" class="btn-run btn-v3">10k Cap</button></form>
                        <form action="/run_v3/1" method="POST"><button type="submit" class="btn-run btn-v3">20k Cap</button></form>
                        <form action="/run_v3/2" method="POST"><button type="submit" class="btn-run btn-v3" style="background:#1d4ed8">Nifty 500</button></form>
                    </div>
                    <div class="progress-panel" id="panel-v3">
                        <div class="progress-label">Run Status</div>
                        <div class="progress-copy" id="copy-v3">Idle</div>
                        <div class="progress-track"><div class="progress-fill" id="fill-v3"></div></div>
                        <div class="progress-meta">
                            <span id="pct-v3">0%</span>
                            <span id="time-v3">No recent run</span>
                        </div>
                        <div class="log-box" id="log-v3"></div>
                    </div>
                </div>

                <!-- Sector Tracker -->
                <div class="control-card">
                    <h3>📊 SECTOR TRACKER</h3>
                    <div class="btn-stack">
                        <form action="/run_sector" method="POST">
                            <button type="submit" class="btn-run" style="background:#0f766e">Run EOD Report</button>
                        </form>
                        <a href="/sector" target="view_frame" style="display:block;text-align:center;margin-top:8px;padding:10px;background:#134e4a;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">
                            📂 Open Latest Report
                        </a>
                    </div>
                    <div class="progress-panel" id="panel-sector">
                        <div class="progress-label">Run Status</div>
                        <div class="progress-copy" id="copy-sector">Idle</div>
                        <div class="progress-track"><div class="progress-fill" id="fill-sector" style="background:#0f766e"></div></div>
                        <div class="progress-meta">
                            <span id="pct-sector">0%</span>
                            <span id="time-sector">No recent run</span>
                        </div>
                        <div class="log-box" id="log-sector"></div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="header-flex">
                    <div>
                        <h1>Live Holdings</h1>
                        <p style="color: var(--text-muted); margin: 6px 0 0 0; font-size: 14px; font-weight: 500;">Last Sync: {{ now.strftime('%H:%M:%S') }}</p>
                    </div>
                    <div class="holdings-tabs">
                        {% for portfolio in portfolios %}
                        <button type="button" class="holdings-tab {{ 'active' if loop.first else '' }}" data-target="{{ portfolio.key }}">{{ portfolio.label }}</button>
                        {% endfor %}
                    </div>
                </div>

                {% for portfolio in portfolios %}
                <div class="holdings-panel {{ 'active' if loop.first else '' }}" id="panel-{{ portfolio.key }}">
                    <div class="mini-summary">
                        <div class="mini-chip">{{ portfolio.summary.count }} stocks</div>
                        <div class="mini-chip">Avg Day {{ '+' if portfolio.summary.avg_day > 0 }}{{ portfolio.summary.avg_day }}%</div>
                        <div class="mini-chip">Avg P&amp;L {{ '+' if portfolio.summary.avg_pl > 0 }}{{ portfolio.summary.avg_pl }}%</div>
                    </div>

                    {% if portfolio.rows %}
                    <table id="{{ portfolio.table_id }}" class="display nowrap holdings-table" style="width:100%">
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Avg Cost</th>
                                <th>LTP</th>
                                <th>Day %</th>
                                <th>Total P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for stock in portfolio.rows %}
                            <tr>
                                <td><span class="symbol-tag">{{ stock.symbol }}</span></td>
                                <td style="color: var(--text-muted);">₹{{ stock.fixed_value }}</td>
                                <td style="font-weight: 700;">₹{{ stock.cmp }}</td>
                                <td class="{{ 'positive' if stock.day_change > 0 else 'negative' }}">
                                    {{ '+' if stock.day_change > 0 }}{{ stock.day_change }}%
                                </td>
                                <td class="{{ 'positive' if stock.pl_percent > 0 else 'negative' }}" data-order="{{ stock.pl_percent }}" style="font-weight: 800;">
                                    {{ '+' if stock.pl_percent > 0 }}{{ stock.pl_percent }}%
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <div class="empty-state">{{ portfolio.label }} is empty. Add entries to the matching JSON file to populate this tab.</div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        
        <iframe name="view_frame" id="view_frame" style="display:none;"></iframe>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
    <script>
        const selectedRun = {{ selected_run|tojson }};
        const taskChoices = ['0', '1', '2'];
        const portfolioTableIds = {{ portfolio_table_ids|tojson }};
        const versionTasks = {
            v1: taskChoices.map(choice => `v1_${choice}`),
            v2: taskChoices.map(choice => `v2_${choice}`),
            v3: taskChoices.map(choice => `v3_${choice}`),
            sector: []    // sector tasks are matched by prefix, not fixed IDs
        };
        const knownTaskIds = new Set(Object.values(versionTasks).flat());

        const STALE_MINUTES = 30;

        // Returns true if HH:MM:SS timestamp is older than STALE_MINUTES
        function isStale(timeStr) {
            if (!timeStr) return true;
            try {
                const now  = new Date();
                const [h, m, s] = timeStr.split(':').map(Number);
                const t    = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, s);
                let diff   = (now - t) / 1000;
                if (diff < 0) diff += 86400;   // midnight rollover
                return diff > STALE_MINUTES * 60;
            } catch (e) { return true; }
        }

        function formatStatus(status, taskId) {
            if (status === 'completed')   return '✓ ANALYSIS COMPLETE';
            if (status === 'error')       return '✗ Run failed / interrupted';
            if (status === 'downloading') return '⏬ Fetching market data...';
            if (status === 'downloaded')  return '✓ Data ready — starting analysis';
            if (status === 'analyzing')   return '🔍 Calculating momentum scores...';
            if (status === 'running')     return '⚙️ Running...';
            return 'Idle';
        }

        function prettifyTaskId(taskId) {
            if (!taskId) return '';
            if (taskId.startsWith('sector')) return 'Sector Tracker';
            const parts  = taskId.split('_');
            const labels = { '0': '10k Cap', '1': '20k Cap', '2': 'Nifty 500' };
            return `${parts[0].toUpperCase()} · ${labels[parts[1]] || parts[1]}`;
        }

        function pickLatestTask(progressData, versionKey) {
            let tasks;
            if (versionKey === 'sector') {
                // Match any key that starts with "sector"
                tasks = Object.entries(progressData)
                    .filter(([id]) => id.startsWith('sector'))
                    .map(([taskId, data]) => ({ taskId, data }));
            } else {
                tasks = (versionTasks[versionKey] || [])
                    .map(taskId => ({ taskId, data: progressData[taskId] }))
                    .filter(item => item.data);
            }

            if (!tasks.length) return null;

            if (selectedRun && selectedRun.startsWith(versionKey + '_')) {
                const sel = tasks.find(item => item.taskId === selectedRun);
                if (sel) return sel;
            }

            tasks.sort((a, b) => (a.data.time || '').localeCompare(b.data.time || ''));
            return tasks[tasks.length - 1];
        }

        function updateProgressCard(versionKey, task) {
            const copyEl  = document.getElementById(`copy-${versionKey}`);
            const fillEl  = document.getElementById(`fill-${versionKey}`);
            const pctEl   = document.getElementById(`pct-${versionKey}`);
            const timeEl  = document.getElementById(`time-${versionKey}`);
            const logEl   = document.getElementById(`log-${versionKey}`);
            const trackEl = fillEl ? fillEl.parentElement : null;

            if (!task) {
                copyEl.innerText = 'Idle';
                if (trackEl) trackEl.style.display = 'none';
                pctEl.innerText = '0%';
                timeEl.innerText = 'No recent run';
                if (logEl) { logEl.innerHTML = ''; logEl.classList.remove('active'); }
                return;
            }

            const data    = task.data || {};
            const status  = data.status || 'running';
            const taskTime = data.time || '';

            // Treat stale "running" tasks as interrupted — don't show fake progress
            const effectiveStatus = (
                ['downloading','analyzing','running'].includes(status) && isStale(taskTime)
            ) ? 'error' : status;

            const current = Number(data.current || 0);
            const total   = Number(data.total   || 0);
            const pct = effectiveStatus === 'completed'
                ? 100
                : (total > 0 ? Math.max(0, Math.min(99, Math.round((current / total) * 100))) : 0);

            // Show bar only when actively running or completed
            const showBar = ['downloading','analyzing','running','completed'].includes(effectiveStatus);
            if (trackEl) trackEl.style.display = showBar ? '' : 'none';

            copyEl.innerText  = formatStatus(effectiveStatus, task.taskId);
            if (fillEl) fillEl.style.width = `${pct}%`;
            pctEl.innerText   = showBar ? `${pct}%` : '';

            if (effectiveStatus === 'error') {
                const msg = data.error || 'Process interrupted';
                timeEl.innerText = `✗ ${msg.replace('Process interrupted (stale)', 'Interrupted — click to re-run')}`;
            } else if (effectiveStatus === 'completed') {
                const label = versionKey === 'sector' ? 'Sectors' : versionKey.toUpperCase();
                timeEl.innerText = `✓ Updated ${taskTime} · Open ${label} tab`;
            } else {
                // Active: show step counts
                const stepInfo = total > 0 ? ` (${current}/${total})` : '';
                timeEl.innerText = `Last update ${taskTime}${stepInfo}`;
            }

            // ── Live terminal log ──
            if (logEl) {
                const logs = data.logs || [];
                const isActive = ['downloading','analyzing','running'].includes(effectiveStatus)
                              && !isStale(taskTime);
                if (logs.length > 0 && (isActive || effectiveStatus === 'error')) {
                    logEl.classList.add('active');
                    logEl.innerHTML = logs
                        .map(l => `<div class="log-line">${l.replace(/</g,'&lt;')}</div>`)
                        .join('');
                    // Auto-scroll to bottom
                    logEl.scrollTop = logEl.scrollHeight;
                } else {
                    logEl.innerHTML = '';
                    logEl.classList.remove('active');
                }
            }
        }

        function getActiveTask(progressData) {
            const activeTasks = Object.entries(progressData)
                .map(([taskId, data]) => ({ taskId, data: data || {} }))
                // Include v1/v2/v3 known IDs + any sector_ prefixed task
                .filter(item => knownTaskIds.has(item.taskId) || item.taskId.startsWith('sector'))
                .filter(item => ['downloading', 'analyzing', 'running'].includes(item.data.status))
                // Only count as active if NOT stale (otherwise buttons stay locked forever)
                .filter(item => !isStale(item.data.time || ''));

            if (!activeTasks.length) return null;

            if (selectedRun) {
                const selectedTask = activeTasks.find(item => item.taskId === selectedRun);
                if (selectedTask) return selectedTask;
            }

            activeTasks.sort((a, b) => (a.data.time || '').localeCompare(b.data.time || ''));
            return activeTasks[activeTasks.length - 1];
        }

        function setRunButtonsDisabled(disabled) {
            document.querySelectorAll('.btn-run').forEach(button => {
                button.disabled = disabled;
            });
        }

        function updateRunLockBanner(activeTask) {
            const banner = document.getElementById('run-lock-banner');
            if (!banner) return;

            if (activeTask) {
                banner.classList.add('visible');
                banner.innerText = `${prettifyTaskId(activeTask.taskId)} is running. All run buttons are temporarily disabled.`;
                setRunButtonsDisabled(true);
            } else {
                banner.classList.remove('visible');
                banner.innerText = 'Analysis running. All run buttons are temporarily disabled.';
                setRunButtonsDisabled(false);
            }
        }

        async function refreshProgress() {
            try {
                const response = await fetch('/api/progress', { cache: 'no-store' });
                const progressData = await response.json();
                updateRunLockBanner(getActiveTask(progressData));
                ['v1', 'v2', 'v3'].forEach(versionKey => {
                    updateProgressCard(versionKey, pickLatestTask(progressData, versionKey));
                });
                // Sector tracker progress (task keys start with "sector_v2_")
                updateProgressCard('sector', pickLatestTask(progressData, 'sector'));
            } catch (error) {
                console.error('Progress refresh failed', error);
            }
        }

        $(document).ready( function () {
            portfolioTableIds.forEach((tableId) => {
                const selector = `#${tableId}`;
                if (!$(selector).length) return;
                $(selector).DataTable({
                    "pageLength": 50,
                    "order": [[4, "desc"]],
                    "dom": '<"header-flex"f>rt<"footer-info"p>',
                    "language": {
                        "search": "",
                        "searchPlaceholder": "Filter symbols..."
                    }
                });
            });

            $('.holdings-tab').on('click', function() {
                const target = $(this).data('target');
                $('.holdings-tab').removeClass('active');
                $(this).addClass('active');
                $('.holdings-panel').removeClass('active');
                $(`#panel-${target}`).addClass('active');
            });

            refreshProgress();
            setInterval(refreshProgress, 3000);

            setInterval(() => {
                const now = new Date();
                const clockEl = document.getElementById('clock');
                if (clockEl) clockEl.innerText = now.toTimeString().split(' ')[0];
            }, 1000);
        });

        function showPortfolio() {
            $('#portfolio-view').show();
            $('#view_frame').hide();
            $('.nav-btn').removeClass('active');
            $('.nav-btn:contains("Portfolio")').addClass('active');
        }

        function showReport() {
            $('#portfolio-view').hide();
            $('#view_frame').show();
            $('.nav-btn').removeClass('active');
        }

        $('.nav-btn').click(function() {
            if($(this).text().includes("Portfolio")) {
                showPortfolio();
            } else {
                showReport();
                $(this).addClass('active');
            }
        });
    </script>
</body>
</html>
"""

# ── Optional: start Telegram bot in background thread if token is present ─────
def _start_telegram_bot():
    """Run master_bot in a daemon thread so gunicorn stays the main process."""
    import threading, importlib.util, pathlib
    bot_path = pathlib.Path(__file__).parent / "master_bot.py"
    if not bot_path.exists():
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ℹ️  TELEGRAM_BOT_TOKEN not set — Telegram bot disabled.")
        return
    try:
        import telebot
        from apscheduler.schedulers.background import BackgroundScheduler
        import datetime as _dt

        bot = telebot.TeleBot(token)
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        def _scheduled():
            if not chat_id:
                return
            try:
                symbols = [s['symbol'] for p in [("core",), ("momentum2",)] for s in engine.read_portfolio(p[0])]
                quotes = engine.get_market_quote(symbols)
                lines = [f"{sym}: {quotes.get(sym, {}).get('ltp', 'N/A')}" for sym in symbols[:10]]
                bot.send_message(chat_id, "📊 Scheduled update:\n" + "\n".join(lines))
            except Exception as e:
                print(f"Bot scheduled update error: {e}")

        sched = BackgroundScheduler()
        sched.add_job(_scheduled, 'cron', hour=9,  minute=0,  timezone='Asia/Kolkata')
        sched.add_job(_scheduled, 'cron', hour=15, minute=15, timezone='Asia/Kolkata')
        sched.start()

        def _poll():
            print("✅ Telegram bot polling started (background thread).")
            bot.infinity_polling(none_stop=True, timeout=30)

        t = threading.Thread(target=_poll, daemon=True, name="telegram-bot")
        t.start()
    except Exception as e:
        print(f"⚠️  Could not start Telegram bot: {e}")

_start_telegram_bot()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
