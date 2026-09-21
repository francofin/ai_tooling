import React, {useState, useEffect} from 'react';
import { useRouter } from 'next/router';
import {fetcher} from '../utils/helpers';

export const useIndexHeatMaps = (index, initialIndexName) => {
    const [loading, setLoading] = useState(true)
    const [series, setSeries] = useState([])
    const [options, setOptions] = useState(undefined)
    const [indexUniverseData, setIndexUniverseData] = useState([])
    const router = useRouter()

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const baseUrl = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/constituent-returns/${index}/`
                const indexDataPack = await fetcher(baseUrl);
                const universeData = indexDataPack?.universe_data || []
                const heatMapData = indexDataPack?.heat_map || []

                setIndexUniverseData(universeData)
                setSeries([{data: heatMapData}])

                setOptions({
                  legend: { show: false },
                  chart: {
                    height: 350,
                    type: 'treemap',
                    toolbar: { show: false },
                    background: '#ffffff',
                    foreColor: '#000000',
                    events: {
                      dataPointSelection: function(event, chartContext, config) {
                        const symbol = config.w.config.series[0]?.data[config.dataPointIndex]?.x
                        if (symbol) router.push(`/stocks/${symbol}`)
                      }
                    }
                  },
                  title: {
                    text: `${initialIndexName} Stock Performance`,
                    align: 'left',
                    style: { color: '#000000' }
                  },
                  dataLabels: {
                    enabled: true,
                    style: { fontSize: '12px' },
                    formatter: function(text, op) {
                      return [text, `${op.value}%`]
                    },
                    offsetY: -4
                  },
                  plotOptions: {
                    treemap: {
                      enableShades: false,
                      colorScale: {
                        ranges: [
                          { from: -9999,   to: -6,      color: '#5a0a10' },
                          { from: -5.9999, to: -3,      color: '#3d0912' },
                          { from: -2.9999, to: -0.0001, color: '#3d0912' },
                          { from: -0.0001, to: 0.0001,  color: '#1c1c1e' },
                          { from: 0.0001,  to: 3,       color: '#0d3a18' },
                          { from: 3.0001,  to: 9999,    color: '#0d4a1f' },
                        ]
                      }
                    }
                  },
                  tooltip: {
                    theme: 'dark',
                    y: { formatter: (value) => `${value}%` }
                  }
                })
            } catch (error) {
                console.error("Error fetching heat map data:", error);
            } finally {
                setLoading(false)
            }
        }
        fetchData()
    }, [index, initialIndexName]);

    return { options, series, loading, indexUniverseData }
}
