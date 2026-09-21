import React from "react"
import Link from "next/link"
import { Container, Row, Col } from "react-bootstrap"

import IndexHeader from "@componentsLegacy/IndexDetail/IndexHeader"
import IndexPriceChart from "@componentsLegacy/IndexDetail/IndexPriceChart"
import IndexInternals from "@componentsLegacy/IndexDetail/IndexInternals"
import RiskDecomposition from "@componentsLegacy/IndexDetail/RiskDecomposition"
import SectorContribution from "@componentsLegacy/IndexDetail/SectorContribution"
import VixComparisonChart from "@componentsLegacy/IndexDetail/VixComparisonChart"
import PeerComparisonSection from "@componentsLegacy/IndexDetail/PeerComparisonSection"
import MoversPanel from "@componentsLegacy/IndexDetail/MoversPanel"
import ValuationsSection from "@componentsLegacy/IndexDetail/ValuationsSection"

import { useIndexQuotes } from "@hooks/useIndexQuotes"
import { fetchIndexSeries } from "@/lib/indexApi"
import indexMetaData from "@data/index-meta.json"

import "@utils/indexDetail/chartOptions" // registers the Chart.js elements

/**
 * Index detail page.
 *
 * Composition only. The previous version ran to 842 lines: five duplicated
 * comparison sections, 20 state variables, 10 identical handlers, and calls to
 * five backend endpoints that no longer existed. It 500'd on every slug because
 * the valuations fetch had no try/catch, and it could not compile at all --
 * `Gallery` pulled in an uninstalled package.
 *
 * The price series is fetched server-side so the page renders with a chart and
 * stays indexable; every other section loads client-side through SWR, so a slow
 * or missing section never blocks the first paint.
 */
export async function getServerSideProps({ query, res }) {
  const { slug } = query
  const nav = { light: true, classes: "shadow", color: "white" }

  // An unknown slug is a 404, not a 500. The old version returned undefined
  // props for anything outside its switch, and Next rejects undefined during
  // prop serialisation -- an SSR error page rather than a real 404.
  //
  // A 404 status with our own state, not `notFound: true`: that hands off to
  // the App Router's not-found path, which throws inside AppProviders and
  // surfaces as a 500. Same workaround as stock-data/[ticker].js.
  if (!indexMetaData[slug]) {
    res.statusCode = 404
    return { props: { nav, title: "Index not found", unknownSlug: slug } }
  }

  try {
    const series = await fetchIndexSeries(slug)
    return {
      props: { nav, title: series.title, slug, series, meta: indexMetaData[slug] },
    }
  } catch (error) {
    if (error?.response?.status === 404) {
      res.statusCode = 404
      return { props: { nav, title: "Index not found", unknownSlug: slug } }
    }
    // Backend down or S3 unreachable: render the shell with the static copy
    // rather than failing the whole request.
    console.error(`indexes/${slug}: index-series fetch failed`, error.message)
    return {
      props: {
        nav,
        title: indexMetaData[slug].title,
        slug,
        series: null,
        meta: indexMetaData[slug],
      },
    }
  }
}

const UnknownIndex = ({ slug }) => (
  <section>
    <Container className="py-6 text-center">
      <Row>
        <Col lg="6" className="mx-auto">
          <h1 className="mb-3">Index not found</h1>
          <p className="text-muted mb-4">
            We don&apos;t cover an index at <code>{slug}</code>. Pick one from the Market
            Performance menu.
          </p>
          <Link href="/markets">Browse market performance</Link>
        </Col>
      </Row>
    </Container>
  </section>
)

const IndexDetail = ({ slug, series, meta, unknownSlug }) => {
  const { quotes } = useIndexQuotes(unknownSlug ? null : slug)

  if (unknownSlug) return <UnknownIndex slug={unknownSlug} />

  const title = series?.title ?? meta.title

  return (
    <section>
      <Container className="py-6">
        <Row>
          <Col lg="8">
            <IndexHeader
              title={title}
              history={meta.indexHistory}
              performance={series?.performance}
              asOf={series?.as_of}
              priceSource={series?.price_source}
            />

            <IndexPriceChart title={title} dates={series?.dates} series={series?.series} />

            <IndexInternals internals={series?.internals} asOf={series?.as_of} />

            <SectorContribution slug={slug} />

            <RiskDecomposition slug={slug} />

            <VixComparisonChart slug={slug} baseTitle={title} />

            <PeerComparisonSection slug={slug} peers={series?.peers} baseTitle={title} />

            <Container>
              <ValuationsSection quotes={quotes} />
            </Container>
          </Col>

          <Col lg="4">
            <MoversPanel quotes={quotes} />
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default IndexDetail
