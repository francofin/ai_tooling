# Homepage Component Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break `src/pages/index.js` into focused section components under `src/componentsLegacy/Homepage/`, fix the inverted loading bug on all 14 index charts, and remove the unused Redux binding.

**Architecture:** Each visible section of the homepage becomes its own `.js` component in `src/componentsLegacy/Homepage/`. A shared `IndexChartCard` component internalises the `useIndexCharter` hook so the parent doesn't need 14 hook calls. `index.js` becomes a thin composition file: SSR data fetching + rendering section components.

**Tech Stack:** React (Pages Router), Next.js, Chart.js via `react-chartjs-2`, ApexCharts via `react-apexcharts` (dynamic import), React Bootstrap, react-select, SWR, Redux (connect)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/componentsLegacy/Homepage/HeroSection.js` | Hero swiper background + title copy + Random Ticker Search button |
| Create | `src/componentsLegacy/Homepage/IndexReturnsSection.js` | Top Swiper carousel of index returns (calls `useHomeIndex`) |
| Create | `src/componentsLegacy/Homepage/IndexChartCard.js` | Single Chart.js combo chart for one index (calls `useIndexCharter` internally) |
| Create | `src/componentsLegacy/Homepage/IndexChartsSection.js` | Grid of paired `IndexChartCard` components |
| Create | `src/componentsLegacy/Homepage/SectorPerformanceSection.js` | Sector grid with dropdown (calls `useSectorData`) |
| Create | `src/componentsLegacy/Homepage/MoversSection.js` | Gainers + Losers Swiper carousels (receives `moverData` prop) |
| Create | `src/componentsLegacy/Homepage/IndexHeatMapSection.js` | ApexCharts treemap with dropdown (calls `useIndexHeatMaps`) |
| Create | `src/componentsLegacy/Homepage/NewsSection.js` | News card grid (receives `articles` prop) |
| Create | `src/componentsLegacy/Homepage/JumbotronSection.js` | Bottom dark overlay CTA with Discover button |
| Modify | `src/pages/index.js` | Thin composition: SSR + render section components, remove unused Redux |

---

## Task 1: HeroSection

**Files:**
- Create: `src/componentsLegacy/Homepage/HeroSection.js`

Context:
- `Swiper` is at `src/componentsLegacy/Swiper.js`
- `data` (static JSON) has `.hero.title`, `.hero.subTitle`, `.hero.subtitle2`, `.swiperImages`
- `allStocks` is derived from `useStockNames` — the button is disabled until the list loads
- `randomTickerSearch` uses `useRouter` to push to `/stock-data/{symbol}`

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/HeroSection.js
import React from "react"
import { Container, Row, Col, Button } from "react-bootstrap"
import Swiper from "../Swiper"
import { useStockNames } from "../../hooks/useStockNames"
import { useRouter } from "next/router"

const EXCHANGE_LIST = ["NASDAQ", "TSX", "NYSE", "CBOE"]

const HeroSection = ({ data }) => {
  const router = useRouter()
  const { data: stockNames } = useStockNames()
  const allStocks = stockNames?.stocks?.filter(
    (s) => EXCHANGE_LIST.includes(s.exchange_short_name)
  )

  const randomTickerSearch = () => {
    const idx = Math.floor(Math.random() * allStocks.length)
    router.push(`/stock-data/${allStocks[idx].symbol}`)
  }

  return (
    <section className="hero-home">
      <Swiper
        className="hero-slider"
        wrapperClasses="dark-overlay"
        data={data.swiperImages}
        simple
        effect="fade"
        speed={2000}
        autoplay={{ delay: 10000 }}
      />
      <Container className="py-6 py-md-7 text-white z-index-20">
        <Row>
          <Col xl="10">
            {data.hero && (
              <div className="text-center text-lg-start">
                <p className="subtitle letter-spacing-4 mb-2 text-secondary text-shadow">
                  {data.hero.subTitle}
                </p>
                <h1 className="display-3 fw-bold text-shadow">{data.hero.title}</h1>
                <p className="subtitle letter-spacing-4 mb-2 text-secondary text-shadow">
                  {data.hero.subtitle2}
                </p>
              </div>
            )}
            <Button onClick={randomTickerSearch} disabled={!allStocks}>
              Random Ticker Search
            </Button>
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default HeroSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
cd /path/to/fintank && npm run lint -- --quiet 2>&1 | head -30
```

Expected: no new errors for `Homepage/HeroSection.js`.

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/HeroSection.js
git commit -m "feat: extract HeroSection component from homepage"
```

---

## Task 2: IndexReturnsSection

**Files:**
- Create: `src/componentsLegacy/Homepage/IndexReturnsSection.js`

Context:
- Uses `useHomeIndex` hook which calls `/index-performance/` via SWR
- Renders `Swiper` with `indexReturns` prop and `data={indexData.data}`
- `data.topBlocks` has `.subTitle` and `.title` — these are the section heading strings from the static JSON

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/IndexReturnsSection.js
import React from "react"
import { Container } from "react-bootstrap"
import Swiper from "../Swiper"
import { useHomeIndex } from "../../hooks/useHomeIndex"

const IndexReturnsSection = ({ data }) => {
  const indexData = useHomeIndex()

  if (!data.topBlocks) return null

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <div className="text-center pb-lg-4">
          <p className="subtitle text-primary">{data.topBlocks.subTitle}</p>
          <h2 className="mb-5">{data.topBlocks.title}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-3 pb-5"
          wrapperClasses="dark-overlay"
          indexReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={indexData.data}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
    </section>
  )
}

export default IndexReturnsSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/IndexReturnsSection.js
git commit -m "feat: extract IndexReturnsSection component from homepage"
```

---

## Task 3: IndexChartCard (fixes the loading bug)

**Files:**
- Create: `src/componentsLegacy/Homepage/IndexChartCard.js`

Context:
- **The bug:** The original code uses `{loading && <Chart/>}` which shows charts only while fetching and hides them when data arrives. The fix is to render the chart when `!loading` (data ready).
- `useIndexCharter(index)` returns `{ chartData, chartOptions, indexName, loading }`. `loading` starts `true`, becomes `false` after fetch completes.
- `Chart` is from `react-chartjs-2`. ChartJS must be registered — it's done once at the page level; don't duplicate here.
- `chartType` prop (e.g. `"bar"`) defaults to `"bar"` to match original behavior.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/IndexChartCard.js
import React from "react"
import { Chart } from "react-chartjs-2"
import { useIndexCharter } from "../../hooks/useIndexChart"

const IndexChartCard = ({ index, chartType = "bar" }) => {
  const { chartData, chartOptions, loading } = useIndexCharter(index)

  if (loading || !chartOptions) return <div style={{ height: 200 }} />

  return (
    <Chart
      type={chartType}
      options={chartOptions}
      data={chartData}
      height={100}
      width={200}
    />
  )
}

export default IndexChartCard
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/IndexChartCard.js
git commit -m "feat: extract IndexChartCard, fix inverted loading guard on charts"
```

---

## Task 4: IndexChartsSection

**Files:**
- Create: `src/componentsLegacy/Homepage/IndexChartsSection.js`

Context:
- Original paired charts by logical grouping. Declarative config array used here to replace 14 explicit hook calls.
- Each row is a `{ indices: [key, key?], cols: 6|4 }` — two-column rows use `lg="6"`, three-column rows use `lg="4"`.
- `ChartJS.register(...)` must be called once. Do it here since this is where Chart.js components live.
- Chart.js imports: `CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend` from `chart.js`.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/IndexChartsSection.js
import React from "react"
import { Container, Row, Col } from "react-bootstrap"
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js"
import IndexChartCard from "./IndexChartCard"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const CHART_ROWS = [
  { indices: ["sp500", "nas"],        cols: 6 },
  { indices: ["dj",    "rus_1000"],   cols: 6 },
  { indices: ["tsx",   "tsx_60"],     cols: 6 },
  { indices: ["rus_2000", "ftse"],    cols: 6 },
  { indices: ["nik",   "nsei"],       cols: 6 },
  { indices: ["hsi",   "vix"],        cols: 6 },
  { indices: ["short_term", "ten_year", "thirty_year"], cols: 4 },
]

const IndexChartsSection = () => (
  <section className="py-0 bg-gray-100">
    <Container>
      {CHART_ROWS.map((row, rowIdx) => (
        <Row key={rowIdx} className="pt-3">
          {row.indices.map((index) => (
            <Col key={index} lg={row.cols}>
              <IndexChartCard index={index} />
            </Col>
          ))}
        </Row>
      ))}
    </Container>
  </section>
)

export default IndexChartsSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/IndexChartsSection.js
git commit -m "feat: extract IndexChartsSection with declarative chart row config"
```

---

## Task 5: SectorPerformanceSection

**Files:**
- Create: `src/componentsLegacy/Homepage/SectorPerformanceSection.js`

Context:
- Dropdown state (`sectorValue`, `sectorLabel`) lives here — it's local UI state, not needed by parent.
- `useSectorData(sectorValue)` returns `{ data: sectorData }` via SWR.
- `sectorMappings` from `src/utils/IndexMappings.js` — the dropdown options.
- Images: `stock-up.jpg` / `stock-down-3.jpg` under `/images/stockPerformance/`.
- `Image` is the custom one at `src/componentsLegacy/CustomImage.js`.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/SectorPerformanceSection.js
import React, { useState } from "react"
import { Container, Row, Col } from "react-bootstrap"
import Select from "react-select"
import Image from "../CustomImage"
import { useSectorData } from "../../hooks/UseSectorData"
import { sectorMappings } from "../../utils/IndexMappings"

const SectorPerformanceSection = () => {
  const [sectorValue, setSectorValue] = useState(sectorMappings[0].value)
  const [sectorLabel, setSectorLabel] = useState(sectorMappings[0].label)
  const { data: sectorData } = useSectorData(sectorValue)

  if (!sectorData) return null

  return (
    <section className="pt-6 pb-6">
      <Container fluid>
        <div className="text-center">
          <label className="form-label me-2">Select Index For Sector Performance</label>
          <Select
            id="sector-index"
            options={sectorMappings}
            value={sectorValue}
            placeholder={sectorLabel}
            onChange={(opt) => { setSectorLabel(opt.label); setSectorValue(opt.value) }}
            className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
            classNamePrefix="selectpicker"
          />
        </div>
        <div className="text-center pb-lg-4">
          <p className="h2">Sector Performance: {sectorData?.message}</p>
        </div>
        <Row>
          {sectorData.sectors.map((sector, index) => (
            <Col
              key={index}
              xs="4"
              lg="3"
              xl="3"
              className={`px-0 ${
                index === sectorData.sectors.length ? "d-none d-lg-block d-xl-none" : ""
              }`}
            >
              <div
                style={{ minHeight: "400px" }}
                className="d-flex align-items-center dark-overlay hover-scale-bg-image"
              >
                <Image
                  src={`/images/stockPerformance/${
                    parseFloat(sector.averageChange) > 0 ? "stock-up.jpg" : "stock-down-3.jpg"
                  }`}
                  alt={sector.sector}
                  layout="fill"
                  className="bg-image"
                />
                <div className="p-3 p-sm-5 text-white z-index-20">
                  <h4 className="h4 text-center">{sector.sector}</h4>
                  <p className="mb-4">
                    <strong>{parseFloat(sector.averageChange).toFixed(2)}%</strong>
                  </p>
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  )
}

export default SectorPerformanceSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/SectorPerformanceSection.js
git commit -m "feat: extract SectorPerformanceSection component from homepage"
```

---

## Task 6: MoversSection

**Files:**
- Create: `src/componentsLegacy/Homepage/MoversSection.js`

Context:
- Receives `moverData` (SSR prop) with `.gainers` and `.losers` arrays.
- `data.movers.subTitle`, `data.movers.gainers`, `data.movers.losers` — heading strings from static JSON.
- Dropdown state for the heatmap (`indexHeatMapValue`, `indexHeatMapLabel`) lives here.
- `useIndexHeatMaps(indexHeatMapValue, indexHeatMapLabel)` returns `{ options, series, loading }`.
- `ReactApexChart` must be dynamic-imported (SSR: false) — bring that import here.
- `constituentIndexMaps` from `src/utils/IndexMappings.js`.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/MoversSection.js
import React, { useState } from "react"
import { Container, Row } from "react-bootstrap"
import Select from "react-select"
import dynamic from "next/dynamic"
import Swiper from "../Swiper"
import { useIndexHeatMaps } from "../../hooks/useIndexHeatMap"
import { constituentIndexMaps } from "../../utils/IndexMappings"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

const MoversSection = ({ moverData, data }) => {
  const [indexHeatMapValue, setIndexHeatMapValue] = useState(constituentIndexMaps[0].value)
  const [indexHeatMapLabel, setIndexHeatMapLabel] = useState(constituentIndexMaps[0].label)
  const { options: heatMapOptions, series: heatMapSeries } = useIndexHeatMaps(
    indexHeatMapValue,
    indexHeatMapLabel
  )

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <div className="text-center pb-lg-4">
          <p className="subtitle text-primary">{data.movers.subTitle}</p>
          <h2 className="mb-5">{data.movers.gainers}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-1 pb-5"
          wrapperClasses="dark-overlay"
          moverReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={moverData?.gainers}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
      <Container>
        <div className="text-center pb-lg-4">
          <h2 className="mb-5">{data.movers.losers}</h2>
        </div>
        <Swiper
          className="swiper-container-mx-negative pt-1 pb-5"
          wrapperClasses="dark-overlay"
          moverReturns
          perView={1}
          md={2}
          lg={3}
          xl={4}
          data={moverData?.losers}
          loop
          speed={1000}
          pagination
          autoplay={{ delay: 5000 }}
        />
      </Container>
      <Container fluid>
        <div className="text-center">
          <label className="form-label me-2">Select Index For Heat Map Performance</label>
          <Select
            id="heatmap-index"
            options={constituentIndexMaps}
            value={indexHeatMapValue}
            placeholder={indexHeatMapLabel}
            onChange={(opt) => {
              setIndexHeatMapLabel(opt.label)
              setIndexHeatMapValue(opt.value)
            }}
            className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
            classNamePrefix="selectpicker"
          />
        </div>
        <div className="text-center pb-lg-4">
          <p className="h2">{indexHeatMapLabel} Constituent Stock Performance</p>
        </div>
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
      </Container>
    </section>
  )
}

export default MoversSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/MoversSection.js
git commit -m "feat: extract MoversSection (gainers, losers, heatmap) from homepage"
```

---

## Task 7: NewsSection

**Files:**
- Create: `src/componentsLegacy/Homepage/NewsSection.js`

Context:
- Receives `articles` prop (already filtered: no newslanes, no null images — filter happens in `index.js`).
- `data.blogPosts.subTitle`, `.title`, `.button`, `.buttonLink` — heading/CTA strings from static JSON.
- Shows up to 64 articles (index <= 63).
- `NewsPost` is at `src/componentsLegacy/NewsPost.js`.
- `blog` (from `src/data/blog.json`) gated the original render — keep that guard via a `hasPosts` prop.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/NewsSection.js
import React from "react"
import Link from "next/link"
import { Container, Row, Col } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faAngleDoubleRight } from "@fortawesome/free-solid-svg-icons"
import NewsPost from "../NewsPost"

const NewsSection = ({ articles, data }) => {
  if (!articles?.length) return null

  return (
    <section className="py-6 bg-gray-100">
      <Container>
        <Row className="mb-5">
          <Col md="8">
            <p className="subtitle text-primary">{data.blogPosts.subTitle}</p>
            <h2>{data.blogPosts.title}</h2>
          </Col>
          <Col md="4" className="d-md-flex align-items-center justify-content-end">
            <Link href={data.blogPosts.buttonLink} className="text-muted text-sm" target="_blank">
              {data.blogPosts.button}
              <FontAwesomeIcon icon={faAngleDoubleRight} className="ms-2" />
            </Link>
          </Col>
        </Row>
        <Row>
          {articles.slice(0, 64).map((post, index) => (
            <Col key={index} lg="3" sm="6" className="mb-4 hover-animate">
              <NewsPost data={post} />
            </Col>
          ))}
        </Row>
      </Container>
    </section>
  )
}

export default NewsSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/NewsSection.js
git commit -m "feat: extract NewsSection component from homepage"
```

---

## Task 8: JumbotronSection

**Files:**
- Create: `src/componentsLegacy/Homepage/JumbotronSection.js`

Context:
- Dark overlay section with a background image and a "Discover A Company" button.
- `data.jumbotron.img` is the image filename (prepend `/images/`), `.title` is the heading.
- Uses `useStockNames` + `useRouter` — same random-ticker pattern as HeroSection.
- `Image` is `src/componentsLegacy/CustomImage.js`.

- [ ] **Step 1: Create the component**

```js
// src/componentsLegacy/Homepage/JumbotronSection.js
import React from "react"
import { Container, Button } from "react-bootstrap"
import Image from "../CustomImage"
import { useStockNames } from "../../hooks/useStockNames"
import { useRouter } from "next/router"

const EXCHANGE_LIST = ["NASDAQ", "TSX", "NYSE", "CBOE"]

const JumbotronSection = ({ data }) => {
  const router = useRouter()
  const { data: stockNames } = useStockNames()
  const allStocks = stockNames?.stocks?.filter(
    (s) => EXCHANGE_LIST.includes(s.exchange_short_name)
  )

  const randomTickerSearch = () => {
    const idx = Math.floor(Math.random() * allStocks.length)
    router.push(`/stock-data/${allStocks[idx].symbol}`)
  }

  if (!data.jumbotron) return null

  return (
    <section className="py-7 position-relative dark-overlay">
      <Image
        src={`/images/${data.jumbotron.img}`}
        alt=""
        className="bg-image"
        layout="fill"
      />
      <Container>
        <div className="overlay-content text-white py-lg-5">
          <h4 className="display-4 fw-bold text-serif text-shadow mb-5">
            {data.jumbotron.title}
          </h4>
          <Button onClick={randomTickerSearch} variant="light" disabled={!allStocks}>
            Discover A Company
          </Button>
        </div>
      </Container>
    </section>
  )
}

export default JumbotronSection
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add src/componentsLegacy/Homepage/JumbotronSection.js
git commit -m "feat: extract JumbotronSection component from homepage"
```

---

## Task 9: Refactor index.js — compose sections, remove unused Redux

**Files:**
- Modify: `src/pages/index.js`

Context:
- Remove: all hook calls that moved to sub-components (`useIndexCharter` ×14, `useSectorData`, `useIndexHeatMaps`, `useStockNames`, `useHomeIndex`).
- Remove: `ChartJS.register(...)` and chart.js imports (now in `IndexChartsSection`).
- Remove: `ReactApexChart` dynamic import (now in `MoversSection`).
- Remove: `mapStateToProps` / Redux `connect` — `screenerData` was imported but never used in JSX.
- Keep: `getServerSideProps` (SSR fetch of `moverData` + `responseNews`).
- Keep: `data` import from `../data/index.json` (passed as prop to sections).
- The news article filter (`!newslanes && image !== null`) moves here before passing to `NewsSection`.
- `blog` was only used to gate the news section — `NewsSection` now does a `!articles?.length` guard itself, so `blog.json` import can be removed.

- [ ] **Step 1: Replace index.js with the composed version**

```js
// src/pages/index.js
import React from "react"
import axios from "axios"
import data from "../data/index.json"
import HeroSection from "../componentsLegacy/Homepage/HeroSection"
import IndexReturnsSection from "../componentsLegacy/Homepage/IndexReturnsSection"
import IndexChartsSection from "../componentsLegacy/Homepage/IndexChartsSection"
import SectorPerformanceSection from "../componentsLegacy/Homepage/SectorPerformanceSection"
import MoversSection from "../componentsLegacy/Homepage/MoversSection"
import NewsSection from "../componentsLegacy/Homepage/NewsSection"
import JumbotronSection from "../componentsLegacy/Homepage/JumbotronSection"

const fetcher = async (url) => {
  const res = await axios.get(url)
  return res.data
}

export async function getServerSideProps() {
  const moverData = await fetcher(
    `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/gainers-losers/`
  )

  let responseNews = []
  try {
    const fmpRes = await axios.get(
      `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/get_articles/fmp`
    )
    responseNews = fmpRes.data ?? []
  } catch (_) {
    // news fetch failed — page renders with empty articles
  }

  return {
    props: {
      nav: { light: true, classes: "shadow", color: "white" },
      title: "Fintank",
      data,
      moverData,
      responseNews,
    },
  }
}

const Index = ({ moverData, responseNews }) => {
  const fmpArticles = Array.isArray(responseNews)
    ? responseNews
    : (responseNews?.data ?? [])
  const filteredArticles = fmpArticles.filter(
    (a) => a.site !== "newslanes" && a.image !== null
  )

  return (
    <React.Fragment>
      <HeroSection data={data} />
      <IndexReturnsSection data={data} />
      <IndexChartsSection />
      <SectorPerformanceSection />
      {moverData && <MoversSection moverData={moverData} data={data} />}
      <NewsSection articles={filteredArticles} data={data} />
      <JumbotronSection data={data} />
    </React.Fragment>
  )
}

export default Index
```

- [ ] **Step 2: Verify no lint errors**

```bash
npm run lint -- --quiet 2>&1 | head -30
```

Expected: no errors or warnings for `src/pages/index.js`.

- [ ] **Step 3: Build check**

```bash
npm run build 2>&1 | tail -20
```

Expected: build completes without errors. Warnings about image optimisation are acceptable.

- [ ] **Step 4: Commit**

```bash
git add src/pages/index.js
git commit -m "refactor: compose homepage from section components, drop unused Redux binding"
```

---

## Self-Review

### Spec Coverage

| Requirement | Covered by |
|---|---|
| Fix inverted loading bug | Task 3 — `IndexChartCard` renders when `!loading` |
| Remove unused Redux `screenerData` | Task 9 — `mapStateToProps` and `connect` removed |
| HeroSection | Task 1 |
| IndexReturnsSection | Task 2 |
| IndexChartsSection (14 charts) | Tasks 3 + 4 |
| SectorPerformanceSection | Task 5 |
| MoversSection (gainers, losers, heatmap) | Task 6 |
| NewsSection | Task 7 |
| JumbotronSection | Task 8 |
| Thin index.js composition | Task 9 |

### Placeholder Scan

No TBDs, no "implement later", no steps without code. ✓

### Type Consistency

- `useIndexCharter` imported as `../../hooks/useIndexChart` (filename is `useIndexChart.js`, not `useIndexCharter.js`) — confirmed correct.
- `useSectorData` imported as `../../hooks/UseSectorData` (filename is `UseSectorData.js` with capital U) — confirm before running.
- `useIndexHeatMaps` from `../../hooks/useIndexHeatMap` (filename `useIndexHeatMap.js`) — confirmed correct.
- `useHomeIndex` from `../../hooks/useHomeIndex` — confirmed correct.
- `useStockNames` from `../../hooks/useStockNames` — confirmed correct.
- `constituentIndexMaps` and `sectorMappings` from `../../utils/IndexMappings` — confirmed correct.

> **Important:** File [UseSectorData.js](src/hooks/UseSectorData.js) has a capital U. Imports in `SectorPerformanceSection.js` use `../../hooks/UseSectorData` — this is correct on case-sensitive Linux filesystems but double-check when running.
