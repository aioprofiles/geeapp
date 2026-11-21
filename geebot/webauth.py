"""Mini App initData validation (HMAC-SHA256 per Telegram docs) - stdlib only."""
import hashlib
import hmac
import json
import time
import urllib.parse


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    got = parsed.pop("hash", None)
    if not got:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        return None
    if max_age and time.time() - int(parsed.get("auth_date", "0") or 0) > max_age:
        return None
    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except ValueError:
            return None
    return parsed


def sign_for_test(fields: dict, bot_token: str) -> str:
    """Builds a valid initData string (used by tests)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**fields, "hash": h})
