import json
import os
import yfinance as yf
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)
STOCKS_FILE = "portfolio_stocks.json"

def get_tracked_stocks():
    if not os.path.exists(STOCKS_FILE):
        return []
    with open(STOCKS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_stocks(stocks):
    with open(STOCKS_FILE, "w") as f:
        json.dump(stocks, f, indent=4)

def get_detailed_portfolio():
    stocks = get_tracked_stocks()
    if not stocks:
        return []
    
    symbols = [f"{s['symbol']}.NS" if not s['symbol'].endswith(".NS") else s['symbol'] for s in stocks]
    try:
        data = yf.download(symbols, period="1d", interval="1m", progress=False)['Close']
        if not data.empty:
            data = data.iloc[-1]
    except Exception as e:
        print(f"Error fetching data: {e}")
        data = None

    results = []
    for stock in stocks:
        symbol = stock['symbol']
        fixed_val = float(stock['fixed_value'])
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        
        cmp = "N/A"
        pl_percent = 0.0
        
        if data is not None:
            try:
                cmp_val = data[ticker_symbol] if len(symbols) > 1 else data
                if isinstance(cmp_val, (int, float)):
                    cmp = round(float(cmp_val), 2)
                    pl_percent = round(((cmp - fixed_val) / fixed_val) * 100, 2)
            except:
                pass

        results.append({
            "symbol": symbol,
            "fixed_value": fixed_val,
            "cmp": cmp,
            "pl_percent": pl_percent
        })
    return results

@app.route("/")
def index():
    portfolio = get_detailed_portfolio()
    discounted = [s for s in portfolio if isinstance(s['cmp'], (int, float)) and s['cmp'] < s['fixed_value']]
    rallying = [s for s in portfolio if isinstance(s['cmp'], (int, float)) and s['pl_percent'] > 5] # Rallying if >5% profit
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Portfolio Dashboard</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background-color: #f0f2f5; color: #333; }
            .container { max-width: 1000px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            h1 { text-align: center; color: #1a73e8; }
            .section { margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 20px; }
            .section h2 { color: #5f6368; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
            th { background-color: #f8f9fa; cursor: pointer; position: relative; }
            
            /* Show only one arrow for sorting */
            table.dataTable thead th.sorting:before, 
            table.dataTable thead th.sorting:after,
            table.dataTable thead th.sorting_asc:before,
            table.dataTable thead th.sorting_asc:after,
            table.dataTable thead th.sorting_desc:before,
            table.dataTable thead th.sorting_desc:after { display: none !important; }
            
            table.dataTable thead th.sorting_asc::after { content: " ↑"; }
            table.dataTable thead th.sorting_desc::after { content: " ↓"; }
            
            .positive { color: #28a745 !important; font-weight: bold; }
            .negative { color: #dc3545 !important; font-weight: bold; }
            .add-form { background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 30px; display: flex; gap: 10px; align-items: flex-end; justify-content: center; }
            .add-form div { display: flex; flex-direction: column; gap: 5px; }
            input { padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
            button { padding: 10px 20px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #1557b0; }
            .delete-btn { color: #dc3545; text-decoration: none; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Stock Portfolio Dashboard</h1>
            
            <form class="add-form" action="/add" method="POST">
                <div>
                    <label>Symbol (e.g., RELIANCE)</label>
                    <input type="text" name="symbol" required placeholder="RELIANCE">
                </div>
                <div>
                    <label>Fixed Value (Buy Price)</label>
                    <input type="number" step="0.01" name="fixed_value" required placeholder="2500.00">
                </div>
                <button type="submit">Add Stock</button>
            </form>

            <div class="section">
                <h2>All Tracked Stocks</h2>
                <table id="portfolioTable" class="display">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Fixed Value</th>
                            <th>Current Price</th>
                            <th>P/L %</th>
                            <th>Action</th>
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
                            <td><a href="/delete/{{ stock.symbol }}" class="delete-btn" onclick="return confirm('Delete {{ stock.symbol }}?')">Delete</a></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h2>Insights</h2>
                <div style="display: flex; gap: 20px;">
                    <div style="flex: 1; background: #fff9db; padding: 15px; border-radius: 8px;">
                        <h3>💰 Discounted Stocks (CMP < Fixed)</h3>
                        <ul>
                            {% for stock in discounted %}
                                <li><strong>{{ stock.symbol }}</strong>: {{ stock.cmp }} (Fixed: {{ stock.fixed_value }})</li>
                            {% else %}
                                <li>No discounted stocks.</li>
                            {% endfor %}
                        </ul>
                    </div>
                    <div style="flex: 1; background: #e6fffa; padding: 15px; border-radius: 8px;">
                        <h3>🚀 Rallying Stocks (>5% Profit)</h3>
                        <ul>
                            {% for stock in rallying %}
                                <li><strong>{{ stock.symbol }}</strong>: +{{ stock.pl_percent }}%</li>
                            {% else %}
                                <li>No rallying stocks.</li>
                            {% endfor %}
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://code.jquery.com/jquery-3.5.1.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
        <script>
            $(document).ready( function () {
                $('#portfolioTable').DataTable({
                    "pageLength": 50,
                    "order": [[3, "desc"]], // Sort by P/L % by default (descending)
                    "columnDefs": [
                        { "orderable": false, "targets": 4 } // Disable sorting on "Action" column
                    ]
                });
            } );
        </script>
    </body>

    </html>
    """
    return render_template_string(html, portfolio=portfolio, discounted=discounted, rallying=rallying)

@app.route("/add", methods=["POST"])
def add_stock():
    symbol = request.form.get("symbol").upper().strip()
    fixed_value = request.form.get("fixed_value")
    
    if symbol and fixed_value:
        stocks = get_tracked_stocks()
        # Avoid duplicates
        stocks = [s for s in stocks if s['symbol'] != symbol]
        stocks.append({"symbol": symbol, "fixed_value": float(fixed_value)})
        save_stocks(stocks)
    
    return redirect(url_for("index"))

@app.route("/delete/<symbol>")
def delete_stock(symbol):
    stocks = get_tracked_stocks()
    stocks = [s for s in stocks if s['symbol'] != symbol]
    save_stocks(stocks)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(port=5001, debug=True)
