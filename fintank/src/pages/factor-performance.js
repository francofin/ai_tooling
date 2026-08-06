import React, {useEffect, useMemo, useState, useContext, useRef} from "react"
import Link from "next/link"
import Image from "@componentsLegacy/CustomImage"
import axios from 'axios'
import { DayPicker } from "react-day-picker"
import "react-day-picker/dist/style.css"
import { Container, Row, Col, Button, Dropdown, Form, Overlay, Collapse, Pagination, InputGroup, ListGroup, Modal } from "react-bootstrap"
import { faAngleDoubleRight  } from "@fortawesome/free-solid-svg-icons"
import UseWindowSize from "@hooks/UseWindowSize"
import Select from "react-select"
import { useChartResource } from "@hooks/useChartResources"
import Nouislider from "nouislider-react"
import data from "@data/chartsettings.json"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faArrowRight, faSearch } from "@fortawesome/free-solid-svg-icons"
import { useNewCandleStick } from "@hooks/useNewCandleSticks";
import { useStockNames } from "@hooks/useStockNames"
import { useRouter } from "next/router"
import Icon from "@componentsLegacy/Icon"
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, BarElement, LineElement, Title, Tooltip, LineController, BarController, Legend } from 'chart.js';

import swal from 'sweetalert';
import { Line, Chart } from 'react-chartjs-2';
import { factorCharter } from "@utils/plotFactorChart"
import dynamic from 'next/dynamic'
import {connect} from 'react-redux';
import bucketAction from '../src/actions/bucketAction'
import { bindActionCreators } from "redux"
const ReactApexChart = dynamic(() => import('react-apexcharts'), { ssr: false });

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  LineController,
  BarController,
);


export async function getStaticProps() {

  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Factor Performance",
    },
  }
}



const StockPerformances = (props) => {
  const [index, setIndex] = useState('')
  const [indexLabel, setIndexLabel] = useState('Select Index')
  const [frequency, setFrequency] = useState('')
  const [frequencyLabel, setFrequencyLabel] = useState('Select Periodicity')
  const [peChart, setPeChart] = useState(false)
  const [peData, setPeData] = useState(null)
  const [peKeys, setPeKeys] = useState([]);
  const [peStocks, setPeStocks] = useState(null);
  const [betaChart, setBetaChart] = useState(false)
  const [betaData, setBetaData] = useState(null)
  const [betaKeys, setBetaKeys] = useState([]);
  const [betaStocks, setBetaStocks] = useState(null);
  const [cfdChart, setCfdChart] = useState(false)
  const [cfdData, setCfdData] = useState(null)
  const [cfdKeys, setCfdKeys] = useState([]);
  const [cfdStocks, setCfdStocks] = useState(null);
  const [psChart, setPSChart] = useState(false)
  const [psData, setPSData] = useState(null)
  const [psKeys, setPsKeys] = useState([]);
  const [psStocks, setPsStocks] = useState(null);
  const [pbChart, setPbChart] = useState(false)
  const [pbData, setPbData] = useState(null)
  const [pbKeys, setPbKeys] = useState([]);
  const [pbStocks, setPbStocks] = useState(null);
  const [pcfChart, setPcfChart] = useState(false)
  const [pcfData, setPcfData] = useState(null)
  const [pcfKeys, setPcfKeys] = useState([]);
  const [pcfStocks, setPcfStocks] = useState(null);
  const [roeChart, setRoeChart] = useState(false)
  const [roeData, setRoeData] = useState(null)
  const [roeKeys, setRoeKeys] = useState([]);
  const [roeStocks, setRoeStocks] = useState(null);
  const [deChart, setDeChart] = useState(false)
  const [deData, setDeData] = useState(null)
  const [deKeys, setDeKeys] = useState([]);
  const [deStocks, setDeStocks] = useState(null);
  const [fcfChart, setFcfChart] = useState(false)
  const [fcfData, setFcfData] = useState(null)
  const [fcfKeys, setFcfKeys] = useState([]);
  const [fcfStocks, setFcfStocks] = useState(null);
  const [divChart, setDivChart] = useState(false)
  const [divData, setDivData] = useState(null)
  const [divKeys, setDivKeys] = useState([]);
  const [divStocks, setDivStocks] = useState(null);
  const [stdevOneChart, setStdevOneChart] = useState(false)
  const [stdevOneData, setStdevOneData] = useState(null)
  const [stdevOneKeys, setStdevOneKeys] = useState([]);
  const [stdevOneStocks, setStdevOneStocks] = useState(null);
  const [stdevThreeChart, setStdevThreeChart] = useState(false)
  const [stdevThreeData, setStdevThreeData] = useState(null)
  const [stdevThreeKeys, setStdevThreeKeys] = useState([]);
  const [stdevThreeStocks, setStdevThreeStocks] = useState(null);
  const [stdevSixChart, setStdevSixChart] = useState(false)
  const [stdevSixData, setStdevSixData] = useState(null)
  const [stdevSixKeys, setStdevSixKeys] = useState([]);
  const [stdevSixStocks, setStdevSixStocks] = useState(null);
  const [stdevYtdChart, setStdevYtdChart] = useState(false)
  const [stdevYtdData, setStdevYtdData] = useState(null)
  const [stdevYtdKeys, setStdevYtdKeys] = useState([]);
  const [stdevYtdStocks, setStdevYtdStocks] = useState(null);
  const [sectorChart, setSectorChart] = useState(false)
  const [sectorData, setSectorData] = useState(null)
  const [sectorKeys, setSectorKeys] = useState([]);
  const [sectorStocks, setSectorStocks] = useState(null);
  const [loading, setLoading] = useState(false);

  const [analysisLink, setAnalysisLink] = useState("/rankings/[slug]");
  const [linkAs, setLinkAs] = useState(`/rankings/`)


  const handleIndexSelection = (e) => {
    console.log(e)
    setIndexLabel(e.label);
    setIndex(e.value);
  }

  const handleFrequencySelection = (e) => {
    console.log(e)
    setFrequencyLabel(e.label);
    setFrequency(e.value);
  }

  const handlBucketData = (e) =>{
    setLoading(true);
    console.log(e.target.value)
    let bucketData;
    let bucketKeys;
    if (e.target.value === 'pe'){
      bucketData = peStocks;
      bucketKeys = peKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Price to Earnings Rankings', indexLabel, 'Price/Earnings');
      setLoading(false)
      !loading && window.open("/rankings/pe","_blank")
    } else if(e.target.value === 'ps'){
      bucketData = psStocks;
      bucketKeys = psKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Price to Sales Rankings', indexLabel, 'Price/Sales');
      setLoading(false)
      !loading && window.open("/rankings/ps","_blank")
    }
    else if(e.target.value === 'pb'){
      bucketData = pbStocks;
      bucketKeys = pbKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Price to Book Rankings', indexLabel, 'Price/Book');
      setLoading(false)
      !loading && window.open("/rankings/pb","_blank")
    }
    else if(e.target.value === 'pcf'){
      bucketData = pcfStocks;
      bucketKeys = pcfKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Price to Cash Flow Rankings', indexLabel, 'Price/Cash Flow');
      setLoading(false)
      !loading && window.open("/rankings/pcf","_blank")
    }
    else if(e.target.value === 'div'){
      bucketData = divStocks;
      bucketKeys = divKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Dividend Yield Rankings', indexLabel, 'Dividend Yield');
      setLoading(false)
      !loading && window.open("/rankings/div","_blank")
    }
    else if(e.target.value === 'fcf'){
      bucketData = fcfStocks;
      bucketKeys = fcfKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Free Cash Flow Rankings', indexLabel, 'Free Cash Flow');
      setLoading(false)
      !loading && window.open("/rankings/fcf","_blank")
    }
    else if(e.target.value === 'de'){
      bucketData = deStocks;
      bucketKeys = deKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Debt to Equity Rankings', indexLabel, 'Debt/Equity');
      setLoading(false)
      !loading && window.open("/rankings/de","_blank")
    }
    else if(e.target.value === 'roe'){
      bucketData = roeStocks;
      bucketKeys = roeKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Return on Equity Rankings', indexLabel, 'Return on Equity');
      setLoading(false)
      !loading && window.open("/rankings/roe","_blank")
    }
    else if(e.target.value === 'cfd'){
      bucketData = cfdStocks;
      bucketKeys = cfdKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Cash Flow to Debt Rankings', indexLabel, 'Cash Flow/Debt');
      setLoading(false)
      !loading && window.open("/rankings/cfd","_blank")
    }
    else if(e.target.value === 'stdevone'){
      bucketData = stdevOneStocks;
      bucketKeys = stdevOneKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Standard Deviation One Month Rankings', indexLabel, 'Standard Deviation One Month');
      setLoading(false)
      !loading && window.open("/rankings/stdone","_blank")
    }
    else if(e.target.value === 'stdevthree'){
      bucketData = stdevThreeStocks;
      bucketKeys = stdevThreeKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Standard Deviation Three Month Rankings', indexLabel, 'Standard Deviation Three Month');
      setLoading(false)
      !loading && window.open("/rankings/stdthree","_blank")
    }
    else if(e.target.value === 'stdevsix'){
      bucketData = stdevSixStocks;
      bucketKeys = stdevSixKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Standard Deviation Six Month Rankings', indexLabel, 'Standard Deviation Six Month');
      setLoading(false)
      !loading && window.open("/rankings/stdsix","_blank")
    }
    else if(e.target.value === 'stdevytd'){
      bucketData = stdevYtdStocks;
      bucketKeys = stdevYtdKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Standard Deviation Year to Date Rankings', indexLabel, 'Standard Deviation YTD');
      setLoading(false)
      !loading && window.open("/rankings/stdytd","_blank")
    }
    else if(e.target.value === 'sector'){
      bucketData = sectorStocks;
      bucketKeys = sectorKeys;
      props.bucketActionRun(bucketData, bucketKeys, 'Sector Rankings', indexLabel, 'Sector');
      setLoading(false)
      !loading && window.open("/rankings/sector","_blank")
    }
  
  }

  const submitDecilePerformance = async(e) => {
    e.preventDefault();
    if(index === '' || frequency === ''){
      swal({
        title: `You Must Select an Index and a Time Period first.`,
        icon: "warning",
    });
    return
    }
      let periodicityData;
      let periodicityResults= null;
      if (index && frequency){
        periodicityData = axios.get(`${process.env.NEXT_PUBLIC_FINTANK_API_URL}/getstockquintiles/${frequency}/${index}/`)
        periodicityResults = (await periodicityData).data;

        console.log(periodicityResults);
        const peCharter = factorCharter(periodicityResults?.data?.pe?.values, periodicityResults?.data?.pe?.buckets, 'Price/Earnings', 'Stock Returns Ranked by Price to Earnings Ratio')
        setPeChart(true)
        setPeData(peCharter)
        setPeKeys(periodicityResults?.data?.pe?.bucket_keys)
        setPeStocks(periodicityResults?.data?.pe?.bucket_holdings)

        const psCharter = factorCharter(periodicityResults?.data?.ps?.values, periodicityResults?.data?.ps?.buckets, 'Price/Sales', 'Stock Returns Ranked by Price to Sales Ratio')
        setPSChart(true)
        setPSData(psCharter)
        setPsKeys(periodicityResults?.data?.ps?.bucket_keys)
        setPsStocks(periodicityResults?.data?.ps?.bucket_holdings)

        const pbCharter = factorCharter(periodicityResults?.data?.pb?.values, periodicityResults?.data?.pb?.buckets, 'Price/Book', 'Stock Returns Ranked by Price to Book Ratio')
        setPbChart(true)
        setPbData(pbCharter)
        setPbKeys(periodicityResults?.data?.pb?.bucket_keys)
        setPbStocks(periodicityResults?.data?.pb?.bucket_holdings)

        const pcfCharter = factorCharter(periodicityResults?.data?.pcf?.values, periodicityResults?.data?.pcf?.buckets, 'Price/Cash Flow', 'Stock Returns Ranked by Price to Cash Flow Ratio')
        setPcfChart(true)
        setPcfData(pcfCharter)
        setPcfKeys(periodicityResults?.data?.pcf?.bucket_keys)
        setPcfStocks(periodicityResults?.data?.pcf?.bucket_holdings)

        const divCharter = factorCharter(periodicityResults?.data?.div?.values, periodicityResults?.data?.div?.buckets, 'Dividend Yield', 'Stock Returns Ranked by Dividend Yield')
        setDivChart(true)
        setDivData(divCharter)
        setDivKeys(periodicityResults?.data?.div?.bucket_keys)
        setDivStocks(periodicityResults?.data?.div?.bucket_holdings)

        const fcfCharter = factorCharter(periodicityResults?.data?.fcf?.values, periodicityResults?.data?.fcf?.buckets, 'Free Cash Flow', 'Stock Returns Ranked by Free Cash Flow')
        setFcfChart(true)
        setFcfData(fcfCharter)
        setFcfKeys(periodicityResults?.data?.fcf?.bucket_keys)
        setFcfStocks(periodicityResults?.data?.fcf?.bucket_holdings)

        const roeCharter = factorCharter(periodicityResults?.data?.roe?.values, periodicityResults?.data?.roe?.buckets, 'Return On Equity', 'Stock Returns Ranked by Return On Equity')
        setRoeChart(true)
        setRoeData(roeCharter)
        setRoeKeys(periodicityResults?.data?.roe?.bucket_keys)
        setRoeStocks(periodicityResults?.data?.roe?.bucket_holdings)

        const deCharter = factorCharter(periodicityResults?.data?.de?.values, periodicityResults?.data?.de?.buckets, 'Debt to Equity', 'Stock Returns Ranked by Debt To Equity Ratio')
        setDeChart(true)
        setDeData(deCharter)
        setDeKeys(periodicityResults?.data?.de?.bucket_keys)
        setDeStocks(periodicityResults?.data?.de?.bucket_holdings)

        const cfdCharter = factorCharter(periodicityResults?.data?.cfd?.values, periodicityResults?.data?.cfd?.buckets, 'Cash Flow to Debt', 'Stock Returns Ranked by Cash Flow to Debt Ratio')
        setCfdChart(true)
        setCfdData(cfdCharter)
        setCfdKeys(periodicityResults?.data?.cfd?.bucket_keys)
        setCfdStocks(periodicityResults?.data?.cfd?.bucket_holdings)
        

        const betaCharter = factorCharter(periodicityResults?.data?.beta?.values, periodicityResults?.data?.beta?.buckets, 'Beta', 'Stock Returns Ranked by Beta')
        setBetaChart(true)
        setBetaData(betaCharter)
        setBetaKeys(periodicityResults?.data?.beta?.bucket_keys)
        setBetaStocks(periodicityResults?.data?.beta?.bucket_holdings)
        

        const stdevoneCharter = factorCharter(periodicityResults?.data?.stdevone?.values, periodicityResults?.data?.stdevone?.buckets, 'Standard Deviation One Month', 'Stock Returns Ranked by Standard Deviation One Month')
        setStdevOneChart(true)
        setStdevOneData(stdevoneCharter)
        setStdevOneKeys(periodicityResults?.data?.stdevone?.bucket_keys)
        setStdevOneStocks(periodicityResults?.data?.stdevone?.bucket_holdings)

        const stdevthreeCharter = factorCharter(periodicityResults?.data?.stdevthree?.values, periodicityResults?.data?.stdevthree?.buckets, 'Standard Deviation Three Month', 'Stock Returns Ranked by Standard Deviation Three Month')
        setStdevThreeChart(true)
        setStdevThreeData(stdevthreeCharter)
        setStdevThreeKeys(periodicityResults?.data?.stdevthree?.bucket_keys)
        setStdevThreeStocks(periodicityResults?.data?.stdevthree?.bucket_holdings)

        const stdevsixCharter = factorCharter(periodicityResults?.data?.stdevsix?.values, periodicityResults?.data?.stdevsix?.buckets, 'Standard Deviation Six Month', 'Stock Returns Ranked by Standard Deviation Six Month')
        setStdevSixChart(true)
        setStdevSixData(stdevsixCharter)
        setStdevSixKeys(periodicityResults?.data?.stdevsix?.bucket_keys)
        setStdevSixStocks(periodicityResults?.data?.stdevsix?.bucket_holdings)

        const stdevytdCharter = factorCharter(periodicityResults?.data?.stdevytd?.values, periodicityResults?.data?.stdevytd?.buckets, 'Standard Deviation YTD', 'Stock Returns Ranked by Standard Deviation YTD')
        setStdevYtdChart(true)
        setStdevYtdData(stdevytdCharter)
        setStdevYtdKeys(periodicityResults?.data?.stdevytd?.bucket_keys)
        setStdevYtdStocks(periodicityResults?.data?.stdevytd?.bucket_holdings)

        const sectorsCharter = factorCharter(periodicityResults?.data?.sectors?.values, periodicityResults?.data?.sectors?.buckets, 'Sectors', 'Stock Returns Ranked by Sector')
        setSectorChart(true)
        setSectorData(sectorsCharter)
        setSectorKeys(periodicityResults?.data?.sectors?.bucket_keys)
        setSectorStocks(periodicityResults?.data?.sectors?.bucket_holdings)
      } 
      
      
      
    }

    return (
        <React.Fragment>
            <section className="d-flex align-items-center dark-overlay">
            <Image
                src={`/images/homeImages/world.jpg`}
                layout="fill"
                className="bg-image"
                alt="Hero image"
                loading="eager"
                priority={true}
            />
            <Container className="py-6 py-lg-7 text-white overlay-content text-center">
                <Row>
                <Col xl="10" className="mx-auto">
                    <h1 className="display-3 fw-bold text-shadow">
                    {`Fintank Factor Researh`}
                    </h1>
                    <p className="text-lg text-shadow mt-3">{`Stock And Factor Research Performance`}</p>
                </Col>
                </Row>
            </Container>
            </section>
            <section className="py-1 bg-gray-100">
              <Container>
                <div className="text-center pb-lg-4">
                  <h2 className="mb-3">{`Stock Performance By Factor`}</h2>
                </div>
                <Row>
                <Col
                    lg="3"
                    className="mb-1 mb-lg-0 text-center"
                  >
                    <div className="px-0 px-lg-3">
                      <div className="icon-rounded bg-primary-light mb-3">
                        <Icon
                          icon='earth-globe-1'
                          className="text-primary w-2rem h-2rem"
                        />
                      </div>
                      <h3 className="h5">Select Index</h3>
                      <p className="text-muted">The stocks in the selected index will be divided into deciles or quartiles based on the number of stocks in the Index.</p>
                    </div>
                  </Col>
                  <Col
                    lg="6"
                    className="mb-1 mb-lg-0 text-center"
                  >
                    <div className="px-0 px-lg-3">
                      <div className="icon-rounded bg-primary-light mb-3">
                        <Icon
                          icon='time-1'
                          className="text-primary w-2rem h-2rem"
                        />
                      </div>
                      <h3 className="h5">Select A Frequency to Show for the Factors</h3>      
                      <p className="text-muted">The available frequencies include 1 Month, 3 Month, 6 Month and Year to Date returns. The performance of the stocks in the Index is divided based on the specific fundamental attribute. 
                      Stocks are sorted from highest to lowest based on the fundamental attributes presented, and the performance for a specific decile or quartile is computed. The stocks in each bucket are equal weighted.
                      The factor performance can help determine what stocks performed well over the selected frequency and what type of factor has been driving the markets.</p>
                    </div>
                  </Col>
                  <Col
                    lg="3"
                    className="mb-1 mb-lg-0 text-center"
                  >
                    <div className="px-0 px-lg-3">
                      <div className="icon-rounded bg-primary-light mb-3">
                        <Icon
                          icon='compass-1'
                          className="text-primary w-2rem h-2rem"
                        />
                      </div>
                      <h3 className="h5">Stocks Per Bucket</h3>
                      <p className="text-muted">Click on a specific factor to see the stocks in the buckets displayed. This is not advice about which stocks would outperform as the analysis is historical, but can help guide decisions as to what 
                      the market has been rewarding.</p>
                    </div>
                  </Col>
                </Row>
              </Container>
            </section>
            <Container fluid className="py-5 px-lg-5">
              <Row>
                <Col lg="2" className="pt-3">
                  <div className="mb-4">
                    <div className="filter-block">
                      <h6 className="mb-3">Select Index and Periodicity</h6>
                      <div className="mb-4">
                      <Form onSubmit={submitDecilePerformance}>
                        <Form.Label htmlFor="index">
                            Select Index
                        </Form.Label>
                        <div className="mb-4">
                        <Row>
                          <Col lg="12" className="pt-3">
                              <Select
                                name="index"
                                options={data.markets && data.markets}
                                value={indexLabel}
                                placeholder = {indexLabel}
                                onChange = {handleIndexSelection}
                                isSearchable
                                className="form-control dropdown bootstrap-select"
                                classNamePrefix="selectpicker"
                              />
                          </Col>
                        </Row>
                        </div>
                        <Form.Label htmlFor="index">
                            Select Periodicity
                        </Form.Label>
                        <div className="mb-4">
                        <Row>
                          <Col lg="12" className="pt-3">
                              <Select
                                name="periodicity"
                                options={data.factorPeriods && data.factorPeriods}
                                value={frequencyLabel}
                                placeholder = {frequencyLabel}
                                onChange = {handleFrequencySelection}
                                isSearchable
                                className="form-control dropdown bootstrap-select"
                                classNamePrefix="selectpicker"
                              />
                          </Col>
                        </Row>
                        </div>
                        <Row>
                          <Col lg="12" className="pt-3">
                          <Button
                              type="submit"
                              className={`h-100 ${
                                props.btnClassName ? props.btnClassName : ""
                              }`}
                            >
                              Show Performance
                            </Button>
                          </Col>
                        </Row>
                      </Form>
                      </div>
                    </div>
                  </div>
                </Col>
                <Col lg="9">
                  <Row>
                    {peChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'pe'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={peData?.options} series={peData?.series} type="bar" height={450} />
                    </Col>
                    }
                    {psChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'ps'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={psData?.options} series={psData?.series} type="bar" height={450} />
                    </Col>
                    }
                  </Row>
                  <Row>
                    {pbChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'pb'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={pbData?.options} series={pbData?.series} type="bar" height={325} />
                    </Col>
                    }
                    {pcfChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'pcf'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={pcfData?.options} series={pcfData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                    {divChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'div'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={divData?.options} series={divData?.series} type="bar" height={325} />
                    </Col>
                    }
                    {fcfChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'fcf'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={fcfData?.options} series={fcfData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                    {deChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'de'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={deData?.options} series={deData?.series} type="bar" height={325} />
                    </Col>
                    }
                    {roeChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'roe'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={roeData?.options} series={roeData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                    {cfdChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'cfd'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={cfdData?.options} series={cfdData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                  {stdevOneChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'stdevone'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={stdevOneData?.options} series={stdevOneData?.series} type="bar" height={325} />
                    </Col>
                    }
                    {stdevThreeChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'stdevthree'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={stdevThreeData?.options} series={stdevThreeData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                  {stdevSixChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'stdevsix'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={stdevSixData?.options} series={stdevSixData?.series} type="bar" height={325} />
                    </Col>
                    }
                    {stdevYtdChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'stdevytd'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={stdevYtdData?.options} series={stdevYtdData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                  {betaChart &&
                    <Col lg='6'>
                      <Button variant="link" value={'beta'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={betaData?.options} series={betaData?.series} type="bar" height={325} />
                    </Col>
                    }
                  </Row>
                  <Row>
                    {sectorChart &&
                    <Col lg='12'>
                      <Button variant="link" value={'sector'} onClick={handlBucketData}>Click to view Universe bucket holdings
                          <FontAwesomeIcon
                            icon={faAngleDoubleRight}
                            className="ms-2"
                          />
                      </Button>
                      <ReactApexChart options={sectorData?.options} series={sectorData?.series} type="bar" height={500} />
                    </Col>
                    }
                  </Row>
                </Col>
              </Row>
            </Container>
        </React.Fragment>
    )
}


function mapStateToProps(state){
  return {
    bucketAction:state.bucket
  }
}

function mapDispatchToProps(dispatch){

  return bindActionCreators({
    bucketActionRun:bucketAction
  }, dispatch)

}
export default connect(mapStateToProps, mapDispatchToProps)(StockPerformances);