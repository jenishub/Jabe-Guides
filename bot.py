import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import anthropic

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

GROUPS_FILE = "groups.json"

def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r") as f:
            return json.load(f)
    return []

def save_groups(groups):
    with open(GROUPS_FILE, "w") as f:
        json.dump(groups, f, indent=2)

DAY1_OPTIONS = [
    "Arrival + Transfer to Hotel",
    "Arrival with Dinner + Hotel Transfer",
    "Early Arrival with Full Day City Tour"
]

OTHER_DAY_OPTIONS = [
    "City Tour + Kok Tobe",
    "Shymbulak Ski Resort",
    "Charyn Canyon",
    "Charyn Canyon + Kolsay Lakes",
    "Issyk Lake",
    "Almaarasan Gorge + Shopping (Green Bazaar)",
    "Shopping + Departure",
    "Oi Qaragai Resort"
]

EARLY_START_TOURS = ["Charyn Canyon", "Charyn Canyon + Kolsay Lakes"]

def day_options_keyboard(day_num, is_day1=False):
    options = DAY1_OPTIONS if is_day1 else OTHER_DAY_OPTIONS
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"day_{day_num}_{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_itinerary(group_data):
    days_text = ""
    for i, day in enumerate(group_data["days"], 1):
        is_early = any(tour in day for tour in EARLY_START_TOURS)
        start_time = "07:00" if is_early else "10:00"
        days_text += f"Day {i}: {day} (start: {start_time})\n"

    prompt = f"""You are a professional tour operator assistant for JABE Concierge in Almaty, Kazakhstan.

Generate a detailed daily itinerary for the following tour group:

Group: {group_data['name']}
Arrival: Flight {group_data['arrival_flight']} on {group_data['arrival_date']} at {group_data['arrival_time']}
Departure: Flight {group_data['departure_flight']} on {group_data['departure_date']} at {group_data['departure_time']}

Tour Program:
{days_text}

Rules:
- Tours start at 10:00 and finish at 22:00, EXCEPT Charyn Canyon and Charyon Canyon + Kolsay Lakes which start at 07:00
- Day 1 should reference the arrival flight details
- Last day should reference the departure flight
- Use emojis for each activity
- Keep each day concise but informative
- Format each day clearly with the day number and program name as header
- Times should be realistic for each activity

Return ONLY the itinerary text, no intro or outro."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def format_group_message(group):
    status = "✅ Confirmed" if group["status"] == "confirmed" else "❌ Cancelled"
    text = (
        f"🌟 *{group['name']}*\n"
        f"Status: {status}\n\n"
        f"✈️ *FLIGHTS*\n"
        f"Arrival: {group['arrival_flight']} | {group['arrival_date']} | {group['arrival_time']}\n"
        f"Departure: {group['departure_flight']} | {group['departure_date']} | {group['departure_time']}\n\n"
        f"📅 *ITINERARY*\n\n"
        f"{group['itinerary']}"
    )
    return text

def is_admin(user_id):
    return user_id == ADMIN_ID

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "Welcome to JABE Guides Bot!\n\n"
        "Commands:\n"
        "/group — View confirmed groups\n"
        "/addgroup — Add new group (admin only)"
    )

# /group — view all groups
async def view_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = load_groups()
    if not groups:
        await update.message.reply_text("No confirmed groups yet.")
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if g['status'] == 'confirmed' else '❌'} {g['name']}",
            callback_data=f"view_group_{i}"
        )]
        for i, g in enumerate(groups)
    ]
    await update.message.reply_text(
        "📋 *Confirmed Groups:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# /addgroup — admin only
async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only admins can add groups.")
        return
    context.user_data.clear()
    context.user_data["step"] = "group_name"
    await update.message.reply_text("Enter the *group name/subject line:*\nExample: Smith Family - 6 pax - July", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    groups = load_groups()
    user_id = update.effective_user.id

    if query.data.startswith("view_group_"):
        index = int(query.data.split("_")[2])
        group = groups[index]
        text = format_group_message(group)
        keyboard = []
        if is_admin(user_id):
            if group["status"] == "confirmed":
                keyboard.append([
                    InlineKeyboardButton("✏️ Edit Flights", callback_data=f"edit_flights_{index}"),
                    InlineKeyboardButton("❌ Cancel Group", callback_data=f"cancel_group_{index}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("✅ Reconfirm", callback_data=f"reconfirm_group_{index}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_group_{index}")
                ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_groups")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "back_to_groups":
        groups = load_groups()
        if not groups:
            await query.edit_message_text("No confirmed groups yet.")
            return
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if g['status'] == 'confirmed' else '❌'} {g['name']}",
                callback_data=f"view_group_{i}"
            )]
            for i, g in enumerate(groups)
        ]
        await query.edit_message_text(
            "📋 *Confirmed Groups:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("cancel_group_"):
        if not is_admin(user_id):
            return
        index = int(query.data.split("_")[2])
        groups[index]["status"] = "cancelled"
        save_groups(groups)
        await query.edit_message_text(
            f"❌ *{groups[index]['name']}* has been cancelled.",
            parse_mode="Markdown"
        )

    elif query.data.startswith("reconfirm_group_"):
        if not is_admin(user_id):
            return
        index = int(query.data.split("_")[2])
        groups[index]["status"] = "confirmed"
        save_groups(groups)
        await query.edit_message_text(
            f"✅ *{groups[index]['name']}* has been reconfirmed!",
            parse_mode="Markdown"
        )

    elif query.data.startswith("delete_group_"):
        if not is_admin(user_id):
            return
        index = int(query.data.split("_")[2])
        name = groups[index]["name"]
        groups.pop(index)
        save_groups(groups)
        await query.edit_message_text(f"🗑️ *{name}* has been deleted.", parse_mode="Markdown")

    elif query.data.startswith("edit_flights_"):
        if not is_admin(user_id):
            return
        index = int(query.data.split("_")[2])
        context.user_data["editing_group"] = index
        context.user_data["step"] = "edit_arrival_flight"
        await query.edit_message_text(
            "Enter new *arrival flight number:*",
            parse_mode="Markdown"
        )

    elif query.data.startswith("day_"):
        parts = query.data.split("_")
        day_num = int(parts[1])
        option_index = int(parts[2])

        is_day1 = day_num == 1
        options = DAY1_OPTIONS if is_day1 else OTHER_DAY_OPTIONS
        selected = options[option_index]

        days = context.user_data.get("days", [])
        days.append(selected)
        context.user_data["days"] = days

        total_days = context.user_data["total_days"]
        next_day = day_num + 1

        if next_day <= total_days:
            await query.edit_message_text(
                f"✅ Day {day_num}: *{selected}*\n\nNow select program for *Day {next_day}:*",
                parse_mode="Markdown",
                reply_markup=day_options_keyboard(next_day, is_day1=(next_day == 1))
            )
        else:
            await query.edit_message_text("⏳ Generating itinerary with AI, please wait...")
            group_data = {
                "name": context.user_data["group_name"],
                "arrival_flight": context.user_data["arrival_flight"],
                "arrival_date": context.user_data["arrival_date"],
                "arrival_time": context.user_data["arrival_time"],
                "departure_flight": context.user_data["departure_flight"],
                "departure_date": context.user_data["departure_date"],
                "departure_time": context.user_data["departure_time"],
                "days": days,
                "status": "confirmed",
                "created": datetime.now().strftime("%d %B %Y")
            }
            try:
                itinerary = generate_itinerary(group_data)
                group_data["itinerary"] = itinerary
                groups = load_groups()
                groups.append(group_data)
                save_groups(groups)

                message = format_group_message(group_data)
                await query.edit_message_text(f"✅ *Group added successfully!*", parse_mode="Markdown")

                # Post to group chat
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🌟 *NEW CONFIRMED GROUP*\n\n{message}",
                    parse_mode="Markdown"
                )
                context.user_data.clear()
            except Exception as e:
                await query.edit_message_text(f"❌ Error generating itinerary: {str(e)}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        step = context.user_data.get("step")
        if not step:
            return

    step = context.user_data.get("step")
    if not step:
        return

    if step == "group_name":
        context.user_data["group_name"] = update.message.text
        context.user_data["step"] = "arrival_flight"
        await update.message.reply_text("Enter *arrival flight number:*\nExample: TK0123", parse_mode="Markdown")

    elif step == "arrival_flight":
        context.user_data["arrival_flight"] = update.message.text
        context.user_data["step"] = "arrival_date"
        await update.message.reply_text("Enter *arrival date:*\nExample: 10 July", parse_mode="Markdown")

    elif step == "arrival_date":
        context.user_data["arrival_date"] = update.message.text
        context.user_data["step"] = "arrival_time"
        await update.message.reply_text("Enter *arrival time:*\nExample: 14:30", parse_mode="Markdown")

    elif step == "arrival_time":
        context.user_data["arrival_time"] = update.message.text
        context.user_data["step"] = "departure_flight"
        await update.message.reply_text("Enter *departure flight number:*\nExample: TK0124", parse_mode="Markdown")

    elif step == "departure_flight":
        context.user_data["departure_flight"] = update.message.text
        context.user_data["step"] = "departure_date"
        await update.message.reply_text("Enter *departure date:*\nExample: 15 July", parse_mode="Markdown")

    elif step == "departure_date":
        context.user_data["departure_date"] = update.message.text
        context.user_data["step"] = "departure_time"
        await update.message.reply_text("Enter *departure time:*\nExample: 09:00", parse_mode="Markdown")

    elif step == "departure_time":
        context.user_data["departure_time"] = update.message.text
        context.user_data["step"] = "total_days"
        await update.message.reply_text("How many days is the tour?\nExample: 5", parse_mode="Markdown")

    elif step == "total_days":
        try:
            total = int(update.message.text)
            context.user_data["total_days"] = total
            context.user_data["days"] = []
            context.user_data["step"] = "selecting_days"
            await update.message.reply_text(
                "Select program for *Day 1:*",
                parse_mode="Markdown",
                reply_markup=day_options_keyboard(1, is_day1=True)
            )
        except:
            await update.message.reply_text("Please enter a valid number.")

    elif step == "edit_arrival_flight":
        context.user_data["new_arrival_flight"] = update.message.text
        context.user_data["step"] = "edit_arrival_date"
        await update.message.reply_text("Enter new *arrival date:*", parse_mode="Markdown")

    elif step == "edit_arrival_date":
        context.user_data["new_arrival_date"] = update.message.text
        context.user_data["step"] = "edit_arrival_time"
        await update.message.reply_text("Enter new *arrival time:*", parse_mode="Markdown")

    elif step == "edit_arrival_time":
        context.user_data["new_arrival_time"] = update.message.text
        context.user_data["step"] = "edit_departure_flight"
        await update.message.reply_text("Enter new *departure flight number:*", parse_mode="Markdown")

    elif step == "edit_departure_flight":
        context.user_data["new_departure_flight"] = update.message.text
        context.user_data["step"] = "edit_departure_date"
        await update.message.reply_text("Enter new *departure date:*", parse_mode="Markdown")

    elif step == "edit_departure_date":
        context.user_data["new_departure_date"] = update.message.text
        context.user_data["step"] = "edit_departure_time"
        await update.message.reply_text("Enter new *departure time:*", parse_mode="Markdown")

    elif step == "edit_departure_time":
        index = context.user_data["editing_group"]
        groups = load_groups()
        groups[index]["arrival_flight"] = context.user_data["new_arrival_flight"]
        groups[index]["arrival_date"] = context.user_data["new_arrival_date"]
        groups[index]["arrival_time"] = context.user_data["new_arrival_time"]
        groups[index]["departure_flight"] = context.user_data["new_departure_flight"]
        groups[index]["departure_date"] = context.user_data["new_departure_date"]
        groups[index]["departure_time"] = update.message.text
        save_groups(groups)
        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Flights updated successfully!",
            parse_mode="Markdown"
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("group", view_groups))
    app.add_handler(CommandHandler("addgroup", add_group))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Guides bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()