import axios from 'axios';
import cookie from 'cookie';

// eslint-disable-next-line import/no-anonymous-default-export
export default async (req, res) => {
    if (req.method === 'POST'){
        const {username, password} = req.body;
        try{
            const response = await axios.post(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/auth/token/`, {
                username, 
                password
            },  {
                headers:{
                    'Content-Type':'application/json'
                }
            });

            if(response.data.access){
                //sets secure to true in production
                res.setHeader('Set-Cookie', [
                    cookie.serialize('access', response.data.access, {
                        httpOnly:true, secure:process.env.NODE_ENV !== 'development',
                        maxAge: 60*60*24*5,
                        sameSite:'Lax',
                        path:'/',
                    })
                ]);

                return res.status(200).json({success:true});

            } else {
                res.status(response.status).json({
                    error:'Error Authenticating User.'
                })
            }

        } catch(error){
            // No response means Django never answered (down, wrong URL, timeout).
            // Reading error.response.status here used to throw and crash the route.
            if (!error.response) {
                return res.status(502).json({
                    error: 'Could not reach the login service. Please try again.'
                });
            }
            // simplejwt puts its message in `detail` ("No active account found
            // with the given credentials"), not `error`.
            const { status, data } = error.response;
            return res.status(status).json({
                error: data?.detail || data?.error || 'Error Authenticating User.'
            });
        }
    }

    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method not allowed.' });
};