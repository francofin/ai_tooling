# Automated Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the hand-run `lean_run` / `full_run` / `news_updater` notebooks into a tracked, tested Python package that AWS runs on a schedule — weekly market data (lean, full in the first week of the month) and daily news — with checks before anything reaches the live bucket, approval holds, email notifications and rollback.

**Architecture:** `backend/pipelines/` holds the moved `StockDataPipeline`, a stage runner with resume, pure check functions, a run report, state archives in a private S3 bucket, diff-based staging and publishing, a rewritten news job and a CLI. AWS CDK (Python) in `infra/` deploys Fargate task definitions driven by two Step Functions state machines (JSONata ASL files) on EventBridge Scheduler, with SNS email alerts.

**Tech Stack:** Python 3.12, pandas 2.3 / pyarrow 22, boto3, zstandard, pandas-market-calendars, pytest + moto; AWS CDK v2 (Python), ECS Fargate, Step Functions (JSONata), EventBridge Scheduler, SNS, SQS, CloudWatch, SSM Parameter Store, S3.

**Spec:** `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`

## Global Constraints

- Every file this plan creates or edits is inside `fintank/`. `backend/class_files/` is git-ignored: edits there are local only and are **never** `git add -f`'d.
- **Never run anything against real AWS** — no `aws` CLI calls, no `cdk deploy`/`cdk bootstrap`, no boto3 without moto. All AWS behaviour is tested with `moto` or fakes. Franc deploys.
- **Never execute notebooks.** Notebook changes are JSON edits only.
- Never start Django, Celery, `npm run dev` or any background process.
- No secrets in code, tests or commits. Keys come from the environment (`FMP_API`, `FRED_API`, `SERPAPI_KEY`).
- S3 keys written to `thetradingfloor` must equal what today's `upload_*` methods write, byte for byte (the site reads them).
- Region is `us-east-1` everywhere.
- Schedule (UTC): weekly `cron(0 10 ? * SAT *)`, mode auto = full on day-of-month 1–7 else lean; news `cron(30 9 * * ? *)`.
- Thresholds are exactly those in Task 4's `thresholds.py`.
- Pipeline tests: `cd fintank/backend && ../../.venv/bin/python -m pytest pipelines/tests -q`. Infra tests: `cd fintank/infra && .venv/bin/python -m pytest -q`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work on branch `feat/data-pipeline` (created in Task 1).

## Rulings against the spec (made while planning)

| # | Spec said | Plan does | Why |
|---|---|---|---|
| R1 | Diff each file against the live object's `x-amz-meta-sha256` | Diff against `state/live-manifest.json` (`{key: sha256}`), kept current by every publish and rollback; publish still sets the metadata | One read instead of ~140k HEAD requests |
| R2 | State machine sends all emails | Python sends Held / Complete / News emails; the state machine sends Started / Failed / Discarded / Busy | Message content is unit-testable in Python |
| R3 | Prices: any >80% move warns | `adjClose <= 0` warns; >80% one-day moves are listed, and warn only when >1% of symbols have one | ~2,400 micro/small caps produce real 80% moves most weeks; warning on every one would hold every run |
| R4 | News: ≥5 articles per file | FMP feeds ≥50, search topics ≥3 | Observed: FMP feeds return ~300; `canadian_stock` returns 5, `industrials` 8 |
| R5 | `pipeline` dependency group in `pyproject.toml` | `pipelines/requirements.txt` (+ `requirements-dev.txt`) | Backend deps live in the shared monorepo venv; one pinned file serves both Docker and local install |
| R6 | Enable schedules in the EventBridge console | Enable via CDK context (`-c news_schedule=on -c weekly_schedule=on`) | A console change would be reverted by the next `cdk deploy` |
| R7 | Small tasks 21 GiB disk | Fargate default (20 GiB) | 21 is just "more than default"; nothing needs it |
| R8 | `ALWAYS_HOLD` decided in the state machine | The container decides `hold` (verdict ≠ pass or `ALWAYS_HOLD`) and writes it to `verdict.json` | One place owns the hold rule; the state machine just reads it |
| R9 | "1 automatic retry" via Step Functions `Retry` | An `attempt` counter: a failed task **or** a missing `verdict.json` retries once | Works whether or not ECS `.sync` fails on a non-zero exit code |
| R10 | State carries raw JSON only | State also carries `stock_data/revenue_segments/` | Lean runs don't refetch segments but must still have them, or output counts drop vs a full baseline |
| R11 | `resume <run-id>` command | `start --mode … --run-id <id>` starts a new execution that resumes that run | Resume needs a fresh container anyway; one command |

---

## File Map

| File | Responsibility |
|---|---|
| `backend/pipelines/__init__.py` | Package marker + pointer to the spec |
| `backend/pipelines/__main__.py` | `python -m pipelines` → `cli.main()` |
| `backend/pipelines/cli.py` | All commands |
| `backend/pipelines/stock_pipeline.py` | Moved from `class_files/`; data root/credential defaults; stages return `StageResult` |
| `backend/pipelines/pipeline_config.py` | Moved from `class_files/`, unchanged |
| `backend/pipelines/results.py` | `StageResult` |
| `backend/pipelines/thresholds.py` | Every check threshold |
| `backend/pipelines/checks.py` | `CheckResult`, `verdict()`, one function per check |
| `backend/pipelines/report.py` | `RunReport` model, JSON round-trip, text summary |
| `backend/pipelines/store.py` | `LocalStore` / `S3Store`, key helpers, AWS client factory, bucket names |
| `backend/pipelines/state.py` | State units, `.tar.zst` push/pull |
| `backend/pipelines/outputs.py` | `Output`, `collect_outputs()` — local file → live key, in publish order |
| `backend/pipelines/publish.py` | Diff, stage, publish, rollback, live manifest |
| `backend/pipelines/notify.py` | `Notifier` (SNS or stdout) and message builders |
| `backend/pipelines/runner.py` | Stage lists, mode/run-id, `run_weekly()` with resume, `run_checks()`, `stage_outputs()` |
| `backend/pipelines/news.py` | News fetchers, per-file checks, `run_news()` |
| `backend/pipelines/requirements*.txt` | Pinned runtime / test deps |
| `backend/pipelines/Dockerfile`, `backend/.dockerignore` | Container image (whitelist build context) |
| `backend/pipelines/tests/` | All pipeline tests |
| `backend/fintank_backend/settings.py` | Celery beat at fixed UTC times |
| `infra/` | CDK app, stack, ASL state machines, stack tests |

---

### Task 1: Package skeleton — move the pipeline into git

**Files:**
- Create: `backend/pipelines/__init__.py`, `backend/pipelines/stock_pipeline.py` (copy), `backend/pipelines/pipeline_config.py` (copy), `backend/pipelines/requirements.txt`, `backend/pipelines/requirements-dev.txt`, `backend/pipelines/tests/__init__.py`, `backend/pipelines/tests/conftest.py`, `backend/pipelines/tests/helpers.py`, `backend/pipelines/tests/test_setup.py`
- Move: `backend/utils/factor_windows.py` → `backend/pipelines/factor_windows.py`; `backend/utils/test_factor_windows.py` → `backend/pipelines/tests/test_factor_windows.py`
- Create: `backend/utils/factor_windows.py` (re-export shim for the old v2 notebook)
- Modify (local only, git-ignored): `backend/class_files/stock_pipeline.py`, `backend/class_files/pipeline_config.py` → shims

Why the move: nothing else in the backend imports `factor_windows` (only the pipeline and its own test), and having it inside the package lets the container's build context be `backend/pipelines/` alone — far away from the 48 GB in `class_files/`.

**Interfaces:**
- Produces: `pipelines.factor_windows` (moved, unchanged); `pipelines.stock_pipeline.StockDataPipeline(root=None, env_path=None, max_calls=295, pause=60)`; module constants `MODULE_DIR`, `BACKEND_DIR`, `DEFAULT_DATA_ROOT`, `DEFAULT_BUCKET`; `pipelines.pipeline_config` (same names as today). Test fixtures `clean_env`, `pipeline`, `aws` and helpers `write_constituents`, `price_rows`, `write_price_json`.

- [ ] **Step 1: Branch and install test deps**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git checkout -b feat/data-pipeline
mkdir -p backend/pipelines/tests
cp backend/class_files/stock_pipeline.py backend/pipelines/stock_pipeline.py
cp backend/class_files/pipeline_config.py backend/pipelines/pipeline_config.py
git mv backend/utils/factor_windows.py backend/pipelines/factor_windows.py
git mv backend/utils/test_factor_windows.py backend/pipelines/tests/test_factor_windows.py
```

In `backend/pipelines/tests/test_factor_windows.py` change `from utils.factor_windows import WINDOWS, window_return_and_std` to `from pipelines.factor_windows import WINDOWS, window_return_and_std`.

Create `backend/utils/factor_windows.py` (keeps `stock_data_getter_v2.ipynb` importing):

```python
"""Moved to backend/pipelines/factor_windows.py; re-exported for old notebooks."""
from pipelines.factor_windows import WINDOWS, window_return_and_std  # noqa: F401
```

Create `backend/pipelines/requirements.txt`:

```
# Runtime deps of the pipeline image and of local runs. Versions match the
# shared venv so local and AWS runs write identical parquet bytes.
pandas==2.3.3
pyarrow==22.0.0
numpy==2.3.4
boto3==1.42.44
requests==2.32.5
python-dotenv==1.2.1
pandas-market-calendars==5.3.0
zstandard==0.25.0
```

Create `backend/pipelines/requirements-dev.txt`:

```
-r requirements.txt
pytest==9.0.2
moto[s3,sns]>=5.1,<6
```

Install into the shared venv (adds moto; the rest are already at these versions):

```bash
cd backend && uv pip install --python ../../.venv/bin/python -r pipelines/requirements-dev.txt
```

- [ ] **Step 2: Write the failing tests**

`backend/pipelines/__init__.py`:

```python
"""Fintank's automated data pipeline: the weekly market-data run and the daily
news run. Design: docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md"""
```

`backend/pipelines/tests/__init__.py`: empty file.

`backend/pipelines/tests/helpers.py`:

```python
"""Small builders for fixture data shaped like FMP payloads on disk."""
import json
import os

import pandas as pd


def write_constituents(p, key, symbols):
    path = p.constituents_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([{"asset": s, "weightPercentage": 100 / len(symbols)}
                   for s in symbols], f)


def price_rows(end, n=40, start_price=100.0):
    """FMP 'historical' rows, newest first, the last one on business day `end`."""
    days = pd.bdate_range(end=end, periods=n)
    rows = []
    for i, day in enumerate(days):
        price = start_price + i
        rows.append({"date": day.strftime("%Y-%m-%d"), "open": price,
                     "high": price, "low": price, "close": price,
                     "adjClose": price, "volume": 1000})
    return list(reversed(rows))


def write_price_json(p, sub, symbol, end, n=40):
    folder = p.json_dir("stock_prices", sub)
    os.makedirs(folder, exist_ok=True)
    with open(f"{folder}{symbol}_prices.json", "w") as f:
        json.dump({"symbol": symbol, "historical": price_rows(end, n)}, f)
```

`backend/pipelines/tests/conftest.py`:

```python
import boto3
import pytest
from moto import mock_aws

from pipelines import stock_pipeline as sp

LEAKY_ENV = ("PIPELINE_DATA_ROOT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
             "AWS_SESSION_TOKEN", "AWS_BUCKET_NAME", "AWS_PROFILE",
             "SNS_TOPIC_ARN", "STATE_BUCKET", "LIVE_BUCKET", "ALWAYS_HOLD")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Nothing real leaks in from the shell or backend/.env. Returns a path to
    a .env that does not exist, for StockDataPipeline(env_path=...)."""
    for name in LEAKY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FMP_API", "test-fmp-key")
    monkeypatch.setenv("FRED_API", "test-fred-key")
    return tmp_path / "no.env"


@pytest.fixture
def pipeline(clean_env, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    p = sp.StockDataPipeline(root=str(root), env_path=str(clean_env))
    p.limiter = sp.RateLimiter(max_calls=10**9, pause=0)
    return p


@pytest.fixture
def aws(clean_env, monkeypatch):
    """moto-backed AWS with fake credentials. Yields an S3 client."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")
```

`backend/pipelines/tests/test_setup.py`:

```python
import os

from pipelines import stock_pipeline as sp


def test_root_defaults_to_class_files(clean_env):
    p = sp.StockDataPipeline(env_path=str(clean_env))
    assert p.root == os.path.join(sp.BACKEND_DIR, "class_files")


def test_root_from_environment(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_DATA_ROOT", str(tmp_path))
    assert sp.StockDataPipeline(env_path=str(clean_env)).root == str(tmp_path)


def test_explicit_root_beats_environment(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_DATA_ROOT", "/somewhere/else")
    p = sp.StockDataPipeline(root=str(tmp_path), env_path=str(clean_env))
    assert p.root == str(tmp_path)


def test_bucket_defaults_to_live_bucket(clean_env):
    assert sp.StockDataPipeline(env_path=str(clean_env)).bucket == "thetradingfloor"


def test_s3_uses_default_chain_without_keys(clean_env, monkeypatch):
    calls = []
    monkeypatch.setattr(sp.boto3, "client",
                        lambda *a, **kw: calls.append((a, kw)) or object())
    sp.StockDataPipeline(env_path=str(clean_env)).s3
    assert calls == [(("s3",), {"region_name": "us-east-1"})]


def test_s3_uses_keys_when_present(clean_env, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    calls = []
    monkeypatch.setattr(sp.boto3, "client",
                        lambda *a, **kw: calls.append((a, kw)) or object())
    sp.StockDataPipeline(env_path=str(clean_env)).s3
    assert calls[0][1]["aws_access_key_id"] == "id"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline_config'` (the copied module still uses the old sys.path import).

- [ ] **Step 4: Edit `backend/pipelines/stock_pipeline.py`**

Replace the import block (copied lines 78–85):

```python
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(MODULE_DIR)
for _p in (MODULE_DIR, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pipeline_config as cfg
from utils.factor_windows import WINDOWS, window_return_and_std
```

with:

```python
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(MODULE_DIR)
# Local data stays beside the notebooks; on AWS, PIPELINE_DATA_ROOT is /data.
DEFAULT_DATA_ROOT = os.path.join(BACKEND_DIR, "class_files")
DEFAULT_BUCKET = "thetradingfloor"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from pipelines import pipeline_config as cfg  # noqa: E402
from pipelines.factor_windows import WINDOWS, window_return_and_std  # noqa: E402
```

In the module docstring, change `from stock_pipeline import StockDataPipeline` to `from pipelines.stock_pipeline import StockDataPipeline`.

In the class docstring, replace the `root:` line with:

```
    root:     folder holding stock_data_json/, stock_data/, index_data/,
              econ_data/. Defaults to $PIPELINE_DATA_ROOT, else
              backend/class_files/.
```

In `__init__`, replace `self.root = os.path.abspath(root or MODULE_DIR)` with:

```python
        self.root = os.path.abspath(
            root or os.getenv("PIPELINE_DATA_ROOT") or DEFAULT_DATA_ROOT)
```

and replace `self.bucket = os.getenv("AWS_BUCKET_NAME")` with:

```python
        self.bucket = os.getenv("AWS_BUCKET_NAME") or DEFAULT_BUCKET
```

Replace the body of the `s3` property with:

```python
        """Lazily-built S3 client, reused across uploads."""
        if self._s3 is None:
            if self.aws_key and self.aws_secret:
                self._s3 = boto3.client(
                    "s3",
                    aws_access_key_id=self.aws_key,
                    aws_secret_access_key=self.aws_secret,
                    region_name="us-east-1",
                )
            else:
                # No keys in the environment: boto3's default chain — the ECS
                # task role on AWS, an SSO profile (AWS_PROFILE) locally.
                self._s3 = boto3.client("s3", region_name="us-east-1")
        return self._s3
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass (6 setup tests + the moved factor_windows tests).

- [ ] **Step 6: Replace the class_files copies with shims (local only)**

`backend/class_files/stock_pipeline.py` (overwrite — the real code now lives in `pipelines/`):

```python
"""Moved to backend/pipelines/stock_pipeline.py. This shim keeps the notebooks
and research_utils.py importing `stock_pipeline` working."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.stock_pipeline import *  # noqa: E402,F401,F403
from pipelines.stock_pipeline import StockDataPipeline, RateLimiter  # noqa: E402,F401
```

`backend/class_files/pipeline_config.py`:

```python
"""Moved to backend/pipelines/pipeline_config.py. This shim keeps
`import pipeline_config` working for the notebooks and research_utils.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.pipeline_config import *  # noqa: E402,F401,F403
from pipelines.pipeline_config import normalise_segmentation_periods  # noqa: E402,F401
```

Check the shims import (no network, no data read):

```bash
cd backend/class_files && ../../../.venv/bin/python -c "import stock_pipeline, pipeline_config; print(stock_pipeline.StockDataPipeline, len(pipeline_config.ALL_SUB_UNIVERSES))"
```

Expected: `<class 'pipelines.stock_pipeline.StockDataPipeline'> 9`

- [ ] **Step 7: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/pipelines backend/utils/factor_windows.py
git commit -m "feat(pipeline): move StockDataPipeline into a tracked pipelines package

Data root from PIPELINE_DATA_ROOT, S3 via boto3's default chain when no keys
are set, live bucket defaults to thetradingfloor.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Fetch stages report results

**Files:**
- Create: `backend/pipelines/results.py`, `backend/pipelines/tests/test_results.py`, `backend/pipelines/tests/test_fetch_results.py`
- Modify: `backend/pipelines/stock_pipeline.py` (`refresh_constituents`, `fetch_stock_prices`, `fetch_etf_prices`, `_fetch_constituent_datasets` and its five callers, `fetch_revenue_segments`, `fetch_index_prices`, `fetch_sector_history`, `fetch_fred_series`)

**Interfaces:**
- Consumes: Task 1 fixtures.
- Produces: `StageResult(name, attempted=0, saved=0, failed=0, no_data=0, failed_items=[], detail={})` with `.failure_rate`, `.record(ok, item=None)`, `.to_dict()`, `StageResult.from_dict(d)`; `redact(text) -> str` masks `apikey=`/`api_key=` values. Every `refresh_*`/`fetch_*` method returns a `StageResult` whose `name` is the method name. `refresh_constituents().detail["lists"][key] = {"status": "updated"|"kept", "previous": int|None, "new": int|None, "error": str|None}`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_results.py`:

```python
from pipelines.results import FAILED_ITEMS_CAP, StageResult, redact


def test_record_counts_and_rate():
    r = StageResult("fetch_x")
    r.record(True)
    r.record(False, "A")
    r.record(False, "B")
    assert (r.attempted, r.saved, r.failed) == (3, 1, 2)
    assert r.failed_items == ["A", "B"]
    assert r.failure_rate == 2 / 3


def test_empty_rate_is_zero():
    assert StageResult("x").failure_rate == 0.0


def test_redact_masks_api_keys():
    text = "500 Server Error for url: https://x/etf-holder/SPY?apikey=SECRET123&a=1"
    assert redact(text) == "500 Server Error for url: https://x/etf-holder/SPY?apikey=***&a=1"
    assert redact("https://serpapi.com/search?api_key=abc") == "https://serpapi.com/search?api_key=***"


def test_to_dict_caps_failed_items_and_round_trips():
    r = StageResult("x")
    for i in range(FAILED_ITEMS_CAP + 5):
        r.record(False, str(i))
    d = r.to_dict()
    assert len(d["failed_items"]) == FAILED_ITEMS_CAP
    assert d["failed_items_truncated"] is True
    assert d["failure_rate"] == 1.0
    back = StageResult.from_dict(d)
    assert back.failed == FAILED_ITEMS_CAP + 5
```

`backend/pipelines/tests/test_fetch_results.py`:

```python
import json

import pytest
import requests

from pipelines import stock_pipeline as sp
from pipelines.tests.helpers import price_rows, write_constituents


def fake_get(routes):
    """Return a _get replacement: the first route substring found in the URL
    decides the response; an Exception value is raised."""
    def _get(url, timeout=30):
        for needle, response in routes.items():
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected URL {url}")
    return _get


def test_fetch_stock_prices_counts_each_symbol(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA", "BBB", "BAD"])
    pipeline._get = fake_get({
        "/AAA?": {"symbol": "AAA", "historical": price_rows("2026-10-09", 5)},
        "/BBB?": {"symbol": "BBB", "historical": price_rows("2026-10-09", 5)},
        "/BAD?": requests.HTTPError("500"),
    })
    result = pipeline.fetch_stock_prices(constituent_keys=["sp500_const"])
    assert result.name == "fetch_stock_prices"
    assert (result.attempted, result.saved, result.failed) == (3, 2, 1)
    assert result.failed_items == ["sp500_const:BAD"]
    assert result.detail["manifests"]


def test_fetch_etf_prices_is_named_for_itself(pipeline):
    write_constituents(pipeline, "etf_data", ["SPY"])
    pipeline._get = fake_get({"/SPY?": {"historical": price_rows("2026-10-09", 3)}})
    assert pipeline.fetch_etf_prices().name == "fetch_etf_prices"


def test_dataset_fetchers_count_symbols(pipeline):
    write_constituents(pipeline, "sp500_const", ["AAA", "BAD"])
    pipeline._get = fake_get({
        "ratios-ttm/AAA": [{"peRatioTTM": 10}],
        "key-metrics-ttm/AAA": [{"marketCapTTM": 1}],
        "ratios-ttm/BAD": [],
    })
    result = pipeline.fetch_ttm_ratios(constituent_keys=["sp500_const"])
    assert result.name == "fetch_ttm_ratios"
    assert (result.saved, result.failed) == (1, 1)


def test_refresh_constituents_keeps_shrunk_list(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS",
                        {"sp500_const": "SPY", "nas_const": "QQQ"})
    write_constituents(pipeline, "sp500_const", [f"S{i}" for i in range(10)])
    pipeline._get = fake_get({
        "etf-holder/SPY": [{"asset": "S1"}, {"asset": "S2"}],          # shrank 10 → 2
        "etf-holder/QQQ": [{"asset": "Q1"}, {"asset": "Q2"}],          # first time
    })
    result = pipeline.refresh_constituents(include_etf_list=False)
    lists = result.detail["lists"]
    assert lists["sp500_const"]["status"] == "kept"
    assert lists["sp500_const"]["previous"] == 10
    assert "shrank" in lists["sp500_const"]["error"]
    assert lists["nas_const"] == {"status": "updated", "previous": None,
                                  "new": 2, "error": None}
    assert (result.saved, result.failed) == (1, 1)
    with open(pipeline.constituents_path("sp500_const")) as f:
        assert len(json.load(f)) == 10                      # old file intact


def test_revenue_segments_buckets(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "SEGMENTATION_CONSTITUENT_KEYS", ["sp500_const"])
    write_constituents(pipeline, "sp500_const", ["AAA", "NONE", "ERR"])
    pipeline._normalise_segmentation = lambda payload: (payload, "USD", [])
    pipeline._get = fake_get({
        "symbol=AAA": {"2025": {"iPhone": 1}},
        "symbol=NONE": [],
        "symbol=ERR": requests.HTTPError("502"),
    })
    result = pipeline.fetch_revenue_segments()
    assert result.name == "fetch_revenue_segments"
    assert (result.attempted, result.saved, result.no_data, result.failed) == (3, 1, 1, 1)
    assert result.failed_items == ["ERR"]


def test_index_prices_counts_indexes(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "INDEX_TICKERS", {
        "sp500": {"ticker": "^GSPC", "full_name": "S&P 500"},
        "dead": {"ticker": "^DEAD", "full_name": "Dead"},
    })
    pipeline._get = fake_get({
        "^GSPC": {"historical": price_rows("2026-10-09", 30)},
        "^DEAD": requests.HTTPError("404"),
    })
    result = pipeline.fetch_index_prices()
    assert (result.name, result.saved, result.failed) == ("fetch_index_prices", 1, 1)
    assert result.failed_items == ["dead"]


def test_sector_history_counts_combos(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "EXCHANGES", {"nasdaq": {"index_name": "NASDAQ"}})
    monkeypatch.setattr(sp.cfg, "SECTOR_NAMES", {"tech": "Technology", "energy": "Energy"})
    pipeline._get = fake_get({
        "sector=Technology": [{"date": "2026-10-09", "averageChange": 1.0}],
        "sector=Energy": [],
    })
    result = pipeline.fetch_sector_history()
    assert (result.attempted, result.saved, result.failed) == (2, 1, 1)


def test_fred_counts_series(pipeline):
    pipeline._get = fake_get({
        "series_id=DGS10": {"observations": [{"date": "2026-10-08", "value": "4.1"}]},
        "series_id=GDP": {"observations": [{"date": "2026-07-01", "value": "."}]},
    })
    result = pipeline.fetch_fred_series(series_ids=["DGS10", "GDP"])
    assert (result.name, result.saved, result.failed) == ("fetch_fred_series", 1, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_results.py pipelines/tests/test_fetch_results.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.results'`.

- [ ] **Step 3: Create `backend/pipelines/results.py`**

```python
"""What every pipeline stage reports back, so the runner and the checks act on
counts instead of reading printed progress lines."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

FAILED_ITEMS_CAP = 200  # keeps reports readable when a whole feed is down
_SECRET_PARAM = re.compile(r"(api_?key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Mask API keys inside URLs before an error message reaches a report or
    an email — requests puts the full URL, apikey included, in HTTPError."""
    return _SECRET_PARAM.sub(r"\1***", text)


@dataclass
class StageResult:
    name: str
    attempted: int = 0
    saved: int = 0
    failed: int = 0
    no_data: int = 0
    failed_items: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def failure_rate(self) -> float:
        return self.failed / self.attempted if self.attempted else 0.0

    def record(self, ok: bool, item: str | None = None) -> None:
        """Count one attempt; a failure may name the item that failed."""
        self.attempted += 1
        if ok:
            self.saved += 1
        else:
            self.failed += 1
            if item is not None:
                self.failed_items.append(item)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["failure_rate"] = round(self.failure_rate, 4)
        data["failed_items"] = self.failed_items[:FAILED_ITEMS_CAP]
        data["failed_items_truncated"] = len(self.failed_items) > FAILED_ITEMS_CAP
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "StageResult":
        names = ("name", "attempted", "saved", "failed", "no_data",
                 "failed_items", "detail")
        return cls(**{k: data[k] for k in names if k in data})
```

- [ ] **Step 4: Make the fetchers return `StageResult`**

In `stock_pipeline.py` add after the `pipelines.factor_windows` import:

```python
from pipelines.results import StageResult, redact  # noqa: E402
```

(directly after the `from pipelines.factor_windows import …` line.)

**`refresh_constituents`** — replace the whole method body (keep the docstring, but change its last line from `Returns {key: members}.` to `Returns a StageResult; detail["lists"][key] = {"status": "updated" | "kept", "previous", "new", "error"}.`):

```python
        result = StageResult("refresh_constituents")
        lists = result.detail.setdefault("lists", {})

        def previous_count(path):
            if not os.path.exists(path):
                return None
            with open(path) as f:
                return len(json.load(f))

        def refresh(key, fetch_rows):
            path = self.constituents_path(key)
            previous = previous_count(path)
            try:
                rows = fetch_rows()
                if previous is not None and len(rows) < 0.5 * previous:
                    raise ValueError(
                        f"payload shrank {previous} → {len(rows)} — degraded FMP "
                        "feed? (seen 2026-08-02: IEFA served 138 of ~2,600 "
                        "holdings for a day)")
                self._save_json(rows, path)
                lists[key] = {"status": "updated", "previous": previous,
                              "new": len(rows), "error": None}
                result.record(True)
                print(f"{key}: {len(rows)} members")
            except Exception as e:
                lists[key] = {"status": "kept", "previous": previous,
                              "new": None, "error": redact(str(e))}
                result.record(False, key)
                print(f"{key} FAILED (existing file kept): {e}")

        for key, proxy_etf in cfg.CONSTITUENT_PROXY_ETFS.items():
            def holdings(proxy_etf=proxy_etf):
                response = self._get(self._etf_holder_url(proxy_etf))
                self.limiter.tick()
                members = [item for item in response if item.get("asset")]
                if not members:
                    raise ValueError("no rows with an 'asset' symbol in payload")
                return members
            refresh(key, holdings)

        if include_etf_list:
            def etf_list():
                etf_data = self._get(self._etf_list_url())
                self.limiter.tick()
                requested = [x for x in etf_data
                             if x.get("exchange") in cfg.ETF_EXCHANGE_FILTER]
                if not requested:
                    raise ValueError("exchange filter matched no ETFs")
                return requested
            refresh("etf_data", etf_list)

        return result
```

**`fetch_stock_prices`** — add `stage_name="fetch_stock_prices"` as the last parameter; append to the docstring: `Returns a StageResult (one attempt per symbol); detail["manifests"] lists the path_helpers manifests written.` In the body:
- after `manifests = []` add `result = StageResult(stage_name)`;
- after `universe_items[symbol] = {"prices": f"{symbol}_prices.json"}` add `result.record(True)`;
- in the `except` block, after `failed.append(symbol)` add `result.record(False, f"{const_key}:{symbol}")`;
- replace the final `return manifests` with:

```python
        result.detail["manifests"] = manifests
        return result
```

**`fetch_etf_prices`** — body becomes:

```python
        return self.fetch_stock_prices(from_date=from_date,
                                       constituent_keys=["etf_data"], limit=limit,
                                       stage_name="fetch_etf_prices")
```

**`_fetch_constituent_datasets`** — signature becomes `(self, datasets, manifest_group, stage_name, constituent_keys=None, limit=None)`; same four edits as `fetch_stock_prices` (`result = StageResult(stage_name)`, `result.record(True)` after `universe_items[symbol] = entry`, `result.record(False, f"{const_key}:{symbol}")` in the except, return `result` with `detail["manifests"]`). Then pass `stage_name=` from each caller: `fetch_profiles` → `"fetch_profiles"`, `fetch_etf_profiles` → `"fetch_etf_profiles"`, `fetch_financial_statements` → `"fetch_financial_statements"`, `fetch_ratios` → `"fetch_ratios"`, `fetch_ttm_ratios` → `"fetch_ttm_ratios"`.

**`fetch_revenue_segments`** — replace the final `return manifest` with:

```python
        return StageResult(
            "fetch_revenue_segments",
            attempted=len(seen) - len(skipped),
            saved=len(with_data),
            failed=len(errors),
            no_data=len(no_data),
            failed_items=sorted(errors),
            detail={"manifest": manifest, "skipped": len(skipped)},
        )
```

and change the docstring's mention of the return to `Returns a StageResult: saved = with data, no_data = nothing disclosed, failed = errors (the only retry-worthy bucket).`

**`fetch_index_prices`** — replace `index_data, failed = {}, []` with `result, failed = StageResult("fetch_index_prices"), []`; replace `index_data[key] = existing_raw` with `result.record(True)` and `index_data[key] = combined` with `result.record(True)`; in the `except` add `result.record(False, key)` after `failed.append(key)`; replace `return index_data` with `return result`. Docstring: replace the `Returns {key: …}` sentence with `Returns a StageResult (one attempt per index); failures are collected and reported, not raised, so one dead ticker doesn't kill the run.`

**`fetch_sector_history`** — replace `failed = []` with `result, failed = StageResult("fetch_sector_history"), []`; after the `print(f"\r{ex_key}/{sec_key}: perf …")` line add `result.record(True)`; in the except add `result.record(False, f"{ex_key}/{sec_key}")`; end the method with `return result`.

**`fetch_fred_series`** — replace `failed = []` with `result, failed = StageResult("fetch_fred_series"), []`; after the `print(f"\r{sid}: …")` line add `result.record(True)`; in the except add `result.record(False, sid)`; end with `return result`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass (6 + 3 + 8).

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): fetch stages return StageResult counts

Constituent refresh reports updated/kept per list; revenue segments keep
their with-data/no-data/errors split.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Build stages report results; freshness without printing

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py` (`build_price_parquets`, `build_fundamentals_parquets`, `build_factor_metrics`, `build_profile_aggregate`, `build_contr_to_var`, `build_econ_parquets`, `build_relative_performance`, `status`; add `modal_last_dates`)
- Create: `backend/pipelines/tests/test_build_results.py`

**Interfaces:**
- Consumes: `StageResult` (Task 2), test helpers (Task 1).
- Produces: every `build_*` returns a `StageResult` named after the method. `build_factor_metrics().detail["lists"][sub] = {"rows": int, "skipped": int, "stale": int}`. `build_profile_aggregate().detail["rows"][name] = int`. `StockDataPipeline.modal_last_dates(sample=60, seed=7) -> {sub: {"files", "modal_last_date", "newest", "sampled"}}`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_build_results.py`:

```python
import os

from pipelines import stock_pipeline as sp
from pipelines.tests.helpers import write_constituents, write_price_json


def test_build_price_parquets_counts_files(pipeline):
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    folder = pipeline.json_dir("stock_prices", "sp500")
    with open(f"{folder}BAD_prices.json", "w") as f:
        f.write("{not json")
    result = pipeline.build_price_parquets(sub_universes=["sp500"])
    assert result.name == "build_price_parquets"
    assert (result.saved, result.failed) == (1, 1)
    assert result.failed_items == ["sp500/BAD"]
    assert result.detail["sp500"] == {"saved": 1, "failed": 1}


def test_build_factor_metrics_reports_stale_rows(pipeline):
    write_price_json(pipeline, "sp500", "NEW", "2026-10-09")
    write_price_json(pipeline, "sp500", "OLD", "2020-01-10")
    pipeline.build_price_parquets(sub_universes=["sp500"])
    result = pipeline.build_factor_metrics(sub_universes=["sp500"])
    assert result.name == "build_factor_metrics"
    assert result.detail["lists"]["sp500"] == {"rows": 2, "skipped": 0, "stale": 1}
    assert result.saved == 1


def test_build_factor_metrics_counts_empty_list_as_failed(pipeline):
    os.makedirs(pipeline.price_parquet_dir("daily", "nas"), exist_ok=True)
    result = pipeline.build_factor_metrics(sub_universes=["nas"])
    assert (result.saved, result.failed) == (0, 1)


def test_build_profile_aggregate_without_profiles_fails(pipeline):
    result = pipeline.build_profile_aggregate()
    assert (result.name, result.failed) == ("build_profile_aggregate", 1)


def test_build_contr_to_var_records_missing_prices(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    write_constituents(pipeline, "sp500_const", ["AAA", "BBB"])
    result = pipeline.build_contr_to_var()
    assert (result.name, result.failed, result.failed_items) == (
        "build_contr_to_var", 1, ["sp500"])


def test_modal_last_dates(pipeline):
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    write_price_json(pipeline, "sp500", "BBB", "2026-10-09")
    write_price_json(pipeline, "sp500", "CCC", "2026-10-08")
    dates = pipeline.modal_last_dates()
    assert dates["sp500"]["modal_last_date"] == "2026-10-09"
    assert dates["sp500"]["files"] == 3
    assert dates["nas"] == {"files": 0, "modal_last_date": None,
                            "newest": None, "sampled": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_build_results.py -q`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'name'`.

- [ ] **Step 3: Edit the build methods**

**`build_price_parquets`** — first line of the body: `result = StageResult("build_price_parquets")`. After `done += 1` add `result.record(True)`; in the except, after `failed += 1`, add `result.record(False, f"{sub}/{symbol}")`. After the inner `for fname in files:` loop (next to the bare `print()`), add `result.detail[sub] = {"saved": done, "failed": failed}`. End the method with `return result`.

**`build_fundamentals_parquets`** — first line: `result = StageResult("build_fundamentals_parquets")`. After `done += 1` add `result.record(True)`; in the except add `result.record(False, f"{data_type}/{sub}/{symbol}")`. After the file loop add `result.detail[f"{data_type}/{sub}"] = {"saved": done, "failed": failed}`. End with `return result`.

**`build_factor_metrics`** — replace `results = {}` with:

```python
        result = StageResult("build_factor_metrics")
        lists = result.detail.setdefault("lists", {})
```

In the `if not os.path.isdir(folder):` branch and the `if not rows:` branch, add `result.record(False, sub)` before `continue`. Replace `results[sub] = df` with:

```python
            lists[sub] = {"rows": len(df), "skipped": len(skipped), "stale": stale}
            result.record(True)
```

Replace `return results` with `return result`, and the docstring's return description with `Returns a StageResult; detail["lists"][sub] = {"rows", "skipped", "stale"}.`

**`build_profile_aggregate`** — first line: `result = StageResult("build_profile_aggregate")`. In the `if not frames:` branch replace `return {}` with:

```python
            result.record(False, "no per-symbol profiles")
            return result
```

Replace `results = {}` with `rows = result.detail.setdefault("rows", {})`, replace `results[name] = df` with `rows[name] = len(df)` followed by `result.record(True)`, and `return results` with `return result`. Docstring: `Returns a StageResult; detail["rows"][name] = row count.`

**`build_contr_to_var`** — replace the loop body so each list is guarded and counted:

```python
        result = StageResult("build_contr_to_var")
        for const_key in keys:
            sub = self.sub_universe_for(const_key)
            try:
                weights = self.constituent_weights(const_key)
                prices, missing = self._load_adj_close_matrix(
                    sub, list(weights), lookback=frequency + 10)
                df, dropped = self.compute_contr_to_vol(prices, weights,
                                                        frequency=frequency)
            except (FileNotFoundError, ValueError) as e:
                result.record(False, sub)
                print(f"{sub}: SKIPPED — {e}; existing parquet left untouched")
                continue
            if df.empty:
                result.record(False, sub)
                print(f"{sub}: SKIPPED — no symbols survived alignment "
                      f"({len(missing)} no local prices, {len(dropped)} dropped); "
                      "existing parquet left untouched")
                continue
            out_path = os.path.join(self.contr_to_var_dir,
                                    f"{sub}_contr_to_var.parquet")
            df.reset_index().to_parquet(out_path, index=False)
            result.record(True)
            result.detail[sub] = len(df)
            print(f"{sub}: {len(df)} stocks ({len(missing)} no local prices, "
                  f"{len(dropped)} gappy window) → {out_path}")
        return result
```

(keep the `keys = …` and `os.makedirs(self.contr_to_var_dir, exist_ok=True)` lines above it.)

**`build_econ_parquets`** — end with:

```python
        result = StageResult("build_econ_parquets", attempted=4, saved=4)
        result.detail = {"yield_spreads": len(yields), "cpi": len(cpi),
                         "nonfarm": len(nfp), "unemployment": len(unemp)}
        return result
```

(It still raises when a FRED JSON is missing — a crash, by design.)

**`build_relative_performance`** — replace `failed = []` with `result, failed = StageResult("build_relative_performance"), []`; after the success `print` add `result.record(True)`; in the except add `result.record(False, pair)`; end with `return result`.

**`modal_last_dates`** — add above `status()`:

```python
    def modal_last_dates(self, sample=60, seed=7):
        """Per sub-universe: price-file count and the MODAL last price date over
        a random sample of `sample` files (see status() for why modal). Reads
        only the first 4 KB of each file and prints nothing — the runner's
        freshness check uses it.

        Returns {sub: {"files", "modal_last_date", "newest", "sampled"}}."""
        import collections
        import random
        import re

        pattern = re.compile(rb'"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"')
        out = {}
        for sub in cfg.ALL_SUB_UNIVERSES:
            folder = self.json_dir("stock_prices", sub)
            if not os.path.isdir(folder):
                out[sub] = {"files": 0, "modal_last_date": None,
                            "newest": None, "sampled": 0}
                continue
            files = [f for f in os.listdir(folder) if f.endswith("_prices.json")]
            picks = random.Random(seed).sample(files, min(sample, len(files)))
            dates = []
            for name in picks:
                with open(os.path.join(folder, name), "rb") as fh:
                    match = pattern.search(fh.read(4096))
                if match:
                    dates.append(match.group(1).decode())
            modal = collections.Counter(dates).most_common(1)
            out[sub] = {
                "files": len(files),
                "modal_last_date": modal[0][0] if modal else None,
                "newest": max(dates) if dates else None,
                "sampled": len(dates),
            }
        return out
```

In `status()`, delete the `import collections` / `import random` / `import re` lines, the `pattern = …` line and the whole first `for sub in cfg.ALL_SUB_UNIVERSES:` loop, and replace them with:

```python
        rows = [{"sub_universe": sub, **info}
                for sub, info in self.modal_last_dates(sample, seed).items()]
```

(the following `prices = pd.DataFrame(rows)` line stays.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): build stages return StageResult; modal_last_dates

Factor metrics report rows/skipped/stale per list; contribution-to-variance no
longer dies on one list with no prices.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Thresholds and checks

**Files:**
- Create: `backend/pipelines/thresholds.py`, `backend/pipelines/checks.py`, `backend/pipelines/tests/test_checks.py`

**Interfaces:**
- Consumes: `StageResult` (Task 2); `FACTOR_METRICS_COLUMNS`, `cfg.FIELD_MAPPINGS` from `stock_pipeline`.
- Produces: `PASS, WARN, FAIL`; `CheckResult(name, status, value=None, threshold=None, detail="")` with `.to_dict()`; `verdict(results) -> str`; `check_constituents(StageResult) -> list`; `check_fetch(StageResult) -> CheckResult`; `recent_nyse_sessions(today, days=30) -> list[date]`; `check_freshness(modal_dates: {sub: "YYYY-MM-DD"|None}, sessions) -> list`; `check_outputs_readable(outputs, read_schema=None) -> list` (outputs have `.local_path`, `.dataset`); `check_counts(current: dict, baseline: dict|None) -> list`; `check_factor_staleness(current: {sub: {"rows","stale"}}, baseline) -> list`; `check_price_sanity(iterable of (symbol, pd.Series)) -> list`; `check_econ(last_dates: {sid: "YYYY-MM-DD"}, today) -> list`; `check_staging(changed: int, prices_saved: int) -> CheckResult`.

- [ ] **Step 1: Create `backend/pipelines/thresholds.py`** (values are the contract — copy verbatim)

```python
"""Every check threshold in one place. Changing one is a code change: edit,
run the tests, redeploy (cdk deploy rebuilds the image)."""

# Fetch stages: share of attempted items that failed.
FETCH_FAILURE_WARN = 0.02
FETCH_FAILURE_FAIL = 0.10

# Constituent lists: growth beyond this share of the previous count warns.
# (Shrinking by more than 50% is refused by refresh_constituents itself.)
CONSTITUENT_GROWTH_WARN = 0.50

# Freshness: NYSE sessions the modal last price date may trail the last
# completed session. Exactly this many behind warns; more fails.
FRESHNESS_WARN_SESSIONS = 1

# Output counts vs the last published run.
COUNT_RATIO_WARN = 0.98
COUNT_RATIO_FAIL = 0.90

# Factor metrics stale symbols (returns nulled because prices lag).
STALE_GROWTH_WARN = 2.0         # current >= 2x the baseline ...
STALE_GROWTH_MIN_DELTA = 5      # ... and at least 5 more symbols, to ignore noise
STALE_SHARE_FAIL = 0.10         # more than 10% of a list stale fails

# Prices: one-day adjClose moves above PRICE_JUMP within the last
# PRICE_RECENT_ROWS rows are listed; the check warns only when more than
# PRICE_JUMP_SHARE_WARN of checked symbols have one (plan ruling R3).
PRICE_JUMP = 0.80
PRICE_JUMP_SHARE_WARN = 0.01
PRICE_RECENT_ROWS = 10

# FRED: maximum days between today and a series' last observation date.
# Observation dates are period starts, so monthly/quarterly series lag a lot.
ECON_MAX_LAG_DAYS = {
    "DGS2": 10, "DGS5": 10, "DGS10": 10, "DGS30": 10,
    "DFII5": 10, "DFII10": 10, "BAMLH0A0HYM2EY": 10,
    "CCSA": 21, "WALCL": 21,
    "CPIAUCSL": 75, "PAYEMS": 75, "UNRATE": 75, "USREC": 75, "USRECD": 75,
    "CPGRLE01USM659N": 150,
    "GDP": 200, "GDPC1": 200,
}
ECON_DEFAULT_MAX_LAG_DAYS = 120

# News (plan ruling R4).
NEWS_MIN_ARTICLES = {"fmp": 50, "search": 3}
NEWS_MAX_AGE_DAYS = {"fmp": 3, "search": 7}
NEWS_FAILED_SHARE_FAIL = 0.5
```

- [ ] **Step 2: Write the failing tests**

`backend/pipelines/tests/test_checks.py`:

```python
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from pipelines import checks as c
from pipelines import thresholds as t
from pipelines.results import StageResult

D = dt.date


def statuses(results):
    return {r.name: r.status for r in results}


def test_verdict_is_worst():
    assert c.verdict([]) == c.PASS
    assert c.verdict([c.CheckResult("a", c.PASS), c.CheckResult("b", c.WARN)]) == c.WARN
    assert c.verdict([c.CheckResult("a", c.FAIL), c.CheckResult("b", c.WARN)]) == c.FAIL


def test_constituents():
    r = StageResult("refresh_constituents", detail={"lists": {
        "kept": {"status": "kept", "previous": 10, "new": None, "error": "shrank"},
        "grew": {"status": "updated", "previous": 100, "new": 151, "error": None},
        "fine": {"status": "updated", "previous": 100, "new": 150, "error": None},
        "new": {"status": "updated", "previous": None, "new": 5, "error": None},
    }})
    assert statuses(c.check_constituents(r)) == {
        "constituents.kept": c.FAIL, "constituents.grew": c.WARN,
        "constituents.fine": c.PASS, "constituents.new": c.PASS}


@pytest.mark.parametrize("failed,expected", [
    (2, c.PASS), (3, c.WARN), (10, c.WARN), (11, c.FAIL)])
def test_fetch_failure_rate_boundaries(failed, expected):
    r = StageResult("fetch_x", attempted=100, saved=100 - failed, failed=failed)
    result = c.check_fetch(r)
    assert (result.name, result.status) == ("fetch_x.failure_rate", expected)


def test_freshness():
    sessions = [D(2026, 10, 7), D(2026, 10, 8), D(2026, 10, 9)]
    results = c.check_freshness(
        {"a": "2026-10-09", "b": "2026-10-08", "c": "2026-10-07", "d": None,
         "e": "2026-10-10"}, sessions)
    assert statuses(results) == {
        "freshness.a": c.PASS, "freshness.b": c.WARN, "freshness.c": c.FAIL,
        "freshness.d": c.FAIL, "freshness.e": c.PASS}


def test_recent_nyse_sessions_skips_weekend_and_today():
    sessions = c.recent_nyse_sessions(D(2026, 10, 10))          # a Saturday
    assert sessions[-1] == D(2026, 10, 9)
    assert all(s.weekday() < 5 for s in sessions)


def test_outputs_readable(tmp_path):
    good = tmp_path / "AAA_prices.parquet"
    pd.DataFrame({"adjClose": [1.0], "returns": [0.0]}).to_parquet(good)
    missing_col = tmp_path / "BBB_prices.parquet"
    pd.DataFrame({"adjClose": [1.0]}).to_parquet(missing_col)
    broken = tmp_path / "x.parquet"
    broken.write_text("nope")
    seg = tmp_path / "A_segments.json"
    seg.write_text(json.dumps({"ok": 1}))
    outputs = [SimpleNamespace(local_path=str(good), dataset="stock_prices"),
               SimpleNamespace(local_path=str(missing_col), dataset="stock_prices"),
               SimpleNamespace(local_path=str(broken), dataset="econ"),
               SimpleNamespace(local_path=str(seg), dataset="revenue_segments")]
    results = statuses(c.check_outputs_readable(outputs))
    assert results == {"readable.stock_prices": c.FAIL, "readable.econ": c.FAIL,
                       "readable.revenue_segments": c.PASS}


def test_counts():
    assert statuses(c.check_counts({"x": 1}, None)) == {"counts": c.PASS}
    results = c.check_counts({"a": 98, "b": 97, "c": 89},
                             {"a": 100, "b": 100, "c": 100, "zero": 0})
    assert statuses(results) == {"counts.a": c.PASS, "counts.b": c.WARN,
                                 "counts.c": c.FAIL}


def test_factor_staleness():
    current = {"a": {"rows": 100, "stale": 11},   # 11% → fail
               "b": {"rows": 100, "stale": 10},   # 2x baseline 5, +5 → warn
               "c": {"rows": 100, "stale": 3},    # 3x baseline 1 but only +2 → pass
               "d": {"rows": 100, "stale": 4}}    # no baseline → pass
    baseline = {"a": {"stale": 1}, "b": {"stale": 5}, "c": {"stale": 1}}
    assert statuses(c.check_factor_staleness(current, baseline)) == {
        "factor_staleness.a": c.FAIL, "factor_staleness.b": c.WARN,
        "factor_staleness.c": c.PASS, "factor_staleness.d": c.PASS}


def test_price_sanity():
    calm = pd.Series([10.0, 10.5, 10.4])
    jump = pd.Series([10.0, 10.1, 30.0])
    bad = pd.Series([10.0, 0.0, 10.0])
    few = [("CALM", calm), ("JUMP", jump), ("BAD", bad)]
    results = statuses(c.check_price_sanity(few))
    assert results["prices.non_positive"] == c.WARN
    # 2 of 3 symbols jumped (BAD's recovery from 0 is a jump too): > 1% → warn
    assert results["prices.large_moves"] == c.WARN
    many = [(f"S{i}", calm) for i in range(200)] + [("JUMP", jump)]
    assert statuses(c.check_price_sanity(many))["prices.large_moves"] == c.PASS


def test_econ():
    today = D(2026, 10, 14)
    results = statuses(c.check_econ(
        {"DGS10": "2026-10-09", "GDP": "2026-01-01", "NEWSERIES": "2026-01-01"},
        today))
    assert results == {"econ.DGS10": c.PASS, "econ.GDP": c.WARN,
                       "econ.NEWSERIES": c.WARN}


def test_staging():
    assert c.check_staging(0, 100).status == c.FAIL
    assert c.check_staging(0, 0).status == c.PASS
    assert c.check_staging(5, 100).status == c.PASS
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_checks.py -q`
Expected: FAIL — `ImportError: cannot import name 'checks'`.

- [ ] **Step 4: Create `backend/pipelines/checks.py`**

```python
"""Run checks. Each function is pure (it reads files it is handed, never the
network) and returns CheckResult(s). The run's verdict is the worst status.

Exceptions are never turned into checks: a crash fails the run, and a failed
run publishes nothing."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass

from pipelines import thresholds as t
from pipelines.results import StageResult
from pipelines.stock_pipeline import FACTOR_METRICS_COLUMNS, cfg

PASS, WARN, FAIL = "pass", "warn", "fail"
_RANK = {PASS: 0, WARN: 1, FAIL: 2}

# Columns a parquet must carry, per output dataset. Datasets not listed are
# only checked for being readable (mapped fundamentals keep whatever FMP sent).
REQUIRED_COLUMNS = {
    "stock_prices": {"adjClose", "returns"},
    "index_prices": {"adjClose", "returns"},
    "factor_metrics": set(FACTOR_METRICS_COLUMNS),
    "profile_aggregates": set(cfg.FIELD_MAPPINGS["long_profiles"].values()),
}


@dataclass
class CheckResult:
    name: str
    status: str
    value: object = None
    threshold: object = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def verdict(results) -> str:
    worst = PASS
    for result in results:
        if _RANK[result.status] > _RANK[worst]:
            worst = result.status
    return worst


def check_constituents(result: StageResult) -> list[CheckResult]:
    out = []
    for key, info in sorted(result.detail.get("lists", {}).items()):
        name = f"constituents.{key}"
        if info["status"] == "kept":
            out.append(CheckResult(name, FAIL, None, None,
                                   f"refresh failed, previous list kept: {info['error']}"))
            continue
        previous, new = info["previous"], info["new"]
        if previous and new / previous - 1 > t.CONSTITUENT_GROWTH_WARN:
            out.append(CheckResult(name, WARN, new, t.CONSTITUENT_GROWTH_WARN,
                                   f"grew {previous} → {new}"))
        else:
            out.append(CheckResult(name, PASS, new, None, f"{previous} → {new}"))
    return out


def check_fetch(result: StageResult) -> CheckResult:
    rate = result.failure_rate
    if rate > t.FETCH_FAILURE_FAIL:
        status = FAIL
    elif rate > t.FETCH_FAILURE_WARN:
        status = WARN
    else:
        status = PASS
    detail = f"{result.failed} of {result.attempted} failed"
    if result.failed_items:
        detail += ": " + ", ".join(result.failed_items[:10])
    return CheckResult(f"{result.name}.failure_rate", status, round(rate, 4),
                       t.FETCH_FAILURE_WARN, detail)


def recent_nyse_sessions(today: dt.date, days: int = 30) -> list[dt.date]:
    """Completed NYSE sessions in the `days` before `today` (today excluded: a
    run during market hours must not expect today's close)."""
    import pandas_market_calendars as mcal

    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=today - dt.timedelta(days=days),
        end_date=today - dt.timedelta(days=1))
    return [ts.date() for ts in schedule.index]


def check_freshness(modal_dates: dict, sessions: list[dt.date]) -> list[CheckResult]:
    out = []
    for sub, modal in sorted(modal_dates.items()):
        name = f"freshness.{sub}"
        if modal is None:
            out.append(CheckResult(name, FAIL, None, t.FRESHNESS_WARN_SESSIONS,
                                   "no price files"))
            continue
        last = dt.date.fromisoformat(modal)
        behind = sum(1 for s in sessions if s > last)
        if behind == 0:
            status = PASS
        elif behind <= t.FRESHNESS_WARN_SESSIONS:
            status = WARN
        else:
            status = FAIL
        out.append(CheckResult(name, status, behind, t.FRESHNESS_WARN_SESSIONS,
                               f"modal last date {last}, {behind} NYSE session(s) behind"))
    return out


def _parquet_columns(path) -> set:
    import pyarrow.parquet as pq

    return set(pq.read_schema(path).names)


def check_outputs_readable(outputs, read_schema=None) -> list[CheckResult]:
    """One result per dataset: every parquet opens and has its required
    columns; every JSON parses."""
    read_schema = read_schema or _parquet_columns
    bad, seen = {}, {}
    for output in outputs:
        seen[output.dataset] = seen.get(output.dataset, 0) + 1
        try:
            if output.local_path.endswith(".parquet"):
                columns = read_schema(output.local_path)      # raises if unreadable
                missing = REQUIRED_COLUMNS.get(output.dataset, set()) - columns
                if missing:
                    raise ValueError(f"missing columns {sorted(missing)}")
            else:
                with open(output.local_path) as f:
                    json.load(f)
        except Exception as e:  # noqa: BLE001 — any unreadable file is a finding
            bad.setdefault(output.dataset, []).append(f"{output.local_path}: {e}")
    out = []
    for dataset in sorted(seen):
        problems = bad.get(dataset, [])
        out.append(CheckResult(
            f"readable.{dataset}", FAIL if problems else PASS, len(problems), 0,
            f"{len(problems)} of {seen[dataset]} unreadable"
            + (": " + "; ".join(problems[:5]) if problems else "")))
    return out


def check_counts(current: dict, baseline: dict | None) -> list[CheckResult]:
    if not baseline:
        return [CheckResult("counts", PASS, None, None, "no published baseline yet")]
    out = []
    for name, base in sorted(baseline.items()):
        if not base:
            continue
        now = current.get(name, 0)
        ratio = now / base
        if ratio < t.COUNT_RATIO_FAIL:
            status = FAIL
        elif ratio < t.COUNT_RATIO_WARN:
            status = WARN
        else:
            status = PASS
        out.append(CheckResult(f"counts.{name}", status, round(ratio, 4),
                               t.COUNT_RATIO_WARN, f"{now} vs {base} last published"))
    return out


def check_factor_staleness(current: dict, baseline: dict | None) -> list[CheckResult]:
    out = []
    for sub, info in sorted(current.items()):
        rows, stale = info["rows"], info["stale"]
        share = stale / rows if rows else 0.0
        base = (baseline or {}).get(sub, {}).get("stale")
        if share > t.STALE_SHARE_FAIL:
            status = FAIL
        elif (base is not None and stale >= t.STALE_GROWTH_WARN * base
              and stale - base >= t.STALE_GROWTH_MIN_DELTA):
            status = WARN
        else:
            status = PASS
        out.append(CheckResult(f"factor_staleness.{sub}", status, stale,
                               t.STALE_SHARE_FAIL,
                               f"{stale} of {rows} stale (last published: {base})"))
    return out


def check_price_sanity(series_by_symbol) -> list[CheckResult]:
    non_positive, jumps, checked = [], [], 0
    for symbol, adj_close in series_by_symbol:
        checked += 1
        recent = adj_close.dropna().iloc[-(t.PRICE_RECENT_ROWS + 1):]
        if (recent <= 0).any():
            non_positive.append(symbol)
        if (recent.pct_change().abs() > t.PRICE_JUMP).any():
            jumps.append(symbol)
    share = len(jumps) / checked if checked else 0.0
    return [
        CheckResult("prices.non_positive", WARN if non_positive else PASS,
                    len(non_positive), 0, ", ".join(non_positive[:20])),
        CheckResult("prices.large_moves",
                    WARN if share > t.PRICE_JUMP_SHARE_WARN else PASS,
                    len(jumps), t.PRICE_JUMP_SHARE_WARN,
                    f"{len(jumps)} of {checked} symbols moved more than "
                    f"{t.PRICE_JUMP:.0%} in a day recently"
                    + (": " + ", ".join(jumps[:20]) if jumps else "")),
    ]


def check_econ(last_dates: dict, today: dt.date) -> list[CheckResult]:
    out = []
    for sid, last in sorted(last_dates.items()):
        limit = t.ECON_MAX_LAG_DAYS.get(sid, t.ECON_DEFAULT_MAX_LAG_DAYS)
        lag = (today - dt.date.fromisoformat(last)).days
        out.append(CheckResult(f"econ.{sid}", WARN if lag > limit else PASS, lag,
                               limit, f"last observation {last}, {lag} days ago"))
    return out


def check_staging(changed: int, prices_saved: int) -> CheckResult:
    if changed == 0 and prices_saved > 0:
        return CheckResult("staging", FAIL, 0, None,
                           "no file differs from live although prices were fetched")
    return CheckResult("staging", PASS, changed, None, f"{changed} files differ from live")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): thresholds and pure check functions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Run report and stores

**Files:**
- Create: `backend/pipelines/report.py`, `backend/pipelines/store.py`, `backend/pipelines/tests/test_report.py`, `backend/pipelines/tests/test_store.py`

**Interfaces:**
- Consumes: `StageResult` (Task 2), `CheckResult`, `verdict`, `PASS` (Task 4).
- Produces:
  - `store.REGION = "us-east-1"`; `store.run_key(run_id, name) -> "runs/{run_id}/{name}"`; `store.LIVE_MANIFEST = "state/live-manifest.json"`; `store.LAST_PUBLISHED_REPORT = "state/last-published-report.json"`; `store.aws_client(service)`; `store.default_state_bucket(sts=None)`; `store.live_bucket()`.
  - `LocalStore(base_dir)` and `S3Store(bucket, client=None)`, both with `get_json(key, default=None)`, `put_json(key, data)`, `put_file(key, local_path)`, `exists(key)`, `list_prefixes(prefix) -> list[str]`, `url(key)`.
  - `report.now_iso()`; `RunReport(run_id, job, mode, started_at, dry_run=False, finished_at=None, stages=[], checks=[], counts={}, factor_staleness={}, staged_files=0, verdict=None)` with `add_stage(StageResult, seconds)`, `stage(name) -> dict|None`, `add_checks(list[CheckResult])`, `finish(verdict_override=None)`, `to_dict()`, `RunReport.from_dict(d)`, `summary() -> str`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_report.py`:

```python
from pipelines.checks import CheckResult
from pipelines.report import RunReport
from pipelines.results import StageResult


def make_report():
    return RunReport(run_id="lean-20261017-1000", job="weekly", mode="lean",
                     started_at="2026-10-17T10:00:00+00:00")


def test_add_stage_replaces_same_name():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=1, saved=1), 3.0)
    r.add_stage(StageResult("fetch_a", attempted=2, saved=2), 4.0)
    assert len(r.stages) == 1
    assert r.stage("fetch_a")["attempted"] == 2
    assert r.stage("fetch_a")["seconds"] == 4.0


def test_finish_takes_worst_check():
    r = make_report()
    r.add_checks([CheckResult("a", "pass"), CheckResult("b", "warn")])
    r.finish()
    assert r.verdict == "warn"
    assert r.finished_at is not None


def test_finish_override():
    r = make_report()
    r.add_checks([CheckResult("a", "fail")])
    r.finish(verdict_override="warn")
    assert r.verdict == "warn"


def test_round_trip():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=1, saved=1), 1.0)
    r.add_checks([CheckResult("a", "warn", 1, 0, "detail")])
    r.counts = {"stock_prices": 10}
    r.finish()
    back = RunReport.from_dict(r.to_dict())
    assert back == r


def test_summary_lists_non_passing_checks():
    r = make_report()
    r.add_stage(StageResult("fetch_a", attempted=100, saved=97, failed=3), 3725)
    r.add_checks([CheckResult("ok", "pass"),
                  CheckResult("freshness.tsx", "warn", 1, 1, "1 session behind")])
    r.finish()
    text = r.summary()
    assert "verdict: WARN" in text
    assert "fetch_a" in text and "1h02m" in text
    assert "1 pass, 1 warn, 0 fail" in text
    assert "WARN freshness.tsx — 1 session behind" in text
    assert "ok —" not in text
```

`backend/pipelines/tests/test_store.py`:

```python
import pytest

from pipelines import store


@pytest.fixture(params=["local", "s3"])
def any_store(request, tmp_path, aws):
    if request.param == "local":
        return store.LocalStore(str(tmp_path / "runs-store"))
    aws.create_bucket(Bucket="state")
    return store.S3Store("state", client=aws)


def test_json_round_trip_and_default(any_store):
    assert any_store.get_json("runs/x/a.json") is None
    assert any_store.get_json("runs/x/a.json", {"d": 1}) == {"d": 1}
    any_store.put_json("runs/x/a.json", {"v": 1})
    assert any_store.get_json("runs/x/a.json") == {"v": 1}
    assert any_store.exists("runs/x/a.json")
    assert not any_store.exists("runs/x/b.json")


def test_put_file_and_list_prefixes(any_store, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("hi")
    any_store.put_file("runs/r1/f.txt", str(f))
    any_store.put_json("runs/r2/report.json", {})
    assert any_store.list_prefixes("runs/") == ["runs/r1/", "runs/r2/"]


def test_run_key():
    assert store.run_key("lean-1", "report.json") == "runs/lean-1/report.json"


def test_default_state_bucket(monkeypatch):
    class FakeSts:
        def get_caller_identity(self):
            return {"Account": "123456789012"}
    monkeypatch.delenv("STATE_BUCKET", raising=False)
    assert store.default_state_bucket(FakeSts()) == "fintank-pipeline-123456789012"
    monkeypatch.setenv("STATE_BUCKET", "custom")
    assert store.default_state_bucket(FakeSts()) == "custom"


def test_live_bucket(monkeypatch):
    monkeypatch.delenv("LIVE_BUCKET", raising=False)
    assert store.live_bucket() == "thetradingfloor"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_report.py pipelines/tests/test_store.py -q`
Expected: FAIL — `ImportError` for `pipelines.report` / `pipelines.store`.

- [ ] **Step 3: Create `backend/pipelines/store.py`**

```python
"""Where run bookkeeping lives: the state bucket on AWS, a local folder for dry
runs. Both stores speak the same small interface, so the runner doesn't care."""
from __future__ import annotations

import json
import os
import shutil

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
LIVE_MANIFEST = "state/live-manifest.json"
LAST_PUBLISHED_REPORT = "state/last-published-report.json"


def run_key(run_id: str, name: str) -> str:
    return f"runs/{run_id}/{name}"


def aws_client(service: str):
    """The one place AWS clients are built — tests monkeypatch it."""
    return boto3.client(service, region_name=REGION)


def default_state_bucket(sts=None) -> str:
    """$STATE_BUCKET, else the CDK stack's fintank-pipeline-<account-id>."""
    if os.getenv("STATE_BUCKET"):
        return os.environ["STATE_BUCKET"]
    sts = sts or aws_client("sts")
    return f"fintank-pipeline-{sts.get_caller_identity()['Account']}"


def live_bucket() -> str:
    return os.getenv("LIVE_BUCKET", "thetradingfloor")


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound")


class LocalStore:
    def __init__(self, base_dir: str):
        self.base = base_dir

    def _path(self, key: str) -> str:
        return os.path.join(self.base, *key.split("/"))

    def get_json(self, key, default=None):
        try:
            with open(self._path(key)) as f:
                return json.load(f)
        except FileNotFoundError:
            return default

    def put_json(self, key, data):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def put_file(self, key, local_path):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(local_path, path)

    def exists(self, key):
        return os.path.exists(self._path(key))

    def list_prefixes(self, prefix):
        folder = self._path(prefix.rstrip("/"))
        if not os.path.isdir(folder):
            return []
        return sorted(f"{prefix}{name}/" for name in os.listdir(folder)
                      if os.path.isdir(os.path.join(folder, name)))

    def url(self, key):
        return self._path(key)


class S3Store:
    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or aws_client("s3")

    def get_json(self, key, default=None):
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as e:
            if _is_missing(e):
                return default
            raise
        return json.loads(body)

    def put_json(self, key, data):
        self.client.put_object(Bucket=self.bucket, Key=key,
                               Body=json.dumps(data, indent=2, default=str).encode(),
                               ContentType="application/json")

    def put_file(self, key, local_path):
        self.client.upload_file(local_path, self.bucket, key)

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if _is_missing(e):
                return False
            raise

    def list_prefixes(self, prefix):
        paginator = self.client.get_paginator("list_objects_v2")
        prefixes = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            prefixes += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
        return sorted(prefixes)

    def url(self, key):
        return (f"https://s3.console.aws.amazon.com/s3/object/{self.bucket}"
                f"?region={REGION}&prefix={key}")
```

- [ ] **Step 4: Create `backend/pipelines/report.py`**

```python
"""The record of one run: every stage's counts and timing, every check, and
the verdict. Saved as runs/<run-id>/report.json and summarised in emails."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import asdict, dataclass, field, fields

from pipelines.checks import CheckResult, verdict
from pipelines.results import StageResult


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _fmt_seconds(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{int(seconds % 60):02d}s"


@dataclass
class RunReport:
    run_id: str
    job: str                      # "weekly" | "news"
    mode: str                     # "lean" | "full" | "news"
    started_at: str
    dry_run: bool = False
    finished_at: str | None = None
    stages: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    factor_staleness: dict = field(default_factory=dict)
    staged_files: int = 0
    verdict: str | None = None

    def add_stage(self, result: StageResult, seconds: float) -> None:
        entry = result.to_dict()
        entry["seconds"] = round(seconds, 1)
        self.stages = [s for s in self.stages if s["name"] != result.name] + [entry]

    def stage(self, name: str) -> dict | None:
        return next((s for s in self.stages if s["name"] == name), None)

    def add_checks(self, results) -> None:
        self.checks.extend(r.to_dict() for r in results)

    def finish(self, verdict_override: str | None = None) -> None:
        self.verdict = verdict_override or verdict(CheckResult(**c) for c in self.checks)
        self.finished_at = now_iso()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunReport":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def summary(self) -> str:
        lines = [f"Run {self.run_id} ({self.job}, {self.mode}) — verdict: "
                 f"{(self.verdict or 'n/a').upper()}"]
        if self.dry_run:
            lines.append("DRY RUN — nothing was staged or published.")
        timing = f"Started {self.started_at}"
        if self.finished_at:
            elapsed = (dt.datetime.fromisoformat(self.finished_at)
                       - dt.datetime.fromisoformat(self.started_at)).total_seconds()
            timing += f", finished {self.finished_at} ({_fmt_seconds(elapsed)})"
        lines += [timing, "", "Stages:"]
        for s in self.stages:
            lines.append(
                f"  {s['name']:<30} {s['attempted']:>6} attempted {s['saved']:>6} saved "
                f"{s['failed']:>5} failed ({s.get('failure_rate', 0):.1%})  "
                f"{_fmt_seconds(s.get('seconds', 0))}")
        tally = Counter(c["status"] for c in self.checks)
        lines += ["", f"Checks: {tally.get('pass', 0)} pass, {tally.get('warn', 0)} warn, "
                      f"{tally.get('fail', 0)} fail"]
        for c in self.checks:
            if c["status"] != "pass":
                lines.append(f"  {c['status'].upper()} {c['name']} — {c['detail']}")
        if self.staged_files:
            lines += ["", f"Files that differ from live: {self.staged_files}"]
        return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): run report and local/S3 stores

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: State archives

**Files:**
- Create: `backend/pipelines/state.py`, `backend/pipelines/tests/test_state.py`

**Interfaces:**
- Consumes: S3 client (moto in tests).
- Produces: `state.STATE_PREFIX = "state/"`; `state_units(root) -> list[str]` (e.g. `"stock_data_json/stock_prices"`, `"index_data"`, `"stock_data/revenue_segments"`); `archive_key(unit)`; `push(client, bucket, root, units=None, since=None, log=print) -> list[str]` (units pushed); `pull(client, bucket, root, log=print) -> list[str]` (units restored; each local unit folder is replaced, not merged).

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_state.py`:

```python
import os
import time

import pytest

from pipelines import state


def make_tree(root):
    files = {
        "stock_data_json/stock_prices/sp500/AAA_prices.json": '{"a": 1}',
        "stock_data_json/ratios_ttm/sp500/AAA_ratios_ttm.json": "[]",
        "index_data/constituents/sp500_const_constituents.json": "[]",
        "stock_data/revenue_segments/AAA_segments.json": "{}",
        "stock_data/stock_prices/daily/sp500/AAA_prices.parquet": "not state",
    }
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    return files


def read_tree(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for name in names:
            path = os.path.join(dirpath, name)
            out[os.path.relpath(path, root)] = open(path).read()
    return out


def test_state_units(tmp_path):
    make_tree(tmp_path)
    assert state.state_units(str(tmp_path)) == [
        "stock_data_json/ratios_ttm", "stock_data_json/stock_prices",
        "index_data", "stock_data/revenue_segments"]


def test_push_then_pull_restores_state(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    src = tmp_path / "src"
    files = make_tree(src)
    pushed = state.push(aws, "state", str(src))
    assert len(pushed) == 4
    dest = tmp_path / "dest"
    restored = state.pull(aws, "state", str(dest))
    assert sorted(restored) == sorted(pushed)
    expected = {k: v for k, v in files.items() if not k.startswith("stock_data/stock_prices")}
    assert read_tree(dest) == expected


def test_push_since_only_sends_changed_units(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    make_tree(tmp_path)
    old = time.time() - 3600
    for dirpath, _, names in os.walk(tmp_path):
        for name in names:
            os.utime(os.path.join(dirpath, name), (old, old))
    marker = time.time() - 60
    with open(tmp_path / "stock_data_json/stock_prices/sp500/AAA_prices.json", "w") as f:
        f.write('{"a": 2}')
    assert state.push(aws, "state", str(tmp_path), since=marker) == [
        "stock_data_json/stock_prices"]


def test_pull_replaces_local_unit(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    make_tree(tmp_path)
    state.push(aws, "state", str(tmp_path))
    stray = tmp_path / "index_data/constituents/stray.json"
    stray.write_text("[]")
    state.pull(aws, "state", str(tmp_path))
    assert not stray.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_state.py -q`
Expected: FAIL — `ImportError: cannot import name 'state'`.

- [ ] **Step 3: Create `backend/pipelines/state.py`**

```python
"""The pipeline's raw inputs live in the state bucket as one .tar.zst per
folder ("unit"): the merged FMP/FRED JSON, the index price parquets the index
fetcher self-detects from, the constituent lists and the revenue segments.

A run pulls every unit, then pushes back only the units a stage changed — so a
crashed run resumes from its last finished fetch stage. Built parquets are not
state: every run rebuilds them from the JSON."""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile

import zstandard as zstd

STATE_PREFIX = "state/"
SUFFIX = ".tar.zst"
# Split one level down so a prices-only change doesn't re-upload statements.
SPLIT_ROOTS = ("stock_data_json",)
WHOLE_UNITS = ("index_data", "stock_data/revenue_segments")


def state_units(root: str) -> list[str]:
    units = []
    for split in SPLIT_ROOTS:
        base = os.path.join(root, split)
        if os.path.isdir(base):
            units += [f"{split}/{name}" for name in sorted(os.listdir(base))
                      if os.path.isdir(os.path.join(base, name))]
    units += [u for u in WHOLE_UNITS if os.path.isdir(os.path.join(root, u))]
    return units


def archive_key(unit: str) -> str:
    return f"{STATE_PREFIX}{unit}{SUFFIX}"


def _changed_since(root: str, unit: str, since: float) -> bool:
    for dirpath, _, names in os.walk(os.path.join(root, unit)):
        for name in names:
            if os.path.getmtime(os.path.join(dirpath, name)) > since:
                return True
    return False


def _write_archive(root: str, unit: str, out_path: str) -> None:
    compressor = zstd.ZstdCompressor(level=3, threads=-1)
    with open(out_path, "wb") as fh, compressor.stream_writer(fh) as zw, \
            tarfile.open(fileobj=zw, mode="w|") as tar:
        tar.add(os.path.join(root, unit), arcname=unit)


def _extract_archive(path: str, root: str) -> None:
    with open(path, "rb") as fh, zstd.ZstdDecompressor().stream_reader(fh) as zr, \
            tarfile.open(fileobj=zr, mode="r|") as tar:
        tar.extractall(root, filter="data")


def push(client, bucket, root, units=None, since=None, log=print) -> list[str]:
    """Archive and upload units. With `since` (epoch seconds), only units
    holding a file modified after it."""
    units = state_units(root) if units is None else units
    pushed = []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "unit" + SUFFIX)
        for unit in units:
            if since is not None and not _changed_since(root, unit, since):
                continue
            _write_archive(root, unit, out)
            size_mb = os.path.getsize(out) / 1e6
            client.upload_file(out, bucket, archive_key(unit))
            os.remove(out)
            pushed.append(unit)
            log(f"state: pushed {unit} ({size_mb:,.1f} MB)")
    return pushed


def pull(client, bucket, root, log=print) -> list[str]:
    """Download and unpack every unit, replacing each local unit folder."""
    paginator = client.get_paginator("list_objects_v2")
    keys = [obj["Key"]
            for page in paginator.paginate(Bucket=bucket, Prefix=STATE_PREFIX)
            for obj in page.get("Contents", [])
            if obj["Key"].endswith(SUFFIX)]
    restored = []
    os.makedirs(root, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, "unit" + SUFFIX)
        for key in sorted(keys):
            unit = key[len(STATE_PREFIX):-len(SUFFIX)]
            client.download_file(bucket, key, local)
            shutil.rmtree(os.path.join(root, unit), ignore_errors=True)
            _extract_archive(local, root)
            os.remove(local)
            restored.append(unit)
            log(f"state: pulled {unit}")
    return restored
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): state archives (.tar.zst per folder) push and pull

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Outputs, diff, staging, publish, rollback

**Files:**
- Create: `backend/pipelines/outputs.py`, `backend/pipelines/publish.py`, `backend/pipelines/tests/test_outputs.py`, `backend/pipelines/tests/test_publish.py`

**Interfaces:**
- Consumes: `StockDataPipeline` paths (Task 1), `S3Store`, `run_key`, `LIVE_MANIFEST`, `LAST_PUBLISHED_REPORT` (Task 5).
- Produces:
  - `outputs.Output(local_path, key, dataset)` (frozen dataclass); `outputs.DATASET_ORDER`; `outputs.collect_outputs(p) -> list[Output]` in publish order, unique by key.
  - `publish.sha256_file(path)`; `publish.diff_outputs(outputs, live_manifest: dict, workers=8) -> list[dict]` (`{"key","local_path","dataset","sha256"}`); `publish.stage_changed(client, state_bucket, run_id, changed, workers=32, log=print)`; `publish.publish(client, state_bucket, live_bucket, run_id, workers=32, log=print) -> {"published": int, "by_dataset": {dataset: int}}`; `publish.rollback(client, state_bucket, live_bucket, run_id, log=print) -> int`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_outputs.py`:

```python
import os

from pipelines.outputs import DATASET_ORDER, collect_outputs


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def test_keys_match_the_upload_methods(pipeline):
    p, r = pipeline, pipeline.root
    touch(p.constituents_path("sp500_const"))
    touch(os.path.join(p.index_prices_dir, "daily", "sp500_prices.parquet"))
    touch(os.path.join(p.price_parquet_dir("daily", "sp500"), "AAA_prices.parquet"))
    touch(os.path.join(p.price_parquet_dir("daily", "nas"), "AAA_prices.parquet"))
    touch(os.path.join(p.parquet_root, "ratios_ttm", "sp500", "AAA_ratios_ttm.parquet"))
    touch(os.path.join(p.revenue_segments_dir, "AAA_segments.json"))
    touch(os.path.join(p.contr_to_var_dir, "sp500_contr_to_var.parquet"))
    touch(os.path.join(p.factor_metrics_dir, "sp500_metrics_returns.parquet"))
    touch(os.path.join(p.parquet_root, "company_profiles", "company_profiles.parquet"))
    touch(os.path.join(p.parquet_root, "long_profiles", "long_profiles.parquet"))
    touch(os.path.join(p.econ_dir, "cpi.parquet"))
    touch(os.path.join(p.econ_dir, "relative_perf", "eafevg.parquet"))

    keys = [(o.dataset, o.key) for o in collect_outputs(p)]
    assert keys == [
        ("constituents", "index_data/constituents/sp500_const_constituents.json"),
        ("index_prices", "index_data/index_prices_v2/daily/sp500_prices.parquet"),
        ("stock_prices", "stock_data/stock_prices/daily/AAA_prices.parquet"),  # once
        ("fundamentals", "stock_data/ratios_ttm/AAA_ratios_ttm.parquet"),
        ("revenue_segments", "stock_data/revenue_segments/AAA_segments.json"),
        ("contr_to_var", "index_data/contr_to_var/sp500_contr_to_var.parquet"),
        ("factor_metrics", "stock_data/factor_metrics/sp500_metrics_returns.parquet"),
        ("profile_aggregates", "stock_data/company_profiles/company_profiles.parquet"),
        ("profile_aggregates", "stock_data/long_profiles/long_profiles.parquet"),
        ("econ", "econ_data/cpi.parquet"),
        ("econ", "econ_data/relative_perf/eafevg.parquet"),
    ]
    assert [d for d, _ in keys] == sorted((d for d, _ in keys), key=DATASET_ORDER.index)
```

`backend/pipelines/tests/test_publish.py`:

```python
import json

import pytest

from pipelines import publish
from pipelines.outputs import Output
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key


@pytest.fixture
def buckets(aws):
    aws.create_bucket(Bucket="state")
    aws.create_bucket(Bucket="live")
    aws.put_bucket_versioning(Bucket="live",
                              VersioningConfiguration={"Status": "Enabled"})
    return aws


def make_outputs(tmp_path, contents):
    outs = []
    for key, text in contents.items():
        path = tmp_path / key.replace("/", "__")
        path.write_text(text)
        dataset = "econ" if key.startswith("econ") else "stock_prices"
        outs.append(Output(str(path), key, dataset))
    return outs


def live_body(client, key):
    return client.get_object(Bucket="live", Key=key)["Body"].read().decode()


def do_run(client, tmp_path, run_id, contents):
    store = S3Store("state", client)
    store.put_json(run_key(run_id, "report.json"), {"run_id": run_id, "counts": {}})
    outs = make_outputs(tmp_path, contents)
    changed = publish.diff_outputs(outs, store.get_json(LIVE_MANIFEST, {}))
    publish.stage_changed(client, "state", run_id, changed)
    return changed, publish.publish(client, "state", "live", run_id)


def test_first_run_publishes_everything_then_nothing(buckets, tmp_path):
    contents = {"stock_data/stock_prices/daily/A.parquet": "a1", "econ_data/cpi.parquet": "c1"}
    changed, result = do_run(buckets, tmp_path, "r1", contents)
    assert len(changed) == 2
    assert result == {"published": 2, "by_dataset": {"stock_prices": 1, "econ": 1}}
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"
    head = buckets.head_object(Bucket="live", Key="econ_data/cpi.parquet")
    assert head["Metadata"]["sha256"] == publish.sha256_file(changed[1]["local_path"])
    store = S3Store("state", buckets)
    assert store.get_json(LAST_PUBLISHED_REPORT)["run_id"] == "r1"
    outs = make_outputs(tmp_path, contents)
    assert publish.diff_outputs(outs, store.get_json(LIVE_MANIFEST)) == []


def test_staged_in_publish_order(buckets, tmp_path):
    contents = {"econ_data/cpi.parquet": "c1", "stock_data/stock_prices/daily/A.parquet": "a1"}
    outs = make_outputs(tmp_path, contents)
    changed = publish.diff_outputs(outs, {})
    publish.stage_changed(buckets, "state", "r1", changed)
    manifest = S3Store("state", buckets).get_json(run_key("r1", "stage-manifest.json"))
    assert [f["dataset"] for f in manifest["files"]] == ["stock_prices", "econ"]


def test_rollback_restores_previous_versions_and_removes_new_keys(buckets, tmp_path):
    do_run(buckets, tmp_path, "r1", {"econ_data/cpi.parquet": "c1"})
    do_run(buckets, tmp_path, "r2", {"econ_data/cpi.parquet": "c2",
                                     "econ_data/new.parquet": "n2"})
    assert live_body(buckets, "econ_data/cpi.parquet") == "c2"

    assert publish.rollback(buckets, "state", "live", "r2") == 2
    assert live_body(buckets, "econ_data/cpi.parquet") == "c1"
    with pytest.raises(buckets.exceptions.NoSuchKey):
        buckets.get_object(Bucket="live", Key="econ_data/new.parquet")
    manifest = S3Store("state", buckets).get_json(LIVE_MANIFEST)
    assert "econ_data/new.parquet" not in manifest
    outs = make_outputs(tmp_path, {"econ_data/cpi.parquet": "c1"})
    assert publish.diff_outputs(outs, manifest) == []


def test_parquet_output_is_byte_stable(tmp_path):
    """The diff relies on identical input producing identical bytes; otherwise
    every run re-publishes every parquet (correct, just slower and dearer)."""
    import pandas as pd
    from pipelines.stock_pipeline import StockDataPipeline
    df = pd.DataFrame({"adjClose": [1.0, 2.0]},
                      index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    a, b = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    StockDataPipeline._write_parquet(df, a)
    StockDataPipeline._write_parquet(df, b)
    assert publish.sha256_file(a) == publish.sha256_file(b)


def test_publish_refuses_unversioned_live_bucket(aws, tmp_path):
    aws.create_bucket(Bucket="state")
    aws.create_bucket(Bucket="live")
    with pytest.raises(RuntimeError, match="versioning"):
        publish.publish(aws, "state", "live", "r1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_outputs.py pipelines/tests/test_publish.py -q`
Expected: FAIL — `ImportError` for `pipelines.outputs` / `pipelines.publish`.

- [ ] **Step 3: Create `backend/pipelines/outputs.py`**

```python
"""Every file a run produces for the live bucket, and the exact key it goes
to. The keys reproduce what the upload_* methods in stock_pipeline.py write —
the site reads these, so a key change is a site outage."""
from __future__ import annotations

import os
from dataclasses import dataclass

from pipelines.stock_pipeline import cfg

# Publish order: per-symbol data first, the aggregates the site reads as
# "LIVE" last, so a page never sees new aggregates before their inputs.
DATASET_ORDER = ["constituents", "index_prices", "stock_prices", "fundamentals",
                 "revenue_segments", "contr_to_var", "factor_metrics",
                 "profile_aggregates", "econ"]


@dataclass(frozen=True)
class Output:
    local_path: str
    key: str
    dataset: str


def _files(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f)))


def collect_outputs(p) -> list[Output]:
    out = []

    def add(folder, prefix, dataset):
        out.extend(Output(os.path.join(folder, name), f"{prefix}/{name}", dataset)
                   for name in _files(folder))

    add(os.path.join(p.index_root, "constituents"), "index_data/constituents",
        "constituents")
    for freq in ("daily", "monthly"):
        add(os.path.join(p.index_prices_dir, freq),
            f"index_data/index_prices_v2/{freq}", "index_prices")
    # upload_stock_prices drops the sub-universe folder from the key.
    for freq in ("daily", "monthly"):
        for sub in cfg.ALL_SUB_UNIVERSES:
            add(p.price_parquet_dir(freq, sub), f"stock_data/stock_prices/{freq}",
                "stock_prices")
    # upload_fundamentals drops it too.
    for data_type in cfg.FUNDAMENTALS_DATASETS:
        for sub in cfg.ALL_SUB_UNIVERSES:
            add(os.path.join(p.parquet_root, data_type, sub),
                f"stock_data/{data_type}", "fundamentals")
    add(p.revenue_segments_dir, "stock_data/revenue_segments", "revenue_segments")
    add(p.contr_to_var_dir, "index_data/contr_to_var", "contr_to_var")
    add(p.factor_metrics_dir, "stock_data/factor_metrics", "factor_metrics")
    for name in p.PROFILE_AGGREGATES:
        path = os.path.join(p.parquet_root, name, f"{name}.parquet")
        if os.path.isfile(path):
            out.append(Output(path, f"stock_data/{name}/{name}.parquet",
                              "profile_aggregates"))
    add(p.econ_dir, "econ_data", "econ")
    add(os.path.join(p.econ_dir, "relative_perf"), "econ_data/relative_perf", "econ")

    # A symbol in two lists maps to one key with identical content: keep the first.
    seen, unique = set(), []
    for output in out:
        if output.key not in seen:
            seen.add(output.key)
            unique.append(output)
    return unique
```

- [ ] **Step 4: Create `backend/pipelines/publish.py`**

```python
"""Diff → stage → publish → rollback.

The live bucket is only ever written by publish(), by server-side copies of
files a run staged in the state bucket — so an approval days later needs no
local data. Which files changed is decided against state/live-manifest.json
({key: sha256}), which publish() and rollback() keep current (plan ruling R1).
Every published object also carries its sha256 as x-amz-meta-sha256."""
from __future__ import annotations

import hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from pipelines.outputs import DATASET_ORDER
from pipelines.report import now_iso
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def diff_outputs(outputs, live_manifest: dict, workers: int = 8) -> list[dict]:
    """Outputs whose content differs from what live holds, in input order."""
    with ThreadPoolExecutor(workers) as pool:
        hashes = list(pool.map(lambda o: sha256_file(o.local_path), outputs))
    return [{"key": o.key, "local_path": o.local_path, "dataset": o.dataset, "sha256": h}
            for o, h in zip(outputs, hashes) if live_manifest.get(o.key) != h]


def stage_changed(client, state_bucket, run_id, changed, workers=32, log=print) -> None:
    def upload(entry):
        client.upload_file(entry["local_path"], state_bucket,
                           run_key(run_id, f"stage/{entry['key']}"))

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(upload, changed))
    ordered = sorted(changed, key=lambda e: DATASET_ORDER.index(e["dataset"]))
    S3Store(state_bucket, client).put_json(run_key(run_id, "stage-manifest.json"), {
        "run_id": run_id,
        "files": [{k: e[k] for k in ("key", "sha256", "dataset")} for e in ordered],
    })
    log(f"staged {len(changed)} changed files for {run_id}")


def _current_version(client, bucket, key):
    try:
        return client.head_object(Bucket=bucket, Key=key).get("VersionId")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def publish(client, state_bucket, live_bucket, run_id, workers=32, log=print) -> dict:
    versioning = client.get_bucket_versioning(Bucket=live_bucket).get("Status")
    if versioning != "Enabled":
        raise RuntimeError(f"s3://{live_bucket} versioning is {versioning or 'off'} — "
                           "enable it first (setup step 3), or rollback is impossible")
    store = S3Store(state_bucket, client)
    staged = store.get_json(run_key(run_id, "stage-manifest.json"))
    if staged is None:
        raise RuntimeError(f"nothing staged for {run_id}")
    live = store.get_json(LIVE_MANIFEST, {})
    published = []

    def copy(entry):
        previous = _current_version(client, live_bucket, entry["key"])
        response = client.copy_object(
            Bucket=live_bucket, Key=entry["key"],
            CopySource={"Bucket": state_bucket,
                        "Key": run_key(run_id, f"stage/{entry['key']}")},
            Metadata={"sha256": entry["sha256"]}, MetadataDirective="REPLACE")
        return {"key": entry["key"], "dataset": entry["dataset"],
                "sha256": entry["sha256"], "previous_sha256": live.get(entry["key"]),
                "previous_version": previous, "new_version": response.get("VersionId")}

    for dataset in DATASET_ORDER:
        group = [f for f in staged["files"] if f["dataset"] == dataset]
        if not group:
            continue
        with ThreadPoolExecutor(workers) as pool:
            done = list(pool.map(copy, group))
        published += done
        for entry in done:
            live[entry["key"]] = entry["sha256"]
        # Checkpoint after each dataset so a crash mid-publish can still be rolled back.
        store.put_json(run_key(run_id, "publish-manifest.json"),
                       {"run_id": run_id, "published_at": now_iso(), "files": published})
        store.put_json(LIVE_MANIFEST, live)
        log(f"published {len(done)} {dataset} files")

    store.put_json(run_key(run_id, "publish-manifest.json"),
                   {"run_id": run_id, "published_at": now_iso(), "files": published})
    report = store.get_json(run_key(run_id, "report.json"))
    if report is not None:
        store.put_json(LAST_PUBLISHED_REPORT, report)
    by_dataset = Counter(e["dataset"] for e in published)
    return {"published": len(published),
            "by_dataset": {d: by_dataset[d] for d in DATASET_ORDER if by_dataset[d]}}


def rollback(client, state_bucket, live_bucket, run_id, log=print) -> int:
    store = S3Store(state_bucket, client)
    manifest = store.get_json(run_key(run_id, "publish-manifest.json"))
    if manifest is None:
        raise RuntimeError(f"{run_id} has no publish manifest — nothing to roll back")
    live = store.get_json(LIVE_MANIFEST, {})
    for entry in reversed(manifest["files"]):
        key = entry["key"]
        if entry["previous_version"]:
            client.copy_object(Bucket=live_bucket, Key=key, MetadataDirective="COPY",
                               CopySource={"Bucket": live_bucket, "Key": key,
                                           "VersionId": entry["previous_version"]})
            if entry["previous_sha256"]:
                live[key] = entry["previous_sha256"]
            else:
                live.pop(key, None)       # pre-manifest object: next run re-diffs it
        else:
            client.delete_object(Bucket=live_bucket, Key=key)
            live.pop(key, None)
    store.put_json(LIVE_MANIFEST, live)
    store.put_json(run_key(run_id, "rollback.json"),
                   {"rolled_back_at": now_iso(), "files": len(manifest["files"])})
    log(f"rolled back {len(manifest['files'])} files from {run_id}")
    return len(manifest["files"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): output keys, diff/stage/publish and rollback

Live keys reproduce the upload_* methods; publish copies staged files server
side, in dataset order, and refuses an unversioned live bucket.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: Notifications and the weekly runner

**Files:**
- Create: `backend/pipelines/notify.py`, `backend/pipelines/runner.py`, `backend/pipelines/tests/test_notify.py`, `backend/pipelines/tests/test_runner.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7.
- Produces:
  - `notify.Notifier(topic_arn=None, client=None, log=print).send(subject, message)` (SNS when a topic ARN is given or `$SNS_TOPIC_ARN` is set, else prints); `notify.report_url(state_bucket, run_id)`; message builders returning `(subject, body)`: `held_message(report, state_bucket, always_hold)`, `complete_message(report, publish_result, state_bucket)`, `news_message(report, uploaded, state_bucket)`, `crash_message(job, run_id, error_text)`.
  - `runner.BUILD_STAGES`, `LEAN_STAGES`, `FULL_STAGES`, `CHECKPOINTED`; `resolve_mode(mode, today) -> "lean"|"full"`; `make_run_id(mode, now) -> "<mode>-YYYYMMDD-HHMM"`; `RunContext(pipeline, store, run_id, mode, dry_run=False, limit=None, s3=None, state_bucket=None, notifier=None, always_hold=False, today=date.today(), log=print)`; `run_weekly(ctx, checks=None, staging=None) -> RunReport` (writes `runs/<id>/progress.json`, `report.json`, `verdict.json` = `{"run_id", "verdict", "hold"}`); `run_checks(ctx, report)`; `stage_outputs(ctx, report)`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_notify.py`:

```python
from pipelines.checks import CheckResult
from pipelines.notify import (Notifier, complete_message, crash_message,
                              held_message, news_message)
from pipelines.report import RunReport


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


def report(verdict="warn"):
    r = RunReport("lean-20261017-1000", "weekly", "lean", "2026-10-17T10:00:00+00:00")
    r.add_checks([CheckResult("freshness.tsx", verdict, 1, 1, "1 session behind")])
    r.finish()
    return r


def test_without_topic_prints(capsys):
    Notifier(topic_arn="").send("Subject", "Body")
    assert "Subject" in capsys.readouterr().out


def test_with_topic_publishes_and_truncates_subject():
    sns = FakeSns()
    Notifier(topic_arn="arn:topic", client=sns).send("x" * 150, "Body")
    assert sns.published == [{"TopicArn": "arn:topic", "Subject": "x" * 100,
                              "Message": "Body"}]


def test_held_message_has_commands_and_reason():
    subject, body = held_message(report("warn"), "state-bucket", always_hold=False)
    assert subject == "[Fintank] Weekly run lean-20261017-1000 held - WARN"
    assert "python -m pipelines approve lean-20261017-1000" in body
    assert "python -m pipelines discard lean-20261017-1000" in body
    assert "a check did not pass" in body
    _, body = held_message(report("pass"), "state-bucket", always_hold=True)
    assert "ALWAYS_HOLD" in body


def test_complete_message_lists_datasets_and_rollback():
    subject, body = complete_message(
        report("pass"), {"published": 12, "by_dataset": {"stock_prices": 10, "econ": 2}},
        "state-bucket")
    assert subject == "[Fintank] Weekly run lean-20261017-1000 published - 12 files"
    assert "stock_prices: 10" in body
    assert "python -m pipelines rollback lean-20261017-1000" in body


def test_subjects_are_ascii():
    for subject, _ in (held_message(report(), "b", False),
                       complete_message(report("pass"), {"published": 1, "by_dataset": {}}, "b"),
                       crash_message("run", "lean-1", "x")):
        assert subject.isascii(), subject


def test_news_and_crash_messages():
    r = RunReport("news-20261017-0930", "news", "news", "2026-10-17T09:30:00+00:00")
    r.finish(verdict_override="pass")
    subject, _ = news_message(r, 28, "state-bucket")
    assert subject == "[Fintank] News news-20261017-0930 - PASS, 28 files updated"
    subject, body = crash_message("run", "lean-1", "Traceback ... ?apikey=SECRET")
    assert subject == "[Fintank] run lean-1 crashed"
    assert "SECRET" not in body
```

`backend/pipelines/tests/test_runner.py`:

```python
import datetime as dt

import pytest

from pipelines import runner
from pipelines.checks import CheckResult
from pipelines.report import RunReport
from pipelines.results import StageResult
from pipelines.store import LocalStore, run_key
from pipelines.tests.helpers import write_constituents, write_price_json


class FakePipeline:
    def __init__(self, root, fail_on=None):
        self.root = root
        self.calls = []
        self.fail_on = fail_on

    def __getattr__(self, name):
        if not name.startswith(("refresh_", "fetch_", "build_")):
            raise AttributeError(name)

        def stage(**kwargs):
            self.calls.append((name, kwargs))
            if name == self.fail_on:
                raise RuntimeError(f"{name} blew up")
            return StageResult(name, attempted=1, saved=1)
        return stage


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, subject, message):
        self.sent.append(subject)


def adds(status):
    return lambda ctx, report: report.add_checks([CheckResult("x", status)])


def nothing(ctx, report):
    pass


def make_ctx(tmp_path, pipeline=None, **kwargs):
    defaults = dict(pipeline=pipeline or FakePipeline(str(tmp_path / "data")),
                    store=LocalStore(str(tmp_path / "store")), run_id="lean-1",
                    mode="lean", dry_run=True, log=lambda *a: None)
    defaults.update(kwargs)
    return runner.RunContext(**defaults)


def test_resolve_mode():
    assert runner.resolve_mode("auto", dt.date(2026, 11, 7)) == "full"
    assert runner.resolve_mode("auto", dt.date(2026, 11, 8)) == "lean"
    assert runner.resolve_mode("lean", dt.date(2026, 11, 1)) == "lean"
    with pytest.raises(ValueError):
        runner.resolve_mode("weekly", dt.date(2026, 11, 1))


def test_make_run_id():
    assert runner.make_run_id("lean", dt.datetime(2026, 10, 17, 10, 0)) == "lean-20261017-1000"


def test_full_adds_the_quarterly_fetches():
    assert set(runner.FULL_STAGES) - set(runner.LEAN_STAGES) == {
        "fetch_profiles", "fetch_etf_profiles", "fetch_financial_statements",
        "fetch_ratios", "fetch_revenue_segments"}
    assert runner.LEAN_STAGES[0] == "refresh_constituents"
    assert runner.LEAN_STAGES[-len(runner.BUILD_STAGES):] == runner.BUILD_STAGES


def test_lean_order_and_arguments(tmp_path):
    ctx = make_ctx(tmp_path, limit=5)
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    calls = dict(ctx.pipeline.calls)
    assert [name for name, _ in ctx.pipeline.calls] == runner.LEAN_STAGES
    assert calls["fetch_stock_prices"] == {"from_date": "1999-01-01", "limit": 5}
    assert calls["fetch_sector_history"] == {"from_date": "2010-01-01"}
    assert calls["refresh_constituents"] == {}


def test_resume_skips_checkpointed_stages_but_rebuilds(tmp_path):
    first = make_ctx(tmp_path, pipeline=FakePipeline(str(tmp_path), fail_on="fetch_ttm_ratios"))
    with pytest.raises(RuntimeError):
        runner.run_weekly(first, checks=adds("pass"), staging=nothing)
    second = make_ctx(tmp_path, pipeline=FakePipeline(str(tmp_path)))
    runner.run_weekly(second, checks=adds("pass"), staging=nothing)
    names = [name for name, _ in second.pipeline.calls]
    assert names[0] == "fetch_ttm_ratios"
    assert names[-len(runner.BUILD_STAGES):] == runner.BUILD_STAGES
    report = second.store.get_json(run_key("lean-1", "report.json"))
    assert {s["name"] for s in report["stages"]} == set(runner.LEAN_STAGES)


def test_warn_holds_and_notifies(tmp_path):
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, notifier=notifier)
    report = runner.run_weekly(ctx, checks=adds("warn"), staging=nothing)
    assert report.verdict == "warn"
    assert ctx.store.get_json(run_key("lean-1", "verdict.json")) == {
        "run_id": "lean-1", "verdict": "warn", "hold": True}
    assert notifier.sent == ["[Fintank] Weekly run lean-1 held - WARN"]


@pytest.mark.parametrize("always_hold,hold,emails", [(True, True, 1), (False, False, 0)])
def test_pass_publishes_unless_always_hold(tmp_path, always_hold, hold, emails):
    notifier = FakeNotifier()
    ctx = make_ctx(tmp_path, notifier=notifier, always_hold=always_hold)
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    assert ctx.store.get_json(run_key("lean-1", "verdict.json"))["hold"] is hold
    assert len(notifier.sent) == emails


def test_real_run_pulls_and_pushes_state(tmp_path, monkeypatch):
    pulled, pushed = [], []
    monkeypatch.setattr(runner.state, "pull", lambda *a, **kw: pulled.append(a))
    monkeypatch.setattr(runner.state, "push", lambda *a, **kw: pushed.append(kw["since"]))
    ctx = make_ctx(tmp_path, dry_run=False, s3=object(), state_bucket="state")
    runner.run_weekly(ctx, checks=adds("pass"), staging=nothing)
    assert len(pulled) == 1
    assert len(pushed) == len([s for s in runner.LEAN_STAGES if s in runner.CHECKPOINTED])


def test_run_checks_on_fixture_data(pipeline, tmp_path):
    write_constituents(pipeline, "sp500_const", ["AAA"])
    write_price_json(pipeline, "sp500", "AAA", "2026-10-09")
    pipeline.build_price_parquets(sub_universes=["sp500"])
    ctx = make_ctx(tmp_path, pipeline=pipeline, today=dt.date(2026, 10, 10))
    report = RunReport("lean-1", "weekly", "lean", "2026-10-10T10:00:00+00:00", dry_run=True)
    report.add_stage(StageResult("fetch_stock_prices", attempted=1, saved=1), 1.0)
    runner.run_checks(ctx, report)
    runner.stage_outputs(ctx, report)
    by_name = {c["name"]: c["status"] for c in report.checks}
    assert by_name["freshness.sp500"] == "pass"
    assert by_name["fetch_stock_prices.failure_rate"] == "pass"
    assert by_name["readable.stock_prices"] == "pass"
    assert by_name["counts"] == "pass"
    assert by_name["prices.non_positive"] == "pass"
    assert by_name["staging"] == "pass"
    assert report.counts["stock_prices"] == 2           # daily + monthly
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_notify.py pipelines/tests/test_runner.py -q`
Expected: FAIL — `ImportError` for `pipelines.notify` / `pipelines.runner`.

- [ ] **Step 3: Create `backend/pipelines/notify.py`**

```python
"""Emails. On AWS they go to the SNS topic (SNS_TOPIC_ARN); locally they print.

Python sends the emails whose content needs run detail — held, published,
news, crashed. The state machines send started / failed / discarded."""
from __future__ import annotations

import os

from pipelines.results import redact
from pipelines.store import REGION, aws_client

SUBJECT_MAX = 100   # SNS limit; subjects must also be plain ASCII (no em dashes)


def report_url(state_bucket, run_id) -> str:
    if not state_bucket:
        return "(dry run — report saved locally)"
    return (f"https://s3.console.aws.amazon.com/s3/object/{state_bucket}"
            f"?region={REGION}&prefix=runs/{run_id}/report.json")


class Notifier:
    def __init__(self, topic_arn=None, client=None, log=print):
        self.topic_arn = os.getenv("SNS_TOPIC_ARN") if topic_arn is None else topic_arn
        self._client = client
        self.log = log

    def send(self, subject: str, message: str) -> None:
        subject = subject[:SUBJECT_MAX]
        if not self.topic_arn:
            self.log(f"[notify] {subject}\n{message}")
            return
        client = self._client or aws_client("sns")
        client.publish(TopicArn=self.topic_arn, Subject=subject, Message=message)


def held_message(report, state_bucket, always_hold) -> tuple[str, str]:
    reason = ("a check did not pass" if report.verdict != "pass"
              else "ALWAYS_HOLD is on (the go-live guard)")
    subject = f"[Fintank] Weekly run {report.run_id} held - {report.verdict.upper()}"
    body = (f"Held for your approval because {reason}.\n\n{report.summary()}\n\n"
            f"Publish:  python -m pipelines approve {report.run_id}\n"
            f"Discard:  python -m pipelines discard {report.run_id}\n"
            "Unanswered runs are discarded automatically after 7 days.\n\n"
            f"Report: {report_url(state_bucket, report.run_id)}")
    return subject, body


def complete_message(report, publish_result, state_bucket) -> tuple[str, str]:
    subject = (f"[Fintank] Weekly run {report.run_id} published - "
               f"{publish_result['published']} files")
    datasets = "\n".join(f"  {name}: {count}"
                         for name, count in publish_result["by_dataset"].items())
    body = (f"Published {publish_result['published']} changed files:\n{datasets}\n\n"
            f"{report.summary()}\n\n"
            f"Undo:    python -m pipelines rollback {report.run_id}\n"
            f"Report:  {report_url(state_bucket, report.run_id)}")
    return subject, body


def news_message(report, uploaded, state_bucket) -> tuple[str, str]:
    subject = (f"[Fintank] News {report.run_id} - {report.verdict.upper()}, "
               f"{uploaded} files updated")
    return subject, f"{report.summary()}\n\nReport: {report_url(state_bucket, report.run_id)}"


def crash_message(job, run_id, error_text) -> tuple[str, str]:
    return (f"[Fintank] {job} {run_id} crashed",
            f"The {job} command for {run_id} crashed. Nothing was published by "
            f"this step.\n\n{redact(error_text)}")
```

- [ ] **Step 4: Create `backend/pipelines/runner.py`**

```python
"""The weekly run: which stages, in what order, with resume.

Fetch stages (and the constituent refresh) are checkpointed: when one
finishes, the state folders it changed are pushed to the state bucket and
progress.json records it, so a retried run skips it. Build stages are never
checkpointed — their outputs live on the container's disk, so a fresh
container rebuilds them from the pulled JSON."""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from pipelines import state
from pipelines.checks import (PASS, CheckResult, check_constituents, check_counts,
                              check_econ, check_factor_staleness, check_fetch,
                              check_freshness, check_outputs_readable,
                              check_price_sanity, check_staging, recent_nyse_sessions)
from pipelines.notify import held_message
from pipelines.outputs import collect_outputs
from pipelines.publish import diff_outputs, stage_changed
from pipelines.report import RunReport, now_iso
from pipelines.results import StageResult
from pipelines.store import LAST_PUBLISHED_REPORT, LIVE_MANIFEST, S3Store, run_key

BUILD_STAGES = [
    "build_price_parquets", "build_fundamentals_parquets", "build_profile_aggregate",
    "build_factor_metrics", "build_contr_to_var", "build_econ_parquets",
    "build_relative_performance",
]
LEAN_STAGES = [
    "refresh_constituents", "fetch_stock_prices", "fetch_etf_prices",
    "fetch_ttm_ratios", "fetch_sector_history", "fetch_index_prices",
    "fetch_fred_series", *BUILD_STAGES,
]
FULL_STAGES = [
    "refresh_constituents", "fetch_stock_prices", "fetch_etf_prices",
    "fetch_profiles", "fetch_etf_profiles", "fetch_financial_statements",
    "fetch_ratios", "fetch_ttm_ratios", "fetch_revenue_segments",
    "fetch_sector_history", "fetch_index_prices", "fetch_fred_series", *BUILD_STAGES,
]
CHECKPOINTED = frozenset(s for s in FULL_STAGES if s not in BUILD_STAGES)

# The arguments the notebooks used. A full-history price window costs the same
# number of calls and avoids the gap and split-seam problems (see
# fetch_stock_prices.__doc__).
FROM_DATES = {"fetch_stock_prices": "1999-01-01", "fetch_etf_prices": "1999-01-01",
              "fetch_sector_history": "2010-01-01"}
LIMITABLE = frozenset({
    "fetch_stock_prices", "fetch_etf_prices", "fetch_profiles", "fetch_etf_profiles",
    "fetch_financial_statements", "fetch_ratios", "fetch_ttm_ratios",
    "fetch_revenue_segments", "build_price_parquets", "build_fundamentals_parquets",
    "build_factor_metrics",
})


def resolve_mode(mode: str, today: dt.date) -> str:
    if mode in ("lean", "full"):
        return mode
    if mode == "auto":
        return "full" if today.day <= 7 else "lean"
    raise ValueError(f"unknown mode {mode!r}")


def make_run_id(mode: str, now: dt.datetime) -> str:
    return f"{mode}-{now:%Y%m%d-%H%M}"


def stages_for(mode: str) -> list[str]:
    return FULL_STAGES if mode == "full" else LEAN_STAGES


def call_stage(p, name, limit=None) -> StageResult:
    kwargs = {}
    if name in FROM_DATES:
        kwargs["from_date"] = FROM_DATES[name]
    if limit is not None and name in LIMITABLE:
        kwargs["limit"] = limit
    return getattr(p, name)(**kwargs)


@dataclass
class RunContext:
    pipeline: object
    store: object                  # LocalStore (dry run) or S3Store
    run_id: str
    mode: str
    dry_run: bool = False
    limit: int | None = None
    s3: object = None              # S3 client; unused in dry runs
    state_bucket: str | None = None
    notifier: object = None
    always_hold: bool = False
    today: dt.date = field(default_factory=dt.date.today)
    log: object = print


def run_weekly(ctx: RunContext, checks=None, staging=None) -> RunReport:
    checks = checks or run_checks
    staging = staging or stage_outputs
    report_key = run_key(ctx.run_id, "report.json")
    progress_key = run_key(ctx.run_id, "progress.json")

    saved = ctx.store.get_json(report_key)
    report = (RunReport.from_dict(saved) if saved else
              RunReport(ctx.run_id, "weekly", ctx.mode, now_iso(), dry_run=ctx.dry_run))
    progress = ctx.store.get_json(progress_key, {"done": []})

    if not ctx.dry_run:
        state.pull(ctx.s3, ctx.state_bucket, ctx.pipeline.root, log=ctx.log)

    for name in stages_for(ctx.mode):
        if name in progress["done"]:
            ctx.log(f"{name}: finished in an earlier attempt, skipping")
            continue
        ctx.log(f"── {name}")
        started = time.time()
        result = call_stage(ctx.pipeline, name, ctx.limit)
        report.add_stage(result, time.time() - started)
        if name in CHECKPOINTED:
            if not ctx.dry_run:
                state.push(ctx.s3, ctx.state_bucket, ctx.pipeline.root,
                           since=started, log=ctx.log)
            progress["done"].append(name)
            ctx.store.put_json(progress_key, progress)
        ctx.store.put_json(report_key, report.to_dict())

    report.checks = []          # a resumed run re-checks from scratch
    checks(ctx, report)
    staging(ctx, report)
    report.finish()
    ctx.store.put_json(report_key, report.to_dict())

    hold = report.verdict != PASS or ctx.always_hold
    ctx.store.put_json(run_key(ctx.run_id, "verdict.json"),
                       {"run_id": ctx.run_id, "verdict": report.verdict, "hold": hold})
    if hold and ctx.notifier is not None:
        ctx.notifier.send(*held_message(report, ctx.state_bucket, ctx.always_hold))
    return report


def collect_counts(outputs, stages: dict) -> dict:
    counts = dict(Counter(o.dataset for o in outputs))
    factor = stages.get("build_factor_metrics")
    if factor:
        for sub, info in factor.detail.get("lists", {}).items():
            counts[f"factor_rows.{sub}"] = info["rows"]
    profiles = stages.get("build_profile_aggregate")
    if profiles:
        for name, rows in profiles.detail.get("rows", {}).items():
            counts[f"profile_rows.{name}"] = rows
    return counts


def recent_adj_close(outputs):
    """(symbol, adjClose) for every daily stock price parquet. Unreadable files
    are skipped here — check_outputs_readable already reports them."""
    for output in outputs:
        if output.key.startswith("stock_data/stock_prices/daily/"):
            symbol = os.path.basename(output.key).removesuffix("_prices.parquet")
            try:
                series = pd.read_parquet(output.local_path, columns=["adjClose"])["adjClose"]
            except Exception:  # noqa: BLE001
                continue
            yield symbol, series


def fred_last_dates(p) -> dict:
    out = {}
    folder = p.econ_json_dir
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(folder, name)) as f:
            rows = json.load(f)
        dates = [r["date"] for r in rows if isinstance(r, dict) and "date" in r]
        if dates:
            out[name.removesuffix(".json")] = max(dates)
    return out


def run_checks(ctx: RunContext, report: RunReport) -> None:
    p = ctx.pipeline
    stages = {s["name"]: StageResult.from_dict(s) for s in report.stages}
    baseline = ctx.store.get_json(LAST_PUBLISHED_REPORT) or {}
    results = []
    if "refresh_constituents" in stages:
        results += check_constituents(stages["refresh_constituents"])
    results += [check_fetch(r) for name, r in stages.items() if name.startswith("fetch_")]
    modal = {sub: info["modal_last_date"] for sub, info in p.modal_last_dates().items()}
    results += check_freshness(modal, recent_nyse_sessions(ctx.today))
    outputs = collect_outputs(p)
    results += check_outputs_readable(outputs)
    report.counts = collect_counts(outputs, stages)
    results += check_counts(report.counts, baseline.get("counts"))
    if "build_factor_metrics" in stages:
        report.factor_staleness = stages["build_factor_metrics"].detail.get("lists", {})
    results += check_factor_staleness(report.factor_staleness,
                                      baseline.get("factor_staleness"))
    results += check_price_sanity(recent_adj_close(outputs))
    results += check_econ(fred_last_dates(p), ctx.today)
    report.add_checks(results)


def stage_outputs(ctx: RunContext, report: RunReport) -> None:
    if ctx.dry_run:
        report.add_checks([CheckResult("staging", PASS, None, None,
                                       "dry run: nothing staged")])
        return
    outputs = collect_outputs(ctx.pipeline)
    live = S3Store(ctx.state_bucket, ctx.s3).get_json(LIVE_MANIFEST, {})
    changed = diff_outputs(outputs, live)
    stage_changed(ctx.s3, ctx.state_bucket, ctx.run_id, changed, log=ctx.log)
    report.staged_files = len(changed)
    prices = report.stage("fetch_stock_prices")
    report.add_checks([check_staging(len(changed), prices["saved"] if prices else 0)])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass. (`test_run_checks_on_fixture_data` reports other sub-universes as `freshness.<sub>: fail` because they have no files — the test only asserts `sp500`.)

- [ ] **Step 6: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): weekly runner with resume, checks wiring and emails

Fetch stages checkpoint state and progress; builds always rerun. The verdict
file tells the state machine whether to hold; a hold sends the held email.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: The daily news job

**Files:**
- Create: `backend/pipelines/news.py`, `backend/pipelines/tests/test_news.py`

**Interfaces:**
- Consumes: `CheckResult`, `PASS/WARN/FAIL` (Task 4); `RunReport`, `now_iso` (Task 5); `StageResult`, `redact` (Task 2); `run_key` (Task 5); `news_message` (Task 8).
- Produces: `news.FMP_FEEDS` (4), `news.SEARCH_TERMS` (24), `news.NEWS_PREFIX = "news_json_articles"`, `news.file_name(name)`; `fetch_fmp_feed(path, api_key, get)`, `fetch_search(term, api_key, get)`; `prepare(name, articles, source, now) -> (kept, CheckResult)`; `run_news(run_id, fmp_key, serp_key, out_dir, store, upload=None, notifier=None, notify_all=True, now=None, get=http_get_json, log=print, state_bucket=None, dry_run=False) -> RunReport` (verdict = `news.overall`).

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_news.py`:

```python
import datetime as dt
import json

import pytest

from pipelines import news
from pipelines.store import LocalStore, run_key

NOW = dt.datetime(2026, 10, 17, 9, 30, tzinfo=dt.timezone.utc)
FRESH = (NOW - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")


def fmp_page(path, page, n=20, date=FRESH):
    return [{"title": f"{path} {page}-{i}", "url": f"https://x/{path}/{page}/{i}",
             "publishedDate": date} for i in range(n)]


def search_results(term, n=5, age="2h"):
    return {"organic_results": [{"title": f"{term} {i}", "link": f"https://y/{term}/{i}",
                                 "date": age} for i in range(n)]}


def make_get(broken=(), pages=3):
    def get(url, params=None):
        params = params or {}
        if url == news.SERPAPI_URL:
            if params["q"] in broken:
                raise ValueError(f"boom for {url}?api_key=SECRET")
            return search_results(params["q"])
        path = url.removeprefix(news.FMP_STABLE + "/")
        if path in broken:
            raise ValueError(f"500 for url {url}?apikey=SECRET")
        return fmp_page(path, params["page"]) if params["page"] < pages else []
    return get


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, subject, message):
        self.sent.append(subject)


def run(tmp_path, get, **kwargs):
    uploads = []
    store = LocalStore(str(tmp_path / "store"))
    report = news.run_news("news-1", "fmp", "serp", str(tmp_path / "out"), store,
                           upload=lambda path, key: uploads.append(key),
                           now=NOW, get=get, log=lambda *a: None, **kwargs)
    return report, uploads, store


def test_catalogue_matches_django_reader():
    assert len(news.FMP_FEEDS) == 4 and len(news.SEARCH_TERMS) == 24
    assert news.file_name("fmp_articles") == "fmp_articles_articles.json"


def test_everything_passes_and_uploads(tmp_path):
    report, uploads, store = run(tmp_path, make_get())
    assert report.verdict == "pass"
    assert len(uploads) == 28
    assert "news_json_articles/econ_articles.json" in uploads
    assert "news_json_articles/stock_articles_articles.json" in uploads
    saved = store.get_json(run_key("news-1", "report.json"))
    assert saved["verdict"] == "pass"
    with open(tmp_path / "out" / "fmp_articles_articles.json") as f:
        assert len(json.load(f)) == 60


def test_one_broken_feed_is_kept_and_warns(tmp_path):
    report, uploads, _ = run(tmp_path, make_get(broken={"news/crypto-latest"}))
    assert report.verdict == "warn"
    assert "news_json_articles/crypto_articles_articles.json" not in uploads
    assert len(uploads) == 27
    failed = next(c for c in report.checks if c["name"] == "news.crypto_articles")
    assert failed["status"] == "fail" and "SECRET" not in failed["detail"]


def test_majority_broken_fails(tmp_path):
    report, uploads, _ = run(tmp_path, make_get(broken=set(news.SEARCH_TERMS.values())))
    assert report.verdict == "fail"
    assert len(uploads) == 4


def test_dry_run_uploads_nothing(tmp_path):
    _, uploads, _ = run(tmp_path, make_get(), dry_run=True)
    assert uploads == []


@pytest.mark.parametrize("notify_all,verdict_broken,emails", [
    (True, set(), 1), (False, set(), 0), (False, {"news/crypto-latest"}, 1)])
def test_notify_modes(tmp_path, notify_all, verdict_broken, emails):
    notifier = FakeNotifier()
    run(tmp_path, make_get(broken=verdict_broken), notifier=notifier, notify_all=notify_all)
    assert len(notifier.sent) == emails


def test_prepare_drops_bad_and_duplicate_articles():
    articles = fmp_page("f", 0, n=60) + [fmp_page("f", 0, n=1)[0], {"title": "no url"}, "junk"]
    kept, check = news.prepare("f", articles, "fmp", NOW)
    assert len(kept) == 60
    assert check.status == "pass" and "3 dropped" in check.detail


def test_prepare_fails_stale_and_thin_files():
    stale = fmp_page("f", 0, n=60, date="2026-10-01 00:00:00")
    assert news.prepare("f", stale, "fmp", NOW)[1].status == "fail"
    thin = search_results("t", n=2)["organic_results"]
    assert news.prepare("t", thin, "search", NOW)[1].status == "fail"
    old = search_results("t", n=5, age="3w")["organic_results"]
    assert news.prepare("t", old, "search", NOW)[1].status == "fail"
    unknown = search_results("t", n=5, age="Oct 3")["organic_results"]
    assert news.prepare("t", unknown, "search", NOW)[1].status == "pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_news.py -q`
Expected: FAIL — `ImportError: cannot import name 'news'`.

- [ ] **Step 3: Create `backend/pipelines/news.py`**

```python
"""The daily news job: 4 FMP news feeds and 24 SerpAPI news searches, one JSON
file each under news_json_articles/ in the live bucket. Django's news app reads
those exact keys (news/getNews.py), so names and article shapes are unchanged
from news_updater.ipynb.

A file is uploaded only when it passes its checks; a failing file keeps
yesterday's version live. Search results carry relative ages ("7h", "1d") that
Django anchors to the S3 write time, so files are uploaded right after fetch."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

import requests

from pipelines import thresholds as t
from pipelines.checks import FAIL, PASS, WARN, CheckResult
from pipelines.notify import news_message
from pipelines.report import RunReport, now_iso
from pipelines.results import StageResult, redact
from pipelines.store import run_key

FMP_STABLE = "https://financialmodelingprep.com/stable"
SERPAPI_URL = "https://serpapi.com/search.json"
NEWS_PREFIX = "news_json_articles"
FMP_PAGES, FMP_PAGE_SIZE = 15, 20

FMP_FEEDS = {
    "fmp_articles": "fmp-articles",
    "stock_articles": "news/stock-latest",
    "crypto_articles": "news/crypto-latest",
    "forex_articles": "news/forex-latest",
}
SEARCH_TERMS = {
    "econ": "Economic news updates", "global_news": "News on Global Markets",
    "tech": "Technology news", "macro": "Macroeconomic news",
    "politics": "Political news", "energy": "Energy", "oil": "Oil",
    "mid_east": "Middle East", "south_america": "South America markets",
    "us_stock": "US stock market", "japan_stock": "Japan stock market",
    "china_stock": "China stock market", "canadian_stock": "Canadian stock market",
    "eu_markets": "EU markets", "africa_economy": "Africa economy",
    "basic_materials": "Basic Materials", "industrials": "Industrials",
    "utilities": "Utilities Sector", "pharmaceuticals": "Pharmaceuticals",
    "consumer_trends": "Consumer trends", "financials": "Financials",
    "real_estate": "Real Estate", "communications": "Communications Industry",
    "digital_assets": "Digital Assets",
}

# Each tuple lists alternative field names; an article needs one of each.
REQUIRED_FIELDS = {
    "fmp": (("title",), ("url", "link"), ("publishedDate", "date")),
    "search": (("title",), ("link",), ("date",)),
}
_RELATIVE_AGE = re.compile(r"^\s*(\d+)\s*(mo|min|sec|hr|s|m|h|d|w|y)", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600,
                 "d": 86400, "w": 604800, "mo": 2592000, "y": 31536000}


def file_name(name: str) -> str:
    return f"{name}_articles.json"


def http_get_json(url, params=None, timeout=30, retries=1):
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(2)


def fetch_fmp_feed(path, api_key, get=http_get_json) -> list:
    articles = []
    for page in range(FMP_PAGES):
        batch = get(f"{FMP_STABLE}/{path}",
                    params={"page": page, "limit": FMP_PAGE_SIZE, "apikey": api_key})
        if not isinstance(batch, list):
            raise ValueError(f"unexpected FMP payload: {str(batch)[:200]}")
        if not batch:
            break
        articles.extend(batch)
    return articles


def fetch_search(term, api_key, get=http_get_json) -> list:
    data = get(SERPAPI_URL, params={
        "engine": "bing_news", "q": term, "api_key": api_key, "device": "desktop",
        "qft": 'interval="7"', "count": "20", "safeSearch": "strict"})
    if "error" in data:
        raise ValueError(data["error"])
    return data.get("organic_results", [])


def _age_days(article, source, now):
    raw = article.get("publishedDate") or article.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    if source == "fmp":
        try:
            published = dt.datetime.strptime(raw.strip()[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return (now.replace(tzinfo=None) - published).total_seconds() / 86400
    match = _RELATIVE_AGE.match(raw)
    if not match:
        return None
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()] / 86400


def prepare(name, articles, source, now) -> tuple[list, CheckResult]:
    """Drop malformed and duplicate articles, then check what is left."""
    kept, seen, dropped = [], set(), 0
    for article in articles:
        if not isinstance(article, dict) or not all(
                any(article.get(f) for f in alternatives)
                for alternatives in REQUIRED_FIELDS[source]):
            dropped += 1
            continue
        url = article.get("url") or article.get("link")
        if url in seen:
            dropped += 1
            continue
        seen.add(url)
        kept.append(article)

    minimum, max_age = t.NEWS_MIN_ARTICLES[source], t.NEWS_MAX_AGE_DAYS[source]
    ages = [a for a in (_age_days(x, source, now) for x in kept) if a is not None]
    newest = min(ages) if ages else None
    detail = (f"{len(kept)} articles ({dropped} dropped), newest "
              + (f"{newest:.1f} days old" if newest is not None else "of unknown age"))
    if len(kept) < minimum:
        status, detail = FAIL, f"only {len(kept)} articles (need {minimum}); {detail}"
    elif newest is not None and newest > max_age:
        status, detail = FAIL, f"newest article older than {max_age} days; {detail}"
    else:
        status = PASS
    return kept, CheckResult(f"news.{name}", status, len(kept), minimum, detail)


def run_news(run_id, fmp_key, serp_key, out_dir, store, upload=None, notifier=None,
             notify_all=True, now=None, get=http_get_json, log=print,
             state_bucket=None, dry_run=False) -> RunReport:
    now = now or dt.datetime.now(dt.timezone.utc)
    report = RunReport(run_id, "news", "news", now_iso(), dry_run=dry_run)
    os.makedirs(out_dir, exist_ok=True)

    jobs = [(name, "fmp", lambda path=path: fetch_fmp_feed(path, fmp_key, get))
            for name, path in FMP_FEEDS.items()]
    jobs += [(name, "search", lambda term=term: fetch_search(term, serp_key, get))
             for name, term in SEARCH_TERMS.items()]

    results, uploaded = [], 0
    for name, source, fetch in jobs:
        started = time.time()
        try:
            kept, check = prepare(name, fetch(), source, now)
        except Exception as e:  # noqa: BLE001 — one bad feed must not stop the rest
            kept, check = [], CheckResult(f"news.{name}", FAIL, 0, None,
                                          f"fetch failed: {redact(str(e))}")
        stage = StageResult(f"news.{name}")
        stage.record(check.status == PASS, None if check.status == PASS else name)
        stage.detail["articles"] = len(kept)
        report.add_stage(stage, time.time() - started)
        results.append(check)
        if check.status != PASS:
            log(f"{name}: kept yesterday's file — {check.detail}")
            continue
        path = os.path.join(out_dir, file_name(name))
        with open(path, "w") as f:
            json.dump(kept, f)
        if not dry_run and upload is not None:
            upload(path, f"{NEWS_PREFIX}/{file_name(name)}")
            uploaded += 1

    failed = sum(r.status == FAIL for r in results)
    if failed / len(results) > t.NEWS_FAILED_SHARE_FAIL:
        overall = FAIL
    elif failed:
        overall = WARN
    else:
        overall = PASS
    results.append(CheckResult("news.overall", overall, failed, t.NEWS_FAILED_SHARE_FAIL,
                               f"{failed} of {len(jobs)} files failed checks and "
                               "were not uploaded"))
    report.staged_files = uploaded
    report.add_checks(results)
    report.finish(verdict_override=overall)
    store.put_json(run_key(run_id, "report.json"), report.to_dict())
    if notifier is not None and (notify_all or overall != PASS):
        notifier.send(*news_message(report, uploaded, state_bucket))
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): daily news job with per-file checks

Rewrites news_updater.ipynb without hardcoded keys or swallowed errors. A
failing file is not uploaded, so yesterday's stays live.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The command line

**Files:**
- Create: `backend/pipelines/cli.py`, `backend/pipelines/__main__.py`, `backend/pipelines/tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `python -m pipelines {run,publish,news,start,start-news,approve,discard,rollback,seed-state,pull-state,status}`; `cli.main(argv=None) -> int`; `cli.WEEKLY_MACHINE = "fintank-weekly-data-run"`, `cli.NEWS_MACHINE = "fintank-daily-news"`. Container commands (used by the state machines): `run --mode M --run-id ID [--limit N]`, `publish ID`, `news --run-id ID`.

- [ ] **Step 1: Write the failing tests**

`backend/pipelines/tests/test_cli.py`:

```python
import json

import pytest

from pipelines import cli
from pipelines.store import S3Store, run_key


class FakeSfn:
    def __init__(self):
        self.calls = []

    def send_task_success(self, **kw):
        self.calls.append(("send_task_success", kw))

    def send_task_failure(self, **kw):
        self.calls.append(("send_task_failure", kw))

    def start_execution(self, **kw):
        self.calls.append(("start_execution", kw))
        return {"executionArn": "arn:exec"}

    def get_paginator(self, name):
        assert name == "list_state_machines"
        machines = [{"name": cli.WEEKLY_MACHINE, "stateMachineArn": "arn:weekly"},
                    {"name": cli.NEWS_MACHINE, "stateMachineArn": "arn:news"}]
        return type("P", (), {"paginate": lambda self: [{"stateMachines": machines}]})()


@pytest.fixture
def wired(aws, monkeypatch):
    aws.create_bucket(Bucket="state")
    monkeypatch.setenv("STATE_BUCKET", "state")
    sfn = FakeSfn()
    monkeypatch.setattr(cli, "aws_client",
                        lambda service: sfn if service == "stepfunctions" else aws)
    return sfn, aws


def test_parser_defaults():
    args = cli.build_parser().parse_args(["run"])
    assert (args.mode, args.dry_run, args.limit, args.run_id) == ("auto", False, None, None)
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["start"])            # --mode is required


def test_approve_sends_task_success(wired):
    sfn, s3 = wired
    S3Store("state", s3).put_json(run_key("lean-1", "approval-token.json"),
                                  {"task_token": "tok", "run_id": "lean-1"})
    assert cli.main(["approve", "lean-1"]) == 0
    assert sfn.calls == [("send_task_success",
                          {"taskToken": "tok", "output": json.dumps({"decision": "approve"})})]


def test_discard_sends_task_failure(wired):
    sfn, s3 = wired
    S3Store("state", s3).put_json(run_key("lean-1", "approval-token.json"),
                                  {"task_token": "tok", "run_id": "lean-1"})
    cli.main(["discard", "lean-1"])
    name, kwargs = sfn.calls[0]
    assert (name, kwargs["taskToken"], kwargs["error"]) == ("send_task_failure", "tok", "Discarded")


def test_approve_without_token_exits(wired):
    with pytest.raises(SystemExit, match="not waiting for approval"):
        cli.main(["approve", "lean-9"])


def test_start_passes_mode_limit_and_run_id(wired):
    sfn, _ = wired
    cli.main(["start", "--mode", "lean", "--limit", "5", "--run-id", "lean-1"])
    name, kwargs = sfn.calls[0]
    assert (name, kwargs["stateMachineArn"]) == ("start_execution", "arn:weekly")
    assert json.loads(kwargs["input"]) == {"mode": "lean", "limit": 5, "run_id": "lean-1"}


def test_start_news(wired):
    sfn, _ = wired
    cli.main(["start-news"])
    assert sfn.calls[0][1]["stateMachineArn"] == "arn:news"


def test_crash_sends_email_and_reraises(monkeypatch):
    sent = []

    class FakeNotifier:
        def send(self, subject, message):
            sent.append(subject)

    def boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(cli.COMMANDS, "run", boom)
    monkeypatch.setattr(cli, "Notifier", FakeNotifier)
    with pytest.raises(RuntimeError):
        cli.main(["run", "--run-id", "lean-1"])
    assert sent == ["[Fintank] run lean-1 crashed"]


def test_dry_run_crash_sends_nothing(monkeypatch):
    sent = []
    monkeypatch.setitem(cli.COMMANDS, "run", lambda args: 1 / 0)
    monkeypatch.setattr(cli, "Notifier", lambda: sent.append("x"))
    with pytest.raises(ZeroDivisionError):
        cli.main(["run", "--dry-run"])
    assert sent == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'cli'`.

- [ ] **Step 3: Create `backend/pipelines/cli.py`**

```python
"""python -m pipelines <command> — the pipeline's command line.

On AWS the containers run `run`, `publish` and `news`. Everything else is for
Franc's terminal, with AWS_PROFILE=fintank set."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import traceback

from pipelines import publish as publishing
from pipelines import state
from pipelines.notify import Notifier, complete_message, crash_message
from pipelines.report import RunReport
from pipelines.runner import RunContext, make_run_id, resolve_mode, run_weekly
from pipelines.store import (LocalStore, S3Store, aws_client, default_state_bucket,
                             live_bucket, run_key)

WEEKLY_MACHINE = "fintank-weekly-data-run"
NEWS_MACHINE = "fintank-daily-news"
CRASH_EMAIL_COMMANDS = ("run", "publish", "news")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipelines")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="weekly data run (the AWS task's entry point)")
    run.add_argument("--mode", choices=["lean", "full", "auto"], default="auto")
    run.add_argument("--run-id")
    run.add_argument("--dry-run", action="store_true",
                     help="local data only: no state pull/push, nothing staged, no "
                          "emails. Fetchers still write to the local data folder.")
    run.add_argument("--limit", type=int, help="symbols per list (smoke test)")

    pub = sub.add_parser("publish", help="copy a run's staged files to the live bucket")
    pub.add_argument("run_id")

    news = sub.add_parser("news", help="daily news run (the AWS task's entry point)")
    news.add_argument("--run-id")
    news.add_argument("--dry-run", action="store_true")

    start = sub.add_parser("start", help="start the weekly state machine now")
    start.add_argument("--mode", choices=["lean", "full"], required=True)
    start.add_argument("--limit", type=int)
    start.add_argument("--run-id", help="resume this run instead of starting a new one")
    sub.add_parser("start-news", help="start the news state machine now")

    for name, text in (("approve", "publish a held run"),
                       ("discard", "throw a held run away"),
                       ("rollback", "restore every live file a run changed")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("run_id")
        if name == "rollback":
            cmd.add_argument("--yes", action="store_true")

    sub.add_parser("seed-state", help="one time: upload local JSON state to AWS")
    pull = sub.add_parser("pull-state", help="replace local state with the AWS copy")
    pull.add_argument("--yes", action="store_true")
    sub.add_parser("status", help="recent executions and run verdicts")
    return parser


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _data_root() -> str:
    from pipelines.stock_pipeline import DEFAULT_DATA_ROOT
    return os.getenv("PIPELINE_DATA_ROOT") or DEFAULT_DATA_ROOT


def _always_hold() -> bool:
    return os.getenv("ALWAYS_HOLD", "false").lower() == "true"


def cmd_run(args) -> int:
    from pipelines.stock_pipeline import StockDataPipeline

    p = StockDataPipeline()
    now = _utcnow()
    mode = resolve_mode(args.mode, now.date())
    run_id = args.run_id or make_run_id(mode, now)
    if args.dry_run:
        store, s3, bucket, notifier = LocalStore(os.path.join(p.root, ".runs")), None, None, None
    else:
        s3 = aws_client("s3")
        bucket = default_state_bucket()
        store, notifier = S3Store(bucket, s3), Notifier()
    ctx = RunContext(pipeline=p, store=store, run_id=run_id, mode=mode,
                     dry_run=args.dry_run, limit=args.limit, s3=s3, state_bucket=bucket,
                     notifier=notifier, always_hold=_always_hold(), today=now.date())
    report = run_weekly(ctx)
    print(report.summary())
    print(json.dumps({"run_id": run_id, "verdict": report.verdict}))
    return 0


def cmd_publish(args) -> int:
    s3, bucket = aws_client("s3"), default_state_bucket()
    result = publishing.publish(s3, bucket, live_bucket(), args.run_id)
    report = RunReport.from_dict(S3Store(bucket, s3).get_json(
        run_key(args.run_id, "report.json")))
    Notifier().send(*complete_message(report, result, bucket))
    print(json.dumps(result))
    return 0


def cmd_news(args) -> int:
    from dotenv import load_dotenv

    from pipelines.news import run_news
    from pipelines.stock_pipeline import BACKEND_DIR

    load_dotenv(os.path.join(BACKEND_DIR, ".env"))      # local runs; absent on AWS
    fmp_key = os.getenv("FMP_API")
    serp_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API")
    if not (fmp_key and serp_key):
        raise SystemExit("FMP_API and SERPAPI_KEY must be set")
    root = _data_root()
    run_id = args.run_id or f"news-{_utcnow():%Y%m%d-%H%M}"
    if args.dry_run:
        store, upload, notifier, bucket = LocalStore(os.path.join(root, ".runs")), None, None, None
    else:
        s3, bucket, live = aws_client("s3"), default_state_bucket(), live_bucket()
        store, notifier = S3Store(bucket, s3), Notifier()

        def upload(path, key):
            s3.upload_file(path, live, key)
    report = run_news(run_id, fmp_key, serp_key, os.path.join(root, "news_json_articles"),
                      store, upload=upload, notifier=notifier,
                      notify_all=os.getenv("NEWS_NOTIFY", "all") == "all",
                      state_bucket=bucket, dry_run=args.dry_run)
    print(report.summary())
    return 0


def _machine_arn(sfn, name) -> str:
    for page in sfn.get_paginator("list_state_machines").paginate():
        for machine in page["stateMachines"]:
            if machine["name"] == name:
                return machine["stateMachineArn"]
    raise SystemExit(f"state machine {name} not found — is the stack deployed?")


def cmd_start(args) -> int:
    sfn = aws_client("stepfunctions")
    payload = {"mode": args.mode}
    if args.limit:
        payload["limit"] = args.limit
    if args.run_id:
        payload["run_id"] = args.run_id
    response = sfn.start_execution(stateMachineArn=_machine_arn(sfn, WEEKLY_MACHINE),
                                   input=json.dumps(payload))
    print(f"started {response['executionArn']}")
    return 0


def cmd_start_news(args) -> int:
    sfn = aws_client("stepfunctions")
    response = sfn.start_execution(stateMachineArn=_machine_arn(sfn, NEWS_MACHINE),
                                   input="{}")
    print(f"started {response['executionArn']}")
    return 0


def _approval_token(run_id) -> str:
    token = S3Store(default_state_bucket(), aws_client("s3")).get_json(
        run_key(run_id, "approval-token.json"))
    if not token:
        raise SystemExit(f"{run_id} is not waiting for approval")
    return token["task_token"]


def cmd_approve(args) -> int:
    aws_client("stepfunctions").send_task_success(
        taskToken=_approval_token(args.run_id), output=json.dumps({"decision": "approve"}))
    print(f"approved {args.run_id} — publishing now; you'll get an email when it's done")
    return 0


def cmd_discard(args) -> int:
    aws_client("stepfunctions").send_task_failure(
        taskToken=_approval_token(args.run_id), error="Discarded",
        cause="discarded from the command line")
    print(f"discarded {args.run_id} — nothing was published")
    return 0


def cmd_rollback(args) -> int:
    if not args.yes:
        answer = input(f"Restore every live file {args.run_id} changed? "
                       "Type the run id to confirm: ")
        if answer.strip() != args.run_id:
            print("aborted")
            return 1
    count = publishing.rollback(aws_client("s3"), default_state_bucket(),
                                live_bucket(), args.run_id)
    print(f"restored {count} files")
    return 0


def cmd_seed_state(args) -> int:
    root = _data_root()
    units = state.state_units(root)
    print(f"uploading {len(units)} state folders from {root} (this takes a while)")
    state.push(aws_client("s3"), default_state_bucket(), root)
    return 0


def cmd_pull_state(args) -> int:
    root = _data_root()
    if not args.yes:
        print(f"pull-state REPLACES these folders under {root} with the AWS copy:\n  "
              + "\n  ".join(state.state_units(root) or ["(none yet)"])
              + "\nRe-run with --yes to continue.")
        return 1
    state.pull(aws_client("s3"), default_state_bucket(), root)
    return 0


def cmd_status(args) -> int:
    sfn = aws_client("stepfunctions")
    for name in (WEEKLY_MACHINE, NEWS_MACHINE):
        print(name)
        executions = sfn.list_executions(stateMachineArn=_machine_arn(sfn, name),
                                         maxResults=10)["executions"]
        for e in executions:
            print(f"  {e['startDate']:%Y-%m-%d %H:%M}  {e['status']:<10} {e['name']}")
    store = S3Store(default_state_bucket(), aws_client("s3"))
    print("recent runs")
    prefixes = sorted(store.list_prefixes("runs/"), key=lambda p: p.split("-", 1)[-1])
    for prefix in prefixes[-10:]:
        run_id = prefix.split("/")[1]
        verdict = (store.get_json(run_key(run_id, "verdict.json"))
                   or store.get_json(run_key(run_id, "report.json")) or {})
        print(f"  {run_id:<26} {verdict.get('verdict') or '-'}")
    return 0


COMMANDS = {
    "run": cmd_run, "publish": cmd_publish, "news": cmd_news,
    "start": cmd_start, "start-news": cmd_start_news,
    "approve": cmd_approve, "discard": cmd_discard, "rollback": cmd_rollback,
    "seed-state": cmd_seed_state, "pull-state": cmd_pull_state, "status": cmd_status,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args) or 0
    except Exception:
        # The state machine also reports failures, but whether ECS marks a
        # non-zero exit as failed is not something to rely on — so the
        # container says so itself.
        if args.command in CRASH_EMAIL_COMMANDS and not getattr(args, "dry_run", False):
            run_id = getattr(args, "run_id", None) or "?"
            try:
                Notifier().send(*crash_message(args.command, run_id,
                                               traceback.format_exc()))
            except Exception:  # noqa: BLE001 — never mask the original error
                traceback.print_exc()
        raise
```

`backend/pipelines/__main__.py`:

```python
import sys

from pipelines.cli import main

sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass. Also check the help renders: `cd backend && ../../.venv/bin/python -m pipelines --help` lists all eleven commands.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): python -m pipelines command line

Container entry points (run, publish, news) plus start, approve, discard,
rollback, seed/pull state and status. A crash in a container command emails.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: Container image

**Files:**
- Create: `backend/pipelines/Dockerfile`, `backend/pipelines/.dockerignore`, `backend/pipelines/tests/test_container.py`

**Interfaces:**
- Consumes: the package from Tasks 1–10.
- Produces: an image built from the build context `backend/pipelines/` whose entrypoint is `python -m pipelines` (so a container command is just the CLI arguments, e.g. `["run", "--mode", "lean", "--run-id", "lean-…"]`). Task 12 builds it with `ContainerImage.from_asset("backend/pipelines")`.

- [ ] **Step 1: Write the failing test**

`backend/pipelines/tests/test_container.py`:

```python
"""The image is built by `cdk deploy` on Franc's machine, so these tests guard
what can be checked without Docker: the build context and what it copies."""
import ast
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parents[1]
STDLIB = set(sys.stdlib_module_names)
# import name → requirements.txt name
DISTRIBUTIONS = {"dotenv": "python-dotenv", "pandas_market_calendars": "pandas-market-calendars",
                 "botocore": "boto3", "pyarrow": "pyarrow"}


def test_dockerfile_copies_from_its_own_folder():
    text = (PIPELINES / "Dockerfile").read_text()
    for line in text.splitlines():
        if line.startswith("COPY "):
            source = line.split()[1]
            assert (PIPELINES / source).exists(), source
    assert 'ENTRYPOINT ["python", "-m", "pipelines"]' in text


def test_dockerignore_keeps_tests_out():
    lines = (PIPELINES / ".dockerignore").read_text().split()
    assert "tests/" in lines and "**/__pycache__" in lines


def test_runtime_imports_are_in_requirements():
    required = {line.split("==")[0].strip().lower()
                for line in (PIPELINES / "requirements.txt").read_text().splitlines()
                if line and not line.startswith("#")}
    for path in PIPELINES.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top in STDLIB or top == "pipelines":
                    continue
                dist = DISTRIBUTIONS.get(top, top).lower()
                assert dist in required, f"{path.name} imports {top}, not in requirements.txt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_container.py -q`
Expected: FAIL — `FileNotFoundError` for `Dockerfile`.

- [ ] **Step 3: Create the image files**

`backend/pipelines/Dockerfile`:

```dockerfile
# Fintank pipeline image. Built from backend/pipelines/ by `cdk deploy`
# (infra/pipeline_stack.py). Data lives in /data on the task's ephemeral disk.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIPELINE_DATA_ROOT=/data

WORKDIR /app
COPY requirements.txt pipelines/requirements.txt
RUN pip install -r pipelines/requirements.txt
COPY . pipelines/

RUN useradd --create-home --uid 10001 pipeline \
    && mkdir -p /data && chown pipeline /data
USER pipeline

ENTRYPOINT ["python", "-m", "pipelines"]
CMD ["--help"]
```

`backend/pipelines/.dockerignore`:

```
tests/
**/__pycache__
.pytest_cache/
Dockerfile
.dockerignore
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
Expected: all pass.

If Docker is available (`docker --version` succeeds — it is not installed in Franc's WSL yet; skip this if not), also check the image builds and the CLI starts:

```bash
cd backend/pipelines && docker build -t fintank-pipeline:dev . && docker run --rm fintank-pipeline:dev --help
```

Expected: the help text listing the eleven commands.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines
git commit -m "feat(pipeline): container image for the Fargate tasks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: AWS infrastructure (CDK)

**Files:**
- Create: `infra/app.py`, `infra/cdk.json`, `infra/requirements.txt`, `infra/pipeline_stack.py`, `infra/statemachines/weekly.asl.json`, `infra/statemachines/news.asl.json`, `infra/tests/__init__.py`, `infra/tests/test_pipeline_stack.py`
- Modify: `.gitignore` (fintank root)

**Interfaces:**
- Consumes: the image context `backend/pipelines/` (Task 11); container commands `run --mode M --run-id ID [--limit N]`, `publish ID`, `news --run-id ID` (Task 10); files `runs/<id>/verdict.json` (`{"hold": bool}`) and `runs/<id>/approval-token.json` (Task 8 / Task 10); env vars the CLI reads: `PIPELINE_DATA_ROOT`, `STATE_BUCKET`, `LIVE_BUCKET`, `SNS_TOPIC_ARN`, `ALWAYS_HOLD`, `NEWS_NOTIFY`, `FMP_API`, `FRED_API`, `SERPAPI_KEY`.
- Produces: stack `FintankPipeline`; state machines `fintank-weekly-data-run` and `fintank-daily-news` (names the CLI looks up); state bucket `fintank-pipeline-<account>`; SNS topic `fintank-pipeline-alerts`; log group `/fintank/pipeline`. CDK context: `alert_email` (required), `always_hold` (`true`|`false`, default `true`), `news_notify` (`all`|`warnings_only`), `weekly_schedule` / `news_schedule` (`on`|`off`, default `off`), `s3_endpoint` (`on`|`off`, default `on`).

- [ ] **Step 1: Scaffold and install CDK into its own venv**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
mkdir -p infra/statemachines infra/tests
```

`infra/requirements.txt`:

```
aws-cdk-lib>=2.200.0,<3
constructs>=10.0.0,<11
pytest==9.0.2
```

```bash
cd infra && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
```

Append to `fintank/.gitignore`:

```
# AWS CDK (infra/)
/infra/.venv/
/infra/cdk.out/
/infra/cdk.context.json
```

(`cdk.context.json` caches the default-VPC lookup for one account; keeping it out of git keeps the account id out too.)

`infra/tests/__init__.py`: empty file.

- [ ] **Step 2: Write the failing tests**

`infra/tests/test_pipeline_stack.py`:

```python
import json
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from pipeline_stack import ASL_DIR, PipelineStack, asl_placeholders

ENV = cdk.Environment(account="123456789012", region="us-east-1")


def synth(**kwargs):
    app = cdk.App()
    stack = PipelineStack(app, "Test", env=ENV, alert_email="ops@example.com", **kwargs)
    return stack, Template.from_stack(stack)


@pytest.fixture(scope="module")
def built():
    return synth()


def test_no_nat_gateway(built):
    built[1].resource_count_is("AWS::EC2::NatGateway", 0)


def test_task_security_group_has_no_inbound_rules(built):
    template = built[1]
    template.resource_count_is("AWS::EC2::SecurityGroupIngress", 0)
    for sg in template.find_resources("AWS::EC2::SecurityGroup").values():
        assert "SecurityGroupIngress" not in sg["Properties"]


def test_run_task_size(built):
    built[1].has_resource_properties("AWS::ECS::TaskDefinition", {
        "Family": "fintank-run", "Cpu": "4096", "Memory": "16384",
        "EphemeralStorage": {"SizeInGiB": 150}})


def test_state_bucket_locked_down(built):
    built[1].has_resource_properties("AWS::S3::Bucket", {
        "VersioningConfiguration": {"Status": "Enabled"},
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True}})


def test_schedules_off_by_default_and_on_by_context():
    _, template = synth()
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert sorted(s["Properties"]["State"] for s in schedules) == ["DISABLED", "DISABLED"]
    _, template = synth(weekly_schedule=True, news_schedule=True)
    schedules = template.find_resources("AWS::Scheduler::Schedule").values()
    assert {s["Properties"]["ScheduleExpression"]: s["Properties"]["State"]
            for s in schedules} == {"cron(0 10 ? * SAT *)": "ENABLED",
                                    "cron(30 9 * * ? *)": "ENABLED"}


def role_of(template, family):
    for td in template.find_resources("AWS::ECS::TaskDefinition").values():
        if td["Properties"]["Family"] == family:
            return td["Properties"]["TaskRoleArn"]["Fn::GetAtt"][0]
    raise AssertionError(family)


def roles_writing_live_bucket(template):
    writers = set()
    for policy in template.find_resources("AWS::IAM::Policy").values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            actions = statement["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            if (any(a.startswith(("s3:Put", "s3:DeleteObject", "s3:Abort")) for a in actions)
                    and "thetradingfloor" in json.dumps(statement["Resource"])):
                writers |= {r["Ref"] for r in policy["Properties"]["Roles"]}
    return writers


def test_only_publish_and_news_can_write_the_live_bucket(built):
    template = built[1]
    writers = roles_writing_live_bucket(template)
    assert role_of(template, "fintank-run") not in writers
    assert role_of(template, "fintank-publish") in writers
    assert role_of(template, "fintank-news") in writers


def test_alerts_go_to_the_email(built):
    built[1].has_resource_properties("AWS::SNS::Subscription", {
        "Protocol": "email", "Endpoint": "ops@example.com"})


@pytest.mark.parametrize("name", ["weekly.asl.json", "news.asl.json"])
def test_asl_placeholders_are_all_substituted(built, name):
    stack, _ = built
    assert asl_placeholders(ASL_DIR / name) == set(stack.substitutions[name])


@pytest.mark.parametrize("name", ["weekly.asl.json", "news.asl.json"])
def test_asl_is_valid_jsonata_json_after_substitution(name):
    text = (ASL_DIR / name).read_text()
    for key in asl_placeholders(ASL_DIR / name):
        value = {"SubnetIds": '["subnet-1"]', "NotifyStart": "true"}.get(key, "x")
        text = text.replace("${" + key + "}", value)
    definition = json.loads(text)
    assert definition["QueryLanguage"] == "JSONata"
    states = definition["States"]
    for state in states.values():
        for target in [state.get("Next"), state.get("Default")] + [
                c["Next"] for c in state.get("Choices", []) + state.get("Catch", [])]:
            assert target is None or target in states, target
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd infra && .venv/bin/python -m pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline_stack'`.

- [ ] **Step 4: Write the state machines**

`infra/statemachines/weekly.asl.json` (the `${…}` placeholders are filled by CDK; `${SubnetIds}` is deliberately unquoted — it becomes a JSON array):

```json
{
  "Comment": "Fintank weekly market-data run. See docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md",
  "QueryLanguage": "JSONata",
  "TimeoutSeconds": 777600,
  "StartAt": "Init",
  "States": {
    "Init": {
      "Type": "Pass",
      "Assign": {
        "mode": "{% $exists($states.input.mode) ? $states.input.mode : ($number($fromMillis($toMillis($states.context.Execution.StartTime), '[D1]')) <= 7 ? 'full' : 'lean') %}",
        "limit": "{% $exists($states.input.limit) ? ['--limit', $string($states.input.limit)] : [] %}",
        "attempt": 0,
        "error": null,
        "reason": null
      },
      "Next": "NameRun"
    },
    "NameRun": {
      "Type": "Pass",
      "Assign": {
        "run_id": "{% $exists($states.input.run_id) ? $states.input.run_id : $mode & '-' & $fromMillis($toMillis($states.context.Execution.StartTime), '[Y0001][M01][D01]-[H01][m01]') %}"
      },
      "Next": "CheckBusy"
    },
    "CheckBusy": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:sfn:listExecutions",
      "Arguments": {
        "StateMachineArn": "{% $states.context.StateMachine.Id %}",
        "StatusFilter": "RUNNING"
      },
      "Assign": {"running": "{% $count($states.result.Executions) %}"},
      "Next": "Busy?"
    },
    "Busy?": {
      "Type": "Choice",
      "Choices": [{"Condition": "{% $running > 1 %}", "Next": "NotifyBusy"}],
      "Default": "NotifyStarted"
    },
    "NotifyBusy": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] Weekly run ' & $run_id & ' skipped' %}",
        "Message": "Another weekly run is still in progress, so this one did not start. See: python -m pipelines status"
      },
      "Next": "AlreadyRunning"
    },
    "AlreadyRunning": {"Type": "Fail", "Error": "AlreadyRunning", "Cause": "another weekly run is in progress"},
    "NotifyStarted": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] Weekly run ' & $run_id & ' started' %}",
        "Message": "{% 'Mode: ' & $mode & '\\nRun ID: ' & $run_id & '\\nExecution: ' & $states.context.Execution.Id %}"
      },
      "Next": "RunPipeline"
    },
    "RunPipeline": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": {
        "Cluster": "${ClusterArn}",
        "TaskDefinition": "${RunTaskDefinitionArn}",
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "AwsvpcConfiguration": {
            "Subnets": ${SubnetIds},
            "SecurityGroups": ["${SecurityGroupId}"],
            "AssignPublicIp": "ENABLED"
          }
        },
        "Overrides": {
          "ContainerOverrides": [
            {"Name": "app", "Command": "{% $append(['run', '--mode', $mode, '--run-id', $run_id], $limit) %}"}
          ]
        }
      },
      "TimeoutSeconds": 43200,
      "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"error": "{% $states.errorOutput %}"}, "Next": "CanRetry?"}],
      "Next": "ReadVerdict"
    },
    "ReadVerdict": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
      "Arguments": {
        "Bucket": "${StateBucket}",
        "Key": "{% 'runs/' & $run_id & '/verdict.json' %}"
      },
      "Assign": {"verdict": "{% $parse($states.result.Body) %}"},
      "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"error": "{% $states.errorOutput %}"}, "Next": "CanRetry?"}],
      "Next": "Hold?"
    },
    "CanRetry?": {
      "Type": "Choice",
      "Choices": [{"Condition": "{% $attempt < 1 %}", "Next": "WaitBeforeRetry"}],
      "Default": "NotifyFailed"
    },
    "WaitBeforeRetry": {
      "Type": "Wait",
      "Seconds": 60,
      "Assign": {"attempt": "{% $attempt + 1 %}"},
      "Next": "RunPipeline"
    },
    "Hold?": {
      "Type": "Choice",
      "Choices": [{"Condition": "{% $verdict.hold %}", "Next": "WaitForApproval"}],
      "Default": "Publish"
    },
    "WaitForApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:s3:putObject.waitForTaskToken",
      "Arguments": {
        "Bucket": "${StateBucket}",
        "Key": "{% 'runs/' & $run_id & '/approval-token.json' %}",
        "Body": "{% $string({'task_token': $states.context.Task.Token, 'run_id': $run_id}) %}",
        "ContentType": "application/json"
      },
      "TimeoutSeconds": 604800,
      "Catch": [
        {"ErrorEquals": ["States.Timeout"], "Assign": {"reason": "it was not approved within 7 days"}, "Next": "NotifyDiscarded"},
        {"ErrorEquals": ["Discarded"], "Assign": {"reason": "it was discarded"}, "Next": "NotifyDiscarded"},
        {"ErrorEquals": ["States.ALL"], "Assign": {"error": "{% $states.errorOutput %}"}, "Next": "NotifyFailed"}
      ],
      "Next": "Publish"
    },
    "Publish": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": {
        "Cluster": "${ClusterArn}",
        "TaskDefinition": "${PublishTaskDefinitionArn}",
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "AwsvpcConfiguration": {
            "Subnets": ${SubnetIds},
            "SecurityGroups": ["${SecurityGroupId}"],
            "AssignPublicIp": "ENABLED"
          }
        },
        "Overrides": {"ContainerOverrides": [{"Name": "app", "Command": "{% ['publish', $run_id] %}"}]}
      },
      "TimeoutSeconds": 7200,
      "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"error": "{% $states.errorOutput %}"}, "Next": "NotifyFailed"}],
      "Next": "Published"
    },
    "Published": {"Type": "Succeed"},
    "NotifyDiscarded": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] Weekly run ' & $run_id & ' discarded' %}",
        "Message": "{% 'Run ' & $run_id & ' was not published because ' & $reason & '. The live site is unchanged.' %}"
      },
      "Next": "Discarded"
    },
    "Discarded": {"Type": "Succeed"},
    "NotifyFailed": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] Weekly run ' & $run_id & ' FAILED' %}",
        "Message": "{% 'Run ' & $run_id & ' failed.\\n\\nIf it failed while publishing, some files may already be live — undo with: python -m pipelines rollback ' & $run_id & '\\nResume with: python -m pipelines start --mode ' & $mode & ' --run-id ' & $run_id & '\\n\\nError: ' & $string($error) & '\\n\\nLogs: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Ffintank$252Fpipeline' %}"
      },
      "Next": "Failed"
    },
    "Failed": {"Type": "Fail", "Error": "WeeklyRunFailed"}
  }
}
```

`infra/statemachines/news.asl.json`:

```json
{
  "Comment": "Fintank daily news run. See docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md",
  "QueryLanguage": "JSONata",
  "TimeoutSeconds": 3600,
  "StartAt": "Init",
  "States": {
    "Init": {
      "Type": "Pass",
      "Assign": {
        "run_id": "{% $exists($states.input.run_id) ? $states.input.run_id : 'news-' & $fromMillis($toMillis($states.context.Execution.StartTime), '[Y0001][M01][D01]-[H01][m01]') %}",
        "error": null
      },
      "Next": "NotifyStart?"
    },
    "NotifyStart?": {
      "Type": "Choice",
      "Choices": [{"Condition": "{% ${NotifyStart} %}", "Next": "NotifyStarted"}],
      "Default": "RunNews"
    },
    "NotifyStarted": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] News ' & $run_id & ' started' %}",
        "Message": "{% 'Run ID: ' & $run_id & '\\nExecution: ' & $states.context.Execution.Id %}"
      },
      "Next": "RunNews"
    },
    "RunNews": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": {
        "Cluster": "${ClusterArn}",
        "TaskDefinition": "${NewsTaskDefinitionArn}",
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "AwsvpcConfiguration": {
            "Subnets": ${SubnetIds},
            "SecurityGroups": ["${SecurityGroupId}"],
            "AssignPublicIp": "ENABLED"
          }
        },
        "Overrides": {"ContainerOverrides": [{"Name": "app", "Command": "{% ['news', '--run-id', $run_id] %}"}]}
      },
      "TimeoutSeconds": 1800,
      "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"error": "{% $states.errorOutput %}"}, "Next": "NotifyFailed"}],
      "Next": "Done"
    },
    "Done": {"Type": "Succeed"},
    "NotifyFailed": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Arguments": {
        "TopicArn": "${TopicArn}",
        "Subject": "{% '[Fintank] News ' & $run_id & ' FAILED' %}",
        "Message": "{% 'News run ' & $run_id & ' failed; the previous files stay live.\\n\\nError: ' & $string($error) & '\\n\\nLogs: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Ffintank$252Fpipeline' %}"
      },
      "Next": "Failed"
    },
    "Failed": {"Type": "Fail", "Error": "NewsRunFailed"}
  }
}
```

- [ ] **Step 5: Write the stack**

`infra/pipeline_stack.py`:

```python
"""Fintank pipeline infrastructure. Design and setup instructions:
docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md"""
from __future__ import annotations

import json
import re
from pathlib import Path

from aws_cdk import (CfnOutput, Duration, RemovalPolicy, Stack)
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct

HERE = Path(__file__).resolve().parent
IMAGE_DIR = HERE.parent / "backend" / "pipelines"
ASL_DIR = HERE / "statemachines"
LIVE_BUCKET = "thetradingfloor"
WEEKLY_NAME = "fintank-weekly-data-run"
NEWS_NAME = "fintank-daily-news"
CONTAINER = "app"                       # the ASL container overrides use this name
WEEKLY_CRON = "cron(0 10 ? * SAT *)"
NEWS_CRON = "cron(30 9 * * ? *)"
LOG_GROUP = "/fintank/pipeline"


def asl_placeholders(path) -> set[str]:
    return set(re.findall(r"\$\{(\w+)\}", Path(path).read_text()))


class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str,
                 always_hold: bool = True, news_notify: str = "all",
                 weekly_schedule: bool = False, news_schedule: bool = False,
                 s3_endpoint: bool = True, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Network: default VPC, public subnets, no NAT gateway (~$32/month saved).
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)
        if s3_endpoint:
            vpc.add_gateway_endpoint("S3Endpoint",
                                     service=ec2.GatewayVpcEndpointAwsService.S3)
        task_sg = ec2.SecurityGroup(self, "TaskSg", vpc=vpc, allow_all_outbound=True,
                                    description="Fintank pipeline tasks: outbound only")
        subnet_ids = vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnet_ids

        # ── Storage.
        state_bucket = s3.Bucket(
            self, "StateBucket", bucket_name=f"fintank-pipeline-{self.account}",
            versioned=True, encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(id="ExpireRuns", prefix="runs/",
                                 expiration=Duration.days(90)),
                s3.LifecycleRule(id="ExpireOldVersions",
                                 noncurrent_version_expiration=Duration.days(14)),
            ])
        live_bucket = s3.Bucket.from_bucket_name(self, "LiveBucket", LIVE_BUCKET)

        # ── Alerts.
        topic = sns.Topic(self, "Alerts", topic_name="fintank-pipeline-alerts")
        topic.add_subscription(subs.EmailSubscription(alert_email))

        # ── Containers.
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc, cluster_name="fintank-pipeline")
        image = ecs.ContainerImage.from_asset(str(IMAGE_DIR),
                                              platform=ecr_assets.Platform.LINUX_AMD64)
        log_group = logs.LogGroup(self, "Logs", log_group_name=LOG_GROUP,
                                  retention=logs.RetentionDays.ONE_MONTH,
                                  removal_policy=RemovalPolicy.DESTROY)
        secrets = {
            name: ecs.Secret.from_ssm_parameter(
                ssm.StringParameter.from_secure_string_parameter_attributes(
                    self, f"Param{name}", parameter_name=f"/fintank/pipeline/{name}"))
            for name in ("FMP_API", "FRED_API", "SERPAPI_KEY")
        }
        environment = {
            "PIPELINE_DATA_ROOT": "/data",
            "STATE_BUCKET": state_bucket.bucket_name,
            "LIVE_BUCKET": LIVE_BUCKET,
            "SNS_TOPIC_ARN": topic.topic_arn,
            "ALWAYS_HOLD": "true" if always_hold else "false",
            "NEWS_NOTIFY": news_notify,
        }

        def task_definition(name, cpu, memory, disk, secret_names):
            td = ecs.FargateTaskDefinition(
                self, f"{name.title()}Task", family=f"fintank-{name}",
                cpu=cpu, memory_limit_mib=memory, ephemeral_storage_gib=disk,
                runtime_platform=ecs.RuntimePlatform(
                    cpu_architecture=ecs.CpuArchitecture.X86_64,
                    operating_system_family=ecs.OperatingSystemFamily.LINUX))
            td.add_container(CONTAINER, image=image, environment=environment,
                             secrets={k: secrets[k] for k in secret_names},
                             logging=ecs.LogDriver.aws_logs(stream_prefix=name,
                                                            log_group=log_group))
            return td

        run_td = task_definition("run", 4096, 16384, 150, ("FMP_API", "FRED_API"))
        publish_td = task_definition("publish", 512, 1024, None, ())
        news_td = task_definition("news", 512, 1024, None, ("FMP_API", "SERPAPI_KEY"))

        # Least privilege: only publish and news can write the live bucket.
        state_bucket.grant_read_write(run_td.task_role)
        topic.grant_publish(run_td.task_role)

        state_bucket.grant_read_write(publish_td.task_role)
        live_bucket.grant_read_write(publish_td.task_role)
        publish_td.task_role.add_to_principal_policy(iam.PolicyStatement(
            actions=["s3:GetBucketVersioning", "s3:GetObjectVersion"],
            resources=[live_bucket.bucket_arn, live_bucket.arn_for_objects("*")]))
        topic.grant_publish(publish_td.task_role)

        live_bucket.grant_put(news_td.task_role, "news_json_articles/*")
        state_bucket.grant_read_write(news_td.task_role, "runs/*")
        topic.grant_publish(news_td.task_role)

        # ── Step Functions.
        sm_role = iam.Role(self, "StateMachineRole",
                           assumed_by=iam.ServicePrincipal("states.amazonaws.com"))
        for td in (run_td, publish_td, news_td):
            sm_role.add_to_policy(iam.PolicyStatement(
                actions=["ecs:RunTask"], resources=[td.task_definition_arn]))
            sm_role.add_to_policy(iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[td.task_role.role_arn, td.obtain_execution_role().role_arn]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["ecs:StopTask", "ecs:DescribeTasks"], resources=["*"]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["events:PutTargets", "events:PutRule", "events:DescribeRule"],
            resources=[f"arn:aws:events:{self.region}:{self.account}:rule/"
                       "StepFunctionsGetEventsForECSTaskRule"]))
        sm_role.add_to_policy(iam.PolicyStatement(
            actions=["states:ListExecutions"],
            resources=[f"arn:aws:states:{self.region}:{self.account}:stateMachine:{n}"
                       for n in (WEEKLY_NAME, NEWS_NAME)]))
        topic.grant_publish(sm_role)
        state_bucket.grant_read_write(sm_role, "runs/*")

        common = {
            "ClusterArn": cluster.cluster_arn,
            "SubnetIds": json.dumps(subnet_ids),
            "SecurityGroupId": task_sg.security_group_id,
            "TopicArn": topic.topic_arn,
        }
        self.substitutions = {
            "weekly.asl.json": {**common, "StateBucket": state_bucket.bucket_name,
                                "RunTaskDefinitionArn": run_td.task_definition_arn,
                                "PublishTaskDefinitionArn": publish_td.task_definition_arn},
            "news.asl.json": {**common, "NewsTaskDefinitionArn": news_td.task_definition_arn,
                              "NotifyStart": "true" if news_notify == "all" else "false"},
        }
        weekly = sfn.StateMachine(
            self, "Weekly", state_machine_name=WEEKLY_NAME, role=sm_role,
            definition_body=sfn.DefinitionBody.from_file(str(ASL_DIR / "weekly.asl.json")),
            definition_substitutions=self.substitutions["weekly.asl.json"])
        news = sfn.StateMachine(
            self, "News", state_machine_name=NEWS_NAME, role=sm_role,
            definition_body=sfn.DefinitionBody.from_file(str(ASL_DIR / "news.asl.json")),
            definition_substitutions=self.substitutions["news.asl.json"])

        # ── Schedules, with a dead-letter queue for runs that never start.
        dlq = sqs.Queue(self, "SchedulerDlq", queue_name="fintank-pipeline-scheduler-dlq",
                        retention_period=Duration.days(14), enforce_ssl=True)
        scheduler_role = iam.Role(self, "SchedulerRole",
                                  assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"))
        weekly.grant_start_execution(scheduler_role)
        news.grant_start_execution(scheduler_role)
        dlq.grant_send_messages(scheduler_role)
        for cid, name, cron, machine, enabled in (
                ("WeeklySchedule", WEEKLY_NAME, WEEKLY_CRON, weekly, weekly_schedule),
                ("NewsSchedule", NEWS_NAME, NEWS_CRON, news, news_schedule)):
            scheduler.CfnSchedule(
                self, cid, name=name, state="ENABLED" if enabled else "DISABLED",
                schedule_expression=cron, schedule_expression_timezone="UTC",
                flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
                target=scheduler.CfnSchedule.TargetProperty(
                    arn=machine.state_machine_arn, role_arn=scheduler_role.role_arn,
                    input="{}",
                    dead_letter_config=scheduler.CfnSchedule.DeadLetterConfigProperty(
                        arn=dlq.queue_arn),
                    retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                        maximum_retry_attempts=3, maximum_event_age_in_seconds=3600)))

        never_started = cw.Alarm(
            self, "ScheduleNeverStarted",
            alarm_description="A Fintank pipeline schedule failed to start its run",
            metric=dlq.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(5)),
            threshold=0, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)
        never_started.add_alarm_action(cw_actions.SnsAction(topic))

        # Timeouts and aborts skip the state machines' own failure email.
        events.Rule(
            self, "ExecutionTimedOutOrAborted",
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail_type=["Step Functions Execution Status Change"],
                detail={"status": ["TIMED_OUT", "ABORTED"],
                        "stateMachineArn": [weekly.state_machine_arn,
                                            news.state_machine_arn]}),
            targets=[targets.SnsTopic(topic, message=events.RuleTargetInput.from_text(
                f"Fintank pipeline execution {events.EventField.from_path('$.detail.name')} "
                f"ended {events.EventField.from_path('$.detail.status')}: "
                f"{events.EventField.from_path('$.detail.executionArn')}"))])

        CfnOutput(self, "StateBucketName", value=state_bucket.bucket_name)
        CfnOutput(self, "WeeklyStateMachine", value=weekly.state_machine_arn)
        CfnOutput(self, "NewsStateMachine", value=news.state_machine_arn)
```

`infra/app.py`:

```python
#!/usr/bin/env python3
"""cdk deploy --profile fintank -c alert_email=you@example.com [-c …]

Context flags (all optional except alert_email):
  always_hold=true|false        hold every weekly run for approval (go-live guard)
  news_notify=all|warnings_only email for every news run, or only problems
  weekly_schedule=on|off        enable the Saturday schedule
  news_schedule=on|off          enable the daily news schedule
  s3_endpoint=on|off            off if the default VPC already has an S3 endpoint
"""
import os

import aws_cdk as cdk

from pipeline_stack import PipelineStack

app = cdk.App()
ctx = app.node.try_get_context
alert_email = ctx("alert_email")
if not alert_email:
    raise SystemExit("pass -c alert_email=you@example.com")

PipelineStack(
    app, "FintankPipeline",
    env=cdk.Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"], region="us-east-1"),
    alert_email=alert_email,
    always_hold=str(ctx("always_hold")).lower() != "false",
    news_notify=ctx("news_notify") or "all",
    weekly_schedule=ctx("weekly_schedule") == "on",
    news_schedule=ctx("news_schedule") == "on",
    s3_endpoint=ctx("s3_endpoint") != "off",
)
app.synth()
```

`infra/cdk.json`:

```json
{
  "app": ".venv/bin/python app.py",
  "context": {
    "always_hold": "true",
    "news_notify": "all",
    "weekly_schedule": "off",
    "news_schedule": "off",
    "s3_endpoint": "on"
  }
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd infra && .venv/bin/python -m pytest -q`
Expected: all pass. The default-VPC lookup is satisfied by CDK's dummy VPC during tests (no AWS call is made); the image asset is staged from `backend/pipelines/` but not built.

If a test fails on a CDK API name (e.g. a renamed property in a newer `aws-cdk-lib`), fix it against the installed version's docs — use Context7 for `aws-cdk-lib` — and keep the asserted behaviour unchanged.

- [ ] **Step 7: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add infra .gitignore
git commit -m "feat(infra): CDK stack for the weekly data and daily news pipelines

Fargate tasks in the default VPC (no NAT), JSONata state machines with an
approval hold and one retry, disabled-by-default schedules with a DLQ alarm,
and least-privilege roles (only publish/news write thetradingfloor).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Django caches refresh at fixed times

**Files:**
- Modify: `backend/fintank_backend/settings.py` (`CELERY_BEAT_SCHEDULE`)
- Create: `backend/fintank_backend/test_beat_schedule.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: beat entries at fixed UTC times after the AWS jobs.

- [ ] **Step 1: Confirm which scheduled tasks read pipeline outputs**

```bash
cd backend && grep -n "def update_news_articles\|def update_universe_profiles\|def update_economic_data" -A6 news/tasks.py analyzer/tasks.py
```

Expected: `update_news_articles` caches `news_json_articles/*`, `update_universe_profiles` caches the profile aggregates, `update_economic_data` caches `econ_data/*` — the three scheduled entries. No other beat entry exists, so nothing else needs moving. If the grep shows a different reader, add it to the 20:00 group and say so in the report.

- [ ] **Step 2: Write the failing test**

`backend/fintank_backend/test_beat_schedule.py`:

```python
from celery.schedules import crontab
from django.conf import settings
from django.test import SimpleTestCase


class BeatScheduleTests(SimpleTestCase):
    """Caches of pipeline outputs refresh at fixed UTC times just after the AWS
    jobs (news 09:30 daily; weekly data Saturdays from 10:00), not 24 h after
    whenever beat happened to start."""

    def test_news_cache_refreshes_after_the_news_job(self):
        entry = settings.CELERY_BEAT_SCHEDULE["update_news_articles_daily"]
        self.assertEqual(entry["schedule"], crontab(hour=10, minute=0))

    def test_market_data_caches_refresh_after_the_weekly_run(self):
        for name in ("update_universe_profiles_daily", "update_economic_data_daily"):
            entry = settings.CELERY_BEAT_SCHEDULE[name]
            self.assertEqual(entry["schedule"], crontab(hour=20, minute=0), name)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && ../../.venv/bin/python manage.py test fintank_backend.test_beat_schedule`
Expected: FAIL — `AssertionError: 86400 != <crontab: 0 10 * * *>`.

- [ ] **Step 4: Edit `settings.py`**

Add `from celery.schedules import crontab` beside the file's other top-level imports, and replace the `CELERY_BEAT_SCHEDULE` dict with:

```python
# Fixed UTC times just after the AWS pipeline jobs (news 09:30 daily, weekly
# data Saturdays from 10:00, done by ~18:00 on a full run), so new S3 data is
# cached within minutes instead of up to 24 h later. See
# docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md.
CELERY_BEAT_SCHEDULE = {
    "update_news_articles_daily": {
        "task": "news.tasks.update_news_articles",
        "schedule": crontab(hour=10, minute=0),
    },
    "update_universe_profiles_daily": {
        "task": "analyzer.tasks.update_universe_profiles",
        "schedule": crontab(hour=20, minute=0),
    },
    "update_economic_data_daily": {
        "task": "analyzer.tasks.update_economic_data",
        "schedule": crontab(hour=20, minute=0),
    },
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ../../.venv/bin/python manage.py test fintank_backend.test_beat_schedule users backtester billing analyzer news`
Expected: OK (the full backend suite still passes).

- [ ] **Step 6: Commit**

```bash
git add backend/fintank_backend/settings.py backend/fintank_backend/test_beat_schedule.py
git commit -m "feat(celery): refresh pipeline-fed caches at fixed UTC times

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Notebooks, runbook and spec sync

**Files:**
- Modify (local only, git-ignored): `backend/class_files/lean_run.ipynb`, `backend/class_files/full_run.ipynb` (JSON edits — never executed)
- Create: `backend/pipelines/README.md`
- Modify: `CLAUDE.md` (fintank), `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`

**Interfaces:**
- Consumes: CLI command names (Task 10), CDK context flags (Task 12).
- Produces: documentation only.

- [ ] **Step 1: Take the uploads out of the notebooks (JSON edit, no execution)**

```bash
cd backend/class_files && ../../../.venv/bin/python - <<'EOF'
import json

NOTE = ("> **Uploads now run on AWS** (`python -m pipelines …`, see "
        "`backend/pipelines/README.md`). The upload cells were removed so a local "
        "run can never push older data over newer. Before exploring locally, run "
        "`python -m pipelines pull-state --yes` from `backend/` to get the latest "
        "state.\n")

for name in ("lean_run.ipynb", "full_run.ipynb"):
    with open(name) as f:
        nb = json.load(f)
    kept, removed = [], 0
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        code_lines = [l.strip().lstrip("# ").strip() for l in src.splitlines() if l.strip()]
        if cell["cell_type"] == "code" and code_lines and all(
                l.startswith("p.upload_") for l in code_lines):
            removed += 1
            continue
        kept.append(cell)
    kept.insert(1, {"cell_type": "markdown", "metadata": {}, "source": [NOTE]})
    nb["cells"] = kept
    with open(name, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(name, "removed", removed, "upload cells")
EOF
```

Expected: `lean_run.ipynb removed 7 upload cells` and `full_run.ipynb removed 8 upload cells` (full_run's commented `# p.refresh_constituents()` / `# p.upload_constituents()` cell is not all-upload, so it stays). These files are git-ignored — nothing to commit.

- [ ] **Step 2: Write `backend/pipelines/README.md`**

```markdown
# Fintank data pipeline

Weekly market data (Saturdays 10:00 UTC — full run in the first week of the
month, lean otherwise) and daily news (09:30 UTC), run on AWS. Design, costs
and the one-time AWS setup: `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`.
Infrastructure: `infra/`.

Run every command from `fintank/backend` with `AWS_PROFILE=fintank` set
(after `aws sso login --profile fintank`).

| Situation | Command |
|---|---|
| "Held" email | read the report link, then `python -m pipelines approve <run-id>` or `discard <run-id>` |
| "Failed" email | open the logs link; resume with `python -m pipelines start --mode <lean\|full> --run-id <run-id>` |
| Bad data went live | `python -m pipelines rollback <run-id>` |
| Run now | `python -m pipelines start --mode lean` (or `full`); news: `python -m pipelines start-news` |
| What happened lately | `python -m pipelines status` |
| Explore data locally | `python -m pipelines pull-state --yes` first |
| Local test, no AWS | `python -m pipelines run --mode lean --dry-run --limit 5`; `python -m pipelines news --dry-run` |
| Change a threshold | edit `pipelines/thresholds.py`, run the tests, `cdk deploy` |

Tests: `../../.venv/bin/python -m pytest pipelines/tests -q`.
```

- [ ] **Step 3: Add the pipeline to `CLAUDE.md`**

Under `## Commands`, after the `### Backend (Django)` block, add:

````markdown
### Data pipeline (`backend/pipelines/`, runs on AWS)

```bash
cd backend
../../.venv/bin/python -m pytest pipelines/tests -q        # tests (moto, no AWS)
python -m pipelines run --mode lean --dry-run --limit 5     # local smoke run
python -m pipelines --help                                  # approve/discard/rollback/status…
cd ../infra && .venv/bin/python -m pytest -q                # CDK stack tests
```

Runbook: `backend/pipelines/README.md`. Design + AWS setup: `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`. The notebooks in `class_files/` no longer upload; `class_files/stock_pipeline.py` and `pipeline_config.py` are shims over `pipelines/`.
````

- [ ] **Step 4: Bring the spec in line with the plan's rulings**

Edit `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`:

1. Status line → `**Status:** Implemented on branch feat/data-pipeline (see docs/superpowers/plans/2026-10-14-automated-data-pipeline.md for rulings R1–R11)`.
2. In "Diff before publish", replace the first bullet's comparison source with: `compare with state/live-manifest.json ({key: sha256}), which every publish and rollback keeps current; published objects also carry x-amz-meta-sha256`.
3. In "Notifications", add a sentence: `Held, Complete and News emails are sent by the Python commands; Started, Failed, Discarded and Skipped by the state machines. A crashing container command also emails directly.`
4. In the checks table, Prices row: Warn → `adjClose ≤ 0; or > 1% of symbols with a > 80% one-day move (moves are always listed)`.
5. In "News", change `≥ 5 articles` to `≥ 50 articles for FMP feeds, ≥ 3 for search topics`.
6. In "ECS task sizes", change the two `21 GiB` cells to `20 GiB (default)`.
7. In "Container", replace the paragraph with: `backend/pipelines/Dockerfile`, build context `backend/pipelines/` only: `python:3.12-slim`, `pip install -r requirements.txt`, non-root user, entrypoint `python -m pipelines`. `factor_windows.py` moved into the package so the context stays small.
8. In "CLI", replace the `resume <run-id>` row with `start --mode M --run-id <id>` (resume a run in a fresh execution) and add a `start-news` row.
9. Setup step 4 commands become:
   ```bash
   cd fintank/backend
   uv pip install --python ../../.venv/bin/python -r pipelines/requirements-dev.txt
   ../../.venv/bin/python -m pytest pipelines/tests -q
   python -m pipelines run --mode lean --dry-run --limit 5
   python -m pipelines news --dry-run
   ```
   and add: `The news dry run is also where SerpAPI's bing_news engine gets confirmed — if every news.<topic> check says "fetch failed", the engine needs replacing before go-live.`
10. Setup step 5 becomes:
    ```bash
    cd fintank/infra
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    cdk diff   --profile fintank -c alert_email=<you@example.com>
    cdk deploy --profile fintank -c alert_email=<you@example.com>
    ```
    plus: `If the deploy fails creating S3Endpoint because the default VPC already has an S3 gateway endpoint, re-run with -c s3_endpoint=off.`
11. Setup step 7: enabling schedules is `cdk deploy … -c news_schedule=on` (step 1) and `… -c news_schedule=on -c weekly_schedule=on` (step 3), not the console; turning `ALWAYS_HOLD` off is `… -c always_hold=false`. Every later deploy must repeat the flags in use (or set them in `infra/cdk.json`).
12. "Day-to-day" table: `Turn it all off` → `cdk deploy … -c news_schedule=off -c weekly_schedule=off`, or `cdk destroy`.

- [ ] **Step 5: Run every test suite once more**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank/backend
../../.venv/bin/python -m pytest pipelines/tests -q
../../.venv/bin/python manage.py test users backtester billing analyzer news fintank_backend.test_beat_schedule
cd ../infra && .venv/bin/python -m pytest -q
```

Expected: all three green.

- [ ] **Step 6: Commit**

```bash
cd /home/franc/projects/ai_agents/ai_tooling/fintank
git add backend/pipelines/README.md CLAUDE.md docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md
git commit -m "docs(pipeline): runbook, CLAUDE.md commands, spec synced to plan rulings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After the plan: Franc's go-live (not agent work)

The spec's "Setup instructions" (as updated in Task 14) are the checklist: budget alert, SSO login, tools, key rotation, SSM parameters, live-bucket versioning, local dry runs, `cdk deploy`, SNS confirmation, `seed-state`, then news → smoke weekly → real weekly → schedules on → `always_hold=false` after three good held runs, and the Celery beat restart.
