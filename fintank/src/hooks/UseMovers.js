import useSWR from "swr"
import axios from 'axios'

const URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/movers/`;

const fetcher = async (url) => {
    const res = await axios.get(url)
    
    const resData = res.data
    return resData
}

export const useMoversData = () => {

    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    const swrRes = useSWR(
        URL,
        fetcher
    )

    return swrRes
}