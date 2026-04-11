# Sector Index Momentum Tracker — Simple Plan

## Goal

Create a lightweight momentum tracker that analyzes only these NSE sector indices:

- Nifty Auto
- Nifty Infra
- Nifty 50
- Nifty Consumption
- Nifty FMCG
- Nifty Fin Service
- Nifty Pharma
- Nifty IT
- Nifty Media
- Nifty Metal
- Nifty Energy
- Nifty Realty
- Nifty Services

This tracker should not load or analyze any individual stocks.

It should behave like the stock momentum tracker logic, but only for the above sector indices.

---

## What It Should Do

For each sector index:

- fetch historical daily close data
- use up to 5 years of history
- calculate momentum returns for these timeframes:
  - 1d
  - 1w
  - 2w
  - 3w
  - 4w
  - 1m
  - 2m
  - 3m
  - 6m
  - 9m
  - 1y
  - 3y
  - 5y
- count how many timeframes are positive
- generate a momentum score like `X/13`
- classify the sector index using the same momentum-style logic as existing trackers
- show strongest and weakest sectors ranked by score

---

## Data Scope

- Only 13 sector indices
- No Nifty500 stock list
- No stock-level drill-down
- No sector aggregation layer
- No stock vs index comparison

This should be a pure sector-index momentum report.

---

## Suggested Index Mapping

Use one internal mapping table like this:

- Nifty Auto
- Nifty Infra
- Nifty 50
- Nifty Consumption
- Nifty FMCG
- Nifty Fin Service
- Nifty Pharma
- Nifty IT
- Nifty Media
- Nifty Metal
- Nifty Energy
- Nifty Realty
- Nifty Services

The implementation can later map each display name to the correct provider symbol or NSE index name.

---

## Timeframe Logic

Use the same return style as stock momentum trackers:

- current close vs close from target date
- percentage return
- positive return = green timeframe
- negative return = red timeframe

Timeframes:

- 1d = 1 trading day / previous close style
- 1w = 7 days
- 2w = 14 days
- 3w = 21 days
- 4w = 28 days
- 1m = 30 days
- 2m = 60 days
- 3m = 90 days
- 6m = 180 days
- 9m = 270 days
- 1y = 365 days
- 3y = 1095 days
- 5y = 1825 days

Total score:

- `13/13` maximum

---

## Output Idea

Simple HTML report with one main table:

Columns:

- Sector Index
- Current Value
- Score
- Category
- 1d
- 1w
- 2w
- 3w
- 4w
- 1m
- 2m
- 3m
- 6m
- 9m
- 1y
- 3y
- 5y

Optional extras later:

- top 3 strongest sectors
- top 3 weakest sectors
- heatmap coloring
- Telegram summary

---

## Suggested Category Logic

Keep it simple and close to the stock momentum logic:

- `💎 Diamond` = all 13 positive
- `🚀 Strong Leader` = strong long-term and high score
- `🔄 Turnaround` = short-term green, long-term weak
- `📈 Improving` = mostly positive
- `Other` = mixed or weak

Exact thresholds can be decided during implementation.

---

## Why This Version Is Better For Now

- much faster than 500-stock sector tracker
- easier to verify
- no stock-data dependency
- no heavy sector aggregation step
- easier to make reliable
- more useful if the main goal is just sector momentum direction

---

## Proposed File

Create a separate script later, for example:

- `sector_index_momentum_tracker.py`

This keeps it independent from:

- `momentum_tracker.py`
- `momentum_tracker_v2.py`
- `sector_tracker_v2.py`

---

## Execution Plan

Phase 1:

- define the 13 sector indices
- fetch 5-year history
- calculate 13 timeframe returns
- build score and category
- rank sectors

Phase 2:

- generate clean HTML table
- add color formatting

Phase 3:

- optional Telegram summary
- optional scheduling

---

## Approval Scope

If approved, the next implementation should:

- work only inside `getFilterValue_v2`
- not change old `getFilterValue`
- create a new standalone tracker for sector indices only
