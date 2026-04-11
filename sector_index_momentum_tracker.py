#!/usr/bin/env python3
"""
sector_index_momentum_tracker.py
================================
Standalone momentum tracker for key NSE sector indices only.

Tracks:
  - Nifty Bank
  - Nifty Auto
  - Nifty Capital Markets
  - Nifty Chemicals
  - Nifty CPSE
  - Nifty Defence
  - Nifty Infra
  - Nifty 50
  - Nifty Consumption
  - Nifty India Manufacturing
  - Nifty FMCG
  - Nifty Fin Service
  - Nifty Pharma
  - Nifty IT
  - Nifty Media
  - Nifty Metal
  - Nifty Energy
  - Nifty Oil & Gas
  - Nifty PSU Bank
  - Nifty Private Bank
  - Nifty Realty
  - Nifty Services

Uses a 6-year fetch buffer and calculates momentum across 15 timeframes up to 5y.
"""

import datetime
import os

import pandas as pd

from nse_history_provider import fetch_price_matrices


OUTPUT_DIR = "output"

TIMEFRAMES = {
    "1d": 1,
    "1w": 7,
    "2w": 14,
    "3w": 21,
    "4w": 28,
    "1m": 30,
    "2m": 60,
    "3m": 90,
    "6m": 180,
    "9m": 270,
    "1y": 365,
    "2y": 730,
    "3y": 1095,
    "4y": 1460,
    "5y": 1825,
}
TF_LABELS = list(TIMEFRAMES.keys())

INDEX_QUERY_NAME = {
    "Nifty Bank": "NIFTY BANK",
    "Nifty Auto": "NIFTY AUTO",
    "Nifty Capital Markets": ("NIFTY CAPITAL MARKETS", "Nifty Capital Markets"),
    "Nifty Chemicals": ("NIFTY CHEMICALS", "Nifty Chemicals"),
    "Nifty CPSE": "NIFTY CPSE",
    "Nifty Defence": ("NIFTY INDIA DEFENCE", "Nifty India Defence"),
    "Nifty Infra": "NIFTY INFRASTRUCTURE",
    "Nifty 50": "NIFTY 50",
    "Nifty Consumption": "NIFTY INDIA CONSUMPTION",
    "Nifty India Manufacturing": "NIFTY INDIA MANUFACTURING",
    "Nifty FMCG": "NIFTY FMCG",
    "Nifty Fin Service": "NIFTY FINANCIAL SERVICES",
    "Nifty Pharma": "NIFTY PHARMA",
    "Nifty IT": "NIFTY IT",
    "Nifty Media": "NIFTY MEDIA",
    "Nifty Metal": "NIFTY METAL",
    "Nifty Energy": "NIFTY ENERGY",
    "Nifty Oil & Gas": ("NIFTY OIL AND GAS INDEX", "NIFTY OIL & GAS", "Nifty Oil & Gas"),
    "Nifty PSU Bank": "NIFTY PSU BANK",
    "Nifty Private Bank": "NIFTY PRIVATE BANK",
    "Nifty Realty": "NIFTY REALTY",
    "Nifty Services": "NIFTY SERVICES SECTOR",
}


def calc_returns(series, last_date):
    clean = series.dropna()
    if clean.empty:
        return {label: None for label in TF_LABELS}, None

    current = float(clean.iloc[-1])
    returns = {}
    for label, days in TIMEFRAMES.items():
        try:
            target = last_date - datetime.timedelta(days=days)
            old_price = series.asof(target)
            if pd.notna(old_price) and old_price != 0:
                returns[label] = round(((current / float(old_price)) - 1) * 100, 2)
            else:
                returns[label] = None
        except Exception:
            returns[label] = None
    return returns, round(current, 2)


def score_from_returns(returns):
    return sum(1 for value in returns.values() if value is not None and value > 0)


def categorise(score, returns):
    if score == len(TF_LABELS):
        return "💎 Diamond"
    if score >= 10 and all((returns.get(tf) or -999) > 0 for tf in ["1y", "3y", "5y"]):
        return "🚀 Strong Leader"
    if all((returns.get(tf) or -999) > 0 for tf in ["1d", "1w", "1m"]) and any(
        (returns.get(tf) or 0) < 0 for tf in ["1y", "3y", "5y"]
    ):
        return "🔄 Turnaround"
    if score >= 8:
        return "📈 Improving"
    return "Other"


def analyze_indices():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _, index_data = fetch_price_matrices([], INDEX_QUERY_NAME, years=6)
    if index_data.empty:
        return pd.DataFrame()

    rows = []
    for display_name in INDEX_QUERY_NAME:
        if display_name not in index_data.columns:
            continue
        series = index_data[display_name].dropna()
        if series.empty:
            continue
        last_date = series.index[-1]
        returns, current_value = calc_returns(series, last_date)
        if current_value is None:
            continue
        score = score_from_returns(returns)
        row = {
            "Sector Index": display_name,
            "Current Value": current_value,
            "Score": score,
            "Score Label": f"{score}/{len(TF_LABELS)}",
            "Category": categorise(score, returns),
        }
        for label in TF_LABELS:
            row[label] = returns.get(label)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        by=["Score", "1m", "1y"], ascending=[False, False, False]
    ).reset_index(drop=True)


def _ret_style(value):
    if value is None:
        return ""
    try:
        num = float(value)
    except Exception:
        return ""
    if num > 0:
        return "color:#1f7a3d;font-weight:700;"
    if num < 0:
        return "color:#b42318;font-weight:700;"
    return "color:#666;"


def generate_html(df):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filepath = os.path.join(OUTPUT_DIR, f"sector_index_momentum_{timestamp}.html")
    generated = datetime.datetime.now().strftime("%d %b %Y, %H:%M")

    headers = ["Sector Index", "Current Value", "Score", "Category"] + TF_LABELS
    header_html = "".join(
        f'<th onclick="sortTable({idx})">{col}<span class="sort-indicator">↕</span></th>'
        for idx, col in enumerate(headers)
    )

    rows_html = ""
    for _, row in df.iterrows():
        cells = [
            f'<td><b>{row["Sector Index"]}</b></td>',
            f'<td>{row["Current Value"]}</td>',
            f'<td><b>{row["Score Label"]}</b></td>',
            f'<td>{row["Category"]}</td>',
        ]
        for label in TF_LABELS:
            value = row[label]
            display = "N/A" if value is None else f'{value:+.2f}%'
            cells.append(f'<td style="{_ret_style(value)}">{display}</td>')
        rows_html += f"<tr>{''.join(cells)}</tr>\n"

    top3 = df.head(3)[["Sector Index", "Score Label", "Category"]]
    bottom3 = df.tail(3)[["Sector Index", "Score Label", "Category"]]
    top_html = "".join(
        f"<li><b>{row['Sector Index']}</b> — {row['Score Label']} | {row['Category']}</li>"
        for _, row in top3.iterrows()
    )
    bottom_html = "".join(
        f"<li><b>{row['Sector Index']}</b> — {row['Score Label']} | {row['Category']}</li>"
        for _, row in bottom3.iterrows()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Sector Index Momentum Tracker</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: 'Segoe UI', Tahoma, sans-serif; background: #eef3f8; color: #243b53; }}
  .page {{ max-width: 1480px; margin: 0 auto; padding: 24px; }}
  .hero {{ background: linear-gradient(135deg, #173f73, #295e9b); color: white; padding: 24px 28px; border-radius: 18px; box-shadow: 0 18px 40px rgba(23,63,115,.18); }}
  .hero h1 {{ margin: 0 0 8px; font-size: 2rem; }}
  .hero p {{ margin: 0; opacity: 0.9; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 22px 0; }}
  .card {{ background: white; border-radius: 16px; padding: 20px 22px; box-shadow: 0 10px 30px rgba(15,23,42,.08); }}
  .card h3 {{ margin: 0 0 12px; font-size: 1.1rem; }}
  ul {{ margin: 0; padding-left: 18px; }}
  li {{ margin-bottom: 8px; }}
  .table-card {{ background: white; border-radius: 16px; padding: 20px 22px; box-shadow: 0 10px 30px rgba(15,23,42,.08); overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; min-width: 1200px; }}
  th {{ background: #264b78; color: white; font-weight: 700; font-size: 0.92rem; padding: 12px 10px; position: sticky; top: 0; cursor: pointer; user-select: none; white-space: nowrap; }}
  td {{ padding: 11px 10px; border-bottom: 1px solid #dde7f0; font-size: 0.95rem; }}
  tr:nth-child(even) td {{ background: #f8fbff; }}
  .note {{ margin-top: 14px; color: #52667a; font-size: 0.9rem; }}
  .sort-indicator {{ margin-left: 6px; font-size: 0.8rem; opacity: 0.75; }}
  @media (max-width: 900px) {{
    .grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Sector Index Momentum Tracker</h1>
      <p>{len(INDEX_QUERY_NAME)} NSE sector indices · 5 years history target · Generated {generated}</p>
    </div>

    <div class="grid">
      <div class="card">
        <h3>Top Momentum Sectors</h3>
        <ul>{top_html}</ul>
      </div>
      <div class="card">
        <h3>Weakest Momentum Sectors</h3>
        <ul>{bottom_html}</ul>
      </div>
    </div>

    <div class="table-card">
      <h3 style="margin-top:0">Full Sector Momentum Table</h3>
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody id="momentumTableBody">{rows_html}</tbody>
      </table>
      <div class="note">Positive returns are highlighted in green and negative returns in red. Click any column header to sort.</div>
    </div>
  </div>
<script>
  let currentSortColumn = 2;
  let currentSortAsc = false;

  function parseCellValue(text) {{
    const cleaned = text.replace(/[%+,₹]/g, '').trim();
    if (cleaned === 'N/A' || cleaned === '') return null;
    const num = Number(cleaned);
    return Number.isNaN(num) ? text.trim().toLowerCase() : num;
  }}

  function compareValues(a, b, asc) {{
    if (a === null && b === null) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    if (typeof a === 'number' && typeof b === 'number') return asc ? a - b : b - a;
    const result = String(a).localeCompare(String(b));
    return asc ? result : -result;
  }}

  function sortTable(colIndex) {{
    const tbody = document.getElementById('momentumTableBody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const asc = currentSortColumn === colIndex ? !currentSortAsc : false;

    rows.sort((rowA, rowB) => {{
      const valA = parseCellValue(rowA.children[colIndex].textContent);
      const valB = parseCellValue(rowB.children[colIndex].textContent);
      return compareValues(valA, valB, asc);
    }});

    rows.forEach(row => tbody.appendChild(row));
    currentSortColumn = colIndex;
    currentSortAsc = asc;

    document.querySelectorAll('th .sort-indicator').forEach(el => el.textContent = '↕');
    const active = document.querySelectorAll('th')[colIndex].querySelector('.sort-indicator');
    if (active) active.textContent = asc ? '↑' : '↓';
  }}

  sortTable(2);
</script>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as handle:
        handle.write(html)
    return filepath


def main():
    print("\n" + "=" * 60)
    print(f"  SECTOR INDEX MOMENTUM TRACKER  |  {datetime.datetime.now()}")
    print("=" * 60)

    df = analyze_indices()
    if df.empty:
        print("[ERROR] No sector index data available.")
        return

    html_path = generate_html(df)
    print(f"\nAnalysis complete: {len(df)} sector indices ranked.")
    print(f"Report saved: {html_path}")


if __name__ == "__main__":
    main()
