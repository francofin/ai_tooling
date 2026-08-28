import React, {useState, useEffect} from 'react';

const colorSchemes = ['rgb(252, 186, 3)', 'rgb(198, 252, 3)','rgb(163, 16, 65)', 'rgb(108, 133, 21)', 'rgb(252, 248, 10)', 'rgb(68, 181, 27)', 'rgb(27, 96, 181)', 
'rgb(9, 40, 79)', 'rgb(118, 74, 133)', 'rgb(245, 20, 83)', 'rgb(245, 163, 20)','rgb(70, 219, 224)','rgb(22, 82, 13)','rgb(161, 201, 155)','rgb(3, 33, 36)',
'rgb(37, 20, 112)','rgb(112, 45, 20)','rgb(252, 248, 10)','rgb(35, 57, 222)','rgb(0, 1, 5)','rgb(163, 16, 65)','rgb(186, 99, 73)',]
export const useWatchListLineChart = (labels, data) => {
    const [myChartData, setMyChartData] = useState([]);
    const [chartCreated, setChartCreated] = useState(false);
    const [createChart, setCreateChart] = useState(null);

    const dataSets = []
    for(let i=0; i<data?.length; i++){
        dataSets.push({
            label: data[i].symbol,
            data: data[i].prices,
            borderColor: colorSchemes[i],
            backgroundColor: colorSchemes[i],
            yAxisID: i % 2 === 0?'y':'y1',
            pointRadius: 1
        }
        )
    }

    const chartOptions = {
        responsive: true,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        stacked: false,
        plugins: {
          title: {
            display: true,
            text: `Stock Price Movements`,
          },
        },
        scales: {
          y: {
            type: 'linear',
            display: true,
            position: 'left',
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            grid: {
              drawOnChartArea: false,
            },
          },
        },
      };



    useEffect(() => {


        const drawChart = () => {
            
            let chart= {
                labels,
                datasets: dataSets     
              }

              return chart
        }

        setCreateChart(drawChart())
        setChartCreated(true)
    }, [myChartData, data])

    return {
        chartCreated, 
        createChart,
        chartOptions
    }
}