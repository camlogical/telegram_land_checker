import os
import threading
import time
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
PING_URL = os.getenv("PING_URL")

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)))

def auto_ping():
    if not PING_URL:
        print("⚠ No PING_URL set. Skipping auto-ping.")
        return
    while True:
        try:
            print(f"Pinging {PING_URL}")
            requests.get(PING_URL)
        except Exception as e:
            print(f"Ping failed: {e}")
        time.sleep(600)  # 10 minutes

def scrape_land_data(land_number: str) -> dict:
    url = "https://miniapp.mlmupc.gov.kh/search?digest=Dvy%2B5MEhP2%2F36gfYb2iuIaO6kNNCiOdCVmmoNNVdVBQTDhNqVIkwTwssn33SvcXk80Rj6fL7yKJC%2FRYXdiEJDaDAIlaTGtHn98Ttb7y6pNXzdtuF806hzu2HBefFjIuz0Y%2F%2BmHCaFYP%2Fn41B9EAEQvuLVovWSVRG75PDNCTZMtwdu%2F5%2BF5xV%2B7InLXEhfFbVFdL65u3NN%2FueAxB5fBNsV9%2BGWVn7CsCsR%2B%2Frfng5f0MfLx965CvXSJS2BZU22%2FeUyikeeFjakJ0KRit97MSmw2K2aR1UVkiW%2BzcIi%2Br8uCLKKUmuAfAcpsJZn95dAEIf"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {"recaptchaToken": "", "landNum": land_number}

    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": f"HTTP error {response.status_code}"}

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        if "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found"}

        # Find the table manually if #extra_table is missing
        table = soup.select_one("#extra_table")
        if not table:
            tables = soup.find_all("table")
            for t in tables:
                if "លេខសម្គាល់កម្មសិទ្ធិ" in t.text:
                    table = t
                    break

        if not table:
            return {"status": "error", "message": "Extra table not found."}

        rows = table.find_all("tr")
        land_info = {}
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                land_info[key] = value

        if not land_info:
            return {"status": "error", "message": "No land information extracted."}

        return {"status": "found", "info": land_info}

    except Exception as e:
        return {"status": "error", "message": str(e)}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏡 Welcome to the MLMUPC Land Checker Bot!\n\n"
        "Send me a land number like: `18020601-0001`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    land_number = update.message.text.strip()
    if not land_number:
        await update.message.reply_text("❌ Please send a valid land number.")
        return

    result = scrape_land_data(land_number)
    if result["status"] == "found":
        info = result["info"]
        msg = "✅ *Land Information:*\n\n"
        for key, value in info.items():
            msg += f"• *{key}:* {value}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif result["status"] == "not_found":
        await update.message.reply_text("⚠️ No land information found.")
    else:
        await update.message.reply_text(f"❌ Error: {result.get('message', 'Unknown error')}")

if __name__ == "__main__":
    # Start Flask server
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Start auto-pinging thread
    ping_thread = threading.Thread(target=auto_ping)
    ping_thread.start()

    # Start Telegram Bot
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.run_polling()