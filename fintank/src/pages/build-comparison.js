import React, { useEffect, useMemo, useState } from 'react'
import { Col, Container, Row } from 'react-bootstrap'
import { useRouter } from 'next/router'
import TickerPicker from '@componentsLegacy/Comparison/TickerPicker'
import IndicatorRail from '@componentsLegacy/Comparison/IndicatorRail'
import PanelRail from '@componentsLegacy/Comparison/PanelRail'
import { useDebounce } from '@hooks/useDebounce'
import { deserializeSpec, serializeSpec, validateInstance, MAX_SYMBOLS } from '@utils/technicalSpec'

/**
 * Layout.js renders `<title>{pageProps.title} - Portfolio Manager</title>` and
 * forwards `nav` to Header, so dropping getStaticProps silently costs the page
 * its title and header treatment.
 */
export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: 'shadow',
        color: 'white',
      },
      title: 'Chart Comparison',
    },
  }
}

const ChartComparison = () => {
  const router = useRouter()
  const [symbols, setSymbols] = useState([])
  const [instances, setInstances] = useState([])
  const [seeded, setSeeded] = useState(false)

  // Seed from the query string once the router has hydrated it. There is no
  // shallow-routing precedent in this codebase, so this establishes one.
  useEffect(() => {
    if (!router.isReady || seeded) return
    const { symbols: rawSymbols, indicators } = router.query
    if (typeof rawSymbols === 'string') {
      setSymbols(
        rawSymbols
          .split(',')
          .map((symbol) => symbol.trim().toUpperCase())
          .filter(Boolean)
          .filter((symbol, index, all) => all.indexOf(symbol) === index)
          .slice(0, MAX_SYMBOLS),
      )
    }
    if (typeof indicators === 'string') setInstances(deserializeSpec(indicators))
    setSeeded(true)
  }, [router.isReady, router.query, seeded])

  // Debounce the state object, not the serialized string: debouncing the
  // string leaves `symbols` undebounced, so a ticker added mid-flight mounts a
  // panel that fetches the stale spec and refetches 400ms later.
  const debounced = useDebounce(instances, 400)

  const spec = useMemo(() => {
    const valid = debounced.filter((instance) => !validateInstance(instance))
    return serializeSpec(valid)
  }, [debounced])

  // Write back shallowly so the URL is shareable and back/forward works.
  useEffect(() => {
    if (!seeded) return
    const query = {}
    if (symbols.length) query.symbols = symbols.join(',')
    if (spec) query.indicators = spec
    router.replace({ pathname: '/build-comparison', query }, undefined, {
      shallow: true,
    })
    // router is intentionally omitted: including it re-runs on every replace.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols, spec, seeded])

  const removeSymbol = (symbol) => setSymbols((current) => current.filter((entry) => entry !== symbol))

  return (
    <Container fluid className="py-4">
      <Row>
        <Col xs={12}>
          <h1 className="h4 mb-1">Chart Comparison</h1>
          <p className="text-muted">
            {`Compare up to ${MAX_SYMBOLS} tickers side by side on one year of daily prices. Indicator settings apply to every column, so the panels stay comparable.`}
          </p>
        </Col>
      </Row>

      <Row className="mt-3">
        <Col lg={3} xl={2} className="mb-4">
          <TickerPicker symbols={symbols} onChange={setSymbols} />
          <IndicatorRail instances={instances} onChange={setInstances} />
        </Col>

        <Col lg={9} xl={10}>
          {symbols.length === 0 ? (
            <div className="text-center text-muted py-5 border rounded">Search for a ticker to start comparing.</div>
          ) : (
            <PanelRail symbols={symbols} spec={spec} onRemove={removeSymbol} />
          )}
        </Col>
      </Row>
    </Container>
  )
}

export default ChartComparison
