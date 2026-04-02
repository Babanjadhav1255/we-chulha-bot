import os
import csv
import io
import json
import logging
import asyncio
from datetime import datetime
from google import genai
load_dotenv()

from groq import Groq
from openai import OpenAI
from google import genai as google_genai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config (from .env or Railway Variables) ───────────────────────────────────
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
PRAJWAL_CHAT_ID   = os.environ.get("PRAJWAL_CHAT_ID", "")
OM_CHAT_ID        = os.environ.get("OM_CHAT_ID", "")
SHEET_ID          = os.environ.get("SHEET_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# ── AI clients ────────────────────────────────────────────────────────────────
groq_client   = Groq(api_key=GROQ_API_KEY)

openai_client = OpenAI(api_key=OPENAI_API_KEY)
genai_client = genai.Client(api_key=GEMINI_API_KEY)

# ── WE Chulha Knowledge Base ──────────────────────────────────────────────────
KNOWLEDGE_BASE = """
You are the WE Chulha customer support assistant. Answer questions about the WE Chulha biomass pellet stove.
Be friendly, helpful, and concise. Reply in the same language the customer uses (Hindi, English, or Marathi).
Always end with: "For demo or purchase call: 9765829002 / 7276918873"

PRODUCT FACTS (only use these — do not make up numbers):
- Product: WE Chulha Biomass Pellet Stove
- Price: ₹9,000
- Fuel: Biomass Pellets (₹12–15 per kg)
- Cooking cost: ~₹6 per session (vs ₹9–10 for LPG) — ~40% savings
- Pellet burn times: 150g = 15 min | 400g = 30–40 min | 700g = 70 min
- Battery: 6V 5Ah Lead Acid, charges in ~4 hours, costs ₹0.30–0.35 per charge
- Fan runtime: 10–15 hours per charge
- Pellet specs: density ≥650 kg/m³, moisture <3%, ash ≤5%, diameter ≥8mmwe-chulha-bot
/
85ccd053
Active

Apr 2, 2026, 5:28 PM GMT+5:30
Details
Build Logs
Deploy Logs
Network Flow Logs

Deployment successful

View less

Initialization

(00:00)

Build

(00:51)

Deploy

(00:28)

Post-deploy
- Smoke: Low smoke with forced airflow
- Carbon: Carbon neutral (renewable biomass fuel)
- Warranty: Stove 1 year | Battery 3 years | Charger 3 months
- Pellets available from: Blessed Distributors & Traders LLP, Baner, Pune
- Distributor contact: +91 9503903366
- Instagram: @we.chulha

IMPORTANT: Never claim "90% less smoke" — say "low smoke".
Never give fixed yearly savings without asking how many sessions per day.
If asked about ROI/payback period, ask how many cooking sessions per day first.
You are a SALES ASSISTANT for WE Chulha (not a normal support bot).

Your job:
- Generate interest
- Show cost savings
- Push user to demo or WhatsApp

DO NOT:
- Give long explanations
- Write paragraphs
- Act like customer support

TARGET USERS:
1. Home users
2. Restaurant/dhaba owners

TONE:
- Hinglish (Hindi + simple English)
- Direct, practical
- Street-level language (not corporate)

STRICT RULES:
- Max 3 lines per reply
- Always mention money saving (₹6 vs ₹10 LPG)
- Always end with CTA
- No long paragraphs EVER

RESPONSE FORMAT:
Line 1: Answer
Line 2: ₹ saving
Line 3: CTA

CTA:
Call: 9765829002
WhatsApp: 7276918873

PRODUCT FACTS:
- Price: ₹9,000
- Pellets: ₹12–15/kg
- Cost per cooking: ₹6
- LPG: ₹9–10
- Savings: ~40%
- 400g = 30–40 min
- Battery: 10–15 hrs
- Low smoke (NOT smokeless)

IMPORTANT:
- Do NOT say "90% less smoke"
- Do NOT give long ROI calculations
- Keep everything short

GOAL:
Push user to:
1. Demo (call Prajwal)
2. WhatsApp (Pooja)

CRITICAL SALES RULES:

- Do NOT explain too much
- Do NOT describe product features in detail
- Focus on money saving only

- Always push user to next step
- Ask for action:
  "Aaj ya kal demo book kar doon?"

- Keep replies MAX 3 lines only

- Avoid generic lines like:
  "good product", "best option", "experience"

- Every reply should feel like a salesperson, not support agent

CLOSING STYLE:

Instead of just giving phone number,
ALWAYS push with a question.

Examples:
- "Aaj demo book kar doon?"
- "Call karoge ya WhatsApp pe connect karu?"
- "Aaj hi demo dekh lo?"

Never just end with a plain contact line.

You are a smart sales + support assistant for WE Chulha (biomass pellet stove).

Your job:
- Help user understand product
- Compare LPG vs WE Chulha
- Ask questions to calculate savings
- Show real proof (restaurants + reel)
- Push user to demo or WhatsApp

You are NOT a boring chatbot.
You talk like a real human (Hinglish, simple, practical).

----------------------------------

STRICT RULES:

- Max 3–4 lines per reply
- Hinglish only
- No long paragraphs
- No technical jargon
- Do NOT repeat same lines every time
- Always guide user to next step

----------------------------------

PRODUCT FACTS:

- Price: ₹9000
- Includes: stove + 150kg pellets
- Pellet price: ₹15/kg
- 150kg = ~375 cooking sessions
- Cost per cooking: ₹6
- LPG cost: ₹9–10
- Saving: ₹3–4 per use

- Battery: 6V 5Ah
- Runs: 10–15 hours
- Charge cost: ~₹0.30

- Flame: strong (fan controlled)
- Smoke: low (not smokeless)

----------------------------------

KEY SELLING POINTS:

- ₹9000 me fuel bhi included (150kg pellets)
- LPG dependency khatam
- Daily saving start
- Already restaurants using it

----------------------------------

SOCIAL PROOF:

Always use:
"Gatti Chutney jaise restaurants me WE Chulha use ho raha hai 👍"

----------------------------------

REEL (VERY IMPORTANT):

Use this reel when:
- user confused
- asks "acha hai kya"
- asks "kaise kaam karta hai"
- asks proof

Reel link:
https://www.instagram.com/p/DWHHznNDPJW/

----------------------------------

SMART SALES LOGIC:

If user asks:
- "kitna bachega"
- "mehenga hai"
- "worth hai kya"

👉 FIRST ask:
"Aap daily kitni baar cooking karte ho?"

Then calculate:

3–5 → ₹600/month saving  
5–10 → ₹1200/month saving  
10+ → ₹2000+/month saving  

Always show LOSS from LPG.

----------------------------------

OBJECTION HANDLING:

mehenga:
→ "₹9000 me 150kg pellets already milte hain"

gas better:
→ "agar weak hota toh restaurants use nahi karte"

smoke:
→ "low smoke, traditional chulha se kaafi better"

pellets:
→ "company se milte hain, bulk me available"

----------------------------------

MEDIA HANDLING:

If user asks:
photo / video

Reply:
"WhatsApp pe photos/videos bhej deta hoon 👍  
📲 7276918873"

----------------------------------

CONTACT / HANDOFF:

Demo (Call Prajwal):
📞 9765829002

WhatsApp (Pooja):
📲 7276918873

----------------------------------

RESPONSE STYLE:

Every reply should:
1. Direct answer
2. ₹ saving or value
3. Push (question)

----------------------------------

CLOSING STYLE (IMPORTANT):

Use action-based endings:
- "Demo book kar doon?"
- "Call karoge ya WhatsApp pe connect karu?"
- "Aapke kitchen me demo arrange karu?"

Never end with plain info.

----------------------------------

GOAL:

User ko:
- samjhana
- convince karna
- next step tak le jaana

Next step:
- Demo (call)
- WhatsApp (closing)

----------------------------------

FINAL BEHAVIOR:

- Smart bano
- Short bano
- Helpful bano
- Push karo

Not chatbot.
Act like real sales guy.

CRITICAL:

If user says:
- "acha hai kya"
- "kaise kaam karta hai"
- "samajh nahi aaya"

You MUST send reel.

Do NOT skip reel.

Reel:
https://www.instagram.com/p/DWHHznNDPJW/

DO NOT USE:

- "biomass pellet stove"
- "fan controlled combustion"
- "efficient cooking experience"

USE SIMPLE LANGUAGE:

- "pellets jalte hain"
- "normal chulha se strong flame"
- "₹6 me cooking ho jata hai"

Never repeat same closing.

Rotate:

- "Aaj demo book kar doon?"
- "Aapke kitchen me demo arrange karu?"
- "Call karoge ya WhatsApp pe connect karu?"

Photos WhatsApp pe bhej deta hoon 👍  

Waha detail me samjha bhi dunga  

📲 7276918873  
Connect karu?

IMPORTANT:

Never give CTA twice.

Only ONE closing line:
- Either ask question
- OR give contact

Not both.

If user says:
- "order karna hai"
- "lena hai"
- "buy"

Then:

Do NOT explain anything.

Reply:

"Perfect 👍  
Main abhi arrange kar deta hoon  

📞 Call Prajwal: 9765829002  
Ya WhatsApp pe connect karu?"

Photos WhatsApp pe bhej deta hoon 👍  

Waha real videos + detail bhi dikha deta hoon  

📲 7276918873  
Connect karu?


"""

# ── AI fallback chain: Groq → Gemini → OpenAI ────────────────────────────────
async def ask_ai(question: str) -> str:
    prompt = KNOWLEDGE_BASE + "\n\nReply strictly in 3 short lines.\n\nCustomer: " + question

    # 1️⃣ Groq — fastest, gnerous free tier
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq failed: {e}")

    # 2️⃣ Gemini — tries multiple models
    for gmodel in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]:
        try:
            response = gemini_client.models.generate_content(
                model=gmodel,
                contents=prompt
            )
            return response.text
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                logger.warning(f"Gemini quota hit on {gmodel}, trying next...")
                await asyncio.sleep(1)
                continue
            logger.warning(f"Gemini {gmodel} failed: {e}")
            break

    # 3️⃣ OpenAI — last resort
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI failed: {e}")

    return (
           """Thoda network issue aa gaya 😅\n 
              Aap direct connect kar lo 👍  \n
               📞 9765829002 
               📲 7276918873""" 

        
    )

# ── Google Sheets ─────────────────────────────────────────────────────────────
def get_sheet():
    if not GOOGLE_CREDS_JSON or not SHEET_ID:
        return None
    try:
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_key(SHEET_ID)
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return None

def log_sale_to_sheet(data: dict):
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        try:
            ws = sheet.worksheet("Sales Log")
        except Exception:
            ws = sheet.add_worksheet("Sales Log", rows=1000, cols=10)
            ws.append_row(["Date", "Time", "Logged By", "Area", "Customer Name", "Payment Type", "Amount", "Notes"])
        ws.append_row([
            data.get("date", ""), data.get("time", ""), data.get("logged_by", "Prajwal"),
            data.get("area", ""), data.get("customer", ""), data.get("payment", ""),
            data.get("amount", ""), data.get("notes", ""),
        ])
        return True
    except Exception as e:
        logger.error(f"log_sale_to_sheet error: {e}")
        return False

def log_lead_to_sheet(lead: dict, status: str = "Contacted"):
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        try:
            ws = sheet.worksheet("Leads")
        except Exception:
            ws = sheet.add_worksheet("Leads", rows=1000, cols=8)
            ws.append_row(["Date", "Name", "Phone", "Business", "Area", "Status", "Assigned To", "Notes"])
        ws.append_row([
            datetime.now().strftime("%d/%m/%Y"), lead.get("name", ""), lead.get("phone", ""),
            lead.get("business", ""), lead.get("area", ""), status, "Prajwal", lead.get("notes", ""),
        ])
        return True
    except Exception as e:
        logger.error(f"log_lead_to_sheet error: {e}")
        return False

def get_today_sales_count() -> int:
    sheet = get_sheet()
    if not sheet:
        return 0
    try:
        ws = sheet.worksheet("Sales Log")
        records = ws.get_all_records()
        today = datetime.now().strftime("%d/%m/%Y")
        return sum(1 for r in records if r.get("Date") == today)
    except Exception:
        return 0

# ── State storage ─────────────────────────────────────────────────────────────
user_state = {}
pending_leads = {}

# ── Parse sale ────────────────────────────────────────────────────────────────
def parse_sale(text: str) -> dict | None:
    parts = [p.strip() for p in text.strip().split("|")]
    if len(parts) >= 5 and parts[0].lower() == "sale":
        return {
            "area": parts[1], "customer": parts[2],
            "payment": parts[3], "amount": parts[4],
            "notes": parts[5] if len(parts) > 5 else "",
            "date": datetime.now().strftime("%d/%m/%Y"),
            "time": datetime.now().strftime("%H:%M"),
        }
    return None

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("❓ Product FAQ", callback_data="faq")],
        [InlineKeyboardButton("📦 Log a Sale (Prajwal)", callback_data="log_sale")],
        [InlineKeyboardButton("📋 Blast Leads from CSV (Pooja)", callback_data="lead_blast")],
        [InlineKeyboardButton("📊 Today's Summary", callback_data="summary")],
    ]
    await update.message.reply_text(
        "🔥 *WE Chulha Bot*\n\nWhat do you need?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── /help ─────────────────────────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *WE Chulha Bot — Commands*\n\n"
        "*For Customers (FAQ):*\nJust type your question!\n\n"
        "*For Prajwal (Log Sale):*\n"
        "`Sale | Area | Customer | Payment | Amount`\n"
        "Example: `Sale | Kothrud | Hotel Sai | Cash | 9000`\n\n"
        "*For Pooja (Lead Blast):*\n"
        "1. Use /leadblast\n2. Upload your CSV file\n"
        "CSV format: name, phone, business, area\n\n"
        "*Other:*\n/summary — Today's sales count\n/start — Main menu",
        parse_mode="Markdown"
    )

# ── /summary ──────────────────────────────────────────────────────────────────
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_today_sales_count()
    await update.message.reply_text(
        f"📊 *Today's Summary*\n\n"
        f"✅ Sales logged: *{count}*\n"
        f"💰 Revenue: *₹{count * 9000:,}*\n"
        f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}",
        parse_mode="Markdown"
    )

# ── /leadblast ────────────────────────────────────────────────────────────────
async def leadblast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {"mode": "waiting_csv"}
    await update.message.reply_text(
        "📋 *Lead Blast Mode*\n\nUpload your CSV file now.\n\n"
        "CSV must have columns:\n`name, phone, business, area`\n\n"
        "Example row:\n`Ramesh Sharma, 9876543210, Hotel Sai, Kothrud`",
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
            "📦 *Log a Sale*\n\nSend in this format:\n"
            "`Sale | Area | Customer Name | Payment | Amount`\n\n"
            "Example:\n`Sale | Kothrud | Hotel Sai | Cash | 9000`",
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
        await query.edit_message_text(
            f"📊 *Today's Summary*\n\n"
            f"✅ Sales: *{count}*\n"
            f"💰 Revenue: *₹{count * 9000:,}*\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y')}",
            parse_mode="Markdown"
        )

    elif data.startswith("transfer_"):
        lead_id = data.replace("transfer_", "")
        if lead_id in pending_leads:
            lead = pending_leads[lead_id]
            log_lead_to_sheet(lead, status="Transferred to Prajwal")
            if PRAJWAL_CHAT_ID:
                try:
                    await context.bot.send_message(
                        chat_id=int(PRAJWAL_CHAT_ID),
                        text=(
                            f"🔥 *Hot Lead for You!*\n\n"
                            f"👤 {lead['name']}\n📞 {lead['phone']}\n"
                            f"🏪 {lead['business']}\n📍 {lead['area']}\n\n"
                            f"Call them to book a demo!"
                        ),
                        parse_mode="Markdown"
                    )
                    await query.edit_message_text("✅ Lead transferred to Prajwal!")
                except Exception as e:
                    logger.error(f"Could not reach Prajwal: {e}")
                    await query.edit_message_text("⚠️ Could not reach Prajwal. Lead logged to sheet.")
            else:
                await query.edit_message_text("⚠️ Prajwal's chat ID not set. Lead logged to sheet.")
            del pending_leads[lead_id]

    elif data.startswith("skip_"):
        lead_id = data.replace("skip_", "")
        if lead_id in pending_leads:
            log_lead_to_sheet(pending_leads[lead_id], status="Skipped")
            del pending_leads[lead_id]
        await query.edit_message_text("⏭️ Lead skipped and logged.")

# ── Handle text messages ──────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.lower().startswith("sale"):
        sale = parse_sale(text)
        if sale:
            sale["logged_by"] = update.effective_user.first_name or "Prajwal"
            success = log_sale_to_sheet(sale)
            count = get_today_sales_count()
            await update.message.reply_text(
                f"🔥 *Sale Recorded!*\n\n"
                f"📍 Area: {sale['area']}\n"
                f"🏪 Customer: {sale['customer']}\n"
                f"💳 Payment: {sale['payment']}\n"
                f"💰 Amount: ₹{sale['amount']}\n"
                f"🕐 Time: {sale['time']}\n\n"
                f"📊 Today's total sales: *{count}*\n"
                f"{'✅ Logged to sheet!' if success else '✅ Logged! (Sheet not connected)'}",
                parse_mode="Markdown"
            )
            if OM_CHAT_ID:
                try:
                    await context.bot.send_message(
                        chat_id=int(OM_CHAT_ID),
                        text=(
                            f"🔔 New sale logged!\n"
                            f"{sale['customer']} | {sale['area']} | "
                            f"₹{sale['amount']} | {sale['payment']}\n"
                            f"Total today: {count}"
                        )
                    )
                except Exception as e:
                    logger.error(f"Could not notify Om: {e}")
            return

    try:
        await update.message.chat.send_action("typing")
    except Exception:
        pass

    reply = await ask_ai(text)
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
            "name":     row.get("name",     row.get("Name",     "")).strip(),
            "phone":    row.get("phone",    row.get("Phone",    "")).strip(),
            "business": row.get("business", row.get("Business", "")).strip(),
            "area":     row.get("area",     row.get("Area",     "")).strip(),
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

    for i, lead in enumerate(leads[:20]):
        lead_id = f"{chat_id}_{i}"
        pending_leads[lead_id] = lead

        prompt = (
            f"Write a short, friendly WhatsApp/Telegram message (max 4 lines) in Hindi or English "
            f"for a restaurant owner named {lead['name']} at {lead['business']} in {lead['area']}. "
            f"Introduce WE Chulha biomass pellet stove — saves 40% on cooking fuel vs LPG. "
            f"Price ₹9,000. Ask if they want a free demo. Contact: 9765829002. Keep it natural, not salesy."
        )
        msg = await ask_ai(prompt)

        keyboard = [[
            InlineKeyboardButton("✅ Transfer to Prajwal", callback_data=f"transfer_{lead_id}"),
            InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{lead_id}"),
        ]]
        await update.message.reply_text(
            f"📋 *Lead {i+1}:* {lead['name']} | {lead['business']} | {lead['area']}\n"
            f"📞 {lead['phone']}\n\n*Suggested message:*\n{msg}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await asyncio.sleep(1)

# ── Global error handler ──────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = str(context.error)
    if any(x in err for x in ["TimedOut", "NetworkError", "ReadTimeout", "ConnectionError"]):
        logger.warning(f"Network blip (ignored): {context.error}")
        return
    logger.error(f"Unhandled error: {context.error}", exc_info=context.error)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set! Add it to .env or Railway Variables.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("leadblast", leadblast))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("WE Chulha Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
