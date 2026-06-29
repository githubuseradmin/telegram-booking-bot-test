"""
Смоук-тест чистой логики (без Telegram): расписание, мастера, занятость, БД.
Запуск: python tests_smoke.py   (использует временную БД, ничего не трогает).
"""
import tempfile
from pathlib import Path

import db

# Подменяем путь к БД на временный — не трогаем рабочую.
db.DB_PATH = Path(tempfile.gettempdir()) / "test_bookings.db"
if db.DB_PATH.exists():
    db.DB_PATH.unlink()
db.init_db()

import config  # noqa: E402
import slots    # noqa: E402

d = slots.work_dates()[0]
ds = d.isoformat()

# Услуга haircut_w выполняется двумя мастерами (anna, lena) -> ёмкость 2.
fs = slots.free_slots(ds, "haircut_w", None)
assert fs, "должны быть свободные слоты"
label = fs[0]

db.add_booking(1, "u1", "Аня", "+375291112233", "haircut_w", "anna", f"{ds}T{label}")
assert label in slots.free_slots(ds, "haircut_w", None), "ёмкость 2: 'любой' ещё свободен"
assert label not in slots.free_slots(ds, "haircut_w", "anna"), "anna занята"
assert label in slots.free_slots(ds, "haircut_w", "lena"), "lena свободна"
assert slots.assign_master(ds, label, "haircut_w") == "lena", "должны назначить lena"

db.add_booking(2, "u2", "Боб", "+375291112244", "haircut_w", "lena", f"{ds}T{label}")
assert label not in slots.free_slots(ds, "haircut_w", None), "оба мастера заняты"
assert slots.assign_master(ds, label, "haircut_w") is None, "свободных мастеров нет"

# Услуга color -> один мастер (anna).
l2 = slots.free_slots(ds, "color", "anna")[0]
db.add_booking(3, "u3", "Вика", "+375291112255", "color", "anna", f"{ds}T{l2}")
assert l2 not in slots.free_slots(ds, "color", "anna"), "anna занята на color"

# БД-агрегаты
assert db.count_active_between(f"{ds}T00:00", f"{ds}T23:59") >= 3
assert any(r["service_id"] == "haircut_w" for r in
           db.service_breakdown(f"{ds}T00:00", f"{ds}T23:59"))
assert db.all_client_ids(), "должны быть клиенты"

# --- Защита от двойной брони (атомарно, через UNIQUE-индекс) ---
# Берём ДАЛЬНЮЮ рабочую дату — у неё полная сетка слотов независимо от времени суток.
import lifecycle  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

ds2 = slots.work_dates()[-1].isoformat()
free_anna = slots.free_slots(ds2, "haircut_w", "anna")
assert len(free_anna) >= 2, "на дальней дате у anna есть свободные слоты"
slot_a, slot_b = free_anna[0], free_anna[1]

bid = db.add_booking(10, "ux", "Икс", "+375290000010", "haircut_w", "anna", f"{ds2}T{slot_a}")
assert bid is not None, "первая бронь проходит"
dup = db.add_booking(11, "uy", "Игрек", "+375290000011", "haircut_w", "anna", f"{ds2}T{slot_a}")
assert dup is None, "двойная бронь того же мастера на тот же слот отклоняется"
other = db.add_booking(12, "uz", "Зет", "+375290000012", "haircut_w", "lena", f"{ds2}T{slot_a}")
assert other is not None, "другой мастер на тот же слот — можно (ёмкость)"

# --- Перенос на занятый слот отклоняется ---
mover = db.add_booking(13, "um", "Мовер", "+375290000013", "haircut_w", "anna", f"{ds2}T{slot_b}")
assert mover is not None
assert db.reschedule_booking(mover, 13, f"{ds2}T{slot_a}") is False, "перенос на занятый слот anna отклоняется"

# --- Жизненный цикл: переходы ---
assert lifecycle.can_transition(lifecycle.ACTIVE, lifecycle.COMPLETED)
assert not lifecycle.can_transition(lifecycle.COMPLETED, lifecycle.ACTIVE)
assert lifecycle.is_terminal(lifecycle.NO_SHOW)
assert db.set_status(mover, lifecycle.NO_SHOW) is True, "active -> no_show"
assert db.set_status(mover, lifecycle.COMPLETED) is False, "из терминального состояния перехода нет"

# --- Авто-завершение прошедших визитов + счётчик лояльности + отзывы ---
past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
pid = db.add_booking(20, "uc", "Клиент", "+375290000020", "color", "anna", past)
assert pid is not None
assert db.completed_visits(20) == 0, "пока визит не завершён — счётчик 0"
assert db.complete_due(config.ATTENDANCE_GRACE_MINUTES) >= 1, "прошедшая запись авто-завершилась"
assert db.completed_visits(20) == 1, "после завершения визит засчитан"
assert any(r["id"] == pid for r in db.due_feedback()), "отзыв спрашиваем только о завершённом визите"

try:
    db.DB_PATH.unlink(missing_ok=True)
except PermissionError:
    pass  # Windows иногда держит файл — для теста не критично
print("SMOKE OK: slots, capacity, assignment, DB aggregates, "
      "double-booking guard, lifecycle, auto-complete all pass")
