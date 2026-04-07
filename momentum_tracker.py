import pandas as pd
import yfinance as yf
from tqdm import tqdm
import datetime
import os
import json

# Configuration
INPUT_FILES = [
    "market cap greater than 10000.csv",
    "market cap greater than 20000csv.csv"
]

def update_progress(task_id, current, total, status="running", error=None):
    progress_file = "progress.json"
    data = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
        except: pass
    
    data[task_id] = {
        "current": current,
        "total": total,
        "status": status,
        "error": error,
        "time": datetime.datetime.now().strftime('%H:%M:%S')
    }
    with open(progress_file, "w") as f:
        json.dump(data, f)

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
    update_progress(task_id, 0, total, "downloading")
    print(f"Fetching historical data for {total} symbols...")
    try:
        all_data = yf.download(symbols, period="14mo", interval="1d", progress=True)['Close']
    except Exception as e:
        update_progress(task_id, 0, total, "error", str(e))
        return pd.DataFrame()
    
    if all_data.empty:
        update_progress(task_id, 0, total, "error", "No data available")
        print("Error: Could not fetch data.")
        return pd.DataFrame()

    results = []
    current_prices = all_data.iloc[-1]
    
    for i, symbol in enumerate(tqdm(symbols, desc="Analyzing Momentum")):
        try:
            if i % 10 == 0:
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

if __name__ == "__main__":
    import sys
    # Default to 20000 (index 1) if no argument provided
    choice = 1
    if len(sys.argv) > 1:
        try:
            choice = int(sys.argv[1])
        except:
            pass
            
    if 0 <= choice < len(INPUT_FILES):
        selected_file = INPUT_FILES[choice]
        if os.path.exists(selected_file):
            print(f"Running V1 Analysis on {selected_file}...")
            results_df = process_file(selected_file)
            generate_html(results_df)
        else:
            print(f"Error: {selected_file} not found.")
    else:
        print("Invalid choice index.")
