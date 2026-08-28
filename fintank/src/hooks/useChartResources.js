import useSWRImmutable from 'swr/immutable'
import axios from 'axios'
import React,{useState} from 'react';
import { idbPromise } from "@utils/helpers";
import chartData from "@data/chartsettings.json"

const fetcher = async (url) => {
    const res = await axios.get(url)
    const resData = res
    return resData
}

const shouldFetch = (index) => {
    let items = idbPromise(index, 'get').then((indexedItems => {
        return indexedItems
    }))
    if(items.length == 0){
        return null;
    } else{
        return items.data
    }
}



export const useChartResource = (asset) => {


    const [myAsset, setMyAsset] = useState(asset);
    // let URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/gettopperformers/${index}`;

    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    const indexes = chartData.indexes.map(index =>index.value);
    let URL;
    if(indexes.includes(myAsset.value)){
      URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/index-prices/${myAsset.value}`
    } else {
      URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/other-asset-prices/${myAsset.value}`
    }

    const {data} = useSWRImmutable(
          shouldFetch ? URL : null,
          fetcher
    )


    return data
}