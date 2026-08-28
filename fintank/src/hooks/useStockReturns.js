import React, { useEffect, useState } from "react"


  export const useStockReturns = (data, frequency) => {
    
    
    const [chartLabels, setChartLabels] = useState([])
    const [chartReturns, setChartReturns] = useState([])
    let labels;
    let returns;
    useEffect(() => {
        switch(frequency){
            case '30d':
                labels = data.day_30_date_list;
                returns = data.day_30_return_list;
                setChartLabels(labels)
                setChartReturns(returns)
                break;
            case '120d':
                labels = data.day_120_date_list;
                returns = data.day_120_return_list;
                setChartLabels(labels)
                setChartReturns(returns)
                break;
            case 'quarter':
                labels = data.quarter_date_list;
                returns = data.quarter_return_list;
                setChartLabels(labels)
                setChartReturns(returns)
                break;
            case 'year':
                labels = data.year_1_date_list;
                returns = data.year_1_return_list;
                setChartLabels(labels)
                setChartReturns(returns)
                break;
            default:
                break
        }
    }, [frequency])

    return {
        chartLabels, 
        chartReturns
    }
  }