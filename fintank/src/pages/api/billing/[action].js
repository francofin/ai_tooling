import axios from 'axios'
import cookie from 'cookie'

/**
 * Proxies /api/billing/{subscription,checkout,portal} to Django with the
 * httpOnly `access` cookie as a Bearer token, like /api/backtester/[...path].
 * The Stripe webhook does not come through here; Stripe calls Django directly.
 * Nothing is logged: responses carry Stripe URLs tied to the user's session.
 */
const ROUTES = {
  subscription: 'GET',
  checkout: 'POST',
  portal: 'POST',
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export default async function handler(req, res) {
  const { action } = req.query
  if (!Object.prototype.hasOwnProperty.call(ROUTES, action)) {
    return res.status(404).json({ detail: 'Not found.' })
  }
  const method = ROUTES[action]
  if (req.method !== method) {
    res.setHeader('Allow', method)
    return res.status(405).json({ detail: `${req.method} is not supported here.` })
  }

  const { access } = cookie.parse(req.headers.cookie || '')
  if (!access) {
    return res.status(401).json({ detail: 'Your session has expired. Please log in again.' })
  }

  try {
    const response = await axios({
      method,
      url: `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/billing/${action}/`,
      data: method === 'POST' ? req.body || {} : undefined,
      headers: { Authorization: `Bearer ${access}`, 'Content-Type': 'application/json' },
      // 400/409/502/503 carry a `detail` the page shows, so pass them through.
      validateStatus: () => true,
    })
    // Django is expected to answer JSON. If something in front of it (a proxy,
    // an unhandled 500) returns HTML or another non-object body, don't forward
    // that through as if it were a billing `detail`.
    if (!isPlainObject(response.data)) {
      return res.status(response.status).json({
        detail: 'Billing is unreachable right now. Please try again.',
      })
    }
    return res.status(response.status).json(response.data)
  } catch {
    return res.status(502).json({ detail: 'Billing is unreachable right now. Please try again.' })
  }
}
