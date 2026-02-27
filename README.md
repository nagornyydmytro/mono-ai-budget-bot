Mono AI Budget Bot
==================

Telegram-бот для аналітики витрат Monobank з контрольованою AI-надбудовою.

Ідея: бот підключається до Monobank Personal API (по токену користувача), синхронізує транзакції по обраним рахункам/карткам, рахує метрики за період (кодом) і формує звіт. AI (LLM) отримує лише агреговані “facts” (JSON) і генерує короткі інсайти та рекомендації, прив’язані до цифр.

Проєкт зроблений як тестове завдання на AI-інтернатуру: акцент на архітектурі, стабільності, безпеці, обмеженнях API, і “вау”-ефекті від AI без втрати контролю.
Цей проєкт створений із активним використанням AI-інструментів для демонстрації практичних навичок роботи зі штучним інтелектом у реальному продукті.

AI застосовувався не лише для генерації інсайтів у звітах, а й як інженерний інструмент: проєктування архітектури, рефакторинг коду, формування структурованих відповідей LLM, побудова guardrails, обробка природної мови (NLQ) та оптимізація взаємодії з зовнішніми API. Мета — показати вміння інтегрувати AI системно, контрольовано та безпечно, а не просто “додати модель до коду”.

Що вміє (MVP)
-------------

1) Підключення Monobank
- /connect — додати Monobank token (per-user)
- /status — перевірка доступу до Monobank (client-info / statement)

2) Вибір рахунків/карток
- /accounts — обрати рахунки/картки для аналізу
- після вибору карток бот пропонує первинне завантаження історії (1 місяць або 3 місяці), далі — інкрементальні sync

3) On-demand звіти
- /today — витрати за сьогодні
- /week — витрати за останні 7 днів + порівняння з попередніми 7 днями
- /month — витрати за останні 30 днів (в межах 31d+1h API) + порівняння з попередніми 30 днями

4) Регулярні звіти
- weekly / monthly автозвіти в заданий час (через scheduler)
- refresh/sync у фоні, з локами, щоб один користувач не запускав кілька sync одночасно

5) Звіт містить (типова структура)
- Total spend / income / transfers
- Transactions count
- Top categories / top merchants
- Breakdown by account (по картках)
- Compare with previous period
- AI insights (optional): summary + changes + 3–7 рекомендацій + next_step

AI частина: як це працює (важливо)
---------------------------------

Принцип: “Код рахує факти — LLM пише текст”.

1) Аналітика (код)
- збирає транзакції в ledger
- рахує метрики: totals, counts, топи, розбивки, порівняння періодів
- додає grounded частки (%) у facts:
  - category_shares_real_spend
  - top_merchants_shares_real_spend

2) Генерація інсайтів (LLM)
- LLM отримує facts JSON
- повертає структурований JSON: summary / changes / recs / next_step
- персоналізація: LLM також отримує user_profile (довгострокова “норма” користувача: avg_check, топи)
- guardrails:
  - без інвестиційних/кредитних/юридичних порад
  - без “гарантій”
  - без вигаданих тверджень (тільки grounded на facts)

3) Failure mode (graceful fallback)
- якщо LLM недоступний / таймаут / помилка формату → бот не падає
- показує facts-репорт без AI

NLQ (natural language queries)
------------------------------

Підтримується легкий regex-NLQ (без LLM), приклади:
- “Скільки я за останні 15 днів витратив на Макдональдс?”
- “Скільки транзакцій за тиждень?”

NLQ зараз підтримує:
- spend_sum (сума реальних витрат, без переказів)
- spend_count (кількість витрат/транзакцій)
- період: N днів / тиждень / місяць / сьогодні
- фільтр по мерчанту: “на <текст>”

Monobank API: обмеження і як ми їх обходимо
------------------------------------------

Ключове обмеження Monobank Personal API:
- Rate limit: 1 request / 60 sec на client-info та statement
- Statement діапазон: максимум 31 доба + 1 година за один запит

Що робить бот:
- кешує і тротлить запити (не створює 429-шторм)
- використовує retry/backoff на 429
- тримає per-user locks
- синхронізує інкрементально (оновлення по часу, з overlap)

Зберігання даних (локально до хостингу)
---------------------------------------

До деплою/хостингу дані зберігаються локально у директорії .cache:
- users: профіль користувача, налаштування, вибрані рахунки/картки, зашифрований token
- ledger: транзакції (JSONL) по user_id/account_id
- profiles: збережений user_profile для персоналізації
- reports: кеш звітів (опційно)
- meta: last sync timestamp тощо

Як “очистити для чистого тесту”:
- видалити директорію .cache (або відповідну директорію CACHE_DIR)

Безпека і приватність
---------------------

- Monobank token зберігається зашифрованим (MASTER_KEY, fernet)
- В LLM (OpenAI) не відправляються сирі транзакції (raw statement)
- В LLM відправляються тільки агреговані facts JSON (суми, топи, метрики)
- Логи не містять токенів

Встановлення і запуск (локально)
--------------------------------

Варіант A (Poetry)
1) poetry install
2) Створи .env (див. .env.example)
3) Запуск:
- poetry run monobot bot

Варіант B (venv)
- python -m venv .venv
- activate
- python -m mono_ai_budget_bot.bot.app

Швидка перевірка після встановлення
-----------------------------------

1) Перевір конфігурацію:
- poetry run monobot status-env

2) Перевір, що CLI працює:
- poetry run monobot health

3) Запусти тести:
- poetry run pytest

Якщо OPENAI_API_KEY не задано — бот працює у facts-only режимі (без AI-інсайтів), але повністю функціональний.

ENV змінні (мінімальний набір)
------------------------------

REQUIRED:
- TELEGRAM_BOT_TOKEN
- MASTER_KEY (fernet key для шифрування токенів)

OPTIONAL:
- OPENAI_API_KEY (якщо не задано → facts-only)
- OPENAI_MODEL
- CACHE_DIR
- LOG_LEVEL

Примітка:
MONO_TOKEN не потрібен для MVP — Monobank token вводиться користувачем через /connect і зберігається зашифрованим.

Scheduler (optional):
- SCHED_TZ
- SCHED_REFRESH_MINUTES
- SCHED_DAILY_REFRESH_CRON / SCHED_WEEKLY_CRON / SCHED_MONTHLY_CRON

1-minute walkthrough
-----------------------------------

1) Запуск і перевірка оточення:
- poetry install
- cp .env.example .env
- (згенеруй MASTER_KEY та встав у .env)
- poetry run monobot status-env
- poetry run pytest

2) Демонстрація user flow в Telegram:
- /connect → додай Monobank token
- /accounts → обери рахунки/картки
- bootstrap → обери 1 або 3 місяці (первинне завантаження)
- /week або /month → подивись звіт + compare з попереднім періодом
- Напиши NLQ: “Скільки я за останні 15 днів витратив на Макдональдс?”

Демо (для інтернатури)
----------------------

Connect flow:
![Connect flow](docs/demo/connect.png)

Accounts flow:
![Accounts flow](docs/demo/accounts.png)

Weekly report:
![Weekly report](docs/demo/week.png)

NLQ example:
![NLQ example](docs/demo/nlq.png)

Roadmap (після здачі)
---------------------

Хостинг (Cloudflare):
- storage interface (local vs persistent)
- D1/KV для users/ledger/reports/caches
- global refresh кожні 2–3 години без 429-шторму
- async http + async rate limit

Полірування:
- деталізація MCC та кастомні категорії
- складніший outliers (звички/аномалії)
- більше NLQ інтентів (topN, compare periods, by card)
- merchant/category normalization (кеш)
- templates для UI, налаштування автозвітів, метрики