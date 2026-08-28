import React, {useReducer,useState, createContext, useEffect, useMemo} from 'react';
import { useRouter } from 'next/router';
import axios from 'axios'
import swal from 'sweetalert';


const screenerReducer = (state, action) => {
    switch(action.type){
        case "RUN_FINTANK_SCREEN":
            return {...state, screenerResults: action.payload}
        default:
            return state
    }
}


const initialState = {
    screenerResults: [],
};


const DjangoScreenerContext = createContext();

const DjangoScreenerProvider = ({children}) => {
    const [loading, setLoading] = useState(false);
    const [screenerResults, setScreenResults] = useState(initialState)
    const [dataReturned, setDataReturned] = useState([])
    const router = useRouter();


    const getScreenResults = async(screenData) => {

        try{
            setLoading(true);
            const res = await axios.post(`${process.env.FINTANK_API_URL}/screen/`, screenData);
            if(res.data){
                setLoading(false);
                swal({
                    title: `Screen Run Successfully`,
                    icon: "success",
                });

                setDataReturned(res.data.screen_results);
                return res.data.screen_results 
            }
        } catch(err){
            swal({
                title: `No Results Found In Your Screen, Please Reset Your Parameters`,
                icon: "error",
            });
        }
    }


    const value = {screenerResults, loading, getScreenResults};

    return(
        <DjangoScreenerContext.Provider value ={value}>
            {children}
        </DjangoScreenerContext.Provider>
    )
}


export {DjangoScreenerContext, DjangoScreenerProvider}