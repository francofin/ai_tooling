# Homepage Heatmap Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing flat ApexCharts treemap in `MoversSection.js` to use a dark terminal aesthetic with symbol + % change on every cell and stock-page navigation on click.

**Architecture:** All changes are frontend-only. The hook `useIndexHeatMaps` owns the ApexCharts options object — updating it there propagates to the chart automatically. `MoversSection.js` gets a loading skeleton so the 750px layout space is held while data fetches.

**Tech Stack:** Next.js (Pages Router), ApexCharts (`react-apexcharts`), `next/router`

---

## File Map

| File | Change |
|---|---|
| `src/hooks/useIndexHeatMap.js` | Add `useRouter`, update ApexCharts options (dark bg, new color scale, formatter, click handler) |
| `src/componentsLegacy/Homepage/MoversSection.js` | Replace bare chart conditional with skeleton-or-chart pattern |
| `.gitignore` | Add `.superpowers/` entry |

---

### Task 1: Add `.superpowers/` to `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the entry**

Open `.gitignore` and append after the existing `# production` block (or at end of file):

```
# brainstorming visual companion
.superpowers/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .superpowers brainstorm directory"
```

---

### Task 2: Update `useIndexHeatMap.js` — dark palette, labels, click navigation

**Files:**
- Modify: `src/hooks/useIndexHeatMap.js`

- [ ] **Step 1: Add `useRouter` import**

Replace the first line of the file:

```js
import React, {useState, useEffect} from 'react';
import { useRouter } from 'next/router';
import {fetcher} from '../utils/helpers';
```

- [ ] **Step 2: Call `useRouter` at the top of the hook**

Add one line immediately after `const [indexUniverseData, setIndexUniverseData] = useState([])`:

```js
const router = useRouter()
```

- [ ] **Step 3: Replace the `setOptions(...)` call**

Replace the entire `setOptions({...})` block (lines 28–71 in the original) with:

```js
setOptions({
  legend: { show: false },
  chart: {
    height: 350,
    type: 'treemap',
    toolbar: { show: false },
    background: '#0d1117',
    foreColor: '#c9d1d9',
    events: {
      dataPointSelection: function(event, chartContext, config) {
        const symbol = config.w.config.series[0]?.data[config.dataPointIndex]?.x
        if (symbol) router.push(`/stocks/${symbol}`)
      }
    }
  },
  title: {
    text: `${indexName} Stock Performance`,
    align: 'left',
    style: { color: '#c9d1d9' }
  },
  dataLabels: {
    enabled: true,
    style: { fontSize: '12px' },
    formatter: function(text, op) {
      return [text, `${op.value}%`]
    },
    offsetY: -4
  },
  plotOptions: {
    treemap: {
      enableShades: false,
      colorScale: {
        ranges: [
          { from: -9999,   to: -6,      color: '#5a0a10' },
          { from: -5.9999, to: -3,      color: '#3d0912' },
          { from: -2.9999, to: -0.0001, color: '#3d0912' },
          { from: -0.0001, to: 0.0001,  color: '#1c1c1e' },
          { from: 0.0001,  to: 3,       color: '#0d3a18' },
          { from: 3.0001,  to: 9999,    color: '#0d4a1f' },
        ]
      }
    }
  },
  tooltip: {
    theme: 'dark',
    y: { formatter: (value) => `${value}%` }
  }
})
```

- [ ] **Step 4: Verify the full file looks correct**

The complete file should be:

```js
import React, {useState, useEffect} from 'react';
import { useRouter } from 'next/router';
import {fetcher} from '../utils/helpers';

export const useIndexHeatMaps = (index, initialIndexName) => {
    const [loading, setLoading] = useState(true)
    const [series, setSeries] = useState([])
    const [options, setOptions] = useState(undefined)
    const [indexName, setIndexName] = useState(initialIndexName)
    const [indexUniverseData, setIndexUniverseData] = useState([])
    const router = useRouter()

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const baseUrl = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/constituent-returns/${index}`
                const indexDataPack = await fetcher(baseUrl);
                const universeData = indexDataPack?.universe_data || []
                const heatMapData = indexDataPack?.heat_map || []

                setIndexUniverseData(universeData)
                setSeries([{data: heatMapData}])

                setOptions({
                  legend: { show: false },
                  chart: {
                    height: 350,
                    type: 'treemap',
                    toolbar: { show: false },
                    background: '#0d1117',
                    foreColor: '#c9d1d9',
                    events: {
                      dataPointSelection: function(event, chartContext, config) {
                        const symbol = config.w.config.series[0]?.data[config.dataPointIndex]?.x
                        if (symbol) router.push(`/stocks/${symbol}`)
                      }
                    }
                  },
                  title: {
                    text: `${indexName} Stock Performance`,
                    align: 'left',
                    style: { color: '#c9d1d9' }
                  },
                  dataLabels: {
                    enabled: true,
                    style: { fontSize: '12px' },
                    formatter: function(text, op) {
                      return [text, `${op.value}%`]
                    },
                    offsetY: -4
                  },
                  plotOptions: {
                    treemap: {
                      enableShades: false,
                      colorScale: {
                        ranges: [
                          { from: -9999,   to: -6,      color: '#5a0a10' },
                          { from: -5.9999, to: -3,      color: '#3d0912' },
                          { from: -2.9999, to: -0.0001, color: '#3d0912' },
                          { from: -0.0001, to: 0.0001,  color: '#1c1c1e' },
                          { from: 0.0001,  to: 3,       color: '#0d3a18' },
                          { from: 3.0001,  to: 9999,    color: '#0d4a1f' },
                        ]
                      }
                    }
                  },
                  tooltip: {
                    theme: 'dark',
                    y: { formatter: (value) => `${value}%` }
                  }
                })
            } catch (error) {
                console.error("Error fetching heat map data:", error);
            } finally {
                setLoading(false)
            }
        }
        fetchData()
    }, [index, indexName]);

    return { options, series, loading, indexUniverseData }
}
```

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useIndexHeatMap.js
git commit -m "feat: restyle heatmap with dark terminal palette and stock navigation"
```

---

### Task 3: Add loading skeleton in `MoversSection.js`

**Files:**
- Modify: `src/componentsLegacy/Homepage/MoversSection.js`

- [ ] **Step 1: Replace the chart conditional block**

Find this block (lines 79–88):

```jsx
<Row>
  {typeof window !== "undefined" && heatMapOptions && (
    <ReactApexChart
      options={heatMapOptions}
      series={heatMapSeries}
      type="treemap"
      height={750}
    />
  )}
</Row>
```

Replace with:

```jsx
<Row>
  {typeof window !== "undefined" && (
    heatMapOptions ? (
      <ReactApexChart
        options={heatMapOptions}
        series={heatMapSeries}
        type="treemap"
        height={750}
      />
    ) : (
      <div
        style={{
          height: 750,
          background: '#0d1117',
          borderRadius: 6,
          opacity: 0.5,
        }}
        className="placeholder-glow"
      />
    )
  )}
</Row>
```

- [ ] **Step 2: Commit**

```bash
git add src/componentsLegacy/Homepage/MoversSection.js
git commit -m "feat: add dark loading skeleton for heatmap"
```

---

### Task 4: Manual browser verification

- [ ] **Step 1: Start the dev server**

```bash
npm run dev
```

Expected: server starts on `http://localhost:8020`

- [ ] **Step 2: Open the homepage**

Navigate to `http://localhost:8020`. Scroll down past the gainers/losers swiper.

Expected:
- Dark `#0d1117` background skeleton shows while data loads
- Once loaded: dark treemap appears with green/red cells
- Every cell (large and small) shows ticker symbol + `%` value
- Cells for > +3% change are dark green (`#0d4a1f`)
- Cells for < -6% change are deep red (`#5a0a10`)
- Near-zero cells are dark neutral (`#1c1c1e`)

- [ ] **Step 3: Test click navigation**

Click any stock tile.

Expected: browser navigates to `/stocks/[SYMBOL]` (404 is acceptable — page not yet built).

- [ ] **Step 4: Test index switcher**

Use the dropdown to switch from S&P 500 to NASDAQ (or another index).

Expected: chart re-renders with new data, dark styling persists.
