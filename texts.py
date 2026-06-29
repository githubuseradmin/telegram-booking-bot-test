"""Тексты сообщений (HTML). Вынесены отдельно, чтобы легко менять тон/язык."""
from datetime import datetime

import config

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def fmt_dt(slot_iso: str) -> str:
    """'2026-06-25T14:00' -> '25 июня (Чт) в 14:00'."""
    dt = datetime.fromisoformat(slot_iso)
    return f"{dt.day} {MONTHS[dt.month]} ({WEEKDAYS[dt.weekday()]}) в {dt:%H:%M}"


def _master_line(master_id: "str | None") -> str:
    m = config.master_by_id(master_id) if master_id else None
    return f"\n👩‍🔧 Мастер: <b>{m.emoji} {m.name}</b>" if m else ""


def greeting() -> str:
    return (
        f"👋 Здравствуйте! Это бот записи <b>{config.BUSINESS_NAME}</b>.\n\n"
        "Запишитесь онлайн за 30 секунд, посмотрите свои записи, цены и контакты.\n"
        "Выберите действие:"
    )


def webapp_hint() -> str:
    return "✨ Или нажмите кнопку внизу — запись в удобном мини-приложении 👇"


def booking_summary(service_name, master_id, slot_iso, name, phone) -> str:
    return (
        "<b>Проверьте запись:</b>\n\n"
        f"💇 Услуга: <b>{service_name}</b>"
        f"{_master_line(master_id)}\n"
        f"🗓 Время: <b>{fmt_dt(slot_iso)}</b>\n"
        f"👤 Имя: {name}\n"
        f"📞 Телефон: {phone}\n\n"
        "Всё верно?"
    )


def booking_confirmed(service_name, master_id, slot_iso, visit_no) -> str:
    bonus = ""
    if visit_no and config.LOYALTY_EVERY and visit_no % config.LOYALTY_EVERY == 0:
        bonus = "\n\n🎁 Это ваш юбилейный визит — вас ждёт приятный бонус!"
    elif visit_no:
        left = config.LOYALTY_EVERY - (visit_no % config.LOYALTY_EVERY)
        bonus = f"\n\n💎 Визит №{visit_no}. До бонуса осталось {left}."
    return (
        "✅ <b>Вы записаны!</b>\n\n"
        f"💇 {service_name}"
        f"{_master_line(master_id)}\n"
        f"🗓 {fmt_dt(slot_iso)}\n\n"
        f"📍 {config.BUSINESS_ADDRESS}\n"
        f"📞 {config.BUSINESS_PHONE}"
        f"{bonus}\n\n"
        f"Напомним за {config.REMINDER_HOURS_BEFORE} ч. Изменить — в «Мои записи»."
    )


def admin_new_booking(b) -> str:
    svc = config.service_by_id(b["service_id"])
    uname = f"@{b['username']}" if b["username"] else "—"
    return (
        "🔔 <b>Новая запись!</b>\n\n"
        f"💇 {svc.name if svc else b['service_id']}"
        f"{_master_line(b['master_id'])}\n"
        f"🗓 {fmt_dt(b['slot'])}\n"
        f"👤 {b['client_name']} ({uname})\n"
        f"📞 {b['phone']}"
    )


def admin_booking_cancelled(b) -> str:
    svc = config.service_by_id(b["service_id"])
    uname = f"@{b['username']}" if b["username"] else "—"
    return (
        "🚫 <b>Клиент отменил запись</b>\n\n"
        f"💇 {svc.name if svc else b['service_id']}"
        f"{_master_line(b['master_id'])}\n"
        f"🗓 {fmt_dt(b['slot'])}\n"
        f"👤 {b['client_name']} ({uname})\n"
        f"📞 {b['phone']}"
    )


def admin_booking_rescheduled(b, old_slot) -> str:
    svc = config.service_by_id(b["service_id"])
    uname = f"@{b['username']}" if b["username"] else "—"
    return (
        "🔁 <b>Клиент перенёс запись</b>\n\n"
        f"💇 {svc.name if svc else b['service_id']}"
        f"{_master_line(b['master_id'])}\n"
        f"🗓 {fmt_dt(old_slot)} → <b>{fmt_dt(b['slot'])}</b>\n"
        f"👤 {b['client_name']} ({uname})\n"
        f"📞 {b['phone']}"
    )


def reminder(service_name, master_id, slot_iso) -> str:
    return (
        "⏰ <b>Напоминание о записи</b>\n\n"
        f"💇 {service_name}{_master_line(master_id)}\n"
        f"🗓 Сегодня в {datetime.fromisoformat(slot_iso):%H:%M}\n\n"
        f"📍 {config.BUSINESS_ADDRESS}\nЖдём вас!"
    )


def feedback_request(service_name, slot_iso) -> str:
    return (
        "Спасибо, что были у нас! 🌸\n"
        f"Как прошла услуга «{service_name}» {fmt_dt(slot_iso)}?\n"
        "Оцените от 1 до 5:"
    )


def rating_thanks(rating: int) -> str:
    if rating >= 4:
        return "Спасибо за высокую оценку! ❤️ Будем рады видеть вас снова."
    return ("Спасибо за честность 🙏 Напишите, что можно улучшить — "
            "ваше сообщение увидит администратор.")


def services_list() -> str:
    lines = [f"<b>Услуги и цены — {config.BUSINESS_NAME}</b>\n"]
    for s in config.SERVICES:
        masters = ", ".join(m.name for m in config.masters_for(s.id)) if config.ENABLE_MASTERS else ""
        tail = f" · {masters}" if masters else ""
        lines.append(f"• {s.name} — <b>{s.price} {config.CURRENCY}</b> (~{s.duration} мин){tail}")
    return "\n".join(lines)


def contacts() -> str:
    return (f"<b>{config.BUSINESS_NAME}</b>\n\n"
            f"📍 {config.BUSINESS_ADDRESS}\n📞 {config.BUSINESS_PHONE}")
