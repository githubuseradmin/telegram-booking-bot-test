# 🏗 Архитектура · Бот онлайн-записи + Telegram Mini App

Документ для клиента/портфолио: как устроена система, как идут данные, где проверяется занятость, как разворачивать. Диаграммы — Mermaid (рендерятся на GitHub и в большинстве просмотрщиков Markdown).

## Скриншоты интерфейса (Mini App)

Реальные экраны мини-приложения (снято в предпросмотре, тема Telegram):

![Экраны Mini App](screenshots/ui-mockups.svg)

1. **Выбор услуги** → 2. **Выбор мастера** → 3. **Дата и время** → 4. **Контакты и подтверждение**. Прогресс-бар, подсветка выбора, авто-тема Telegram (светлая/тёмная).

## Компоненты

| Модуль | Ответственность |
|---|---|
| `bot.py` | Точка входа, `Dispatcher`/`Router`, FSM-сценарий записи, переносы, оценки, админка, приём данных из Mini App |
| `config.py` | Настройки бизнеса: услуги, цены, часы, рабочие дни, мастера, лояльность, `WEBAPP_URL` |
| `slots.py` | Чистая логика расписания: сетка времени, свободные слоты с учётом ёмкости мастеров (без зависимостей от Telegram → тестируется) |
| `db.py` | SQLite: записи, занятость, отмена/перенос, оценки, агрегаты для статистики; мягкая миграция схемы |
| `keyboards.py` | Inline/Reply-клавиатуры, кнопка запуска Mini App (`web_app`) |
| `texts.py` | Все тексты сообщений (легко менять тон/язык) |
| `reminders.py` | Фоновые задачи (APScheduler): напоминания до визита, запрос оценки после |
| `security.py` | Валидация `initData` (HMAC-SHA256) — на случай backend-API Mini App |
| `webapp/` | Telegram Mini App: `index.html`, `style.css`, `app.js` (статика, HTTPS) |

```mermaid
graph TD
  U["👤 Клиент в Telegram"] -->|чат| B["bot.py<br/>aiogram Router + FSM"]
  U -->|Mini App| W["webapp/<br/>HTML · CSS · JS"]
  W -->|"Telegram.WebApp.sendData(JSON)"| B
  ADM["🛠 Администратор"] -->|/admin| B
  B --> CFG["config.py<br/>услуги · часы · мастера"]
  B --> K["keyboards.py"]
  K --> S["slots.py<br/>свободные слоты"]
  S --> DB[("SQLite · db.py")]
  B --> DB
  B --> T["texts.py"]
  SCH["reminders.py<br/>APScheduler"] --> DB
  SCH -->|напоминания · отзывы| U
  B -.->|initData HMAC<br/>при backend-API| SEC["security.py"]
```

## Поток записи через чат

```mermaid
sequenceDiagram
  actor U as Клиент
  participant B as Бот (FSM)
  participant S as slots.py
  participant DB as SQLite
  participant A as Админ
  U->>B: /start → «Записаться»
  B->>U: список услуг
  U->>B: услуга
  alt у услуги >1 мастера
    B->>U: выбор мастера / «любой»
    U->>B: мастер
  end
  B->>S: free_slots(день, услуга, мастер)
  S->>DB: active_bookings_on(день)
  S-->>B: свободные слоты
  B->>U: дни → время → имя → телефон
  U->>B: подтверждение
  B->>S: повторная проверка слота (анти-дабл-бук)
  B->>DB: add_booking()
  B-->>U: ✅ запись + счётчик лояльности
  B-->>A: 🔔 уведомление о новой записи
```

## Поток записи через Mini App

```mermaid
sequenceDiagram
  actor U as Клиент
  participant W as Mini App (web)
  participant B as Бот
  participant DB as SQLite
  U->>W: открывает Mini App (reply-кнопка web_app)
  W->>W: услуга → мастер → день → время → контакты
  U->>W: «Записаться»
  W->>B: sendData(JSON)
  Note over W,B: доставляет Telegram → отправитель доверенный<br/>(HMAC не нужен для sendData)
  B->>B: F.web_app_data → json.loads
  B->>DB: проверка слота + add_booking()
  B-->>U: ✅ подтверждение
  B-->>U: главное меню
```

## Конечный автомат записи (FSM)

```mermaid
stateDiagram-v2
  [*] --> service: «Записаться»
  service --> master: услуга (мастеров >1)
  service --> date: услуга (1 мастер / без мастеров)
  master --> date: мастер выбран
  date --> time: день
  time --> name: время
  name --> phone: имя
  phone --> confirm: телефон
  confirm --> [*]: подтверждено ✅
  confirm --> date: слот занят → выбрать заново
```

## Модель данных (таблица `bookings`)

| Поле | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | номер записи |
| `user_id` | INTEGER | Telegram ID клиента |
| `username` | TEXT | @username (если есть) |
| `client_name` | TEXT | имя |
| `phone` | TEXT | телефон |
| `service_id` | TEXT | услуга (из config) |
| `master_id` | TEXT | мастер (или NULL = «любой/без мастера») |
| `slot` | TEXT | ISO `YYYY-MM-DDTHH:MM` — начало визита |
| `created_at` | TEXT | когда создана |
| `status` | TEXT | `active` / `cancelled` |
| `reminded` | INTEGER | напоминание отправлено |
| `rating` | INTEGER | оценка 1–5 после визита |
| `feedback` | TEXT | текстовый отзыв |
| `feedback_asked` | INTEGER | запрос оценки отправлен |

## Где проверяется занятость (важно)

Источник правды о свободных слотах — **бэкенд бота** (`slots.free_slots`, данные из SQLite). Mini App не имеет прямого доступа к БД: он показывает сетку и отправляет выбор через `sendData`, а **бот при приёме повторно проверяет слот** и при конфликте отклоняет. Это исключает двойную бронь даже если двое выбрали одно время одновременно.

> Апгрейд: если нужен «живой» календарь занятости в Mini App — добавляется лёгкий read-API (`/free?date=&service=`), который вызывает ту же `slots.free_slots`; запросы из Mini App тогда подписываются `initData` и проверяются `security.validate_init_data` (это backend-сценарий, см. `security.py`).

## Развёртывание

```mermaid
graph LR
  subgraph "VPS ~$5/мес"
    BOT["bot.py (long-polling)<br/>systemd/pm2 · SQLite"]
  end
  subgraph "Статика (бесплатный HTTPS)"
    MA["webapp/ → GitHub Pages /<br/>Cloudflare Pages"]
  end
  TG["Telegram"] --- BOT
  TG --- MA
  BOT -. WEBAPP_URL .-> MA
```

- **Бот:** маленький VPS, запуск `python bot.py` под `systemd`/`pm2` (long-polling — вебхук/домен не нужен). SQLite-файл рядом.
- **Mini App:** статика на GitHub Pages или Cloudflare Pages (бесплатный HTTPS — обязателен для Telegram). URL прописывается в `.env` как `WEBAPP_URL`; бот показывает кнопку запуска.
- **Масштаб:** SQLite держит тысячи записей; при росте — Postgres (заменить только `db.py`).

> Реализация и запуск — в [README.md](README.md). Стратегия услуг — в `../../games-project/24_грузия_вывод_детально.md`.
