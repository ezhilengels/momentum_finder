import pandas as pd
import yfinance as yf
from tqdm import tqdm
import datetime
import os
import json

# Sector and Index Configuration
SECTOR_MAP = {
    'Silverbees': 'SILVERBEES.NS',
    'Goldbees': 'GOLDBEES.NS',
    'PSU Bank Index': '^CNXPSUBANK',
    'Nifty Metal': '^CNXMETAL',
    'Nifty Auto': '^CNXAUTO',
    'Midcap 100': '^CNXMIDCAP',
    'Nifty Pharma': '^CNXPHARMA',
    'Nifty Bank': '^NSEBANK',
    'Nifty 50': '^NSEI',
    'Sensex': '^BSESN',
    'Smallcap 100': '^CNXSC',
    'Nifty FMCG': '^CNXFMCG',
    'Nifty IT': '^CNXIT',
    'Nifty Realty': '^CNXREALTY',
    'Nifty Media': '^CNXMEDIA',
    'Nifty Energy': '^CNXENERGY',
    'Nifty Infra': '^CNXINFRA',
    'Nifty Commodities': '^CNXCOMMODITIES',
    'Nifty Consumption': '^CNXCONSUMP',
    'Nifty CPSE': '^CNXCPSE',
    'Nifty PSE': '^CNXPSE',
    'Nifty Services': '^CNXSERVICE'
}

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

def process_sectors(task_id="sector_v1"):
    print(f"\nProcessing Sector Momentum Analysis...")
    
    symbols = list(SECTOR_MAP.values())
    names = list(SECTOR_MAP.keys())
    name_to_symbol = {v: k for k, v in SECTOR_MAP.items()}
    
    # Define timeframes
    timeframes = {
        '1w': 7, '2w': 14, '3w': 21, '4w': 28,
        '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
        '1y': 365, '2y': 730, '3y': 1095, '5y': 1825
    }
    
    total = len(symbols)
    update_progress(task_id, 0, total, "downloading")
    print(f"Fetching historical data for {total} sectors/indices...")
    try:
        # Fetch 6 years of data
        all_data = yf.download(symbols, period="6y", interval="1d", progress=True)['Close']
    except Exception as e:
        update_progress(task_id, 0, total, "error", str(e))
        return pd.DataFrame()
    
    if all_data.empty:
        update_progress(task_id, 0, total, "error", "No data available")
        print("Error: Could not fetch data.")
        return pd.DataFrame()

    results = []
    current_prices = all_data.iloc[-1]
    
    for i, symbol in enumerate(tqdm(symbols, desc="Sector Analysis")):
        try:
            update_progress(task_id, i, total, "analyzing")
            
            if symbol not in all_data.columns:
                continue
                
            curr_price = current_prices[symbol]
            if pd.isna(curr_price):
                # Try to get last valid price
                curr_price = all_data[symbol].dropna().iloc[-1]
            
            if pd.isna(curr_price):
                continue
                
            row = {'Sector/Index': name_to_symbol[symbol], 'Current Value': round(float(curr_price), 2)}
            
            green_count = 0
            returns = {}
            
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
            
            # Momentum Rating Logic
            rating = "Neutral"
            if green_count >= 12:
                rating = "🔥 Super Bullish"
            elif green_count >= 10:
                rating = "📈 Bullish"
            elif green_count <= 4:
                rating = "📉 Bearish"
            elif green_count <= 2:
                rating = "🧊 Super Bearish"
            
            row['Score'] = f"{green_count}/{len(timeframes)}"
            row['Rating'] = rating
                
            results.append(row)
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue
            
    update_progress(task_id, total, total, "completed")
    return pd.DataFrame(results)

def generate_html(df, output_file="sector_momentum_report.html"):
    if df.empty:
        print("No data to generate report.")
        return

    # Column order
    cols = ['Sector/Index', 'Rating', 'Score', 'Current Value', 
            '1w', '2w', '3w', '4w', '1m', '2m', '3m', '6m', '9m', 
            '1y', '2y', '3y', '5y']
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
            
            # Rating styling
            if col_name == 'Rating':
                if "Super Bullish" in str(val): cls = "rate-super-bull"
                elif "Bullish" in str(val): cls = "rate-bull"
                elif "Super Bearish" in str(val): cls = "rate-super-bear"
                elif "Bearish" in str(val): cls = "rate-bear"
                
            row_html += f'<td class="{cls}">{val}</td>'
        row_html += "</tr>"
        rows += row_html

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Indian Sector Momentum Dashboard</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f0f4f8; }}
            .container {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 25px rgba(0,0,0,0.1); }}
            h2 {{ color: #1a365d; text-align: center; margin-bottom: 5px; }}
            .subtitle {{ text-align: center; color: #4a5568; margin-bottom: 30px; font-size: 0.95em; }}
            
            .positive {{ color: #276749 !important; font-weight: bold; }}
            .negative {{ color: #9b2c2c !important; font-weight: bold; }}
            
            .rate-super-bull {{ background-color: #f0fff4 !important; color: #22543d !important; font-weight: bold; border-left: 5px solid #276749; }}
            .rate-bull {{ background-color: #f0fff4 !important; color: #276749 !important; }}
            .rate-super-bear {{ background-color: #fff5f5 !important; color: #822727 !important; font-weight: bold; border-left: 5px solid #9b2c2c; }}
            .rate-bear {{ background-color: #fff5f5 !important; color: #9b2c2c !important; }}
            
            table.dataTable thead th {{ background-color: #2a4365 !important; color: white !important; }}
            
            .fixedHeader-floating {{ top: 0 !important; }}
            
            .heatmap-cell {{
                transition: transform 0.2s;
            }}
            .heatmap-cell:hover {{
                transform: scale(1.1);
                z-index: 10;
                position: relative;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Indian Sector Momentum Dashboard</h2>
            <div class="subtitle">Sector-wise Multi-Timeframe Analysis | Generated: {date}</div>
            
            <table id="sectorTable" class="display" style="width:100%">
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
            $(document).ready( function () {{
                $('#sectorTable').DataTable({{
                    "pageLength": 50,
                    "order": [[2, "desc"]], // Default sort by Score
                    "scrollX": true,
                    "fixedHeader": true
                }});
            }} );
        </script>
    </body>
    </html>
    """.format(date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), headers=headers, rows=rows)
    
    with open(output_file, "w") as f:
        f.write(html_template)
    print(f"\nSector Dashboard generated: {output_file}")

if __name__ == "__main__":
    results_df = process_sectors()
    generate_html(results_df)
