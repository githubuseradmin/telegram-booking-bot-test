"""Конфигурация бота. Всё, что меняется под конкретный бизнес, — здесь."""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # без python-dotenv просто читаем переменные окружения как есть
    pass

# --- Технические настройки (из .env) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
]
TIMEZONE = os.getenv("TZ", "Europe/Minsk")
# HTTPS-ссылка на Mini App (GitHub Pages/Cloudflare Pages). Пусто = кнопка скрыта.
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

# --- Данные бизнеса (показываются клиенту) ---
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Салон красоты «Пример»")
BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "г. Минск, ул. Примерная, 1")
BUSINESS_PHONE = os.getenv("BUSINESS_PHONE", "+375 (29) 000-00-00")

# --- Расписание (легко поменять под любой бизнес) ---
WORK_START_HOUR = 10        # начало рабочего дня
WORK_END_HOUR = 20          # конец (последний слот начинается до этого часа)
SLOT_MINUTES = 60           # шаг сетки записи, минут
BOOKING_DAYS_AHEAD = 7      # на сколько дней вперёд открыта запись
WORK_DAYS = {0, 1, 2, 3, 4, 5}   # рабочие дни недели (0=Пн ... 6=Вс). Здесь Пн–Сб
REMINDER_HOURS_BEFORE = 2   # за сколько часов до визита присылать напоминание
LOYALTY_EVERY = 5           # каждый N-й визит — бонус
CURRENCY = "BYN"


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    price: int
    duration: int  # минут (справочно для клиента)


# Список услуг. Поменяй под клиента — бот сам перестроится.
SERVICES = [
    Service("haircut_m", "Мужская стрижка", 25, 60),
    Service("haircut_w", "Женская стрижка", 40, 90),
    Service("color", "Окрашивание", 90, 120),
    Service("manicure", "Маникюр с покрытием", 35, 90),
    Service("brows", "Коррекция и окрашивание бровей", 20, 30),
]


def service_by_id(service_id: str) -> "Service | None":
    return next((s for s in SERVICES if s.id == service_id), None)


# --- Мастера/специалисты ---
ENABLE_MASTERS = True       # False = запись без выбора мастера (как раньше)


@dataclass(frozen=True)
class Master:
    id: str
    name: str
    emoji: str = "👩‍🔧"


MASTERS = [
    Master("anna", "Анна", "💇‍♀️"),
    Master("ivan", "Иван", "💈"),
    Master("lena", "Лена", "💅"),
]

# Какие мастера выполняют услугу (id услуги -> список id мастеров).
SERVICE_MASTERS = {
    "haircut_m": ["ivan"],
    "haircut_w": ["anna", "lena"],
    "color": ["anna"],
    "manicure": ["lena"],
    "brows": ["anna", "lena"],
}


def master_by_id(master_id: str) -> "Master | None":
    return next((m for m in MASTERS if m.id == master_id), None)


def masters_for(service_id: str) -> list[Master]:
    """Мастера, выполняющие услугу. Если не задано — все."""
    ids = SERVICE_MASTERS.get(service_id) or [m.id for m in MASTERS]
    return [m for m in MASTERS if m.id in ids]
