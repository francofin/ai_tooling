# FMP v3 → stable migration — design

**Date:** 2026-11-19
**Status:** draft for approval

## Why

FMP's `api/v3` routes return **403** for Fintank's key, starting around 2026-11-18. FMP retired v3 for non-legacy subscriptions. The weekly pipeline on 2026-11-14 still fetched 10,610 prices through v3, so the cut-over happened after that.

What breaks today:
- The live homepage index, ETF and crypto cards, and the index charts, whenever Redis is empty. Redis has no persistence, so that's after every restart or deploy.
- The index page's constituent quotes.
- The weekly AWS pipeline: prices, ETF holdings (all constituent lists), statements and TTM ratios. The run on 21 Nov will fail its checks and hold, so S3 keeps last week's data, but nothing updates until this is fixed.

On 2026-11-19 Franc subscribed to **FMP Ultimate** ($139/month, billed monthly). The same day, every `stable` endpoint below was probed once with the live key and returned 200 with data. The responses are saved in the session scratchpad. The symbols the August notes recorded as refused all returned data:
- history: `^GSPTSE`, `TX60.TS`, `^N225`;
- quotes: all 25 homepage index symbols;
- other endpoints: `etf/holdings`, `ratios-ttm`, `key-metrics-ttm`.

**Any v3 call found during planning that isn't listed below is in scope.** It joins the branch that owns its file, rather than being deferred.

## Goals

- The site and the pipeline make **no `api/v3` (or `api/v4`) calls**.
- Downstream shapes stay the same. Redis payloads the frontend reads, S3 parquet files and Django columns keep their field names, so nothing downstream changes.
- Verify each part against real data before it ships.

## Non-goals

- Rebuilding the pipeline around the bulk endpoints (option 2B). It's a later optimisation, and the mapping layer built here is reused by it.
- The watchlist feature (`feat/watchlist-analytics`). It's parked until this ships.
- The FMP display licence. This is a business question for Franc, flagged in the hand-off.

## Anti-goals

- Changing numbers users see without saying so. Where a `stable` field isn't the same thing as the v3 field (`close` vs `adjClose` for indexes), the doc says why it's equivalent.
- Adding FMP call volume the site doesn't need. Every live call stays one batched call where `stable` allows it.

## Approaches considered

- **2A, swap one for one plus a mapping layer (chosen).** Each v3 call becomes its `stable` equivalent. A mapping step renames the `stable` fields back to the names our code and data already use. Correctness is provable by comparing against last week's v3-built S3 data.
- **2B, rebuild the pipeline around the bulk endpoints.** For example, `eod-bulk` gives prices in about 5 calls a week instead of about 10,000. Deferred: it's a structural change, it's harder to verify, and it isn't urgent under Ultimate's 3,000 calls a minute.
- **Stay on Premium and read from S3 or free sources.** Rejected: Franc upgraded. Premium lacks ETF holdings, most index symbols and non-US prices.

## Delivery: three branches, in order, each deployed before the next

### Branch 1: `fix/fmp-stable-live-site`, the live site

Call sites:

| Function | v3 today | `stable` replacement |
|---|---|---|
| `CorePerformanceTools.get_index_performance` | `quote/{25 index symbols}` | `batch-quote?symbols=…`, 1 call |
| `CorePerformanceTools.get_etf_performance` | `quote/{~110 ETFs}` | `batch-quote?symbols=…`, 1 call |
| `CorePerformanceTools.get_crypto_performance` | `quotes/crypto/{~100 coins}` | `batch-quote?symbols=…`, 1 call (probed with crypto symbols: full quote fields) |
| `CorePerformanceTools.get_index_charts` | `historical-price-full/{5 symbols}` × 3 | `historical-price-eod/full?symbol=…`, 15 calls (no multi-symbol history on `stable`) |
| `index_tools` constituent quotes (`api/v3/quote/{batch}`) | batched quotes | `batch-quote?symbols=…`, same batching |
| `backtester/engine/prices.py` `_fetch_from_fmp` (user-facing backtests, already broken by the 403) | `historical-price-full/{sym}?serietype=line` → `historical[].close` | `historical-price-eod/light?symbol=` → rows of `{symbol, date, price, volume}`; map `price` → the `close` the code reads. Probed 200 with SPY. |

All 25 homepage index symbols, including `^DJITR`, `^NMX0530`, `^VXSLV` and `TX60.TS`, came back from **one** `batch-quote` call (probed 2026-11-19, none missing).

Field mapping, applied in one shared helper so the frontend and existing tests keep working:
- **Quotes:**
  - `stable` `changePercentage` → also written as `changesPercentage`, the v3 name. 20+ frontend reads and `index_tools` sorting depend on it.
  - The `stable` quote has **no `pe` or `eps`**. The index page sorts constituents by `pe`. **My call:** take `pe` from the TTM ratios the pipeline already stores in S3 (`priceToEarningsRatioTTM`, or the v3-era column it was mapped to), joined by symbol. No extra FMP calls. Where a symbol has no ratio, `pe` is `None`, which the existing filter already skips.
  - The homepage cards don't read `pe`/`eps` (to confirm in the plan); if they do, the same S3 join applies.
  - **Where the `pe` join runs (my call):** in the same place the constituent quotes are built and cached today, never per request. The symbol→`pe` map is loaded once from S3 and cached in Redis for 24h under its own versioned key. Symbols outside the stored ratios (some non-US constituents) get `pe = None`.
- **Index history:** `stable` `historical-price-eod/full` has `close` but no `adjClose`. `format_index_prices` reads `adjClose`. Price indexes have no dividends to adjust for, so `close` is the same series. The mapper copies `close` into `adjClose`. The history is also oldest-first or newest-first depending on the endpoint; the plan pins the order the chart expects.
- **Errors:** a failed `stable` call keeps today's behaviour. The view returns its existing error response, and Celery keeps the previous cache.

Verification:
- Unit tests with the probed `stable` payloads as fixtures, checking the mapped output has the field names and types the frontend reads.
- A local check that each homepage card and chart renders, once Franc starts the servers.

### Branch 2: `fix/fmp-stable-pipeline`, the weekly AWS pipeline

All `_v3` builders in `pipelines/stock_pipeline.py` move to `stable`. The code comments record the August reasons each one stayed on v3:

| Data | v3 | `stable` | Mapping work |
|---|---|---|---|
| Index history | `historical-price-full` | `historical-price-eod/full` | `close` → `adjClose` (as branch 1) |
| Stock prices | `historical-price-full` | `historical-price-eod/dividend-adjusted`, plus `full` if raw OHLC is used downstream | Rebuild the v3 row shape (`open/high/low/close/adjClose/volume`). The plan checks which columns downstream actually reads, to avoid doubling calls when only `adjClose` and `volume` matter. |
| Constituents | `etf-holder/{etf}` | `etf/holdings?symbol=` | `asset`, `weightPercentage`, `sharesNumber` (probed). Map to the v3 names the constituent code reads. |
| ETF list | `etf/list` (has `exchange`) | `etf-list` (no `exchange`) | Join `exchange` from `profile-bulk`, one bulk CSV call, or from the profiles the pipeline already stores. The plan picks whichever already holds every ETF. |
| Statements (income, balance sheet, cash flow) | v3 | `stable` | Rename (`filingDate`→`fillingDate`, `fiscalYear`→`calendarYear`, `epsDiluted`→`epsdiluted`, …) and **calculate** the dropped ratio columns (`grossProfitRatio`, `ebitdaratio`, `operatingIncomeRatio`, `incomeBeforeTaxRatio`, `netIncomeRatio`) from their parts. `link`/`finalLink` become null. |
| Ratios TTM | `ratios-ttm` | `ratios-ttm` | About 31 renamed fields (`peRatioTTM`←`priceToEarningsRatioTTM`, `dividendYielTTM`←`dividendYieldTTM`, …). The full map is built in the plan by diffing a v3-era S3 row against a `stable` row for the same symbol. |
| Key metrics TTM | `key-metrics-ttm` | `key-metrics-ttm` | Same renaming method. |
| Daily sector snapshot (`get_sector_performance`, ~L1379) | `sector-performance`: one row per sector, `changesPercentage` as `"0.63%"` strings | `sector-performance-snapshot?date=`: floats, **one row per sector per exchange** (probed 200, 11 rows) | **My call:** request NYSE and NASDAQ, average `averageChange` per sector, write it back as the v3 row shape (`sector`, `changesPercentage` as `"x.xx%"`) so the parser and the stored file stay unchanged. Verified against the last v3-era file in the comparison step. |
| Index sector exposure (`get_index_sector_exposure`, ~L1405) | `etf-sector-weightings/{etf}`, `weightPercentage` as `"35.5%"` | `etf/sector-weightings?symbol=`, `weightPercentage` as a float (probed 200) | The parser already strips `%` from a string; make it accept floats. |

Verification, the core of 2A:
- A comparison script loads the **current** S3 objects, which are all still v3-built because `stable` hasn't written anything yet. It covers a sample of about 40 symbols across US, TSX, EAFE, small-cap and ETFs. It runs the new `stable` path for the same symbols and diffs the overlapping dates field by field.
- **Pass rule (my call):**
  - Every field the downstream code reads exists, with the same name and type.
  - Prices: `adjClose` is within 0.5% relative on at least 99% of overlapping rows. Small differences are expected from FMP restating adjusted prices.
  - Statements and ratios: the values match within 1% wherever both sides have a value.
  - Anything outside these limits is either explained in the plan (data drift or a basis change) or blocks the merge. A missing field always blocks.
- Then a `--dry-run --limit` local run, then the real AWS run started by hand, which holds for approval as usual.

**Timing (my call):** branch 2 is not rushed to beat the 21 Nov weekly run. That run will fail its checks and hold, S3 keeps last week's data, and nothing is lost. Once branch 2 deploys, the run is started by hand. Within branch 2, prices and constituents are built and verified first, because the most pages depend on them.

### Branch 3: `chore/remove-dead-fmp-helpers`

Delete `backend/utils/GetPrices.py`, `UniverseCalculations.py`, `RunCovar.py` and `PeerCalculations.py`. Nothing imports them (checked 2026-11-19 across `.py`, `.ipynb` and `.md`; the plan re-runs that check as its first step); only `docs/BACKEND_BREAKDOWN.md` and an old plan mention them, so those docs get a one-line note. `class_files/research_utils.py` keeps its own v3/v4 constants. **My call:** it's a research shim, not deployed. Its v3 URLs are switched to `stable` only where its functions are still called by `pipelines/`, otherwise left with a comment.

## Constraints

- One branch per part, each from an up-to-date `main`. Franc pushes, and merging deploys.
- No new `NEXT_PUBLIC_*` settings, no migrations and no server `.env` changes are expected. If the plan finds one, it follows the live-site rules: an ARG/ENV line, a build-arg and a GitHub variable.
- Python changes get the `python-code-reviewer` pass. Django tests per app; pipeline tests with `pytest pipelines/tests`.
- FMP calls during development are kept to probes and fixture capture. Tests use saved fixtures, never live FMP.

## Left to the builder (the plan)

- The exact rename tables for statements, ratios TTM and key metrics TTM, derived by diffing real rows.
- Whether the pipeline needs the raw OHLC price call or only the dividend-adjusted one.
- Where the ETF `exchange` comes from.
- The sort order of the `stable` history responses.
