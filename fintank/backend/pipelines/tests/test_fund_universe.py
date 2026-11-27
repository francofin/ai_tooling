import csv
import io
import re

import pytest

from pipelines import pipeline_config as cfg
from pipelines.fund_universe import _aum, bucket_of, build_universe, company_ids

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
    assert detail["adrs_linked"] == 4          # DUPE now links too


def test_company_ids_second_listing_merges():
    sym, _, detail = company_ids(rows())
    assert sym["DUPE"] == sym["TWN.L"] == sym["TWN.PA"] == "FR0000000001"  # tie -> smallest
    assert detail["unlinked"] == [] and detail["adrs"] == 4


def test_bucket_of_is_stable():
    assert bucket_of("CA7800871021") == 40
    assert all(0 <= bucket_of(c) < 64 for c in ["a", "US0378331005", "CA7800871021"])


@pytest.mark.parametrize("name,dropped", [
    ("Vanguard Ultra-Short Bond ETF", False),
    ("BMO Ultra Short-Term Bond ETF", False),
    ("JPMorgan Ultra-Short Income ETF", False),
    ("ProShares UltraShort QQQ", True),
    ("ProShares UltraPro QQQ", True),
    ("ProShares Ultra QQQ", True),
    ("ProShares Short 20+ Year Treasury", True),
    ("ProShares Short QQQ", True),
    ("ProShares Short S&P500", True),
    ("Direxion Daily S&P 500 Bear 1X Shares", True),
    ("iShares Short Treasury Bond ETF", False),
    ("SPDR Bloomberg Short Term Corporate Bond ETF", False),
    ("Vanguard Short-Term Treasury ETF", False),
    ("PIMCO Enhanced Short Maturity Active ETF", False),
    ("iShares Short-Term National Muni Bond ETF", False),
    ("ProShares - Ultra QQQ", True),            # FMP's spelling
    ("Invesco S&P Ultra Dividend Revenue ETF", False),
    ("Innovator Equity Premium Income – Daily PutWrite ETF", False),
    ("Ninepoint Royal Bank HighShares ETF", True),
    ("Harvest Apple Enhanced High Income Shares ETF", True),
    ("GraniteShares 1.25x Long TSLA Daily ETF", True),
    ("Direxion Daily Semiconductor Bull 3X Shares", True),
    ("T-Rex 2X Long NVIDIA Daily Target ETF", True),
    # Long/short equity funds are ordinary funds, kept (owner decision 2026-11-26)
    ("First Trust Long/Short Equity ETF", False),
    ("Harbor Long-Short Equity ETF", False),
    ("BMO Long Short Canadian Equity ETF", False),
    ("Franklin LONG/SHORT Equity ETF", False),
    # ...unless something else in the name marks them leveraged
    ("Acme 2x Long/Short Equity ETF", True),
    ("Acme Leveraged Long/Short ETF", True),
])
def test_leveraged_pattern_names(name, dropped):
    assert bool(re.search(cfg.FUND_LEVERAGED_PATTERN, name, re.I)) is dropped


@pytest.mark.parametrize("v", ["nan", "inf", "-inf", "", "x"])
def test_aum_non_finite_is_zero(v):
    assert _aum({"marketCap": v}) == 0.0


def _line(symbol, name, isin, exchange, adr=False):
    return {"symbol": symbol, "companyName": name, "isin": isin, "exchange": exchange,
            "isEtf": "false", "isFund": "false", "isAdr": "true" if adr else "false"}


def test_company_ids_adr_links_past_cdr_and_own_isin_abroad():
    tsmc = "Taiwan Semiconductor Manufacturing Company Limited"
    extra = [
        _line("TSFA.F", tsmc, "US8740391003", "FSX"),     # the ADR's own ISIN abroad
        _line("UTSD.SI", tsmc, "SGXE59874987", "SES"),    # a depositary line
        _line("TSMWF", tsmc, "TW0002330008", "OTC"),
        _line("ASML.TO", "ASML Holding N.V.", "CA0449281090", "TSX"),  # CDR
        _line("NOVO.TO", "Novo Nordisk A/S", "CA67010P1018", "TSX"),   # CDR
    ]
    sym, isin, detail = company_ids(rows() + extra)
    assert sym["TSM"] == "TW0002330008"
    assert sym["ASML"] == "NL0010273215"
    assert sym["NVO"] == "DK0062498333"
    assert sym["DUPE"] == "FR0000000001" and detail["unlinked"] == []
    assert detail["adrs_linked"] == 4


def test_company_ids_majority_isin_wins_tie_links_smallest():
    base = [_line("X", "Xco", "US1111111111", "NYSE", adr=True),
            _line("X.DE", "Xco", "DE0000000001", "XETRA"),
            _line("X.F", "Xco", "DE0000000001", "FSX"),
            _line("X2.DE", "Xco", "DE0000000002", "XETRA")]
    sym, _, _ = company_ids(base)
    assert sym["X"] == sym["X2.DE"] == "DE0000000001"
    sym, _, detail = company_ids(base[:2] + base[3:])
    assert sym["X"] == "DE0000000001" and detail["unlinked"] == []


def test_company_ids_share_classes_merge_when_in_index():
    rs = [_line("GOOGL", "Alphabet Inc.", "US02079K3059", "NASDAQ"),
          _line("ABEA.DE", "Alphabet Inc.", "US02079K3059", "XETRA"),
          _line("GOOG", "Alphabet Inc.", "US02079K1079", "NASDAQ")]
    sym, isin, detail = company_ids(rs, common_symbols={"GOOG", "GOOGL"})
    assert sym["GOOG"] == sym["GOOGL"] == "US02079K3059"   # most lines
    assert isin["US02079K1079"] == "US02079K3059"
    assert detail["merged_groups"] == 1 and detail["merged_isins"] == 2
    assert detail["north_american_merge"] is True


def test_company_ids_north_american_unmerged_without_index_lists():
    rs = [_line("GOOGL", "Alphabet Inc.", "US02079K3059", "NASDAQ"),
          _line("GOOG", "Alphabet Inc.", "US02079K1079", "NASDAQ")]
    sym, _, detail = company_ids(rs)
    assert sym["GOOG"] == "US02079K1079" and sym["GOOGL"] == "US02079K3059"
    assert detail["north_american_merge"] is False and detail["merged_groups"] == 0


def test_company_ids_us_preferred_stays_separate():
    rs = [_line("PSA", "Public Storage", "US74460D1090", "NYSE"),
          _line("PSA-PF", "Public Storage", "US74460W6856", "NYSE"),
          _line("HBANP", "Public Storage", "US4461507083", "NASDAQ"),
          _line("TRTN-PA", "Public Storage", "BMG9078F1077", "NYSE")]  # foreign ISIN, US-listed
    sym, _, _ = company_ids(rs, common_symbols={"PSA"})
    assert sym["PSA"] == "US74460D1090"
    assert sym["PSA-PF"] == "US74460W6856"
    assert sym["HBANP"] == "US4461507083"
    assert sym["TRTN-PA"] == "BMG9078F1077"


def test_company_ids_european_preference_shares_merge():
    rs = [_line("HEN.DE", "Henkel AG & Co. KGaA", "DE0006048408", "XETRA"),
          _line("HEN3.DE", "Henkel AG & Co. KGaA", "DE0006048432", "XETRA"),
          _line("HEN3.F", "Henkel AG & Co. KGaA", "DE0006048432", "FSX")]
    sym, _, _ = company_ids(rs)
    assert sym["HEN.DE"] == sym["HEN3.DE"] == "DE0006048432"


def test_company_ids_dual_listing_merges():
    rs = [_line("CCL.L", "Carnival Corporation & plc", "GB0031215220", "LSE"),
          _line("POH1.DE", "Carnival Corporation & plc", "GB0031215220", "XETRA"),
          _line("0EV1.L", "Carnival Corporation & plc", "BMG2004J1036", "LSE")]
    sym, _, _ = company_ids(rs)
    assert sym["CCL.L"] == sym["0EV1.L"] == "GB0031215220"


def test_company_ids_mislabelled_line_does_not_bridge():
    rs = [_line("SEA.TO", "Seabridge Gold Inc.", "CA8119271028", "TSX"),
          _line("SAN.MX", "Seabridge Gold Inc.", "ES0113900J37", "MEX"),   # FMP mislabel
          _line("SAN.MC", "Banco Santander, S.A.", "ES0113900J37", "BME"),
          _line("BSD2.DE", "Banco Santander, S.A.", "ES0113900J37", "XETRA")]
    sym, _, _ = company_ids(rs, common_symbols={"SEA.TO"})
    assert sym["SEA.TO"] == "CA8119271028"
    assert sym["SAN.MX"] == sym["SAN.MC"] == "ES0113900J37"


def test_company_ids_owner_name_tie_keeps_own_id():
    rs = [_line("A.L", "Aco", "GB0000000009", "LSE"),
          _line("A.DE", "Bco", "GB0000000009", "XETRA"),
          _line("A2.L", "Aco", "GB0000000008", "LSE")]
    sym, _, _ = company_ids(rs)
    assert sym["A.L"] == sym["A.DE"] == "GB0000000009"
    assert sym["A2.L"] == "GB0000000008"


def test_company_ids_blank_names_never_group():
    rs = [_line("N1.L", "", "GB0000000011", "LSE"),
          _line("N2.L", "", "GB0000000012", "LSE"),
          {**_line("N3.L", "", "GB0000000013", "LSE"), "companyName": None}]
    sym, _, detail = company_ids(rs)
    assert sym == {"N1.L": "GB0000000011", "N2.L": "GB0000000012", "N3.L": "GB0000000013"}
    assert detail["merged_groups"] == 0


def test_company_ids_row_order_does_not_matter():
    rs = rows() + [_line("HEN.DE", "Henkel AG & Co. KGaA", "DE0006048408", "XETRA"),
                   _line("HEN3.DE", "Henkel AG & Co. KGaA", "DE0006048432", "XETRA")]
    a = company_ids(rs)
    b = company_ids(list(reversed(rs)))
    assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2]


def test_company_ids_largest_groups_reported():
    rs = [_line(f"T{i}.MI", "Telecom Italia S.p.A.", f"IT000000000{i}", "MIL") for i in range(3)]
    _, _, detail = company_ids(rs)
    assert detail["largest_groups"] == [
        {"name": "Telecom Italia S.p.A.",
         "isins": ["IT0000000000", "IT0000000001", "IT0000000002"]}]
