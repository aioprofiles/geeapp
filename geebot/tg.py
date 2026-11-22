"""Thin async Bot API client. Raw HTTP on purpose: Bot API 10.x methods (sendWidget,
answerGuestQuery, sendRichMessage ...) may not be in your Telegram library yet."""
import json
import logging

import httpx

from . import rich as _rich
from .ui import btn, kb  # noqa: F401  (re-exported)

log = logging.getLogger("tg")


class TgError(Exception):
    def __init__(self, method: str, code: int | None, desc: str | None):
        super().__init__(f"{method}: {code} {desc}")
        self.method, self.code, self.desc = method, code, desc or ""


class Tg:
    def __init__(self, token: str, test: bool = False, http: httpx.AsyncClient | None = None):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}" + ("/test" if test else "")
        self.file_base = f"https://api.telegram.org/file/bot{token}" + ("/test" if test else "")
        self.http = http or httpx.AsyncClient(timeout=70)

    async def call(self, method: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        r = await self.http.post(f"{self.base}/{method}", json=params)
        d = r.json()
        if not d.get("ok"):
            raise TgError(method, d.get("error_code"), d.get("description"))
        return d["result"]

    async def try_call(self, method: str, **params):
        try:
            return await self.call(method, **params)
        except TgError as e:
            log.warning("%s", e)
        except httpx.HTTPError as e:
            log.warning("%s: %s", method, e)
        return None

    async def upload(self, method: str, field: str, filename: str, data: bytes, ctype: str, **params):
        form = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in params.items() if v is not None}
        r = await self.http.post(f"{self.base}/{method}", data=form, files={field: (filename, data, ctype)})
        d = r.json()
        if not d.get("ok"):
            raise TgError(method, d.get("error_code"), d.get("description"))
        return d["result"]

    # ---- messages ---------------------------------------------------------
    async def send(self, chat_id, text, rows=None, **kw):
        return await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                               reply_markup=kb(rows) if rows else None,
                               link_preview_options={"is_disabled": True}, **kw)

    async def send_rich(self, chat_id, md: str, html: str, rows=None, **kw):
        """Rich message (10.1+). Falls back to a normal HTML message if the rich call is refused,
        so a wrong parameter shape never leaves the user without an answer."""
        try:
            return await self.call("sendRichMessage", chat_id=chat_id, rich_message={"markdown": md},
                                   reply_markup=kb(rows) if rows else None, **kw)
        except (TgError, httpx.HTTPError) as e:
            log.info("rich fallback: %s", e)
            return await self.send(chat_id, html, rows, **kw)

    async def rich(self, chat_id, html: str, rows=None, **kw):
        """Native rich message (HTML flavour: tables, <details>, headings). Falls back to a readable plain message."""
        try:
            return await self.call("sendRichMessage", chat_id=chat_id, rich_message={"html": html},
                                   reply_markup=kb(rows) if rows else None, **kw)
        except (TgError, httpx.HTTPError) as e:
            log.info("rich fallback: %s", e)
            return await self.call("sendMessage", chat_id=chat_id, text=_rich.to_plain(html)[:4000],
                                   reply_markup=kb(rows) if rows else None, **kw)

    async def edit_rich(self, chat_id, message_id, html: str, rows=None):
        """editMessageText with rich_message (not in the official method docs yet -> verified fallback to plain text)."""
        r = await self.try_call("editMessageText", chat_id=chat_id, message_id=message_id,
                                rich_message={"html": html}, reply_markup=kb(rows) if rows else None)
        if r is None:
            r = await self.try_call("editMessageText", chat_id=chat_id, message_id=message_id,
                                    text=_rich.to_plain(html)[:4000], reply_markup=kb(rows) if rows else None)
        return r

    async def set_commands(self, commands: list[tuple[str, str]], language_code: str | None = None):
        return await self.try_call("setMyCommands", commands=[{"command": c, "description": d[:256]} for c, d in commands],
                                   language_code=language_code)

    async def invoice_stars(self, chat_id, title: str, description: str, payload: str, stars: int, **kw):
        """Telegram Stars invoice: currency XTR, no provider token, exactly one price item, whole Stars."""
        return await self.call("sendInvoice", chat_id=chat_id, title=title[:32], description=description[:255],
                               payload=payload[:128], currency="XTR", prices=[{"label": title[:32], "amount": int(stars)}], **kw)

    async def precheckout(self, query_id: str, ok: bool, error: str | None = None):
        return await self.try_call("answerPreCheckoutQuery", pre_checkout_query_id=query_id, ok=ok,
                                   error_message=None if ok else (error or "Payment refused")[:200])

    async def refund_stars(self, user_id: int, charge_id: str):
        return await self.try_call("refundStarPayment", user_id=user_id, telegram_payment_charge_id=charge_id)

    async def edit(self, chat_id, message_id, text, rows=None):
        return await self.try_call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                                   parse_mode="HTML", reply_markup=kb(rows) if rows else None,
                                   link_preview_options={"is_disabled": True})

    async def edit_kb(self, chat_id, message_id, rows):
        return await self.try_call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                                   reply_markup=kb(rows))

    async def answer_cb(self, cb_id, text=None, alert=False):
        return await self.try_call("answerCallbackQuery", callback_query_id=cb_id, text=text, show_alert=alert)

    async def poll_quiz(self, chat_id, question, options, correct: int, **kw):
        # 9.6: correct_option_ids replaces correct_option_id
        return await self.call("sendPoll", chat_id=chat_id, question=question[:300],
                               options=[{"text": o[:100]} for o in options], type="quiz",
                               correct_option_ids=[correct], is_anonymous=False, **kw)

    async def send_audio_bytes(self, chat_id, data: bytes, filename: str, title="", performer="", caption=None, **kw):
        return await self.upload("sendAudio", "audio", filename, data, "audio/mpeg", chat_id=chat_id,
                                 title=title, performer=performer, caption=caption, parse_mode="HTML", **kw)

    async def send_doc_bytes(self, chat_id, data: bytes, filename: str, caption=None):
        return await self.upload("sendDocument", "document", filename, data, "application/octet-stream",
                                 chat_id=chat_id, caption=caption, parse_mode="HTML")

    async def send_video_bytes(self, chat_id, data: bytes, filename: str, caption=None):
        return await self.upload("sendVideo", "video", filename, data, "video/mp4", chat_id=chat_id,
                                 caption=caption, parse_mode="HTML", supports_streaming=True)

    # ---- widgets (Bot API 10.4) ------------------------------------------
    async def widget(self, chat_id, html: str, caption: str, chat_data=None, public_data=None, rows=None,
                     width=0, height=0, allow_queries=True):
        return await self.call("sendWidget", chat_id=chat_id, html=html, caption=caption,
                               chat_data=chat_data, public_data=public_data, allow_queries=allow_queries,
                               width=width or None, height=height or None,
                               reply_markup=kb(rows) if rows else None)

    async def answer_widget(self, query_id, data: str | None = None):
        return await self.try_call("answerWidgetQuery", widget_query_id=query_id, data=data)

    async def edit_widget(self, chat_id, message_id, chat_data=None, public_data=None):
        return await self.try_call("editMessageWidgetData", chat_id=chat_id, message_id=message_id,
                                   chat_data=chat_data, public_data=public_data)

    # ---- guest mode (10.0) -----------------------------------------------
    async def answer_guest(self, guest_query_id, text_html: str, title="Reply", rows=None):
        result = {"type": "article", "id": "1", "title": title,
                  "input_message_content": {"message_text": text_html, "parse_mode": "HTML"}}
        if rows:
            result["reply_markup"] = kb(rows)
        return await self.try_call("answerGuestQuery", guest_query_id=guest_query_id, result=result)

    # ---- files -------------------------------------------------------------
    async def file_url(self, file_id: str) -> str | None:
        f = await self.try_call("getFile", file_id=file_id)
        return f"{self.file_base}/{f['file_path']}" if f and f.get("file_path") else None
