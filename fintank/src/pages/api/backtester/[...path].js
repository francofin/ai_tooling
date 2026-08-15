import axios from 'axios'
import cookie from 'cookie'

/**
 * Server-side proxy for every /api/backtester/* call.
 *
 * The JWT lives in an httpOnly cookie (set by /api/auth/login), so the browser
 * cannot attach it itself. This route reads the cookie and forwards the request
 * to Django with the Bearer header, which is the same pattern
 * /api/auth/userprofile.js uses.
 */
const ALLOWED_METHODS = ['GET', 'POST', 'PATCH', 'DELETE']

export default async function handler(req, res) {
  if (!ALLOWED_METHODS.includes(req.method)) {
    res.setHeader('Allow', ALLOWED_METHODS.join(', '))
    return res.status(405).json({ detail: `${req.method} is not supported here.` })
  }

  const cookies = cookie.parse(req.headers.cookie || '')
  const access = cookies.access || false
  if (!access) {
    return res.status(401).json({ detail: 'Log in to use the backtester.' })
  }

  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path]
  const search = new URLSearchParams()
  Object.entries(req.query).forEach(([key, value]) => {
    if (key !== 'path') search.append(key, value)
  })
  const queryString = search.toString()
  const url =
    `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/backtester/${segments.join('/')}/` +
    (queryString ? `?${queryString}` : '')

  try {
    const response = await axios({
      method: req.method,
      url,
      data: ['POST', 'PATCH'].includes(req.method) ? req.body : undefined,
      headers: {
        Authorization: `Bearer ${access}`,
        'Content-Type': 'application/json',
      },
      // 402, 410 and 422 all carry a body the UI needs to read, so let them
      // through rather than throwing.
      validateStatus: () => true,
    })
    return res.status(response.status).json(response.data)
  } catch (error) {
    const status = error?.response?.status || 502
    return res.status(status).json(error?.response?.data || { detail: 'The backtester is unreachable.' })
  }
}
