import React, {useState, useEffect, useMemo} from 'react';
import swal from 'sweetalert';

export const useSectorBarChart = (sectorData, ticker) => {
    const [rawSectorData, setRawSectorData] = useState([])
    const [myChartLabels, setMyChartLabels] = useState([]);
    const [myChartData, setMyChartData] = useState([]);
    const [barChartCreated, setBarChartCreated] = useState(false);
    const [createChart, setCreateChart] = useState(null);

    

    useMemo(() => {
        setRawSectorData(sectorData)
    }, [sectorData])
    
    useMemo(() => {

        console.log(rawSectorData)
        let chartSectorLabels = [];
        let chartSectorData = [];

        for(let i=0; i<rawSectorData?.length; i++){
            chartSectorData.push(parseFloat(rawSectorData[i]?.exposure));
            chartSectorLabels.push(rawSectorData[i]?.industry);
        }
        setMyChartLabels(chartSectorLabels);
        setMyChartData(chartSectorData);

    }, [rawSectorData])


    useEffect(() => {

        const customBorderColor = myChartLabels?.map(() => 'rgba(46, 46, 46, 0.5)');
        const customBarColor = myChartLabels?.map(() => 'rgba(222, 204, 11, 0.5)');
        const drawChart = () => {
                let chart= {
                    labels:myChartLabels,
                    datasets: [
                        {
                            label: ticker + "Sector Exposure",
                            data:myChartData,
                            borderColor:customBorderColor,
                            backgroundColor:customBarColor
                        }
                    ]
                }
                setBarChartCreated(true)
                return chart
            }
        

        setCreateChart(drawChart())
        
    }, [myChartLabels, myChartData])

    

    return {
        barChartCreated, 
        createChart
    }

   
}