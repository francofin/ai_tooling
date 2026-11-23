import React, { useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { Alert, Container, Spinner } from 'react-bootstrap'
import FundFinderForm from '@componentsLegacy/FundFinder/FundFinderForm'
import FundResultsTable from '@componentsLegacy/FundFinder/FundResultsTable'
import { useFundFinder } from '@hooks/useFundFinder'
import { parseQuery, toQuery, canSearch } from '@utils/fundFinder/query.mjs'

const FundFinder = () => {
  const router = useRouter()
  const [listed, setListed] = useState(null)
  const [include, setInclude] = useState([])
  const [exclude, setExclude] = useState([])
  const [hydrated, setHydrated] = useState(false)

  // Read the URL once it is available (static pages have an empty query on first render).
  useEffect(() => {
    if (!router.isReady || hydrated) return
    const initial = parseQuery(router.query)
    setListed(initial.listed)
    setInclude(initial.include)
    setExclude(initial.exclude)
    setHydrated(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady])

  const state = { listed, include, exclude }

  // Keep the URL in step with the form, shallow so nothing is refetched server-side.
  useEffect(() => {
    if (!hydrated) return
    router.replace({ pathname: router.pathname, query: toQuery({ listed, include, exclude }) }, undefined, {
      shallow: true,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, listed, include, exclude])

  const searchable = canSearch(state)
  const { data, error, isLoading } = useFundFinder(state)
  const picks = data?.include || include

  return (
    <>
      <Head>
        <title>Fund Finder</title>
      </Head>
      <section className="py-6">
        <Container>
          <h1 className="h2 mb-2">Fund Finder</h1>
          <p className="text-muted mb-4">
            Find ETFs by what they hold: the funds with the most combined weight in the stocks you pick.
          </p>

          <FundFinderForm state={state} onListed={setListed} onInclude={setInclude} onExclude={setExclude} />

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
