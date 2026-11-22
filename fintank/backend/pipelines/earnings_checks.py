"""Checks that decide whether a Claude-written earnings note may publish. The
rule that matters: no invented figure ever reaches the site. Every number in
the note must trace back to the transcript, the stored previous note, or the
FMP estimates (including the beat/miss derived from them). Pure: no network.

Figure rules (extract_figures / matches)
- A figure is extracted only when it carries a unit: a currency prefix
  ($, C$, CA$, US$, CAD, USD), a scale (thousand/million/billion/trillion or
  K/M/B/T/mn/bn glued to the number), a percent sign / "percent" / "per cent",
  or bp / bps / "basis points". Bare numbers (years, "Q3", "3 key risks",
  employee counts) are ignored.
- Kinds: "money" (currency, scale or cents), "percent", "bp", and "pp"
  (percentage points: "pp", "pts", "percentage points"; its own kind, matched
  only against percentage-point figures in the sources). Kinds never
  cross-match. "13 cents" is money 0.13.
- Money is stored in units ("$3.2 billion" -> 3_200_000_000.0); percent and bp
  as written (12% -> 12.0). Thousands separators and decimals are read.
- Negative: a leading "-" / minus sign glued to the figure, or the figure
  wrapped in parentheses ("($0.05)", "$(0.05)", "(12%)"). A "-" followed by a
  space ("- 70%", a list bullet) or right after a number, percent or word (the
  dash in "6.5%-7%") is not a minus sign. A parenthetical like "(4.0%)" is
  read as negative; that is harmless because sign only matters for an
  explicit leading "-" in a note (see below).
- Units may be spaced ("12 %", "3.2 bn", "3.2 B") or hyphenated
  ("$500-million", "$3.2-billion", "150-basis-points", "125- basis points").
  Speaker approximations are read as the number: "$1.8-ish billion",
  "$25-odd million", "150+ million", "50 plus million".
- A range "$3.2 to $3.4 billion" or "3.2-3.4 billion": the first figure
  inherits the unit of the second ("1.78 to $1.82": the currency). A first
  figure with its own currency only inherits a money scale ("$0.92 to 11%"
  stays $0.92), and one written with thousands separators inherits nothing.
- Sources only (speakers state a unit once or not at all), all additive:
  - "and", "or" and "," also join a pair, and the first figure counts under
    both readings ("$0.12 or $187 million" sources $0.12 and $0.12 million).
  - A decimal number with no unit ("around 10.5", "about 5.2 in Q3") sources
    any kind at any scale; "N points" sources bp and pp. Whole numbers with no
    unit source nothing: they are too common in a transcript to prove a figure.
  - A figure within 40 characters after a decline word ("down", "fell",
    "lower", "loss"...) also sources its negative, so "down 4%" sources "-4%".
- A note figure matches a source value when the source value, expressed in the
  note figure's unit scale and rounded (half up) to the note figure's number
  of decimals, equals the note value: "$3.2 billion" matches 3,214,000,000.
  Only slack (ruling R7): a figure written with thousands separators that
  re-expresses exactly in the next scale up is read there, at that precision
  with at least 1 decimal: "3,200 million" is 3.2 billion (matches
  3.15-3.249B), "3,000 million" is 3.0 billion. Everything else is strict at
  its stated decimals in its own scale ("$10 billion" matches 9.5-10.49B).
- Unsigned (and parenthesised) note figures match on magnitude: prose says "a
  loss of $0.05" or "down 5%" without a minus sign. A note figure written with
  an explicit leading "-" ("-$0.05", "-5%") must match a source of the same sign.
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal

MIN_WORDS = 1000
MAX_WORDS = 3000
LEANS = ("bullish", "neutral", "bearish")
BLOCKLIST = (
    "buy rating", "sell rating", "we recommend", "price target",
    "strong buy", "strong sell", "you should buy", "you should sell",
)
SECTION_KEYS = (
    "results_vs_consensus", "guidance", "management_tone", "qa_themes",
    "what_changed", "risks", "bull_case", "bear_case", "watch_next",
)
KINDS = ("money", "percent", "bp", "pp")

_SCALES = {
    "thousand": 3, "k": 3, "million": 6, "mn": 6, "m": 6,
    "billion": 9, "bn": 9, "b": 9, "trillion": 12, "t": 12,
}
_PP_UNITS = ("pp", "pt", "pts")

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CURRENCY = r"(?:US\$|CA\$|C\$|\$|CAD\s?|USD\s?)"
# Words (and bp) may follow a space; letters must be glued to the number and must not
# start a longer word ("5M" yes, "5 men" no).
_APPROX = r"(?:\+|[\s-]?(?:ish|odd|plus|some-odd)\b)?"
_UNIT = (
    r"(?:(?:\s?-\s?|\s)?(?P<word>trillion|billion|million|thousand|percentage[\s-]+points?|per\s?cent|percent"
    r"|basis[\s-]+points?|bps?|cents?|pp|pts?)\b"
    r"|(?P<sym>\s?%|(?:bn|mn|[kmbt])(?![A-Za-z&])|\s(?:bn|mn|(?-i:[KMBT]))(?![A-Za-z&])))"
)
_FIGURE = re.compile(
    r"(?<![\w$.,])"                      # not glued to a preceding word or number
    r"(?P<neg>[-−]|\()?\s?"          # leading minus or opening parenthesis
    rf"(?P<cur>{_CURRENCY})?\s?"
    r"(?P<paren>\()?"                     # "$(0.05)"
    rf"(?P<num>{_NUMBER})"
    rf"{_APPROX}"
    rf"(?:{_UNIT})?"
    r"(?P<close>\))?",
    re.IGNORECASE,
)
# What may follow the first figure of a range or pair: " to $3.4 billion",
# "-3.4 billion", " and 70 basis points". The unit is stated once, on the second.
# A note joins a range with "-" or "to". A speaker also pairs figures with
# "and", "or" or a comma ("60 and 70 basis points", "$59 and $65 million",
# "87, 88%"), so on the source side the first figure is read both ways.
_NOTE_JOIN = r"\s*(?:-|–|to)\s*"
_SOURCE_JOIN = r"\s*-?\s*(?:-|–|to|and|or|,)\s*"


def _tails(join):
    return (re.compile(rf"{join}{_CURRENCY}?\s?(?:{_NUMBER}){_APPROX}{_UNIT}", re.IGNORECASE),
            # "1.78 to $1.82": only the second carries the currency.
            re.compile(rf"{join}{_CURRENCY}\s?(?:{_NUMBER})", re.IGNORECASE))


_NOTE_TAILS = _tails(_NOTE_JOIN)
_UNIT_AFTER = re.compile(rf"{_APPROX}{_UNIT}", re.IGNORECASE)
_SOURCE_TAILS = _tails(_SOURCE_JOIN)
# Source-side only (see sourced_values).
_BARE_DECIMAL = re.compile(r"(?<![\w$.,])(\d+\.\d+)(?![\d%])")
_POINTS = re.compile(r"(?<!basis )(?<!percentage )\b(\d+(?:\.\d+)?)[\s-]+points?\b", re.IGNORECASE)
_DECLINE = re.compile(r"\b(?:down|declin\w*|decreas\w*|fell|fall\w*|lower|loss\w*|negative|"
                      r"minus|drop\w*|contract\w*|reduc\w*|shrank|shrink\w*|minus)\b", re.IGNORECASE)


def _unit_of(m: re.Match) -> tuple[str, int] | None:
    """(kind, power-of-ten scale) for the unit captured in `m`, or None."""
    unit = re.sub(r"\s+", " ", (m.group("word") or m.group("sym") or "").lower()).strip()
    if unit.startswith("cent"):
        return "money", -2
    if unit.startswith("percentage") or unit in _PP_UNITS:
        return "pp", 0
    if unit == "%" or unit.startswith("per"):
        return "percent", 0
    if unit.startswith("basis") or unit in ("bp", "bps"):
        return "bp", 0
    if unit in _SCALES:
        return "money", _SCALES[unit]
    return None


def _looks_like_year(num: str) -> bool:
    return num.isdigit() and len(num) == 4 and 1900 <= int(num) <= 2100


def _is_minus(text: str, m: re.Match) -> bool:
    """A leading "-" is a minus sign only when glued to the figure and not
    right after a number, percent or word: "- 70%" is a list bullet and the
    "-" in "6.5%-7%" separates a range."""
    if m.group("neg") not in ("-", "\u2212"):
        return False
    at = m.start("neg")
    glued = not text[at + 1:at + 2].isspace()
    before = text[at - 1:at] if at else ""
    return glued and not (before.isalnum() or before in "%)")


def _extract(text: str, source: bool = False):
    """(value, kind, raw, start) for every unit-bearing figure in text. With
    source=True a first figure joined to a unit-bearing second one is yielded
    under both readings ("$0.12 or $187 million": $0.12 and $0.12 million)."""
    range_tail, currency_tail = _SOURCE_TAILS if source else _NOTE_TAILS
    for m in _FIGURE.finditer(text):
        num = m.group("num")
        own = _unit_of(m)
        if own is None and m.group("cur"):
            own = ("money", 0)
        units = []
        # "750,000 to 1 million" is already a whole number: no scale to inherit.
        if (own is None or own == ("money", 0)) and not _looks_like_year(num) and "," not in num:
            tail = range_tail.match(text, m.end())
            if tail and _unit_of(tail) and (own is None or _unit_of(tail)[0] == "money"):
                units.append(_unit_of(tail))      # "$0.92 to 11%" keeps its "$"
            elif currency_tail.match(text, m.end()):
                units.append(("money", 0))
        if own is not None and (source or not units):
            units.append(own)
        minus = _is_minus(text, m)
        closed = bool(m.group("close"))
        raw = m.group(0).strip()
        if not closed:
            raw = raw.lstrip("(").lstrip()
        if not minus:
            raw = raw.lstrip("-\u2212").lstrip()
        for kind, power in dict.fromkeys(units):
            value = Decimal(num.replace(",", "")) * Decimal(10) ** power
            if ((m.group("neg") == "(" or m.group("paren")) and closed) or minus:
                value = -value
            yield float(value), kind, raw, m.start()


def extract_figures(text: str) -> list[tuple[float, str, str]]:
    """Every unit-bearing figure in text as (value, kind, raw). Money is in
    units; percent and bp as written; parenthesised or minus-led are negative."""
    return [(v, k, raw) for v, k, raw, _ in _extract(text)]


def matches(value: float, raw: str, candidates: list[float]) -> bool:
    """True when a candidate, in the note figure's unit scale and rounded to
    its decimals, equals the note value. Signs are ignored (see docstring)."""
    m = re.search(_NUMBER, raw)
    if not m or value == 0:
        return any(c == value for c in candidates)
    signed = raw.lstrip().startswith(("-", "\u2212"))
    num = Decimal(m.group(0).replace(",", ""))
    decimals = len(m.group(0).split(".")[1]) if "." in m.group(0) else 0
    scale = Decimal(10) ** round(math.log10(abs(value) / float(num))) if num else Decimal(1)
    if "," in m.group(0) and scale in (Decimal(10) ** 3, Decimal(10) ** 6, Decimal(10) ** 9):
        # "3,200 million" is read as 3.2 billion (ruling R7), at least 1 decimal.
        num, scale = num / 1000, scale * 1000
        decimals = max(1, -num.normalize().as_tuple().exponent)
    quantum = Decimal(1).scaleb(-decimals)
    want = num.quantize(quantum, ROUND_HALF_UP)
    for c in candidates:
        if signed and c >= 0:
            continue
        rounded = (abs(Decimal(repr(float(c)))) / scale).quantize(quantum, ROUND_HALF_UP)
        if rounded == want:
            return True
    return False


def note_text(note: dict) -> str:
    """Headline, key points and every section text (works on Claude's output
    and on a stored note; a null what_changed is skipped)."""
    if not isinstance(note, dict):
        return ""
    headline = note.get("headline")
    parts = [headline if isinstance(headline, str) else ""]
    kp = note.get("key_points")
    parts += [p for p in (kp if isinstance(kp, list) else []) if isinstance(p, str)]
    sections = note.get("sections")
    parts += [v for v in (sections.values() if isinstance(sections, dict) else []) if isinstance(v, str)]
    return "\n".join(p for p in parts if p)


def _derived(estimates: dict) -> dict[str, list[float]]:
    out = {k: [] for k in KINDS}
    for est, act in (("eps_estimate", "eps_actual"), ("revenue_estimate", "revenue_actual")):
        e, a = estimates.get(est), estimates.get(act)
        for v in (e, a):
            if v is not None:
                out["money"].append(float(v))
        if e is not None and a is not None:
            out["money"].append(float(a) - float(e))
            if e != 0:
                out["percent"].append((float(a) - float(e)) / abs(float(e)) * 100)
    return out


def sourced_values(transcript: str, estimates: dict, previous_note: dict | None) -> dict[str, list[float]]:
    """Every figure, by kind, in the transcript and previous note, plus the
    estimate values and the derived beat/miss amounts and percentages."""
    sources = [transcript or ""]
    if previous_note:
        sources.append(note_text(previous_note))
    out = _derived(estimates or {})
    for text in sources:
        for value, kind, _, start in _extract(text, source=True):
            out[kind].append(value)
            if value > 0 and _DECLINE.search(text, max(0, start - 40), start):
                out[kind].append(-value)          # "down 4%" sources a note's "-4%"
        _add_unitless(text, out)
    return out


def _add_unitless(text: str, out: dict) -> None:
    """Speakers often state a unit once or not at all: "around 10.5", "about
    5.2 in Q3", "310 points of margin". A decimal number counts as a source for
    any kind at any scale, and "N points" for bp and pp. Bare whole numbers
    stay unsourced: they are too common in a transcript to prove anything."""
    for m in _BARE_DECIMAL.finditer(text):
        if _UNIT_AFTER.match(text, m.end()):
            continue                              # "1.5 percentage points" keeps its kind
        v = float(m.group(1))
        for kind in ("percent", "bp", "pp"):
            out[kind].append(v)
        out["money"] += [v * 10 ** p for p in (0, 3, 6, 9, 12)] + [v / 100]
    for m in _POINTS.finditer(text):
        v = float(m.group(1))
        out["bp"].append(v)
        out["pp"].append(v)


def _blank(v) -> bool:
    return not isinstance(v, str) or not v.strip()


def _type_problems(note) -> list[str]:
    """Wrong types anywhere in Claude's output; checked first so malformed
    output yields reasons instead of an exception in the text checks."""
    if not isinstance(note, dict):
        return ["note is not an object"]
    problems = []
    for key in ("lean", "headline"):
        if not isinstance(note.get(key), str):
            problems.append(f"{key} must be a string")
    kp = note.get("key_points")
    if not isinstance(kp, list) or not all(isinstance(p, str) for p in kp):
        problems.append("key_points must be a list of strings")
    sections = note.get("sections")
    if not isinstance(sections, dict):
        problems.append("sections must be an object")
    else:
        for key, v in sections.items():
            if v is not None and not isinstance(v, str):
                problems.append(f"section {key} must be a string or null")
    return problems


def _schema_problems(note: dict, has_previous: bool) -> list[str]:
    problems = []
    if _blank(note.get("headline")):
        problems.append("headline missing or empty")
    kp = note.get("key_points")
    if not isinstance(kp, list) or not all(isinstance(p, str) for p in kp):
        problems.append("key_points must be a list of strings")
    elif len(kp) != 3:
        problems.append(f"key_points must have exactly 3 items, got {len(kp)}")
    elif any(_blank(p) for p in kp):
        problems.append("key_points contains an empty item")
    sections = note.get("sections")
    if not isinstance(sections, dict):
        return problems + ["sections missing or not an object"]
    for key in SECTION_KEYS:
        if key == "what_changed" and not has_previous:
            continue
        if _blank(sections.get(key)):
            problems.append(f"section {key} missing or empty")
    return problems


def check_note(note: dict, transcript: str, estimates: dict, previous_note: dict | None) -> list[str]:
    """Failure reasons for a note; an empty list means it may publish."""
    reasons = _type_problems(note)
    if reasons:
        return reasons
    if note.get("lean") not in LEANS:
        reasons.append(f"lean must be one of {', '.join(LEANS)}, got {note.get('lean')!r}")
    reasons += _schema_problems(note, previous_note is not None)
    text = note_text(note)
    words = len(text.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        reasons.append(f"word count {words} outside {MIN_WORDS}-{MAX_WORDS} words")
    for phrase in BLOCKLIST:
        if re.search(rf"\b{re.escape(phrase)}s?\b", text, re.IGNORECASE):
            reasons.append(f"blocklisted phrase: {phrase}")
    sourced = sourced_values(transcript, estimates, previous_note)
    bad = []
    for value, kind, raw in extract_figures(text):
        if not matches(value, raw, sourced[kind]) and raw not in bad:
            bad.append(raw)
    if bad:
        reasons.append("unsourced figures: " + ", ".join(bad))
    return reasons
