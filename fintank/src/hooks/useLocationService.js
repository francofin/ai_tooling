import useSWR from "swr"
import axios from 'axios'


const fetcher = async (url) => {
    const res = await axios.get(url)
    const resData = res.data
    return resData
}



export const useLocationService = (address) => {

    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    const {data} = useSWR(
        `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/getgeocode/${address}`,
        fetcher,
    )

    return data
    
}