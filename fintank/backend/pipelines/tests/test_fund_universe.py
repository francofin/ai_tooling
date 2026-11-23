import csv
import io

from pipelines.fund_universe import bucket_of, build_universe, company_ids

from .helpers import load_fixture


def rows():
    return list(csv.DictReader(io.StringIO(load_fixture("profile_bulk_funds", "csv"))))


def test_universe_filters():
    funds, detail = build_universe(rows())
    syms = {f["symbol"] for f in funds}
    for s in "XIU.TO XEQT.TO VEA VTI AGG SHY VGSH XUS.TO IVV".split():
        assert s in syms
    for s in "TQQQ SH TINY.TO SPYX FXAIX RY AAPL".split():
        assert s not in syms
    assert "ProShares UltraPro QQQ" in detail["dropped_leveraged"]
    assert detail["dropped_floor"] == 1
    assert detail["funds"] == len(funds)


def test_series_collapse():
    funds, detail = build_universe(rows())
    by = {f["symbol"]: f for f in funds}
    assert by["ZWC.TO"]["series"] == ["ZWC-T.TO"]
    assert by["BTCQ.TO"]["series"] == ["BTCQ-U.TO"]
    assert "ZWC-T.TO" not in by and "BTCQ-U.TO" not in by
    assert by["VTI"]["series"] == []
    assert by["VTI"]["region"] == "us" and by["XIU.TO"]["region"] == "ca"
    assert detail["collapsed_series"] == 2


def test_company_ids_interlisted():
    sym, _, _ = company_ids(rows())
    assert sym["RY"] == sym["RY.TO"] == "CA7800871021"


def test_company_ids_adr_links():
    sym, isin, detail = company_ids(rows())
    assert sym["TSM"] == "TW0002330008"
    assert sym["ASML"] == "NL0010273215"
    assert sym["NVO"] == "DK0062498333"
    assert isin["US8740391003"] == "TW0002330008"
    assert detail["adrs_linked"] == 3


def test_company_ids_ambiguous_adr_unlinked():
    sym, _, detail = company_ids(rows())
    assert sym["DUPE"] == "US0000000001"
    assert detail["unlinked"] == ["DUPE"]
    assert detail["adrs"] == 4


def test_bucket_of_is_stable():
    assert bucket_of("CA7800871021") == 40
    assert all(0 <= bucket_of(c) < 64 for c in ["a", "US0378331005", "CA7800871021"])


import re

import pytest

from pipelines import pipeline_config as cfg
from pipelines.fund_universe import _aum


@pytest.mark.parametrize("name,dropped", [
    ("Vanguard Ultra-Short Bond ETF", False),
    ("BMO Ultra Short-Term Bond ETF", False),
    ("JPMorgan Ultra-Short Income ETF", False),
    ("ProShares UltraShort QQQ", True),
    ("ProShares UltraPro QQQ", True),
    ("ProShares Ultra QQQ", True),
])
def test_leveraged_pattern_names(name, dropped):
    assert bool(re.search(cfg.FUND_LEVERAGED_PATTERN, name, re.I)) is dropped


@pytest.mark.parametrize("v", ["nan", "inf", "-inf", "", "x"])
def test_aum_non_finite_is_zero(v):
    assert _aum({"marketCap": v}) == 0.0
