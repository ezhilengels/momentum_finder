# Portfolio Profit/Loss Bot & Dashboard Plan

## 1. Objective
A standalone system to track a personal selection of stocks against user-defined "Fixed Values" (buy prices). The system provides scheduled Telegram updates and an interactive web dashboard.

## 2. Core Components (Strictly Isolated)
- **`portfolio_bot.py`**: Main engine for data fetching, P&L calculation, and Telegram notifications.
- **`portfolio_dashboard.py`**: A simple Flask/FastAPI web server to manage stocks and view insights.
- **`portfolio_stocks.json`**: Data storage for symbols and their fixed values.
- **`.env`**: Secure storage for sensitive credentials (Telegram Token, Chat ID).

## 3. Key Features
### A. Automated Scheduling (Telegram)
- **Morning Check (9:00 AM):** Sends a snapshot of all tracked stocks, their CMP, and P&L % relative to the Fixed Value.
- **Evening Check (3:15 PM):** Sends a pre-close update on performance.
- **Message Format:**
  ```
  📊 Portfolio Update
  ------------------
  SYMBOL | CMP | FIXED | P/L %
  RELIANCE | 2550 | 2500 | +2.0%
  TCS | 3350 | 3400 | -1.47%
  ```

### B. Interactive Dashboard
- **Stock Management:**
  - Input field for **Symbol** (e.g., RELIANCE).
  - Input field for **Fixed Value**.
  - **Add Button:** Persists the stock to `portfolio_stocks.json`.
  - **Delete Button:** Removes a stock from tracking.
- **Smart Filters:**
  - **Discounted Stocks:** Automatic list of stocks where `CMP < Fixed Value`.
  - **Rallying Stocks:** Automatic list of stocks showing significant positive momentum.

## 4. Technical Requirements
- **Security:** Telegram Bot Token and Chat ID **MUST** be stored in `.env`.
- **Data Source:** `yfinance` (used independently from the momentum tracker).
- **Scheduler:** `apscheduler` for precise timing.
- **UI:** HTML/CSS with JavaScript for dynamic updates and "Add" functionality.

## 5. Implementation Steps
1. **Initialize `.env`**: Set up the environment variables.
2. **Data Structure**: Create `portfolio_stocks.json` to store the user's selected stocks.
3. **P&L Engine**: Write the logic to fetch CMP and compare it with the stored Fixed Value.
4. **Telegram Integration**: Build the notification function using the `.env` credentials.
5. **Scheduler Setup**: Configure the 9:00 AM and 3:15 PM triggers.
6. **Web Dashboard**: Create the UI for adding/viewing stocks and the "Discounted/Rallying" logic.

## 6. Constraints
- **NO MODIFICATION** to any existing files (`momentum_tracker*.py`, `buffett.py`, etc.).
- The new bot operates on its own schedule and data file.
