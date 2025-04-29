import os
import threading
import time
import requests
import re
import json
from datetime import datetime
from flask import Flask
from bs4 import BeautifulSoup
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 388876020  # 👈 Change to your Telegram ID
SHEET_ID = "1N_LM9CM4egDeEVVbWx7GK8h5usQbg_EEDJZBNt8M1oY"
SHEET_TAB = "User_Search_History"
USER_CONTACT_TAB = "User_Contacts"  # New tab for saving contacts
USER_DB_FILE = "users.json"  # Local user database

# === GLOBALS ===
user_database = {}

# === FLASK SETUP ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)))

def auto_ping():
    url = os.getenv("PING_URL")
    if not url:
        print("⚠ No PING_URL set. Skipping auto-ping.")
        return
    while True:
        try:
            print(f"Pinging {url}")
            requests.get(url)
        except Exception as e:
            print(f"Ping failed: {e}")
        time.sleep(600)

# === GOOGLE SHEETS CLIENT ===
def get_gsheet_client():
    credentials_info = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
    creds = Credentials.from_service_account_info(credentials_info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    client = gspread.authorize(creds)
    return client

# === SAVE & LOAD USER DATABASE ===
def save_user_database():
    try:
        with open(USER_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(user_database, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Failed to save user database: {e}")

def load_user_database():
    global user_database
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, "r", encoding="utf-8") as f:
                user_database = json.load(f)
            print(f"✅ Loaded {len(user_database)} users from {USER_DB_FILE}")
        except Exception as e:
            print(f"❌ Failed to load user database: {e}")

def save_all_users_to_gsheet():
    try:
        if not user_database:
            print("⚠️ No users to save.")
            return
        
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(USER_CONTACT_TAB)

        sheet.clear()
        sheet.append_row(["user_id", "username", "full_name", "phone_number"])

        for user_id, info in user_database.items():
            sheet.append_row([
                str(user_id),
                info.get("username", "Unknown"),
                info.get("full_name", "Unknown"),
                info.get("phone_number", "Unknown")
            ])

        print(f"✅ Saved {len(user_database)} users to Google Sheet.")
        
    except Exception as e:
        print(f"❌ Failed to save users to Google Sheet: {e}")

# === SAVE SEARCH HISTORY TO GOOGLE SHEET ===
def save_user_search(user_id, username, land_number):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_info = user_database.get(str(user_id), {})

        sheet.append_row([
            str(user_id),
            username,
            user_info.get("full_name", ""),
            user_info.get("phone_number", "")
            land_number,
            timestamp,
        ])
    except Exception as e:
        print(f"❌ Failed to save search history: {e}")

# === LAND DATA SCRAPER ===
def scrape_land_data(land_number: str) -> dict:
    if not re.match(r'^\d{8}-\d{4}$', land_number):
        return {"status": "not_found", "message": "អ្នកវាយទម្រង់លេខក្បាលដីខុស.\n សូមវាយជាទម្រង់ ########-#### \n ឧទា.18020601-0001"}

    url = "https://miniapp.mlmupc.gov.kh/search?digest=Dvy%2B5MEhP2%2F36gfYb2iuIaO6kNNCiOdCVmmoNNVdVBQTDhNqVIkwTwssn33SvcXk80Rj6fL7yKJC%2FRYXdiEJDaDAIlaTGtHn98Ttb7y6pNXzdtuF806hzu2HBefFjIuz0Y%2F%2BmHCaFYP%2Fn41B9EAEQvuLVovWSVRG75PDNCTZMtwdu%2F5%2BF5xV%2B7InLXEhfFbVFdL65u3NN%2FueAxB5fBNsV9%2BGWVn7CsCsR%2B%2Frfng5f0MfLx965CvXSJS2BZU22%2FeUyikeeFjakJ0KRit97MSmw2K2aR1UVkiW%2BzcIi%2Br8uCLKKUmuAfAcpsJZn95dAEIf"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {"recaptchaToken": "", "landNum": land_number}

    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": f"HTTP error {response.status_code}"}

        html = response.text

        if "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found", "message": "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ."}

        if "វិញ្ញាបនបត្រសម្គាល់ម្ចាស់អចលនវត្ថុលេខ" in html:
            status = "found"
        else:
            return {"status": "not_found", "message": "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ."}

        def extract_between(text, left, right):
            try:
                return text.split(left)[1].split(right)[0].strip()
            except:
                return ""

        serial_info = extract_between(html, 'id="serail_info">', '</span></td>')
        location = extract_between(html, '<span>ភូមិ ៖ ', '</span>')
        updated_system = extract_between(html, '(ធ្វើបច្ចុប្បន្នភាព: <span>', '</span>)</p>')

        owner_info = {}
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find("table", class_="table table-bordered")
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    owner_info[key] = value

        return {
            "status": status,
            "serial_info": serial_info,
            "location": location,
            "updated_system": updated_system,
            "owner_info": owner_info
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === BOT COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    if user_id not in user_database:
        button = KeyboardButton(text="✅ VERIFY", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("ដើម្បីប្រើប្រាស់សូមចុចប៊ូតុងខាងក្រោមដើម្បីបញ្ជាក់", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            "🏡 សូមស្វាគមន៍មកកាន់កម្មវិធីស្វែងរកព័ត៌មានអំពីក្បាលដី (MLMUPC Land info Checker Bot!)\n\n"
            "សូមវាយជាទម្រង់ ########-#### \nឧទា.18020601-0001\n\n\n"
            "Bot Developed with ❤️ by MNPT."
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = str(contact.user_id)
    username = update.message.from_user.username or "Unknown"
    full_name = update.message.from_user.full_name or "Unknown"
    phone_number = contact.phone_number

    user_database[user_id] = {
        "username": username,
        "full_name": full_name,
        "phone_number": phone_number
    }
    save_user_database()
    save_all_users_to_gsheet()

    await update.message.reply_text(
        "✅ បានបញ្ជាក់ព័ត៌មានរបស់អ្នកជោគជ័យ។\n\n"
        "ឥឡូវនេះ សូមបញ្ចូលលេខក្បាលដី ដើម្បីស្វែងរកព័ត៌មាន។"
    )

async def handle_multiple_land_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in user_database:
        button = KeyboardButton(text="✅ VERIFY", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("ដើម្បីប្រើប្រាស់សូមចុចប៊ូតុងខាងក្រោមដើម្បីបញ្ជាក់", reply_markup=reply_markup)
        return

    land_numbers = update.message.text.strip().split("\n")
    username = update.message.from_user.username or update.message.from_user.full_name or "Unknown"

    for land_number in land_numbers:
        land_number = land_number.strip()
        result = scrape_land_data(land_number)

        save_user_search(user_id, username, land_number)

        if result["status"] == "found":
            msg = f"✅ *Land Info Found for {land_number}!*\n" \
                  f"⏰ *បច្ចុប្បន្នភាព៖* {result.get('updated_system', 'N/A')}\n" \
                  f"👉 *លេខប័ណ្ណកម្មសិទ្ធិ៖* {result.get('serial_info', 'N/A')}\n" \
                  f"📍 *ទីតាំងដី ភូមិ៖* {result.get('location', 'N/A')}\n"

            if result['owner_info']:
                msg += "\n📝 *ព័ត៌មានក្បាលដី៖*\n"
                for key, value in result['owner_info'].items():
                    msg += f"   - {key} {value}\n"
            
            msg += "\n\nChecked data from: [MLMUPC](https://mlmupc.gov.kh/electronic-cadastral-services)\nBot Developed by MNPT"

            await update.message.reply_text(msg, parse_mode="Markdown")
        
        elif result["status"] == "not_found":
            msg = f"⚠️ *{land_number}* {result.get('message', 'មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ.')}"
            await update.message.reply_text(msg, parse_mode="Markdown")
        
        else:
            msg = f"❌ Error for *{land_number}*: {result.get('message', 'Unknown error')}."
            await update.message.reply_text(msg, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to view user search history.")
        return

    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)
        data = sheet.get_all_records()

        if not data:
            await update.message.reply_text("⚠️ No user search history found.")
            return

        history_text = ""
        for row in data[-10:]:
            history_text += f"👤 {row['username']} - {row['land_number']} at {row['timestamp']}\n"

        await update.message.reply_text(f"📄 *Recent User Search History:*\n\n{history_text}", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error reading history: {e}")

# === MAIN RUN ===
if __name__ == "__main__":
    load_user_database()

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=auto_ping)
    ping_thread.start()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("history", history))
    app_bot.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_multiple_land_numbers))
    app_bot.run_polling()
