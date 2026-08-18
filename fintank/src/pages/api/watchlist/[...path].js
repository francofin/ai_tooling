import axios from 'axios'
import cookie from 'cookie'

/**
 * Server-side proxy for the watchlist routes, mirroring
 * /api/backtester/[...path].js.
 *
 * The JWT lives in an httpOnly cookie (set by /api/auth/login) so the browser
 * cannot attach it itself. Going through here also means the access token never
 * has to be passed down through getServerSideProps into page props, which is
 * what the legacy DjangoAuthContext flow did.
 *
 * A logged-out visitor gets a clean 401 that the button renders as a prompt to
 * sign in, rather than an error.
 */
const ALLOWED_METHODS = ['GET', 'POST']

// The backtester proxy is naturally fenced in by its `backtester/` URL prefix.
// These three routes sit at the API root, so without an explicit allowlist this
// handler would forward *any* path to Django carrying the caller's Bearer token
// -- turning it into a general-purpose authenticated proxy. Match exactly.
const ROUTES = [
  { method: 'POST', pattern: /^addtowatchlist\/[^/]+$/ },
  { method: 'POST', pattern: /^deletefromwatchlist\/[^/]+$/ },
  { method: 'GET', pattern: /^stockonwatchlist\/[^/]+\/verify$/ },
]

export default async function handler(req, res) {
  if (!ALLOWED_METHODS.includes(req.method)) {
    res.setHeader('Allow', ALLOWED_METHODS.join(', '))
    return res.status(405).json({ detail: `${req.method} is not supported here.` })
  }

  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path]
  const route = segments.join('/')
  if (!ROUTES.some((r) => r.method === req.method && r.pattern.test(route))) {
    return res.status(404).json({ detail: 'Unknown watchlist route.' })
  }

  const cookies = cookie.parse(req.headers.cookie || '')
  const access = cookies.access || false
  if (!access) {
    return res.status(401).json({ detail: 'Log in to use your watchlist.' })
  }

  const url = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/${route}/`

  try {
    const response = await axios({
      method: req.method,
      url,
      data: req.method === 'POST' ? req.body : undefined,
      headers: {
        Authorization: `Bearer ${access}`,
        'Content-Type': 'application/json',
      },
      // A 404 for an unknown symbol carries a body the UI reads, so let it past
      // rather than throwing.
      validateStatus: () => true,
    })
    return res.status(response.status).json(response.data)
  } catch (error) {
    const status = error?.response?.status || 502
    return res
      .status(status)
      .json(error?.response?.data || { detail: 'The watchlist service is unreachable.' })
  }
}
