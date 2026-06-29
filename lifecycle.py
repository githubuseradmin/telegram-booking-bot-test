"""Жизненный цикл записи — единый источник правды о статусах и переходах.

Раньше статусов было два (active / cancelled), а «завершён» выводился из
времени. Теперь это явная маленькая state-machine: запись активна, затем
переходит в одно из терминальных состояний. Никаких зависимостей — модуль
переиспользуется и ботом, и БД-слоем, и тестами.

    active ──> completed   (визит состоялся; авто- или вручную админом)
           ──> cancelled   (отменена клиентом или админом)
           ──> no_show     (клиент не пришёл; ставит админ)
"""

ACTIVE = "active"
COMPLETED = "completed"
CANCELLED = "cancelled"
NO_SHOW = "no_show"

ALL = frozenset({ACTIVE, COMPLETED, CANCELLED, NO_SHOW})
TERMINAL = frozenset({COMPLETED, CANCELLED, NO_SHOW})

# Разрешённые переходы. Из терминальных состояний переходов нет.
_ALLOWED = {ACTIVE: frozenset({COMPLETED, CANCELLED, NO_SHOW})}

LABELS = {
    ACTIVE: "активна",
    COMPLETED: "завершена",
    CANCELLED: "отменена",
    NO_SHOW: "неявка",
}
EMOJI = {ACTIVE: "🟢", COMPLETED: "✅", CANCELLED: "❌", NO_SHOW: "🚫"}


def can_transition(frm: str, to: str) -> bool:
    """True, если переход frm -> to допустим."""
    return to in _ALLOWED.get(frm, frozenset())


def is_terminal(status: str) -> bool:
    return status in TERMINAL


def label(status: str) -> str:
    return LABELS.get(status, status)


def badge(status: str) -> str:
    """'✅ завершена' — для списков/уведомлений."""
    return f"{EMOJI.get(status, '•')} {label(status)}"
