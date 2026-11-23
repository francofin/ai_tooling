# Fund finder: design

Date: 2026-11-22. Status: draft for the owner's approval.
Working notes with the history of each decision: `fintank/docs/next_stable_features.md` (untracked, main folder), "Feature 3".

## Intent

A reader, mostly Canadian, wants exposure to particular companies and is looking for ETFs that give them the most of those names. They pick the companies (and, optionally, companies they do **not** want), and the page lists the ETFs that hold the most of the picks, measured by combined weight.

Why: it is the third feature FMP Ultimate makes possible, after the analyst view and the earnings hub. It answers a question Canadian investors ask often ("which ETF gives me the most RY and TD?") that broker screeners answer poorly.

**Success:** for a typical pick (a few large US or Canadian names), the top results are the funds an informed investor would name, the weights match the issuers' published holdings within the usual few days of lag, and the page answers in about a second.

## Goals (v1)

1. **Exposure search.** The reader picks one or more stocks to include and, optionally, one or more to exclude. Results are ETFs that hold at least one included stock and none of the excluded ones, ranked by the **combined weight** of the included stocks, highest first.
2. **Listing market chosen first.** A dropdown (Canadian-listed, US-listed, both) that the reader must set before results appear. No default.
3. **Funds of funds counted correctly.** Weight held through an underlying ETF counts, for ranking and for exclusion.
4. **Each result shows** its weight in every included stock, the combined weight, expense ratio (MER), AUM, listing exchange and currency, and the date the holdings were fetched.
5. **Weekly data**, built and checked by the AWS pipeline before anything is published, like every other dataset.

## Non-goals (v1)

- **Mutual funds**: phase 2. US mutual funds are in FMP (`profile-bulk` flags them with `isFund`, and holdings exist, e.g. FXAIX), but the owner wants v1 to focus on ETFs.
- **Canadian mutual funds**: not available at all. FMP has no FundSERV-coded funds (RBF556, Mawer return nothing). The page says so.
- **Fund screener** (filtering all funds on fee, AUM, returns, weighted P/E and so on): phase 2.
- **Weight caps** ("less than 1% in SHOP") and **sector or country filters** ("less than 20% in Canadian banks"): phase 2. They need per-fund sector and country weights, which belong with the screener.
- Picking ETFs, sectors or themes as the thing you want exposure to. v1 picks are stocks only.

## Anti-goals

- **A breadth bonus.** The owner decided on pure combined weight: if the picks are RY, TD and SHOP, a fund with only RY at 8% ranks above one holding all three at 2% each (6%). Each result shows the per-name weights, so the reader can see why.
- **Wrong numbers for funds of funds.** FMP's country-weights endpoint shows XEQT.TO as 85.8% Canada (really about 25%). Nothing on this page may come from that kind of top-level-only figure.
- **Missing a fund because of the listing symbol.** A reader who picks RY must also find funds that list it as RY.TO, and the other way round.
- **Advice.** Like the earnings notes, the page says plainly that it is information, not a recommendation.
- **Slowing the weekly run or the server.** No large query runs while a reader waits; the server's database is not used.

## Constraints

- FMP `stable` only (v3 is dead). Every FMP URL is built through the pipeline's existing stable helpers.
- The pipeline runs on AWS (ECS Fargate + Step Functions) and publishes to S3 bucket `thetradingfloor` only after its checks. The site (Lightsail, Docker Compose) reads S3 and caches in Redis. The pipeline cannot reach the server's Postgres.
- Server: one 4 GB instance running Caddy, web, api, worker, Redis and Postgres. The data must not be loaded whole into each API worker.
- A new dataset follows the existing pattern: a stage in `pipelines/stock_pipeline.py`, listed in `runner.py`, its outputs registered in `pipelines/outputs.py` (`DATASET_ORDER`, `collect_outputs`), minimum counts in `thresholds.MIN_COUNTS`, checks in `pipelines/checks.py`.
- The site stays free until the owner has FMP's Data Display and Licensing Agreement. This page displays FMP holdings data, so the licence covers it too.
- Tests never call live FMP; they use saved fixtures. The owner pushes, opens PRs and starts servers.

## What the data looks like (probed 2026-11-22)

- **Universe.** `profile-bulk` (4 CSV parts, ~96,000 rows; the weekly run already downloads it) has `isEtf`, `isFund`, `isActivelyTrading`, `exchange`, `marketCap`, `isin`, `currency`. `marketCap` tracks AUM for ETFs (SPY $729B, XIU.TO C$22B). Active ETFs on US exchanges (AMEX, NASDAQ, NYSE, CBOE) and Canadian (TSX, NEO), after removing leveraged/inverse funds by name, the AUM floor and one per currency series: **about 2,380 US and about 1,010 Canadian, ~3,400 total**.
- **`etf/holdings`** (one call per fund). Rows have `asset` (symbol), `name`, `isin`, `weightPercentage`, `updatedAt`. Weights sum to 100.
  - Holdings use the **home-market symbol**, even in US funds: VEA lists `RY.TO`, `TD.TO`, `SHOP.TO`, Japanese names as `9501.T`, and so on. VEA also carries a stray `SHOP` row at 0.0000046%.
  - **FMP already looks through funds of funds:** XEQT.TO returns 8,285 underlying stocks (AAPL 3.35%, RY.TO 1.97%), not its 4–6 ETFs. Whether every fund of funds is returned this way is not known; see "Look-through" below.
  - Rows with an empty `asset` are cash, futures, swaps and bonds. AGG returns 13,560 rows, all with an empty `asset`.
  - `updatedAt` is FMP's fetch time (all 2026-11-22 when probed), not the fund's holdings date.
- **ISIN joins the listings of one company.** RY (NYSE) and RY.TO share `CA7800871021`; the same holds for TD, SHOP and ENB. CDRs are separate securities with their own ISIN (AAPL.NE `CA03785Y1007`), which is correct: a CDR is not a holding of Apple.
- **`etf/info`** gives expense ratio, AUM, NAV, asset class, issuer and inception date (probed 2026-11-21).
- **`etf/asset-exposure`** lists the funds holding a symbol (1,107 for RY.TO, 3,849 for AAPL): used only as a cross-check.

## Approaches considered

- **A. Weekly pipeline stage plus a precomputed lookup in S3 (chosen).** The run fetches holdings for every fund in the universe, resolves look-through, and writes (1) a per-fund table and (2) a lookup from each company (ISIN) to the funds that hold it, with weights. Django reads only the lookup entries for the picks, through Redis. Follows the existing S3/Redis/checked-publish pattern; undo is the existing `rollback`; no query runs over the full holdings while a reader waits.
- **B. Live from FMP `etf/asset-exposure` at request time.** Rejected: no look-through, results depend on FMP during the request, nothing is checked before readers see it. Kept as the cross-check for A.
- **C. Holdings loaded into the server's Postgres.** Rejected: the pipeline can't reach the database, so C is A plus a bulk loader; it puts millions of rows weekly into the 4 GB server and its nightly backups, loses the S3 versioning that makes `rollback` work, and adds a table to move when the database becomes managed. Its advantage (new questions as SQL) is small because the phase 2 screener works on one row per fund, which fits in memory.

**The owner chose A on 2026-11-22**, and asked that "holds X but not Y" be in v1.

## Design

### Decided by the owner

- Goal is exposure; ranking is pure combined weight (no breadth bonus).
- ETFs only in v1; mutual funds in phase 2; Canadian mutual funds not covered.
- Listing market is picked first from a dropdown (Canada, US, both); no default.
- Approved count cuts: an AUM floor (for example US $100M, CA $25M), drop leveraged and inverse funds, keep one series among CAD, USD and hedged variants. Measure the final counts in the dry run.
- Approach A.
- Exclusion ("but not Y") in v1.
- Fund screener later.
- **ADRs are linked to the home-market share** (2026-11-22). Picking TSM also finds funds holding 2330.TW, and picking ASML.AS also finds QQQ's ASML ADR; a fund holding both adds the two weights.
- **Bandwidth:** FMP allows 170 GB per 30 days and 3,000 calls a minute; 9.83 GB was used when asked (2026-11-22). The new stage's estimated ~1 GB a week fits, so holdings refresh weekly.

### My calls (the owner can overrule any of these)

1. **No minimum weight.** Any holding above zero counts as "holds" for inclusion and exclusion. Tiny weights sink in the ranking, and the per-name columns show them. One exception: drop holding rows below 0.001% before building the lookup, so a stray row like VEA's `SHOP` at 0.0000046% neither appears as exposure nor excludes a fund. (Thresholds go in `pipelines/thresholds.py`.)
2. **Key everything by a company id, normally the ISIN.** The company id is the ISIN of the home-market share. Shares listed in several markets already share one ISIN (RY and RY.TO). An ADR has its own US ISIN, so it is linked to the home share: for each `profile-bulk` row with `isAdr` true, find the non-ADR, non-fund rows with exactly the same `companyName` outside the US exchanges. If there is exactly one distinct ISIN among them, the ADR's company id is that ISIN; otherwise the ADR keeps its own ISIN (unlinked) and the dry run lists it. Probed pairs that must link: TSM → 2330.TW, ASML → ASML.AS, NVO → NOVO-B.CO. `profile-bulk` flags 2,190 ADRs; the dry run reports how many linked. Below, "ISIN" in the lookup means this company id. A pick is resolved to a company id through the universe data (`profile-bulk`'s `symbol → isin`), so RY and RY.TO find the same funds. When a holding row has no ISIN, fall back to its `asset` symbol mapped through `profile-bulk`; rows that resolve to neither are kept in the per-fund holdings (they count toward weight coverage) but are not in the lookup.
3. **Look-through, one level, only where needed.** For funds FMP already looks through (XEQT.TO), our data does not say which underlying ETF a weight came from, so `via` is blank for them; `via` is filled only for funds we expand ourselves. After fetching, any holding whose ISIN or symbol is itself a fund in the universe (an ETF holding another ETF) is replaced by that fund's holdings scaled by its weight. FMP already does this for XEQT.TO, so most funds of funds need nothing. One level is enough for Canadian asset-allocation ETFs; a deeper chain is logged, not expanded. Holdings of an underlying ETF outside the universe (for example below the AUM floor) are still fetched for the look-through when needed, and those calls count in the stage's numbers.
4. **Exclusion uses look-through too.** A fund that holds SHOP only through an underlying ETF counts as holding SHOP and is removed.
5. **Universe built in the pipeline from `profile-bulk`**, which the run already downloads. Filters, all in `pipeline_config.py` or `thresholds.py` so they can be tuned:
   - `isEtf` true, `isActivelyTrading` true, exchange in the US or Canadian list;
   - AUM floor on `marketCap` (US $100M, CA $25M);
   - leveraged/inverse removed by name, with care: "2x", "3x", "-1x", "Ultra", "UltraPro", "Leveraged", "Inverse", "Bear", "Bull", "Daily" (but not "Daily Income"), "Short" (but not "Short-Term", "Short Duration", "Short Maturity"); the dry run lists every dropped name for a once-over;
   - one series per fund: Canadian `-U.TO` (USD series) and `-T.TO`-style variants collapse to the base symbol, keeping the largest AUM; hedged and unhedged versions are different portfolios in currency terms but hold the same stocks, so they collapse too, and the result shows "also: XUS-U.TO, XUH.TO".
6. **Collapse identical portfolios in results, within one listing market only.** Funds listed in the same market, from the same issuer, whose lookup weights for every pick agree within 0.01 pp show as one result with an "also available as" list (the largest AUM is shown first). This covers series the name rules miss. A Canadian wrapper of a US fund (XUS.TO holding IVV) is **never** merged with the US fund: currency, MER and listing are what a Canadian reader is choosing between, so with `listed=both` both appear as separate rows.
7. **Fund details.** AUM from `profile-bulk` each week. MER, issuer and asset class from `etf/info`, fetched in **full runs only** (monthly), because they rarely change. A fund with no `etf/info` row shows "—".
8. **Holdings date.** `updatedAt` is fetch time, so the page says "holdings fetched <date>", not "as of".
9. **Limits on a query:** up to 10 included and 10 excluded stocks; results capped at the top 100 funds. Ties are broken by AUM, largest first.
10. **Where it lives:** a new Pages Router page `/fund-finder` (`src/pages/fund-finder.js`, legacy components like the rest of the financial UI), and a "Funds that hold this" link on `stock-data/[ticker]` that opens `/fund-finder` with that stock picked. The stock picker reuses the existing ticker search (`src/componentsLegacy/Comparison/TickerPicker.js` or `SearchBar.js`, whichever supports several picks).
11. **Checks are WARN-only for the first three runs**, like index attribution, so a bug in the new dataset can't block prices and fundamentals. Then switch them to FAIL.

### Pipeline

New stage `fetch_fund_holdings`, in both `LEAN_STAGES` and `FULL_STAGES`, after `refresh_constituents` (it reuses the `profile-bulk` rows that stage already downloads; it must not download them again), checkpointed like other fetch stages. A new build stage `build_fund_finder` writes the outputs. Rough cost: about 3,400 `etf/holdings` calls a week plus look-through extras, and about 3,400 `etf/info` calls in full runs. **Bandwidth fits:** FMP allows 170 GB per 30 days (9.83 GB used on 2026-11-22) and 3,000 calls a minute. Still report the stage's bytes in the run email like other stages: large funds return thousands of rows (XEQT.TO 8,285, AGG 13,560), and FMP's monthly bandwidth cap has been hit before (2026-10-18). Payload sizes probed 2026-11-22: XIU.TO 16 KB, VTI 0.85 MB, VEA 0.94 MB, XEQT.TO 2.0 MB, AGG 3.4 MB. A rough guess is 0.3 MB a fund on average, so about 1 GB a week (the 2026-10-24 lean run downloaded 0.7 GB in total). If usage ever gets tight, the owner's order of cuts is: first skip funds whose previous fetch had no rows with an `asset` (bond funds, the heaviest payloads) and recheck them only in full runs; then refresh holdings monthly.

Outputs (new dataset `fund_finder`, published after `attribution` in `DATASET_ORDER`):

| Key | Content |
|---|---|
| `fund_data/funds.parquet` | One row per fund: symbol, name, exchange, region (`ca`/`us`), currency, AUM, MER, issuer, asset class, holdings fetch date, series group ("also available as"), holdings row count, weight coverage (% of weight resolved to an ISIN). |
| `fund_data/exposure/<bucket>.parquet` | The lookup: ISIN, fund symbol, weight (after look-through), `via` (the underlying ETF, or blank when held directly). Split into a fixed number of buckets by a stable hash of the ISIN (64 to start), so a request reads only the buckets for its picks. |
| `fund_data/isin_map.parquet` | symbol → company id, name, exchange, `is_adr`, for every stock listing whose company appears in the lookup (all listings that share a company id, ADRs included), so Django resolves picks without another source. |

Checks (`pipelines/checks.py`, WARN-only at first):
- fund count at least a minimum (`MIN_COUNTS["fund_finder.funds"]`, set from the dry run, about 90% of it);
- fetch failure rate (same rule as other fetch stages; a fund that fails keeps last week's holdings);
- each fund's weights sum to 90–110% before look-through (WARN on the funds outside);
- **cross-check with `etf/asset-exposure`** for five fixed symbols (RY.TO, TD.TO, SHOP.TO, AAPL, MSFT): of the funds in our universe that FMP lists, at least 95% are in our lookup, and the weights agree within 0.5 pp for at least 95% of them. Five extra calls a run.
- an ADR link check: the probed pairs (TSM → 2330.TW, ASML → ASML.AS, NVO → NOVO-B.CO) resolve to the same company id, and the share of ADRs linked is not lower than the previous run's by more than 5 pp;
- a look-through check: no fund in the lookup still has a holding that is itself a fund in the universe (look-through left nothing unexpanded), and XEQT.TO has more than 1,000 rows with an `asset` (FMP still returns it looked through).

### Django

New module `analyzer/analyzer_utils/fund_finder.py`, two read-only endpoints in `analyzer/urls.py`, following the existing pattern (Redis first, gzip-compressed JSON, then S3):

- `GET /api/fund-finder/?include=RY.TO,TD.TO&exclude=SHOP.TO&listed=ca|us|both`
  - `listed` is required (400 without it).
  - Resolve every symbol to an ISIN through `isin_map` (unknown symbols are returned in an `unknown` list, not an error).
  - Read the buckets for the ISINs. Per fund: sum the included weights; drop the fund if any excluded ISIN has weight; filter by region; join `funds.parquet`; collapse identical portfolios; sort by combined weight, then AUM; return the top 100.
  - Response per fund: symbol, name, exchange, currency, combined weight, weight per included pick (with `via` when indirect), MER, AUM, holdings fetch date, "also available as".
  - Cache: `funds.parquet` and `isin_map` in Redis whole (small); each bucket per ISIN in Redis; the final answer cached on the normalised query (sorted symbols), key prefix `funds:`, version `:v1`, expiring before the next weekly publish (or cleared on publish, whichever the cache layer already does for S3 datasets).
- `GET /api/funds-holding/<symbol>/?listed=ca|us|both`: the stock-page shortcut (same as an include of one symbol, top 10).

### Frontend

`/fund-finder`, Pages Router.

```
Funds listed in: [ Choose…  ▾ ]   (Canada / United States / Both)

Exposure to:   [RY.TO ×] [TD.TO ×]          [+ add a stock]
But not:       [SHOP.TO ×]                   [+ add a stock]

 #  Fund      Combined   RY.TO   TD.TO   MER    AUM      Listed
 1  ZEB.TO    33.1%      16.9%   16.2%   0.28%  C$3.4B   TSX
 2  XFN.TO    24.9%      13.0%   11.9%   0.61%  C$1.6B   TSX
 3  XEQT.TO    3.4%       2.0%    1.4%   0.20%  C$18.5B  TSX
 …
 Holdings fetched 2026-11-22 from fund issuers via FMP. ETFs only; mutual
 funds are not covered yet, and Canadian mutual funds are not available.
 Information only, not investment advice.
```
(Numbers are made up to show the layout.)

- Nothing is fetched until the listing dropdown is set and at least one stock is picked.
- The query lives in the URL (`/fund-finder?listed=ca&include=RY.TO,TD.TO&exclude=SHOP.TO`), so results can be shared and the stock-page link can prefill it.
- Each fund links to its existing `/etf-data/[ticker]` page.
- Empty state: "No ETF in this market holds these stocks without the excluded ones."

## Phase 2 (not this build)

US mutual funds (with share-class collapse; VFIAX and VOO hold the same portfolio), the fund screener, weight caps, and sector/country filters built from per-fund sector and country weights computed through look-through.

## Left to the builder

- Exact bucket count and hash; Redis expiry details; exact `MIN_COUNTS` values (from the dry run).
- Which ticker-picker component to reuse, or a small multi-pick wrapper around one.
- How `fetch_fund_holdings` gets the `profile-bulk` rows from `refresh_constituents` (pass them through the run's state or a saved file).
- Test fixtures: save `etf/holdings` payloads for XIU.TO, XEQT.TO, VEA, VTI and AGG, plus one fund of funds that FMP does **not** look through (find one in the dry run, if any exist), and an `etf/asset-exposure` payload for RY.TO.
