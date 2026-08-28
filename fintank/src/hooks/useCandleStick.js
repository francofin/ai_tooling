import React, {useState, useEffect} from 'react';
import swal from 'sweetalert';

export const useCandleStick = (chartData) => {
    const [userChartData, setUserChartData] = useState(null)
    const [chartCreated, setChartCreated] = useState(false)
    const [createChart, setCreateChart] = useState(null)
    
    
    
    useEffect(() => {
        const drawChart = () => {
            setUserChartData(chartData)
            if(userChartData){
                let chartOptions = {
          
                    series: [{
                      name: 'candle',
                      data: userChartData
                    }],
                    options: {
                      chart: {
                        height: 350,
                        type: 'candlestick',
                      },
                      title: {
                        text: 'CandleStick Chart - Category X-axis',
                        align: 'left'
                      },
                      plotOptions: {
                        candlestick: {
                          colors: {
                            upward: '#019153',
                            downward: '#99030d'
                          }
                        }
                      },
                      annotations: {
                        xaxis: [
                          {
                            x: 'Oct 06 14:00',
                            borderColor: '#00E396',
                            label: {
                              borderColor: '#00E396',
                              style: {
                                fontSize: '12px',
                                color: '#fff',
                                background: '#00E396'
                              },
                              orientation: 'horizontal',
                              offsetY: 7,
                              text: 'Annotation Test'
                            }
                          }
                        ]
                      },
                      tooltip: {
                        enabled: true,
                      },
                      xaxis: {
                        type: 'datetime',
                        // labels: {
                        //   formatter: function(val) {
                        //     return dayjs(val).format('MMM DD HH:mm')
                        //   }
                        // }
                      },
                      yaxis: {
                        tooltip: {
                          enabled: true
                        }
                      }
                    },
                  
                  
                  };
                setChartCreated(true)
                return chartOptions
            }
        }
        

        setCreateChart(drawChart())
        
    }, [chartData, userChartData])

    return {
        chartCreated, 
        createChart
    }
}
