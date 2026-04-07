import os
import json
import datetime
import telebot
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
STOCKS_FILE = "portfolio_stocks.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Initialize Telegram Bot
bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

def get_tracked_stocks():
    """Load stocks from the JSON file."""
    if not os.path.exists(STOCKS_FILE):
        return []
    with open(STOCKS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def get_portfolio_update():
    """Fetch CMP for all tracked stocks and calculate P&L."""
    stocks = get_tracked_stocks()
    if not stocks:
        return "📉 No stocks are currently being tracked."

    symbols = [f"{s['symbol']}.NS" if not s['symbol'].endswith(".NS") else s['symbol'] for s in stocks]
    
    try:
        # Download current prices
        data = yf.download(symbols, period="1d", interval="1m", progress=False)['Close'].iloc[-1]
    except Exception as e:
        return f"❌ Error fetching stock data: {e}"

    report = "📊 *Live Portfolio Status*\n"
    report += "---------------------------\n"
    report += "`SYMBOL   | CMP    | FIXED  | P/L %` \n"

    for stock in stocks:
        symbol = stock['symbol']
        fixed_val = float(stock['fixed_value'])
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
        
        try:
            # Handle both single and multiple stock dataframes
            cmp = data[ticker_symbol] if len(symbols) > 1 else data
            if isinstance(cmp, (float, int)):
                pl_percent = ((cmp - fixed_val) / fixed_val) * 100
                status_emoji = "🚀" if pl_percent > 0 else "📉"
                report += f"`{symbol:<8} | {cmp:<6.1f} | {fixed_val:<6.1f} | {pl_percent:>+6.2f}%` {status_emoji}\n"
            else:
                report += f"`{symbol:<8} | N/A    | {fixed_val:<6.1f} | N/A   ` ⚠️\n"
        except Exception:
            report += f"`{symbol:<8} | Error  | {fixed_val:<6.1f} | Error ` ❌\n"

    report += "---------------------------\n"
    report += f"_Updated: {datetime.datetime.now().strftime('%H:%M:%S')}_"
    return report

def send_scheduled_update():
    """Triggered by the scheduler at 9:00 AM and 3:15 PM."""
    if bot and TELEGRAM_CHAT_ID:
        report = get_portfolio_update()
        bot.send_message(TELEGRAM_CHAT_ID, report, parse_mode="Markdown")
        print(f"Scheduled update sent at {datetime.datetime.now()}")

# --- Telegram Command Handlers ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Welcome to Portfolio Bot!\n\nUse `/status` to get your current P&L status.\nScheduled updates: 9:00 AM & 3:15 PM.")

@bot.message_handler(commands=['status'])
def send_status(message):
    print(f"Received /status request from {message.chat.id}")
    msg = bot.send_message(message.chat.id, "🔄 Fetching live data, please wait...")
    report = get_portfolio_update()
    bot.edit_message_text(report, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")

# --- Main Setup ---

if __name__ == "__main__":
    if not bot:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env. Bot cannot start.")
        exit(1)

    print("Portfolio Bot starting...")
    
    # 1. Setup Background Scheduler
    scheduler = BackgroundScheduler()
    # 9:00 AM Update
    scheduler.add_job(send_scheduled_update, 'cron', hour=9, minute=0, timezone='Asia/Kolkata')
    # 3:15 PM Update
    scheduler.add_job(send_scheduled_update, 'cron', hour=15, minute=15, timezone='Asia/Kolkata')
    scheduler.start()
    
    print("✅ Scheduler running (9:00 AM, 3:15 PM IST)")
    print("✅ Command listener for /status active.")
    
    # 2. Start Telegram Bot Polling (Blocks the script to keep it running)
    try:
        bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Bot stopped.")
