import useSWR from "swr"
import axios from 'axios'
import { withIsLoading } from "./swrLoading"


const fetcher = async (url) => {
    const res = await axios.get(url)

    const resData = res.data
    return resData
}

export const useUniverseProfiles = (slug) => {

    const key = slug ? `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/universe-profiles/${slug}/` : null
    const swrRes = useSWR(key, fetcher, { revalidateOnFocus: false })

    return withIsLoading(key, swrRes)
}
