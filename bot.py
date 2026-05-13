"""
OLX + Auto.ria Alert Bot
Головний файл бота
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import Database
from parsers import OLXParser, AutoRiaParser
from analyzer import analyze_listing, check_fraud_risk
import os

# ⚡ Railway підставляє змінні автоматично — load_dotenv не потрібен
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не знайдено! Додай його в Railway → Variables")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
db = Database()


# ─── КОМАНДИ ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вітання при старті"""
    user = update.effective_user
    text = (
        f"👋 Привіт, {user.first_name}!\n\n"
        "🔔 Я — розумний мисливець за оголошеннями.\n"
        "Слідкую за OLX та Auto.ria і сповіщаю тебе першим.\n\n"
        "📋 *Команди:*\n"
        "/add — додати новий алерт\n"
        "/list — мої активні алерти\n"
        "/stats — статистика ринку\n"
        "/help — довідка\n\n"
        "👇 Почни з /add"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def add_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Додати новий алерт"""
    # Перевіряємо чи є аргументи
    if not context.args:
        await update.message.reply_text(
            "📝 *Як додати алерт:*\n\n"
            "`/add {запит} {місто} {мін_ціна}-{макс_ціна}`\n\n"
            "*Приклади:*\n"
            "`/add iPhone 14 Київ`\n"
            "`/add BMW X5 Харків 30000-50000`\n"
            "`/add квартира 2к Одеса 5000-10000`\n\n"
            "💡 Місто та ціна — необов'язкові",
            parse_mode="Markdown"
        )
        return

    raw = " ".join(context.args)
    user_id = update.effective_user.id

    # Парсимо аргументи
    query, city, min_price, max_price = parse_alert_args(raw)

    # Зберігаємо в базу
    alert_id = db.add_alert(user_id, query, city, min_price, max_price)

    # Формуємо підтвердження
    text = f"✅ *Алерт додано!*\n\n"
    text += f"🔍 Запит: `{query}`\n"
    if city:
        text += f"📍 Місто: {city}\n"
    if min_price or max_price:
        text += f"💰 Ціна: {min_price or '0'} – {max_price or '∞'} грн\n"
    text += f"\n📡 Слідкую на: OLX + Auto.ria\n"
    text += f"⏱ Перевіряю кожні 5 хвилин"

    keyboard = [[InlineKeyboardButton("❌ Видалити", callback_data=f"delete_{alert_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список активних алертів"""
    user_id = update.effective_user.id
    alerts = db.get_user_alerts(user_id)

    if not alerts:
        await update.message.reply_text(
            "😴 У тебе немає активних алертів.\n"
            "Додай перший через /add"
        )
        return

    text = f"📋 *Твої алерти ({len(alerts)}):*\n\n"
    keyboard = []

    for alert in alerts:
        text += f"*#{alert['id']}* — `{alert['query']}`"
        if alert.get('city'):
            text += f" | 📍{alert['city']}"
        if alert.get('min_price') or alert.get('max_price'):
            text += f" | 💰{alert.get('min_price', 0)}-{alert.get('max_price', '∞')} грн"
        text += "\n"
        keyboard.append([
            InlineKeyboardButton(f"⏸ Пауза #{alert['id']}", callback_data=f"pause_{alert['id']}"),
            InlineKeyboardButton(f"❌ #{alert['id']}", callback_data=f"delete_{alert['id']}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика ринку"""
    if not context.args:
        await update.message.reply_text(
            "📊 *Статистика ринку:*\n\n"
            "`/stats iPhone 14` — середня ціна, кількість, динаміка\n"
            "`/stats BMW X5` — аналіз авто ринку",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"⏳ Збираю дані по `{query}`...", parse_mode="Markdown")

    # Парсимо з обох майданчиків
    olx = OLXParser()
    autoria = AutoRiaParser()

    olx_listings = await olx.fetch_listings(query)
    autoria_listings = await autoria.fetch_listings(query)

    all_listings = olx_listings + autoria_listings
    prices = [l['price'] for l in all_listings if l.get('price')]

    if not prices:
        await update.message.reply_text("😕 Не знайдено оголошень для аналізу")
        return

    avg_price = sum(prices) // len(prices)
    min_price = min(prices)
    max_price = max(prices)

    text = (
        f"📊 *Ринок: {query}*\n\n"
        f"📦 Знайдено оголошень: {len(all_listings)}\n"
        f"   • OLX: {len(olx_listings)}\n"
        f"   • Auto.ria: {len(autoria_listings)}\n\n"
        f"💰 *Ціни:*\n"
        f"   • Середня: {avg_price:,} грн\n"
        f"   • Мінімум: {min_price:,} грн\n"
        f"   • Максимум: {max_price:,} грн\n\n"
        f"💡 Додай алерт: `/add {query}`"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *OLX Alert Bot — довідка*\n\n"
        "*/add* — додати алерт\n"
        "*/list* — мої алерти\n"
        "*/stats* — аналіз ринку\n\n"
        "🔍 *Формат пошуку:*\n"
        "`/add {товар} {місто} {ціна від}-{ціна до}`\n\n"
        "📡 *Майданчики:* OLX + Auto.ria\n"
        "⏱ *Частота:* кожні 5 хвилин\n\n"
        "❓ Питання? @your_support"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── CALLBACK КНОПКИ ────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("delete_"):
        alert_id = int(data.split("_")[1])
        db.delete_alert(alert_id, update.effective_user.id)
        await query.edit_message_text("✅ Алерт видалено")

    elif data.startswith("pause_"):
        alert_id = int(data.split("_")[1])
        db.toggle_alert(alert_id, update.effective_user.id)
        await query.edit_message_text("⏸ Алерт на паузі. /list щоб переглянути")


# ─── ПЛАНУВАЛЬНИК ────────────────────────────────────────────

async def check_all_alerts(app):
    """Перевіряє всі активні алерти — запускається кожні 5 хвилин"""
    alerts = db.get_all_active_alerts()
    logger.info(f"Перевіряю {len(alerts)} алертів...")

    olx = OLXParser()
    autoria = AutoRiaParser()

    for alert in alerts:
        try:
            # Отримуємо нові оголошення
            olx_new = await olx.fetch_new_listings(
                alert['query'], alert.get('city'),
                alert.get('min_price'), alert.get('max_price'),
                alert['seen_ids']
            )
            autoria_new = await autoria.fetch_new_listings(
                alert['query'], alert.get('city'),
                alert.get('min_price'), alert.get('max_price'),
                alert['seen_ids']
            )

            new_listings = olx_new + autoria_new

            for listing in new_listings:
                # AI аналіз та перевірка шахраїв
                fraud = check_fraud_risk(listing)
                analysis = await analyze_listing(listing)

                # Формуємо повідомлення
                msg = format_listing_message(listing, fraud, analysis)

                # Надсилаємо користувачу
                await app.bot.send_message(
                    chat_id=alert['user_id'],
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )

                # Зберігаємо ID щоб не дублювати
                db.mark_seen(alert['id'], listing['id'])

        except Exception as e:
            logger.error(f"Помилка алерту {alert['id']}: {e}")


def format_listing_message(listing, fraud, analysis):
    """Форматує повідомлення про нове оголошення"""
    # Іконка ризику
    risk_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(fraud['level'], "⚪")
    source_icon = {"olx": "🛒", "autoria": "🚗"}.get(listing['source'], "📦")

    msg = f"{source_icon} *Нове оголошення!*\n\n"
    msg += f"📌 *{listing['title']}*\n"
    msg += f"💰 {listing['price']:,} грн\n"

    if listing.get('city'):
        msg += f"📍 {listing['city']}\n"

    msg += f"\n{risk_icon} *Безпека:* {fraud['message']}\n"

    if analysis:
        msg += f"🧠 *AI:* {analysis}\n"

    msg += f"\n🔗 [Переглянути оголошення]({listing['url']})"

    return msg


# ─── ПАРСИНГ АРГУМЕНТІВ ──────────────────────────────────────

def parse_alert_args(raw: str):
    """Парсить рядок типу 'iPhone 14 Київ 15000-25000'"""
    import re

    # Шукаємо діапазон цін
    price_match = re.search(r'(\d+)\s*-\s*(\d+)', raw)
    min_price = max_price = None
    if price_match:
        min_price = int(price_match.group(1))
        max_price = int(price_match.group(2))
        raw = raw[:price_match.start()].strip()

    # Відомі міста
    cities = ["Київ", "Харків", "Одеса", "Дніпро", "Запоріжжя",
              "Львів", "Миколаїв", "Херсон", "Вінниця", "Полтава",
              "Чернівці", "Житомир", "Суми", "Черкаси", "Хмельницький"]

    city = None
    for c in cities:
        if c.lower() in raw.lower():
            city = c
            raw = raw.lower().replace(c.lower(), "").strip()
            break

    query = raw.strip()
    return query, city, min_price, max_price


# ─── ЗАПУСК ──────────────────────────────────────────────────

async def setup_scheduler(app):
    """Запускає планувальник всередині працюючого циклу подій (post_init)"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_all_alerts,
        "interval",
        minutes=5,
        args=[app]
    )
    scheduler.start()
    logger.info("⏰ Планувальник успішно запущено!")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_alert))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Планувальник стартує після того, як бот підняв event loop
    app.post_init = setup_scheduler

    logger.info("🤖 Бот запущено!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
