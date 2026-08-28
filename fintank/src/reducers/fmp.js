import axios from 'axios'

const fmpReducer = async(state = [], action) => {


    const fmpRes = await axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/newsarticles/fmp`);
    const responseNews = await fmpRes.data;
    state = await responseNews.data
    
    return state
}


export default fmpReducer