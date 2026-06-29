"""
Бот онлайн-записи для бизнеса (салон/барбершоп/студия/кафе).
aiogram 3.x · SQLite · мастера · перенос · отзывы · лояльность · админка ·
автонапоминания · Telegram Mini App.

Демо-портфолио. Переставляется под любой бизнес через config.py.
Запуск: см. README.md · архитектура: см. ARCHITECTURE.md
"""
import asyncio
import json
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import db
import keyboards as kb
import lifecycle
import texts
from config import master_by_id, masters_for, service_by_id
from reminders import send_due_feedback, send_due_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
router = Router()


class Booking(StatesGroup):
    service = State()
    master = State()
    date = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()


class Reschedule(StatesGroup):
    date = State()
    time = State()


class Broadcast(StatesGroup):
    text = State()


class Feedback(StatesGroup):
    comment = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def _safe_edit(cb: CallbackQuery, text: str, markup=None) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


def _slot_master(master_choice) -> "str | None":
    """Мастер для расчёта слотов: 'any'/None -> None (любой)."""
    return None if master_choice in (None, "any") else master_choice


async def _notify_admins(bot, text: str) -> None:
    """Разослать уведомление всем администраторам (best-effort)."""
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logging.warning("Админу %s не доставлено: %s", admin_id, e)


def _change_locked(slot_iso: str) -> bool:
    """True, если до визита меньше CLIENT_CHANGE_CUTOFF_HOURS — самим менять нельзя."""
    from datetime import datetime, timedelta
    if config.CLIENT_CHANGE_CUTOFF_HOURS <= 0:
        return False
    try:
        slot_dt = datetime.fromisoformat(slot_iso)
    except ValueError:
        return False
    return slot_dt - datetime.now() < timedelta(hours=config.CLIENT_CHANGE_CUTOFF_HOURS)


async def _create_booking(bot, user, service_id, master_choice, date_str, label,
                          name, phone) -> "tuple[bool, str, object]":
    """Общая логика создания записи (из чата и из Mini App). Возвращает (ok, err, row)."""
    if service_by_id(service_id) is None:
        return False, "Услуга не найдена.", None
    if label not in kb.free_slots(date_str, service_id, _slot_master(master_choice)):
        return False, "Это время уже заняли — выберите другое.", None

    master_final = master_choice
    if master_choice in (None, "any"):
        master_final = (kb.assign_master(date_str, label, service_id)
                        if config.ENABLE_MASTERS else None)
        if config.ENABLE_MASTERS and not master_final:
            return False, "На это время нет свободного мастера.", None

    slot = f"{date_str}T{label}"
    booking_id = db.add_booking(user.id, user.username, name, phone,
                                service_id, master_final, slot)
    if booking_id is None:                      # слот атомарно заняли между проверкой и вставкой
        return False, "Это время только что заняли — выберите другое.", None
    row = db.get_booking(booking_id)
    await _notify_admins(bot, texts.admin_new_booking(row))
    return True, "", row


# ---------- Старт ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.greeting(), reply_markup=kb.main_menu())
    reply_kb = kb.reply_webapp_kb()
    if reply_kb:
        await message.answer(texts.webapp_hint(), reply_markup=reply_kb)


# ---------- Mini App: приём записи (только из reply-кнопки web_app) ----------
@router.message(F.web_app_data)
async def on_webapp_data(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    try:
        p = json.loads(message.web_app_data.data)
        service_id = str(p["service"])
        master_choice = p.get("master") or "any"
        date_str, label = str(p["date"]), str(p["time"])
        name = str(p.get("name", message.from_user.full_name))[:60]
        phone = str(p["phone"])[:30]
    except (json.JSONDecodeError, KeyError, TypeError):
        return await message.answer("Не удалось прочитать данные записи 😔",
                                    reply_markup=ReplyKeyboardRemove())

    ok, err, row = await _create_booking(bot, message.from_user, service_id,
                                         master_choice, date_str, label, name, phone)
    if not ok:
        return await message.answer(f"❌ {err}", reply_markup=ReplyKeyboardRemove())
    svc = service_by_id(service_id)
    visit_no = db.completed_visits(message.from_user.id) + 1
    await message.answer(
        texts.booking_confirmed(svc.name, row["master_id"], row["slot"], visit_no),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Меню:", reply_markup=kb.main_menu())


# ---------- Главное меню ----------
@router.callback_query(F.data == "menu:home")
async def go_home(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit(cb, texts.greeting(), kb.main_menu())
    await cb.answer()


@router.callback_query(F.data == "menu:services")
async def show_services(cb: CallbackQuery) -> None:
    await _safe_edit(cb, texts.services_list(), kb.main_menu())
    await cb.answer()


@router.callback_query(F.data == "menu:contacts")
async def show_contacts(cb: CallbackQuery) -> None:
    await _safe_edit(cb, texts.contacts(), kb.main_menu())
    await cb.answer()


# ---------- Сценарий записи (чат) ----------
@router.callback_query(F.data == "menu:book")
async def choose_service(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Booking.service)
    await _safe_edit(cb, "Выберите услугу:", kb.services_kb())
    await cb.answer()


@router.callback_query(Booking.service, F.data.startswith("svc:"))
async def chose_service(cb: CallbackQuery, state: FSMContext) -> None:
    service_id = cb.data.split(":", 1)[1]
    if service_by_id(service_id) is None:
        return await cb.answer("Услуга не найдена", show_alert=True)
    caps = masters_for(service_id) if config.ENABLE_MASTERS else []
    if config.ENABLE_MASTERS and len(caps) > 1:
        await state.update_data(service_id=service_id)
        await state.set_state(Booking.master)
        await _safe_edit(cb, "Выберите мастера:", kb.masters_kb(service_id))
    else:
        master = caps[0].id if caps else None
        await state.update_data(service_id=service_id, master=master)
        await state.set_state(Booking.date)
        await _safe_edit(cb, "Выберите день:", kb.dates_kb())
    await cb.answer()


@router.callback_query(Booking.master, F.data.startswith("mst:"))
async def chose_master(cb: CallbackQuery, state: FSMContext) -> None:
    choice = cb.data.split(":", 1)[1]          # id мастера или 'any'
    await state.update_data(master=choice)
    await state.set_state(Booking.date)
    await _safe_edit(cb, "Выберите день:", kb.dates_kb())
    await cb.answer()


@router.callback_query(Booking.date, F.data.startswith("date:"))
async def chose_date(cb: CallbackQuery, state: FSMContext) -> None:
    date_str = cb.data.split(":", 1)[1]
    data = await state.get_data()
    await state.update_data(date=date_str)
    await state.set_state(Booking.time)
    if not kb.free_slots(date_str, data["service_id"], _slot_master(data.get("master"))):
        return await _safe_edit(cb, "На этот день свободных окон нет 😔 "
                                    "Выберите другой день:", kb.dates_kb())
    await _safe_edit(cb, "Выберите время:",
                     kb.times_kb(date_str, data["service_id"], _slot_master(data.get("master"))))
    await cb.answer()


@router.callback_query(Booking.time, F.data.startswith("time:"))
async def chose_time(cb: CallbackQuery, state: FSMContext) -> None:
    label = cb.data.split(":", 1)[1]
    data = await state.get_data()
    await state.update_data(label=label, slot=f"{data['date']}T{label}")
    await state.set_state(Booking.name)
    await _safe_edit(cb, "Как вас зовут? (напишите имя сообщением)")
    await cb.answer()


@router.message(Booking.name, F.text)
async def ask_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip()[:60])
    await state.set_state(Booking.phone)
    await message.answer(
        "Оставьте номер телефона — кнопкой ниже или впишите вручную:",
        reply_markup=kb.phone_request_kb(),
    )


@router.message(Booking.phone)
async def show_confirm(message: Message, state: FSMContext) -> None:
    phone = (message.contact.phone_number if message.contact
             else (message.text or "").strip())
    if len("".join(ch for ch in phone if ch.isdigit())) < 7:
        return await message.answer("Похоже, номер неполный. Введите ещё раз:")
    await state.update_data(phone=phone[:30])
    data = await state.get_data()
    svc = service_by_id(data["service_id"])
    await state.set_state(Booking.confirm)
    await message.answer(
        texts.booking_summary(svc.name, _slot_master(data.get("master")),
                              data["slot"], data["name"], phone),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Подтверждаем запись?", reply_markup=kb.confirm_kb())


@router.callback_query(Booking.confirm, F.data == "confirm:yes")
async def save_booking(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    ok, err, row = await _create_booking(
        bot, cb.from_user, data["service_id"], data.get("master"),
        data["date"], data["label"], data["name"], data["phone"],
    )
    if not ok:
        await state.set_state(Booking.date)
        await _safe_edit(cb, f"{err}\nВыберите другой день:", kb.dates_kb())
        return await cb.answer(err, show_alert=True)
    svc = service_by_id(data["service_id"])
    visit_no = db.completed_visits(cb.from_user.id) + 1
    await state.clear()
    await _safe_edit(cb, texts.booking_confirmed(svc.name, row["master_id"],
                                                 row["slot"], visit_no), kb.main_menu())
    await cb.answer("Готово!")


# ---------- Мои записи / отмена / перенос ----------
@router.callback_query(F.data == "menu:my")
async def my_bookings(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = db.user_upcoming(cb.from_user.id)
    if not rows:
        await _safe_edit(cb, "У вас пока нет активных записей.", kb.main_menu())
        return await cb.answer()
    lines = ["<b>Ваши записи:</b>\n"]
    for b in rows:
        svc = service_by_id(b["service_id"])
        m = master_by_id(b["master_id"]) if b["master_id"] else None
        mtxt = f" · {m.name}" if m else ""
        lines.append(f"№{b['id']} · {svc.name if svc else b['service_id']}{mtxt} — "
                     f"{texts.fmt_dt(b['slot'])}")
    await _safe_edit(cb, "\n".join(lines), kb.my_bookings_kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("ucancel:"))
async def user_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(cb.data.split(":", 1)[1])
    row = db.get_booking(booking_id)
    if row and row["user_id"] == cb.from_user.id and _change_locked(row["slot"]):
        return await cb.answer(
            f"До визита менее {config.CLIENT_CHANGE_CUTOFF_HOURS} ч — "
            f"позвоните нам: {config.BUSINESS_PHONE}", show_alert=True)
    ok = db.cancel_booking(booking_id, user_id=cb.from_user.id)
    if ok and row:                              # сообщаем персоналу об отмене
        await _notify_admins(cb.bot, texts.admin_booking_cancelled(row))
    await cb.answer("Запись отменена" if ok else "Не получилось", show_alert=not ok)
    await my_bookings(cb, state)


@router.callback_query(F.data.startswith("resch:"))
async def reschedule_start(cb: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(cb.data.split(":", 1)[1])
    b = db.get_booking(booking_id)
    if not b or b["user_id"] != cb.from_user.id or b["status"] != lifecycle.ACTIVE:
        return await cb.answer("Запись недоступна", show_alert=True)
    if _change_locked(b["slot"]):
        return await cb.answer(
            f"До визита менее {config.CLIENT_CHANGE_CUTOFF_HOURS} ч — "
            f"позвоните нам: {config.BUSINESS_PHONE}", show_alert=True)
    await state.set_state(Reschedule.date)
    await state.update_data(rid=booking_id, service_id=b["service_id"],
                            master=b["master_id"], old_slot=b["slot"])
    await _safe_edit(cb, "Новый день:", kb.dates_kb(back="menu:my"))
    await cb.answer()


@router.callback_query(Reschedule.date, F.data.startswith("date:"))
async def reschedule_date(cb: CallbackQuery, state: FSMContext) -> None:
    date_str = cb.data.split(":", 1)[1]
    data = await state.get_data()
    await state.update_data(date=date_str)
    await state.set_state(Reschedule.time)
    if not kb.free_slots(date_str, data["service_id"], _slot_master(data.get("master"))):
        return await _safe_edit(cb, "Свободных окон нет, выберите другой день:",
                                kb.dates_kb(back="menu:my"))
    await _safe_edit(cb, "Новое время:",
                     kb.times_kb(date_str, data["service_id"],
                                 _slot_master(data.get("master")), back="menu:my"))
    await cb.answer()


@router.callback_query(Reschedule.time, F.data.startswith("time:"))
async def reschedule_time(cb: CallbackQuery, state: FSMContext) -> None:
    label = cb.data.split(":", 1)[1]
    data = await state.get_data()
    new_slot = f"{data['date']}T{label}"
    if label not in kb.free_slots(data["date"], data["service_id"],
                                  _slot_master(data.get("master"))):
        return await cb.answer("Время уже заняли", show_alert=True)
    ok = db.reschedule_booking(data["rid"], cb.from_user.id, new_slot)
    if not ok:                                  # слот атомарно заняли в момент переноса
        return await cb.answer("Это время только что заняли — выберите другое",
                               show_alert=True)
    await state.clear()
    row = db.get_booking(data["rid"])
    if row and data.get("old_slot"):            # сообщаем персоналу о переносе
        await _notify_admins(cb.bot, texts.admin_booking_rescheduled(row, data["old_slot"]))
    await _safe_edit(cb, f"🔁 Запись перенесена на {texts.fmt_dt(new_slot)}.",
                     kb.main_menu())
    await cb.answer("Перенесено")


# ---------- Оценка после визита ----------
@router.callback_query(F.data.startswith("rate:"))
async def on_rate(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    _, bid, n = cb.data.split(":")
    booking_id, rating = int(bid), int(n)
    db.set_rating(booking_id, cb.from_user.id, rating)
    await _safe_edit(cb, texts.rating_thanks(rating))
    await cb.answer("Спасибо за оценку!")
    if rating <= 3:                              # просим комментарий и зовём админа
        await state.set_state(Feedback.comment)
        await state.update_data(fid=booking_id)
        await cb.message.answer("Напишите, что можно улучшить:")


@router.message(Feedback.comment, F.text)
async def on_feedback_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    db.set_feedback_text(data["fid"], message.from_user.id, message.text.strip()[:500])
    await state.clear()
    await message.answer("Спасибо! Мы обязательно учтём. 🙏")
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📝 Отзыв (запись №{data['fid']}): {message.text.strip()[:500]}")
        except Exception:
            pass


# ---------- Админка ----------
@router.message(Command("admin"))
async def admin_entry(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def admin_menu(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await _safe_edit(cb, "⚙️ <b>Панель администратора</b>", kb.admin_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:list")
async def admin_list(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    rows = db.all_upcoming()
    if not rows:
        await _safe_edit(cb, "Предстоящих записей нет.", kb.admin_menu_kb())
        return await cb.answer()
    lines = ["<b>Предстоящие записи:</b>\n"]
    for b in rows:
        svc = service_by_id(b["service_id"])
        m = master_by_id(b["master_id"]) if b["master_id"] else None
        uname = f"@{b['username']}" if b["username"] else "—"
        lines.append(f"№{b['id']} · {texts.fmt_dt(b['slot'])} · "
                     f"{svc.name if svc else b['service_id']}"
                     f"{(' · ' + m.name) if m else ''} · "
                     f"{b['client_name']} {uname} · {b['phone']}")
    await _safe_edit(cb, "\n".join(lines), kb.admin_bookings_kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("acancel:"))
async def admin_cancel(cb: CallbackQuery, bot: Bot) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    booking_id = int(cb.data.split(":", 1)[1])
    row = db.get_booking(booking_id)
    ok = db.cancel_booking(booking_id)
    await cb.answer("Отменено" if ok else "Уже неактивно")
    if ok and row:
        svc = service_by_id(row["service_id"])
        try:
            await bot.send_message(
                row["user_id"],
                f"❗️Ваша запись ({svc.name if svc else ''} — "
                f"{texts.fmt_dt(row['slot'])}) отменена администратором. "
                f"Свяжитесь с нами: {config.BUSINESS_PHONE}")
        except Exception:
            pass
    await admin_list(cb)


@router.callback_query(F.data == "adm:today")
async def admin_today(cb: CallbackQuery) -> None:
    """Записи на сегодня с отметкой посещаемости (визит / неявка / отмена)."""
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    from datetime import date
    db.complete_due(config.ATTENDANCE_GRACE_MINUTES)
    rows = db.active_on_day(date.today().isoformat())
    if not rows:
        await _safe_edit(cb, "На сегодня активных записей нет.", kb.admin_menu_kb())
        return await cb.answer()
    lines = ["<b>Записи на сегодня</b>",
             "Отметьте: ✅ пришёл · 🚫 неявка · ❌ отмена\n"]
    for b in rows:
        svc = service_by_id(b["service_id"])
        m = master_by_id(b["master_id"]) if b["master_id"] else None
        uname = f"@{b['username']}" if b["username"] else "—"
        lines.append(f"№{b['id']} · {texts.fmt_dt(b['slot'])} · "
                     f"{svc.name if svc else b['service_id']}"
                     f"{(' · ' + m.name) if m else ''} · "
                     f"{b['client_name']} {uname} · {b['phone']}")
    await _safe_edit(cb, "\n".join(lines), kb.admin_today_kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("acomplete:"))
async def admin_complete(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    ok = db.set_status(int(cb.data.split(":", 1)[1]), lifecycle.COMPLETED)
    await cb.answer("Визит отмечен как состоявшийся ✅" if ok else "Уже неактивно")
    await admin_today(cb)


@router.callback_query(F.data.startswith("anoshow:"))
async def admin_no_show(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    ok = db.set_status(int(cb.data.split(":", 1)[1]), lifecycle.NO_SHOW)
    await cb.answer("Отмечено как неявка 🚫" if ok else "Уже неактивно")
    await admin_today(cb)


@router.callback_query(F.data.startswith("atcancel:"))
async def admin_today_cancel(cb: CallbackQuery, bot: Bot) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    booking_id = int(cb.data.split(":", 1)[1])
    row = db.get_booking(booking_id)
    ok = db.cancel_booking(booking_id)
    await cb.answer("Отменено" if ok else "Уже неактивно")
    if ok and row:
        svc = service_by_id(row["service_id"])
        try:
            await bot.send_message(
                row["user_id"],
                f"❗️Ваша запись ({svc.name if svc else ''} — "
                f"{texts.fmt_dt(row['slot'])}) отменена администратором. "
                f"Свяжитесь с нами: {config.BUSINESS_PHONE}")
        except Exception:
            pass
    await admin_today(cb)


@router.callback_query(F.data == "adm:stats")
async def admin_stats(cb: CallbackQuery) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    from datetime import datetime, timedelta
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    iso = lambda d: d.isoformat(timespec="minutes")
    today = db.count_active_between(iso(day_start), iso(day_start + timedelta(days=1)))
    week = db.count_active_between(iso(now), iso(now + timedelta(days=7)))
    breakdown = db.service_breakdown(iso(now), iso(now + timedelta(days=7)))
    revenue = 0
    top = "—"
    for i, b in enumerate(breakdown):
        svc = service_by_id(b["service_id"])
        if svc:
            revenue += svc.price * b["n"]
            if i == 0:
                top = f"{svc.name} ({b['n']})"
    ar = db.avg_rating()
    rating_line = f"{ar[0]:.1f} ⭐ ({ar[1]} оценок)" if ar else "пока нет оценок"
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Записей сегодня: <b>{today}</b>\n"
        f"Записей на 7 дней: <b>{week}</b>\n"
        f"Прогноз выручки (7 дн.): <b>{revenue} {config.CURRENCY}</b>\n"
        f"Популярная услуга: <b>{top}</b>\n"
        f"Средняя оценка: <b>{rating_line}</b>"
    )
    await _safe_edit(cb, text, kb.admin_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:cast")
async def admin_broadcast_start(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    await state.set_state(Broadcast.text)
    await _safe_edit(cb, "📣 Пришлите текст рассылки одним сообщением "
                         "(он уйдёт всем клиентам). /cancel — отмена.")
    await cb.answer()


@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=kb.main_menu())


@router.message(Broadcast.text, F.text)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return await state.clear()
    await state.clear()
    text = message.text
    sent = failed = 0
    for uid in db.all_client_ids():
        try:
            await bot.send_message(uid, f"📣 {config.BUSINESS_NAME}\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)               # бережём лимиты Telegram
    await message.answer(f"Готово. Доставлено: {sent}, не доставлено: {failed}.",
                         reply_markup=kb.admin_menu_kb())


# ---------- Запуск ----------
async def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "❌ Не задан BOT_TOKEN. Скопируйте .env.example в .env, получите токен "
            "у @BotFather и впишите его."
        )
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(send_due_reminders, "interval", minutes=5, args=[bot])
    scheduler.add_job(send_due_feedback, "interval", minutes=30, args=[bot])
    scheduler.start()

    logging.info("Бот запущен. Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        print(e if str(e) else "Остановлено.")
