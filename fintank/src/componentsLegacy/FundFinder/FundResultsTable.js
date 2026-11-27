import React from 'react'
import Link from 'next/link'
import { Badge, Table } from 'react-bootstrap'
import { formatMer, leverageLabel } from '@utils/fundFinder/query.mjs'

export const EMPTY_TEXT = 'No ETF in this market holds these stocks without the excluded ones.'

const pct = (value, digits) => (value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(digits)}%`)

export const formatAum = (aum, currency) => {
  if (aum == null || Number.isNaN(Number(aum))) return '—'
  const prefix = currency === 'CAD' ? 'C$' : '$'
  const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(aum))
  return `${prefix}${compact}`
}

const FundResultsTable = ({ funds, picks, fetched }) => {
  if (!funds.length) return <p className="text-muted">{EMPTY_TEXT}</p>
  return (
    <Table responsive hover className="align-middle">
      <thead>
        <tr>
          <th>#</th>
          <th>Fund</th>
          <th className="text-end">Combined</th>
          {picks.map((pick) => (
            <th key={pick} className="text-end">
              {pick}
            </th>
          ))}
          <th className="text-end">MER</th>
          <th className="text-end">AUM</th>
          <th>Listed</th>
        </tr>
      </thead>
      <tbody>
        {funds.map((fund, index) => (
          <tr key={fund.symbol}>
            <td>{index + 1}</td>
            <td>
              <Link href={`/etf-data/${encodeURIComponent(fund.symbol)}`}>
                <strong>{fund.symbol}</strong>
              </Link>
              {fund.leveraged && leverageLabel(fund.coverage_pct) && (
                <Badge bg="warning" text="dark" className="ms-2" title="Leveraged fund">
                  {leverageLabel(fund.coverage_pct)}
                </Badge>
              )}
              <div className="small text-muted">{fund.name}</div>
              {fund.also?.length > 0 && (
                <div className="small text-muted">also available as {fund.also.join(', ')}</div>
              )}
              {fund.fetched && fund.fetched !== fetched && (
                <div className="small text-muted">fetched {fund.fetched}</div>
              )}
            </td>
            <td className="text-end">
              <strong>{pct(fund.combined, 1)}</strong>
            </td>
            {picks.map((pick) => {
              const cell = fund.weights?.[pick]
              return (
                <td key={pick} className="text-end">
                  {cell ? pct(cell.weight, 1) : '—'}
                  {cell?.via?.length > 0 && <div className="small text-muted">via {cell.via.join(', ')}</div>}
                </td>
              )
            })}
            <td className="text-end">{formatMer(fund.mer)}</td>
            <td className="text-end">{formatAum(fund.aum, fund.currency)}</td>
            <td>{[fund.exchange, fund.currency].filter(Boolean).join(' · ') || '—'}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}

export default FundResultsTable
