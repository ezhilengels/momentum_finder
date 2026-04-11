# 📊 Sector-Wise Indian Stock Market Tracker — Planning Document

**Based on:** `momentum_tracker_v2.py` (NSE Wealth Compounder Dashboard)  
**Goal:** Extend the momentum tracking concept to a full **sector-wise tracking bot** for the Indian stock market  
**Date:** April 2026

---

## 1. What the Existing V2 Tracker Does (Quick Summary)

| Aspect | Detail |
|---|---|
| **Input** | CSV files with NSE stock symbols (Nifty500, market cap filters) |
| **Data source** | `yfinance` — fetches 6 years of daily close prices |
| **Analysis** | % returns across 14 timeframes: 1w, 2w, 3w, 4w, 1m, 2m, 3m, 6m, 9m, 1y, 2y, 3y, 4y, 5y |
| **Categories** | 💎 Diamond (14/14), 🚀 Secular Growth, 🔄 Turnaround, 📈 Improving, Other |
| **Score** | X/14 green timeframes |
| **Output** | Sortable HTML dashboard with color-coded returns |
| **Progress** | `progress.json` polling (for a web UI) |

**Key gap:** There is no sector dimension. All stocks are treated as one flat list. This new bot adds sector-awareness at every layer.

---

## 2. New Bot — Core Concept

> **"Sector-Wise Momentum Bot"** — Track momentum not just per stock, but per Indian market sector. Know which sectors are heating up or cooling down, and drill into each sector's best/worst performers — all with the same multi-timeframe momentum logic from V2.

---

## 3. Sector Universe — Indian Market

### 3a. Primary Sectors to Track (NSE/BSE)

| # | Sector | NSE Sector Index | Example Stocks |
|---|---|---|---|
| 1 | Banking & Finance (BFSI) | NIFTY BANK, NIFTY FIN SERVICE | HDFCBANK, ICICIBANK, AXISBANK, KOTAKBANK |
| 2 | Information Technology (IT) | NIFTY IT | TCS, INFY, WIPRO, HCLTECH, TECHM |
| 3 | Pharmaceuticals & Healthcare | NIFTY PHARMA | SUNPHARMA, DRREDDY, CIPLA, DIVISLAB |
| 4 | Automobiles & Auto Ancillaries | NIFTY AUTO | MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO |
| 5 | FMCG & Consumer Goods | NIFTY FMCG | HINDUNILVR, ITC, NESTLEIND, BRITANNIA |
| 6 | Energy (Oil, Gas, Power) | NIFTY ENERGY | RELIANCE, ONGC, NTPC, POWERGRID |
| 7 | Metals & Mining | NIFTY METAL | TATASTEEL, HINDALCO, JSWSTEEL, COALINDIA |
| 8 | Capital Goods & Industrials | NIFTY CPSE | L&T, ABB, SIEMENS, BHEL |
| 9 | Real Estate | NIFTY REALTY | DLF, GODREJPROP, OBEROIRLTY |
| 10 | Infrastructure & Cement | — | ULTRATECH, SHREECEM, ADANIPORTS |
| 11 | Telecom & Media | — | BHARTIARTL, IDEA, ZEEL |
| 12 | Chemicals & Agrochemicals | — | PIDILITIND, AARTI, PI INDUSTRIES |
| 13 | Consumer Durables & Electronics | NIFTY INDIA CONSUMPTION | DIXON, HAVELLS, VOLTAS |
| 14 | PSU / Defence | NIFTY PSE | BEL, HAL, RVNL, IRFC |

### 3b. Data Sources for Sector Classification

**Option A (Recommended — easiest):** Use the NSE sector column already present in `ind_nifty500list.csv`. The file typically has `Industry` or `Sector` columns.

**Option B:** Download NSE-sector CSVs from NSE's website (e.g., `ind_niftybanklist.csv`, `ind_niftyitlist.csv`, etc.) and merge them together with a sector label column.

**Option C:** Manually create a `sector_map.csv` with columns `Symbol, Sector` for full custom control.

**Option D:** Fetch sector data from `nsepython` or `jugaad-trader` Python libraries (NSE official data).

> **Recommended approach:** Combine Option A + B — parse the `Industry` field from Nifty500 list as the primary sector, and allow override via `sector_map.csv`.

---

## 4. New Bot Architecture

```
sector_tracker_bot/
│
├── data/
│   ├── ind_nifty500list.csv          ← existing input
│   ├── sector_map.csv                ← custom sector overrides (optional)
│   └── nifty_sector_indices.csv      ← sector index symbols (e.g. ^CNXBANK)
│
├── sector_tracker.py                 ← main script
├── sector_data_loader.py             ← handles CSV loading + sector mapping
├── momentum_engine.py                ← reused from V2 (returns calc logic)
├── sector_aggregator.py              ← NEW: aggregates stock data into sector metrics
├── html_generator.py                 ← enhanced HTML output
├── progress.json                     ← same polling mechanism
└── output/
    └── sector_report_YYYYMMDD.html   ← output dashboard
```

---

## 5. Feature Plan

### Feature 1 — Sector Mapping (New)
- Load all symbols from existing CSVs
- Map each symbol to a sector using the `Industry` / `Sector` column in Nifty500 CSV
- Allow a `sector_map.csv` override file for custom reassignments
- Handle unmapped stocks in an "Uncategorised" bucket

### Feature 2 — Sector Index Tracking (New)
- Track **NSE sector indices** directly alongside individual stocks
- Sector indices as yfinance tickers: `^CNXBANK`, `^CNXIT`, `^CNXPHARMA`, `^CNXAUTO`, `^CNXFMCG`, etc.
- Compute the same 14-timeframe returns for each sector index
- This gives a "sector benchmark" — you can compare any stock against its own sector index

### Feature 3 — Stock-Level Momentum (Retained from V2)
- Same 14 timeframes: 1w → 5y
- Same green/red color coding
- Same category logic: Diamond, Secular, Turnaround, Improving
- **Add new column:** `Sector` (so you can sort/filter by sector)
- **Add new column:** `vs. Sector Index` — stock return minus sector index return for 1m, 3m, 1y (outperformance score)

### Feature 4 — Sector-Level Aggregation (New — Core Feature)
For each sector, compute:

| Metric | Formula |
|---|---|
| **Sector Momentum Score** | Average green count across all stocks in sector (e.g. 11.2/14) |
| **% Stocks Positive (short-term)** | % of sector stocks positive in 1m return |
| **% Stocks Positive (long-term)** | % of sector stocks positive in 1y return |
| **Sector Average Return** | Mean return across all stocks per timeframe |
| **Sector Median Return** | Median return per timeframe (more robust) |
| **Best Performer** | Stock with highest score in sector |
| **Worst Performer** | Stock with lowest score in sector |
| **Diamond Count** | How many Diamond stocks in this sector |
| **Sector Category** | Classify the sector itself (Hot / Warming Up / Cooling / Cold) |

### Feature 5 — Sector Rotation Signals (New)
Compare short-term vs long-term sector momentum to detect rotation:

| Signal | Condition |
|---|---|
| 🔥 **Sector Heating Up** | Short-term (1m, 3m) score improving but long-term (1y, 2y) still moderate |
| ✅ **Sector Leader** | Both short-term AND long-term strong |
| ⚠️ **Sector Cooling** | Long-term strong but short-term score declining |
| ❄️ **Sector Cold** | Both short-term AND long-term weak |
| 🔄 **Sector Turnaround** | Short-term green, but 1y/2y red — potential recovery |

### Feature 6 — Sector Heatmap (New — Visual)
- A visual grid/heatmap of sectors × timeframes
- Colour: green (strong) → yellow (neutral) → red (weak)
- Based on average % return or % of stocks positive per cell
- Quick at-a-glance view of which sectors are strong in which timeframes

### Feature 7 — Enhanced HTML Dashboard (Upgraded from V2)

**Tab 1 — Sector Overview**
- Sector ranking table with Sector Momentum Score, rotation signal, best/worst stock, diamond count
- Heatmap of sectors × timeframes

**Tab 2 — Sector Drill-Down**
- Dropdown / button filter to select a sector
- Shows all stocks in that sector with full 14-timeframe momentum table (same as V2)
- Sector index performance shown at top as benchmark
- Stock vs. sector index outperformance column

**Tab 3 — All Stocks (Flat View)**
- Same as V2 output but with added `Sector` column
- Filter buttons: by category + by sector

**Tab 4 — Sector Rotation Chart**
- Simple scatter or ranked list: X = long-term score, Y = short-term score
- Quadrant view: Leaders / Emerging / Laggards / Falling Stars

### Feature 8 — Scheduling & Automation (New)
- Add CLI argument: `--schedule daily` to auto-run at market close (3:30 PM IST)
- Use Python `schedule` library or cron
- Auto-save timestamped HTML reports: `sector_report_20260409.html`
- Optional: send email/Telegram notification with sector summary on completion

### Feature 9 — Progress Tracking (Retained from V2)
- Same `progress.json` mechanism
- Add per-sector progress: `{"sector": "IT", "current": 15, "total": 48, "status": "analyzing"}`
- Enables a web UI to show live sector-by-sector progress

---

## 6. Configuration Plan

```python
# sector_config.py

CONFIG = {
    # Input files (same as V2)
    "INPUT_FILES": [
        "market cap greater than 10000.csv",
        "market cap greater than 20000csv.csv",
        "ind_nifty500list.csv"
    ],

    # Sector classification source
    "SECTOR_SOURCE": "nifty500_industry_column",  # or "custom_csv"
    "SECTOR_MAP_FILE": "sector_map.csv",           # optional override

    # Timeframes (same as V2)
    "TIMEFRAMES": {
        '1w': 7, '2w': 14, '3w': 21, '4w': 28,
        '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
        '1y': 365, '2y': 730, '3y': 1095, '4y': 1460, '5y': 1825
    },

    # Sector indices to track
    "SECTOR_INDICES": {
        "Banking": "^CNXBANK",
        "IT": "^CNXIT",
        "Pharma": "^CNXPHARMA",
        "Auto": "^CNXAUTO",
        "FMCG": "^CNXFMCG",
        "Energy": "^CNXENERGY",
        "Metal": "^CNXMETAL",
        "Realty": "^CNXREALTY",
        "Infra": "^CNXINFRA",
    },

    # Sector rotation thresholds
    "HOT_SECTOR_THRESHOLD": 10,    # avg green count >= 10/14 → "Hot"
    "COLD_SECTOR_THRESHOLD": 5,    # avg green count <= 5/14 → "Cold"

    # Output
    "OUTPUT_DIR": "output/",
    "REPORT_FILENAME": "sector_report_{date}.html",
}
```

---

## 7. Key Differences vs. V2

| Aspect | V2 (Existing) | Sector Bot (New) |
|---|---|---|
| Granularity | Flat stock list | Stocks organised by sector |
| Sector indices | None | Tracked as benchmark |
| Aggregation | None | Per-sector metrics + rotation signals |
| HTML output | 1 flat table | 4 tabs: overview, drill-down, flat view, rotation |
| Heatmap | None | Sector × timeframe heatmap |
| Scheduling | Manual run | Optional auto-run at market close |
| Config | Hardcoded | Centralised `sector_config.py` |
| Outperformance | None | Stock vs. sector index column |

---

## 8. Development Phases

### Phase 1 — Data Layer
1. Load Nifty500 CSV and extract sector/industry mapping
2. Build `sector_map.csv` with clean sector names
3. Verify sector index yfinance tickers work (e.g. `^CNXBANK`)
4. Write `sector_data_loader.py`

### Phase 2 — Momentum Engine (Reuse V2)
1. Extract V2's per-stock return calculation into a standalone `momentum_engine.py`
2. Add `Sector` column to output
3. Add `vs. Sector Index` outperformance columns

### Phase 3 — Sector Aggregation
1. Group stocks by sector after momentum calculation
2. Compute all sector-level metrics (score, % positive, best/worst, diamond count)
3. Apply rotation signal logic
4. Write `sector_aggregator.py`

### Phase 4 — HTML Dashboard
1. Build 4-tab HTML structure
2. Implement sector heatmap (CSS grid or Chart.js)
3. Implement sector drill-down filter
4. Wire up rotation quadrant chart (basic)
5. Retain V2 styling and DataTables

### Phase 5 — Automation & Polish
1. Add scheduling logic (market close trigger)
2. Add timestamped report saving
3. Add optional Telegram/email notification
4. Test on full Nifty500 dataset

---

## 9. Python Libraries Needed

| Library | Use |
|---|---|
| `pandas` | Data manipulation (same as V2) |
| `yfinance` | Price data (same as V2) |
| `tqdm` | Progress bars (same as V2) |
| `schedule` | Automated daily runs (new) |
| `json`, `os`, `datetime` | Utilities (same as V2) |
| `jinja2` *(optional)* | Cleaner HTML templating (upgrade) |
| `requests` *(optional)* | For fetching NSE sector lists directly |

No breaking changes from V2 — all V2 libraries remain, new ones are lightweight additions.

---

## 10. Decisions Locked In

| # | Question | Decision |
|---|---|---|
| 1 | Sector granularity | ✅ Fine-grained industries (use `Industry` column from Nifty500 CSV directly — ~50 sub-industries) |
| 2 | Sector index data source | ✅ See recommendation below — `nsepython` + yfinance hybrid |
| 3 | Scheduling | ✅ Auto-run twice daily: **8:55 AM IST** (pre-market snapshot) + **3:15 PM IST** (EOD snapshot) |
| 4 | Notifications | ✅ Telegram bot only |
| 5 | Stock universe | ✅ Nifty500 (same as V2) |
| 6 | Outperformance column | ✅ Both — raw momentum score AND stock vs. sector index outperformance |

---

## 11. Decision Deep-Dive: Best Data Source for Sector Indices

**Your requirement: data must be correct, always reliable.**

### Option Comparison

| Source | Reliability | Sector Indices? | Speed | Free? | Notes |
|---|---|---|---|---|---|
| **yfinance** (`^CNX*` tickers) | ⚠️ Medium | Yes, inconsistently | Fast | Yes | Some sector indices have gaps or stale data; works well for individual stocks |
| **nsepython** | ✅ High | Yes, via NSE directly | Medium | Yes | Pulls from NSE's official website; always matches what you see on nseindia.com |
| **jugaad-trader** | ✅ High | Yes | Medium | Yes | Similar to nsepython, NSE official source |
| **NSE Bhavcopy (direct CSV)** | ✅ Very High | Index only (EOD) | Slow | Yes | NSE publishes daily bhavcopy CSVs — 100% accurate but complex to parse for history |
| **Paid APIs (Upstox, Zerodha, Angel)** | ✅ Very High | Yes, clean | Very Fast | No | Requires broker account/API key |

### ✅ Recommended Approach: Two-Layer Hybrid

**Layer 1 — Individual stock prices:** Keep using `yfinance` with `.NS` suffix (same as V2). It is very reliable for individual NSE stock historical data.

**Layer 2 — Sector index prices:** Use `nsepython` as the primary source. It pulls index data directly from NSE's official API (same data NSE website shows). Use `yfinance` as a fallback only if `nsepython` fails for a particular index.

**Why not yfinance alone for sector indices?**
The `^CNXBANK`, `^CNXIT` etc. tickers on yfinance often have: missing recent days, slight price discrepancies vs. NSE official, and occasional total data gaps for smaller sector indices. `nsepython` avoids all of this.

### NSE Sector Index Names (for nsepython)

| Sector | NSE Index Name | yfinance Fallback |
|---|---|---|
| Banking | NIFTY BANK | `^NSEBANK` |
| IT | NIFTY IT | `^CNXIT` |
| Pharma | NIFTY PHARMA | `^CNXPHARMA` |
| Auto | NIFTY AUTO | `^CNXAUTO` |
| FMCG | NIFTY FMCG | `^CNXFMCG` |
| Energy | NIFTY ENERGY | `^CNXENERGY` |
| Metal | NIFTY METAL | `^CNXMETAL` |
| Realty | NIFTY REALTY | `^CNXREALTY` |
| Financial Services | NIFTY FIN SERVICE | `^CNXFINANCE` |
| Infrastructure | NIFTY INFRA | `^CNXINFRA` |
| PSE | NIFTY PSE | `^CNXPSE` |
| Media | NIFTY MEDIA | `^CNXMEDIA` |
| Consumption | NIFTY INDIA CONSUMPTION | — |

> **Important note:** `nsepython` only gives EOD (end-of-day) data — which is perfectly fine here since the V2 system also works on daily close prices. No intraday needed.

---

## 12. Scheduling Design

Two daily runs with different purposes:

### Run 1 — 8:55 AM IST (Pre-Market Snapshot)
- Market opens at 9:15 AM — this run fires just before
- Uses **previous day's close** as "current price" (most recent available)
- Purpose: Give a fresh sector momentum picture at the start of the trading day
- Telegram message: Morning sector summary — "Top 3 sectors by momentum, 3 weakest, any rotation signals"

### Run 2 — 3:15 PM IST (EOD Snapshot)
- Market closes at 3:30 PM — this run fires 15 minutes before close
- Uses **intraday price** via yfinance live quote (or last available tick)
- Purpose: End-of-day sector report showing how the day moved
- Telegram message: EOD sector summary — full sector ranking, biggest movers, updated HTML report link or attached image

### Scheduling Implementation
- Use Python `schedule` library with a persistent background process
- OR use system cron (`crontab`) — more reliable for long-running bots
- Recommended: **cron** for reliability (doesn't die if Python crashes), with `schedule` as a simpler alternative

```
# crontab entries (IST = UTC+5:30)
25 3 * * 1-5  python sector_tracker.py --mode morning    # 8:55 AM IST (Mon-Fri)
45 9 * * 1-5  python sector_tracker.py --mode eod        # 3:15 PM IST (Mon-Fri)
```

---

## 13. Telegram Bot Design

### What the Bot Sends

**Morning Message (8:55 AM):**
```
📊 SECTOR MORNING REPORT — 09 Apr 2026

🔥 HOT SECTORS (Strong Momentum):
  1. IT          — Score: 12.4/14 | 1M: +4.2%
  2. Pharma      — Score: 11.8/14 | 1M: +3.7%
  3. Auto        — Score: 11.1/14 | 1M: +2.9%

❄️ WEAK SECTORS:
  1. Realty      — Score: 4.2/14  | 1M: -3.1%
  2. Media       — Score: 5.1/14  | 1M: -1.8%

🔄 ROTATION ALERTS:
  • Banking: Heating Up (short-term green, long-term improving)
  • FMCG: Cooling (long-term strong but short-term fading)

💎 New Diamonds Today: INFY, TCS
📈 Full report: [link or file]
```

**EOD Message (3:15 PM):**
```
📊 SECTOR EOD REPORT — 09 Apr 2026

📈 TOP MOVERS TODAY (1D):
  Banking:  +1.8%  |  IT: +1.2%  |  Pharma: +0.9%
📉 LAGGARDS TODAY:
  Realty:  -2.1%  |  Metal: -1.4%

🔥 Momentum Shifts Since Morning:
  • Auto: upgraded from Warming → Hot
  • Energy: downgraded from Leader → Cooling

Full HTML report attached.
```

### Telegram Implementation
- Use `python-telegram-bot` library (v20+, async)
- Store Bot Token and Chat ID in a `.env` file (never hardcode)
- Send text messages for summaries
- Optionally attach the HTML report as a document (Telegram supports file attachments up to 50MB)

---

## 14. Fine-Grained Industry View — What to Expect

Since you chose fine-grained industries, the Nifty500 `Industry` column typically contains ~50 distinct industry labels such as:

- `Banks`, `Finance`, `Insurance`, `Housing Finance` (instead of one "BFSI" bucket)
- `Computers - Software & Consulting`, `IT - Hardware` (instead of one "IT")
- `Pharmaceuticals & Biotechnology`, `Healthcare Services`, `Medical Devices`
- `Automobile & Ancillaries`, `Auto Ancillaries` (separate)
- `Cement & Cement Products`, `Construction`, `Infrastructure`

**Implication for the dashboard:** The sector drill-down will show ~50 industry tabs instead of 10–15. The sector heatmap will be a larger grid but much more specific. Rotation signals will be industry-level, so you can see "Housing Finance heating up while Banks cooling" — much more actionable than a broad BFSI view.

**Recommendation:** In the dashboard, offer **two views** — a "Grouped Sector" rollup (10–15 broad sectors) and a "Fine Industry" view (all ~50). This gives you both the big picture and the detail.

---

## 15. Revised Development Phases (Updated)

### Phase 1 — Data Layer
- Load `ind_nifty500list.csv` and extract the `Industry` column as the sector label
- Build validation: print all unique industry names, flag any nulls/unknowns
- Set up `nsepython` for sector index fetching; validate all 13 index tickers
- Set up yfinance fallback logic for sector indices

### Phase 2 — Momentum Engine (Reuse V2)
- Extract V2 return calculation into `momentum_engine.py`
- Add `Industry` column to per-stock output
- Add `vs. Sector Index` outperformance for 1m, 3m, 6m, 1y timeframes
- Both raw score and outperformance columns included

### Phase 3 — Sector Aggregation
- Group by fine-grained `Industry`
- Also build a `parent_sector` mapping (e.g. Banks + Finance + Insurance → BFSI) for rollup view
- Compute per-industry: avg score, % positive per timeframe, rotation signal, best/worst stock, diamond count

### Phase 4 — HTML Dashboard (4 tabs)
- Tab 1: Sector overview heatmap + ranking table
- Tab 2: Industry drill-down with benchmark comparison
- Tab 3: Flat V2-style all-stocks table with Industry column
- Tab 4: Rotation quadrant chart (broad sectors)

### Phase 5 — Scheduling + Telegram
- Implement dual-schedule (8:55 AM + 3:15 PM IST, weekdays only)
- Build Telegram bot with morning + EOD message templates
- `.env` for secrets (bot token, chat ID)
- Attach HTML report to EOD Telegram message
