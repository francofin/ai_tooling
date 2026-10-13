import axios from 'axios';
import cookie from 'cookie';

/**
 * Proxies a password change to Django's PATCH /users/me/change-password/ with
 * the httpOnly `access` cookie, so the token never reaches browser JavaScript.
 *
 * Nothing here logs the request or Django's response: both carry passwords.
 * Field errors ({old_password: [...], new_password: [...], new_password2: [...]})
 * pass straight through so the form can show each under its input.
 */
// eslint-disable-next-line import/no-anonymous-default-export
export default async (req, res) => {
    if (req.method !== 'POST') {
        res.setHeader('Allow', 'POST');
        return res.status(405).json({ detail: 'Method not allowed.' });
    }

    const { access } = cookie.parse(req.headers.cookie || '');
    if (!access) {
        return res.status(401).json({ detail: 'Your session has expired. Please log in again.' });
    }

    const { old_password, new_password, new_password2 } = req.body || {};

    try {
        const response = await axios.patch(
            `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/users/me/change-password/`,
            { old_password, new_password, new_password2 },
            {
                headers: {
                    Authorization: `Bearer ${access}`,
                    'Content-Type': 'application/json',
                },
            }
        );
        return res.status(200).json(response.data);
    } catch (error) {
        const status = error.response?.status;
        if (status === 401) {
            return res.status(401).json({ detail: 'Your session has expired. Please log in again.' });
        }
        if (status === 400 && error.response.data) {
            return res.status(400).json(error.response.data);
        }
        return res.status(502).json({ detail: 'Could not update your password right now. Please try again.' });
    }
};
