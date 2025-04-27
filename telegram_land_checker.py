# Remove clear and stats imports
import os
import threading
import time
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import re
from bs4 import BeautifulSoup

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏡 សូមស្វាគមន៍មកកាន់កម្មវិធីស្វែងរកព័ត៌មានអំពីក្បាលដី (MLMUPC Land info Checker Bot!)\n\nសូមវាយជាទម្រង់ ########-#### \nឧទា.18020601-0001\n\n\nBot Developed with ❤️ by MNPT.")

async def handle_multiple_land_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    land_numbers = update.message.text.strip().split("\n")
    
    for land_number in land_numbers:
        result = scrape_land_data(land_number.strip())
        
        if result["status"] == "found":
            msg = f"✅ *Land Info Found for {land_number.strip()}!*\n" \
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
            msg = f"⚠️ *{land_number.strip()}* {result.get('message', 'មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ.')}"

            await update.message.reply_text(msg, parse_mode="Markdown")
        
        else:
            msg = f"❌ Error for *{land_number.strip()}*: {result.get('message', 'Unknown error')}."
            
            await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    ping_thread = threading.Thread(target=auto_ping)
    ping_thread.start()

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_multiple_land_numbers))
    app_bot.run_polling()
