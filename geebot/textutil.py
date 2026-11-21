"""Sinhala-aware text helpers: normalisation, romanisation ("Singlish"), fuzzy match, rhymes."""
import difflib
import re
import unicodedata

_C = {0x9A: "k", 0x9B: "kh", 0x9C: "g", 0x9D: "gh", 0x9E: "ng", 0x9F: "ng", 0xA0: "ch", 0xA1: "chh", 0xA2: "j",
      0xA3: "jh", 0xA4: "ny", 0xA5: "gn", 0xA6: "nj", 0xA7: "t", 0xA8: "th", 0xA9: "d", 0xAA: "dh", 0xAB: "n",
      0xAC: "nd", 0xAD: "th", 0xAE: "thh", 0xAF: "d", 0xB0: "dh", 0xB1: "n", 0xB3: "nd", 0xB4: "p", 0xB5: "ph",
      0xB6: "b", 0xB7: "bh", 0xB8: "m", 0xB9: "mb", 0xBA: "y", 0xBB: "r", 0xBD: "l", 0xC0: "v", 0xC1: "sh",
      0xC2: "sh", 0xC3: "s", 0xC4: "h", 0xC5: "l", 0xC6: "f"}
_V = {0x85: "a", 0x86: "aa", 0x87: "ae", 0x88: "aae", 0x89: "i", 0x8A: "ii", 0x8B: "u", 0x8C: "uu", 0x8D: "ru",
      0x8E: "ruu", 0x91: "e", 0x92: "ee", 0x93: "ai", 0x94: "o", 0x95: "oo", 0x96: "au"}
_S = {0xCF: "aa", 0xD0: "ae", 0xD1: "aae", 0xD2: "i", 0xD3: "ii", 0xD4: "u", 0xD6: "uu", 0xD8: "ru", 0xD9: "e",
      0xDA: "ee", 0xDB: "ai", 0xDC: "o", 0xDD: "oo", 0xDE: "au"}
_BASE = 0x0D00
VIRAMA, ZWJ = _BASE + 0xCA, 0x200D
CONS = {_BASE + k: v for k, v in _C.items()}
IND_V = {_BASE + k: v for k, v in _V.items()}
SIGNS = {_BASE + k: v for k, v in _S.items()}


def roman(text: str) -> str:
    """Approximate Sinhala -> Latin (for display and fuzzy matching, not a strict standard)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = ord(text[i])
        if c in CONS:
            base = CONS[c]
            nxt = ord(text[i + 1]) if i + 1 < n else 0
            if nxt in SIGNS:
                out.append(base + SIGNS[nxt]); i += 2
            elif nxt == VIRAMA:
                out.append(base); i += 2
                if i < n and ord(text[i]) == ZWJ:  # yansa / rakaransa: keep the consonant bare
                    i += 1
            else:
                out.append(base + "a"); i += 1
        elif c in IND_V:
            out.append(IND_V[c]); i += 1
        elif c == _BASE + 0x82:
            out.append("ng"); i += 1
        elif c == _BASE + 0x83:
            out.append("h"); i += 1
        elif c == ZWJ:
            i += 1
        else:
            out.append(text[i]); i += 1
    return "".join(out)


_PUNCT = re.compile(r"[^\w\s\u0D80-\u0DFF]", re.UNICODE)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("\u200d", "")
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", s.lower())).strip()


def key(s: str) -> str:
    """Comparison key: normalised + romanised, so 'ආදරේ' and 'aadare' compare sensibly."""
    return re.sub(r"[aeiou]+", "a", roman(norm(s)))  # collapse vowel length noise


def similarity(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    r1 = difflib.SequenceMatcher(None, na, nb).ratio()
    r2 = difflib.SequenceMatcher(None, key(a), key(b)).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    contain = 1.0 if (na in nb or nb in na) and min(len(na), len(nb)) >= 3 else 0.0
    return max(r1, r2, jac, contain * 0.9)


def graphemes(s: str) -> list[str]:
    out: list[str] = []
    for ch in s:
        if out and (unicodedata.category(ch) in ("Mn", "Mc") or ord(ch) == ZWJ or (out[-1][-1:] == "\u200d")
                    or ord(ch) == VIRAMA):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def rhyme_key(word: str, n: int = 1) -> str:
    g = graphemes(norm(word).replace(" ", ""))
    return "".join(g[-n:]) if g else ""


def rhymes(word: str, vocab: list[str], n: int = 1, limit: int = 20) -> list[str]:
    k = rhyme_key(word, n)
    if not k:
        return []
    seen, res = {norm(word)}, []
    for w in vocab:
        w = norm(w)
        if w and w not in seen and rhyme_key(w, n) == k:
            seen.add(w); res.append(w)
            if len(res) >= limit:
                break
    return res


def words(s: str) -> list[str]:
    return [w for w in norm(s).split() if w]
