/**
 * Display helpers for /subscription. Amounts arrive from Django in the
 * currency's minor unit (cents), exactly as Stripe stores them.
 */
export function formatAmount(cents, currency) {
  if (cents === null || cents === undefined) return null
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: (currency || 'usd').toUpperCase(),
  }).format(cents / 100)
}

/** Yearly price per month, in cents: 7188 -> 599. */
export function perMonth(yearCents) {
  return Math.round(yearCents / 12)
}

export function formatPlanDate(iso) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  // UTC so a period ending at midnight UTC doesn't show as the day before.
  return date.toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  })
}

/** The one-line status under the plan name, or null for free users. */
export function statusNote(sub) {
  if (!sub || sub.tier !== 'pro') return null
  const date = formatPlanDate(sub.current_period_end)

  if (!sub.status) {
    return { variant: 'info', text: 'Pro was added to your account by Fintank.' }
  }
  if (sub.status === 'past_due') {
    return { variant: 'warning', text: 'Your last payment failed. Update your card to keep Pro.' }
  }
  if (sub.cancel_at_period_end) {
    return { variant: 'secondary', text: `Your subscription is cancelled. Pro ends on ${date}.` }
  }
  return { variant: 'light', text: date ? `Renews on ${date}.` : 'Active.' }
}
