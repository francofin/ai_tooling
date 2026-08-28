import React, { useEffect, useMemo, useState } from "react"
import { Form } from "react-bootstrap"
import { Range, getTrackBackground } from "react-range"
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
import IndexChartView from "../Homepage/IndexChartView"
import { useIndexCharter } from "../../hooks/useIndexChart"
import { indexChartMaps } from "../../utils/IndexMappings"
import { sliceChartData, fullRange } from "../../utils/chartRange"

// Chart.js needs its pieces registered before any chart renders. The homepage
// does this in `IndexChartsSection`; registering is idempotent, so doing it here
// too lets this component stand alone on a page that never mounts that section.
ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend)

const TRACK_FILL = "#0d6efd"
const TRACK_REST = "#d5d8dc"

/**
 * One homepage index chart at a time, with a dropdown to pick the index and a
 * two-handled slider to narrow it to a date range.
 *
 * The chart is drawn by the homepage's own `IndexChartView`, so it stays
 * identical in appearance; this component only decides which index is shown and
 * which slice of it reaches the chart.
 *
 * @param defaultIndex  key from `indexChartMaps` to open on
 * @param label         text for the select's accessible label
 */
const IndexChartPicker = ({ defaultIndex = indexChartMaps[0].value, label = "Index" }) => {
  const [index, setIndex] = useState(defaultIndex)
  const { chartData, chartOptions, indexName, loading } = useIndexCharter(index)

  const labels = chartData?.labels ?? []
  const pointCount = labels.length
  const [range, setRange] = useState(null)

  // Each index returns its own history length, so a range chosen for the previous
  // one cannot carry over — reset to the full window whenever the series changes.
  useEffect(() => {
    setRange(pointCount > 0 ? fullRange(pointCount) : null)
  }, [pointCount, index])

  const visible = useMemo(() => sliceChartData(chartData, range), [chartData, range])

  // A one-point window gives Chart.js nothing to draw a line between, so the
  // handles are kept at least one step apart.
  const sliderReady = range !== null && pointCount > 1

  return (
    <div className="index-chart-picker">
      <Form.Group controlId="index-chart-picker-select" className="mb-3">
        <Form.Label className="visually-hidden">{label}</Form.Label>
        <Form.Select value={index} onChange={(e) => setIndex(e.target.value)} aria-label={label}>
          {indexChartMaps.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Form.Select>
      </Form.Group>

      {/*
        Chart.js paints axis ticks, gridlines and the legend onto a canvas using
        its own dark-on-transparent defaults, which CSS cannot reach. On a dark
        surface that is close to illegible, so the chart keeps the light panel it
        has on the homepage instead of inheriting whatever it is dropped onto.
      */}
      <div className="index-chart-panel">
        <IndexChartView
          chartData={visible}
          chartOptions={chartOptions}
          indexName={indexName}
          loading={loading}
        />

        {sliderReady && (
          <div className="index-chart-range">
            <Range
              step={1}
              min={0}
              max={pointCount - 1}
              values={range}
              onChange={setRange}
              renderTrack={({ props, children }) => (
                <div
                  onMouseDown={props.onMouseDown}
                  onTouchStart={props.onTouchStart}
                  className="index-chart-range-track-hit"
                >
                  <div
                    ref={props.ref}
                    className="index-chart-range-track"
                    style={{
                      background: getTrackBackground({
                        values: range,
                        colors: [TRACK_REST, TRACK_FILL, TRACK_REST],
                        min: 0,
                        max: pointCount - 1,
                      }),
                    }}
                  >
                    {children}
                  </div>
                </div>
              )}
              renderThumb={({ props, isDragged }) => (
                <div
                  {...props}
                  className={`index-chart-range-thumb${isDragged ? " is-dragged" : ""}`}
                  style={props.style}
                />
              )}
            />
            <div className="index-chart-range-labels">
              <span>{labels[range[0]]}</span>
              <span>{labels[range[1]]}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default IndexChartPicker
