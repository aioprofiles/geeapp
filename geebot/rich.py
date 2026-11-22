"""Rich-message HTML builders (Bot API 10.1+). Every builder takes PLAIN text and escapes it exactly once, so the
`&amp;amp;` double-escaping seen in other bots cannot happen. Wrap already-built HTML in Raw() to embed it."""
import html as _html
import re


class Raw(str):
    """Already-safe HTML; never escaped again."""


def esc(x) -> str:
    return str(x) if isinstance(x, Raw) else _html.escape(str(x), quote=False)


def b(x) -> Raw: return Raw(f"<b>{esc(x)}</b>")
def i(x) -> Raw: return Raw(f"<i>{esc(x)}</i>")
def code(x) -> Raw: return Raw(f"<code>{esc(x)}</code>")


def heading(text, level: int = 3) -> Raw: return Raw(f"<h{level}>{esc(text)}</h{level}>")
def para(*parts) -> Raw: return Raw("<p>" + "".join(esc(p) for p in parts) + "</p>")
def hr() -> Raw: return Raw("<hr/>")
def footer(text) -> Raw: return Raw(f"<footer>{esc(text)}</footer>")
def callout(text) -> Raw: return Raw(f"<blockquote>{esc(text)}</blockquote>")


def pre(text, language: str = "") -> Raw:
    cls = f' class="language-{_html.escape(language, quote=True)}"' if language else ""
    return Raw(f"<pre><code{cls}>{esc(text)}</code></pre>")


def ul(items) -> Raw: return Raw("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>")


def table(rows, header=None, caption=None) -> Raw:
    head = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr>" if header else ""
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return Raw(f"<table>{cap}{head}{body}</table>")


def kv_table(pairs) -> Raw:
    return table([[k, v] for k, v in pairs])


def details(summary, *body, open: bool = False) -> Raw:
    return Raw(f"<details{' open' if open else ''}><summary>{esc(summary)}</summary>{''.join(esc(x) for x in body)}</details>")


def doc(*blocks) -> str:
    return "".join(esc(x) if not isinstance(x, Raw) else x for x in blocks)


_BR = re.compile(r"</(p|h[1-6]|tr|li|blockquote|footer|details|summary|pre|caption)>|<br\s*/?>|<hr\s*/?>", re.I)
_TD = re.compile(r"</t[dh]>\s*<t[dh][^>]*>", re.I)


def to_plain(html: str) -> str:
    """Readable plain text for the fallback path (tags stripped, structure kept)."""
    s = _TD.sub(" — ", html)
    s = _BR.sub("\n", s)
    s = re.sub(r"<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", _html.unescape(s)).strip()
