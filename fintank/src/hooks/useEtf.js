import useSWR from "swr"
import axios from 'axios'

const URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/etf-performance/`;

const fetcher = async (url) => {
    const res = await axios.get(url)
    return res.data?.data ?? res.data
}

export const useEtfPerformance = () => {

    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    const swrRes = useSWR(
        URL,
        fetcher,
        {
            refreshInterval: 600000
        }
    )

    return swrRes
}