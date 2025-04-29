import os
import threading
import time
import requests
import re
import json
from datetime import datetime
from flask import Flask
from bs4 import BeautifulSoup
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 388876020  # 👈 Change to your Telegram ID
SHEET_ID = "1N_LM9CM4egDeEVVbWx7GK8h5usQbg_EEDJZBNt8M1oY"
SHEET_TAB = "User_Search_History"
USER_CONTACT_TAB = "User_Contacts"
USER_DB_FILE = "users.json"

# === GLOBALS ===
user_database = {}
user_locks = {}  # <-- Add user locks dictionary

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
            user_info.get("phone_number", ""),
            land_number,
            timestamp
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

# === USER LOCK ===
def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_locks[user_id]

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
        "✅ បានបញ្ជាក់ព័ត៌មានរបស់អ្នកជោគជ័យ ✅\n\n\n"
        "🏡 សូមស្វាគមន៍មកកាន់កម្មវិធីស្វែងរកព័ត៌មានអំពីក្បាលដី (MLMUPC Land info Checker Bot!)\n\n"
        "សូមវាយជាទម្រង់ ########-#### \nឧទា.18020601-0001\n\n\n"
        "Bot Developed with ❤️ by MNPT."
    )

async def handle_multiple_land_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    if user_id not in user_database:
        button = KeyboardButton(text="✅ VERIFY", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("ដើម្បីប្រើប្រាស់សូមចុចប៊ូតុងខាងក្រោមដើម្បីបញ្ជាក់", reply_markup=reply_markup)
        return

    lock = get_user_lock(user_id)

    if not lock.acquire(blocking=False):
        await update.message.reply_text("⚠️ប្រព័ន្ធកំពុងរវល់⚠️\nសូមមេត្តារង់ចាំ ឬសូមសាកល្បងស្វែងរកម្ដងទៀត។")
        return

    try:
        land_numbers = update.message.text.strip().split("\n")

        total_land_numbers = len(land_numbers)
        found_count = 0
        not_found_count = 0

        # Send the initial success message
        success_message = await update.message.reply_text(
            f"✅ All land numbers processed successfully!\n"
            f"✅ {found_count} found, {not_found_count} not found.",
            parse_mode=ParseMode.MARKDOWN
        )

        for land_number in land_numbers:
            result = scrape_land_data(land_number.strip())

            if result["status"] == "found":
                found_count += 1
                msg = f"✅ *Land Info Found for {land_number}*\n" \
                      f"⏰ *Update Time:* {result.get('updated_system', 'N/A')}\n" \
                      f"👉 *Serial Number:* {result.get('serial_info', 'N/A')}\n" \
                      f"📍 *Location:* {result.get('location', 'N/A')}\n"

                if result['owner_info']:
                    msg += "\n📝 *Owner Information:*\n"
                    for key, value in result['owner_info'].items():
                        msg += f"   - {key}: {value}\n"
                
                msg += "\n\nChecked from: [MLMUPC](https://mlmupc.gov.kh/electronic-cadastral-services)"
                await update.message.reply_text(msg, parse_mode="Markdown")

            elif result["status"] == "not_found":
                not_found_count += 1
                msg = f"⚠️ *{land_number}* {result.get('message', 'No data found for this land number.')}"
                await update.message.reply_text(msg, parse_mode="Markdown")

            else:
                msg = f"❌ Error for *{land_number}*: {result.get('message', 'Unknown error')}."
                await update.message.reply_text(msg, parse_mode="Markdown")

        # Update the success message with final count
        await success_message.edit_text(
            f"✅ All land numbers processed successfully!\n"
            f"✅ {found_count} found, {not_found_count} not found.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Schedule the deletion of the success message after 5 seconds
        context.job_queue.run_once(delete_message, 5, context=(update.message.chat_id, success_message.message_id))

    finally:
        lock.release()

# Function to delete the message after 5 seconds
async def delete_message(context):
    chat_id, message_id = context.job.context
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

# === MAIN ===
if __name__ == "__main__":
    load_user_database()

    # Start Flask server and auto-ping thread
    threading.Thread(target=run_flask).start()
    threading.Thread(target=auto_ping, daemon=True).start()

    # Create the Telegram bot application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Contact, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_multiple_land_numbers))

    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)
