import React, { useMemo, useState } from 'react'
import { Alert, Button, Col, Row, Spinner } from 'react-bootstrap'

import ProfileLayout from '@componentsLegacy/Profile/ProfileLayout'
import PortfolioBuilder from '@componentsLegacy/Backtest/PortfolioBuilder'
import BacktestSettings from '@componentsLegacy/Backtest/BacktestSettings'
import AdvancedSettings from '@componentsLegacy/Backtest/AdvancedSettings'
import QuotaBanner from '@componentsLegacy/Backtest/QuotaBanner'
import { DEFAULT_SETTINGS, buildRequestPayload } from '@componentsLegacy/Backtest/backtestDefaults'
import useBacktestRun from '@hooks/useBacktestRun'
import useBacktestQuota from '@hooks/useBacktestQuota'

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: 'shadow',
        color: 'white',
      },
      loggedUser: true,
      title: 'Backtest Portfolio',
    },
  }
}

const PROGRESS_LABELS = {
  loading_prices: 'Loading price history…',
  optimizing: 'Choosing weights…',
  simulating: 'Simulating…',
  computing_metrics: 'Crunching the statistics…',
}

const BacktestPortfolio = () => {
  const [holdings, setHoldings] = useState([])
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const { status, progress, result, error, quotaError, submit } = useBacktestRun()
  const { quota, reload: reloadQuota } = useBacktestQuota()

  const updateSettings = (patch) => setSettings((current) => ({ ...current, ...patch }))

  const canRun = holdings.length >= 1 && status !== 'running' && status !== 'submitting'
  const busy = status === 'running' || status === 'submitting'

  const payload = useMemo(() => buildRequestPayload(holdings, settings), [holdings, settings])

  const run = async () => {
    await submit(payload)
    reloadQuota()
  }

  return (
    <ProfileLayout>
      <Row>
        <Col xl={12}>
          <h4 className="mb-1">Backtest a portfolio</h4>
          <p className="text-muted fs-13px">
            Build a basket, choose how it is weighted, and see how it would have behaved. Every result comes with an
            honest account of what the simulation cannot tell you.
          </p>

          <PortfolioBuilder
            holdings={holdings}
            settings={settings}
            onHoldingsChange={setHoldings}
            onSettingsChange={updateSettings}
          />
          <BacktestSettings settings={settings} onChange={updateSettings} />
          <AdvancedSettings settings={settings} onChange={updateSettings} />

          <div className="d-flex align-items-center gap-3 mb-4">
            <Button variant="primary" disabled={!canRun} onClick={run}>
              {busy ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  {PROGRESS_LABELS[progress] || 'Running…'}
                </>
              ) : (
                'Run backtest'
              )}
            </Button>
            <QuotaBanner quota={quota} quotaError={quotaError} />
          </div>

          {error && (
            <Alert variant="danger">
              <strong>The backtest did not run.</strong>
              <div className="fs-13px">{error}</div>
            </Alert>
          )}

          {result && (
            <Alert variant="success">
              Simulated {result.effective_start} to {result.effective_end}. Results rendering lands in the next step.
            </Alert>
          )}
        </Col>
      </Row>
    </ProfileLayout>
  )
}

export default BacktestPortfolio
