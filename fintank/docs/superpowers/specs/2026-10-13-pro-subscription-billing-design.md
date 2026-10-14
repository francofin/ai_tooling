# Pro Subscription Billing (Stripe)

**Status:** Design approved, not yet implemented
**Implements:** §3 "Monetisation Roadmap (Stripe)" of `2026-04-20-fintank-platform-design.md`

---

## Context

`UserProfile.subscription_tier` (`'free'` / `'pro'`) exists and drives one thing: the
backtest quota (`backtester/quota.py` — free gets `FREE_TIER_BACKTEST_LIMIT`, `pro` is
unlimited). Today only an admin can change it. There is no Stripe code, no `stripe`
package, and no page where a user can see or change their plan.

This spec adds a paid Pro plan bought through Stripe Checkout, managed (switch interval,
cancel, card, invoices) through the Stripe Customer Portal, and kept in sync with Django by
a Stripe webhook. Fintank's own sign-up and login are unchanged: every account starts on
Free, and Stripe only handles payment for an already-logged-in user.

## Scope

**Plans**

| Plan | Price | Stripe price |
|------|-------|--------------|
| Free | — | none |
| Pro, monthly | $9.99 USD / month | `STRIPE_PRICE_PRO_MONTHLY` |
| Pro, yearly | $71.88 USD / year (shown as "$5.99/mo, billed yearly") | `STRIPE_PRICE_PRO_YEARLY` |

**What Pro unlocks:** unlimited backtests, which is all `subscription_tier` gates today.
No new feature gating is added by this work.

**What a user can do**

- Free user: upgrade to Pro, choosing monthly or yearly (Stripe Checkout).
- Pro user, in the Stripe Customer Portal: switch monthly ↔ yearly, cancel (at the end of
  the paid period), undo a pending cancellation, update the card, see invoices.

**Out of scope:** trials, coupons/promotion codes, taxes, more than one paid tier, gating
new features, an in-app cancel flow.

## Backend

### New app: `billing`

Registered in `INSTALLED_APPS`, URLs included under `api/` like the other apps.

### Model changes (`users.UserProfile`)

New nullable fields — the migration needs no backfill:

| Field | Type | Meaning |
|-------|------|---------|
| `stripe_customer_id` | `CharField(255, null, unique)` | Stripe Customer for this user |
| `stripe_subscription_id` | `CharField(255, null)` | The subscription currently tracked |
| `subscription_status` | `CharField(32, null)` | Stripe status verbatim (`active`, `past_due`, `canceled`, …) |
| `subscription_interval` | `CharField(8, null)` | `month` or `year` |
| `current_period_end` | `DateTimeField(null)` | Renewal date, or the date Pro ends if cancelling |
| `cancel_at_period_end` | `BooleanField(default=False)` | Cancellation pending |

All are added to `UserProfileSerializer`'s read-only set, like `subscription_tier`, so no
user can PATCH them. The existing `stripe_account_id` is a Stripe *Connect* account ID, a
different thing, and is left alone. The admin shows the new fields read-only.

### Tier rule

One function, `tier_for_status(status)`:

- `active`, `trialing`, `past_due` → `pro` (`past_due` keeps Pro during Stripe's
  automatic payment retries)
- anything else (`canceled`, `unpaid`, `incomplete`, `incomplete_expired`, `paused`,
  `None`) → `free`

`backtest_quota_override` keeps precedence over the tier, as today. Users who have never
had a Stripe subscription are never touched by billing code, so an admin can still set a
complimentary `pro` by hand.

### Endpoints

All but the webhook require an authenticated user (JWT, as elsewhere).

**`GET /api/billing/subscription/`**

```json
{
  "tier": "pro",
  "status": "active",
  "interval": "year",
  "current_period_end": "2027-10-13T00:00:00Z",
  "cancel_at_period_end": false,
  "has_billing_account": true,
  "plans": {
    "month": {"amount": 999, "currency": "usd"},
    "year":  {"amount": 7188, "currency": "usd"}
  }
}
```

`plans` is read from the two Stripe Price objects and cached in Redis for 1 hour, so the
page always shows what Stripe will actually charge. If Stripe is unreachable and nothing
is cached, `plans` is `null` and the page hides the upgrade buttons rather than show
guessed prices.

**`POST /api/billing/checkout/`** — body `{"interval": "month" | "year"}`

- 400 on any other interval.
- 409 if `tier_for_status(subscription_status)` is already `pro`, i.e. the user has a live
  Stripe subscription (prevents a second one; the page sends them to the portal instead).
- Creates the Stripe Customer on first use (email from the Fintank account,
  `metadata.user_id`) and saves `stripe_customer_id` immediately, so it is reused.
- Creates a Checkout Session: `mode=subscription`, the chosen price, `customer`,
  `client_reference_id=user.id`, `success_url={FRONTEND_URL}/subscription?checkout=success`,
  `cancel_url={FRONTEND_URL}/subscription?checkout=cancelled`.
- Returns `{"url": session.url}`.

**`POST /api/billing/portal/`**

- 409 if the user has no `stripe_customer_id`.
- Creates a Billing Portal session with `return_url={FRONTEND_URL}/subscription`.
- Returns `{"url": session.url}`.

**`POST /api/billing/webhook/`**

- Plain Django view, `csrf_exempt`, no authentication — it must read the raw body for
  signature verification, which DRF parsing would consume.
- Verifies the `Stripe-Signature` header against `STRIPE_WEBHOOK_SECRET`; invalid or
  missing signature → 400 and nothing is written.
- Handles `checkout.session.completed`, `customer.subscription.created`,
  `customer.subscription.updated`, `customer.subscription.deleted`. Other events → 200,
  ignored.
- **Sync, not replay.** For every handled event it re-retrieves the subscription from
  Stripe and writes its current state, rather than trusting the event payload. Duplicate
  and out-of-order deliveries therefore converge on the right answer, and no event log
  table is needed.
- Finds the user by `stripe_customer_id`; for `checkout.session.completed` it falls back to
  `client_reference_id`. Unknown customer → 200 and a warning log (Stripe must not retry
  forever).
- If the profile already tracks a *different* subscription that is still Pro-granting and
  the incoming one is also Pro-granting, it keeps the existing one and logs an error for
  manual refund (only reachable if two checkout tabs both complete).
- Writes status, interval, `current_period_end`, `cancel_at_period_end`, and
  `subscription_tier = tier_for_status(status)` in one save.
- Returns 500 only on unexpected errors, so Stripe retries those.

**Stripe API version note:** recent Stripe API versions moved `current_period_end` from the
subscription onto its items. The implementation reads it from
`subscription.items.data[0].current_period_end`, falling back to the top-level field, and
pins the `stripe` package version. Confirm against current Stripe docs at implementation.

### Settings (`backend/.env`)

| Variable | Purpose |
|----------|---------|
| `STRIPE_SECRET_KEY` | Exists already |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret |
| `STRIPE_PRICE_PRO_MONTHLY` | Price ID for $9.99/month |
| `STRIPE_PRICE_PRO_YEARLY` | Price ID for $71.88/year |
| `FRONTEND_URL` | Base for Stripe return URLs, e.g. `http://localhost:8020` |

If any billing setting is missing, the billing endpoints return 503 with a clear message;
nothing else on the site is affected.

### Dependency

`stripe` added to `backend/pyproject.toml`.

## Frontend

### Page: `/subscription` (`src/pages/subscription.js`)

- Uses the `account-page` background and breadcrumb (Home › Account › Subscription), like
  `/security`.
- Requires login; logged-out users get the same treatment as the other account pages.
- **Free user:** a Pro card listing "Unlimited portfolio backtests", a Monthly / Yearly
  toggle showing $9.99/month or $5.99/mo billed $71.88 yearly (from `plans`), and an
  "Upgrade to Pro" button → `POST checkout` → `window.location = url`.
- **Pro user:** plan and interval, "Renews on {date}" or "Pro ends on {date}" when
  `cancel_at_period_end`, a warning when `past_due` ("Your last payment failed — update
  your card"), and a "Manage subscription" button → `POST portal` → redirect.
- **`?checkout=success`:** shows "Confirming your payment…" and polls the subscription
  endpoint every 2 s for up to 20 s until `tier === "pro"`; if the webhook hasn't landed by
  then, it shows "Your payment went through and your upgrade is still processing — refresh
  in a minute." It never shows an error for a slow webhook.
- **`?checkout=cancelled`:** a neutral "Checkout cancelled — you have not been charged."
- Buttons disable while a request is in flight; API errors show in an `Alert`.

### Supporting files

- `src/pages/api/billing/[action].js` — single Next API route (actions: `subscription` GET,
  `checkout` POST, `portal` POST) that forwards to Django with the httpOnly `access` cookie
  as a Bearer token, matching `src/pages/api/auth/changePassword.js` (401 on missing cookie,
  status passthrough, no logging of bodies). The webhook does not go through Next; Stripe
  calls Django directly.
- `src/data/user-account.json` — a "Subscription" card linking to `/subscription`.

## Stripe setup (done by Franc in the Stripe dashboard)

1. Product "Fintank Pro" with two recurring USD prices: $9.99 monthly, $71.88 yearly.
   Their IDs go into `backend/.env`.
2. Customer Portal settings: allow cancellation at period end, allow switching between the
   two Pro prices, allow payment-method updates, show invoice history.
3. Local development: `stripe listen --forward-to localhost:8000/api/billing/webhook/`,
   which prints the webhook signing secret. Use test-mode keys throughout.

## Testing

Django tests in `billing/tests.py`, with the Stripe client mocked:

- `tier_for_status` for every Stripe status.
- Checkout: valid intervals return a URL; bad interval → 400; existing Pro → 409; the
  customer is created once and reused.
- Portal: no customer → 409; otherwise a URL.
- Webhook: bad/missing signature → 400 with no writes; each handled event updates the
  profile; duplicate and out-of-order events converge; deletion drops the tier to free;
  unknown customer → 200; second concurrent subscription is not adopted.
- Quota integration: a webhook-driven upgrade lifts the backtest limit and a cancellation
  restores it.
- Serializer: a user cannot PATCH any of the new fields.
- Missing settings → 503.

Frontend is checked by code review and the existing JS logic harness; servers are started
by Franc.
