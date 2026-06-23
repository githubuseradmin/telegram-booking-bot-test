"""Фоновые задачи: напоминания перед визитом и запрос оценки после (APScheduler)."""
import logging
from datetime import datetime, timedelta

from aiogram import Bot

import config
import db
import keyboards as kb
import texts
from config import service_by_id

log = logging.getLogger(__name__)


async def send_due_reminders(bot: Bot) -> None:
    """Напоминания клиентам, чьё время визита близко."""
    now = datetime.now()
    until = now + timedelta(hours=config.REMINDER_HOURS_BEFORE)
    rows = db.due_reminders(now.isoformat(timespec="minutes"),
                            until.isoformat(timespec="minutes"))
    for b in rows:
        svc = service_by_id(b["service_id"])
        name = svc.name if svc else b["service_id"]
        try:
            await bot.send_message(b["user_id"], texts.reminder(name, b["master_id"], b["slot"]))
        except Exception as e:
            log.warning("Напоминание №%s не доставлено: %s", b["id"], e)
        finally:
            db.mark_reminded(b["id"])


async def send_due_feedback(bot: Bot) -> None:
    """После визита (время прошло) — просим оценить. Только свежие визиты (до 2 дней)."""
    now = datetime.now()
    lower = (now - timedelta(days=2)).isoformat(timespec="minutes")
    rows = db.due_feedback(now.isoformat(timespec="minutes"))
    for b in rows:
        if b["slot"] < lower:               # слишком старое — не спамим
            db.mark_feedback_asked(b["id"])
            continue
        svc = service_by_id(b["service_id"])
        name = svc.name if svc else b["service_id"]
        try:
            await bot.send_message(
                b["user_id"], texts.feedback_request(name, b["slot"]),
                reply_markup=kb.rating_kb(b["id"]),
            )
        except Exception as e:
            log.warning("Запрос отзыва №%s не доставлен: %s", b["id"], e)
        finally:
            db.mark_feedback_asked(b["id"])
