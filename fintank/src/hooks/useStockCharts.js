import React, {useState, useEffect} from 'react';


export const useStockChart = (frequency, chartLabels, chartData) => {
    const [myChartLabels, setMyChartLabels] = useState([]);
    const [myChartData, setMyChartData] = useState([]);
    const [chartCreated, setChartCreated] = useState(false);
    const [createChart, setCreateChart] = useState(null);

    // useEffect(() => {
    //     setMyChartLabels(chartLabels);
    //     setMyChartData(chartData)

    // }, [frequency, chartData, chartLabels])

    
    
    useEffect(() => {

        setMyChartLabels(chartLabels);
        setMyChartData(chartData)
        const drawChart = () => {
            let chart= {
                type:'line',
                labels:myChartLabels,
                datasets: [{
                  label: frequency+" Rolling Returns",
                  data:myChartData,
                  borderColor: 'rgb(11, 79, 135)',
                  backgroundColor: 'rgba(11, 79, 135)',
                  pointRadius: 1
                }]
              }

              return chart
        }

        setCreateChart(drawChart())
        setChartCreated(true)
    }, [myChartLabels, myChartData, frequency, chartData, chartLabels])

    return {
        chartCreated, 
        createChart
    }
}