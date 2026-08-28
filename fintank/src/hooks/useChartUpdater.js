import React, {useState, useEffect} from 'react';
import data from "@data/chartsettings.json"
import axios from 'axios';

const chartColorSet = ['rgba(21, 129, 179)', 'rgba(245, 223, 24)', 'rgba(11, 191, 134)', 'rgba(138, 19, 122)', 'rgba(20, 191, 11)', 
'rgba(78, 78, 78)', 'rgba(179, 61, 32)', 'rgba(115, 113, 10)', 'rgba(18, 97, 56)', 'rgba(21, 47, 54)',
 'rgba(82, 26, 82)', 'rgba(44, 160, 168)'];


export const useChartUpdater = (assets, assetOnePrices,assetOneDates, assetTwoPrices, assetTwoDates) => {
    const [myChartLabels, setMyChartLabels] = useState([]);
    const [myChartData, setMyChartData] = useState([]);
    const [myAssets, setMyAssets] = useState(assets);
    const [indexChartCreated, setIndexChartCreated] = useState(false);
    const [createIndexChart, setCreateChart] = useState(null);
    const [myAssetOneData, setMyAssetOneData] = useState(assetOnePrices)
    const [myAssetOneDates, setMyAssetOneDates] = useState(assetOneDates)
    const [myAssetTwoData, setMyAssetTwoData] = useState(assetTwoPrices)
    const [myAssetTwoDates, setMyAssetTwoDates] = useState(assetTwoDates)
    const [chartColors, setChartColors] = useState(chartColorSet);
    const [dataPack, setDataPack] = useState([]);


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
            text: `Asset Relative Comparisons`,
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

      // yAxisID: 'y'.concat(i%2===0?'':'1'),
    

    useEffect(() => {

      

      const setUpChart = () => {

          // const allChartData = []
          // const itemOneData = assetOnePrices;
          // const itemOneDates = assetOneDates;
          // const chartOneData = {
          //           label: `${myAssets[0].label}`,
          //           data: assetOnePrices,
          //           borderColor: chartColors[0],
          //           backgroundColor: chartColors[0],
          //           yAxisID: 'y',
          //           pointRadius: 1
          //   }
          // allChartData.push(chartOneData);
          // const itemTwoData = assetTwoPrices;
          // const itemTwoDates = assetTwoDates;
          // const chartTwoData = {
          //           label: `${myAssets[1].label}`,
          //           data: assetTwoPrices,
          //           borderColor: chartColors[1],
          //           backgroundColor: chartColors[1],
          //           yAxisID: 'y1',
          //           pointRadius: 1
          //   }
          // allChartData.push(chartTwoData);
          // setDataPack(allChartData)

        
        
        
        // let dataDate = [];
        
        // if(assetOneDates?.length > assetTwoDates?.length){
        //   dataDate = assetOneDates;
        // } else{
        //   dataDate = assetTwoDates;
        // }
        // console.log(dataPack)
        let labels = assetOneDates;
        console.log(assetOneDates)
        let chart= {
          labels,
          datasets: [
              {
                label: `${myAssets[0].label}`,
                data: assetOnePrices,
                borderColor: 'rgb(21, 129, 179)',
                backgroundColor: 'rgba(21, 129, 179, 1)',
                yAxisID: 'y',
                pointRadius: 1
              },
              {
                label: `${myAssets[1].label}`,
                data: assetTwoPrices,
                borderColor: 'rgb(199, 10, 10)',
                backgroundColor: 'rgba(199, 10, 10, 1)',
                yAxisID: 'y1',
                pointRadius: 1
              },
            ],
        }

        return chart

        
      }
    
        setCreateChart(setUpChart());
        setIndexChartCreated(true); 


    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [assetOnePrices, assetOneDates, assetTwoPrices, assetTwoDates]);

  


    return {
        indexChartCreated, 
        createIndexChart,
        chartOptions
    }
}