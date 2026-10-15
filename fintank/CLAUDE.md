# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fintank is a financial data platform with three distinct sub-projects:

1. **Next.js frontend** (root) — stock screener, market data dashboards, crypto/ETF/index analytics, Solana wallet integration
2. **Django REST backend** (`backend/`) — market data API, user auth, Celery background jobs, PostGIS database
3. **Solidity smart contracts** (`stables/`) — `Loonie` (LCAD), an algorithmic stablecoin pegged to the Canadian dollar, built with Foundry
4. **Solana Anchor program** (`anchor/`) — on-chain journal entry state (scaffold-level, mostly empty)

---

## Commands

### Frontend (Next.js)

```bash
# Install dependencies
npm install

# Dev server (runs on port 8020)
npm run dev

# Production build
npm run build

# Lint
npm run lint

# Format check
npm run format:check

# Format fix
npm run format
```

### Backend (Django)

```bash
cd backend

# Run Django dev server
python manage.py runserver

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Celery worker + beat together (development)
celery -A fintank_backend worker -B -l info

# Or separately
celery -A fintank_backend worker -l info
celery -A fintank_backend beat -l info

# Redis must be running first
sudo service redis-server start
# Check: redis-cli ping  → should return PONG
```

### Data pipeline (`backend/pipelines/`, runs on AWS)

```bash
cd backend
../../.venv/bin/python -m pytest pipelines/tests -q        # tests (moto, no AWS)
python -m pipelines run --mode lean --dry-run --limit 5     # local smoke run
python -m pipelines --help                                  # approve/discard/rollback/status…
cd ../infra && .venv/bin/python -m pytest -q                # CDK stack tests
```

Runbook: `backend/pipelines/README.md`. Design + AWS setup: `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`. The notebooks in `class_files/` no longer upload; `class_files/stock_pipeline.py` and `pipeline_config.py` are shims over `pipelines/`.

### Solidity (Foundry — `stables/`)

```bash
cd stables

# Build contracts
forge build

# Run tests
forge test

# Run a single test file
forge test --match-path test/MyTest.t.sol

# Run a single test function
forge test --match-test testFunctionName -vvv

# Deploy (example)
forge script script/DeployLoonie.s.sol --rpc-url $RPC_URL --broadcast
```

### Solana Anchor (`anchor/`)

```bash
# Build the program
npm run anchor-build

# Run tests
npm run anchor-test

# Start local validator with program deployed
npm run anchor-localnet

# Sync program ID after regenerating keypair
npm run anchor keys sync
# Then manually update the constant in anchor/src/counter-exports.ts
```

---

## Architecture

### Frontend

The project uses **two coexisting routing systems** that must not be confused:

- **`src/app/`** — Next.js App Router (new). Entry layout in `src/app/layout.tsx`. Wraps everything in `AppProviders` (Solana wallet context, React Query, theme) and `AppLayout`.
- **`src/pages/`** — Next.js Pages Router (legacy). Entry in `src/pages/_app.js`. Wraps in Redux `Provider` + `PersistGate` + legacy `Layout`.

Most of the financial UI lives in the **Pages Router** (`src/pages/`). The App Router hosts the Solana dApp pages (`/account`, `/counter`).

**State management** (Pages Router pages): Redux (`redux` + `redux-persist` + `redux-thunk`). Store in `src/store.js`, reducers in `src/reducers/`. The legacy components in `src/componentsLegacy/` read state via hooks in `src/hooks/`.

**Data fetching hooks** (`src/hooks/`) — each hook maps to a specific market data endpoint (e.g., `useIndexChart`, `useStockData`, `useSectorExposure`). All call `NEXT_PUBLIC_FINTANK_API_URL` (default `http://localhost:8000/api`).

**`src/componentsLegacy/`** — React components for charts, tables, news cards, screeners, etc. These are `.js` files using Bootstrap + Chart.js / ApexCharts.

**`src/components/`** — Newer `.tsx` components for the App Router pages (Solana wallet UI, theme, layout).

**Chart libraries in use**: ApexCharts (`react-apexcharts`), Chart.js (`react-chartjs-2`), and custom canvas utilities in `src/utils/` (`plotFactorChart.js`). (`macdCharter.js`, `adlCharter.js`, and `plotTechnicalChart.js` were removed by the technical charting comparison rebuild; see `src/componentsLegacy/Comparison/`.)

**`src/data/`** — Static JSON files used for sector/index metadata, menu configs, and mock data. These are not API responses.

### Backend

Django project at `backend/fintank_backend/`. Apps:

| App | Purpose |
|-----|---------|
| `users` | `CustomUser` (AbstractUser) + `UserProfile` + `AvatarPreset`. JWT auth via `rest_framework_simplejwt`. |
| `stockuploader` | Core financial models: `Stock`, `ETF`, `Crypto`, `ProfileStock`, `IncomeStatement`, and other financial statement models. Also handles CSV bulk import via `django-import-export`. |
| `analyzer` | Read-only API views that serve cached market data. No DB models — all data comes from Redis cache (gzip-compressed JSON) or S3 parquet files. |
| `news` | News article ingestion and API. Celery task `tasks.py` fetches from Bing News API (`AZURE_BING_KEY`). |
| `journal` | User journal entries (URLs currently commented out in main urls.py). |
| `pages` | HTML page views (non-API). |

**Caching pattern** in `analyzer/views.py`: every endpoint checks Redis for a `gzip`-compressed JSON blob first, then falls back to `analyzer_utils/CorePerformanceTools.py` functions which fetch live from the FMP API or S3. Cache keys follow the pattern `home:{data_type}:{qualifier}:v1`.

**Financial data sources**:
- **FMP (Financial Modeling Prep)** — live price/fundamental data via `FMP_URL` / `FMP_API` env vars
- **AWS S3 bucket `thetradingfloor`** — historical parquet files for index prices, company profiles, constituents. Accessed via `boto3` / `s3fs` in `backend/utils/StockCalculations.py`.

**Celery periodic tasks** (registered via `django-celery-beat`):
- `update_index_performance` — every 10 min
- `update_market_datasets` — every 15 min
- All tasks respect `is_market_open_now()` guard (skip when market closed)

**Database**: PostgreSQL + PostGIS (`django.contrib.gis.db.backends.postgis`). Requires `libgeos` and `libgdal` on the host (configured via `GEOS_LIBRARY_PATH` / `GDAL_LIBRARY_PATH` env vars).

### Solidity — `stables/`

Two contracts:
- `Loonie.sol` — ERC20Burnable token (LCAD). Mint/burn controlled exclusively by `LoonieEngine`.
- `LoonieEngine.sol` — Manages collateral (ETH, BTC, USDC, USDT), minting, redemption, and liquidations. Uses Chainlink price feeds.

Foundry remappings: `@openzeppelin` → `lib/openzeppelin-contracts/contracts`, `@chainlink/contracts/` → `lib/chainlink-brownie-contracts/`.

### Solana — `anchor/`

Minimal program (`anchor/programs/fintank/src/lib.rs`). Declares a `JounralEntryState` account struct but the `#[program]` module body is empty — no instructions implemented yet. The exported client in `anchor/src/` is the counter template scaffold.

---

## Environment Variables

**Frontend** (`.env`):
- `NEXT_PUBLIC_FINTANK_API_URL` — Django API base URL (default `http://localhost:8000/api`)
- `PROGRAM_ID` — Solana program ID
- `NEXT_PUBLIC_FIREBASE_*` — Firebase project config for auth
- `NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN` — Mapbox for map components

**Backend** (`backend/.env`):
- `DATABASE_*` — PostgreSQL connection (host: `127.0.0.1:5432`, db: `fintank_api`)
- `FMP_API` / `FMP_URL` — Financial Modeling Prep API key and base URL
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_BUCKET_NAME` — S3 access (`thetradingfloor` bucket, `us-east-1`)
- `AZURE_BING_KEY` — Bing News API key for `news` app
- `GEOS_LIBRARY_PATH` / `GDAL_LIBRARY_PATH` — GeoDjango native lib paths (Linux: `/usr/lib/x86_64-linux-gnu/`)
- `REDIS_URL` — defaults to `redis://127.0.0.1:6379/1`
- `STRIPE_SECRET_KEY` / `CLOUDINARY_*` — payment and image storage
