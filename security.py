"""
Проверка подлинности Telegram Mini App initData (HMAC-SHA256).

Нужна, ЕСЛИ Mini App обращается к вашему backend-API напрямую (там данные надо
проверять). В этом проекте запись приходит через Telegram.WebApp.sendData() →
сообщение web_app_data, которое Telegram доставляет от имени пользователя и уже
доверенно, поэтому здесь функция дана «про запас» и для документации.
"""
import hashlib
import hmac
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> "dict | None":
    """Вернёт распарсенные поля initData, если подпись верна, иначе None."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return parsed if hmac.compare_digest(calc_hash, received_hash) else None
