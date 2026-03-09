# SpendLens (`mono-ai-budget-bot`)

> **Telegram-бот для персональної фінансової аналітики Monobank** з **deterministic-first** архітектурою та **контрольованим AI-шаром**.

SpendLens підключається до **Monobank Personal API** через персональний токен користувача, синхронізує транзакції по обраних картках/рахунках, **детерміновано обчислює факти кодом** і вже поверх цих фактів формує:

- звіти;
- відповіді на NLQ-запити;
- insights;
- категоризацію;
- uncategorized flow;
- AI-пояснення у дозволених межах.

Ключовий принцип системи:

> **Code computes facts — AI writes text.**

---

## Зміст

- [1. Що це за продукт](#1-що-це-за-продукт)
- [2. Ключові принципи](#2-ключові-принципи)
- [3. Поточний UX: button-first, а не slash-first](#3-поточний-ux-button-first-а-не-slash-first)
- [4. Канонічний користувацький шлях](#4-канонічний-користувацький-шлях)
- [5. Реально реалізований функціонал](#5-реально-реалізований-функціонал)
- [6. NLQ: питання природною мовою](#6-nlq-питання-природною-мовою)
- [7. Персоналізація](#7-персоналізація)
- [8. Architecture overview](#8-architecture-overview)
- [9. Data flow](#9-data-flow)
- [10. Безпека та обмеження](#10-безпека-та-обмеження)
- [11. Storage model](#11-storage-model)
- [12. CLI та локальна розробка](#12-cli-та-локальна-розробка)
- [13. Environment variables](#13-environment-variables)
- [14. Команди для якості коду](#14-команди-для-якості-коду)
- [15. Demo screenshots](#15-demo-screenshots)
- [16. Поточний стан репозиторію](#16-поточний-стан-репозиторію)

---

## 1. Що це за продукт

SpendLens — це Telegram-бот, який поєднує:

- **Monobank Personal API**;
- **локальний детермінований analytics engine**;
- **button-first Telegram UX**;
- **контрольований AI-шар** для safe summarization / explanation / tool-mode.

Проєкт зібраний не як “генератор красивого тексту”, а як **інженерна фінансова система з AI-політиками**:

- гроші та факти рахує код;
- AI не має повноважень змінювати дані;
- відповіді мають залишатись пояснюваними;
- система повинна бути корисною навіть без AI.

---

## 2. Ключові принципи

### Deterministic first
Усе, що стосується фактів і чисел, обчислюється **тільки кодом**:

- суми;
- кількість транзакцій;
- періоди;
- coverage;
- compare/baseline;
- розбивки по категоріях / мерчантах;
- anomaly / trends / what-if inputs;
- currency conversion.

### Safe AI only
AI у SpendLens **не**:

- рахує гроші;
- бачить Monobank token;
- бачить зайві raw транзакції;
- пише напряму у storage;
- дає інвестиційні / медичні / юридичні поради.

AI **може**:

- сформулювати пояснення поверх already computed facts;
- працювати як semantic interpreter для open-ended запиту;
- повертати strict JSON tool-calls у safe tool-mode;
- працювати тільки через allowlisted deterministic tools.

### Explainable product behavior
Користувачеві має бути зрозуміло:

- коли відповідь побудована повністю детерміновано;
- коли використано AI-пояснення;
- що AI не “вигадує” суми;
- що факти походять з коду та локального ledger.

---

## 3. Поточний UX: button-first, а не slash-first

Поточний продукт — це **button-first Telegram UX**.

Канонічний вхід для користувача:

- `/start`
- onboarding через кнопки
- main menu
- submenu flows
- plain-text NLQ у чаті

Slash-команди можуть існувати в коді як:

- технічні / dev entrypoints;
- fallback paths;
- допоміжні runtime-шляхи.

Але **реальний користувацький продукт** побудований через меню, кнопки, guided flows та звичайні повідомлення в чаті.

---

## 4. Канонічний користувацький шлях

### 4.1 Pre-onboarding
Після `/start` користувач отримує базові entrypoints:

- **Connect**
- **Help**
- **Currency**

На цьому етапі вже доступні:

- довідка;
- огляд продукту;
- екран валют;
- початок підключення Monobank.

### 4.2 Onboarding
Онбординг вважається завершеним тільки коли користувач:

1. підключив Monobank token;
2. вибрав картки;
3. зробив bootstrap history;
4. пройшов персоналізацію;
5. завершив persona step.

### 4.3 Bootstrap history
Стартова історія завантажується кнопками. У поточному коді доступні варіанти:

- **1 місяць**
- **3 місяці**
- **6 місяців**
- **12 місяців**

Після первинного bootstrap далі використовується **інкрементальний sync**.

### 4.4 Main menu
Після завершення onboarding користувач потрапляє в головне меню.

| Розділ | Призначення |
|---|---|
| **Звіти** | Reports by period + AI/facts mode |
| **Uncat** | Робота з некатегоризованими покупками |
| **Категорії** | Таксономія, rules, aliases |
| **Insights** | Trends / anomalies / what-if / forecast / explain |
| **Персоналізація** | Persona, activity, report blocks, uncategorized prompts, AI features |
| **Мої дані** | Token, accounts, refresh, bootstrap, status, wipe |
| **Курси** | Currency screen і conversion support |
| **Help** | Довідка та базові підказки |

### 4.5 NLQ entry
Окремої кнопки **Ask** немає.

**NLQ-вхід — це просто звичайне текстове повідомлення в чат.**

---

## 5. Реально реалізований функціонал

### 5.1 Reports
Підсистема звітів уже продуктово оформлена.

Підтримуються періоди:

- **Today**
- **Last 7 days**
- **Last 30 days**
- **Custom**

Що є в reports flow:

- вибір періоду кнопками;
- окремий вибір режиму побудови:
  - **Лише звіт**
  - **З AI-поясненням**
- custom range з валідацією дат;
- coverage-aware UX;
- deterministic-first rendering;
- optional AI block поверх already computed facts.

#### Coverage behavior
Якщо потрібний період ще не завантажено:

- бот **не вигадує report**;
- бот показує, що даних недостатньо;
- бот направляє до refresh/bootstrap.

#### Reports presets
У personalization already implemented presets:

- **Min**
- **Max**
- **Custom**

Для custom можна керувати блоками окремо по:

- **daily**
- **weekly**
- **monthly**

Підтримувані report blocks у коді:

- `totals`
- `breakdowns`
- `compare_baseline`
- `trends`
- `anomalies`
- `what_if`

---

### 5.2 Uncategorized flow
Окремий UX-контур для некатегоризованих покупок уже є.

Реалізовано:

- queue;
- choose category;
- skip;
- stale click protection;
- pending safety;
- prompt frequency configuration.

Це означає, що бот може:

- знайти uncategorized purchase;
- запропонувати категорію;
- дозволити пропустити;
- захиститись від повторного натискання на stale state;
- керувати тим, коли нагадувати користувачу про cleanup.

---

### 5.3 Categories / taxonomy
Підсистема категорій уже виділена як окремий menu-domain.

Реалізовано:

- add category;
- add subcategory;
- rename;
- delete;
- rules;
- aliases;
- short taxonomy tree preview;
- explicit migration flow for leaf → parent conversion.

#### Rules / aliases
Користувач може працювати з:

- merchant rules;
- recipient rules;
- alias mappings.

#### Safe migration
При спробі зробити leaf-категорію parent-категорією через додавання підкатегорії є **explicit migration prompt**, а не тиха мутація.

При підтвердженні система може безпечно перенести:

- rules;
- aliases.

---

### 5.4 Insights
Insights уже винесені в окремий menu-domain і доступні в main menu.

Підтримуються секції:

- **Trends**
- **Anomalies**
- **What-if**
- **Forecast**
- **Explain**

#### Реальна модель роботи
Insights у поточному коді не є “магією поверх нічого”. Вони працюють на основі вже підготовлених deterministic facts.

При нестачі даних бот:

- не вигадує insight;
- показує дружнє повідомлення;
- направляє до refresh / reports.

---

### 5.5 My Data
Розділ **Мої дані** already implemented як окремий menu-domain.

Доступні дії:

- **Change token**
- **Change accounts**
- **Refresh latest**
- **Bootstrap history**
- **Status**
- **Wipe cache**

#### Що саме це дає
- змінити Monobank token;
- перевибрати картки;
- оновити останні транзакції;
- повторити bootstrap за більший період;
- переглянути стан даних;
- очистити локальний кеш без видалення базового user config.

---

### 5.6 Currency
Currency subsystem already productized.

Підтримується:

- button-first currency screen;
- cache/freshness/source UX;
- refresh;
- stale-cache fallback on fetch error;
- currency normalization;
- conversion from natural text.

#### Приклади підтримуваних формулювань
- `1500 грн в USD`
- `$100 в грн`
- `50 EUR у PLN`

---

### 5.7 Personalization
Personalization уже реалізована як окрема product area.

У меню є такі розділи:

| Розділ | Що налаштовується |
|---|---|
| **Persona** | Тон і стиль формулювання |
| **Activity mode** | Рівень proactive outputs |
| **Report blocks** | Preset/custom blocks для reports |
| **Uncategorized prompts** | Частота нагадувань про uncategorized |
| **AI features** | Які AI-шари дозволені |

---

## 6. NLQ: питання природною мовою

Користувач може просто писати запити в чат — без окремої команди.

### Приклади запитів
- `Скільки я витратив на Мак за 5 днів?`
- `Скільки за січень було поповнень?`
- `Коли востаннє я витрачав на Сільпо?`
- `Скільки витрат було більше 200 грн за 30 днів?`
- `Поясни мої витрати людською мовою`
- `Що це говорить про мої звички витрат?`

### Як це працює
Канонічний flow:

```mermaid
flowchart LR
    U[User text] --> R[Router / Resolver]
    R --> D[Deterministic path]
    R --> C[Clarification]
    R --> S[Safe LLM boundary]
    D --> O[Rendered answer]
    C --> O
    S --> T[Planner / Tool-mode / Narrative]
    T --> O
```

### Поточні властивості NLQ stack
У коді вже є:

- deterministic router;
- resolver;
- executor;
- clarify logic;
- alias memory;
- manual followups;
- semantic boundary;
- safe planner/tool-mode;
- user-visible tool-mode flow.

### Tool-mode
Tool-mode у поточному стані:

- працює тільки через **allowlisted tools**;
- очікує **strict JSON**;
- не пише напряму у storage;
- повертає користувачеві **explainable** відповідь;
- чітко позначає, що AI лише вибрав tool path, а факти витягнув код.

---

## 7. Персоналізація

### 7.1 Persona
Persona editor уже продуктово оформлений.

Поточна модель persona в коді має 4 виміри:

| Поле | Значення |
|---|---|
| `style` | `supportive`, `rational`, `motivator` |
| `verbosity` | `concise`, `balanced`, `detailed` |
| `motivation` | `soft`, `balanced`, `strong` |
| `emoji` | `minimal`, `normal` |

Persona:
- впливає на wording;
- не змінює суми, періоди, coverage, totals або інші deterministic facts.

### 7.2 Activity mode
Activity mode already implemented з такими режимами:

- `loud`
- `quiet`
- `custom`

#### Custom toggles
У коді вже є canonical toggles:

- `auto_reports`
- `uncat_prompts`
- `trends_alerts`
- `anomalies_alerts`
- `forecast_alerts`
- `coach_nudges`

### 7.3 AI features
AI features editor already implemented.

Canonical allowlist feature flags:

- `report_explanations`
- `ai_summaries`
- `ai_insights_wording`
- `semantic_fallback`
- `tool_mode`

Ці прапорці реально впливають на runtime behavior.

### 7.4 Uncategorized prompt frequency
Поточні режими в коді:

- `immediate`
- `daily`
- `weekly`
- `before_report`

---

## 8. Architecture overview

### 8.1 High-level layers

| Layer | Призначення |
|---|---|
| **Monobank / sync** | Підключення, accounts, statement sync, pagination, retry/backoff |
| **Storage** | Users, profiles, reports, taxonomy, rules, uncat, tx ledger |
| **Analytics** | Totals, counts, compare, coverage, trends, anomalies, what-if |
| **Taxonomy** | Categories, rules, aliases, migration logic |
| **NLQ** | Router, resolver, executor, followups, safe tool bridge |
| **Bot UX** | Menus, onboarding, reports, personalization, uncategorized, insights |
| **LLM safety layer** | Explanation, narrative, planner, tool-mode |
| **Currency** | Client, normalize, convert, UI rendering |

### 8.2 Deterministic categorization pipeline
У коді є taxonomy pipeline та categorization logic, яка спирається на:

- rules;
- aliases;
- fallback logic;
- deterministic assignment;
- explicit clarify/uncategorized handling when needed.

### 8.3 Oversized-file refactors already done
Після останніх комітів репозиторій уже розбитий на профільні модулі:

- menu/settings split;
- persona handlers;
- ai settings handlers;
- categories menu handlers;
- insights menu handlers;
- data menu handlers;
- NLQ helper split;
- template domain split.

---

## 9. Data flow

### 9.1 Monobank → ledger

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant MB as Monobank API
    participant L as Ledger / Stores

    U->>B: Connect + choose accounts
    B->>MB: client-info
    MB-->>B: accounts
    U->>B: bootstrap / refresh
    loop paginated statement windows
        B->>MB: statement(account, from, to)
        MB-->>B: tx batch
        B->>L: normalize + dedupe + save
    end
    B-->>U: sync complete
```

### 9.2 Ledger → facts → reports

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant L as Ledger
    participant A as Analytics
    participant AI as LLM

    U->>B: Open Reports / choose period
    B->>L: load period rows
    L-->>B: rows
    B->>A: deterministic computations
    A-->>B: facts
    opt AI mode enabled and allowed
        B->>AI: aggregated facts only
        AI-->>B: explanation text / structured JSON
    end
    B-->>U: report
```

### 9.3 NLQ text → answer

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant R as Router
    participant E as Executor
    participant AI as LLM

    U->>B: plain-text question
    B->>R: parse + route
    alt deterministic path
        R->>E: canonical intent
        E-->>B: deterministic answer
    else clarify
        R-->>B: clarification needed
    else safe AI path
        R->>AI: semantic / planner / tool-mode request
        AI-->>B: safe structured output
    end
    B-->>U: final response
```

---

## 10. Безпека та обмеження

### 10.1 Monobank token
У коді є окремий security layer для token handling.

Важливі властивості:

- token є **read-only**;
- token зберігається локально;
- token шифрується через `cryptography`-based security layer;
- token не повинен потрапляти в AI context.

### 10.2 Data minimization
LLM не отримує повний сирий ledger. Замість цього в safe paths передаються:

- агреговані facts;
- safe filtered payloads;
- структуровані summary-like дані;
- tool calls тільки з allowlist.

### 10.3 Monobank API constraints
Система явно побудована з урахуванням обмежень Monobank API:

- retry/backoff;
- pagination;
- overlap-window;
- safe refresh strategy;
- user-facing guidance on rate limits.

### 10.4 Failure behavior
При збоях продукт не повинен “прикриватися магією”. Поточний код already contains guarded behavior для:

- missing token;
- missing accounts;
- missing ledger;
- stale buttons;
- invalid tool schema;
- AI disabled / no API key;
- currency refresh failures;
- cache/state problems.

---

## 11. Storage model

Поточний стан репозиторію — **local storage mode**.

Дані зберігаються під `CACHE_DIR` (за замовчуванням `.cache`).

### Основні групи storage
- users
- profiles
- reports
- taxonomy
- rules
- uncat
- tx ledger
- meta / scheduler-related state

### Що дає `reset-cache`
CLI команда очищає cache directory і корисна для:

- чистого локального тестування onboarding;
- повторного sync/bootstrap;
- перевірки NLQ/uncat/category flows на чистому state.

---

## 12. CLI та локальна розробка

У поточному коді `monobot` підтримує такі команди:

| Команда | Що робить |
|---|---|
| `health` | Простий health check |
| `status-env` | Показує env-конфіг з mask для секретів |
| `range` | Друкує діапазон для `today/week/month` |
| `reset-cache` | Очищає локальний cache |
| `bot` | Запускає Telegram bot runtime |

### Запуск бота
```bash
poetry run monobot bot
```

### Перевірка середовища
```bash
poetry run monobot status-env
```

### Скидання кешу
```bash
poetry run monobot reset-cache
```

---

## 13. Environment variables

У поточному коді явно використовуються такі variables.

### Core app
| Variable | Призначення |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `MASTER_KEY` | Ключ для шифрування |
| `MONO_TOKEN` | Опціональний debug/default Monobank token |
| `OPENAI_API_KEY` | Ключ для AI paths |
| `OPENAI_MODEL` | OpenAI model name |
| `LOG_LEVEL` | Рівень логування |
| `CACHE_DIR` | Директорія для локального кешу |

### Scheduler
Scheduler також читає env values:

| Variable | Призначення |
|---|---|
| `SCHED_TEST_MODE` | Dev/test scheduler mode |
| `SCHED_TZ` | Timezone for scheduler |
| `SCHED_REFRESH_MINUTES` | Refresh interval |
| `SCHED_DAILY_REFRESH_CRON` | Daily refresh cron |
| `SCHED_WEEKLY_CRON` | Weekly report cron |
| `SCHED_MONTHLY_CRON` | Monthly report cron |

---

## 14. Команди для якості коду

### Install
```bash
poetry install
```

### Format
```bash
poetry run ruff format .
```

### Lint
```bash
poetry run ruff check . --fix
```

### Tests
```bash
poetry run pytest
```

### Pre-commit
```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```

### Git hooks path
У репозиторії є `.githooks/`, тому локально можна увімкнути repo-level hooks:

```bash
git config core.hooksPath .githooks
```

---

## 15. Demo screenshots

У репозиторії вже є demo-зображення.

### Start flow
![Start flow](docs/demo/start.png)

### Help flow
![Help flow](docs/demo/help.png)

### Connect flow
![Connect flow](docs/demo/connect.png)

### Accounts picker
![Accounts picker](docs/demo/accounts.png)

### Weekly report
![Weekly report](docs/demo/week.png)

### AI report
![AI report](docs/demo/week_ai.png)

### No cache / guidance
![No cache](docs/demo/no_info.png)

### NLQ examples
![NLQ example 1](docs/demo/nlq_1.png)

![NLQ example 2](docs/demo/nlq_2.png)

---

## 16. Поточний стан репозиторію

На поточному етапі репозиторій уже **не є раннім MVP з одним монолітним handler-файлом**.

У коді вже є доменно орієнтоване розділення на модулі:

- `bot/`
- `settings/`
- `nlq/`
- `taxonomy/`
- `reports/`
- `currency/`
- `storage/`
- `llm/`
- `analytics/`
- `monobank/`
- `uncat/`

### Що це означає practically
- menu handlers already split by domains;
- settings/persona/AI features already split;
- templates already split by domains;
- NLQ helpers already extracted from oversized modules;
- current repo state is much closer to productized architecture than to prototype bot.

---

## Підсумок

SpendLens у поточному коді — це:

- **button-first Telegram product**;
- **deterministic financial engine**;
- **safe AI integration layer**;
- **structured local-state application**;
- **production-minded architecture**, навіть у локальному runtime режимі.

AI тут не замінює бізнес-логіку і не підміняє собою факти. Він працює як **контрольований шар поверх already computed data**.
