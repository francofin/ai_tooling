import React from "react"
import Link from "next/link"
import Stars from "@componentsLegacy/Stars"
import {
  Container,
  Row,
  Button,
  Table,
} from "react-bootstrap"





const MetricsTable = (props) => (
    <Container>
      <Row>
        <Table striped responsive hover className="text-gray-700 text-sm">
          <tbody>
            <tr>
              <th className="py-4 align-middle">Date</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {column.date} 
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Period</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {column.period} 
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Revenue Per Share</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.revenuePerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Net Income Per Share</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.netIncomePerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Operating Cash Flow Per Share</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.operatingCashFlowPerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Free Cash Flow Per SHare</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.freeCashFlowPerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Book Value Per Share</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.bookValuePerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Interest Debt Per Share</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.interestDebtPerShare).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Market Cap</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    ${(Number(column.marketCap)/10**9).toFixed(2).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}B
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Enterprise Value</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    ${(Number(column.enterpriseValue)/10**9).toFixed(2).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}B
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Price to Earnings Ratio</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.peRatio).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Price to Sales Ratio</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.priceToSalesRatio).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Price to Cash Flow Ratio</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.pfcfRatio).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Price to Book Ratio</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.ptbRatio).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Enterprise Value to Sales</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.evToSales).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Earnings Yield</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.earningsYield).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Free Cash Flow Yield</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.freeCashFlowYield).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Debt to Equity</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.debtToEquity}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.debtToEquity).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Interest Coverage</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.interestCoverage).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Dividend Yield</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.dividendYield).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Pay out  Ratio</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.payoutRatio).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Capex to Operating Cashh Flow</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.capexToOperatingCashFlow).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Return on Equity</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {(Number(column.roe)*100).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Return on Invested Capital</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {(Number(column.roic)*100).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Days of Sales Outstanding</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.daysSalesOutstanding).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Days of Payables Outstanding</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.daysPayablesOutstanding).toFixed(2)}
                  </td>
                ))}
            </tr>
            <tr>
              <th className="py-4 align-middle">Days of Inventory On Hand</th>
              {props.metrics &&
                props.metrics.map((column) => (
                  <td
                    key={column.date}
                    className="py-4 text-center align-middle"
                  >
                    {Number(column.daysOfInventoryOnHand).toFixed(2)}
                  </td>
                ))}
            </tr>
          </tbody>
        </Table>
      </Row>
    </Container>
  )
  
  export default MetricsTable