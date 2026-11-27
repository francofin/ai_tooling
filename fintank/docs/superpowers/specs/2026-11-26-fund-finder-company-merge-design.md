# Fund finder: one company id for all lines of a company (short design)

Date: 2026-11-26. Size: small change (one pipeline function, its tests, one check).
Ships stacked on `feature/fund-finder-leveraged-toggle`; merged and CDK-deployed
after the owner approves the Sat 2026-11-28 publish, before the 2026-12-05 run.

## Intent

Someone who picks a stock wants every fund that owns the company, whichever line
the fund holds. Today the company id is the ISIN of one line, so share classes and
dual listings split: GOOGL finds 647 funds but 767 hold Alphabet; CCL.L (Carnival
plc) finds 16 of 398; ROG.SW finds 0 of 293 Roche holders. The owner reviewed the
131 multi-candidate ADR links on 2026-11-26 (24 High rows: Carnival, Henkel, Roche,
Sartorius, Stora Enso, Publicis, Wise, Schaeffler...) and decided: **merge all lines
of the same company into one**.

## Goals / non-goals / anti-goals

- Goal: one company id per company across share classes (GOOG/GOOGL, HEN/HEN3,
  H/A shares, Thai NVDRs), dual listings (Carnival plc/Corp, Rio plc/Ltd) and ADRs.
  A fund holding two lines counts their combined weight.
- Owner decision: **US and Canadian preferreds stay separate.** A preferred is closer
  to a bond; picking PSA must not bring in preferred-income ETFs. European and
  Brazilian preference shares (BMW3, HEN3, PETR4) do merge: they trade like ordinary
  stock and broad funds hold them.
- Non-goal: Canadian depositary receipts (BRK.TO, GOOG.TO) — they are not in an index
  list, so they stay separate (BRK-B keeps 434, not 461). Possible later.
- Non-goal: any Django or page change. Ids are opaque there already.
- Anti-goal: merging two different companies. FMP mislabels some rows (SAN.MX,
  Banco Santander's ISIN, is named "Seabridge Gold Inc."); one bad label must never
  join two companies.

## Approaches

1. **Merge in `fund_universe.company_ids` (picked).** The weekly build already gives
   every line a company id there; grouping lines by company gives one id, and
   `build_lookup` already sums weights per (company, fund, via). Django unchanged.
2. Expand picks to several ids at query time in Django: more code, bigger caches,
   weights summed per query. No gain over 1.
3. Hand-kept merge list: 100+ pickable stocks need it and it goes stale. Rejected.

## Design

`company_ids(bulk_rows, common_symbols)` in `pipelines/fund_universe.py`:

1. **Lines:** non-ETF, non-fund rows with an ISIN (as today).
2. **Owner name per ISIN:** the `companyName` most of its listings carry. A tie means
   no owner: the ISIN keeps its own id. (Stops SAN.MX joining Seabridge.)
3. **Eligible to merge:** an ISIN joins its owner's group when
   - any listing is an ADR (`isAdr`), or
   - it is not North American, i.e. the ISIN does not start with US/CA **and** no
     listing is on a US/CA main exchange (`FUND_US_EXCHANGES + FUND_CA_EXCHANGES`), or
   - it is North American and at least one listing is in `common_symbols`: the
     union of the pipeline's US and Canadian index constituent lists (S&P 500,
     Nasdaq, Russell 2000, Russell Micro Cap, TSX Composite, TSX Small Cap). Index
     lists hold common shares only, so preferreds (PSA-PF, HBANP, AGNCN, TD-PFI.TO,
     TRTN-PA) and unidentified OTC lines (TDBKF) stay separate.
   An ineligible ISIN keeps its own id, exactly as today.
4. **Canonical id** of a group: the member ISIN with the most listings; tie → the
   smallest ISIN string. Deterministic for a given input.
5. Every symbol and ISIN of a member maps to the canonical id. This replaces the
   ADR vote; `detail` keeps `adrs`, `adrs_linked` (ADR whose id is not its own
   ISIN) and `unlinked`, so the existing `fund_finder.adr_pairs` (TSM, ASML, NVO)
   and `fund_finder.adr_links` checks keep working.
6. New detail: `merged_groups` (groups with ≥2 ISINs), `merged_isins`, and
   `largest_groups` (top 10 by member count: name, members) for review.

`build_fund_finder` passes `common_symbols` from the run's constituent files. If
they are missing, North American lines stay unmerged (safe fallback) and detail
says so; the build does not fail.

Check: `fund_finder.company_merge`, WARN-only, WARN when any group has more than
`FUND_MERGE_MAX_ISINS = 8` members (a sign of a bad name bridge), else PASS with
the group count.

## Measured on the 2026-11-23 data (prototype)

2,280 merged groups (4,887 ISINs). Pickable stocks gaining funds: 117 (using the
site's stock list as the index-list proxy); none lose. GOOG/GOOGL 565/647 → 767,
FOXA 407 → 432, CCL.L 16 → 398, ROG.SW 0 → 293, BMW3.DE 0 → 183, HEN.DE 174 → 201,
TSM 205 → 347. Unchanged: PSA 375, TD.TO 288, RY.TO 279, SEA.TO 81, SAN.MC 253,
ASML 422. Largest group 6 (Telecom Italia: ordinary + savings + ADRs).

## Tests (pytest, `pipelines/tests`)

Share classes merge (GOOG/GOOGL in `common_symbols`); US preferred not in the index
list stays separate; a mislabelled ISIN (minority name) doesn't bridge; tie on owner
name keeps its own id; dual listing (GB + BM ISINs, same name) merges; ADR joins its
group and counts as linked; canonical id deterministic and stable under row order;
no `common_symbols` → North American lines unmerged; `build_lookup` sums two lines
of one company held by one fund; the new check WARNs above 8 members.

## Left to the builder

How `build_fund_finder` reads the constituent files (paths via
`constituents_path`), test names, detail field layout.
