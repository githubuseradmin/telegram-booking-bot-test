"""Слой работы с базой (SQLite). Для небольшого бизнеса этого с запасом."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "bookings.db"

# Колонки, которые могли появиться позже — для мягкой миграции старой БД.
_EXTRA_COLUMNS = {
    "master_id": "TEXT",
    "rating": "INTEGER",
    "feedback": "TEXT",
    "feedback_asked": "INTEGER NOT NULL DEFAULT 0",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db():
    """Соединение, которое коммитит и ЗАКРЫВАЕТСЯ (чтобы не течь и не лочить файл)."""
    conn = _conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                client_name TEXT    NOT NULL,
                phone       TEXT    NOT NULL,
                service_id  TEXT    NOT NULL,
                master_id   TEXT,
                slot        TEXT    NOT NULL,   -- ISO 'YYYY-MM-DDTHH:MM' (начало визита)
                created_at  TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'active',  -- active | cancelled
                reminded    INTEGER NOT NULL DEFAULT 0,
                rating      INTEGER,
                feedback    TEXT,
                feedback_asked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Мягкая миграция: добиваем недостающие колонки в старой БД.
        existing = {r["name"] for r in c.execute("PRAGMA table_info(bookings)")}
        for col, decl in _EXTRA_COLUMNS.items():
            if col not in existing:
                c.execute(f"ALTER TABLE bookings ADD COLUMN {col} {decl}")

        # Защита от двойной брони на уровне БД (атомарно, без гонок):
        # частичные UNIQUE-индексы только по АКТИВНЫМ записям. Отмена/завершение
        # выводят запись из индекса и освобождают слот.
        #   * с мастерами   — уникальна пара (слот, мастер);
        #   * один поток     — уникален сам слот (master_id IS NULL).
        # NULL в SQLite считаются различными, поэтому два отдельных индекса.
        for ddl in (
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_active_slot_master "
            "ON bookings(slot, master_id) WHERE status='active' AND master_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_active_slot_single "
            "ON bookings(slot) WHERE status='active' AND master_id IS NULL",
        ):
            try:
                c.execute(ddl)
            except sqlite3.IntegrityError:
                # В старой БД уже есть дубли активных записей на один слот —
                # не валим запуск; индекс начнёт защищать после ручной чистки.
                pass


def add_booking(user_id, username, client_name, phone,
                service_id, master_id, slot_iso) -> "int | None":
    """Создать запись. Возвращает id или None, если слот только что заняли
    (конфликт ловится атомарно UNIQUE-индексом, без гонки 'проверил-вставил')."""
    try:
        with _db() as c:
            cur = c.execute(
                """INSERT INTO bookings
                   (user_id, username, client_name, phone, service_id, master_id,
                    slot, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, client_name, phone, service_id, master_id, slot_iso,
                 datetime.now().isoformat(timespec="seconds")),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def active_bookings_on(date_str: str) -> list[sqlite3.Row]:
    """Активные записи на дату 'YYYY-MM-DD' (slot, master_id) — для расчёта занятости."""
    with _db() as c:
        return c.execute(
            "SELECT slot, master_id FROM bookings "
            "WHERE status='active' AND slot LIKE ?",
            (f"{date_str}T%",),
        ).fetchall()


def get_booking(booking_id: int) -> "sqlite3.Row | None":
    with _db() as c:
        return c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()


def user_upcoming(user_id: int) -> list[sqlite3.Row]:
    now = datetime.now().isoformat(timespec="minutes")
    with _db() as c:
        return c.execute(
            """SELECT * FROM bookings
               WHERE user_id=? AND status='active' AND slot>=?
               ORDER BY slot""",
            (user_id, now),
        ).fetchall()


def all_upcoming() -> list[sqlite3.Row]:
    now = datetime.now().isoformat(timespec="minutes")
    with _db() as c:
        return c.execute(
            "SELECT * FROM bookings WHERE status='active' AND slot>=? ORDER BY slot",
            (now,),
        ).fetchall()


def cancel_booking(booking_id: int, user_id: "int | None" = None) -> bool:
    with _db() as c:
        if user_id is None:
            cur = c.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=? AND status='active'",
                (booking_id,),
            )
        else:
            cur = c.execute(
                "UPDATE bookings SET status='cancelled' "
                "WHERE id=? AND user_id=? AND status='active'",
                (booking_id, user_id),
            )
        return cur.rowcount > 0


def reschedule_booking(booking_id: int, user_id: int, new_slot: str) -> bool:
    """Перенос записи на новый слот (сбрасывает флаг напоминания).

    Возвращает False, если слот занят (UNIQUE-индекс) или запись недоступна."""
    try:
        with _db() as c:
            cur = c.execute(
                "UPDATE bookings SET slot=?, reminded=0 "
                "WHERE id=? AND user_id=? AND status='active'",
                (new_slot, booking_id, user_id),
            )
            return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def set_status(booking_id: int, new_status: str) -> bool:
    """Перевести АКТИВНУЮ запись в терминальный статус (completed/cancelled/no_show).

    Гард `status='active'` гарантирует корректность переходов на уровне SQL."""
    with _db() as c:
        cur = c.execute(
            "UPDATE bookings SET status=? WHERE id=? AND status='active'",
            (new_status, booking_id),
        )
        return cur.rowcount > 0


def complete_due(grace_minutes: int) -> int:
    """Авто-завершение: активные визиты, начавшиеся раньше (now - grace),
    переводятся в 'completed'. Возвращает число обновлённых записей."""
    from datetime import timedelta
    threshold = (datetime.now() - timedelta(minutes=grace_minutes)).isoformat(
        timespec="minutes"
    )
    with _db() as c:
        cur = c.execute(
            "UPDATE bookings SET status='completed' "
            "WHERE status='active' AND slot<=?",
            (threshold,),
        )
        return cur.rowcount


def active_on_day(date_str: str) -> list[sqlite3.Row]:
    """Все активные записи на дату 'YYYY-MM-DD' (прошедшие и будущие) — для админ-вида «сегодня»."""
    with _db() as c:
        return c.execute(
            "SELECT * FROM bookings WHERE status='active' AND slot LIKE ? ORDER BY slot",
            (f"{date_str}T%",),
        ).fetchall()


# --- Напоминания ---
def due_reminders(now_iso: str, until_iso: str) -> list[sqlite3.Row]:
    with _db() as c:
        return c.execute(
            """SELECT * FROM bookings
               WHERE status='active' AND reminded=0 AND slot>=? AND slot<=?""",
            (now_iso, until_iso),
        ).fetchall()


def mark_reminded(booking_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE bookings SET reminded=1 WHERE id=?", (booking_id,))


# --- Отзывы/оценки ---
def due_feedback() -> list[sqlite3.Row]:
    """Завершённые визиты (status='completed'), у которых ещё не спросили оценку.

    Отмены и неявки сюда не попадают — спрашиваем отзыв только о состоявшихся."""
    with _db() as c:
        return c.execute(
            "SELECT * FROM bookings WHERE status='completed' AND feedback_asked=0",
        ).fetchall()


def mark_feedback_asked(booking_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE bookings SET feedback_asked=1 WHERE id=?", (booking_id,))


def set_rating(booking_id: int, user_id: int, rating: int) -> bool:
    with _db() as c:
        cur = c.execute(
            "UPDATE bookings SET rating=? WHERE id=? AND user_id=?",
            (rating, booking_id, user_id),
        )
        return cur.rowcount > 0


def set_feedback_text(booking_id: int, user_id: int, text: str) -> None:
    with _db() as c:
        c.execute(
            "UPDATE bookings SET feedback=? WHERE id=? AND user_id=?",
            (text, booking_id, user_id),
        )


# --- Лояльность / рассылка / статистика ---
def completed_visits(user_id: int) -> int:
    """Сколько визитов клиент реально совершил (status='completed') — для лояльности."""
    with _db() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM bookings WHERE user_id=? AND status='completed'",
            (user_id,),
        ).fetchone()
    return row["n"]


def all_client_ids() -> list[int]:
    with _db() as c:
        rows = c.execute("SELECT DISTINCT user_id FROM bookings").fetchall()
    return [r["user_id"] for r in rows]


def count_active_between(start_iso: str, end_iso: str) -> int:
    with _db() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM bookings "
            "WHERE status='active' AND slot>=? AND slot<?",
            (start_iso, end_iso),
        ).fetchone()
    return row["n"]


def service_breakdown(start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    with _db() as c:
        return c.execute(
            "SELECT service_id, COUNT(*) n FROM bookings "
            "WHERE status='active' AND slot>=? AND slot<? "
            "GROUP BY service_id ORDER BY n DESC",
            (start_iso, end_iso),
        ).fetchall()


def avg_rating() -> "float | None":
    with _db() as c:
        row = c.execute(
            "SELECT AVG(rating) a, COUNT(rating) n FROM bookings WHERE rating IS NOT NULL"
        ).fetchone()
    return (row["a"], row["n"]) if row["n"] else None
