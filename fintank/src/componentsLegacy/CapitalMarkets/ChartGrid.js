import React from "react";
import { Row } from "react-bootstrap";

/**
 * Lays cards out two per row. The old components hard-coded the pairing and
 * gated each row on `chartACreated && chartBCreated`, so one empty series hid
 * its healthy neighbour. Here empty series are filtered out upstream and
 * whatever remains is chunked, so an odd count (nonfarm) just ends in a
 * half-width row instead of needing a special case.
 */
const ChartGrid = ({ children }) => {
  const cards = React.Children.toArray(children);
  const rows = [];

  for (let i = 0; i < cards.length; i += 2) {
    rows.push(cards.slice(i, i + 2));
  }

  return rows.map((row, index) => (
    <Row className="pt-3" key={index}>
      {row}
    </Row>
  ));
};

export default ChartGrid;
