# FMP API Endpoint Reference

## Base URLs

| Version | Base URL |
|---------|----------|
| v3 | `https://financialmodelingprep.com/api/v3/` |
| stable | `https://financialmodelingprep.com/stable/` |

## Authentication

All requests require `?apikey=<FMP_API>` as a query parameter.

In Django/notebooks, read from environment:
```python
FMP_API = os.environ['FMP_API']
FMP_URL = os.environ['FMP_URL']  # set to whichever base URL the endpoint uses
```

**Fallback rule:** If an endpoint returns 404 on one base URL, try the other.

---

## Endpoints

### Quotes & Pricing

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Historical Prices

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Financial Statements

#### Income Statement

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

#### Cash Flow Statement

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

#### Balance Sheet

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Fundamental Metrics & Ratios

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Company Profile

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### News

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Sector & Industry

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Indices & Market Overview

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### ETF

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Crypto

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Market Breadth & Movers

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

### Analyst Estimates & Price Targets

| Endpoint | Base | Method | Description |
|----------|------|--------|-------------|
| | | | |

**Example response shape:**
```json

```

**Notes:**

---

## Rate Limits & Caching Notes

- FMP rate limits vary by plan tier — document your plan's limits here
- All fintank endpoints cache responses in Redis to minimise FMP calls
- Cache TTLs per data type are defined in `docs/superpowers/specs/2026-04-20-fintank-platform-design.md` §7.3

## Agent Instructions

When writing code that calls the FMP API:
1. Check this file first for the correct base URL and endpoint path
2. Always read credentials from `os.environ['FMP_API']` — never hardcode
3. Set a `timeout` on every `requests.get()` call (8–15 seconds)
4. If an endpoint is not in this file, check `https://site.financialmodelingprep.com/developer/docs` and add it here after confirming it works
