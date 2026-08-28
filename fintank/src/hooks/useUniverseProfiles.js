import useSWR from "swr"
import axios from 'axios'


const fetcher = async (url) => {
    const res = await axios.get(url)

    const resData = res.data
    return resData
}

export const useUniverseProfiles = (slug) => {

    const swrRes = useSWR(
        slug ? `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/universe-profiles/${slug}/` : null,
        fetcher,
        { revalidateOnFocus: false },
    )

    return swrRes
}
