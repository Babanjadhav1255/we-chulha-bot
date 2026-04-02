import os
import csv
import io
import logging
import asyncio
from datetime import datetime
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── ENV vars (set these in Railway) ──────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
PRAJWAL_CHAT_ID  = os.environ.get("PRAJWAL_CHAT_ID", "")   # Prajwal's Telegram chat ID
OM_CHAT_ID       = os.environ.get("OM_CHAT_ID", "")         # Om's Telegram chat ID
SHEET_ID         = os.environ.get("SHEET_ID", "")           # Google Sheet ID (after creating)
GOOGLE_CREDS_JSON= os.environ.get("GOOGLE_CREDS_JSON", "")  # Service account JSON as string

# ── Gemini setup ─────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── WE Chulha Knowledge Base ──────────────────────────────────────────────────
KNOWLEDGE_BASE = """
You are the WE Chulha customer support assistant. Answer questions about the WE Chulha biomass pellet stove.
Be friendly, helpful, and concise. Reply in the same language the customer uses (Hindi, English, or Marathi).
Always end with: "For demo or purchase call: 9765829002 / 7666588707"

PRODUCT FACTS (only use these — do not make up numbers):
- Product: WE Chulha Biomass Pellet Stove
- Price: ₹9,000
- Fuel: Biomass Pellets (₹12–15 per kg)
- Cooking cost: ~₹6 per session (vs ₹9–10 for LPG) — ~40% savings
- Pellet burn times: 150g = 15 min | 400g = 30–40 min | 700g = 70 min
- Battery: 6V 5Ah Lead Acid, charges in ~4 hours, costs ₹0.30–0.35 per charge
- Fan runtime: 10–15 hours per charge
- Pellet specs: density ≥650 kg/m³, moisture <3%, ash ≤5%, diameter ≥8mm
- Smoke: Low smoke with forced airflow
- Carbon: Carbon neutral (renewable biomass fuel)
- Warranty: Stove 1 year | Battery 3 years | Charger 3 months
- Pellets available from: Blessed Distributors & Traders LLP, Baner, Pune
- Distributor contact: +91 9503903366
- Instagram: @we.chulha

IMPORTANT: Never claim "90% less smoke" — say "low smoke". 
Never give fixed yearly savings without asking how many sessions per day.
If asked about ROI/payback period, ask how many cooking sessions per day first.
"""

# ── Google Sheets setup ───────────────────────────────────────────────────────
def get_sheet():
    if not GOOGLE_CREDS_JSON or not SHEET_ID:
        return None
    try:
        import json
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return None

def log_sale_to_sheet(data: dict):
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        ws = sheet.worksheet("Sales Log")
    except:
        ws = sheet.add_worksheet("Sales Log", rows=1000, cols=10)
        ws.append_row(["Date","Time","Logged By","Area","Customer Name","Payment Type","Amount","Notes"])
    row = [
        data.get("date", ""),
        data.get("time", ""),
        data.get("logged_by", "Prajwal"),
        data.get("area", ""),
        data.get("customer", ""),
        data.get("payment", ""),
        data.get("amount", ""),
        data.get("notes", ""),
    ]
    ws.append_row(row)
    return True

def log_lead_to_sheet(lead: dict, status: str = "Contacted"):
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        ws = sheet.worksheet("Leads")
    except:
        ws = sheet.add_worksheet("Leads", rows=1000, cols=8)
        ws.append_row(["Date","Name","Phone","Business","Area","Status","Assigned To","Notes"])
    row = [
        datetime.now().strftime("%d/%m/%Y"),
        lead.get("name", ""),
        lead.get("phone", ""),
        lead.get("business", ""),
        lead.get("area", ""),
        status,
        "Prajwal",
        lead.get("notes", ""),
    ]
    ws.append_row(row)
    return True

# ── State storage (in-memory, simple) ────────────────────────────────────────
user_state = {}   # chat_id -> {"mode": "sale_log" | "lead_blast", "data": {...}}
pending_leads = {}  # stores leads pending transfer to Prajwal

# ── Gemini FAQ helper ─────────────────────────────────────────────────────────
async def ask_gemini(question: str) -> str:
    try:
        response = model.generate_content(KNOWLEDGE_BASE + "\n\nCustomer question: " + question)
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "Sorry, I couldn't process that. Please call us at 9765829002."

# ── Parse sale message ────────────────────────────────────────────────────────
def parse_sale(text: str) -> dict | None:
    """
    Expected format: Sale | Area | Customer Name | Payment | Amount
    Example: Sale | Kothrud | Hotel Sai | Cash | 9000
    Also accepts: sale kothrud hotel sai cash 9000 (flexible)
    """
    text = text.strip()
    parts = [p.strip() for p in text.split("|")]
    if len(parts) >= 5 and parts[0].lower() == "sale":
        return {
            "area": parts[1],
            "customer": parts[2],
            "payment": parts[3],
            "amount": parts[4],
            "notes": parts[5] if len(parts) > 5 else "",
            "date": datetime.now().strftime("%d/%m/%Y"),
            "time": datetime.now().strftime("%H:%M"),
        }
    return None

# ── Count today's sales ───────────────────────────────────────────────────────
def get_today_sales_count() -> int:
    sheet = get_sheet()
    if not sheet:
        return 0
    try:
        ws = sheet.worksheet("Sales Log")
        records = ws.get_all_records()
        today = datetime.now().strftime("%d/%m/%Y")
        return sum(1 for r in records if r.get("Date") == today)
    except:
        return 0

# ── /start command ────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("❓ Product FAQ", callback_data="faq")],
        [InlineKeyboardButton("📦 Log a Sale (Prajwal)", callback_data="log_sale")],
        [InlineKeyboardButton("📋 Blast Leads from CSV (Pooja)", callback_data="lead_blast")],
        [InlineKeyboardButton("📊 Today's Summary", callback_data="summary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 *WE Chulha Bot*\n\nWhat do you need?",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ── /help command ─────────────────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *WE Chulha Bot — Commands*\n\n"
        "*For Customers (FAQ):*\n"
        "Just type your question!\n\n"
        "*For Prajwal (Log Sale):*\n"
        "`Sale | Area | Customer | Payment | Amount`\n"
        "Example: `Sale | Kothrud | Hotel Sai | Cash | 9000`\n\n"
        "*For Pooja (Lead Blast):*\n"
        "1. Use /leadblast\n"
        "2. Upload your CSV file\n"
        "CSV format: name, phone, business, area\n\n"
        "*Other:*\n"
        "/summary — Today's sales count\n"
        "/start — Main menu",
        parse_mode="Markdown"
    )

# ── /summary command ──────────────────────────────────────────────────────────
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_today_sales_count()
    total = count * 9000
    await update.message.reply_text(
        f"📊 *Today's Summary*\n\n"
        f"✅ Sales logged: *{count}*\n"
        f"💰 Revenue: *₹{total:,}*\n"
        f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}",
        parse_mode="Markdown"
    )

# ── /leadblast command ────────────────────────────────────────────────────────
async def leadblast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {"mode": "waiting_csv"}
    await update.message.reply_text(
        "📋 *Lead Blast Mode*\n\n"
        "Upload your CSV file now.\n\n"
        "CSV must have columns:\n"
        "`name, phone, business, area`\n\n"
        "Example row:\n"
        "`Ramesh Sharma, 9876543210, Hotel Sai, Kothrud`",
        parse_mode="Markdown"
    )

# ── Inline button callbacks ───────────────────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "faq":
        await query.edit_message_text("❓ Ask me anything about WE Chulha! Type your question.")
        user_state[chat_id] = {"mode": "faq"}

    elif data == "log_sale":
        await query.edit_message_text(
            "📦 *Log a Sale*\n\n"
            "Send in this format:\n"
            "`Sale | Area | Customer Name | Payment | Amount`\n\n"
            "Example:\n"
            "`Sale | Kothrud | Hotel Sai | Cash | 9000`",
            parse_mode="Markdown"
        )
        user_state[chat_id] = {"mode": "sale_log"}

    elif data == "lead_blast":
        await query.edit_message_text(
            "📋 *Lead Blast*\n\nUpload your CSV file (name, phone, business, area).",
            parse_mode="Markdown"
        )
        user_state[chat_id] = {"mode": "waiting_csv"}

    elif data == "summary":
        count = get_today_sales_count()
        total = count * 9000
        await query.edit_message_text(
            f"📊 *Today's Summary*\n\n"
            f"✅ Sales: *{count}*\n"
            f"💰 Revenue: *₹{total:,}*\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y')}",
            parse_mode="Markdown"
        )

    elif data.startswith("transfer_"):
        lead_id = data.replace("transfer_", "")
        if lead_id in pending_leads:
            lead = pending_leads[lead_id]
            log_lead_to_sheet(lead, status="Transferred to Prajwal")
            if PRAJWAL_CHAT_ID:
                await context.bot.send_message(
                    chat_id=int(PRAJWAL_CHAT_ID),
                    text=(
                        f"🔥 *Hot Lead for You!*\n\n"
                        f"👤 {lead['name']}\n"
                        f"📞 {lead['phone']}\n"
                        f"🏪 {lead['business']}\n"
                        f"📍 {lead['area']}\n\n"
                        f"Call them to book a demo!"
                    ),
                    parse_mode="Markdown"
                )
                await query.edit_message_text(f"✅ Lead transferred to Prajwal!")
            else:
                await query.edit_message_text(f"⚠️ Prajwal's chat ID not set. Lead logged to sheet.")
            del pending_leads[lead_id]

    elif data.startswith("skip_"):
        lead_id = data.replace("skip_", "")
        if lead_id in pending_leads:
            lead = pending_leads[lead_id]
            log_lead_to_sheet(lead, status="Skipped")
            del pending_leads[lead_id]
        await query.edit_message_text("⏭️ Lead skipped and logged.")

# ── Handle text messages ──────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    mode = user_state.get(chat_id, {}).get("mode", "faq")

    # Always try to parse sale format first regardless of mode
    if text.lower().startswith("sale"):
        sale = parse_sale(text)
        if sale:
            sale["logged_by"] = update.effective_user.first_name or "Prajwal"
            success = log_sale_to_sheet(sale)
            count = get_today_sales_count()
            status = "✅ Logged to sheet!" if success else "✅ Logged! (Sheet not connected)"
            await update.message.reply_text(
                f"🔥 *Sale Recorded!*\n\n"
                f"📍 Area: {sale['area']}\n"
                f"🏪 Customer: {sale['customer']}\n"
                f"💳 Payment: {sale['payment']}\n"
                f"💰 Amount: ₹{sale['amount']}\n"
                f"🕐 Time: {sale['time']}\n\n"
                f"📊 Today's total sales: *{count}*\n"
                f"{status}",
                parse_mode="Markdown"
            )
            # Notify Om
            if OM_CHAT_ID:
                await context.bot.send_message(
                    chat_id=int(OM_CHAT_ID),
                    text=f"🔔 New sale logged!\n{sale['customer']} | {sale['area']} | ₹{sale['amount']} | {sale['payment']}\nTotal today: {count}"
                )
            return

    # FAQ / customer support — default for everything else
    await update.message.chat.send_action("typing")
    reply = await ask_gemini(text)
    await update.message.reply_text(reply)

# ── Handle CSV file upload ────────────────────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mode = user_state.get(chat_id, {}).get("mode", "")

    if mode != "waiting_csv":
        await update.message.reply_text("Send /leadblast first, then upload your CSV.")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".csv"):
        await update.message.reply_text("⚠️ Please upload a .csv file only.")
        return

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode("utf-8")

    reader = csv.DictReader(io.StringIO(content))
    leads = []
    for row in reader:
        lead = {
            "name": row.get("name", row.get("Name", "")).strip(),
            "phone": row.get("phone", row.get("Phone", "")).strip(),
            "business": row.get("business", row.get("Business", "")).strip(),
            "area": row.get("area", row.get("Area", "")).strip(),
            "notes": "",
        }
        if lead["name"] and lead["phone"]:
            leads.append(lead)

    if not leads:
        await update.message.reply_text("⚠️ No valid leads found. Check CSV format: name, phone, business, area")
        return

    await update.message.reply_text(
        f"✅ Found *{len(leads)} leads*. Starting outreach now...",
        parse_mode="Markdown"
    )

    user_state[chat_id] = {"mode": "lead_review"}

    # Generate personalised message for each lead via Gemini + show transfer buttons
    for i, lead in enumerate(leads[:20]):  # cap at 20 to avoid spam
        lead_id = f"{chat_id}_{i}"
        pending_leads[lead_id] = lead

        # Generate outreach message
        prompt = (
            f"Write a short, friendly WhatsApp/Telegram message (max 4 lines) in Hindi or English "
            f"for a restaurant owner named {lead['name']} at {lead['business']} in {lead['area']}. "
            f"Introduce WE Chulha biomass pellet stove — saves 40% on cooking fuel vs LPG. "
            f"Price ₹9,000. Ask if they want a free demo. Contact: 9765829002. Keep it natural, not salesy."
        )
        msg = await ask_gemini(prompt)

        keyboard = [
            [
                InlineKeyboardButton("✅ Transfer to Prajwal", callback_data=f"transfer_{lead_id}"),
                InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{lead_id}"),
            ]
        ]
        await update.message.reply_text(
            f"📋 *Lead {i+1}:* {lead['name']} | {lead['business']} | {lead['area']}\n"
            f"📞 {lead['phone']}\n\n"
            f"*Suggested message:*\n{msg}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await asyncio.sleep(0.5)  # avoid rate limiting

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("leadblast", leadblast))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("WE Chulha Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
