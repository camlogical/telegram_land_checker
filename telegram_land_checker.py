# === LOAD ENVIRONMENT ===
from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
import threading
import asyncio
import requests
import random
import re
from datetime import datetime
from flask import Flask, request
from bs4 import BeautifulSoup
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SHEET_ID = "1N_LM9CM4egDeEVVbWx7GK8h5usQbg_EEDJZBNt8M1oY"
SHEET_TAB = "User_Search_History"
USER_CONTACT_TAB = "User_Contacts"
USER_DB_FILE = "users.json"

# === GLOBALS ===
user_database = {}
user_locks = {}
USER_AGENTS = []

# === FLASK SETUP ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK"

# === UTILITIES ===
def auto_ping():
    url = os.getenv("PING_URL")
    if url:
        while True:
            try:
                requests.get(url)
            except Exception as e:
                print(f"Ping failed: {e}")
            time.sleep(600)

def get_gsheet_client():
    credentials_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
    creds = Credentials.from_service_account_info(credentials_info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    return gspread.authorize(creds)

def save_user_database():
    try:
        with open(USER_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(user_database, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save user db: {e}")

def load_user_database():
    global user_database
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, "r", encoding="utf-8") as f:
                user_database = json.load(f)
        except Exception as e:
            print(f"Failed to load user db: {e}")

def save_all_users_to_gsheet():
    try:
        if not user_database:
            return
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(USER_CONTACT_TAB)
        existing_user_ids = {str(row["user_id"]) for row in sheet.get_all_records()}

        for user_id, info in user_database.items():
            if str(user_id) not in existing_user_ids:
                sheet.append_row([
                    str(user_id),
                    info.get("username", "Unknown"),
                    info.get("full_name", "Unknown"),
                    info.get("phone_number", "Unknown")
                ])
    except Exception as e:
        print(f"Failed to sync users: {e}")

def save_user_search(user_id, username, land_number):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info = user_database.get(str(user_id), {})
        sheet.append_row([
            str(user_id), username, info.get("full_name", ""), info.get("phone_number", ""), land_number, timestamp
        ])
    except Exception as e:
        print(f"Failed to log search: {e}")

def save_full_search_log(user_id, username, land_number, result):
    try:
        client = get_gsheet_client()
        full_logs_tab = "Full_Search_Logs"
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet(full_logs_tab)
        except gspread.exceptions.WorksheetNotFound:
            sheet = client.open_by_key(SHEET_ID).add_worksheet(title=full_logs_tab, rows="1000", cols="20")
            sheet.append_row(["user_id", "username", "full_name", "phone_number", "land_number", "timestamp", "status", "serial_info", "location", "updated_system", "owner_info"])
        info = user_database.get(str(user_id), {})
        owner_info = "; ".join(f"{k}: {v}" for k, v in result.get("owner_info", {}).items())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([
            str(user_id), username, info.get("full_name", ""), info.get("phone_number", ""), land_number, timestamp,
            result.get("status", ""), result.get("serial_info", ""), result.get("location", ""), result.get("updated_system", ""), owner_info
        ])
    except Exception as e:
        print(f"Failed to log full: {e}")

def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_locks[user_id]

def get_random_user_agent():
    return random.choice(USER_AGENTS) if USER_AGENTS else "Mozilla/5.0"

def scrape_land_data(land_number):
    if not re.match(r'^\d{8}-\d{4}$', land_number):
        return {"status": "not_found", "message": "ទម្រង់លេខខុស: ########-####"}
    url = os.getenv("URL")
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept-Language": "en-US,en;q=0.9,km-KH;q=0.8",
        "Accept": "text/html",
        "Referer": "https://miniapp.mlmupc.gov.kh/"
    }
    try:
        response = requests.post(url, headers=headers, data={"recaptchaToken": "", "landNum": land_number}, timeout=10)
        html = response.text
        if "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found", "message": "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ."}
        soup = BeautifulSoup(html, 'html.parser')
        def extract(text, left, right): return text.split(left)[1].split(right)[0].strip() if left in text else ""
        serial_info = extract(html, 'id="serail_info">', '</span></td>')
        location = extract(html, '<span>ភូមិ ៖ ', '</span>')
        updated_system = extract(html, '(ធ្វើបច្ចុប្បន្នភាព: <span>', '</span>)</p>')
        table = soup.find("table", class_="table table-bordered")
        owner_info = {}
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) == 2:
                    owner_info[cells[0].get_text(strip=True)] = cells[1].get_text(strip=True)
        return {"status": "found", "serial_info": serial_info, "location": location, "updated_system": updated_system, "owner_info": owner_info}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === TELEGRAM HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    sheet = get_gsheet_client().open_by_key(SHEET_ID).worksheet(USER_CONTACT_TAB)
    in_sheet = any(str(u["user_id"]) == user_id for u in sheet.get_all_records())
    if in_sheet:
        await update.message.reply_text("🏡 សូមវាយលេខក្បាលដីជាទម្រង់ ########-#### \nឧទា.18020601-0001")
    else:
        button = KeyboardButton(text="✅ VERIFY", request_contact=True)
        await update.message.reply_text("ចុចដើម្បីបញ្ជាក់", reply_markup=ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True))

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = str(contact.user_id)
    user_database[user_id] = {
        "username": update.message.from_user.username or "Unknown",
        "full_name": update.message.from_user.full_name,
        "phone_number": contact.phone_number
    }
    save_user_database()
    save_all_users_to_gsheet()
    await update.message.reply_text("✅ បានបញ្ជាក់ជោគជ័យ ✅", reply_markup=ReplyKeyboardRemove())

async def handle_multiple_land_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    lock = get_user_lock(user_id)
    if not lock.acquire(blocking=False):
        await update.message.reply_text("⏳ សូមរងចាំ...")
        return
    try:
        land_numbers = update.message.text.strip().split("\n")
        username = update.message.from_user.username or update.message.from_user.full_name or "Unknown"
        for land_number in land_numbers:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            result = scrape_land_data(land_number.strip())
            save_user_search(user_id, username, land_number)
            save_full_search_log(user_id, username, land_number, result)
            if result["status"] == "found":
                msg = f"✅ *{land_number}*\n📍 ភូមិ៖ {result.get('location', '')}\n🧾 {result.get('serial_info', '')}\n🕒 {result.get('updated_system', '')}"
                if result["owner_info"]:
                    msg += "\n\n👤 ព័ត៌មាន:\n" + "\n".join(f"- {k}: {v}" for k, v in result["owner_info"].items())
                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ {result['message']}")
    finally:
        lock.release()

# === BOT INITIALIZATION ===
if __name__ == "__main__":
    load_user_database()
    threading.Thread(target=auto_ping, daemon=True).start()

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_multiple_land_numbers))

    webhook_url = os.getenv("WEBHOOK_URL")

    async def set_webhook():
        await bot_app.bot.set_webhook(f"{webhook_url}/{BOT_TOKEN}")

    asyncio.run(set_webhook())

    bot_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        webhook_url=f"{webhook_url}/{BOT_TOKEN}"
    )
