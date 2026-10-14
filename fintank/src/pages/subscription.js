import React, { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/router"
import {
  Alert,
  Badge,
  Breadcrumb,
  Button,
  ButtonGroup,
  Card,
  Col,
  Container,
  Row,
} from "react-bootstrap"
import axios from "axios"
import useProfileUser from "@componentsLegacy/Profile/useProfileUser"
import useSubscription from "@hooks/useSubscription"
import {
  formatAmount,
  perMonth,
  statusNote,
} from "@utils/subscriptionFormat"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Subscription",
    },
  }
}

const PRO_FEATURES = ["Unlimited portfolio backtests"]

const Spinner = () => (
  <div className="text-center py-5">
    <div className="spinner-border text-primary" role="status">
      <span className="visually-hidden">Loading...</span>
    </div>
  </div>
)

const Subscription = () => {
  const router = useRouter()
  const { user, loading: userLoading } = useProfileUser()
  const checkout = router.query.checkout
  const { subscription, loading, error, pollExpired } = useSubscription({
    poll: checkout === "success",
  })
  const [billingInterval, setBillingInterval] = useState("year")
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    if (!userLoading && !user) router.replace("/login")
  }, [userLoading, user, router])

  // Sends the browser to a Stripe-hosted page (checkout or portal).
  const goToStripe = async (action, body) => {
    setBusy(true)
    setActionError(null)
    try {
      const { data } = await axios.post(`/api/billing/${action}`, body)
      window.location.assign(data.url)
    } catch (err) {
      setActionError(err.response?.data?.detail || "Something went wrong. Please try again.")
      setBusy(false)
    }
  }

  const isPro = subscription?.tier === "pro"
  const plans = subscription?.plans
  const note = statusNote(subscription)
  const confirming = checkout === "success" && !isPro && !pollExpired

  return (
    <section className="account-page py-5">
      <Container>
        <Breadcrumb listProps={{ className: "ps-0 justify-content-start" }}>
          <Breadcrumb.Item linkAs={Link} href="/">
            Home
          </Breadcrumb.Item>
          <Breadcrumb.Item linkAs={Link} href="/user-account">
            Account
          </Breadcrumb.Item>
          <Breadcrumb.Item active>Subscription</Breadcrumb.Item>
        </Breadcrumb>

        <h1 className="hero-heading mb-0">Subscription</h1>
        <p className="text-muted mb-5">Your plan, billing and renewal.</p>

        <Row>
          <Col lg="7">
            {checkout === "cancelled" && (
              <Alert variant="secondary">Checkout cancelled. You have not been charged.</Alert>
            )}
            {checkout === "success" && pollExpired && !isPro && (
              <Alert variant="info">
                Your payment went through and your upgrade is still processing. Refresh this
                page in a minute.
              </Alert>
            )}
            {(error || actionError) && <Alert variant="danger">{actionError || error}</Alert>}

            {userLoading || loading || confirming ? (
              <>
                <Spinner />
                {confirming && <p className="text-center text-muted">Confirming your payment…</p>}
              </>
            ) : subscription && isPro ? (
              <Card className="border-0 shadow">
                <Card.Body className="p-4">
                  <div className="d-flex align-items-center mb-3">
                    <h3 className="mb-0 me-3">Pro</h3>
                    {subscription.interval && (
                      <Badge bg="primary">
                        {subscription.interval === "year" ? "Yearly" : "Monthly"}
                      </Badge>
                    )}
                  </div>
                  {note && <Alert variant={note.variant}>{note.text}</Alert>}
                  <ul className="mb-4">
                    {PRO_FEATURES.map((feature) => <li key={feature}>{feature}</li>)}
                  </ul>
                  {subscription.has_billing_account && (
                    <>
                      <Button variant="primary" disabled={busy} onClick={() => goToStripe("portal")}>
                        {busy ? "Opening…" : "Manage subscription"}
                      </Button>
                      <p className="text-sm text-muted mt-3 mb-0">
                        Switch between monthly and yearly, cancel, update your card or download
                        invoices on Stripe&apos;s secure billing page.
                      </p>
                    </>
                  )}
                </Card.Body>
              </Card>
            ) : subscription ? (
              <Card className="border-0 shadow">
                <Card.Body className="p-4">
                  <p className="text-muted mb-1">You are on the Free plan.</p>
                  <h3 className="mb-3">Upgrade to Pro</h3>
                  <ul className="mb-4">
                    {PRO_FEATURES.map((feature) => <li key={feature}>{feature}</li>)}
                  </ul>
                  {plans ? (
                    <>
                      <ButtonGroup className="mb-3" aria-label="Billing interval">
                        <Button
                          variant={billingInterval === "month" ? "primary" : "outline-primary"}
                          onClick={() => setBillingInterval("month")}
                        >
                          Monthly
                        </Button>
                        <Button
                          variant={billingInterval === "year" ? "primary" : "outline-primary"}
                          onClick={() => setBillingInterval("year")}
                        >
                          Yearly
                        </Button>
                      </ButtonGroup>
                      <p className="h4 mb-1">
                        {billingInterval === "year"
                          ? `${formatAmount(perMonth(plans.year.amount), plans.year.currency)}/mo`
                          : `${formatAmount(plans.month.amount, plans.month.currency)}/mo`}
                      </p>
                      <p className="text-sm text-muted mb-4">
                        {billingInterval === "year"
                          ? `Billed ${formatAmount(plans.year.amount, plans.year.currency)} yearly.`
                          : "Billed monthly."}{" "}
                        Cancel any time.
                      </p>
                      <Button
                        variant="primary"
                        disabled={busy}
                        onClick={() => goToStripe("checkout", { interval: billingInterval })}
                      >
                        {busy ? "Opening checkout…" : "Upgrade to Pro"}
                      </Button>
                    </>
                  ) : (
                    <p className="text-muted mb-0">
                      Upgrades are unavailable right now. Please try again later.
                    </p>
                  )}
                </Card.Body>
              </Card>
            ) : null}
          </Col>
        </Row>
      </Container>
    </section>
  )
}

export default Subscription
