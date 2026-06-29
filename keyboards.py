"""Клавиатуры Telegram. Логика свободных слотов — в slots.py (переиспользуется)."""
from aiogram.types import (
    InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from slots import free_slots, assign_master, work_dates  # noqa: F401 (re-export)
from texts import WEEKDAYS, MONTHS


# ---------- Меню ----------
def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Записаться", callback_data="menu:book")
    kb.button(text="📋 Мои записи", callback_data="menu:my")
    kb.button(text="💰 Услуги и цены", callback_data="menu:services")
    kb.button(text="📍 Контакты", callback_data="menu:contacts")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


def reply_webapp_kb() -> "ReplyKeyboardMarkup | None":
    """Постоянная кнопка открытия Mini App (только если задан WEBAPP_URL)."""
    if not config.WEBAPP_URL:
        return None
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(
            text="🌐 Записаться в приложении",
            web_app=WebAppInfo(url=config.WEBAPP_URL),
        )]],
        resize_keyboard=True,
    )


def services_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in config.SERVICES:
        kb.button(text=f"{s.name} · {s.price} {config.CURRENCY}", callback_data=f"svc:{s.id}")
    kb.button(text="« Назад", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def masters_kb(service_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for m in config.masters_for(service_id):
        kb.button(text=f"{m.emoji} {m.name}", callback_data=f"mst:{m.id}")
    kb.button(text="🙋 Любой мастер", callback_data="mst:any")
    kb.button(text="« Назад", callback_data="menu:book")
    kb.adjust(2)
    return kb.as_markup()


# ---------- Дата/время ----------
def dates_kb(prefix: str = "date", back: str = "menu:book") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in work_dates():
        kb.button(text=f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month]}",
                  callback_data=f"{prefix}:{d.isoformat()}")
    kb.button(text="« Назад", callback_data=back)
    kb.adjust(1)
    return kb.as_markup()


def times_kb(date_str: str, service_id: str, master_id: "str | None",
             prefix: str = "time", back: str = "menu:book") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for label in free_slots(date_str, service_id, master_id):
        kb.button(text=label, callback_data=f"{prefix}:{label}")
    kb.button(text="« Назад", callback_data=back)
    kb.adjust(3)
    return kb.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="confirm:yes")
    kb.button(text="❌ Отменить", callback_data="menu:home")
    kb.adjust(2)
    return kb.as_markup()


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


def my_bookings_kb(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in rows:
        kb.button(text=f"🔁 Перенести №{b['id']}", callback_data=f"resch:{b['id']}")
        kb.button(text=f"❌ Отменить №{b['id']}", callback_data=f"ucancel:{b['id']}")
    kb.button(text="« Назад", callback_data="menu:home")
    kb.adjust(2)
    return kb.as_markup()


def rating_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n in range(1, 6):
        kb.button(text=f"{n}⭐", callback_data=f"rate:{booking_id}:{n}")
    kb.adjust(5)
    return kb.as_markup()


# ---------- Админ ----------
def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗓 Сегодня", callback_data="adm:today")
    kb.button(text="📋 Записи", callback_data="adm:list")
    kb.button(text="📊 Статистика", callback_data="adm:stats")
    kb.button(text="📣 Рассылка", callback_data="adm:cast")
    kb.adjust(2)
    return kb.as_markup()


def admin_bookings_kb(rows) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in rows:
        kb.button(text=f"❌ Отменить №{b['id']}", callback_data=f"acancel:{b['id']}")
    kb.button(text="« В меню", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def admin_today_kb(rows) -> InlineKeyboardMarkup:
    """Отметка посещаемости на сегодня: визит состоялся / неявка / отмена."""
    kb = InlineKeyboardBuilder()
    for b in rows:
        kb.button(text=f"✅ №{b['id']}", callback_data=f"acomplete:{b['id']}")
        kb.button(text=f"🚫 №{b['id']}", callback_data=f"anoshow:{b['id']}")
        kb.button(text=f"❌ №{b['id']}", callback_data=f"atcancel:{b['id']}")
    kb.button(text="« В меню", callback_data="adm:menu")
    kb.adjust(3)
    return kb.as_markup()
