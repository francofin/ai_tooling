import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { Alert, Col, Container, Row, Spinner } from 'react-bootstrap'
import Swiper from '@componentsLegacy/Swiper'
import FundFinderForm from '@componentsLegacy/FundFinder/FundFinderForm'
import FundResultsTable from '@componentsLegacy/FundFinder/FundResultsTable'
import { useFundFinder } from '@hooks/useFundFinder'
import { parseQuery, toQuery, canSearch, top10Footnote, LEVERAGED_FOOTNOTE } from '@utils/fundFinder/query.mjs'
import indexData from '@data/index.json'

// Same header styling and tab title as the other market pages (capital-markets.js).
export async function getStaticProps() {
  return {
    props: {
      nav: { light: true, classes: 'shadow', color: 'white' },
      title: 'Fund Finder',
    },
  }
}

const FundFinder = () => {
  const router = useRouter()
  const [listed, setListed] = useState(null)
  const [include, setInclude] = useState([])
  const [exclude, setExclude] = useState([])
  const [leveraged, setLeveraged] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  // Read the URL once it is available (static pages have an empty query on first render).
  useEffect(() => {
    if (!router.isReady || hydrated) return
    const initial = parseQuery(router.query)
    setListed(initial.listed)
    setInclude(initial.include)
    setExclude(initial.exclude)
    setLeveraged(initial.leveraged)
    setHydrated(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady])

  const state = { listed, include, exclude, leveraged }

  // Keep the URL in step with the form, shallow so nothing is refetched server-side.
  useEffect(() => {
    if (!hydrated) return
    router.replace({ pathname: router.pathname, query: toQuery({ listed, include, exclude, leveraged }) }, undefined, {
      shallow: true,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, listed, include, exclude, leveraged])

  const searchable = canSearch(state)
  const { data, error, isLoading } = useFundFinder(state)
  const picks = data?.include || include

  return (
    <>
      <section className="hero-home">
        <Swiper
          className="hero-slider"
          wrapperClasses="dark-overlay"
          data={indexData.swiperImages}
          simple
          effect="fade"
          speed={2000}
          autoplay={{ delay: 10000 }}
        />
        <Container className="py-6 py-md-7 text-white z-index-20">
          <Row>
            <Col xl="10">
              <div className="text-center text-lg-start">
                <p className="subtitle letter-spacing-4 mb-2 text-secondary text-shadow">{indexData.hero.subTitle}</p>
                <h1 className="display-3 fw-bold text-shadow">Fund Finder</h1>
                <p className="lead text-shadow mb-0">
                  Find ETFs by what they hold: the funds with the most combined weight in the stocks you pick.
                </p>
              </div>
            </Col>
          </Row>
        </Container>
      </section>
      <section className="py-6 bg-gray-100">
        <Container>
          <FundFinderForm
            state={state}
            onListed={setListed}
            onInclude={setInclude}
            onExclude={setExclude}
            onLeveraged={setLeveraged}
          />

          {searchable && isLoading && (
            <div className="text-center py-5">
              <Spinner animation="border" role="status">
                <span className="visually-hidden">Loading</span>
              </Spinner>
            </div>
          )}

          {searchable && error && (
            <Alert variant="danger">{error.message.replace(/^fund finder request failed: /, '')}</Alert>
          )}

          {searchable && data && (
            <>
              {data.unknown?.length > 0 && (
                <p className="small text-muted">Not found: {data.unknown.join(', ')}</p>
              )}
              <FundResultsTable funds={data.funds || []} picks={picks} fetched={data.fetched} />
              {data.fetched && <p className="small text-muted mb-1">Holdings fetched {data.fetched} from fund issuers via FMP.</p>}
              {top10Footnote(data.dropped_top10_only) && (
                <p className="small text-muted mb-1">{top10Footnote(data.dropped_top10_only)}</p>
              )}
              {data.leveraged && <p className="small text-muted mb-1">{LEVERAGED_FOOTNOTE}</p>}
            </>
          )}

          <p className="small text-muted mb-1">
            ETFs only; mutual funds are not covered yet, and Canadian mutual funds are not available.
          </p>
          <p className="small text-muted">Information only, not investment advice.</p>
        </Container>
      </section>
    </>
  )
}

export default FundFinder
