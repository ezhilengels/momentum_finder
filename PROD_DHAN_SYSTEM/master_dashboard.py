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

# Initialize progress file
if not os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({}, f)

STOCKS_FILE = os.path.join(ROOT_DIR, 'portfolio_stocks.json')

def get_tracked_stocks():
    if not os.path.exists(STOCKS_FILE): return []
    with open(STOCKS_FILE, "r") as f:
        try: return json.load(f)
        except: return []

def read_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    with open(PROGRESS_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def get_portfolio_data():
    """Fetch live data using Universal Engine (yfinance)"""
    stocks = get_tracked_stocks()
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

@app.route("/")
def index():
    try:
        portfolio = get_portfolio_data()
        
        # Calculate summary stats
        total_pl = [s['pl_percent'] for s in portfolio if isinstance(s['pl_percent'], (int, float))]
        avg_pl = round(sum(total_pl) / len(total_pl), 2) if total_pl else 0
        
        total_day = [s['day_change'] for s in portfolio if isinstance(s['day_change'], (int, float))]
        avg_day = round(sum(total_day) / len(total_day), 2) if total_day else 0

        return render_template_string(HTML_TEMPLATE, 
                                     portfolio=portfolio, 
                                     avg_pl=avg_pl, 
                                     avg_day=avg_day,
                                     current_tab='portfolio', 
                                     now=datetime.now(),
                                     selected_run=request.args.get('run', ''))
    except Exception as e:
        return f"<html><body><h1>⚠️ Dashboard Error</h1><p>{str(e)}</p><a href='/'>Try Refreshing</a></body></html>"

@app.route("/report/<version>")
def view_report(version):
    filename = f"momentum_report_{version}.html" if version != "v1" else "momentum_report.html"
    return send_from_directory(ROOT_DIR, filename)

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
        .control-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
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
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="header-flex">
                    <div>
                        <h1>Live Holdings</h1>
                        <p style="color: var(--text-muted); margin: 6px 0 0 0; font-size: 14px; font-weight: 500;">Last Sync: {{ now.strftime('%H:%M:%S') }}</p>
                    </div>
                </div>

                <table id="portfolioTable" class="display nowrap" style="width:100%">
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
                        {% for stock in portfolio %}
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
            </div>
        </div>
        
        <iframe name="view_frame" id="view_frame" style="display:none;"></iframe>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
    <script>
        const selectedRun = {{ selected_run|tojson }};
        const taskChoices = ['0', '1', '2'];
        const versionTasks = {
            v1: taskChoices.map(choice => `v1_${choice}`),
            v2: taskChoices.map(choice => `v2_${choice}`),
            v3: taskChoices.map(choice => `v3_${choice}`)
        };
        const knownTaskIds = new Set(Object.values(versionTasks).flat());

        function formatStatus(status) {
            if (status === 'completed') return '✓ ANALYSIS COMPLETE';
            if (status === 'downloading') return 'Fetching market data...';
            if (status === 'analyzing') return 'Analysis in progress...';
            if (status === 'error') return 'Run failed';
            return 'Idle';
        }

        function prettifyTaskId(taskId) {
            if (!taskId) return '';
            const [version, choice] = taskId.split('_');
            const labels = { '0': '10k Cap', '1': '20k Cap', '2': 'Nifty 500' };
            return `${version.toUpperCase()} · ${labels[choice] || choice}`;
        }

        function pickLatestTask(progressData, versionKey) {
            const tasks = versionTasks[versionKey]
                .map(taskId => ({ taskId, data: progressData[taskId] }))
                .filter(item => item.data);

            if (!tasks.length) return null;

            if (selectedRun && selectedRun.startsWith(versionKey + '_')) {
                const selectedTask = tasks.find(item => item.taskId === selectedRun);
                if (selectedTask) return selectedTask;
            }

            tasks.sort((a, b) => (a.data.time || '').localeCompare(b.data.time || ''));
            return tasks[tasks.length - 1];
        }

        function updateProgressCard(versionKey, task) {
            const copyEl = document.getElementById(`copy-${versionKey}`);
            const fillEl = document.getElementById(`fill-${versionKey}`);
            const pctEl = document.getElementById(`pct-${versionKey}`);
            const timeEl = document.getElementById(`time-${versionKey}`);

            if (!task) {
                copyEl.innerText = 'Idle';
                fillEl.style.width = '0%';
                pctEl.innerText = '0%';
                timeEl.innerText = 'No recent run';
                return;
            }

            const data = task.data || {};
            const current = Number(data.current || 0);
            const total = Number(data.total || 0);
            const status = data.status || 'running';
            const pct = status === 'completed' ? 100 : (total > 0 ? Math.max(0, Math.min(100, Math.round((current / total) * 100))) : 0);

            copyEl.innerText = formatStatus(status);
            fillEl.style.width = `${pct}%`;
            pctEl.innerText = `${pct}%`;

            if (status === 'error' && data.error) {
                timeEl.innerText = data.error;
            } else if (status === 'completed') {
                const reportLabel = versionKey.toUpperCase();
                timeEl.innerText = `Updated ${data.time || '--'} · Open ${reportLabel} tab`;
            } else {
                timeEl.innerText = `Last update ${data.time || '--'}`;
            }
        }

        function getActiveTask(progressData) {
            const activeTasks = Object.entries(progressData)
                .map(([taskId, data]) => ({ taskId, data: data || {} }))
                .filter(item => knownTaskIds.has(item.taskId))
                .filter(item => ['downloading', 'analyzing', 'running'].includes(item.data.status));

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
            } catch (error) {
                console.error('Progress refresh failed', error);
            }
        }

        $(document).ready( function () {
            $('#portfolioTable').DataTable({
                "pageLength": 50,
                "order": [[4, "desc"]],
                "dom": '<"header-flex"f>rt<"footer-info"p>',
                "language": {
                    "search": "",
                    "searchPlaceholder": "Filter symbols..."
                }
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
