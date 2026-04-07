# NSE Momentum Tracker Plan

## 1. Objective
Analyze momentum for stocks already filtered by market cap (>10,000 Cr and >20,000 Cr) using a generic, time-flexible engine.

## 2. Input Sources (User Provided)
- `market cap greater than 10000.csv`
- `market cap greater than 20000csv.csv`
- *Note: Bot B will allow selecting which file to analyze.*

## 3. Momentum Analyzer Engine (`momentum_tracker.py`)
### A. Core Logic
- **Generic Momentum Function:** `calculate_returns(symbol, days)`
    - Fetches current price and price from `X` days ago.
    - Returns percentage change.
- **Timeframes to Calculate:**
    - **Weekly:** 1w, 2w, 3w, 4w
    - **Monthly:** 1m, 2m, 3m, 6m, 9m
    - **Yearly:** 1y
    - *Designed to easily add 3y, 5y in the future.*

### B. Data Processing
1. Load symbols from the selected CSV.
2. Suffix symbols with `.NS` for Yahoo Finance.
3. Fetch batch historical data to minimize API calls.
4. Handle non-trading days (holidays/weekends) by finding the nearest previous trading day.

## 4. Output: HTML Dashboard
- **File:** `momentum_report.html`
- **Features:**
    - **Interactive Table:** Powered by DataTables (JS library) for sorting and searching.
    - **Filters:** Dropdown/buttons to filter by momentum (e.g., "Show Top 10 for 3 months").
    - **Color Coding:** Green for positive returns, Red for negative.
    - **Responsive:** Works on both desktop and mobile browsers.

## 5. Technical Stack
- **Backend:** Python, `pandas`, `yfinance`.
- **Frontend:** HTML5, CSS (Vanilla), DataTables.js (via CDN).

## 6. Development Steps
1. **Research & Validation:** Verify `.NS` symbols and data availability for all timeframes.
2. **Engine Implementation:** Build the generic calculation loop.
3. **HTML Generator:** Create a template that takes the `pandas` result and converts it to an interactive HTML page.
4. **Final Review:** Ensure the dashboard is user-friendly and the math is accurate.
