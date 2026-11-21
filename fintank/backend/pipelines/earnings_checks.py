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
- Kinds: "money" (currency or scale), "percent", "bp". Kinds never cross-match.
- Money is stored in units ("$3.2 billion" -> 3_200_000_000.0); percent and bp
  as written (12% -> 12.0). Thousands separators and decimals are read.
- Negative: a leading "-" / minus sign, or the figure wrapped in parentheses
  ("($0.05)", "$(0.05)", "(12%)").
- A range "$3.2 to $3.4 billion" or "3.2-3.4 billion": the first figure
  inherits the unit of the second.
- A note figure matches a source value when the source value, expressed in the
  note figure's unit scale and rounded (half up) to the note figure's number
  of decimals, equals the note value: "$3.2 billion" matches 3,214,000,000.
  A scaled whole number ("3,200 million") counts its trailing zeros as
  rounding, so it also matches 3,214 million.
- Signs are ignored when matching: prose says "a loss of $0.05" or "down 5%"
  without a minus sign, so magnitudes are compared.
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal

MIN_WORDS = 1200
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
KINDS = ("money", "percent", "bp")

_SCALES = {
    "thousand": 3, "k": 3, "million": 6, "mn": 6, "m": 6,
    "billion": 9, "bn": 9, "b": 9, "trillion": 12, "t": 12,
}

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CURRENCY = r"(?:US\$|CA\$|C\$|\$|CAD\s?|USD\s?)"
# Words (and bp) may follow a space; letters must be glued to the number and must not
# start a longer word ("5M" yes, "5 men" no).
_UNIT = (
    r"(?:\s?(?P<word>trillion|billion|million|thousand|per\s?cent|percent|basis\s+points?|bps?)\b"
    r"|(?P<sym>%|(?:bn|mn|[kmbt])(?![A-Za-z])))"
)
_FIGURE = re.compile(
    r"(?<![\w$.,])"                      # not glued to a preceding word or number
    r"(?P<neg>[-−]|\()?\s?"          # leading minus or opening parenthesis
    rf"(?P<cur>{_CURRENCY})?\s?"
    r"(?P<paren>\()?"                     # "$(0.05)"
    rf"(?P<num>{_NUMBER})"
    rf"(?:{_UNIT})?"
    r"(?P<close>\))?",
    re.IGNORECASE,
)
# What may follow the first figure of a range: " to $3.4 billion", "-3.4 billion".
_RANGE_TAIL = re.compile(
    rf"\s*(?:-|–|to)\s*{_CURRENCY}?\s?(?:{_NUMBER}){_UNIT}", re.IGNORECASE
)


def _unit_of(m: re.Match) -> tuple[str, int] | None:
    """(kind, power-of-ten scale) for the unit captured in `m`, or None."""
    unit = re.sub(r"\s+", " ", (m.group("word") or m.group("sym") or "").lower())
    if unit == "%" or unit.startswith("per"):
        return "percent", 0
    if unit.startswith("basis") or unit in ("bp", "bps"):
        return "bp", 0
    if unit in _SCALES:
        return "money", _SCALES[unit]
    return None


def _looks_like_year(num: str) -> bool:
    return num.isdigit() and len(num) == 4 and 1900 <= int(num) <= 2100


def extract_figures(text: str) -> list[tuple[float, str, str]]:
    """Every unit-bearing figure in text as (value, kind, raw). Money is in
    units; percent and bp as written; parenthesised or minus-led are negative."""
    figures = []
    for m in _FIGURE.finditer(text):
        num = m.group("num")
        unit = _unit_of(m)
        if unit is None and not _looks_like_year(num):
            tail = _RANGE_TAIL.match(text, m.end())
            if tail:
                unit = _unit_of(tail)
        if unit is None and m.group("cur"):
            unit = ("money", 0)
        if unit is None:
            continue
        kind, power = unit
        value = Decimal(num.replace(",", "")) * Decimal(10) ** power
        closed = bool(m.group("close"))
        if (m.group("neg") == "(" or m.group("paren")) and closed:
            value = -value
        elif m.group("neg") in ("-", "−"):
            value = -value
        raw = m.group(0).strip()
        if not closed:
            raw = raw.lstrip("(").lstrip()
        figures.append((float(value), kind, raw))
    return figures


def matches(value: float, raw: str, candidates: list[float]) -> bool:
    """True when a candidate, in the note figure's unit scale and rounded to
    its decimals, equals the note value. Signs are ignored (see docstring)."""
    m = re.search(_NUMBER, raw)
    if not m or value == 0:
        return any(c == value for c in candidates)
    num = Decimal(m.group(0).replace(",", ""))
    decimals = len(m.group(0).split(".")[1]) if "." in m.group(0) else 0
    scale = Decimal(10) ** round(math.log10(abs(value) / float(num))) if num else Decimal(1)
    if scale > 1 and "." not in m.group(0):
        # "3,200 million" is a rounded figure: trailing zeros are not precision.
        decimals = -(len(m.group(0).replace(",", "")) - len(m.group(0).replace(",", "").rstrip("0")))
    quantum = Decimal(1).scaleb(-decimals)
    for c in candidates:
        rounded = (abs(Decimal(repr(float(c)))) / scale).quantize(quantum, ROUND_HALF_UP)
        if rounded == num.quantize(quantum, ROUND_HALF_UP):
            return True
    return False


def note_text(note: dict) -> str:
    """Headline, key points and every section text (works on Claude's output
    and on a stored note; a null what_changed is skipped)."""
    parts = [note.get("headline") or ""]
    parts += [p for p in (note.get("key_points") or []) if isinstance(p, str)]
    sections = note.get("sections") or {}
    parts += [v for v in sections.values() if isinstance(v, str)]
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
        for value, kind, _ in extract_figures(text):
            out[kind].append(value)
    return out


def _blank(v) -> bool:
    return not isinstance(v, str) or not v.strip()


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
    reasons = []
    if note.get("lean") not in LEANS:
        reasons.append(f"lean must be one of {', '.join(LEANS)}, got {note.get('lean')!r}")
    reasons += _schema_problems(note, previous_note is not None)
    text = note_text(note)
    words = len(text.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        reasons.append(f"word count {words} outside {MIN_WORDS}-{MAX_WORDS} words")
    for phrase in BLOCKLIST:
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            reasons.append(f"blocklisted phrase: {phrase}")
    sourced = sourced_values(transcript, estimates, previous_note)
    bad = []
    for value, kind, raw in extract_figures(text):
        if not matches(value, raw, sourced[kind]) and raw not in bad:
            bad.append(raw)
    if bad:
        reasons.append("unsourced figures: " + ", ".join(bad))
    return reasons
