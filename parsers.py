"""
Парсери для OLX та Auto.ria
Обидва повертають уніфікований формат Listing
"""

import asyncio
import aiohttp
import logging
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()
logger = logging.getLogger(__name__)

AUTORIA_API_KEY = os.getenv("AUTORIA_API_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "uk-UA,uk;q=0.9",
}

# Відповідність міст для OLX
OLX_CITIES = {
    "Київ": "kiev",
    "Харків": "kharkov",
    "Одеса": "odessa",
    "Дніпро": "dnepropetrovsk",
    "Запоріжжя": "zaporozhe",
    "Львів": "lvov",
    "Миколаїв": "nikolaev",
    "Херсон": "kherson",
    "Вінниця": "vinnitsa",
    "Полтава": "poltava",
}


def get_driver():
    """Створює headless Chrome драйвер для серверного парсингу."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # нова headless-архітектура Chrome 112+
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


@dataclass
class Listing:
    """Уніфікований формат оголошення"""
    id: str
    source: str          # "olx" або "autoria"
    title: str
    price: Optional[int]
    city: Optional[str]
    url: str
    photos: int = 0
    seller_age_days: Optional[int] = None
    posted_at: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self):
        return self.__dict__


# ─── OLX ПАРСЕР ─────────────────────────────────────────────

class OLXParser:
    BASE_URL = "https://www.olx.ua"

    def build_url(self, query: str, city: str = None) -> str:
        """Будує URL для пошуку на OLX (сортування — найновіші)"""
        q = query.replace(" ", "+")
        city_slug = OLX_CITIES.get(city, "") if city else ""

        if city_slug:
            return f"{self.BASE_URL}/uk/{city_slug}/q-{q}/?search[order]=created_at:desc"
        return f"{self.BASE_URL}/uk/list/q-{q}/?search[order]=created_at:desc"

    async def fetch_listings(
        self,
        query: str,
        city: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> list[dict]:
        """Повертає список оголошень з OLX"""
        url = self.build_url(query, city)

        # Додаємо фільтри ціни
        params = {}
        if min_price:
            params["search[filter_float_price:from]"] = min_price
        if max_price:
            params["search[filter_float_price:to]"] = max_price

        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"OLX відповів {resp.status}")
                        return []
                    html = await resp.text()

            results = self._parse_html(html)
            if results:
                return results

            logger.info("OLX HTML не містить карток, fallback на Selenium")
            return await self._fetch_with_selenium(url)

        except Exception as e:
            logger.error(f"OLX помилка: {e}")
            try:
                logger.info("OLX fallback на Selenium після помилки aiohttp")
                return await self._fetch_with_selenium(url)
            except Exception as selenium_error:
                logger.error(f"OLX Selenium помилка: {selenium_error}")
                return []

    async def _fetch_with_selenium(self, url: str) -> list[dict]:
        """Резервний парсинг OLX через Selenium для динамічних сторінок."""
        def _parse_olx():
            driver = get_driver()
            try:
                driver.get(url)
                driver.implicitly_wait(10)

                items = driver.find_elements("css selector", "[data-cy='l-card']")
                logger.info(f"DEBUG: Знайдено елементів OLX через Selenium: {len(items)}")

                html = driver.page_source
                return self._parse_html(html)
            finally:
                driver.quit()

        return await asyncio.to_thread(_parse_olx)

    def _parse_html(self, html: str) -> list[dict]:
        """Витягує оголошення з HTML"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Основний селектор OLX — data-cy="l-card"
        cards = soup.find_all("div", {"data-cy": "l-card"})

        # Запасний селектор (нова верстка OLX)
        if not cards:
            logger.warning("OLX: data-cy='l-card' не знайдено, пробую запасний селектор")
            cards = soup.select("a.css-z3gu2d")

        logger.info(f"OLX: знайдено карток у HTML: {len(cards)}")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    results.append(listing.to_dict())
            except Exception as e:
                logger.debug(f"Помилка парсингу картки: {e}")
                continue

        logger.info(f"OLX: знайдено {len(results)} оголошень")
        return results

    def _parse_card(self, card) -> Optional[Listing]:
        """Парсить одну картку оголошення"""
        # ID
        listing_id = card.get("id", "")
        if not listing_id:
            return None

        # Заголовок
        title_el = card.find("h6") or card.find("h4")
        title = title_el.get_text(strip=True) if title_el else "Без назви"

        # Посилання
        link_el = card.find("a", href=True)
        url = ""
        if link_el:
            href = link_el["href"]
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

        # Ціна
        price = None
        price_el = card.find("p", {"data-testid": "ad-price"})
        if price_el:
            price_text = price_el.get_text(strip=True)
            price = self._parse_price(price_text)

        # Місто
        city = None
        location_el = card.find("p", {"data-testid": "location-date"})
        if location_el:
            city_text = location_el.get_text(strip=True)
            city = city_text.split(",")[0].strip() if "," in city_text else city_text

        # Фото
        photos = len(card.find_all("img"))

        return Listing(
            id=f"olx_{listing_id}",
            source="olx",
            title=title,
            price=price,
            city=city,
            url=url,
            photos=photos
        )

    def _parse_price(self, text: str) -> Optional[int]:
        """Витягує число з рядка типу '24 500 грн'"""
        import re
        numbers = re.findall(r"\d+", text.replace(" ", ""))
        if numbers:
            return int("".join(numbers[:2]))
        return None

    async def fetch_new_listings(
        self,
        query: str,
        city: str,
        min_price: int,
        max_price: int,
        seen_ids: set
    ) -> list[dict]:
        """Повертає тільки нові оголошення (яких немає в seen_ids)"""
        all_listings = await self.fetch_listings(query, city, min_price, max_price)
        new = [l for l in all_listings if l["id"] not in seen_ids]
        logger.info(f"OLX нових: {len(new)}")
        return new


# ─── AUTO.RIA ПАРСЕР ─────────────────────────────────────────

class AutoRiaParser:
    """
    Auto.ria має офіційний безкоштовний API!
    Реєстрація: https://developers.auto.ria.com/
    """
    API_BASE = "https://developers.auto.ria.com/auto/search"

    # Відповідність міст для Auto.ria (city_id)
    CITY_IDS = {
        "Київ": 9,
        "Харків": 7,
        "Одеса": 12,
        "Дніпро": 4,
        "Запоріжжя": 6,
        "Львів": 10,
    }

    async def fetch_listings(
        self,
        query: str,
        city: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> list[dict]:
        """Отримує оголошення через офіційний Auto.ria API"""

        if not AUTORIA_API_KEY:
            # Якщо немає API ключа — парсимо HTML
            return await self._fetch_html(query, city, min_price, max_price)

        params = {
            "api_key": AUTORIA_API_KEY,
            "q": query,
            "countpage": 20,
            "page": 0,
        }

        if city and city in self.CITY_IDS:
            params["city_id[0]"] = self.CITY_IDS[city]

        if min_price:
            params["price_ot"] = min_price
        if max_price:
            params["price_do"] = max_price

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_BASE,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    data = await resp.json()

            return self._parse_api_response(data)

        except Exception as e:
            logger.error(f"Auto.ria API помилка: {e}")
            return []

    def _parse_api_response(self, data: dict) -> list[dict]:
        """Парсить відповідь Auto.ria API"""
        results = []
        ads = data.get("result", {}).get("search_result", {}).get("ids", [])

        for ad_id in ads[:20]:
            results.append(Listing(
                id=f"autoria_{ad_id}",
                source="autoria",
                title=f"Оголошення #{ad_id}",
                price=None,
                city=None,
                url=f"https://auto.ria.com/auto__{ad_id}.html",
                photos=0
            ).to_dict())

        return results

    async def _fetch_html(
        self,
        query: str,
        city: str = None,
        min_price: int = None,
        max_price: int = None
    ) -> list[dict]:
        """Резервний варіант — парсинг HTML Auto.ria"""
        q = query.replace(" ", "+")
        url = f"https://auto.ria.com/uk/search/?q={q}&indexName=auto"

        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    html = await resp.text()

            return self._parse_autoria_html(html)

        except Exception as e:
            logger.error(f"Auto.ria HTML помилка: {e}")
            return []

    def _parse_autoria_html(self, html: str) -> list[dict]:
        """Парсить HTML сторінку Auto.ria"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Auto.ria використовує section.ticket-item для карток
        cards = soup.find_all("section", class_="ticket-item")

        for card in cards:
            try:
                # ID
                listing_id = card.get("data-advertisement-id", "")
                if not listing_id:
                    continue

                # Заголовок
                title_el = card.find("a", class_="address")
                title = title_el.get_text(strip=True) if title_el else "Авто"

                # URL
                url = ""
                if title_el and title_el.get("href"):
                    url = title_el["href"]

                # Ціна
                price = None
                price_el = card.find("strong", class_="green")
                if price_el:
                    import re
                    nums = re.findall(r"\d+", price_el.get_text().replace(" ", ""))
                    if nums:
                        price = int(nums[0])

                results.append(Listing(
                    id=f"autoria_{listing_id}",
                    source="autoria",
                    title=title,
                    price=price,
                    city=None,
                    url=url
                ).to_dict())

            except Exception as e:
                logger.debug(f"Auto.ria картка помилка: {e}")
                continue

        logger.info(f"Auto.ria: знайдено {len(results)} оголошень")
        return results

    async def fetch_new_listings(
        self,
        query: str,
        city: str,
        min_price: int,
        max_price: int,
        seen_ids: set
    ) -> list[dict]:
        """Повертає тільки нові оголошення"""
        all_listings = await self.fetch_listings(query, city, min_price, max_price)
        new = [l for l in all_listings if l["id"] not in seen_ids]
        logger.info(f"Auto.ria нових: {len(new)}")
        return new
