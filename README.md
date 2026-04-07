# NSE Momentum & Portfolio Management Suite

Professional-grade stock screening and portfolio tracking tools for the National Stock Exchange (NSE) of India. This suite combines **Multi-Year Momentum (Technical)**, **Warren Buffett's Owner Earnings Model (Fundamental)**, and a **24/7 Live Portfolio Tracker**.

---

## 🚀 New Feature: Master Control Center (Production Ready)

The **Master Control Center** is a unified system that tracks your live portfolio and allows you to view all momentum reports from a single dashboard.

### 1. The Master Dashboard
Run the dashboard locally to manage your stocks and view reports:
```bash
python3 PROD_DHAN_SYSTEM/master_dashboard.py
```
- **Live Portfolio:** Track real-time CMP and P&L % against your fixed buy prices.
- **Unified Navigation:** Tabs for V1, V2, and V3 reports inside one browser window.
- **Background Run:** Trigger V3 Analysis directly from the dashboard.
- **Free Engine:** Uses a throttled `yfinance` engine (0.5s delay) for 100% free and stable data.

### 2. The Telegram Portfolio Bot
Get automated updates directly on your phone:
```bash
python3 PROD_DHAN_SYSTEM/master_bot.py
```
- **Scheduled Updates:** 9:00 AM (Market Open) and 3:15 PM (Market Close).
- **Interactive Commands:** Send `/status` to the bot anytime for a live P&L snapshot.

---

## ☁️ Railway Deployment (24/7 Hosting)

This suite is optimized for **Railway.app** deployment.

### Steps to Deploy:
1.  **Environment Variables:** Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to your Railway project variables.
2.  **Procfile:** The included `Procfile` automatically starts both the Dashboard (`web`) and the Bot (`worker`).
3.  **Persistent Storage:** Mount a **Railway Volume** to the root directory to ensure your `portfolio_stocks.json` (tracked stocks) is never lost during deployments.
4.  **Dependencies:** Railway will automatically install all libraries from the provided `requirements.txt`.

---

## 📈 Analysis Bot Versions

| Version | Focus | Best For | Execution |
| :--- | :--- | :--- | :--- |
| **V1** | Short-Term Momentum | Swing trades | ~1 min |
| **V2** | Multi-Year Compounder | Multi-baggers | ~2 mins |
| **V3** | Ultimate Value + Momentum | Value-investing (GARP) | ~10-15 mins |

### To Run Analysis Manually:
```bash
python3 momentum_tracker.py       # V1
python3 momentum_tracker_v2.py    # V2
python3 momentum_tracker_v3.py    # V3
```

---

## 🛠️ Technical Stack
- **Backend:** Python 3.9+, Flask (Dashboard), APScheduler (Scheduling).
- **Data:** `yfinance` (Free Universal Engine with 0.5s throttle).
- **Frontend:** HTML5, CSS3 (Modern Top-Nav), DataTables.js (Sorting/Searching).
- **Notifications:** Telegram Bot API (via `pyTelegramBotAPI`).
- **Deployment:** Railway / Gunicorn (Production-grade).

---

## 📂 Key Files
- `PROD_DHAN_SYSTEM/`: The production-ready folder for deployment.
- `portfolio_stocks.json`: Your personal list of stocks and fixed buy prices.
- `requirements.txt` & `Procfile`: Configuration for cloud hosting.
- `buffett.py`: Fundamental valuation engine.

---

## ⚠️ Disclaimer
*This tool is for educational and research purposes only. Stock market investments are subject to market risks. Always consult with a certified financial advisor before making any investment decisions.*
# momentum_finder
