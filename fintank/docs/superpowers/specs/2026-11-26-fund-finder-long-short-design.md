# Fund finder: keep long/short equity ETFs (short design)

Date: 2026-11-26. Size: small change. Deadline: deployed before the Sat 2026-11-28 lean run (first `fund_finder` publish).

## Intent

Long/short equity ETFs are ordinary funds people own; the leveraged/inverse
name filter drops them only because their names contain "short". The owner
reviewed the 29 long/short ETFs on 2026-11-26 and decided to keep the 7 that
would actually appear: FTLS, CLSE, ORR, ZLSU.TO, ZLSC.TO, FLSE.TO, FTLS.TO.

## Goals / non-goals

- Goal: those funds reach the fund finder, ranked on their long holdings as published.
- Non-goal: showing short positions ("funds betting against a stock"). Measured
  2026-11-26 and parked (thin Canadian coverage, 0.1–0.8% positions, many funds
  short mechanically, BTAL data broken). Recorded under "Other ideas" in
  `docs/next_stable_features.md`.
- Anti-goal: letting any leveraged or inverse fund through.

## Approaches

1. **Rule (picked):** in `FUND_LEVERAGED_PATTERN`, the `short` alternative no longer
   matches when preceded by "long " / "long-" / "long/". Over the 17,244 ETF names in
   the 2026-11-23 profile data this frees exactly 27 names, all long/short funds from
   the owner's 29-fund review (the other 2, PFIA.TO and HELS, were never dropped by
   name), and drops no new ones. 20 of the 27 still drop out (below the AUM floor, no
   holdings, or top-10-only), so the 7 above are what reach the page. New long/short
   funds are handled the same way.
2. Fixed allow-list of the 7 symbols: no surprises, but every new long/short
   fund needs a code change. Rejected for that.
3. Scale the longs to 100%: not needed. Re-ranking real searches with the 7
   added, none comes near a top 10 (best: ZLSC.TO #54 for SHOP.TO, #65 for RY.TO).

## Design

- `pipeline_config.py`: add `(?<!long/)(?<!long-)(?<!long )` before `\bshort\b`
  in the last alternative; comment why.
- Leveraged names stay caught by their own alternatives (multipliers,
  "leveraged", "inverse", bear/bull, ultra...).
- Shorts (negative weights) keep being dropped by `FUND_MIN_HOLDING_PCT`; longs
  count as published. No change to `fund_lookup.py`, Django or the page.
- Tests: add the long/short spellings to `test_leveraged_pattern_names` as kept
  (False), and a leveraged long/short name (e.g. "2x Long/Short ...") as dropped.
- Deploy: PR, merge, then `cdk deploy` with all four flags before Saturday.

## Left to the builder

Nothing beyond the test names.
