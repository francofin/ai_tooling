import React, { useEffect, useMemo, useState } from "react"
import { Row, Col, Form, Button } from "react-bootstrap"

/**
 * Client-side screener over a universe-profiles payload (/universe/<slug>).
 * Every record is already in the browser for the list below, so filtering is
 * instant and costs no request.
 *
 * Market cap / AUM is in each record's listing currency, not USD (Toyota's is
 * in yen), so size is only filtered or sorted when everything else in view
 * shares one currency. Mixed universes ask for a currency first rather than
 * comparing yen with dollars.
 */

const UNKNOWN = "__unknown__"
const TOP_COUNTRIES = 12

// "Asset Management - Bonds" -> "Bonds"; bare "Asset Management" is the general bucket.
export const etfCategory = (industry) => {
  if (!industry) return "Other"
  if (industry === "Asset Management") return "General"
  return industry.replace(/^Asset Management - /, "")
}

const KINDS = {
  etf: {
    title: "ETF Screener",
    noun: "ETFs",
    sizeLabel: "AUM",
    ageLabel: "Fund age",
    payoutLabel: "Distributions",
    payoutYes: "Pays distributions",
    payoutNo: "No distributions",
    sectors: false,
    employees: false,
    group: { label: "Category", of: (r) => etfCategory(r.industry), any: "All categories" },
    searchHint: "e.g. S&P 500, bond, gold, XIU",
  },
  equity: {
    title: "Stock Screener",
    noun: "stocks",
    sizeLabel: "Market cap",
    ageLabel: "Listed for",
    payoutLabel: "Dividends",
    payoutYes: "Pays a dividend",
    payoutNo: "No dividend",
    sectors: true,
    employees: true,
    group: null,
    searchHint: "e.g. Apple, bank, SHOP",
  },
}

const SIZE_STEPS = [
  ["1e7", "10M"],
  ["5e7", "50M"],
  ["1e8", "100M"],
  ["5e8", "500M"],
  ["1e9", "1B"],
  ["1e10", "10B"],
  ["1e11", "100B"],
  ["1e12", "1T"],
]
const BETA_STEPS = [["", "Any"], ["0", "0"], ["0.5", "0.5"], ["1", "1"], ["1.5", "1.5"], ["2", "2"]]
const VOLUME_STEPS = [["", "Any"], ["10000", "10K shares"], ["100000", "100K shares"], ["1000000", "1M shares"]]
const EMPLOYEE_STEPS = [["", "Any"], ["100", "100+"], ["1000", "1,000+"], ["10000", "10,000+"], ["100000", "100,000+"]]
const AGE_STEPS = [["", "Any"], ["0-1", "Under 1 year"], ["1-5", "1–5 years"], ["5-10", "5–10 years"], ["10-", "10+ years"]]

const SIZE_SORTS = new Set(["size-desc", "size-asc"])

const DEFAULTS = {
  countries: [],
  sector: "",
  industry: "",
  group: "",
  exchange: "",
  currency: "",
  sizeMin: "",
  sizeMax: "",
  betaMin: "",
  betaMax: "",
  volumeMin: "",
  employeesMin: "",
  payout: "",
  age: "",
  name: "",
  sort: "size-desc",
}

const regionNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" })
  } catch {
    return null
  }
})()

const countryLabel = (code) => {
  if (code === UNKNOWN) return "Unknown"
  try {
    return regionNames?.of(code) || code
  } catch {
    return code
  }
}

// FMP quotes London prices in pence (GBp) but market cap in pounds.
export const sizeCurrency = (currency) => (currency === "GBp" ? "GBP" : currency)

const num = (v) => (v === null || v === undefined || v === "" ? null : Number(v))

const ageInYears = (ipoDate, now) => {
  const t = Date.parse(ipoDate)
  return Number.isFinite(t) ? (now - t) / (365.25 * 24 * 3600 * 1000) : null
}

const countBy = (records, keyOf) => {
  const counts = new Map()
  records.forEach((r) => {
    const k = keyOf(r)
    counts.set(k, (counts.get(k) || 0) + 1)
  })
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

const within = (value, min, max) => {
  if (min === "" && max === "") return true
  const v = num(value)
  if (v === null) return false
  if (min !== "" && v < Number(min)) return false
  if (max !== "" && v > Number(max)) return false
  return true
}

const compare = {
  "size-desc": (a, b) => (num(b.market_cap) ?? -1) - (num(a.market_cap) ?? -1),
  "size-asc": (a, b) => (num(a.market_cap) ?? Infinity) - (num(b.market_cap) ?? Infinity),
  "volume-desc": (a, b) => (num(b.volume_avg) ?? -1) - (num(a.volume_avg) ?? -1),
  "beta-desc": (a, b) => (num(b.beta) ?? -Infinity) - (num(a.beta) ?? -Infinity),
  "beta-asc": (a, b) => (num(a.beta) ?? Infinity) - (num(b.beta) ?? Infinity),
  "employees-desc": (a, b) => (num(b.no_of_employees) ?? -1) - (num(a.no_of_employees) ?? -1),
  newest: (a, b) => String(b.ipo_date || "").localeCompare(String(a.ipo_date || "")),
  oldest: (a, b) => String(a.ipo_date || "9999").localeCompare(String(b.ipo_date || "9999")),
  name: (a, b) => String(a.name || "").localeCompare(String(b.name || "")),
}

/**
 * Filters and sorts `records`. Returns the results plus the single listing
 * currency in view (null when mixed), which decides whether size applies.
 */
export const screenUniverse = (records, f, kind = "equity", now = Date.now()) => {
  const cfg = KINDS[kind]
  const countries = new Set(f.countries)
  const name = f.name.trim().toLowerCase()
  const [ageMin, ageMax] = f.age ? f.age.split("-").map((v) => (v === "" ? null : Number(v))) : [null, null]

  // Everything except size, so the currency check sees what size would act on.
  const base = records.filter((r) => {
    if (countries.size && !countries.has(r.country || UNKNOWN)) return false
    if (cfg.sectors && f.sector && r.sector !== f.sector) return false
    if (cfg.sectors && f.industry && r.industry !== f.industry) return false
    if (cfg.group && f.group && cfg.group.of(r) !== f.group) return false
    if (f.exchange && (r.exchange_short_name || "Unknown") !== f.exchange) return false
    if (f.currency && (r.currency || "Unknown") !== f.currency) return false
    if (!within(r.beta, f.betaMin, f.betaMax)) return false
    if (!within(r.volume_avg, f.volumeMin, "")) return false
    if (cfg.employees && !within(r.no_of_employees, f.employeesMin, "")) return false
    if (f.payout === "yes" && !(num(r.last_dividend) > 0)) return false
    if (f.payout === "no" && num(r.last_dividend) > 0) return false
    if (f.age) {
      const age = ageInYears(r.ipo_date, now)
      if (age === null) return false
      if (ageMin !== null && age < ageMin) return false
      if (ageMax !== null && age >= ageMax) return false
    }
    if (name && !`${r.name || ""} ${r.symbol || ""}`.toLowerCase().includes(name)) return false
    return true
  })

  const currencies = new Set(base.map((r) => sizeCurrency(r.currency || "Unknown")))
  const currency = currencies.size === 1 ? [...currencies][0] : null

  const sized = currency ? base.filter((r) => within(r.market_cap, f.sizeMin, f.sizeMax)) : base

  let sortFn = compare[f.sort] || compare.name
  if (SIZE_SORTS.has(f.sort) && !currency) {
    // Mixed currencies: rank within each currency, biggest currency group first
    // (Russell 2000 is ~99% USD), rather than comparing yen with dollars.
    const groupSize = countBy(base, (r) => sizeCurrency(r.currency || "Unknown"))
    const rank = new Map(groupSize.map(([c], i) => [c, i]))
    const bySize = compare[f.sort]
    sortFn = (a, b) =>
      rank.get(sizeCurrency(a.currency || "Unknown")) - rank.get(sizeCurrency(b.currency || "Unknown")) ||
      bySize(a, b)
  }
  return { results: sized.sort(sortFn), currency, currencies: [...currencies] }
}

const panelStyle = {
  background: "rgba(10, 10, 20, 0.82)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  backdropFilter: "blur(6px)",
  padding: "1.25rem",
}
const labelStyle = {
  fontSize: "0.68rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "rgba(255,255,255,0.55)",
  marginBottom: "4px",
}
const hintStyle = { fontSize: "0.75rem", color: "rgba(255,255,255,0.55)" }
const chipStyle = (active) => ({
  fontSize: "0.78rem",
  borderRadius: "999px",
  padding: "4px 12px",
  border: `1px solid ${active ? "#fff" : "rgba(255,255,255,0.25)"}`,
  background: active ? "#fff" : "transparent",
  color: active ? "#0a0a14" : "rgba(255,255,255,0.8)",
  cursor: "pointer",
})

const Select = ({ label, value, onChange, options, id, disabled }) => (
  <Form.Group controlId={id}>
    <Form.Label style={labelStyle}>{label}</Form.Label>
    <Form.Select size="sm" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map(([v, text, optionDisabled]) => (
        <option key={v} value={v} disabled={optionDisabled}>
          {text}
        </option>
      ))}
    </Form.Select>
  </Form.Group>
)

const withAny = (entries, anyLabel) => [
  ["", anyLabel],
  ...entries.map(([v, n]) => [v, `${v} (${n.toLocaleString()})`]),
]

const UniverseScreener = ({ records, onResults, kind = "equity" }) => {
  const cfg = KINDS[kind]
  const [filters, setFilters] = useState(DEFAULTS)
  const set = (key) => (value) => setFilters((f) => ({ ...f, [key]: value }))

  // Option lists come from the whole universe, not the filtered set, so a
  // choice never disappears out from under the user. Industry is the exception:
  // it narrows to the chosen sector.
  const countries = useMemo(() => countBy(records, (r) => r.country || UNKNOWN), [records])
  const options = useMemo(
    () => ({
      sector: countBy(records.filter((r) => r.sector), (r) => r.sector),
      group: cfg.group ? countBy(records, cfg.group.of) : [],
      exchange: countBy(records, (r) => r.exchange_short_name || "Unknown"),
      currency: countBy(records, (r) => r.currency || "Unknown"),
    }),
    [records, cfg]
  )
  const industries = useMemo(
    () =>
      countBy(
        records.filter((r) => r.industry && (!filters.sector || r.sector === filters.sector)),
        (r) => r.industry
      ),
    [records, filters.sector]
  )

  const { results, currency, currencies } = useMemo(
    () => screenUniverse(records, filters, kind),
    [records, filters, kind]
  )

  useEffect(() => {
    onResults(results)
  }, [results, onResults])

  const toggleCountry = (code) =>
    setFilters((f) => ({
      ...f,
      countries: f.countries.includes(code) ? f.countries.filter((c) => c !== code) : [...f.countries, code],
    }))

  // The busiest countries as chips; the long tail (MSCI has ~45) in a select.
  const chipCountries = countries.filter(
    ([code], i) => i < TOP_COUNTRIES || filters.countries.includes(code)
  )
  const moreCountries = countries.filter(
    ([code], i) => i >= TOP_COUNTRIES && !filters.countries.includes(code)
  )

  const sizeSteps = [["", "Any"], ...SIZE_STEPS.map(([v, text]) => [v, currency ? `${currency} ${text}` : text])]
  const sorts = [
    ["size-desc", `${cfg.sizeLabel}: high to low${currency ? "" : " (within each currency)"}`],
    ["size-asc", `${cfg.sizeLabel}: low to high${currency ? "" : " (within each currency)"}`],
    ["volume-desc", "Avg volume: high to low"],
    ["beta-desc", "Beta: high to low"],
    ["beta-asc", "Beta: low to high"],
    ...(cfg.employees ? [["employees-desc", "Employees: most first"]] : []),
    ["newest", "Newest listing first"],
    ["oldest", "Oldest listing first"],
    ["name", "Name A–Z"],
  ]
  const isDefault = JSON.stringify(filters) === JSON.stringify(DEFAULTS)

  return (
    <div style={panelStyle} className="mb-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h2 className="h6 text-uppercase mb-0" style={{ color: "#fff", letterSpacing: "0.12em" }}>
          {cfg.title}
        </h2>
        <div className="d-flex align-items-center gap-3">
          <span style={{ color: "rgba(255,255,255,0.75)", fontSize: "0.85rem" }}>
            <strong style={{ color: "#fff" }}>{results.length.toLocaleString()}</strong> of{" "}
            {records.length.toLocaleString()} {cfg.noun}
          </span>
          <Button size="sm" variant="outline-light" disabled={isDefault} onClick={() => setFilters(DEFAULTS)}>
            Reset
          </Button>
        </div>
      </div>

      <div className="mb-3">
        <div style={labelStyle}>Country</div>
        <div className="d-flex flex-wrap gap-2 align-items-center" role="group" aria-label="Filter by country">
          <button
            type="button"
            style={chipStyle(filters.countries.length === 0)}
            aria-pressed={filters.countries.length === 0}
            onClick={() => set("countries")([])}
          >
            All countries
          </button>
          {chipCountries.map(([code, count]) => {
            const active = filters.countries.includes(code)
            return (
              <button
                key={code}
                type="button"
                style={chipStyle(active)}
                aria-pressed={active}
                onClick={() => toggleCountry(code)}
              >
                {countryLabel(code)} <span style={{ opacity: 0.6 }}>{count.toLocaleString()}</span>
              </button>
            )
          })}
          {moreCountries.length > 0 && (
            <Form.Select
              size="sm"
              style={{ width: "auto" }}
              value=""
              aria-label="More countries"
              onChange={(e) => e.target.value && toggleCountry(e.target.value)}
            >
              <option value="">More countries ({moreCountries.length})…</option>
              {moreCountries.map(([code, count]) => (
                <option key={code} value={code}>
                  {countryLabel(code)} ({count.toLocaleString()})
                </option>
              ))}
            </Form.Select>
          )}
        </div>
      </div>

      <Row className="g-3">
        {cfg.sectors && (
          <>
            <Col xs={6} md={4} lg={3}>
              <Select
                id="screen-sector"
                label="Sector"
                value={filters.sector}
                onChange={(v) => setFilters((f) => ({ ...f, sector: v, industry: "" }))}
                options={withAny(options.sector, "All sectors")}
              />
            </Col>
            <Col xs={6} md={4} lg={3}>
              <Select id="screen-industry" label="Industry" value={filters.industry} onChange={set("industry")}
                options={withAny(industries, "All industries")} />
            </Col>
          </>
        )}
        {cfg.group && (
          <Col xs={6} md={4} lg={3}>
            <Select id="screen-group" label={cfg.group.label} value={filters.group} onChange={set("group")}
              options={withAny(options.group, cfg.group.any)} />
          </Col>
        )}
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-exchange" label="Exchange" value={filters.exchange} onChange={set("exchange")}
            options={withAny(options.exchange, "All exchanges")} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-currency" label="Currency" value={filters.currency} onChange={set("currency")}
            options={withAny(options.currency, "Any")} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-payout" label={cfg.payoutLabel} value={filters.payout} onChange={set("payout")}
            options={[["", "Any"], ["yes", cfg.payoutYes], ["no", cfg.payoutNo]]} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-age" label={cfg.ageLabel} value={filters.age} onChange={set("age")} options={AGE_STEPS} />
        </Col>

        <Col xs={6} md={4} lg={2}>
          <Select id="screen-size-min" label={`Min ${cfg.sizeLabel}`} value={currency ? filters.sizeMin : ""}
            onChange={set("sizeMin")} options={sizeSteps} disabled={!currency} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-size-max" label={`Max ${cfg.sizeLabel}`} value={currency ? filters.sizeMax : ""}
            onChange={set("sizeMax")} options={sizeSteps} disabled={!currency} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-beta-min" label="Min beta" value={filters.betaMin} onChange={set("betaMin")} options={BETA_STEPS} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-beta-max" label="Max beta" value={filters.betaMax} onChange={set("betaMax")} options={BETA_STEPS} />
        </Col>
        <Col xs={6} md={4} lg={2}>
          <Select id="screen-volume" label="Min avg volume" value={filters.volumeMin} onChange={set("volumeMin")}
            options={VOLUME_STEPS} />
        </Col>
        {cfg.employees && (
          <Col xs={6} md={4} lg={2}>
            <Select id="screen-employees" label="Min employees" value={filters.employeesMin}
              onChange={set("employeesMin")} options={EMPLOYEE_STEPS} />
          </Col>
        )}
        <Col xs={6} md={4} lg={cfg.employees ? 3 : 2}>
          <Select id="screen-sort" label="Sort by" value={filters.sort} onChange={set("sort")} options={sorts} />
        </Col>

        {!currency && (
          <Col xs={12}>
            <div style={hintStyle}>
              {cfg.sizeLabel} is in each listing&apos;s own currency and these results mix{" "}
              {currencies.filter((c) => c !== "Unknown").join(", ") || "several"}. Pick a currency (or a
              single country) to filter by {cfg.sizeLabel.toLowerCase()}; sorting by it ranks within each
              currency.
            </div>
          </Col>
        )}

        <Col xs={12}>
          <Form.Group controlId="screen-name">
            <Form.Label style={labelStyle}>Name or ticker contains</Form.Label>
            <Form.Control
              size="sm"
              type="search"
              placeholder={cfg.searchHint}
              value={filters.name}
              onChange={(e) => set("name")(e.target.value)}
            />
          </Form.Group>
        </Col>
      </Row>
    </div>
  )
}

export default UniverseScreener
