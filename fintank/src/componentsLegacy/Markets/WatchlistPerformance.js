import React, { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Form, Spinner } from "react-bootstrap"
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js"
import { Chart } from "react-chartjs-2"
import { useWatchlist, useWatchlistPerformance } from "../../hooks/useWatchlistPerformance"
import { fmtPercent } from "../../utils/quoteFormat"

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend)

// Order the tiles are shown in. Mirrors PERIOD_ORDER in the backend's
// analyzer_utils/watchlist_performance.py.
const PERIODS = ["1D", "1W", "1M", "3M", "YTD", "1Y"]

const formatAdded = (value) => {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}

/** One labelled return. A null value renders as an em dash, never as 0.00%. */
const PerformanceTile = ({ label, value, sub }) => {
  const tone = value == null ? "muted" : value > 0 ? "up" : value < 0 ? "down" : "flat"
  return (
    <div className={`watchlist-tile watchlist-tile-${tone}`}>
      <div className="watchlist-tile-label">{label}</div>
      <div className="watchlist-tile-value">{value == null ? "—" : fmtPercent(value)}</div>
      {sub && <div className="watchlist-tile-sub">{sub}</div>}
    </div>
  )
}

/**
 * Watchlist performance panel: pick a holding, see its price history, its
 * returns over the standard horizons, and its return since it was added.
 *
 * Every figure comes from the server's cached daily series, so switching symbols
 * costs one request and no upstream API call.
 */
const WatchlistPerformance = () => {
  const { data: watchlist, error: listError, isLoading: listLoading } = useWatchlist()
  const [symbol, setSymbol] = useState("")

  const holdings = useMemo(() => (Array.isArray(watchlist) ? watchlist : []), [watchlist])

  // Select the first holding once the list arrives, and recover if the selected
  // symbol is removed from the watchlist in another tab.
  useEffect(() => {
    if (holdings.length === 0) {
      setSymbol("")
      return
    }
    setSymbol((current) =>
      current && holdings.some((h) => h.symbol === current) ? current : holdings[0].symbol
    )
  }, [holdings])

  const { data, error, isLoading } = useWatchlistPerformance(symbol)

  const chart = useMemo(() => {
    if (!data?.dates?.length || !data?.prices?.length) return null

    const prices = data.prices
    const gained = prices[prices.length - 1] >= prices[0]
    const color = gained ? "#16a34a" : "#dc2626"

    return {
      data: {
        labels: data.dates,
        datasets: [
          {
            type: "line",
            label: data.symbol,
            data: prices,
            borderColor: color,
            backgroundColor: color,
            pointRadius: 0,
            borderWidth: 2,
            tension: 0.15,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: $${Number(ctx.raw).toFixed(2)}`,
            },
          },
        },
        scales: {
          y: { title: { display: true, text: "Price" } },
          x: { ticks: { maxTicksLimit: 8 } },
        },
      },
    }
  }, [data])

  if (listLoading) {
    return (
      <div className="text-center py-4">
        <Spinner animation="border" variant="light" size="sm" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
      </div>
    )
  }

  if (listError) {
    return <p className="text-inverse text-opacity-50 mb-0">Your watchlist is unavailable right now.</p>
  }

  if (holdings.length === 0) {
    return (
      <p className="text-inverse text-opacity-75 mb-0">
        Your watchlist is empty. Add stocks from the{" "}
        <Link href="/markets">markets page</Link> to track how they have performed
        since you added them.
      </p>
    )
  }

  const sinceAdded = data?.since_added
  const addedOn = formatAdded(data?.date_added)

  return (
    <div className="watchlist-performance">
      <Form.Group controlId="watchlist-performance-select" className="mb-3">
        <Form.Label className="visually-hidden">Watchlist stock</Form.Label>
        <Form.Select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          aria-label="Watchlist stock"
        >
          {holdings.map((holding) => (
            <option key={holding.symbol} value={holding.symbol}>
              {holding.symbol}
              {holding.name ? ` — ${holding.name}` : ""}
            </option>
          ))}
        </Form.Select>
      </Form.Group>

      {error && (
        <p className="text-inverse text-opacity-50 mb-0">
          {error?.response?.data?.detail || "Performance data is unavailable for this symbol."}
        </p>
      )}

      {!error && isLoading && (
        <div className="text-center py-4">
          <Spinner animation="border" variant="light" size="sm" role="status">
            <span className="visually-hidden">Loading...</span>
          </Spinner>
        </div>
      )}

      {!error && !isLoading && chart && (
        <>
          {/* Chart.js draws to a canvas in its own dark-on-transparent defaults,
              which CSS cannot reach, so it keeps a light surface of its own. */}
          <div className="index-chart-panel">
            <div style={{ position: "relative", height: 260 }}>
              <Chart type="line" data={chart.data} options={chart.options} />
            </div>
          </div>

          <div className="watchlist-tiles">
            {PERIODS.map((period) => (
              <PerformanceTile key={period} label={period} value={data.periods?.[period]} />
            ))}
            <PerformanceTile
              label="Since added"
              value={sinceAdded?.return}
              sub={
                sinceAdded?.truncated
                  ? "from earliest available price"
                  : addedOn || undefined
              }
            />
          </div>

          <p className="watchlist-performance-note mb-0">
            Daily closing prices. 1D is the move from the previous close, not
            live intraday.
          </p>
        </>
      )}
    </div>
  )
}

export default WatchlistPerformance
