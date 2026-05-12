# 🤖 OLX + Auto.ria Alert Bot

Telegram бот який стежить за новими оголошеннями на OLX та Auto.ria
і надсилає сповіщення першим.

## ✨ Можливості

- 🔍 Пошук на OLX + Auto.ria одночасно
- 🧠 AI аналіз кожного оголошення (Claude)
- 🚨 Антишахрай фільтр
- 💰 Фільтри по ціні та місту
- ⏸ Пауза/відновлення алертів
- 📊 Аналітика ринку

## 🚀 Запуск за 5 хвилин

### 1. Встанови Python
Завантаж з python.org (версія 3.11+)

### 2. Склонуй або розпакуй файли
```
olx_alert_bot/
  bot.py
  parsers.py
  database.py
  analyzer.py
  requirements.txt
  .env.example
```

### 3. Встанови залежності
```bash
pip install -r requirements.txt
```

### 4. Налаштуй .env
```bash
cp .env.example .env
# Відкрий .env і встав свій BOT_TOKEN від @BotFather
```

### 5. Запусти
```bash
python bot.py
```

## 📱 Команди бота

| Команда | Опис |
|---------|------|
| `/start` | Вітання |
| `/add iPhone 14 Київ` | Додати алерт |
| `/add BMW X5 30000-50000` | З фільтром ціни |
| `/list` | Мої алерти |
| `/stats iPhone 14` | Аналітика ринку |
| `/help` | Довідка |

## 🌐 Деплой на Railway (безкоштовно)

1. Зареєструйся на railway.app
2. New Project → Deploy from GitHub
3. Додай змінні середовища (BOT_TOKEN тощо)
4. Deploy!

## 🔑 API ключі

- **BOT_TOKEN** — обов'язковий, від @BotFather
- **ANTHROPIC_API_KEY** — необов'язковий, для AI аналізу (console.anthropic.com)
- **AUTORIA_API_KEY** — необов'язковий, офіційний API Auto.ria (developers.auto.ria.com)
