import os
import json
import subprocess
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory
from universal_engine import engine

app = Flask(__name__)

# Paths to frozen assets in the root folder
ROOT_DIR = os.path.join(os.path.dirname(__file__), '..')
STOCKS_FILE = os.path.join(ROOT_DIR, 'portfolio_stocks.json')
REPORTS = {
    "v1": os.path.join(ROOT_DIR, 'momentum_report.html'),
    "v2": os.path.join(ROOT_DIR, 'momentum_report_v2.html'),
    "v3": os.path.join(ROOT_DIR, 'momentum_report_v3.html')
}

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
        cmp = quotes.get(symbol, "N/A")
        
        pl_percent = 0.0
        if isinstance(cmp, (int, float)):
            pl_percent = round(((cmp - fixed_val) / fixed_val) * 100, 2)
            
        results.append({
            "symbol": symbol,
            "fixed_value": fixed_val,
            "cmp": cmp,
            "pl_percent": pl_percent
        })
    return results

@app.route("/")
def index():
    portfolio = get_portfolio_data()
    return render_template_string(HTML_TEMPLATE, portfolio=portfolio, current_tab='portfolio', now=datetime.now())

@app.route("/report/<version>")
def view_report(version):
    # This serves the actual frozen HTML reports
    filename = f"momentum_report_{version}.html" if version != "v1" else "momentum_report.html"
    return send_from_directory(ROOT_DIR, filename)

@app.route("/run_v3", methods=["POST"])
def run_v3():
    # Execute the frozen V3 script in the background from the ROOT directory
    v3_path = os.path.join(ROOT_DIR, 'momentum_tracker_v3.py')
    
    # We use 'cwd=ROOT_DIR' so the script can find your CSV files and buffett.py
    subprocess.Popen(["python3", v3_path], cwd=ROOT_DIR)
    
    return redirect(url_for('index'))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Master Control Center</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 0; background: #f0f2f5; }
        
        /* Top Navigation Styling */
        .top-nav { background: #2d3436; color: white; padding: 10px 30px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .nav-links { display: flex; gap: 15px; }
        .nav-btn { padding: 8px 16px; background: #3d4648; border: none; color: white; cursor: pointer; border-radius: 4px; text-decoration: none; font-size: 14px; transition: 0.3s; }
        .nav-btn:hover { background: #0984e3; }
        .nav-btn.active { background: #0984e3; font-weight: bold; }
        
        .main { padding: 20px; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; }
        h1 { color: #2d3436; margin-top: 0; font-size: 22px; }
        
        /* Table Colors */
        .positive { color: #27ae60 !important; font-weight: bold; }
        .negative { color: #d63031 !important; font-weight: bold; }
        
        .action-bar { margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #eee; }
        iframe { width: 100%; height: calc(100vh - 100px); border: none; border-radius: 8px; background: white; margin-top: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        
        /* DataTables Customization */
        .dataTables_wrapper { margin-top: 20px; }
        table.dataTable thead th { background: #f8f9fa; border-bottom: 2px solid #dee2e6; color: #444; }
    </style>
</head>
<body>
    <div class="top-nav">
        <h2 style="margin:0; font-size: 18px;">🚀 Master Dashboard</h2>
        <div class="nav-links">
            <a href="/" class="nav-btn {{ 'active' if current_tab == 'portfolio' else '' }}">📊 Live Portfolio</a>
            <a href="/report/v1" target="view_frame" class="nav-btn">📈 V1 Momentum</a>
            <a href="/report/v2" target="view_frame" class="nav-btn">🔥 V2 Strong</a>
            <a href="/report/v3" target="view_frame" class="nav-btn">💎 V3 Ultimate</a>
        </div>
        <div id="clock" style="font-size: 14px; color: #ccc;">{{ now.strftime('%Y-%m-%d %H:%M:%S') }}</div>
    </div>
    
    <div class="main">
        <div id="content-area">
            <div id="portfolio-view" class="card">
                <div style="display:flex; justify-content: space-between; align-items: center;">
                    <h1>Live Portfolio (Free Engine)</h1>
                    <form action="/run_v3" method="POST" style="margin:0;">
                        <button type="submit" style="background:#0984e3; color:white; padding:10px 20px; border:none; border-radius:6px; cursor:pointer; font-weight: bold;">
                            🚀 Run V3 Analysis
                        </button>
                    </form>
                </div>

                <table id="portfolioTable" class="display nowrap" style="width:100%">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Fixed Value</th>
                            <th>Live CMP</th>
                            <th>P/L %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for stock in portfolio %}
                        <tr>
                            <td><strong>{{ stock.symbol }}</strong></td>
                            <td>{{ stock.fixed_value }}</td>
                            <td>{{ stock.cmp }}</td>
                            <td class="{{ 'positive' if stock.pl_percent > 0 else 'negative' }}" data-order="{{ stock.pl_percent }}">
                                {{ stock.pl_percent }}%
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                
                <div class="action-bar">
                    <span style="font-size: 13px; color: #666;">ℹ️ Live prices updated via Universal Engine (0.5s throttle)</span>
                    <span style="font-weight: bold; color: #2d3436;">Last Refresh: {{ now.strftime('%H:%M:%S') }}</span>
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
                "order": [[3, "desc"]], // Default sort by P/L % descending
                "dom": '<"top"f>rt<"bottom"lp><"clear">'
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
