import React from 'react'
import { Alert } from 'react-bootstrap'

/**
 * Five sibling panels render from independent responses. Without a boundary,
 * one panel throwing during render blanks the entire page.
 */
class PanelErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <Alert variant="danger" className="m-3">
          {`${this.props.symbol} could not be charted.`}
        </Alert>
      )
    }
    return this.props.children
  }
}

export default PanelErrorBoundary
