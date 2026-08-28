import useSWR from "swr"
import axios from 'axios'



const fetcher = async (url) => {
    const res = await axios.get(url)
    
    const resData = res.data
    return resData
}

export const useSectorData = (exchange) => {

    const URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/sector-industry/${exchange}/`;
    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    
    const swrRes = useSWR(
        URL,
        fetcher,
        {
            refreshInterval: 900000, // 15 minutes
        }
    )

    return swrRes
}