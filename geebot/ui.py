"""Inline-keyboard helpers (no network deps)."""


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, data=None, url=None, webapp=None, style=None, copy=None, icon=None):
    b = {"text": text}
    if data is not None:
        b["callback_data"] = data[:64]
    elif url:
        b["url"] = url
    elif webapp:
        b["web_app"] = {"url": webapp}
    elif copy:
        b["copy_text"] = {"text": copy}
    if style:  # primary | success | danger | link(callback only)
        b["style"] = style
    if icon:  # custom emoji icon id (needs the bot owner to have Telegram Premium)
        b["icon_custom_emoji_id"] = icon
    return b
