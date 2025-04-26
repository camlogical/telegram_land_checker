import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

def scrape_land_data(land_number: str) -> dict:
    url = "https://miniapp.mlmupc.gov.kh/search?digest=Dvy%2B5MEhP2%2F36gfYb2iuIaO6kNNCiOdCVmmoNNVdVBQTDhNqVIkwTwssn33SvcXk80Rj6fL7yKJC%2FRYXdiEJDaDAIlaTGtHn98Ttb7y6pNXzdtuF806hzu2HBefFjIuz0Y%2F%2BmHCaFYP%2Fn41B9EAEQvuLVovWSVRG75PDNCTZMtwdu%2F5%2BF5xV%2B7InLXEhfFbVFdL65u3NN%2FueAxB5fBNsV9%2BGWVn7CsCsR%2B%2Frfng5f0MfLx965CvXSJS2BZU22%2FeUyikeeFjakJ0KRit97MSmw2K2aR1UVkiW%2BzcIi%2Br8uCLKKUmuAfAcpsJZn95dAEIf"
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {"recaptchaToken": "", "landNum": land_number}
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            return {"status": "error", "message": "HTTP error", "code": response.status_code}
        
        html = response.text
        
        if "វិញ្ញាបនបត្រសម្គាល់ម្ចាស់អចលនវត្ថុលេខ" in html:
            status = "found"
        elif "មិនមានព័ត៌មានអំពីក្បាលដីនេះទេ" in html:
            return {"status": "not_found", "land": land_number}
        else:
            return {"status": "error", "message": "Unexpected page structure", "land": land_number}
        
        soup = BeautifulSoup(html, "html.parser")
        
        def extract_between(text, left, right):
            try:
                return text.split(left)[1].split(right)[0].strip()
            except:
                return ""
        
        serail_info = extract_between(html, 'id="serail_info">', '</span></td>')
        location = extract_between(html, '<span>ភូមិ ៖ ', '</span>')
        area = extract_between(html, '<span id="land_size">', '</span>')
        updated_system = extract_between(html, '(ធ្វើបច្ចុប្បន្នភាព: <span>', '</span>)</p>')
        
        return {
            "status": status,
            "land": land_number,
            "serail_info": serail_info,
            "location": location,
            "area": area,
            "updated_system": updated_system,
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e), "land": land_number}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Send me a Land Number like `18020601-0001` to check info.", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    land_number = update.message.text.strip()
    if not land_number:
        await update.message.reply_text("Please send a valid Land Number.")
        return
    
    await update.message.reply_text(f"🔎 Checking land number: {land_number} ...")
    
    result = scrape_land_data(land_number)
    
    if result["status"] == "found":
        reply = f"✅ *Found!*

"
        reply += f"• *Serail Info:* {result.get('serail_info')}
"
        reply += f"• *Location:* {result.get('location')}
"
        reply += f"• *Area:* {result.get('area')} m²
"
        reply += f"• *Updated:* {result.get('updated_system')}"
        await update.message.reply_text(reply, parse_mode="Markdown")
    
    elif result["status"] == "not_found":
        await update.message.reply_text("⚠️ No information found for this land number.")
    
    else:
        await update.message.reply_text(f"❌ Error: {result.get('message')}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
