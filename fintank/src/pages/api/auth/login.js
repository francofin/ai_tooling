import axios from 'axios';
import cookie from 'cookie';

// eslint-disable-next-line import/no-anonymous-default-export
export default async (req, res) => {
    console.log(req)
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
            console.log(error.response);
            res.status(error.response.status).json({
                error: error.response && error.response.data.error
            })
        }
    }
};