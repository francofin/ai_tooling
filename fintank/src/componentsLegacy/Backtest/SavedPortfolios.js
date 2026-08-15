import React, { useState } from 'react'
import { Alert, Button, Card, Form, InputGroup, Table } from 'react-bootstrap'

import usePortfolios from '@hooks/usePortfolios'

/**
 * List, load, duplicate and delete. All of it free — only running meters — which
 * the copy states so the meter does not feel like it is watching everything.
 */
const SavedPortfolios = ({ holdings, settings, onLoad }) => {
  const { portfolios, loading, error, create, remove, duplicate } = usePortfolios()
  const [name, setName] = useState('')
  const [saved, setSaved] = useState(null)

  const save = async () => {
    if (!name.trim() || holdings.length === 0) return
    const created = await create({
      name: name.trim(),
      benchmark_symbol: settings.benchmarkSymbol,
      initial_amount: Number(settings.initialAmount) || 10000,
      periodic_contribution: Number(settings.periodicContribution) || 0,
      contribution_frequency: settings.contributionFrequency,
      weighting_scheme: settings.weightingScheme,
      backtest_mode: settings.backtestMode,
      rebalance_frequency: settings.rebalanceFrequency,
      settings: { ...settings },
      holdings: holdings.map((holding, index) => ({
        symbol: holding.symbol,
        target_weight: Number(holding.weight || 0) / 100,
        order: index,
      })),
    })
    if (created) {
      setName('')
      setSaved(`Saved “${created.name}”.`)
    }
  }

  const load = (portfolio) => {
    onLoad({
      holdings: (portfolio.holdings || []).map((holding) => ({
        symbol: holding.symbol,
        name: '',
        kind: 'stock',
        weight: Number(holding.target_weight) * 100,
      })),
      settings:
        portfolio.settings && Object.keys(portfolio.settings).length
          ? portfolio.settings
          : {
              benchmarkSymbol: portfolio.benchmark_symbol,
              initialAmount: Number(portfolio.initial_amount),
              periodicContribution: Number(portfolio.periodic_contribution),
              contributionFrequency: portfolio.contribution_frequency,
              weightingScheme: portfolio.weighting_scheme,
              backtestMode: portfolio.backtest_mode,
              rebalanceFrequency: portfolio.rebalance_frequency,
            },
    })
  }

  return (
    <Card className="border-0 shadow-sm mb-4">
      <Card.Body>
        <h5 className="mb-2">Saved portfolios</h5>
        <p className="text-muted fs-13px">
          Saving, loading, copying and deleting are always free — only running a backtest uses an allowance.
        </p>

        <InputGroup className="mb-3">
          <Form.Control
            placeholder="Name this portfolio…"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button variant="outline-primary" onClick={save} disabled={!name.trim() || holdings.length === 0}>
            Save current
          </Button>
        </InputGroup>

        {saved && (
          <Alert variant="success" className="fs-13px py-2">
            {saved}
          </Alert>
        )}
        {error && (
          <Alert variant="warning" className="fs-13px py-2">
            {error}
          </Alert>
        )}

        {loading ? (
          <p className="fs-13px text-muted mb-0">Loading…</p>
        ) : portfolios.length === 0 ? (
          <p className="fs-13px text-muted mb-0">Nothing saved yet.</p>
        ) : (
          <Table size="sm" responsive className="align-middle mb-0">
            <tbody>
              {portfolios.map((portfolio) => (
                <tr key={portfolio.id}>
                  <td>
                    <strong>{portfolio.name}</strong>
                    <div className="text-muted fs-13px">
                      {(portfolio.holdings || []).map((h) => h.symbol).join(', ') || 'no holdings'}
                    </div>
                  </td>
                  <td className="text-end">
                    <Button size="sm" variant="outline-primary" className="me-2" onClick={() => load(portfolio)}>
                      Load
                    </Button>
                    <Button
                      size="sm"
                      variant="outline-secondary"
                      className="me-2"
                      onClick={() => duplicate(portfolio.id)}
                    >
                      Copy
                    </Button>
                    <Button size="sm" variant="outline-danger" onClick={() => remove(portfolio.id)}>
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>
    </Card>
  )
}

export default SavedPortfolios
