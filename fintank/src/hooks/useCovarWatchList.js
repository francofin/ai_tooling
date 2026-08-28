import React, {useState, useEffect} from 'react';


export const useWatchListCovar = (percContr,stockLabels) => {
    const [myChartData, setMyChartData] = useState([]);
    const [chartCreated, setChartCreated] = useState(false);
    const [createChart, setCreateChart] = useState(null);



    useEffect(() => {
        // let chartData = []
        // for (let i=0; i<percContr?.length; i++){
        //     chartData.push({x:Number(percReturn[i]), y:Number(percContr[i]), label:stockLabels[i]})
        // }
        // console.log(chartData)
        const drawChart = () => {
            let chart= {
                labels:stockLabels,
                datasets: [
                    {
                      label: `YTD Contribution to Volatility and YTD Return For Watchlist`,
                      data: percContr,
                      backgroundColor: 'rgba(255, 99, 132, 1)',
                      borderColor: 'rgba(255, 99, 132, 1)'
                    },
                  ],
              }

              return chart
        }

        setCreateChart(drawChart())
        setChartCreated(true)
    }, [myChartData, percContr, stockLabels])

    return {
        chartCreated, 
        createChart
    }
}