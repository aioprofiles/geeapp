"""Inline-keyboard helpers (no network deps)."""


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, data=None, url=None, webapp=None, style=None, copy=None):
    b = {"text": text}
    if data is not None:
        b["callback_data"] = data[:64]
    elif url:
        b["url"] = url
    elif webapp:
        b["web_app"] = {"url": webapp}
    elif copy:
        b["copy_text"] = {"text": copy}
    if style:  # Bot API 9.4 button colour; check docs for the accepted values
        b["style"] = style
    return b
