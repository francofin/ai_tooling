"""Unit tests for the pure helpers of the fundamentals check in verify_stable
(no FMP, no S3). Importing the module must have no side effects."""
import pandas as pd
import pytest

from pipelines import pipeline_config as cfg
from pipelines import verify_stable as vs


def _closes(rows):
    return pd.Series([c for _, c in rows], index=pd.to_datetime([d for d, _ in rows]))


# ── close_ratio ──────────────────────────────────────────────────────────
def test_close_ratio_uses_close_on_or_before_v3_run_date():
    closes = _closes([("2026-11-13", 100.0), ("2026-11-14", 80.0),
                      ("2026-11-17", 90.0), ("2026-11-20", 60.0)])
    assert vs.close_ratio(closes) == pytest.approx(60.0 / 80.0)


def test_close_ratio_falls_back_to_last_close_before_the_date():
    closes = _closes([("2026-11-12", 50.0), ("2026-11-20", 55.0)])   # 11-14 is a gap
    assert vs.close_ratio(closes) == pytest.approx(1.1)


@pytest.mark.parametrize("closes", [
    None, pd.Series(dtype=float), _closes([("2026-11-16", 10.0), ("2026-11-20", 12.0)])])
def test_close_ratio_none_without_a_base(closes):
    assert vs.close_ratio(closes) is None


# ── drift_factor ─────────────────────────────────────────────────────────
RD = {"price": 0.8, "ev": 0.9}


def test_drift_factor_direct_price_field_scales_with_price():
    assert vs.drift_factor("peRatioTTM", RD) == pytest.approx(0.8)
    assert vs.drift_factor("marketCapTTM", RD) == pytest.approx(0.8)


def test_drift_factor_inverse_field():
    assert vs.drift_factor("dividendYielTTM", RD) == pytest.approx(1 / 0.8)
    assert vs.drift_factor("debtToMarketCapTTM", RD) == pytest.approx(1 / 0.8)


def test_drift_factor_ev_multiple_uses_ev_ratio():
    assert vs.drift_factor("evToSalesTTM", RD) == pytest.approx(0.9)
    assert vs.drift_factor("enterpriseValueMultipleTTM", RD) == pytest.approx(0.9)


@pytest.mark.parametrize("name", ["priceless", "perShareFoo", "pbFoo", "returnOnEquityTTM",
                                  "payoutRatioTTM", "pegFoo"])
def test_drift_factor_unlisted_names_are_never_scaled(name):
    # a prefix match would have flagged these; only the explicit lists scale
    assert vs.drift_factor(name, RD) is None


def test_drift_factor_none_without_ratios():
    assert vs.drift_factor("peRatioTTM", None) is None
    assert vs.drift_factor("peRatioTTM", {"price": None, "ev": None}) is None
    assert vs.drift_factor("evToSalesTTM", {"price": 0.8, "ev": None}) is None


def test_explicit_sets_are_real_v3_ttm_fields_and_disjoint():
    fields = set(cfg.FIELD_MAPPINGS["company_ratios_ttm"]) | set(cfg.FIELD_MAPPINGS["company_metrics_ttm"])
    sets = (vs.PRICE_DRIVEN, vs.PRICE_INVERSE, vs.EV_DRIVEN)
    for s in sets:
        assert s <= fields
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])


# ── ttm_verdict ──────────────────────────────────────────────────────────
def _st(live_n=40, raw=0, drift_only=0, new_null=0):
    return {"live_n": live_n, "raw": raw, "drift_only": drift_only, "new_null": new_null}


def test_verdict_pass_when_raw_matches():
    assert vs.ttm_verdict(_st(raw=36)) == "PASS"           # 90% exactly


def test_verdict_flag_when_only_drift_explains_it():
    assert vs.ttm_verdict(_st(raw=18, drift_only=20)) == "FLAG"


def test_verdict_fail_below_threshold_even_after_drift():
    assert vs.ttm_verdict(_st(raw=0, drift_only=35)) == "FAIL"   # 87.5%


def test_verdict_fail_below_half():
    assert vs.ttm_verdict(_st(raw=8)) == "FAIL"                 # 20%


# ── search_candidates ────────────────────────────────────────────────────
def _search_inputs():
    live = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    good = [1.0, 2.0, 3.0, 9.0]       # matches 3 of 4 symbols (75%)
    weak = [1.0, 9.0, 9.0, 9.0]       # matches 1 of 4 (25%): below the 50% bar
    pct = [0.01, 0.02, 0.03, 0.04]    # matches all four only after x100
    raw = {s: {"R": {"goodField": good[i], "weakField": weak[i]},
               "M": {"pctField": pct[i], "label": "text"}}
           for i, s in enumerate(live)}
    return live, raw


def test_search_candidates_keeps_matches_over_half_and_drops_weak_ones():
    live, raw = _search_inputs()
    found = vs.search_candidates("fooTTM", live, raw, {})
    by_field = {(ep, k, scale): share for share, ep, k, scale, nn in found}
    assert by_field[("R", "goodField", 1)] == pytest.approx(0.75)
    assert not any(k == "weakField" for _, k, _ in by_field)


def test_search_candidates_finds_x100_variant_and_ranks_it_first():
    live, raw = _search_inputs()
    found = vs.search_candidates("fooTTM", live, raw, {})
    share, ep, k, scale, nn = found[0]
    assert (ep, k, scale, share) == ("M", "pctField", 100, 1.0)


def test_search_candidates_empty_when_nothing_reaches_half():
    live, raw = _search_inputs()
    for rows in raw.values():
        rows["R"].pop("goodField")
        rows["M"].pop("pctField")
    assert vs.search_candidates("fooTTM", live, raw, {}) == []


def test_search_candidates_applies_price_drift_for_price_driven_fields():
    live = {"A": 10.0, "B": 20.0}
    raw = {"A": {"R": {"peRatioTTM": 8.0}}, "B": {"R": {"peRatioTTM": 16.0}}}
    ratios = {s: {"price": 0.8, "ev": None} for s in live}
    found = vs.search_candidates("peRatioTTM", live, raw, ratios)
    assert [(ep, k, scale) for _, ep, k, scale, _ in found][0] == ("R", "peRatioTTM", 1)
    assert vs.search_candidates("returnOnEquityTTM", live, raw, ratios) == []


def test_verdict_fail_when_new_side_null_over_5_percent():
    assert vs.ttm_verdict(_st(raw=36, new_null=3)) == "FAIL"


def test_verdict_missing_and_na():
    assert vs.ttm_verdict(_st(new_null=40)) == "MISSING"
    assert vs.ttm_verdict(_st(live_n=0)) == "n/a"
