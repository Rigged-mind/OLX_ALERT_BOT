"""
AI аналіз оголошень через Claude API
+ Антишахрай фільтр
"""

import aiohttp
import logging
import os
import re
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Підозрілі слова для антишахрай фільтру
FRAUD_KEYWORDS = [
    "передоплата", "предоплата", "нова пошта тільки",
    "нп тільки", "перевод на карту", "відправлю після оплати",
    "без зустрічі", "пишіть у вайбер", "ціна договірна після оплати",
    "термінова продажа", "їду за кордон"
]

SAFE_KEYWORDS = [
    "торг", "торгуюсь", "документи є", "в наявності",
    "можлива зустріч", "самовивіз"
]


def check_fraud_risk(listing: dict) -> dict:
    """
    Перевіряє оголошення на ознаки шахрайства.
    Повертає: {level: green/yellow/red, message: str}
    """
    risk_score = 0
    reasons = []

    title = (listing.get('title') or '').lower()
    description = (listing.get('description') or '').lower()
    text = title + " " + description

    # Перевірка підозрілих слів
    for keyword in FRAUD_KEYWORDS:
        if keyword in text:
            risk_score += 2
            reasons.append(f'слово "{keyword}"')

    # Вік продавця (якщо є)
    seller_age = listing.get('seller_age_days')
    if seller_age is not None:
        if seller_age < 7:
            risk_score += 3
            reasons.append("акаунт < 7 днів")
        elif seller_age < 30:
            risk_score += 1
            reasons.append("акаунт < 30 днів")

    # Фото
    photos = listing.get('photos', 0)
    if photos == 0:
        risk_score += 2
        reasons.append("немає фото")
    elif photos < 2:
        risk_score += 1
        reasons.append("мало фото")

    # Визначаємо рівень
    if risk_score == 0:
        return {"level": "green", "message": "Безпечно"}
    elif risk_score <= 2:
        reason_str = ", ".join(reasons[:2])
        return {"level": "yellow", "message": f"Обережно ({reason_str})"}
    else:
        reason_str = ", ".join(reasons[:2])
        return {"level": "red", "message": f"⚠️ Ризик! {reason_str}"}


async def analyze_listing(listing: dict) -> str:
    """
    AI аналіз оголошення через Claude API.
    Повертає короткий висновок (1-2 речення).
    """
    if not ANTHROPIC_API_KEY:
        return ""  # Без ключа — пропускаємо

    title = listing.get('title', '')
    price = listing.get('price')
    city = listing.get('city', '')

    prompt = (
        f"Оголошення: {title}\n"
        f"Ціна: {price} грн\n"
        f"Місто: {city}\n\n"
        "Дай ДУЖЕ короткий аналіз (1 речення): чи ціна адекватна, "
        "чи варто звернути увагу. Відповідай українською."
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",  # Найшвидша та найдешевша модель
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                return data["content"][0]["text"].strip()

    except Exception as e:
        logger.error(f"Claude API помилка: {e}")
        return ""
