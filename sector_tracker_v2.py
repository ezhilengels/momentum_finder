#!/usr/bin/env python3
"""
sector_tracker_v2.py — Sector-Wise Indian Stock Market Tracker
===============================================================
Tracks all 500 Nifty500 stocks grouped by their 20 NSE industries.

Features
--------
  • Multi-timeframe momentum (14 TFs: 1w → 5y) — same engine as V2
  • Sector index benchmarking via yfinance (^CNXIT, ^CNXAUTO, etc.)
  • Stock vs. sector-index outperformance columns (1m, 3m, 1y)
  • Per-industry aggregation: avg score, % positive, rotation signal
  • 4-tab HTML dashboard (Sector Overview | Drill-Down | All Stocks | Rotation)
  • Sector rotation heatmap (industries × timeframes)
  • Telegram bot notifications (morning brief + EOD report)
  • APScheduler: 8:55 AM IST (pre-market) + 3:15 PM IST (EOD) — weekdays only
  • progress.json polling (compatible with existing web UI)

Usage
-----
  python sector_tracker_v2.py              # run immediately (full mode)
  python sector_tracker_v2.py --mode morning
  python sector_tracker_v2.py --mode eod
  python sector_tracker_v2.py --schedule   # start the scheduler daemon
"""

import os, sys, json, datetime, argparse, time, threading
import pandas as pd
from tqdm import tqdm
from nse_history_provider import fetch_price_matrices

# ── Optional dependencies (graceful fallback) ─────────────────────────────────
try:
    import telebot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[WARN] pyTelegramBotAPI not installed — Telegram disabled.")

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz
    SCHEDULER_AVAILABLE = True
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    SCHEDULER_AVAILABLE = False
    IST = None
    print("[WARN] apscheduler / pytz not installed — scheduling disabled.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

NIFTY500_CSV  = "ind_nifty500list.csv"
OUTPUT_DIR    = "output"
PROGRESS_FILE = "progress.json"

# 15 timeframes — 1d added first so it appears as leftmost column
TIMEFRAMES = {
    '1d': 1,
    '1w': 7,  '2w': 14, '3w': 21, '4w': 28,
    '1m': 30, '2m': 60, '3m': 90, '6m': 180, '9m': 270,
    '1y': 365,'2y': 730,'3y': 1095,'4y': 1460,'5y': 1825
}
TF_LABELS = list(TIMEFRAMES.keys())  # 15 total

# ── Industry → NSE Sector Index identifiers ──────────────────────────────────
# We keep the old legacy ids so the rest of the analysis pipeline stays stable,
# but the provider maps them to NSE index names instead of Yahoo symbols.
# ── Verified Yahoo Finance tickers for NSE sector indices ─────────────────────
# Tickers marked (yf only) have no nsepython equivalent — yfinance is the sole source.
# Tickers marked (nsepy) are fetched via nsepython index_history() first.
#
#  ✓ confirmed working   ✗ replaced with working equivalent
#
#  OLD (broken)       NEW (working)
#  ^CNXFINANCE    →   ^CNXFIN
#  ^CNXCONSUMP    →   ^NSEI  (no Consumption index on Yahoo; use Nifty50 proxy)
#  ^CNXPHARMA     →   ^CNXPHARMA  (works via nsepython "NIFTY PHARMA")
#  ^CNXINFRA      →   ^NSEI  (Infra not on Yahoo; use Nifty50 proxy)

INDUSTRY_INDEX_MAP = {
    "Automobile and Auto Components":    "^CNXAUTO",
    "Capital Goods":                     "^NSEI",       # Infra index broken → Nifty50 proxy
    "Chemicals":                         "^NSEI",
    "Construction":                      "^NSEI",       # Infra index broken → Nifty50 proxy
    "Construction Materials":            "^NSEI",       # Infra index broken → Nifty50 proxy
    "Consumer Durables":                 "^NSEI",       # Consumption index broken → Nifty50 proxy
    "Consumer Services":                 "^NSEI",       # Consumption index broken → Nifty50 proxy
    "Diversified":                       "^NSEI",
    "Fast Moving Consumer Goods":        "^CNXFMCG",
    "Financial Services":                "^CNXFIN",     # was ^CNXFINANCE (wrong)
    "Healthcare":                        "^CNXPHARMA",
    "Information Technology":            "^CNXIT",
    "Media Entertainment & Publication": "^CNXMEDIA",
    "Metals & Mining":                   "^CNXMETAL",
    "Oil Gas & Consumable Fuels":        "^CNXENERGY",
    "Power":                             "^CNXENERGY",
    "Realty":                            "^CNXREALTY",
    "Services":                          "^CNXSERVICE",
    "Telecommunication":                 "^CNXSERVICE",
    "Textiles":                          "^NSEI",
}

INDEX_DISPLAY = {
    "^CNXAUTO":    "Nifty Auto",
    "^NSEI":       "Nifty 50",
    "^CNXFMCG":    "Nifty FMCG",
    "^CNXFIN":     "Nifty Fin Service",
    "^CNXPHARMA":  "Nifty Pharma",
    "^CNXIT":      "Nifty IT",
    "^CNXMEDIA":   "Nifty Media",
    "^CNXMETAL":   "Nifty Metal",
    "^CNXENERGY":  "Nifty Energy",
    "^CNXREALTY":  "Nifty Realty",
    "^CNXSERVICE": "Nifty Services",
}

ALL_INDEX_TICKERS = sorted(set(INDUSTRY_INDEX_MAP.values()))

# nsepython index_history() query names — only for indices nsepython can serve.
# Any ticker not listed here will go straight to yfinance fallback.
INDEX_QUERY_NAME = {
    "^CNXAUTO":    "NIFTY AUTO",
    "^NSEI":       "NIFTY 50",
    "^CNXFMCG":    "NIFTY FMCG",
    "^CNXFIN":     "NIFTY FINANCIAL SERVICES",
    "^CNXPHARMA":  "NIFTY PHARMA",
    "^CNXIT":      "NIFTY IT",
    "^CNXMEDIA":   "NIFTY MEDIA",
    "^CNXMETAL":   "NIFTY METAL",
    "^CNXENERGY":  "NIFTY ENERGY",
    "^CNXREALTY":  "NIFTY REALTY",
    "^CNXSERVICE": "NIFTY SERVICES SECTOR",
}

# Telegram (loaded from .env)
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Rotation signal thresholds (% of stocks positive in a group of timeframes)
HOT_THRESHOLD  = 60    # ≥60% positive → strong in that band
COLD_THRESHOLD = 40    # ≤40% positive → weak in that band


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKING  (compatible with existing progress.json web UI)
# ══════════════════════════════════════════════════════════════════════════════

def _read_progress_file():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_progress_file(data):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f)

def update_progress(task_id, current, total, status="running", error=None, log=None):
    data = _read_progress_file()
    existing = data.get(task_id, {})
    logs = existing.get("logs", [])
    if log:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{ts}] {log}")
        logs = logs[-12:]           # keep last 12 lines
    data[task_id] = {
        "current": current,
        "total":   total,
        "status":  status,
        "error":   error,
        "time":    datetime.datetime.now().strftime("%H:%M:%S"),
        "logs":    logs,
    }
    _write_progress_file(data)

def _append_log(task_id, msg):
    """Append a single log line without changing current/total/status."""
    data = _read_progress_file()
    existing = data.get(task_id, {})
    logs = existing.get("logs", [])
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{ts}] {msg}")
    logs = logs[-12:]
    existing["logs"] = logs
    data[task_id] = existing
    _write_progress_file(data)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_nifty500():
    """
    Read ind_nifty500list.csv.
    Returns:
        industry_map : { 'Financial Services': ['HDFCBANK.NS', ...], ... }
        sym_to_ind   : { 'HDFCBANK.NS': 'Financial Services', ... }
        all_symbols  : ['HDFCBANK.NS', ...]
    """
    df = pd.read_csv(NIFTY500_CSV)
    df["Symbol"]   = df["Symbol"].str.replace('"', "").str.strip()
    df["Industry"] = df["Industry"].str.strip()

    industry_map = {}
    sym_to_ind   = {}

    for _, row in df.iterrows():
        sym = row["Symbol"]
        ind = row["Industry"]
        if pd.isna(sym) or pd.isna(ind):
            continue
        full = f"{sym}.NS"
        industry_map.setdefault(ind, []).append(full)
        sym_to_ind[full] = ind

    all_symbols = [s for syms in industry_map.values() for s in syms]
    return industry_map, sym_to_ind, all_symbols


# ══════════════════════════════════════════════════════════════════════════════
# MOMENTUM ENGINE  (identical logic to momentum_tracker_v2.py)
# ══════════════════════════════════════════════════════════════════════════════

def calc_returns(series, last_date):
    """
    Calculate % returns for all 14 timeframes given a price Series.
    Returns: (returns_dict, current_price)  —  None values for missing data.
    """
    clean = series.dropna()
    if clean.empty:
        return {lbl: None for lbl in TF_LABELS}, None

    curr = float(clean.iloc[-1])
    returns = {}
    for label, days in TIMEFRAMES.items():
        try:
            target    = last_date - datetime.timedelta(days=days)
            price_old = series.asof(target)
            if pd.notna(price_old) and price_old != 0:
                returns[label] = round(((curr / float(price_old)) - 1) * 100, 2)
            else:
                returns[label] = None
        except Exception:
            returns[label] = None
    return returns, curr


def score_from_returns(returns):
    """Count how many timeframes have a positive return."""
    return sum(1 for v in returns.values() if v is not None and v > 0)


def categorise(green, returns):
    """V2 category logic — unchanged."""
    if green == 14:
        return "💎 Diamond"
    if all(returns.get(y) and returns[y] > 0 for y in ["2y", "3y", "4y", "5y"]):
        return "🚀 Secular Growth"
    if (all(returns.get(m) and returns[m] > 0 for m in ["1w", "1m", "3m"]) and
            ((returns.get("3y") and returns["3y"] < 0) or
             (returns.get("5y") and returns["5y"] < 0))):
        return "🔄 Turnaround"
    if green >= 10:
        return "📈 Strong/Improving"
    return "Other"


# ══════════════════════════════════════════════════════════════════════════════
# SECTOR AGGREGATION + ROTATION SIGNALS
# ══════════════════════════════════════════════════════════════════════════════

def rotation_signal(short_pct, long_pct):
    """
    Classify a sector based on short-term (1w/1m/3m) and
    long-term (1y/2y/3y) % of stocks that are positive.
    """
    if short_pct >= HOT_THRESHOLD and long_pct >= HOT_THRESHOLD:
        return "✅ Leader"
    if short_pct >= HOT_THRESHOLD and long_pct < COLD_THRESHOLD:
        return "🔥 Heating Up"
    if short_pct >= HOT_THRESHOLD and long_pct < HOT_THRESHOLD:
        return "🌡️ Warming"
    if short_pct < COLD_THRESHOLD and long_pct >= HOT_THRESHOLD:
        return "⚠️ Cooling"
    if short_pct >= COLD_THRESHOLD and long_pct < COLD_THRESHOLD:
        return "🔄 Turnaround Attempt"
    if short_pct < COLD_THRESHOLD and long_pct < COLD_THRESHOLD:
        return "❄️ Cold"
    return "➡️ Neutral"


def aggregate_sectors(stocks_df, index_returns):
    """
    Group stocks_df by Industry and compute sector-level metrics.
    Returns a sector_df sorted by Avg Score descending.
    """
    rows = []
    for industry, grp in stocks_df.groupby("Industry"):
        n = len(grp)

        # Average score
        avg_score = round(grp["Score"].mean(), 1)

        # % of stocks positive per timeframe
        tf_pct = {}
        for tf in TF_LABELS:
            vals = grp[tf].dropna()
            tf_pct[tf] = round((vals > 0).sum() / len(vals) * 100, 1) if len(vals) else None

        # Short / long pct for rotation signal
        short_tfs = ["1w", "1m", "3m"]
        long_tfs  = ["1y", "2y", "3y"]
        s_vals = [tf_pct[t] for t in short_tfs if tf_pct.get(t) is not None]
        l_vals = [tf_pct[t] for t in long_tfs  if tf_pct.get(t) is not None]
        short_pct = round(sum(s_vals) / len(s_vals), 1) if s_vals else 50.0
        long_pct  = round(sum(l_vals) / len(l_vals), 1) if l_vals else 50.0
        signal    = rotation_signal(short_pct, long_pct)

        # Diamond / category counts
        diamond_count  = int((grp["Score"] == 14).sum())
        secular_count  = int((grp["Category"] == "🚀 Secular Growth").sum())
        turnaround_cnt = int((grp["Category"] == "🔄 Turnaround").sum())

        # Best / worst stock by momentum score
        best  = grp.loc[grp["Score"].idxmax()]
        worst = grp.loc[grp["Score"].idxmin()]

        idx_ticker = INDUSTRY_INDEX_MAP.get(industry, "^NSEI")
        idx_name   = INDEX_DISPLAY.get(idx_ticker, idx_ticker)
        idx_ret    = index_returns.get(idx_ticker, {})

        row = {
            "Industry":      industry,
            "Stocks":        n,
            "Sector Index":  idx_name,
            "Avg Score":     avg_score,
            "Score Label":   f"{avg_score}/14",
            "Signal":        signal,
            "Short %":       short_pct,
            "Long %":        long_pct,
            "Diamond #":     diamond_count,
            "Secular #":     secular_count,
            "Turnaround #":  turnaround_cnt,
            "Best Stock":    best["Symbol"],
            "Best Score":    int(best["Score"]),
            "Worst Stock":   worst["Symbol"],
            "Worst Score":   int(worst["Score"]),
        }
        # % positive per timeframe
        for tf in TF_LABELS:
            row[f"pct_{tf}"] = tf_pct.get(tf)
        # Sector index returns per timeframe
        for tf in TF_LABELS:
            row[f"idx_{tf}"] = idx_ret.get(tf)

        rows.append(row)

    return pd.DataFrame(rows).sort_values("Avg Score", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# HTML DASHBOARD  (4 tabs)
# ══════════════════════════════════════════════════════════════════════════════

def _pct_color(val):
    """Return a CSS background colour for a % positive value (0–100)."""
    if val is None:
        return "#f0f0f0"
    if val >= 70:
        return "#c6efce"  # green
    if val >= 55:
        return "#d9ead3"
    if val >= 45:
        return "#fff2cc"  # yellow
    if val >= 30:
        return "#fce4d6"
    return "#f4cccc"      # red


def _ret_color_style(val):
    """Return inline style for a return % value."""
    if val is None or val == "N/A":
        return ""
    try:
        v = float(val)
        return "color:#276749;font-weight:bold;" if v > 0 else "color:#9b2c2c;font-weight:bold;"
    except Exception:
        return ""


def generate_html(stocks_df, sector_df, index_returns, mode="morning"):
    """Generate the 4-tab HTML dashboard and return the file path."""
    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"sector_report_{ts}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)

    gen_time = datetime.datetime.now().strftime("%d %b %Y, %H:%M")

    # ── Tab 1: Sector Overview Table ─────────────────────────────────────────
    key_tfs = ["1d", "1w", "1m", "3m", "6m", "1y", "2y", "3y"]

    sector_header_cells = (
        "<th>Industry</th><th>Stocks</th><th>Sector Index</th>"
        "<th>Signal</th><th>Avg Score</th><th>💎</th>"
        "<th>Best Stock</th><th>Worst Stock</th>"
        + "".join(f"<th>%+{tf}</th>" for tf in key_tfs)
    )
    sector_rows_html = ""
    for _, r in sector_df.iterrows():
        cells = (
            f'<td><b>{r["Industry"]}</b></td>'
            f'<td>{r["Stocks"]}</td>'
            f'<td style="font-size:0.85em;color:#555">{r["Sector Index"]}</td>'
            f'<td class="signal-cell">{r["Signal"]}</td>'
            f'<td><b>{r["Score Label"]}</b></td>'
            f'<td>{r["Diamond #"]}</td>'
            f'<td style="color:#276749">{r["Best Stock"]} ({r["Best Score"]})</td>'
            f'<td style="color:#9b2c2c">{r["Worst Stock"]} ({r["Worst Score"]})</td>'
        )
        for tf in key_tfs:
            v = r.get(f"pct_{tf}")
            bg = _pct_color(v)
            disp = f"{v}%" if v is not None else "—"
            cells += f'<td style="background:{bg};text-align:center">{disp}</td>'
        sector_rows_html += f"<tr>{cells}</tr>\n"

    # ── Tab 1: Heatmap ────────────────────────────────────────────────────────
    heatmap_html = '<table class="heatmap-tbl">'
    heatmap_html += "<tr><th>Industry</th>" + "".join(f"<th>{t}</th>" for t in key_tfs) + "</tr>"
    for _, r in sector_df.iterrows():
        heatmap_html += f'<tr><td style="text-align:left;padding:4px 8px">{r["Industry"]}</td>'
        for tf in key_tfs:
            v = r.get(f"pct_{tf}")
            bg = _pct_color(v)
            disp = f"{v}%" if v is not None else "—"
            heatmap_html += f'<td style="background:{bg};text-align:center">{disp}</td>'
        heatmap_html += "</tr>"
    heatmap_html += "</table>"

    # ── Tab 3: All Stocks Flat Table ─────────────────────────────────────────
    flat_cols = (
        ["Symbol", "Industry", "Category", "Score Label", "Current Price"]
        + TF_LABELS
        + ["1m_vs_idx", "3m_vs_idx", "1y_vs_idx"]
    )
    def _flat_col_header(c):
        if c == "Score Label":   return "Score"
        if c == "1m_vs_idx":    return "1m vs Idx"
        if c == "3m_vs_idx":    return "3m vs Idx"
        if c == "1y_vs_idx":    return "1y vs Idx"
        return c
    flat_header = "".join(f"<th>{_flat_col_header(c)}</th>" for c in flat_cols)
    def _cat_chip_html(cat):
        """Wrap category text in a styled chip span."""
        cat = str(cat)
        if "Diamond"   in cat: cls = "cat-diamond"
        elif "Secular" in cat: cls = "cat-secular"
        elif "Turnaround" in cat: cls = "cat-turn"
        elif "Strong"  in cat: cls = "cat-strong"
        else:                  cls = "cat-other"
        return f'<span class="{cls}">{cat}</span>'

    def _score_chip_html(score_label):
        """Render score as a colored bold number."""
        try:
            n = int(str(score_label).split("/")[0])
        except Exception:
            return str(score_label)
        if n == 14:   color = "#22543d"; bg = "#c6f6d5"   # deep green
        elif n >= 11: color = "#276749"; bg = "#f0fff4"   # green
        elif n >= 8:  color = "#744210"; bg = "#fefcbf"   # amber
        else:         color = "#9b2c2c"; bg = "#fff5f5"   # red
        return (f'<span style="background:{bg};color:{color};font-weight:bold;'
                f'border-radius:4px;padding:2px 7px;font-size:.82em">{score_label}</span>')

    flat_rows_html = ""
    for _, row in stocks_df.iterrows():
        flat_rows_html += "<tr>"
        for i, col in enumerate(flat_cols):
            val = row.get(col, "")
            val_disp = "N/A" if val is None else val
            if col == "Category":
                flat_rows_html += f'<td>{_cat_chip_html(val_disp)}</td>'
            elif col == "Score Label":
                # data-order lets DataTables sort numerically on the raw score
                try:
                    sort_n = int(str(val_disp).split("/")[0])
                except Exception:
                    sort_n = 0
                flat_rows_html += f'<td data-order="{sort_n}">{_score_chip_html(val_disp)}</td>'
            else:
                style = _ret_color_style(val) if i >= 5 else ""
                flat_rows_html += f'<td style="{style}">{val_disp}</td>'
        flat_rows_html += "</tr>\n"

    # ── Tab 4: Rotation Quadrant (SVG) ───────────────────────────────────────
    W, H = 700, 500
    svg_circles = ""
    colors = ["#3182ce","#dd6b20","#38a169","#e53e3e","#805ad5",
              "#d69e2e","#00b5d8","#d53f8c","#2f855a","#c05621",
              "#2b6cb0","#b7791f","#285e61","#44337a","#9b2c2c",
              "#276749","#2c7a7b","#553c9a","#97266d","#744210"]
    for idx2, (_, r) in enumerate(sector_df.iterrows()):
        x = int(r["Long %"]  / 100 * (W - 100) + 50)
        y = int((1 - r["Short %"] / 100) * (H - 100) + 50)
        r_size = max(14, min(30, r["Stocks"] // 2))
        color  = colors[idx2 % len(colors)]
        label  = r["Industry"][:18]
        svg_circles += (
            f'<circle cx="{x}" cy="{y}" r="{r_size}" '
            f'fill="{color}" fill-opacity="0.7" stroke="#fff" stroke-width="1.5">'
            f'<title>{r["Industry"]}\nShort: {r["Short %"]}%  Long: {r["Long %"]}%\n'
            f'Signal: {r["Signal"]}</title></circle>'
            f'<text x="{x}" y="{y + r_size + 12}" text-anchor="middle" '
            f'font-size="10" fill="#333">{label}</text>'
        )

    quadrant_svg = f"""
    <svg width="{W}" height="{H}" style="border:1px solid #ddd;border-radius:8px;background:#fafafa">
      <!-- Quadrant dividers -->
      <line x1="{W//2}" y1="10" x2="{W//2}" y2="{H-10}" stroke="#ccc" stroke-dasharray="6,4"/>
      <line x1="10" y1="{H//2}" x2="{W-10}" y2="{H//2}" stroke="#ccc" stroke-dasharray="6,4"/>
      <!-- Quadrant labels -->
      <text x="20"      y="30"    fill="#38a169" font-size="12" font-weight="bold">🔥 Emerging</text>
      <text x="{W//2+10}" y="30" fill="#276749" font-size="12" font-weight="bold">✅ Leaders</text>
      <text x="20"      y="{H-15}" fill="#9b2c2c" font-size="12" font-weight="bold">❄️ Laggards</text>
      <text x="{W//2+10}" y="{H-15}" fill="#c05621" font-size="12" font-weight="bold">⚠️ Fading</text>
      <!-- Axis labels -->
      <text x="{W//2}" y="{H-2}" text-anchor="middle" fill="#666" font-size="11">Long-Term % Positive →</text>
      <text x="8" y="{H//2}" transform="rotate(-90,8,{H//2})" text-anchor="middle" fill="#666" font-size="11">↑ Short-Term % Positive</text>
      {svg_circles}
    </svg>"""

    # ── Embed stock data as JSON (for JS drill-down in Tab 2) ─────────────────
    stock_json_rows = []
    for _, row in stocks_df.iterrows():
        d = {
            "sym":   row["Symbol"],
            "ind":   row["Industry"],
            "cat":   row["Category"],
            "score": row["Score Label"],
            "price": row["Current Price"],
        }
        for lbl in TF_LABELS:
            d[lbl] = row.get(lbl)
        for tf in ["1m", "3m", "1y"]:
            d[f"{tf}v"] = row.get(f"{tf}_vs_idx")
        stock_json_rows.append(d)

    sector_json_rows = []
    for _, row in sector_df.iterrows():
        d = {
            "ind":    row["Industry"],
            "idx":    row["Sector Index"],
            "signal": row["Signal"],
            "score":  row["Score Label"],
            "short":  row["Short %"],
            "long":   row["Long %"],
        }
        for tf in TF_LABELS:
            d[f"idx_{tf}"] = row.get(f"idx_{tf}")
        sector_json_rows.append(d)

    industries_list = sorted(stocks_df["Industry"].unique().tolist())

    # ── Assemble full HTML ────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Sector Tracker — {gen_time}</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.css">
<link rel="stylesheet" href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #f0f4f8; color: #2d3748; }}
  .page-wrap {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
  h1 {{ text-align: center; color: #1a365d; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; color: #718096; margin-bottom: 20px; font-size: .93em; }}

  /* Tab nav */
  .tab-nav {{ display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }}
  .tab-btn {{
    padding: 10px 22px; border: none; border-radius: 8px; cursor: pointer;
    font-weight: 600; background: #e2e8f0; color: #2d3748; font-size: .9em;
    transition: background .2s;
  }}
  .tab-btn.active {{ background: #2c5282; color: #fff; }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}

  /* Cards */
  .card {{ background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,.08); margin-bottom: 20px; }}

  /* Table base */
  table.dataTable thead th {{ background: #2a4365 !important; color: #fff !important; cursor: pointer; }}
  .positive {{ color: #276749 !important; font-weight: bold; }}
  .negative {{ color: #9b2c2c !important; font-weight: bold; }}

  /* Sector overview */
  .signal-cell {{ font-size: .85em; white-space: nowrap; }}
  #sectorTable th, #sectorTable td {{ white-space: nowrap; }}
  .heatmap-tbl {{ border-collapse: collapse; width: 100%; font-size: .82em; }}
  .heatmap-tbl th, .heatmap-tbl td {{ border: 1px solid #e2e8f0; padding: 5px 8px; text-align: center; white-space: nowrap; }}
  .heatmap-tbl th {{ background: #2a4365; color: #fff; }}

  /* Drill-down */
  .industry-select {{ padding: 8px 14px; border: 1px solid #cbd5e0; border-radius: 6px;
                      font-size: 1em; min-width: 280px; margin-right: 10px; }}
  #drillIndexBanner {{ background: #ebf8ff; border-left: 4px solid #3182ce;
                       padding: 10px 16px; border-radius: 4px; margin-bottom: 14px; font-size: .9em; }}
  #drillTable {{ width: 100% !important; }}
  #drillTable th, #drillTable td {{
    font-size: .82em; padding: 5px 10px;
    white-space: nowrap;    /* prevent wrapping so columns stay aligned */
    text-align: center;
  }}
  #drillTable td:first-child {{ text-align: left; }}   /* Symbol left-aligned */
  #drillTable td:nth-child(2) {{ text-align: left; font-size: .78em; }} /* Category */

  /* Flat table */
  #flatTable {{ width: 100% !important; }}
  #flatTable th, #flatTable td {{
    font-size: .8em; padding: 5px 10px;
    white-space: nowrap;
    text-align: center;
  }}
  #flatTable td:first-child  {{ text-align: left; font-weight: bold; }}  /* Symbol */
  #flatTable td:nth-child(2) {{ text-align: left; font-size: .78em; }}   /* Industry */
  #flatTable td:nth-child(3) {{ text-align: left; font-size: .78em; }}   /* Category */

  /* Category chips */
  .cat-diamond {{ background:#ebf8ff;color:#2c5282;border-radius:12px;padding:2px 9px;font-size:.78em;font-weight:bold;white-space:nowrap; }}
  .cat-secular  {{ background:#f0fff4;color:#22543d;border-radius:12px;padding:2px 9px;font-size:.78em;font-weight:bold;white-space:nowrap; }}
  .cat-turn     {{ background:#fff5f5;color:#822727;border-radius:12px;padding:2px 9px;font-size:.78em;font-weight:bold;white-space:nowrap; }}
  .cat-strong   {{ background:#fefcbf;color:#744210;border-radius:12px;padding:2px 9px;font-size:.78em;font-weight:bold;white-space:nowrap; }}
  .cat-other    {{ background:#f7fafc;color:#4a5568;border-radius:12px;padding:2px 9px;font-size:.78em;white-space:nowrap; }}

  .fixedHeader-floating {{ top:0!important; }}
</style>
</head>
<body>
<div class="page-wrap">
  <h1>📊 NSE Sector Momentum Tracker</h1>
  <div class="subtitle">Nifty500 · 20 Industries · 14 Timeframes · Generated: {gen_time} ({mode.upper()})</div>

  <!-- Tab navigation -->
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('overview', this)">🗺️ Sector Overview</button>
    <button class="tab-btn"        onclick="switchTab('drilldown',this)">🔍 Industry Drill-Down</button>
    <button class="tab-btn"        onclick="switchTab('allstocks',this)">📋 All Stocks</button>
    <button class="tab-btn"        onclick="switchTab('rotation', this)">🔄 Rotation Map</button>
  </div>

  <!-- ════ TAB 1: Sector Overview ══════════════════════════════════════════ -->
  <div id="tab-overview" class="tab-pane active">
    <div class="card">
      <h3 style="margin-top:0">📊 Sector Heatmap — % Stocks Positive per Timeframe</h3>
      <p style="font-size:.82em;color:#718096">Green = >70% stocks positive · Yellow = ~50% · Red = <30%</p>
      {heatmap_html}
    </div>
    <div class="card">
      <h3 style="margin-top:0">🏆 Sector Rankings</h3>
      <table id="sectorTable" class="display" style="width:100%">
        <thead><tr>{sector_header_cells}</tr></thead>
        <tbody>{sector_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- ════ TAB 2: Industry Drill-Down ════════════════════════════════════ -->
  <div id="tab-drilldown" class="tab-pane">
    <div class="card">
      <label style="font-weight:600;margin-right:10px">Select Industry:</label>
      <select class="industry-select" id="industrySelect" onchange="renderDrill()">
        {"".join(f'<option value="{ind}">{ind}</option>' for ind in industries_list)}
      </select>
      <div id="drillIndexBanner"></div>
      <table id="drillTable" class="display" style="width:100%;margin-top:10px">
        <thead><tr id="drillHeader"></tr></thead>
        <tbody id="drillBody"></tbody>
      </table>
    </div>
  </div>

  <!-- ════ TAB 3: All Stocks Flat ════════════════════════════════════════ -->
  <div id="tab-allstocks" class="tab-pane">
    <div class="card">
      <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap" id="catFilters">
        <button class="tab-btn active" onclick="filterFlat('all',this)">All</button>
        <button class="tab-btn" onclick="filterFlat('Diamond',this)">💎 Diamond</button>
        <button class="tab-btn" onclick="filterFlat('Secular',this)">🚀 Secular</button>
        <button class="tab-btn" onclick="filterFlat('Turnaround',this)">🔄 Turnaround</button>
        <button class="tab-btn" onclick="filterFlat('Strong',this)">📈 Strong</button>
      </div>
      <table id="flatTable" class="display" style="width:100%">
        <thead><tr>{flat_header}</tr></thead>
        <tbody>{flat_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- ════ TAB 4: Rotation Map ════════════════════════════════════════════ -->
  <div id="tab-rotation" class="tab-pane">
    <div class="card">
      <h3 style="margin-top:0">🔄 Sector Rotation Quadrant</h3>
      <p style="font-size:.85em;color:#718096">
        X-axis = % stocks positive in 1y/2y/3y (long-term) ·
        Y-axis = % stocks positive in 1w/1m/3m (short-term) ·
        Circle size ∝ number of stocks
      </p>
      {quadrant_svg}
    </div>
    <div class="card">
      <h3 style="margin-top:0">Signal Legend</h3>
      <table style="width:auto;border-collapse:collapse;font-size:.9em">
        <tr><td style="padding:4px 12px">✅ Leader</td><td>High short-term AND long-term momentum</td></tr>
        <tr><td style="padding:4px 12px">🔥 Heating Up</td><td>Short-term surging, long-term lagging</td></tr>
        <tr><td style="padding:4px 12px">🌡️ Warming</td><td>Short-term green but long-term mixed</td></tr>
        <tr><td style="padding:4px 12px">⚠️ Cooling</td><td>Long-term strong but short-term fading</td></tr>
        <tr><td style="padding:4px 12px">🔄 Turnaround</td><td>Short-term improving from long-term weakness</td></tr>
        <tr><td style="padding:4px 12px">❄️ Cold</td><td>Weak across both short and long term</td></tr>
      </table>
    </div>
  </div>
</div><!-- /page-wrap -->

<!-- ════ JavaScript ══════════════════════════════════════════════════════════ -->
<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.js"></script>
<script src="https://cdn.datatables.net/fixedheader/3.2.2/js/dataTables.fixedHeader.min.js"></script>
<script>
// ── Embedded data ──────────────────────────────────────────────────────────
const STOCK_DATA  = {json.dumps(stock_json_rows)};
const SECTOR_DATA = {json.dumps(sector_json_rows)};
const TF_LABELS   = {json.dumps(TF_LABELS)};

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(name, btn) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn' ).forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'drilldown' && !window._drillInit) {{ renderDrill(); window._drillInit = true; }}
  if (name === 'allstocks' && !window._flatInit)  {{ initFlat();   window._flatInit  = true; }}
}}

// ── Tab 1: Sector Overview Table (DataTables) ─────────────────────────────
$(document).ready(function() {{
  $('#sectorTable').DataTable({{
    pageLength: 25,
    order: [[4, 'desc']],
    scrollX: true,
    scrollCollapse: true,
    autoWidth: false,
    fixedHeader: true,
    columnDefs: [
      {{ targets: '_all',  className: 'dt-center' }},
      {{ targets: [0,2,3], className: 'dt-left'   }}
    ]
  }});
}});

// ── Tab 2: Drill-Down ─────────────────────────────────────────────────────
let drillDT = null;

function renderDrill() {{
  const ind  = document.getElementById('industrySelect').value;
  const rows = STOCK_DATA.filter(r => r.ind === ind);
  const sec  = SECTOR_DATA.find(s => s.ind === ind) || {{}};

  // STEP 1: destroy DataTable FIRST — before any innerHTML changes
  // (DataTables moves thead/tbody into its own wrapper; touching innerHTML
  //  while it's active corrupts the DOM and the dropdown stops working)
  if (drillDT) {{
    drillDT.destroy();
    drillDT = null;
  }}

  // STEP 2: rebuild banner
  let bannerHtml = `<b>Sector Index Benchmark: ${{sec.idx || '—'}}</b> &nbsp;|&nbsp; `;
  ['1m','3m','1y'].forEach(tf => {{
    const v = sec['idx_' + tf];
    const disp = (v !== null && v !== undefined) ? v : null;
    if (disp !== null) {{
      const cls = disp > 0 ? 'positive' : 'negative';
      bannerHtml += `${{tf}}: <span class="${{cls}}">${{disp > 0 ? '+' : ''}}${{disp}}%</span> &nbsp; `;
    }} else {{
      bannerHtml += `${{tf}}: <span style="color:#999">N/A</span> &nbsp; `;
    }}
  }});
  bannerHtml += `&nbsp;|&nbsp; Signal: <b>${{sec.signal || '—'}}</b>`;
  document.getElementById('drillIndexBanner').innerHTML = bannerHtml;

  // STEP 3: rebuild header + body
  const hdrCols = ['Symbol','Category','Score','Price (₹)', ...TF_LABELS, '1m vs Idx','3m vs Idx','1y vs Idx'];
  document.getElementById('drillHeader').innerHTML = hdrCols.map(c => `<th>${{c}}</th>`).join('');

  const fmt = (v, suffix='%') => {{
    if (v === null || v === undefined) return '<span style="color:#aaa">N/A</span>';
    const style = v > 0 ? 'color:#276749;font-weight:bold' : 'color:#9b2c2c;font-weight:bold';
    return `<span style="${{style}}">${{v > 0 ? '+' : ''}}${{v}}${{suffix}}</span>`;
  }};

  const catChip = cat => {{
    if (!cat) return '<span class="cat-other">—</span>';
    if (cat.includes('Diamond'))    return `<span class="cat-diamond">${{cat}}</span>`;
    if (cat.includes('Secular'))    return `<span class="cat-secular">${{cat}}</span>`;
    if (cat.includes('Turnaround')) return `<span class="cat-turn">${{cat}}</span>`;
    if (cat.includes('Strong'))     return `<span class="cat-strong">${{cat}}</span>`;
    return `<span class="cat-other">${{cat}}</span>`;
  }};

  const scoreChip = sl => {{
    if (!sl) return sl;
    const n = parseInt(sl);
    let bg, fg;
    if (n === 14)      {{ bg='#c6f6d5'; fg='#22543d'; }}
    else if (n >= 11)  {{ bg='#f0fff4'; fg='#276749'; }}
    else if (n >= 8)   {{ bg='#fefcbf'; fg='#744210'; }}
    else               {{ bg='#fff5f5'; fg='#9b2c2c'; }}
    return `<span style="background:${{bg}};color:${{fg}};font-weight:bold;border-radius:4px;padding:2px 7px;font-size:.82em">${{sl}}</span>`;
  }};

  document.getElementById('drillBody').innerHTML = rows.map(r => {{
    let cells = `<td><b>${{r.sym}}</b></td>`;
    cells += `<td>${{catChip(r.cat)}}</td>`;
    const scoreN = parseInt(r.score) || 0;
    cells += `<td data-order="${{scoreN}}">${{scoreChip(r.score)}}</td>`;
    cells += `<td>₹${{r.price}}</td>`;
    TF_LABELS.forEach(tf => {{ cells += `<td>${{fmt(r[tf])}}</td>`; }});
    ['1m','3m','1y'].forEach(tf => {{ cells += `<td>${{fmt(r[tf + 'v'])}}</td>`; }});
    return `<tr>${{cells}}</tr>`;
  }}).join('');

  // STEP 4: init fresh DataTable on clean DOM
  drillDT = $('#drillTable').DataTable({{
    pageLength: 50,
    order: [[2, 'desc']],
    scrollX: true,
    scrollCollapse: true,
    autoWidth: false,
    fixedHeader: true,
    destroy: true,
    columnDefs: [
      {{ targets: '_all',     className: 'dt-center' }},
      {{ targets: [0,1],      className: 'dt-left' }}
    ]
  }});
}}

// ── Tab 3: Flat All-Stocks (DataTables) ──────────────────────────────────
let flatDT = null;

function initFlat() {{
  flatDT = $('#flatTable').DataTable({{
    pageLength: 100,
    order: [[3,'desc']],
    scrollX: true,
    scrollCollapse: true,
    autoWidth: false,
    fixedHeader: true,
    columnDefs: [
      {{ targets: '_all',   className: 'dt-center' }},
      {{ targets: [0,1,2],  className: 'dt-left' }}
    ]
  }});
}}

function filterFlat(cat, btn) {{
  document.querySelectorAll('#catFilters .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (!flatDT) initFlat();
  flatDT.column(2).search(cat === 'all' ? '' : cat).draw();
}}

// Colour return cells in flat table on page load
$(document).ready(function() {{
  document.querySelectorAll('#flatTable tbody td').forEach(td => {{
    const txt = td.textContent.trim();
    if (txt.endsWith('%')) {{
      const v = parseFloat(txt);
      if (!isNaN(v)) td.style.color = v > 0 ? '#276749' : '#9b2c2c';
    }}
  }});
}});
</script>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nDashboard saved: {filepath}")
    return filepath


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _format_morning_message(sector_df):
    now   = datetime.datetime.now().strftime("%d %b %Y")
    top3  = sector_df.head(3)
    bot3  = sector_df.tail(3)

    top_lines = "\n".join(
        f"  {i+1}. {r['Industry'][:22]:22s} — {r['Score Label']} | {r['Signal']}"
        for i, (_, r) in enumerate(top3.iterrows())
    )
    bot_lines = "\n".join(
        f"  {i+1}. {r['Industry'][:22]:22s} — {r['Score Label']} | {r['Signal']}"
        for i, (_, r) in enumerate(bot3.iterrows())
    )

    heating = sector_df[sector_df["Signal"].str.contains("Heating|Warming", na=False)]
    cooling = sector_df[sector_df["Signal"].str.contains("Cooling", na=False)]
    diamonds_total = int(sector_df["Diamond #"].sum())

    heat_text = ", ".join(heating["Industry"].tolist()) or "None"
    cool_text = ", ".join(cooling["Industry"].tolist()) or "None"

    return (
        f"📊 *SECTOR MORNING REPORT — {now}*\n\n"
        f"🔥 *Top Sectors:*\n{top_lines}\n\n"
        f"❄️ *Weak Sectors:*\n{bot_lines}\n\n"
        f"🌡️ *Heating Up:* {heat_text}\n"
        f"⚠️ *Cooling Down:* {cool_text}\n\n"
        f"💎 Total Diamond Stocks: {diamonds_total}"
    )


def _format_eod_message(sector_df, stocks_df):
    now       = datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    leaders   = sector_df[sector_df["Signal"] == "✅ Leader"]["Industry"].tolist()
    cold      = sector_df[sector_df["Signal"] == "❄️ Cold"]["Industry"].tolist()
    diamonds  = stocks_df[stocks_df["Score"] == 14]["Symbol"].tolist()
    new_diams = ", ".join(diamonds[:10]) if diamonds else "None"
    top5 = sector_df.head(5)[["Industry", "Score Label", "Signal"]]

    ranking = "\n".join(
        f"  {i+1}. {r['Industry'][:22]:22s} {r['Score Label']} {r['Signal']}"
        for i, (_, r) in enumerate(top5.iterrows())
    )
    return (
        f"📊 *SECTOR EOD REPORT — {now}*\n\n"
        f"🏆 *Top 5 by Momentum:*\n{ranking}\n\n"
        f"✅ *Leaders:* {', '.join(leaders) or 'None'}\n"
        f"❄️ *Cold:* {', '.join(cold) or 'None'}\n\n"
        f"💎 *Diamond Stocks ({len(diamonds)}):* {new_diams}"
    )


def send_telegram(text, filepath=None):
    """Send a Telegram message and optionally attach the HTML report."""
    if not TELEGRAM_AVAILABLE:
        print("[Telegram] Library not available — skipping.")
        return
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] BOT_TOKEN / CHAT_ID not set in .env — skipping.")
        return
    try:
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")
        if filepath and os.path.exists(filepath):
            with open(filepath, "rb") as f:
                bot.send_document(TELEGRAM_CHAT_ID, f,
                                  caption="📎 Full sector report attached.")
        print("[Telegram] Message sent.")
    except Exception as e:
        print(f"[Telegram] Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED JOB RUNNER
# ══════════════════════════════════════════════════════════════════════════════

_job_running = False   # set True while a run is active (silences the ticker)


def _fmt_eta(seconds: int) -> str:
    """Human-readable countdown from a number of seconds."""
    if seconds < 0:
        return "overdue"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"


def _status_ticker(scheduler):
    """
    Background thread: every 60 s print a heartbeat showing next-run times.
    Stays silent while a job is already executing (_job_running = True).
    """
    global _job_running
    while True:
        time.sleep(60)
        if _job_running:
            continue
        try:
            if not IST:
                continue
            now  = datetime.datetime.now(IST)
            jobs = scheduler.get_jobs()
            if not jobs:
                continue
            print(f"\n┌─ [{now.strftime('%d %b %Y  %H:%M:%S IST')}] Scheduler heartbeat")
            for job in jobs:
                nxt = job.next_run_time
                if nxt:
                    secs = int((nxt - now).total_seconds())
                    eta  = _fmt_eta(secs)
                    print(f"│  ⏰  {job.name:22s}  →  {nxt.strftime('%H:%M IST')}  "
                          f"(in {eta})")
            print("└─ Ctrl+C to stop\n")
        except Exception:
            pass


def run_job(mode="morning"):
    """
    Full pipeline for one run — called by scheduler or directly.
    mode: 'morning' | 'eod'
    """
    global _job_running
    _job_running = True
    t_start = time.time()

    now_str = datetime.datetime.now().strftime("%d %b %Y  %H:%M:%S")
    print(f"\n{'━'*60}")
    print(f"  🚀  SECTOR TRACKER V2  |  {mode.upper()} RUN  |  {now_str}")
    print(f"{'━'*60}")
    print(f"  Phase 1 of 4 › Loading Nifty500 CSV …")

    task_id = f"sector_v2_{mode}_{datetime.datetime.now().strftime('%H%M')}"

    # ── Phase 1: Load CSV ──────────────────────────────────────────────────────
    industry_map, sym_to_ind, all_stocks = load_nifty500()
    print(f"  ✔  {len(all_stocks)} stocks across {len(industry_map)} industries")
    update_progress(task_id, 0, len(all_stocks), "downloading",
                    log=f"📋 Loaded CSV: {len(all_stocks)} stocks · {len(industry_map)} industries")

    # ── Phase 2: Fetch prices ─────────────────────────────────────────────────
    total_syms = len(all_stocks) + len(ALL_INDEX_TICKERS)
    _append_log(task_id, f"⏬ Fetching {len(all_stocks)} stocks + {len(ALL_INDEX_TICKERS)} indices …")
    print(f"\n  Phase 2 of 4 › Fetching prices ({len(all_stocks)} stocks + {len(ALL_INDEX_TICKERS)} indices) …")
    print(f"  (bulk yfinance  →  Stooq fallback  →  parquet cache)\n")

    # Pass _append_log as the logger so per-batch progress appears in the dashboard
    def _dash_logger(msg):
        # Filter to key summary lines to avoid flooding the 12-line log box
        msg_stripped = msg.strip()
        if any(k in msg_stripped for k in [
            "Cache hits", "Need fetch", "Bulk yfinance", "Per-ticker fallback",
            "✅ Stocks ready", "✗", "⚠", "BATCH_DOWNLOAD"
        ]):
            _append_log(task_id, msg_stripped)

    stock_data, index_data = fetch_price_matrices(
        all_stocks, INDEX_QUERY_NAME, years=6, logger=_dash_logger
    )

    if stock_data.empty:
        print("  ✗  No data returned. Aborting.")
        update_progress(task_id, 0, total_syms, "error", error="No data returned from fetch")
        _job_running = False
        return

    got_stocks  = [c for c in stock_data.columns if c in set(all_stocks)]
    missing     = [s for s in all_stocks if s not in stock_data.columns]
    print(f"\n  ✔  Data ready: {len(got_stocks)} stocks, {len(index_data.columns)} indices")

    # ── Log fetch summary with success / fail counts ──────────────────────────
    _append_log(task_id,
        f"✅ Fetch done: ✓{len(got_stocks)} success · ✗{len(missing)} failed · "
        f"{len(index_data.columns)} indices")
    if missing:
        sample = ", ".join(s.replace(".NS","") for s in missing[:6])
        extra  = f" +{len(missing)-6} more" if len(missing) > 6 else ""
        _append_log(task_id, f"⚠ Failed/delisted: {sample}{extra}")
        print(f"  ⚠  Missing/delisted ({len(missing)}): "
              f"{', '.join(missing[:8])}{'…' if len(missing)>8 else ''}")

    update_progress(task_id, total_syms, total_syms, "downloaded")

    # ── Phase 3: Momentum analysis ────────────────────────────────────────────
    print(f"\n  Phase 3 of 4 › Calculating momentum for {len(got_stocks)} stocks …")
    _append_log(task_id, f"🔢 Analysing momentum for {len(got_stocks)} stocks …")
    last_date = stock_data.index[-1]

    # pre-compute sector index returns
    index_returns = {}
    for idx_sym in ALL_INDEX_TICKERS:
        if idx_sym in index_data.columns:
            ret, _ = calc_returns(index_data[idx_sym], last_date)
            index_returns[idx_sym] = ret
        else:
            index_returns[idx_sym] = {lbl: None for lbl in TF_LABELS}

    # per-stock momentum
    stock_results = []
    total = len(all_stocks)
    update_progress(task_id, 0, total, "analyzing",
                    log=f"📊 Starting per-stock scoring (data up to {last_date}) …")

    for i, sym in enumerate(tqdm(all_stocks, desc="  Momentum", ncols=72,
                                  bar_format="  {l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")):
        if i % 50 == 0 and i > 0:
            update_progress(task_id, i, total, "analyzing",
                            log=f"📊 Scored {i}/{total} stocks …")
        if sym not in stock_data.columns:
            continue
        returns, curr_price = calc_returns(stock_data[sym], last_date)
        if curr_price is None:
            continue
        green    = score_from_returns(returns)
        cat      = categorise(green, returns)
        industry = sym_to_ind.get(sym, "Unknown")
        idx_tick = INDUSTRY_INDEX_MAP.get(industry, "^NSEI")
        idx_ret  = index_returns.get(idx_tick, {})
        row = {
            "Symbol":        sym.replace(".NS", ""),
            "Industry":      industry,
            "Sector Index":  INDEX_DISPLAY.get(idx_tick, idx_tick),
            "Current Price": round(curr_price, 2),
            "Score":         green,
            "Score Label":   f"{green}/14",
            "Category":      cat,
        }
        for lbl in TF_LABELS:
            row[lbl] = returns.get(lbl)
        for tf in ["1m", "3m", "1y"]:
            s = returns.get(tf)
            b = idx_ret.get(tf)
            row[f"{tf}_vs_idx"] = round(s - b, 2) if (s is not None and b is not None) else None
        stock_results.append(row)

    stocks_df = pd.DataFrame(stock_results)
    sector_df = aggregate_sectors(stocks_df, index_returns)

    diamonds_count = int(sector_df["Diamond #"].sum()) if "Diamond #" in sector_df.columns else 0
    update_progress(task_id, total, total, "completed",
                    log=f"✅ Done: {len(stocks_df)} scored · {len(missing)} failed · "
                        f"{len(sector_df)} sectors · 💎{diamonds_count} diamonds")

    # quick sector summary in terminal
    print(f"\n  ✔  Analysis complete: {len(stocks_df)} stocks | {len(sector_df)} sectors")
    print(f"\n  {'Industry':<34} {'Signal':<22} {'Score':>5}")
    print(f"  {'─'*65}")
    for _, r in sector_df.head(6).iterrows():
        print(f"  {r['Industry'][:34]:<34} {r['Signal']:<22} {r['Score Label']:>5}")
    print(f"  {'─'*65}")
    diamonds_total = int(sector_df["Diamond #"].sum())
    print(f"  💎 Diamond stocks total: {diamonds_total}")

    # ── Phase 4: Generate HTML + Telegram ────────────────────────────────────
    print(f"\n  Phase 4 of 4 › Generating HTML dashboard …")
    html_path = generate_html(stocks_df, sector_df, index_returns, mode)

    if mode == "morning":
        msg = _format_morning_message(sector_df)
        send_telegram(msg)
    else:
        msg = _format_eod_message(sector_df, stocks_df)
        send_telegram(msg, html_path)

    elapsed = time.time() - t_start
    m, s    = divmod(int(elapsed), 60)
    print(f"\n{'━'*60}")
    print(f"  ✅  Done in {m}m {s:02d}s  |  Report: {html_path}")
    print(f"{'━'*60}\n")
    _job_running = False


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULER  (APScheduler + IST timezone)
# ══════════════════════════════════════════════════════════════════════════════

def start_scheduler():
    if not SCHEDULER_AVAILABLE:
        print("[ERROR] APScheduler not installed. Run: pip install apscheduler pytz")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=IST)

    # 8:55 AM IST, Mon–Fri
    scheduler.add_job(
        run_job, CronTrigger(hour=8, minute=55, day_of_week="mon-fri", timezone=IST),
        kwargs={"mode": "morning"}, id="morning_run", name="Morning Snapshot"
    )
    # 3:15 PM IST, Mon–Fri
    scheduler.add_job(
        run_job, CronTrigger(hour=15, minute=15, day_of_week="mon-fri", timezone=IST),
        kwargs={"mode": "eod"}, id="eod_run", name="EOD Snapshot"
    )

    # ── Print startup banner with first next-run times ───────────────────────
    now = datetime.datetime.now(IST)
    print(f"\n{'━'*60}")
    print(f"  📡  SECTOR TRACKER V2  —  Scheduler started")
    print(f"  🕐  Current time : {now.strftime('%d %b %Y  %H:%M:%S IST')}")
    print(f"{'━'*60}")

    for job in scheduler.get_jobs():
        nxt  = job.next_run_time
        secs = int((nxt - now).total_seconds()) if nxt else -1
        eta  = _fmt_eta(secs)
        print(f"  ⏰  {job.name:24s} → {nxt.strftime('%d %b  %H:%M IST') if nxt else 'N/A'}"
              f"  (in {eta})")

    print(f"\n  Status updates print every 60 s  •  Ctrl+C to stop")
    print(f"{'━'*60}\n")

    # ── Background ticker thread ──────────────────────────────────────────────
    ticker = threading.Thread(target=_status_ticker, args=(scheduler,), daemon=True)
    ticker.start()

    scheduler.start()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE Sector Momentum Tracker V2")
    parser.add_argument(
        "--mode", choices=["morning", "eod", "full"],
        default="full",
        help="Run mode: morning | eod | full (default: full)"
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Start the APScheduler daemon (8:55 AM + 3:15 PM IST, Mon-Fri)"
    )
    args = parser.parse_args()

    if args.schedule:
        start_scheduler()
    else:
        run_job(mode=args.mode)
