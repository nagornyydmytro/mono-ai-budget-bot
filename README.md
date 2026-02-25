# Mono AI Budget Bot

Telegram-бот для аналітики витрат Monobank з AI-інсайтами.

Бот підключається до Monobank Personal API по токену користувача, синхронізує транзакції у локальний ledger, рахує фінансові метрики за період і генерує AI-звіт (короткий аналіз + рекомендації).

LLM (OpenAI) отримує лише агреговані факти (facts JSON). Усі суми та метрики рахує код, а не модель.

---

## Основні можливості

### Підключення
- /connect — додати Monobank token
- /status — перевірити доступ до API
- /accounts — вибрати рахунки/картки
- /refresh — примусова синхронізація ledger

### Звіти
- /today — витрати за сьогодні
- /week — витрати за останні 7 днів + порівняння з попередніми 7
- /month — витрати за останні 30 днів + порівняння з попередніми 30

### AI-інсайти
Модель генерує:
- короткий підсумок змін
- 3–7 рекомендацій, прив’язаних до конкретних цифр
- конкретний “наступний крок”

Модель не надає інвестиційних, медичних або юридичних порад.

### Scheduler
- автоматичні weekly / monthly звіти
- пер-користувацький refresh
- захист від одночасних sync

---

## Архітектура

Monobank API  
→ Ledger (jsonl, локально)  
→ Обчислення facts  
→ LLM prompt  
→ Telegram report  

LLM не працює з сирими транзакціями — лише з агрегованими даними.

---

## Quickstart (Local)

1. Клонувати репозиторій

git clone https://github.com/nagornyydmytro/mono-ai-budget-bot.git  
cd mono-ai-budget-bot

2. Створити virtualenv

python -m venv .venv  
source .venv/bin/activate   (Windows: .venv\Scripts\activate)

3. Встановити залежності

pip install -r requirements.txt

4. Задати environment variables

Linux / macOS:
export TELEGRAM_BOT_TOKEN=...
export OPENAI_API_KEY=...

Windows (PowerShell):
setx TELEGRAM_BOT_TOKEN "..."
setx OPENAI_API_KEY "..."

Опційно для тестування scheduler:
SCHED_TEST_MODE=1

5. Запуск

python -m mono_ai_budget_bot.bot

---

## Як отримати Monobank token

1. Перейти на:
https://api.monobank.ua/index.html

2. Згенерувати персональний токен

3. Надіслати його боту через /connect

Важливо: токен дає доступ до персональних фінансових даних. Не передавайте його третім особам.

---

## Зберігання даних (локально)

До деплою всі дані зберігаються у папці .cache/

.cache/users/ — конфіг користувача (token, обрані рахунки)  
.cache/tx/ — ledger транзакцій (jsonl)  
.cache/reports/ — кешовані звіти  
.cache/ratelimit* — стан rate limiter  

Щоб повністю видалити дані:

Linux / macOS:
rm -rf .cache

Windows:
видалити папку .cache вручну

---

## Обмеження Monobank API

- statement: максимум 31 день + 1 година за запит
- rate limit: 1 запит / 60 секунд
- до 500 транзакцій за відповідь

Для дуже активних користувачів можливе неповне покриття (планується покращена пагінація).

---

## Privacy

- Дані зберігаються локально (до хостингу).
- LLM отримує лише агреговані facts.
- Сирі транзакції не передаються в OpenAI.

---

## Roadmap

- NLQ: “Скільки я витратив на Макдональдс за 15 днів?”
- User spending profile
- Persistent storage (Cloudflare)
- Async Monobank client
- CI + automated tests