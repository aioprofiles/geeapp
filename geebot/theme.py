"""Semantic button roles -> Bot API button style. Styles confirmed in the Bot API types:
primary (blue), success (green), danger (red), link (borderless, callback buttons only), None (grey/default)."""
from .ui import btn

ROLES = {"primary": "primary", "success": "success", "danger": "danger", "link": "link", "muted": None}


def B(text, data=None, role: str = "muted", url=None, webapp=None, copy=None, icon=None):
    style = ROLES.get(role)
    if style == "link" and data is None:      # 'link' style is allowed for callback buttons only
        style = None
    return btn(text, data=data, url=url, webapp=webapp, copy=copy, style=style, icon=icon)


def row(*buttons):
    return [x for x in buttons if x]


def grid(buttons, cols: int = 2):
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]
