import os
import json
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory

# Ensure the current directory is in the path for imports
sys.path.append(os.path.dirname(__file__))
from universal_engine import engine

app = Flask(__name__)

# Paths to frozen assets in the root folder
ROOT_DIR = os.path.join(os.path.dirname(__file__), '..')
STOCKS_FILE = os.path.join(ROOT_DIR, 'portfolio_stocks.json')

def get_tracked_stocks():
    if not os.path.exists(STOCKS_FILE): return []
    with open(STOCKS_FILE, "r") as f:
        try: return json.load(f)
        except: return []

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
        return render_template_string(HTML_TEMPLATE, portfolio=portfolio, current_tab='portfolio', now=datetime.now())
    except Exception as e:
        return f"<html><body><h1>⚠️ Dashboard Error</h1><p>{str(e)}</p><a href='/'>Try Refreshing</a></body></html>"

@app.route("/report/<version>")
def view_report(version):
    filename = f"momentum_report_{version}.html" if version != "v1" else "momentum_report.html"
    return send_from_directory(ROOT_DIR, filename)

@app.route("/run_v3", methods=["POST"])
def run_v3():
    v3_path = os.path.join(ROOT_DIR, 'momentum_tracker_v3.py')
    subprocess.Popen(["python3", v3_path], cwd=ROOT_DIR)
    return redirect(url_for('index'))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Master Portfolio | Terminal</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #0066ff;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --success: #10b981;
            --danger: #ef4444;
            --border: #e2e8f0;
        }

        body { 
            font-family: 'Inter', sans-serif; 
            margin: 0; 
            background: var(--bg); 
            color: var(--text-main);
            -webkit-font-smoothing: antialiased;
        }
        
        /* Premium Top Nav */
        .top-nav { 
            background: #0f172a; 
            color: white; 
            padding: 0 40px; 
            height: 64px;
            display: flex; 
            align-items: center; 
            justify-content: space-between; 
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 700;
            font-size: 18px;
            letter-spacing: -0.5px;
        }

        .nav-links { display: flex; height: 100%; }
        
        .nav-btn { 
            display: flex;
            align-items: center;
            padding: 0 20px; 
            color: #94a3b8; 
            cursor: pointer; 
            text-decoration: none; 
            font-size: 14px; 
            font-weight: 500;
            transition: all 0.2s;
            border-bottom: 2px solid transparent;
        }

        .nav-btn:hover { color: white; background: rgba(255,255,255,0.05); }
        .nav-btn.active { 
            color: white; 
            border-bottom: 2px solid var(--primary);
            background: rgba(0, 102, 255, 0.1);
        }
        
        .main { padding: 32px 40px; }
        
        /* Modern Card Styling */
        .card { 
            background: var(--card-bg); 
            padding: 32px; 
            border-radius: 16px; 
            box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
            border: 1px solid var(--border); 
        }

        .header-flex {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 24px;
        }

        h1 { font-size: 24px; font-weight: 700; margin: 0; color: var(--text-main); letter-spacing: -0.5px; }
        
        /* P&L Colors */
        .positive { color: var(--success) !important; font-weight: 600; }
        .negative { color: var(--danger) !important; font-weight: 600; }
        
        .badge {
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-live { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }

        .btn-primary {
            background: var(--primary);
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.2s;
            box-shadow: 0 4px 6px -1px rgba(0, 102, 255, 0.2);
        }
        .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn-primary:active { transform: translateY(0); }

        /* DataTables Custom Polish */
        .dataTables_wrapper .dataTables_filter input {
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            margin-left: 12px;
            outline: none;
        }
        table.dataTable { border-collapse: collapse !important; border: none !important; }
        table.dataTable thead th { 
            background: #f1f5f9 !important; 
            color: var(--text-muted) !important; 
            font-weight: 600 !important;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
            padding: 16px !important;
            border: none !important;
            position: relative;
        }
        /* Remove default DataTables arrows and add custom clean ones */
        table.dataTable thead th.sorting:before, 
        table.dataTable thead th.sorting:after,
        table.dataTable thead th.sorting_asc:before,
        table.dataTable thead th.sorting_asc:after,
        table.dataTable thead th.sorting_desc:before,
        table.dataTable thead th.sorting_desc:after { display: none !important; }
        
        table.dataTable thead th.sorting { cursor: pointer; }
        table.dataTable thead th.sorting_asc { border-bottom: 2px solid var(--primary) !important; color: var(--primary) !important; }
        table.dataTable thead th.sorting_desc { border-bottom: 2px solid var(--primary) !important; color: var(--primary) !important; }

        table.dataTable tbody td { 
            padding: 16px !important; 
            border-bottom: 1px solid #f1f5f9 !important;
            font-size: 14px;
        }
        table.dataTable tbody tr:hover { background-color: #f8fafc !important; }

        iframe { 
            width: 100%; 
            height: calc(100vh - 120px); 
            border: none; 
            border-radius: 16px; 
            background: white; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .footer-info {
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <nav class="top-nav">
        <div class="brand">
            <span style="font-size: 24px;">📊</span>
            <span>PORTFOLIO TERMINAL</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-btn {{ 'active' if current_tab == 'portfolio' else '' }}">Live Portfolio</a>
            <a href="/report/v1" target="view_frame" class="nav-btn">V1 Momentum</a>
            <a href="/report/v2" target="view_frame" class="nav-btn">V2 Strong</a>
            <a href="/report/v3" target="view_frame" class="nav-btn">V3 Ultimate</a>
        </div>
        <div style="display: flex; align-items: center; gap: 16px;">
            <div id="clock" style="font-family: monospace; font-weight: 600; color: #94a3b8;">{{ now.strftime('%H:%M:%S') }}</div>
            <div class="badge badge-live">● System Live</div>
        </div>
    </nav>
    
    <div class="main">
        <div id="content-area">
            <div id="portfolio-view" class="card">
                <div class="header-flex">
                    <div>
                        <h1>Real-time Holdings</h1>
                        <p style="color: var(--text-muted); margin: 4px 0 0 0; font-size: 14px;">Tracking 1-day change and total portfolio P&L</p>
                    </div>
                    <form action="/run_v3" method="POST" style="margin:0;">
                        <button type="submit" class="btn-primary">
                            🚀 Run Global Analysis
                        </button>
                    </form>
                </div>

                <table id="portfolioTable" class="display nowrap" style="width:100%">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Avg Cost</th>
                            <th>Market Price</th>
                            <th>Day Change</th>
                            <th>Profit / Loss</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for stock in portfolio %}
                        <tr>
                            <td style="font-weight: 700; color: var(--primary);">{{ stock.symbol }}</td>
                            <td>{{ stock.fixed_value }}</td>
                            <td style="font-weight: 600;">{{ stock.cmp }}</td>
                            <td class="{{ 'positive' if stock.day_change > 0 else 'negative' }}">
                                {{ '+' if stock.day_change > 0 }}{{ stock.day_change }}%
                            </td>
                            <td class="{{ 'positive' if stock.pl_percent > 0 else 'negative' }}" data-order="{{ stock.pl_percent }}">
                                {{ '+' if stock.pl_percent > 0 }}{{ stock.pl_percent }}%
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                
                <div class="footer-info">
                    <span>Throttled Engine: 500ms delay per request for stability.</span>
                    <span>Last Refreshed: <strong>{{ now.strftime('%d %b, %H:%M') }}</strong></span>
                </div>
            </div>
            
            <iframe name="view_frame" id="view_frame" style="display:none;"></iframe>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
    <script>
        $(document).ready( function () {
            $('#portfolioTable').DataTable({
                "pageLength": 50,
                "order": [[4, "desc"]],
                "dom": '<"header-flex"f>rt<"footer-info"lp><"clear">',
                "language": {
                    "search": "",
                    "searchPlaceholder": "Search tickers..."
                }
            });
        });

        function showPortfolio() {
            document.getElementById('portfolio-view').style.display = 'block';
            document.getElementById('view_frame').style.display = 'none';
            $('.nav-btn').removeClass('active');
            $('.nav-btn:contains("Portfolio")').addClass('active');
        }

        function showReport() {
            document.getElementById('portfolio-view').style.display = 'none';
            document.getElementById('view_frame').style.display = 'block';
            $('.nav-btn').removeClass('active');
        }

        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if(btn.innerText.includes("Live Portfolio")) {
                    showPortfolio();
                } else {
                    showReport();
                    $(btn).addClass('active');
                }
            });
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(port=5001, debug=True)
