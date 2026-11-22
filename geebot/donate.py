"""Telegram Stars: donations from 1 star (preset buttons + any custom amount), supporter tiers, idempotent recording,
pre-checkout validation, owner refunds. Stars are for digital goods/services, so donations are framed as supporter perks."""
import time

from . import rich as R
from .app import Ctx
from .theme import B, grid
from .tg import TgError

TIERS = [(500, "🏆 Champion"), (50, "💎 Patron"), (1, "💖 Supporter")]
PRESETS = [1, 5, 10, 50, 100, 500]


def total_stars(db, uid: int) -> int:
    return int(db.one("SELECT COALESCE(SUM(stars),0) n FROM payments WHERE user_id=? AND kind='donation' AND refunded=0", uid)["n"])


def tier_name(total: int) -> str:
    return next((n for m, n in TIERS if total >= m), "—")


def home(ctx: Ctx, uid: int) -> tuple[str, list]:
    t = total_stars(ctx.db, uid)
    html = R.doc(R.heading("💖 Support ගී", 3),
                 R.para("Any amount helps keep the bot running — from 1 ⭐ upwards. Supporters get a badge and a place on the wall."),
                 R.table([(n, f"from {m} ⭐") for m, n in reversed(TIERS)], header=("Tier", "Total donated")),
                 R.footer(f"Your total: {t} ⭐ · {tier_name(t)}"))
    rows = grid([B(f"⭐ {n}", f"dn:{n}", "success") for n in PRESETS], 3)
    rows += [[B("✍ Custom amount", "dn:custom", "primary")], [B("🏅 Supporters wall", "dn:wall")], [B("‹ Back", "n:home")]]
    return html, rows


def wall(ctx: Ctx) -> tuple[str, list]:
    rows = ctx.db.q("SELECT p.user_id, SUM(p.stars) s, MAX(u.first_name) fn, MAX(u.privacy) pv FROM payments p "
                    "JOIN users u ON u.id=p.user_id WHERE p.kind='donation' AND p.refunded=0 "
                    "GROUP BY p.user_id ORDER BY s DESC LIMIT 10")
    body = [(i, "Anonymous" if r["pv"] else (r["fn"] or "Supporter"), f"{r['s']} ⭐") for i, r in enumerate(rows, 1)]
    html = R.doc(R.heading("🏅 Supporters wall", 3),
                 R.table(body, header=("#", "Name", "Stars")) if body else R.para("Be the first! 💖"))
    return html, [[B("💖 Donate", "dn:home", "success"), B("‹ Back", "n:home")]]


async def send_invoice(ctx: Ctx, chat: int, uid: int, stars: int):
    if not 1 <= stars <= ctx.cfg.donate_max_stars:
        return await ctx.tg.send(chat, f"Please choose between 1 and {ctx.cfg.donate_max_stars} ⭐")
    try:
        await ctx.tg.invoice_stars(chat, "Support ගී", f"Thank you for supporting the bot with {stars} ⭐", f"don:{stars}", stars)
    except TgError as e:  # e.g. Telegram refuses an amount above its per-invoice limit
        await ctx.tg.send(chat, f"Telegram could not create that invoice ({R.esc(e.desc)}). Try a smaller amount.")


async def cb(ctx: Ctx, c: dict, arg: str):
    uid, m = c["from"]["id"], c["message"]
    chat, mid = m["chat"]["id"], m["message_id"]
    await ctx.tg.answer_cb(c["id"])
    if arg == "home":
        html, rows = home(ctx, uid)
        return await ctx.tg.edit_rich(chat, mid, html, rows)
    if arg == "wall":
        html, rows = wall(ctx)
        return await ctx.tg.edit_rich(chat, mid, html, rows)
    if arg == "custom":
        ctx.db.kv_set(f"flow:{uid}", {"k": "don_amount"})
        return await ctx.tg.send(chat, f"How many ⭐? Send a whole number (1 – {ctx.cfg.donate_max_stars}).")
    if arg.isdigit():
        await send_invoice(ctx, chat, uid, int(arg))


async def amount_flow(ctx: Ctx, msg: dict, text: str) -> bool:
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    s = text.strip().replace(",", "")
    ctx.db.kv_del(f"flow:{uid}")
    if not s.isdigit():
        await ctx.tg.send(chat, "That doesn't look like a number. Use /donate to try again.")
        return True
    await send_invoice(ctx, chat, uid, int(s))
    return True


async def cmd_donate(ctx: Ctx, msg: dict, args: str):
    uid, chat = msg["from"]["id"], msg["chat"]["id"]
    if args.strip().isdigit():
        return await send_invoice(ctx, chat, uid, int(args))
    html, rows = home(ctx, uid)
    await ctx.tg.rich(chat, html, rows)


async def pre_checkout(ctx: Ctx, q: dict):
    """Must be answered within 10 s: only accept invoices WE created, with the amount we expect."""
    payload, total, cur = q.get("invoice_payload", ""), q.get("total_amount", 0), q.get("currency")
    ok = cur == "XTR" and (
        (payload.startswith("don:") and payload[4:].isdigit() and int(payload[4:]) == total and 1 <= total <= ctx.cfg.donate_max_stars)
        or (payload == "prem30" and total == ctx.cfg.premium_stars_30d))
    await ctx.tg.precheckout(q["id"], ok, None if ok else "This invoice is not valid any more.")


async def on_paid(ctx: Ctx, msg: dict):
    uid, chat, pay = msg["from"]["id"], msg["chat"]["id"], msg["successful_payment"]
    cid, payload, stars = pay.get("telegram_payment_charge_id"), pay.get("invoice_payload", ""), int(pay.get("total_amount", 0))
    if not cid or pay.get("currency") != "XTR" or ctx.db.one("SELECT 1 x FROM payments WHERE charge_id=?", cid):
        return                                                    # unknown or already credited (Telegram may redeliver)
    kind = "premium" if payload == "prem30" else "donation"
    ctx.db.x("INSERT INTO payments(charge_id,user_id,kind,stars,payload,ts) VALUES(?,?,?,?,?,?)", cid, uid, kind, stars, payload, int(time.time()))
    if kind == "premium":
        ctx.db.add_premium(uid, 30)
        until = time.strftime("%Y-%m-%d", time.gmtime(ctx.db.user(uid)["premium_until"]))
        return await ctx.tg.send(chat, ctx.tr(uid, "premium_on", d=until))
    total = total_stars(ctx.db, uid)
    new = [n for m, n in TIERS if total >= m and ctx.db.give_badge(uid, n)]
    html = R.doc(R.heading("Thank you! 💖", 3), R.para(f"You donated {stars} ⭐ — total {total} ⭐."),
                 R.kv_table([("Tier", tier_name(total)), ("New badge", ", ".join(new) or "—")]))
    await ctx.tg.rich(chat, html, [[B("🏅 Supporters wall", "dn:wall"), B("🏠 Menu", "n:home", "success")]])


async def cmd_refund(ctx: Ctx, msg: dict, args: str):
    """/refund <telegram_payment_charge_id>  (owner only)."""
    if not ctx.is_owner(msg["from"]["id"]):
        return
    chat, cid = msg["chat"]["id"], args.strip()
    p = ctx.db.one("SELECT * FROM payments WHERE charge_id=? AND refunded=0", cid)
    if not p:
        return await ctx.tg.send(chat, "No such open payment.")
    if await ctx.tg.refund_stars(p["user_id"], cid) is None:
        return await ctx.tg.send(chat, "Telegram refused the refund.")
    ctx.db.x("UPDATE payments SET refunded=1 WHERE charge_id=?", cid)
    await ctx.tg.send(chat, f"Refunded {p['stars']} ⭐")
