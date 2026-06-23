"""
Чистая логика расписания (без зависимостей от Telegram) — поэтому легко
тестируется и переиспользуется (в т.ч. со стороны backend для Mini App).
"""
from datetime import datetime, date, time, timedelta

import config
import db


def grid_times(d: date) -> list[str]:
    """Сетка времени 'HH:MM' на дату, без уже прошедших (с запасом 30 минут)."""
    now = datetime.now()
    out, minutes, end = [], config.WORK_START_HOUR * 60, config.WORK_END_HOUR * 60
    while minutes < end:
        hh, mm = divmod(minutes, 60)
        if datetime.combine(d, time(hh, mm)) > now + timedelta(minutes=30):
            out.append(f"{hh:02d}:{mm:02d}")
        minutes += config.SLOT_MINUTES
    return out


def work_dates() -> list[date]:
    """Ближайшие рабочие даты (по WORK_DAYS), не больше BOOKING_DAYS_AHEAD."""
    result, d = [], date.today()
    for _ in range(config.BOOKING_DAYS_AHEAD * 3):
        if len(result) >= config.BOOKING_DAYS_AHEAD:
            break
        if d.weekday() in config.WORK_DAYS:
            result.append(d)
        d += timedelta(days=1)
    return result


def free_slots(date_str: str, service_id: str, master_id: "str | None" = None) -> list[str]:
    """Свободные слоты на дату для услуги (+ конкретного мастера или 'любой')."""
    d = date.fromisoformat(date_str)
    rows = db.active_bookings_on(date_str)              # (slot, master_id)
    capable_ids = [m.id for m in config.masters_for(service_id)]
    out = []
    for label in grid_times(d):
        iso = f"{date_str}T{label}"
        taken = [r["master_id"] for r in rows if r["slot"] == iso]
        if not config.ENABLE_MASTERS:
            free = len(taken) == 0                      # один поток
        elif master_id and master_id != "any":
            free = master_id not in taken               # конкретный мастер свободен
        else:
            busy = sum(1 for mid in taken if mid in capable_ids)
            free = busy < len(capable_ids)              # «любой»: есть свободный мастер
        if free:
            out.append(label)
    return out


def assign_master(date_str: str, label: str, service_id: str) -> "str | None":
    """Для режима 'любой мастер' — выбрать свободного мастера на слот."""
    iso = f"{date_str}T{label}"
    taken = {r["master_id"] for r in db.active_bookings_on(date_str) if r["slot"] == iso}
    for m in config.masters_for(service_id):
        if m.id not in taken:
            return m.id
    return None
