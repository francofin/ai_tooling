import {useState, useEffect} from 'react';
import { indexMappings } from '../utils/IndexMappings';
import {fetcher} from '../utils/helpers';

export const useIndexCharter = (index) => {

    const [chartData, setChartData] = useState({ labels: [], datasets: [] })
    const [chartOptions, setChartOptions] = useState(null)
    const [indexName, setIndexName] = useState('Index')
    const [loading, setLoading] = useState(true)


    useEffect(() => {
        const fetchData = async () => {
        try {
            setLoading(true)

            const baseUrl = `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/index-history/${index}/`
            const indexDataPack = await fetcher(baseUrl)

            const data = indexDataPack?.data || {}
            const labels = data.dates || []
            const prices = data.prices || []
            const volumes = data.volume || []

            const name = indexDataPack?.index_name || 'Index'
            const chartColor = indexMappings[name]?.chartColor || 'rgba(0, 0, 0, 1)'

            setIndexName(name)

            setChartData({
            labels,
            datasets: [
                {
                    type: 'line',
                    label: name,
                    data: prices,
                    borderColor: chartColor,
                    backgroundColor: chartColor,
                    pointRadius: 1,
                    yAxisID: 'y',
                    tension: 0.25
                },
                {
                    type: 'bar',
                    label: 'Volume',
                    data: volumes,
                    backgroundColor: 'rgba(180,180,180,0.4)',
                    yAxisID: 'yVolume',
                    barPercentage: 1.0,
                    categoryPercentage: 1.0
                }
            ]
            })

            setChartOptions({
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                        legend: {
                        position: 'bottom'
                        },
                        title: {
                        display: false,
                        text: 'Index Level'
                        },
                        tooltip: {
                        callbacks: {
                            label: (ctx) => {
                            const value = ctx.raw

                            if (ctx.dataset.label === 'Volume') {
                                return `Volume: ${value.toLocaleString()}`
                            }

                            return `${ctx.dataset.label}: ${value}`
                            }
                        }
                        }
                    },
                animations: {
                        tension: {
                        duration: 1000,
                        easing: 'linear',
                        from: 1,
                        to: 0
                        }
                    },
                scales: {
                    y: {
                    type: 'linear',
                    position: 'left',
                    ticks: {
                            autoSkip: true
                        },
                        title: {
                            display: true,
                            text: 'Price'
                        }
                    },
                    yVolume: {
                        type: 'linear',
                        position: 'right',
                        grid: {
                            drawOnChartArea: false
                        },
                        ticks: {
                            callback: (value) => {
                            if (value >= 1e9) return `${value / 1e9}B`
                            if (value >= 1e6) return `${value / 1e6}M`
                            return value
                            }
                        }
                    },
                    x: {
                    ticks: {
                            maxTicksLimit: 8
                            }
                        }
                    }
                })
            } catch (err) {
                console.error('Index chart error:', err)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
        
    }, [index])


    // bool, chart, namne
    return {
        chartData,
        chartOptions,
        indexName,
        loading
    }
}