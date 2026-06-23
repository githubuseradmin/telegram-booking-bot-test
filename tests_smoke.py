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

try:
    db.DB_PATH.unlink(missing_ok=True)
except PermissionError:
    pass  # Windows иногда держит файл — для теста не критично
print("SMOKE OK: slots, master capacity, assignment, DB aggregates all pass")
