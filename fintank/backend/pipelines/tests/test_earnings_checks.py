import pytest

from pipelines import earnings_checks as e

SECTION_KEYS = [
    "results_vs_consensus", "guidance", "management_tone", "qa_themes",
    "what_changed", "risks", "bull_case", "bear_case", "watch_next",
]


def make_note(extra="", words=1500, what_changed="Changes since last quarter."):
    """A valid note whose total word count is exactly `words`."""
    note = {
        "lean": "neutral",
        "headline": "Solid quarter",
        "key_points": ["Point one.", "Point two.", "Point three."],
        "sections": {k: f"Section {k} text." for k in SECTION_KEYS},
    }
    note["sections"]["what_changed"] = what_changed
    if extra:
        note["sections"]["guidance"] = extra
    have = len(e.note_text(note).split())
    note["sections"]["watch_next"] += " " + " ".join(["filler"] * (words - have))
    assert len(e.note_text(note).split()) == words
    return note


def check(note, transcript="", estimates=None, previous=None):
    return e.check_note(note, transcript, estimates or {}, previous)


def unmatched(reasons):
    return [r for r in reasons if "figure" in r]


def test_clean_note_passes():
    assert check(make_note(), previous={"headline": "h", "key_points": [], "sections": {}}) == []


def test_equivalent_money_forms_match():
    note = make_note("Revenue was $3.2 billion, or 3.2B, or 3,200 million, or C$3.2 billion.")
    assert unmatched(check(note, "revenue of $3,214 million")) == []


def test_invented_figure_fails():
    note = make_note("Revenue reached $4.1 billion.")
    reasons = check(note, "revenue of $3,214 million")
    assert any("$4.1 billion" in r for r in reasons)


def test_negative_and_parentheses_equal():
    note = make_note("EPS was ($0.05) and a loss of -$0.05 per share.")
    assert unmatched(check(note, "we lost -$0.05 per share")) == []
    note = make_note("EPS was ($0.05).")
    assert unmatched(check(note, "a loss of $(0.05) per share")) == []


def test_bp_and_percent_forms():
    note = make_note("Margin up 120 bp, 120 basis points, 120 bps; sales up 12%, 12 per cent, 12 percent.")
    assert unmatched(check(note, "margin expanded 120 basis points and sales grew 12 percent")) == []


def test_kinds_do_not_cross_match():
    note = make_note("Sales up 12%.")
    assert unmatched(check(note, "we spent $12 on lunch"))
    note = make_note("Costs of $12.")
    assert unmatched(check(note, "sales up 12%"))


def test_beat_vs_consensus_is_allowed():
    est = {"eps_estimate": 3.21, "eps_actual": 3.34, "revenue_estimate": None, "revenue_actual": None}
    note = make_note("EPS of $3.34 versus $3.21 expected: a beat by $0.13 (4.0%).")
    assert unmatched(check(note, "", est)) == []


def test_revenue_estimates_scale():
    est = {"revenue_estimate": 3.1e9, "revenue_actual": 3.2e9}
    note = make_note("Revenue was $3.2 billion against $3,100 million expected, a 3.2% beat.")
    assert unmatched(check(note, "", est)) == []


def test_previous_note_figures_count_as_sourced():
    prev = {"headline": "Revenue hit $2.9 billion", "key_points": ["Margin 45%"], "sections": {"guidance": "ok"}}
    note = make_note("Last quarter revenue was $2.9 billion and margin was 45%.")
    assert unmatched(check(note, "", None, prev)) == []
    assert unmatched(check(note, "", None, None))


def test_years_and_quarters_ignored():
    note = make_note("In fiscal 2026 Q3 there are 3 key risks and 2,500 employees.")
    assert e.extract_figures(e.note_text(note)) == []
    assert unmatched(check(note)) == []


def test_range_inherits_unit():
    note = make_note("Guidance of $3.2 to $3.4 billion, then $3.2-3.4 billion.")
    assert unmatched(check(note, "we expect $3.2 billion to $3.4 billion")) == []


def test_extract_figures_values():
    got = {raw: (v, k) for v, k, raw in e.extract_figures("$3.2 billion, 3,200 million, 5K, 12%, 120 bp, ($0.05), US$2 trillion")}
    assert got["$3.2 billion"] == (3.2e9, "money")
    assert got["3,200 million"] == (3.2e9, "money")
    assert got["5K"] == (5000.0, "money")
    assert got["12%"] == (12.0, "percent")
    assert got["120 bp"] == (120.0, "bp")
    assert got["($0.05)"] == (-0.05, "money")
    assert got["US$2 trillion"] == (2e12, "money")


def test_rounding_in_note_scale():
    assert e.matches(3.2e9, "$3.2 billion", [3_214_000_000.0])
    assert not e.matches(3.2e9, "$3.2 billion", [3_260_000_000.0])
    assert not e.matches(3.2e9, "$3.2 billion", [3_250_000_000.0])  # half rounds up to 3.3
    assert e.matches(3.3e9, "$3.3 billion", [3_250_000_000.0])
    assert not e.matches(4.1e9, "$4.1 billion", [3.2e9])


@pytest.mark.parametrize("words,ok", [(999, False), (1000, True), (3000, True), (3001, False)])
def test_word_count_bounds(words, ok):
    reasons = check(make_note(words=words))
    assert (reasons == []) is ok
    if not ok:
        assert any("words" in r for r in reasons)


def test_what_changed_required_only_with_previous():
    prev = {"headline": "h", "key_points": [], "sections": {}}
    assert check(make_note(what_changed=None)) == []
    assert check(make_note(what_changed=""), previous=prev)
    assert check(make_note(what_changed=None), previous=prev)
    assert check(make_note(what_changed="Something changed."), previous=prev) == []


def test_bad_lean_and_wrong_key_point_count_fail():
    note = make_note()
    note["lean"] = "very bullish"
    assert any("lean" in r for r in check(note))
    note = make_note()
    note["key_points"] = ["one", "two"]
    assert any("key_points" in r for r in check(note))


def test_missing_keys_and_empty_sections_fail():
    note = make_note()
    del note["headline"]
    assert check(note)
    note = make_note()
    note["sections"]["risks"] = "  "
    assert any("risks" in r for r in check(note))
    note = make_note()
    del note["sections"]["bull_case"]
    assert any("bull_case" in r for r in check(note))
    assert check({"lean": "neutral"})


def test_blocklist_phrase_fails():
    note = make_note("We recommend investors buy the stock.")
    assert any("we recommend" in r.lower() for r in check(note))
    note = make_note("A Price Target discussion.")
    assert any("price target" in r.lower() for r in check(note))
    assert not any("blocklist" in r for r in check(make_note("They recommended nothing.")))


@pytest.mark.parametrize("raw,value,source", [
    ("$10 billion", 10e9, 14.6e9),
    ("$20 billion", 20e9, 15.1e9),
    ("$100 million", 100e6, 51e6),
    ("$3,000 million", 3e9, 2.5e9),
])
def test_trailing_zero_figures_are_strict(raw, value, source):
    assert not e.matches(value, raw, [source])


def test_strict_and_thousands_separator_slack():
    assert e.matches(10e9, "$10 billion", [9.6e9])
    assert e.matches(3.2e9, "3,200 million", [3_214_000_000.0])
    assert e.matches(3e9, "$3,000 million", [3_020_000_000.0])
    assert not e.matches(3.2e9, "3,200 million", [3_260_000_000.0])


@pytest.mark.parametrize("bad", [
    {"lean": "neutral", "headline": 5, "key_points": ["a", "b", "c"], "sections": {}},
    {"lean": "neutral", "headline": "h", "key_points": ["a", "b", "c"], "sections": ["x"]},
    {"lean": "neutral", "headline": "h", "key_points": "abc", "sections": {}},
    {"lean": "neutral", "headline": "h", "key_points": [1, 2, 3], "sections": {"risks": 4}},
    {"lean": 3, "headline": "h", "key_points": [], "sections": None},
    "not a dict",
])
def test_malformed_output_returns_reasons(bad):
    assert check(bad)


def test_pp_kind():
    note = make_note("Margin up 1.5 percentage points, or 1.5 pp, or 1.5 pts.")
    assert unmatched(check(note, "margin rose 1.5 percentage points")) == []
    assert unmatched(check(make_note("Margin up 2.5 pp."), "margin rose 1.5 percentage points"))
    assert unmatched(check(make_note("Margin up 1.5%."), "margin rose 1.5 percentage points"))


def test_cents():
    est = {"eps_estimate": 3.21, "eps_actual": 3.34}
    assert unmatched(check(make_note("A beat by 13 cents."), "", est)) == []
    assert unmatched(check(make_note("A beat by 13 cents or $0.13."), "we earned 13 cents")) == []
    assert unmatched(check(make_note("A beat by 40 cents."), "", est))
    assert e.extract_figures("40 cents")[0][:2] == (0.4, "money")


def test_spaced_and_hyphenated_units():
    note = make_note("Sales up 12 %, revenue 3.2 bn and 3.2 B, a $500-million buyback and a $3.2-billion deal.")
    src = "sales grew 12%, revenue $3.2 billion, a $500 million buyback and $3.2-billion deal"
    assert unmatched(check(note, src)) == []
    assert unmatched(check(make_note("A $700-million buyback."), src))
    note = make_note("Revenue of $3.2 billion and a $500 million buyback.")
    assert unmatched(check(note, "revenue of $3.2-billion with a $500-million buyback")) == []
    assert e.extract_figures("a $500-million buyback")[0][:2] == (5e8, "money")


def test_explicit_minus_requires_negative_source():
    assert unmatched(check(make_note("EPS of -$0.05."), "EPS was $0.05"))
    assert unmatched(check(make_note("EPS of -$0.05."), "EPS was ($0.05)")) == []
    assert unmatched(check(make_note("Sales fell -5%."), "sales grew 5%"))
    assert unmatched(check(make_note("Sales fell -5%."), "sales fell 5%")) == []  # "fell" signs it
    assert unmatched(check(make_note("Sales fell 5%."), "sales were (5%)")) == []
    assert unmatched(check(make_note("Sales fell 5%."), "sales fell 5%")) == []


def test_blocklist_plurals():
    assert any("price target" in r for r in check(make_note("Analysts raised price targets.")))
    assert any("buy rating" in r for r in check(make_note("Several buy ratings.")))


def test_bullets_and_range_dashes_are_not_minus_signs():
    assert unmatched(check(make_note("Highlights:\n- 70% of Pillsbury is renovated."), "70% of it")) == []
    assert unmatched(check(make_note("Growth guidance of 6.5%-7%."), "6.5% to 7%")) == []
    assert e.extract_figures("- $500 million")[0][0] == 5e8


def test_hyphenated_and_spaced_unit_forms_in_sources():
    assert unmatched(check(make_note("Gross margin expanded 150 basis points."),
                           "We expanded gross margin 150-basis-points to 40.5%.")) == []
    assert unmatched(check(make_note("Margins up 75 to 125 basis points."),
                           "margins to improve 75- to 125- basis points")) == []


def test_source_pairs_share_the_unit_stated_once():
    assert unmatched(check(make_note("Core spread of 60 to 70 basis points."),
                           "60 and 70 basis points of real GDP")) == []
    assert unmatched(check(make_note("Interest expense of $59 to $65 million."),
                           "an expense between $59 and $65 million")) == []
    assert unmatched(check(make_note("2027 guidance of $1.78 to $1.82."),
                           "2027 core EPS guidance of 1.78 to $1.82")) == []
    # either reading of "$0.12 or $187 million" counts as sourced
    assert unmatched(check(make_note("A $0.12, or $187 million, charge."),
                           "a $0.12 or $187 million noncash charge")) == []


def test_note_pairs_keep_their_own_currency():
    # "$1.87 and 16.3%" is $1.87, not 1.87%; "$0.92 to 11%" is $0.92
    assert unmatched(check(make_note("EPS of $1.87 and 16.3% ROTCE."), "EPS of $1.87, ROTCE 16.3%")) == []
    assert unmatched(check(make_note("AFFO up $0.92 to 11% growth."), "AFFO per share of $0.92 to 11%")) == []


def test_speaker_approximations():
    src = "call it $1.8-ish billion, $25-odd million, a 150+ million expansion, 50 plus million dollars"
    note = make_note("About $1.8 billion, about $25 million, 150 million, more than $50 million.")
    assert unmatched(check(note, src)) == []


def test_unitless_decimals_and_points_in_sources():
    assert unmatched(check(make_note("Growth around 10.5%."), "It's around 10.5, and we expect")) == []
    assert unmatched(check(make_note("About $5.2 million in Q3."), "about 5.2 in Q3")) == []
    assert unmatched(check(make_note("310 basis points of lift."), "another 310 points of margin lift")) == []
    # a decimal that carries its own unit keeps its kind
    assert unmatched(check(make_note("Margin up 1.5%."), "margin rose 1.5 percentage points"))


def test_unitless_whole_numbers_stay_unsourced():
    assert unmatched(check(make_note("Inflation cost about 160 basis points."), "inflation of about 160 in the quarter"))


def test_not_figures():
    assert e.extract_figures("2027 M&A pipeline") == []
    assert e.extract_figures("750,000 to 1 million tons")[-1][0] == 1e6
    assert len(e.extract_figures("750,000 to 1 million tons")) == 1
