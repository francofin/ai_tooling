import React, { useEffect, useRef, useState, useMemo } from "react"
import useSWR from "swr"
import axios from 'axios'

const fetcher = async (url) => {
  const res = await axios.get(url)
  
  const resData = res.data
  return resData
}

  export const useSectorReturnTS = (frequency) => {


    
    const [dates, setDates] = useState([])
    const [basicMaterial, setBasicMaterial] = useState([])
    const [communication, setCommunication] = useState([])
    const [consCyc, setConsCyc] = useState([])
    const [consDisc, setConsDisc] = useState([])
    const [energy, setEnergy] = useState([])
    const [finServices, setFinServices] = useState([])
    const [financials, setFinancials] = useState([])
    const [healthCare, setHealthCare] = useState([])
    const [industrials, setIndustrials] = useState([])
    const [realEstate, setRealEstate] = useState([])
    const [tech, setTech] = useState([])
    const [utilities, setUtilities] = useState([])
    const [exportedData, setExportedData] = useState({})


    const [volDates, setVolDates] = useState([])
    const [basicMaterialVol, setVolBasicMaterial] = useState([])
    const [communicationVol, setVolCommunication] = useState([])
    const [consCycVol, setVolConsCyc] = useState([])
    const [consDiscVol, setVolConsDisc] = useState([])
    const [energyVol, setVolEnergy] = useState([])
    const [finServicesVol, setVolFinServices] = useState([])
    const [financialsVol, setVolFinancials] = useState([])
    const [healthCareVol, setVolHealthCare] = useState([])
    const [industrialsVol, setVolIndustrials] = useState([])
    const [realEstateVol, setVolRealEstate] = useState([])
    const [techVol, setVolTech] = useState([])
    const [utilitiesVol, setVolUtilities] = useState([])
    const [exportedVolData, setExportedVolData] = useState({})

    const SECTOR_TIME_SERIES_URL = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/sector-timeseries/${frequency}/`;

    const {data} = useSWR(
      SECTOR_TIME_SERIES_URL,
      fetcher
  )
  

  useEffect(() => {
    setDates(data?.return_time_series?.dates)
    setBasicMaterial(data?.return_time_series?.basicM)
    setCommunication(data?.return_time_series?.communications)
    setConsCyc(data?.return_time_series?.cons_cyc)
    setConsDisc(data?.return_time_series?.cons_def)
    setEnergy(data?.return_time_series?.energy)
    setFinServices(data?.return_time_series?.fin_services)
    setFinancials(data?.return_time_series?.financials)
    setHealthCare(data?.return_time_series?.health_care)
    setIndustrials(data?.return_time_series?.industrials)
    setRealEstate(data?.return_time_series?.real_estate)
    setTech(data?.return_time_series?.tech)
    setUtilities(data?.return_time_series?.utilities)


    setVolDates(data?.vol_time_series?.dates)
    setVolBasicMaterial(data?.vol_time_series?.basicM)
    setVolCommunication(data?.vol_time_series?.communications)
    setVolConsCyc(data?.vol_time_series?.cons_cyc)
    setVolConsDisc(data?.vol_time_series?.cons_def)
    setVolEnergy(data?.vol_time_series?.energy)
    setVolFinServices(data?.vol_time_series?.fin_services)
    setVolFinancials(data?.vol_time_series?.financials)
    setVolHealthCare(data?.vol_time_series?.health_care)
    setVolIndustrials(data?.vol_time_series?.industrials)
    setVolRealEstate(data?.vol_time_series?.real_estate)
    setVolTech(data?.vol_time_series?.tech)
    setVolUtilities(data?.vol_time_series?.utilities)

    const returnChartData = () => {

      const chartData = {
        labels:data? dates : [],
        datasets:[
          {
            label: 'Basic Materials',
            data: data? basicMaterial : [],
            borderColor: 'rgb(235, 64, 52)',
            backgroundColor: 'rgba(235, 64, 52, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Communications',
            data: data? communication: [],
            borderColor: 'rgb(52, 235, 195)',
            backgroundColor: 'rgba(52, 235, 195, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Consumer Cyclical',
            data: data? consCyc: [],
            borderColor: 'rgb(52, 165, 235)',
            backgroundColor: 'rgba(52, 165, 235, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Consumer Discretionary',
            data: data? consDisc: [],
            borderColor: 'rgb(165, 52, 235)',
            backgroundColor: 'rgba(165, 52, 235, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Energy',
            data: data? energy: [],
            borderColor: 'rgb(51, 56, 48)',
            backgroundColor: 'rgba(51, 56, 48, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Financial Services',
            data: data? finServices: [],
            borderColor: 'rgb(13, 75, 145)',
            backgroundColor: 'rgba(13, 75, 145, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Financials',
            data: data? financials: [],
            borderColor: 'rgb(153, 17, 26)',
            backgroundColor: 'rgba(153, 17, 26, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Health Care',
            data: data? healthCare: [],
            borderColor: 'rgb(17, 124, 153)',
            backgroundColor: 'rgba(17, 124, 153, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Industrials',
            data: data? industrials: [],
            borderColor: 'rgb(204, 95, 27)',
            backgroundColor: 'rgba(204, 95, 27, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Real Estate',
            data: data? realEstate: [],
            borderColor: 'rgb(16, 158, 37)',
            backgroundColor: 'rgba(16, 158, 37, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Technology',
            data: data? tech: [],
            borderColor: 'rgb(217, 206, 91)',
            backgroundColor: 'rgba(217, 206, 91, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
          {
            label: 'Utilities',
            data: data? utilities: [],
            borderColor: 'rgb(189, 60, 180)',
            backgroundColor: 'rgba(189, 60, 180, 0.5)',
            borderWidth: 3,
            radius: 0,
            yAxisID: 'y',
          },
        ]
    }

    return chartData
  }


  const returnVolChartData = () => {

    const chartData = {
      labels:data? volDates : [],
      datasets:[
        {
          label: 'Basic Materials',
          data: data? basicMaterialVol : [],
          borderColor: 'rgb(235, 64, 52)',
          backgroundColor: 'rgba(235, 64, 52, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Communications',
          data: data? communicationVol: [],
          borderColor: 'rgb(52, 235, 195)',
          backgroundColor: 'rgba(52, 235, 195, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Consumer Cyclical',
          data: data? consCycVol: [],
          borderColor: 'rgb(52, 165, 235)',
          backgroundColor: 'rgba(52, 165, 235, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Consumer Discretionary',
          data: data? consDiscVol: [],
          borderColor: 'rgb(165, 52, 235)',
          backgroundColor: 'rgba(165, 52, 235, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Energy',
          data: data? energyVol: [],
          borderColor: 'rgb(51, 56, 48)',
          backgroundColor: 'rgba(51, 56, 48, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Financial Services',
          data: data? finServicesVol: [],
          borderColor: 'rgb(13, 75, 145)',
          backgroundColor: 'rgba(13, 75, 145, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Financials',
          data: data? financialsVol: [],
          borderColor: 'rgb(153, 17, 26)',
          backgroundColor: 'rgba(153, 17, 26, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Health Care',
          data: data? healthCareVol: [],
          borderColor: 'rgb(17, 124, 153)',
          backgroundColor: 'rgba(17, 124, 153, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Industrials',
          data: data? industrialsVol: [],
          borderColor: 'rgb(204, 95, 27)',
          backgroundColor: 'rgba(204, 95, 27, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Real Estate',
          data: data? realEstateVol: [],
          borderColor: 'rgb(16, 158, 37)',
          backgroundColor: 'rgba(16, 158, 37, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Technology',
          data: data? techVol: [],
          borderColor: 'rgb(217, 206, 91)',
          backgroundColor: 'rgba(217, 206, 91, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
        {
          label: 'Utilities',
          data: data? utilitiesVol: [],
          borderColor: 'rgb(189, 60, 180)',
          backgroundColor: 'rgba(189, 60, 180, 0.5)',
          borderWidth: 3,
          radius: 0,
          yAxisID: 'y',
        },
      ]
  }

  return chartData
}
    const myChartData = returnChartData()
    const myChartVolData = returnVolChartData()

    setExportedData(myChartData)
    setExportedVolData(myChartVolData)
    


  }, [data, dates])

  
   

    const options = {
      responsive: true,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      stacked: false,
      plugins: {
        title: {
          display: true,
          text: '',
        },
      },
      scales: {
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          grid: {
            drawOnChartArea: false,
          },
        },
        xAxes: [{
          type: 'time',
          distribution: 'linear',
          display:false,
        }],
      },
    };

    
    


    return {
      data, 
      options,
      exportedData,
      exportedVolData
    }
        

  }