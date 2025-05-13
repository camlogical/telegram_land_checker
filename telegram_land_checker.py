import os
import json
import time
import re
import random
import asyncio
import threading
import requests
from flask import Flask
from dotenv import load_dotenv
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ChatAction
import gspread
from google.oauth2.service_account import Credentials

# === Load env ===
load_dotenv()

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SHEET_ID = "1N_LM9CM4egDeEVVbWx7GK8h5usQbg_EEDJZBNt8M1oY"
SHEET_TAB = "User_Search_History"
USER_CONTACT_TAB = "User_Contacts"
USER_DB_FILE = "users.json"
USER_AGENTS_URL = os.getenv("USER_AGENTS_URL")
LAND_DATA_URL = os.getenv("URL")

# === Globals ===
user_database = {}
user_locks = {}
app = Flask(__name__)

# === Serve health check ===
@app.route('/')
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

def auto_ping():
    url = os.getenv("PING_URL")
    while url:
        print(f"Pinging {url}")
        try: requests.get(url)
        except Exception as e: print(f"Ping failed: {e}")
        time.sleep(600)

# === Google Sheets ===
def get_gsheet_client():
    credentials_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
    creds = Credentials.from_service_account_info(credentials_info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    return gspread.authorize(creds)

def save_user_database():
    with open(USER_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(user_database, f, ensure_ascii=False, indent=2)

def load_user_database():
    global user_database
    if os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "r", encoding="utf-8") as f:
            user_database = json.load(f)
        print(f"✅ Loaded {len(user_database)} users from {USER_DB_FILE}")

# === Utilities ===
def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_locks[user_id]

def fetch_user_agents(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return [line.strip() for line in response.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"Failed to fetch user agents: {e}")
        return []

USER_AGENTS = fetch_user_agents(USER_AGENTS_URL)

def get_random_user_agent():
    return random.choice(USER_AGENTS) if USER_AGENTS else "Mozilla/5.0"

# === Scraper ===
def scrape_land_data(land_number: str) -> dict:
    if not re.match(r'^\d{8}-\d{4}$', land_number):
        return {"status": "not_found", "message": "លេខខុសទម្រង់"}

    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept-Language": "en-US,en;q=0.9,km-KH;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://miniapp.mlmupc.gov.kh/"
    }
    data = {"recaptchaToken": "", "landNum": land_number}

    try:
        res = requests.post(LAND_DATA_URL, headers=headers, data=data, timeout=10)
        html = res.text

        if "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found", "message": "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ."}

        serial_info = re.search(r'id="serail_info">([^<]+)', html)
        location = re.search(r'ភូមិ ៖ ([^<]+)', html)
        updated = re.search(r'\(ធ្វើបច្ចុប្បន្នភាព: <span>([^<]+)', html)

        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find("table", class_="table table-bordered")
        owner_info = {}
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) == 2:
                    owner_info[cells[0].text.strip()] = cells[1].text.strip()

        return {
            "status": "found",
            "serial_info": serial_info.group(1) if serial_info else "",
            "location": location.group(1) if location else "",
            "updated_system": updated.group(1) if updated else "",
            "owner_info": owner_info
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === Google Sheet Writers ===
def save_user_search(user_id, username, land_number):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)
        user_info = user_database.get(str(user_id), {})
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([user_id, username, user_info.get("full_name", ""), user_info.get("phone_number", ""), land_number, timestamp])
    except Exception as e:
        print(f"❌ Failed to log search: {e}")

def save_full_search_log(user_id, username, land_number, result):
    try:
        client = get_gsheet_client()
        sheet_name = "Full_Search_Logs"
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = client.open_by_key(SHEET_ID).add_worksheet(title=sheet_name, rows="1000", cols="20")
            sheet.append_row(["user_id", "username", "full_name", "phone_number", "land_number", "timestamp", "status", "serial_info", "location", "updated_system", "owner_info"])

        user_info = user_database.get(str(user_id), {})
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        owner_str = "; ".join(f"{k}: {v}" for k, v in result.get("owner_info", {}).items())

        sheet.append_row([user_id, username, user_info.get("full_name", ""), user_info.get("phone_number", ""), land_number, timestamp, result.get("status", ""), result.get("serial_info", ""), result.get("location", ""), result.get("updated_system", ""), owner_str])
    except Exception as e:
        print(f"❌ Failed to save full search: {e}")

# === Bot Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_database:
        button = KeyboardButton(text="✅ VERIFY", request_contact=True)
        reply = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("សូមចុចប៊ូតុង VERIFY ដើម្បីចូលប្រើ", reply_markup=reply)
    else:
        await update.message.reply_text("សូមវាយលេខក្បាលដី ដូចជា: 18020601-0001")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_database[str(contact.user_id)] = {
        "username": update.message.from_user.username or "Unknown",
        "full_name": update.message.from_user.full_name or "Unknown",
        "phone_number": contact.phone_number
    }
    save_user_database()
    await update.message.reply_text("✅ ព័ត៌មានបានបញ្ជាក់។ សូមវាយលេខក្បាលដី", reply_markup=ReplyKeyboardRemove())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in user_database:
        await update.message.reply_text("សូមបញ្ជាក់ទំនាក់ទំនងជាមុន")
        return

    land_numbers = update.message.text.strip().split()
    username = update.message.from_user.username or "Unknown"

    for land_number in land_numbers:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(0.5)
        result = scrape_land_data(land_number)
        save_user_search(user_id, username, land_number)
        save_full_search_log(user_id, username, land_number, result)

        if result["status"] == "found":
            msg = f"✅ *{land_number}* បានរកឃើញ\n"
            msg += f"📍 ទីតាំង: {result.get('location')}\n"
            msg += f"📄 លេខប័ណ្ណ: {result.get('serial_info')}\n"
            msg += f"📅 បច្ចុប្បន្នភាព: {result.get('updated_system')}\n"
            if result["owner_info"]:
                msg += "\n🧾 *ព័ត៌មានម្ចាស់:*\n"
                for k, v in result["owner_info"].items():
                    msg += f"• {k}: {v}\n"
        else:
            msg = f"❌ {land_number}: {result.get('message')}"

        await update.message.reply_text(msg, parse_mode="Markdown")

# === Run App ===
if __name__ == "__main__":
    load_user_database()
    threading.Thread(target=run_flask).start()
    threading.Thread(target=auto_ping).start()

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Render deployment (webhook)
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_path = f"/{BOT_TOKEN}"
        full_webhook_url = f"{render_url}{webhook_path}"
        print(f"✅ Webhook set to: {full_webhook_url}")
        bot_app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 8080)),
            webhook_path=webhook_path,
            webhook_url=full_webhook_url
        )
    else:
        # For local use
        asyncio.run(bot_app.bot.delete_webhook(drop_pending_updates=True))
        bot_app.run_polling()
