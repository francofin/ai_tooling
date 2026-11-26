# Fund finder: "Include leveraged funds" toggle (short design)

Date: 2026-11-26. Size: small-to-medium (pipeline, Django, page). No deadline;
ships after the 2026-11-28 first publish, ideally before a following weekly run.

## Intent

Canadian "Enhanced" ETFs (Hamilton, Harvest: HCAL.TO, HUTS.TO, HHLE.TO, CDAY.NE...)
borrow about 25% to hold about 125% of an underlying ETF. They are popular, but
the lookup drops every fund whose holdings add up to more than 110%
(`FUND_LEVERAGE_COVERAGE_PCT`), so someone who owns HCAL never finds it. The
owner wants them available behind a checkbox, off by default.

## Goals / non-goals / anti-goals

- Goal: with "Include leveraged funds" ticked, the 14 funds the >110% rule removes
  (2026-11-23 data) appear, ranked at their real exposure and marked with their
  leverage (e.g. "1.24x").
- Goal: unticked (the default), results are exactly as today. The stock-page
  "funds holding this stock" list never shows them.
- Non-goal: daily 2x/3x and inverse funds (TQQQ, SOXL...). They are dropped by
  name before fetching and hold mostly swaps; possible later under the same
  checkbox.
- Anti-goal: leveraged funds showing up when the box is unticked, including
  during the deploy window.

## Approaches

1. **Flag and filter (picked):** the pipeline keeps funds between 110% and 150%
   coverage, flags them `leveraged`, and Django hides them unless asked.
2. Scale them to 100% and always show them: rejected by the owner in favour of
   a user choice.
3. Keep dropping them: the status quo, rejected.

## Design

- **Pipeline (`fund_lookup.py`, `thresholds.py`):**
  - Funds with coverage over `FUND_LEVERAGE_COVERAGE_PCT` (110) and up to a new
    `FUND_LEVERAGE_MAX_PCT` (150) are no longer dropped. Their exposure rows are
    kept at the real weight.
  - `funds.parquet` gets a boolean `leveraged` column (the existing
    `coverage_pct` gives the multiple).
  - Over 150% is still dropped as bad data. The 14 on 2026-11-23 sit at about
    120–128%.
  - `detail["dropped_leveraged_holdings"]` keeps listing only the >150% drops;
    a new `detail["leveraged_kept"]` lists the flagged funds.
- **Django (`analyzer_utils/fund_finder.py`, `views.py`):**
  - `parse_query` reads `leveraged=1` (anything else means off).
  - `_query` skips funds with `leveraged` true unless it is on.
  - The flag is part of the query cache key.
  - Rows carry `leveraged` and `coverage_pct`.
  - A missing column (an old parquet) counts as not leveraged.
  - `get_funds_holding` (stock page) never sets it.
- **Page:**
  - A checkbox "Include leveraged funds", synced to the URL as `leveraged=1` in
    `query.mjs`.
  - Flagged rows get a small badge with the multiple ("1.24x").
  - When ticked, a footnote: "Leveraged funds borrow to hold more than 100% of
    their assets; weights shown are their full exposure."
- **Deploy order (protects the anti-goal):** one PR. The merge deploys the web
  first, which tolerates old data. Then `cdk deploy` puts the pipeline change in
  the next weekly run.
- **Tests:** pipeline (110–150% kept and flagged, >150% dropped, ≤110% unflagged);
  Django (hidden by default, shown with `leveraged=1`, cache key differs, old
  parquet without the column); `query.mjs` round-trip of `leveraged`.

## Left to the builder

- Whether the fund-finder checks (fund count, TD cross-check) need adjusting for
  the 14 extra funds. They should not, but run them on the 2026-11-23 data.
- Checkbox placement: next to "Funds listed in".
