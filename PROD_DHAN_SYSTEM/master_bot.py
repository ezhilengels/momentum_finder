import os
import datetime
import telebot
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Ensure the current directory is in the path for imports
sys.path.append(os.path.dirname(__file__))
from universal_engine import engine

# Load environment variables from root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Configuration
ROOT_DIR = os.path.join(os.path.dirname(__file__), '..')
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PORTFOLIOS = [
    ("Core Portfolio", "core"),
    ("Momentum2", "momentum2"),
]

# Initialize Telegram Bot
bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

def get_tracked_stocks(portfolio_key):
    return engine.read_portfolio(portfolio_key)

def get_portfolio_report(title, portfolio_key):
    stocks = get_tracked_stocks(portfolio_key)
    if not stocks:
        return f"📉 *{title}*\nNo stocks are currently being tracked."

    symbols = [s['symbol'] for s in stocks]
    quotes = engine.get_market_quote(symbols)
    
    if not quotes:
        return f"❌ *{title}*\nCould not fetch data from Yahoo Finance."

    # Separate stocks for better organization
    profit_data = []
    loss_data = []
    total_pl = 0
    count = 0

    for stock in stocks:
        symbol = stock['symbol']
        fixed_val = float(stock['fixed_value'])
        quote = quotes.get(symbol, {})
        cmp = quote.get("ltp")
        
        if isinstance(cmp, (int, float)):
            pl_percent = ((cmp - fixed_val) / fixed_val) * 100
            total_pl += pl_percent
            count += 1
            
            # Format row: Symbol (10 chars), CMP (8 chars), PL (7 chars)
            row_text = f"{symbol:<10} {cmp:<8.1f} {pl_percent:>+6.2f}%"
            
            if pl_percent >= 0:
                profit_data.append({"text": f"+ {row_text}", "val": pl_percent})
            else:
                loss_data.append({"text": f"- {row_text}", "val": pl_percent})
        else:
            loss_data.append({"text": f"! {symbol:<10} {'N/A':<8} {'N/A':>6}", "val": -999})

    # Sort both lists by P/L percentage descending
    profit_data.sort(key=lambda x: x['val'], reverse=True)
    loss_data.sort(key=lambda x: x['val'], reverse=True)

    profits = [item['text'] for item in profit_data]
    losses = [item['text'] for item in loss_data]

    # Build the Message
    report = f"🚀 *{title.upper()}*\n"
    report += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Header for the table
    header = f"{'STOCK':<12} {'CMP':<8} {'P/L %':<7}\n"
    divider = "━━━━━━━━━━━━━━━━━━━━━━\n"

    # PROFIT SECTION (Green in many Telegram clients via diff syntax)
    if profits:
        report += "🟢 *PROFITABLE STOCKS*\n"
        report += "```diff\n"
        report += header
        report += "\n".join(profits)
        report += "```\n"

    # LOSS SECTION (Red in many Telegram clients via diff syntax)
    if losses:
        report += "🔴 *STOCKS IN RED*\n"
        report += "```diff\n"
        report += header
        report += "\n".join(losses)
        report += "```\n"

    report += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if count > 0:
        avg_pl = total_pl / count
        status = "🟢 POSITIVE" if avg_pl > 0 else "🔴 NEGATIVE"
        report += f"📊 *Overall:* `{avg_pl:>+6.2f}%` ({status})\n"

    report += f"🕒 *Updated:* `{datetime.datetime.now().strftime('%H:%M:%S')}`"
    return report

def build_all_reports():
    return [get_portfolio_report(title, key) for title, key in PORTFOLIOS]

def scheduled_update():
    if bot and TELEGRAM_CHAT_ID:
        for report in build_all_reports():
            bot.send_message(TELEGRAM_CHAT_ID, report, parse_mode="Markdown")

# --- Telegram Handlers ---

@bot.message_handler(commands=['status'])
def send_status(message):
    msg = bot.send_message(message.chat.id, "🔄 *Analyzing your portfolio...*", parse_mode="Markdown")
    reports = build_all_reports()
    bot.edit_message_text(reports[0], chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
    for report in reports[1:]:
        bot.send_message(message.chat.id, report, parse_mode="Markdown")

@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    help_text = (
        "💎 *Master Control Bot (V4)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Your financial tracking is active.\n\n"
        "🔹 `/status` - Live P/L with colors\n"
        "🔹 *9:00 AM* - Market Open Report\n"
        "🔹 *3:15 PM* - Market Close Report\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

if __name__ == "__main__":
    if not bot:
        print("❌ Error: Telegram Token missing.")
        exit(1)

    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_update, 'cron', hour=9, minute=0, timezone='Asia/Kolkata')
    scheduler.add_job(scheduled_update, 'cron', hour=15, minute=15, timezone='Asia/Kolkata')
    scheduler.start()

    print("✅ Master Bot Color UI Active...")
    try:
        bot.infinity_polling()
    except:
        scheduler.shutdown()
