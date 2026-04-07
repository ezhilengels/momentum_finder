import pandas as pd
import yfinance as yf
from tqdm import tqdm
import datetime
import os

# Configuration
INPUT_FILES = [
    "market cap greater than 10000.csv",
    "market cap greater than 20000csv.csv"
]

def process_file(file_path):
    print(f"\nProcessing {file_path} (V2 Long-Term)...")
    df = pd.read_csv(file_path)
    
    # Clean symbols
    df['Symbol'] = df['Symbol'].str.replace('"', '').str.strip()
    symbols = [f"{s}.NS" for s in df['Symbol'].tolist() if pd.notna(s)]
    
    # Define expanded timeframes (14 total)
    timeframes = {
        '1w': 7, '2w': 14, '3w': 21, '4w': 28,
        '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
        '1y': 365, '2y': 730, '3y': 1095, '4y': 1460, '5y': 1825
    }
    
    # Fetch 6 years of data for ALL symbols (covers 5y + buffer)
    print(f"Fetching 6 years of historical data for {len(symbols)} symbols...")
    all_data = yf.download(symbols, period="6y", interval="1d", progress=True)['Close']
    
    if all_data.empty:
        print("Error: Could not fetch data.")
        return pd.DataFrame()

    results = []
    current_prices = all_data.iloc[-1]
    
    for symbol in tqdm(symbols, desc="V2 Momentum Analysis"):
        try:
            if symbol not in all_data.columns:
                continue
                
            curr_price = current_prices[symbol]
            if pd.isna(curr_price):
                continue
                
            row = {'Symbol': symbol.replace('.NS', ''), 'Current Price': round(float(curr_price), 2)}
            
            green_count = 0
            returns = {}
            
            # Calculate for each timeframe
            for label, days in timeframes.items():
                try:
                    target_date = all_data.index[-1] - datetime.timedelta(days=days)
                    price_then = all_data[symbol].asof(target_date)
                    
                    if pd.notna(price_then) and price_then != 0:
                        ret = ((curr_price / price_then) - 1) * 100
                        val = round(float(ret), 2)
                        row[label] = val
                        returns[label] = val
                        if val > 0:
                            green_count += 1
                    else:
                        row[label] = "N/A"
                        returns[label] = None
                except Exception:
                    row[label] = "N/A"
                    returns[label] = None
            
            # V2 Category Logic
            category = "Other"
            
            # Check for Diamond Compounder (All 14 Green)
            if green_count == 14:
                category = "💎 Diamond (14/14)"
            
            # Check for Secular Growth (All Long-Term Years Green)
            elif all(returns.get(y) and returns[y] > 0 for y in ['2y', '3y', '4y', '5y']):
                category = "🚀 Secular Growth"
            
            # Check for Turnaround Play (Short-term green, but 3y or 5y red)
            elif all(returns.get(m) and returns[m] > 0 for m in ['1w', '1m', '3m']) and \
                 ((returns.get('3y') and returns['3y'] < 0) or (returns.get('5y') and returns['5y'] < 0)):
                category = "🔄 Turnaround"
            
            # Check for Improving (at least 10/14 green)
            elif green_count >= 10:
                category = "📈 Strong/Improving"
            
            row['Score'] = f"{green_count}/14"
            row['Category'] = category
                
            results.append(row)
        except Exception:
            continue
            
    return pd.DataFrame(results)

def generate_html(df, output_file="momentum_report_v2.html"):
    if df.empty:
        print("No data to generate report.")
        return

    # Column order
    cols = ['Symbol', 'Category', 'Score', 'Current Price', 
            '1w', '2w', '3w', '4w', '1m', '2m', '3m', '6m', '9m', 
            '1y', '2y', '3y', '4y', '5y']
    df = df[cols]

    headers = "".join(f"<th>{col}</th>" for col in df.columns)
    rows = ""
    for _, row in df.iterrows():
        row_html = "<tr>"
        for i, col_name in enumerate(df.columns):
            val = row[col_name]
            cls = ""
            # Momentum color logic (Numeric cols from index 4 onwards)
            if i >= 4 and isinstance(val, (int, float)):
                if val > 0: cls = "positive"
                elif val < 0: cls = "negative"
            
            # Category styling
            if col_name == 'Category':
                if "Diamond" in str(val): cls = "cat-diamond"
                elif "Secular" in str(val): cls = "cat-secular"
                elif "Turnaround" in str(val): cls = "cat-turnaround"
                elif "Strong" in str(val): cls = "cat-improving"
                
            row_html += f'<td class="{cls}">{val}</td>'
        row_html += "</tr>"
        rows += row_html

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NSE Wealth Compounder Dashboard (V2)</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f0f4f8; }}
            .container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 25px rgba(0,0,0,0.1); }}
            h2 {{ color: #1a365d; text-align: center; margin-bottom: 5px; }}
            .subtitle {{ text-align: center; color: #4a5568; margin-bottom: 30px; font-size: 0.95em; }}
            
            /* Long-term grouping style */
            th:nth-child(n+14), td:nth-child(n+14) {{ background-color: #fffaf0 !important; border-left: 1px solid #feebc8; }}
            
            .filter-group {{ display: flex; justify-content: center; gap: 8px; margin-bottom: 25px; flex-wrap: wrap; }}
            .filter-btn {{ padding: 12px 20px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; background: #e2e8f0; color: #2d3748; }}
            .filter-btn.active {{ background: #2c5282; color: white; }}
            
            .positive {{ color: #276749 !important; font-weight: bold; }}
            .negative {{ color: #9b2c2c !important; font-weight: bold; }}
            
            .cat-diamond {{ background-color: #ebf8ff !important; color: #2c5282 !important; font-weight: bold; border: 1px solid #bee3f8; }}
            .cat-secular {{ background-color: #f0fff4 !important; color: #22543d !important; font-weight: bold; }}
            .cat-turnaround {{ background-color: #fff5f5 !important; color: #822727 !important; font-weight: bold; }}
            .cat-improving {{ background-color: #fefcbf !important; color: #744210 !important; font-weight: bold; }}
            
            table.dataTable thead th {{ background-color: #2a4365 !important; color: white !important; }}
            .fixedHeader-floating {{ top: 0 !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>NSE Wealth Compounder Dashboard (V2)</h2>
            <div class="subtitle">Multi-Year Analysis | Generated: {date}</div>
            
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterTable('all', this)">All Stocks</button>
                <button class="filter-btn" onclick="filterTable('Diamond', this)">💎 Diamond (14/14)</button>
                <button class="filter-btn" onclick="filterTable('Secular', this)">🚀 Secular Growth</button>
                <button class="filter-btn" onclick="filterTable('Turnaround', this)">🔄 Turnaround Plays</button>
                <button class="filter-btn" onclick="filterTable('Strong', this)">📈 Improving</button>
            </div>

            <table id="momentumTable" class="display" style="width:100%">
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
                table = $('#momentumTable').DataTable({{
                    "pageLength": 100,
                    "order": [[17, "desc"]], // Default sort by 5 Year return
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
    print(f"\nDashboard V2 generated: {output_file}")

if __name__ == "__main__":
    print("V2 - Multi-Year Wealth Tracker")
    print("Choose input file:")
    for i, f in enumerate(INPUT_FILES):
        if os.path.exists(f):
            print(f"{i+1}. {f}")
    
    try:
        choice = int(input("Enter choice (1/2): ")) - 1
        selected_file = INPUT_FILES[choice]
        results_df = process_file(selected_file)
        generate_html(results_df)
    except Exception as e:
        print(f"Error: {e}")
