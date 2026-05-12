"""
База даних — простий SQLite файл.
Не потребує окремого сервера, ідеально для старту.
"""

import sqlite3
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str = "alerts.db"):
        self.path = path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        """Створює таблиці якщо не існують"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    query       TEXT NOT NULL,
                    city        TEXT,
                    min_price   INTEGER,
                    max_price   INTEGER,
                    active      INTEGER DEFAULT 1,
                    seen_ids    TEXT DEFAULT '[]',
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sent_listings (
                    alert_id    INTEGER,
                    listing_id  TEXT,
                    sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (alert_id, listing_id)
                );
            """)
        logger.info("База даних ініціалізована")

    def add_alert(
        self,
        user_id: int,
        query: str,
        city: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
    ) -> int:
        """Додає новий алерт, повертає його ID"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO alerts (user_id, query, city, min_price, max_price)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, query, city, min_price, max_price)
            )
            return cursor.lastrowid

    def get_user_alerts(self, user_id: int) -> list[dict]:
        """Повертає активні алерти користувача"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM alerts WHERE user_id = ? AND active = 1 ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_active_alerts(self) -> list[dict]:
        """Повертає всі активні алерти (для планувальника)"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM alerts WHERE active = 1"
            ).fetchall()

        alerts = []
        for row in rows:
            alert = dict(row)
            # Завантажуємо seen_ids як множину
            alert['seen_ids'] = set(json.loads(alert.get('seen_ids') or '[]'))
            alerts.append(alert)

        return alerts

    def mark_seen(self, alert_id: int, listing_id: str):
        """Позначає оголошення як надіслане"""
        with self._get_conn() as conn:
            # Зберігаємо в окрему таблицю
            conn.execute(
                "INSERT OR IGNORE INTO sent_listings (alert_id, listing_id) VALUES (?, ?)",
                (alert_id, listing_id)
            )
            # Оновлюємо seen_ids в алерті
            row = conn.execute(
                "SELECT seen_ids FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()

            seen = set(json.loads(row[0] or '[]'))
            seen.add(listing_id)

            # Зберігаємо тільки останні 500 ID щоб не роздувати базу
            seen_list = list(seen)[-500:]
            conn.execute(
                "UPDATE alerts SET seen_ids = ? WHERE id = ?",
                (json.dumps(seen_list), alert_id)
            )

    def delete_alert(self, alert_id: int, user_id: int):
        """Видаляє алерт (тільки свій)"""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM alerts WHERE id = ? AND user_id = ?",
                (alert_id, user_id)
            )

    def toggle_alert(self, alert_id: int, user_id: int):
        """Перемикає паузу алерту"""
        with self._get_conn() as conn:
            conn.execute(
                """UPDATE alerts
                   SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
                   WHERE id = ? AND user_id = ?""",
                (alert_id, user_id)
            )
