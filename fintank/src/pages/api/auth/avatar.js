import axios from 'axios'
import cookie from 'cookie'

/**
 * Avatar presets (GET) and the user's avatar choice (PATCH).
 *
 * A separate route from userprofile.js, which is GET-only and returns the whole
 * profile under a `user_profile` key. The JWT lives in an httpOnly cookie, so
 * the browser cannot call Django directly.
 *
 * Only preset selection is proxied here — an image upload is multipart and would
 * need body parsing turned off and the stream piped through, which is a
 * different shape of handler. Django's endpoint still accepts uploads; nothing
 * in the UI sends them yet.
 */
const API = process.env.NEXT_PUBLIC_FINTANK_API_URL

export default async function handler(req, res) {
  const cookies = cookie.parse(req.headers.cookie || '')
  const access = cookies.access || false

  if (!access) {
    return res.status(401).json({ detail: 'Log in to change your avatar.' })
  }

  const auth = { Authorization: `Bearer ${access}` }

  if (req.method === 'GET') {
    try {
      const response = await axios.get(`${API}/avatar-presets/`, { headers: auth })
      return res.status(200).json(response.data)
    } catch (error) {
      const status = error?.response?.status || 502
      return res.status(status).json(error?.response?.data || { detail: 'Could not load avatars.' })
    }
  }

  if (req.method === 'PATCH') {
    const slug = req.body?.preset_avatar_slug
    // The Django serializer accepts an id or a slug; restricting the proxy to
    // slugs keeps one code path and avoids leaking row ids into client code.
    if (typeof slug !== 'string' || !slug) {
      return res.status(400).json({ detail: 'preset_avatar_slug is required.' })
    }

    try {
      // Django's handler is MultiPartParser/FormParser, not JSON, because it
      // also accepts file uploads — so the preset choice goes as form data.
      const form = new URLSearchParams({ preset_avatar_slug: slug })
      const response = await axios.patch(`${API}/users/me/profile/avatar/`, form, {
        headers: { ...auth, 'Content-Type': 'application/x-www-form-urlencoded' },
        validateStatus: () => true,
      })
      return res.status(response.status).json(response.data)
    } catch (error) {
      const status = error?.response?.status || 502
      return res.status(status).json(error?.response?.data || { detail: 'Could not save your avatar.' })
    }
  }

  res.setHeader('Allow', 'GET, PATCH')
  return res.status(405).json({ detail: `${req.method} is not supported here.` })
}
