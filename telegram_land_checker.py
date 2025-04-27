import os
import threading
import time
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import re

BOT_TOKEN = os.getenv("BOT_TOKEN")

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

import requests as req
from bs4 import BeautifulSoup

def scrape_land_data(land_number: str) -> dict:
    # Validate land number format (########-####)
    if not re.match(r'^\d{8}-\d{4}$', land_number):
        return {"status": "not_found", "message": "Invalid land number format. Must be ########-####."}

    url = "https://miniapp.mlmupc.gov.kh/search?digest=Dvy%2B5MEhP2%2F36gfYb2iuIaO6kNNCiOdCVmmoNNVdVBQTDhNqVIkwTwssn33SvcXk80Rj6fL7yKJC%2FRYXdiEJDaDAIlaTGtHn98Ttb7y6pNXzdtuF806hzu2HBefFjIuz0Y%2F%2BmHCaFYP%2Fn41B9EAEQvuLVovWSVRG75PDNCTZMtwdu%2F5%2BF5xV%2B7InLXEhfFbVFdL65u3NN%2FueAxB5fBNsV9%2BGWVn7CsCsR%2B%2Frfng5f0MfLx965CvXSJS2BZU22%2FeUyikeeFjakJ0KRit97MSmw2K2aR1UVkiW%2BzcIi%2Br8uCLKKUmuAfAcpsJZn95dAEIf"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {"recaptchaToken": "", "landNum": land_number}

    try:
        response = req.post(url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": f"HTTP error {response.status_code}"}

        html = response.text

        # Check if the land number is found or not
        if "វិញ្ញាបនបត្រសម្គាល់ម្ចាស់អចលនវត្ថុលេខ" in html:
            status = "found"
        elif "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found", "message": "No land information found."}

        # Function to extract data between two markers
        def extract_between(text, left, right):
            try:
                return text.split(left)[1].split(right)[0].strip()
            except:
                return ""

        serial_info = extract_between(html, 'id="serail_info">', '</span></td>')
        location = extract_between(html, '<span>ភូមិ ៖ ', '</span>')
        updated_system = extract_between(html, '(ធ្វើបច្ចុប្បន្នភាព: <span>', '</span>)</p>')

        # Scraping Owner Information
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏡 Welcome to the MLMUPC Land Checker Bot!\n\nSend me a land number like: 18020601-0001")

async def handle_multiple_land_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get the land numbers from the user's message
    land_numbers = update.message.text.strip().split("\n")
    
    # Process each land number individually and send a separate message
    for land_number in land_numbers:
        result = scrape_land_data(land_number.strip())
        
        if result["status"] == "found":
            msg = f"✅ *Land Info Found for {land_number.strip()}!*\n" \
                  f"🔄 *បច្ចុប្បន្នភាព៖* {result.get('updated_system', 'N/A')}\n" \
                  f"#️⃣ *លេខប័ណ្ណកម្មសិទ្ធិ៖* {result.get('serial_info', 'N/A')}\n" \
                  f"📍 *ទីតាំងដី ភូមិ៖* {result.get('location', 'N/A')}\n"

            
            # Include Owner Info if available
            if result['owner_info']:
                msg += "\nℹ️ *ព័ត៌មានក្បាលដី៖*\n"
                for key, value in result['owner_info'].items():
                    msg += f"   - {key}: {value}\n"
            
            await update.message.reply_text(msg, parse_mode="Markdown")
        
        elif result["status"] == "not_found":
            msg = f"⚠️ *{land_number.strip()}* {result.get('message', 'No land information found.')}"
            await update.message.reply_text(msg, parse_mode="Markdown")
        
        else:
            msg = f"❌ Error for *{land_number.strip()}*: {result.get('message', 'Unknown error')}."
            await update.message.reply_text(msg, parse_mode="Markdown")

# Command to clear chat
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id

    # Fetch all the messages and delete them
    all_messages = await update.message.chat.get_chat_messages()
    for msg in all_messages:
        try:
            await update.message.chat.delete_message(msg.message_id)
        except Exception as e:
            print(f"Error deleting message: {e}")
    
    await update.message.reply_text("✅ All messages in the chat have been cleared.")

# Command to show stats (total users and usage)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Assuming you have some way to store stats such as the number of users and their activity
    total_users = 100  # Example: This would be dynamically fetched
    total_queries = 250  # Example: This would be dynamically fetched

    stats_msg = f"📝 *Bot Stats*\n\n" \
                f"👥 *Total Users:* {total_users}\n" \
                f"🔍 *Total Queries:* {total_queries}"
    await update.message.reply_text(stats_msg)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=auto_ping)
    ping_thread.start()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_multiple_land_numbers))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(CommandHandler("clear", clear))  # /clear command
    app_bot.run_polling()
