#!/usr/bin/env python3
"""
NSE-focused historical data provider with local parquet caching.

Data source priority
--------------------
  Stocks  : 1. Stooq (pandas-datareader)  — fast, no key, .NS format
             2. jugaad-trader              — NSE official, free
             3. local parquet cache        — last-resort fallback

  Indices : 1. nsepython index_history()  — NSE official index data
             2. yfinance (^CNX* tickers)  — fallback
             3. local parquet cache       — last-resort fallback

Caching layer is unchanged — every successful fetch is saved as
.parquet under cache/sector_tracker/ for instant re-use on next run.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Callable

import pandas as pd

# ── Stooq via pandas-datareader (stocks — primary) ────────────────────────────
STOOQ_AVAILABLE = False
try:
    from pandas_datareader import data as pdr
    STOOQ_AVAILABLE = True
except Exception:
    pass

# ── jugaad-trader (stocks — fallback) ─────────────────────────────────────────
JUGAAD_AVAILABLE = False
try:
    from jugaad_data.nse import stock_df as jugaad_stock_df
    JUGAAD_AVAILABLE = True
except Exception:
    pass

# ── nsepython (indices — primary) ─────────────────────────────────────────────
NSEPYTHON_AVAILABLE = False
try:
    from nsepython import index_history as nse_index_history
    NSEPYTHON_AVAILABLE = True
except Exception:
    pass

# ── yfinance (indices — fallback) ─────────────────────────────────────────────
YFINANCE_AVAILABLE = False
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except Exception:
    pass

# Legacy nselib — no longer primary, kept so old cache files remain valid
NSELIB_AVAILABLE   = False
NSELIB_IMPORT_ERROR = None


# ── .env / environment toggle ─────────────────────────────────────────────────
# Set BATCH_DOWNLOAD=false in your .env (or shell) to disable bulk yfinance
# and fall back to the per-ticker Stooq → jugaad → yfinance chain instead.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except Exception:
    pass
import os as _os
BATCH_DOWNLOAD: bool = _os.getenv("BATCH_DOWNLOAD", "true").strip().lower() not in ("false", "0", "no")

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache" / "sector_tracker"
REQUEST_PAUSE = 0.15
REFRESH_OVERLAP_DAYS = 7


def _log(message: str, logger: Callable[[str], None] | None = None) -> None:
    if logger:
        logger(message)
    else:
        print(message)


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_key(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.upper()).strip("_")


def _cache_file(kind: str, key: str) -> Path:
    return CACHE_DIR / kind / f"{_safe_key(key)}.parquet"


def _read_cache(kind: str, key: str) -> pd.Series | None:
    path = _cache_file(kind, key)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty or "close" not in df.columns:
        return None
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce")
        series = pd.Series(df["close"].values, index=dates, name=key)
    else:
        series = pd.Series(df["close"].values, index=pd.to_datetime(df.index), name=key)
    series = series.dropna()
    if series.empty:
        return None
    series.index = pd.to_datetime(series.index).normalize()
    return series.sort_index()


def _write_cache(kind: str, key: str, series: pd.Series) -> None:
    path = _cache_file(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {"date": pd.to_datetime(series.index).normalize(), "close": pd.to_numeric(series.values)}
    )
    frame.to_parquet(path, index=False)


def _merge_cache(existing: pd.Series | None, incoming: pd.Series | None, key: str) -> pd.Series | None:
    frames = []
    if existing is not None and not existing.empty:
        frames.append(existing.rename(key))
    if incoming is not None and not incoming.empty:
        frames.append(incoming.rename(key))
    if not frames:
        return None
    merged = pd.concat(frames).sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]
    merged = merged.dropna()
    merged.name = key
    return merged if not merged.empty else None


def _format_date(value: dt.date) -> str:
    return value.strftime("%d-%m-%Y")


def _find_date_column(df: pd.DataFrame) -> str | None:
    exact = ["Date", "DATE", "HistoricalDate", "TIMESTAMP"]
    for col in exact:
        if col in df.columns:
            return col
    for col in df.columns:
        if "date" in str(col).lower():
            return col
    return None


def _find_close_column(df: pd.DataFrame) -> str | None:
    exact = [
        "Close Price",
        "CLOSE_PRICE",
        "Close",
        "close",
        "Closing Price",
        "CH_CLOSING_PRICE",
        "Index Close",
        "Closing Index Value",
        "Close Index Value",
    ]
    for col in exact:
        if col in df.columns:
            return col
    for col in df.columns:
        name = str(col).lower()
        if "close" in name and "%" not in name:
            return col
    return None


def _normalize_history(raw: pd.DataFrame, key: str) -> pd.Series | None:
    if raw is None or raw.empty:
        return None
    date_col = _find_date_column(raw)
    close_col = _find_close_column(raw)
    if not date_col or not close_col:
        return None
    dates = pd.to_datetime(raw[date_col], errors="coerce", dayfirst=True)
    closes = pd.to_numeric(raw[close_col], errors="coerce")
    series = pd.Series(closes.values, index=dates, name=key).dropna()
    if series.empty:
        return None
    series.index = pd.to_datetime(series.index).normalize()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series if not series.empty else None


def _required_start_date(existing: pd.Series | None, years: int) -> dt.date:
    today = dt.date.today()
    lookback = today - dt.timedelta(days=365 * years)
    if existing is None or existing.empty:
        return lookback
    last_cached = existing.index.max().date()
    refresh_start = last_cached - dt.timedelta(days=REFRESH_OVERLAP_DAYS)
    return max(lookback, refresh_start)


def _fetch_stock_history(symbol: str, start: dt.date, end: dt.date) -> pd.Series | None:
    """
    Fetch stock close-price history.

    Layer 1 — Stooq (pandas-datareader)   no API key, .NS format, fast
    Layer 2 — jugaad-trader               NSE official data
    Layer 3 — yfinance                    last resort, same .NS format
    """
    errors = {}

    # ── Layer 1: Stooq ────────────────────────────────────────────────────────
    if STOOQ_AVAILABLE:
        try:
            raw = pdr.DataReader(symbol, "stooq", start=start, end=end)
            if raw is not None and not raw.empty:
                close_col = next((c for c in raw.columns if "close" in c.lower()), None)
                if close_col:
                    series = raw[close_col].rename(symbol).sort_index()
                    series.index = pd.to_datetime(series.index).normalize()
                    series = series.dropna()
                    if not series.empty:
                        time.sleep(0.15)
                        return series
                    errors["stooq"] = "empty after dropna"
                else:
                    errors["stooq"] = f"no close col in {list(raw.columns)}"
            else:
                errors["stooq"] = "empty DataFrame"
        except Exception as e:
            errors["stooq"] = str(e)
    else:
        errors["stooq"] = "pandas-datareader not installed"

    # ── Layer 2: jugaad-trader ────────────────────────────────────────────────
    if JUGAAD_AVAILABLE:
        try:
            raw = jugaad_stock_df(
                symbol=symbol.replace(".NS", ""),
                from_date=start,
                to_date=end,
                series="EQ",
            )
            series = _normalize_history(pd.DataFrame(raw), symbol)
            if series is not None and not series.empty:
                time.sleep(0.3)
                return series
            errors["jugaad"] = "empty after normalize"
        except Exception as e:
            errors["jugaad"] = str(e)
    else:
        errors["jugaad"] = "jugaad-data not installed"

    # ── Layer 3: yfinance (last resort) ──────────────────────────────────────
    if YFINANCE_AVAILABLE:
        try:
            raw = yf.download(
                symbol, start=start, end=end,
                progress=False, auto_adjust=True
            )
            if raw is not None and not raw.empty:
                close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
                series = close.rename(symbol)
                series.index = pd.to_datetime(series.index).normalize()
                series = series.dropna()
                if not series.empty:
                    time.sleep(0.5)
                    return series
                errors["yfinance"] = "empty after dropna"
            else:
                errors["yfinance"] = "empty DataFrame"
        except Exception as e:
            errors["yfinance"] = str(e)
    else:
        errors["yfinance"] = "yfinance not installed"

    raise RuntimeError(f"All sources failed for {symbol} | " +
                       " | ".join(f"{k}: {v}" for k, v in errors.items()))


def _fetch_index_history(index_name: str, cache_key: str, start: dt.date, end: dt.date) -> pd.Series | None:
    """
    Fetch NSE sector index history.

    Layer 1 — nsepython index_history()
        Pulls directly from NSE's own index endpoint. Most accurate.

    Layer 2 — yfinance
        Used for any index nsepython cannot serve (e.g. ^NSEI).
    """
    # ── Layer 1: nsepython ────────────────────────────────────────────────────
    if NSEPYTHON_AVAILABLE:
        try:
            raw = nse_index_history(
                symbol=index_name,
                start_date=start.strftime("%d-%m-%Y"),
                end_date=end.strftime("%d-%m-%Y"),
            )
            series = _normalize_history(pd.DataFrame(raw), cache_key)
            if series is not None and not series.empty:
                time.sleep(0.3)
                return series
        except Exception:
            pass

    # ── Layer 2: yfinance ─────────────────────────────────────────────────────
    if YFINANCE_AVAILABLE:
        try:
            ticker = cache_key                    # cache_key is the ^CNX* symbol
            raw = yf.download(
                ticker, start=start, end=end,
                progress=False, auto_adjust=True
            )
            if raw is not None and not raw.empty:
                close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
                series = close.rename(cache_key)
                series.index = pd.to_datetime(series.index).normalize()
                series = series.dropna()
                if not series.empty:
                    time.sleep(0.3)
                    return series
        except Exception:
            pass

    raise RuntimeError(f"All data sources failed for index: {index_name} ({cache_key})")


def _load_series(
    *,
    kind: str,
    key: str,
    fetch_fn: Callable[[dt.date, dt.date], pd.Series | None],
    years: int,
    logger: Callable[[str], None] | None = None,
) -> pd.Series | None:
    _ensure_cache_dir()
    existing = _read_cache(kind, key)
    start = _required_start_date(existing, years)
    end = dt.date.today()

    # If cache is fresh enough (fetched today) skip the network call entirely
    if existing is not None:
        last_cached = existing.index.max().date()
        if last_cached >= end - dt.timedelta(days=1):
            _log(f"    ↺ {key}: cache up-to-date ({len(existing)} rows)", logger)
            return existing

    try:
        incoming = fetch_fn(start, end)
        merged = _merge_cache(existing, incoming, key)
        if merged is not None:
            _write_cache(kind, key, merged)
            status = "refreshed" if existing is not None else "cached"
            _log(f"    ✓ {key}: {status} {len(merged)} rows", logger)
            time.sleep(REQUEST_PAUSE)
            return merged
    except Exception as exc:
        if existing is not None:
            _log(f"    ⚠ {key}: refresh failed, using cache ({exc})", logger)
            return existing
        _log(f"    ✗ {key}: fetch failed ({exc})", logger)
        return None

    if existing is not None:
        _log(f"    ↺ {key}: no fresh rows, using cache", logger)
        return existing
    _log(f"    ✗ {key}: no data returned", logger)
    return None


BULK_BATCH_SIZE  = 30   # tickers per yfinance batch
BULK_BATCH_PAUSE = 3    # seconds between batches


def _bulk_yf_download(symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
    """
    Download close prices for a list of symbols in batches via yfinance.
    Returns a DataFrame with symbols as columns, date as index.
    """
    if not YFINANCE_AVAILABLE:
        return pd.DataFrame()

    batches    = [symbols[i:i+BULK_BATCH_SIZE] for i in range(0, len(symbols), BULK_BATCH_SIZE)]
    all_frames = []

    for b_idx, batch in enumerate(batches, 1):
        print(f"  yf bulk batch {b_idx}/{len(batches)} ({len(batch)} tickers)…", end=" ", flush=True)
        try:
            raw = yf.download(
                batch, start=start, end=end,
                progress=False, auto_adjust=True, threads=True
            )
            if raw.empty:
                print("empty")
                continue

            close = raw["Close"] if "Close" in raw.columns else raw
            if isinstance(close, pd.Series):
                close = close.to_frame(name=batch[0])

            close.index = pd.to_datetime(close.index).normalize()
            all_frames.append(close)
            print(f"✓ {close.shape[1]} cols")
        except Exception as e:
            print(f"✗ {e}")

        if b_idx < len(batches):
            time.sleep(BULK_BATCH_PAUSE)

    if not all_frames:
        return pd.DataFrame()

    merged = pd.concat(all_frames, axis=1)
    merged = merged.loc[:, ~merged.columns.duplicated()]
    return merged


def fetch_price_matrices(
    stock_symbols: list[str],
    index_name_map: dict[str, str | tuple[str, ...] | list[str]],
    *,
    years: int = 6,
    logger: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fast two-phase fetch:

    Phase 1 — Check cache
        Any symbol whose cache is fresh (updated today) is skipped entirely.

    Phase 2 — Bulk yfinance download (batch=30, threads=True, 3s pause)
        Fetches all stale/missing symbols in one go. Fast.

    Phase 3 — Per-ticker fallback (Stooq → jugaad)
        Only for symbols the bulk download missed. Usually <10 tickers.

    Returns:
        stock_close: DataFrame with stock symbols as columns
        index_close: DataFrame with legacy index ids as columns
    """
    end   = dt.date.today()
    start = end - dt.timedelta(days=365 * years)
    _ensure_cache_dir()

    # ── Phase 1: split into cached vs needs-download ──────────────────────────
    cached_series  = {}
    need_download  = []

    for sym in stock_symbols:
        existing = _read_cache("stocks", sym)
        if existing is not None:
            last = existing.index.max().date()
            if last >= end - dt.timedelta(days=1):
                cached_series[sym] = existing
                continue
        need_download.append(sym)

    cache_hit = len(cached_series)
    _log(f"\n  Cache hits : {cache_hit}/{len(stock_symbols)} stocks (skipping download)", logger)
    _log(f"  Need fetch : {len(need_download)} stocks", logger)

    # ── Phase 2: bulk yfinance download ───────────────────────────────────────
    bulk_result = pd.DataFrame()
    if need_download and YFINANCE_AVAILABLE and BATCH_DOWNLOAD:
        _log(f"\n  Bulk yfinance download — {len(need_download)} stocks "
             f"in batches of {BULK_BATCH_SIZE} …", logger)
        bulk_result = _bulk_yf_download(need_download, start, end)
    elif need_download and not BATCH_DOWNLOAD:
        _log(f"\n  [BATCH_DOWNLOAD=false] Skipping bulk download — using per-ticker fallback for all {len(need_download)} stocks.", logger)

    # Identify what bulk missed (column not present at all)
    bulk_cols     = set(bulk_result.columns.tolist()) if not bulk_result.empty else set()
    still_missing = [s for s in need_download if s not in bulk_cols]

    # Save bulk results to cache — track which actually had valid data
    # yfinance can return a column that is entirely NaN for tickers it
    # failed to parse (TypeError "'NoneType' not subscriptable").
    # Those must go through per-ticker fallback too.
    actually_saved = set()
    for sym in bulk_cols:
        series = bulk_result[sym].dropna().rename(sym)
        series.index = pd.to_datetime(series.index).normalize()
        if not series.empty:
            existing = _read_cache("stocks", sym)
            merged   = _merge_cache(existing, series, sym)
            if merged is not None:
                _write_cache("stocks", sym, merged)
                cached_series[sym] = merged
                actually_saved.add(sym)

    # Tickers that came back as all-NaN columns → send to per-ticker fallback
    bulk_nan = [s for s in bulk_cols if s not in actually_saved]
    still_missing = still_missing + bulk_nan

    if not bulk_result.empty:
        _log(f"  Bulk with data : {len(actually_saved)} | NaN cols : {len(bulk_nan)} | not in bulk : {len([s for s in need_download if s not in bulk_cols])}", logger)
        _log(f"  → Per-ticker fallback needed for : {len(still_missing)} stocks", logger)

    # ── Phase 3: per-ticker fallback for bulk misses ───────────────────────────
    if still_missing:
        _log(f"\n  Per-ticker fallback for {len(still_missing)} missed stocks …", logger)
        for idx, sym in enumerate(still_missing, 1):
            series = _load_series(
                kind="stocks",
                key=sym,
                fetch_fn=lambda s, e, sy=sym: _fetch_stock_history(sy, s, e),
                years=years,
                logger=logger,
            )
            if series is not None:
                cached_series[sym] = series
            if idx % 10 == 0 or idx == len(still_missing):
                pct = int(idx / len(still_missing) * 100)
                bar = ("█" * (pct // 5)).ljust(20)
                _log(f"  [{bar}] {pct:3d}%  {idx}/{len(still_missing)} fallback", logger)

    # ── Assemble stock_close DataFrame ────────────────────────────────────────
    total_stocks = len(stock_symbols)
    ok_count     = len(cached_series)
    fail_count   = total_stocks - ok_count
    _log(f"\n  ✅ Stocks ready: {ok_count}/{total_stocks}  ✗ {fail_count} missing", logger)

    stock_series = [s.rename(sym) for sym, s in cached_series.items() if s is not None]

    # ── Load index histories ──────────────────────────────────────────────────
    index_series: list[pd.Series] = []
    _log(f"\nLoading {len(index_name_map)} index histories from NSE cache/provider …", logger)
    for legacy_id, index_name in index_name_map.items():
        aliases = index_name if isinstance(index_name, (list, tuple)) else (index_name,)
        series = None
        last_error = None
        for alias in aliases:
            try:
                series = _load_series(
                    kind="indices",
                    key=legacy_id,
                    fetch_fn=lambda start, end, name=alias, cache_key=legacy_id: _fetch_index_history(name, cache_key, start, end),
                    years=years,
                    logger=logger,
                )
            except Exception as exc:
                last_error = exc
                _log(f"    ↺ {legacy_id}: alias '{alias}' failed ({exc})", logger)
                series = None
            if series is not None:
                if alias != aliases[0]:
                    _log(f"    ✓ {legacy_id}: fallback alias worked ({alias})", logger)
                break
        if series is not None:
            index_series.append(series.rename(legacy_id))
        elif last_error is not None:
            _log(f"    ✗ {legacy_id}: all aliases failed", logger)

    stock_close = pd.concat(stock_series, axis=1).sort_index() if stock_series else pd.DataFrame()
    index_close = pd.concat(index_series, axis=1).sort_index() if index_series else pd.DataFrame()

    return stock_close, index_close
