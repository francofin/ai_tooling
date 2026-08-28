/* eslint-disable import/no-anonymous-default-export */
import axios from 'axios';
import cookie from 'cookie';

export default async (req, res) => {
    // console.log(req)
    if (req.method === 'GET'){
        const cookies = cookie.parse(req.headers.cookie || '')

        const access = cookies.access || false;
        let userLogged;

        if (!access) {
            return res.status(401).json({
              message: "Login first to get User Details",
            });
          }
        
          
        try{
            const userProfile = await axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/users/me/profile/`, {
                headers: {
                  Authorization: `Bearer ${access}`,
                },
              })
              console.log(userProfile);
              if(userProfile.data){
                return res.status(200).json({
                    user_profile: userProfile.data
                })
              }
        } catch(error){
            // console.log(error);
            res.status(error?.response.status).json({
                error: 'Something Went Wrong while getting your details, Please try to log in again'
            })
        }
    }
};