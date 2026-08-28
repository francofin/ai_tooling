export const indexMappings = {
    'sp500':{'chartColor':'rgba(21, 129, 179, 0.8)'},
    'nas':{'chartColor':'rgba(245, 223, 24, 0.8)'},
    'rus_2000':{'chartColor':'rgba(11, 191, 134, 0.8)'},
    'rus_1000':{'chartColor':'rgba(119, 11, 191, 0.8)'},
    'tsx':{'chartColor':'rgba(21, 19, 138, 0.8)'},
    'tsx_60':{'chartColor':'rgba(31, 19, 138, 0.8)'},
    'dj':{'chartColor':'rgba(20, 191, 11, 0.8)'},
    'nsei':{'chartColor':'rgba(78, 78, 78, 0.8)'},
    'vix':{'chartColor':'rgba(179, 61, 32, 0.8)'},
    'nik':{'chartColor':'rgba(115, 113, 10, 0.8)'},
    'hsi':{'chartColor':'rgba(18, 97, 56, 0.8)'},
    'ftse':{'chartColor':'rgba(15, 160, 185, 0.8)'},
    'short_term':{'chartColor':'rgba(21, 47, 54, 0.8)'},
    'ten_year':{'chartColor':'rgba(82, 26, 82, 0.8)'},
    'thirty_year':{'chartColor':'rgba(221, 190, 14, 0.9)'}
}


export const sectorMappings = [
    {
        "value":"nas",
        "label":"NASDAQ"
    },
    {
        "value":"nyse",
        "label":"NYSE"
    },
    {
        "value":"amex",
        "label":"AMEX"
    },
    {
        "value":"tsx",
        "label":"TSX"
    },
    {
        "value":"lse",
        "label":"LSE"
    }
]

/**
 * The indexes served by `/index-history/{key}`, in the order the homepage grid
 * lays them out.
 *
 * Labels are copied from the backend's own names for these series
 * (`analyzer/analyzer_utils/CorePerformanceTools.py`), so the picker and the
 * banner the chart draws under itself agree.
 *
 * Note these keys are not the `constituentIndexMaps` ones below — that list
 * addresses a different endpoint and uses different keys for the same indexes.
 */
export const indexChartMaps = [
    { value: 'sp500',       label: 'S&P 500' },
    { value: 'nas',         label: 'NASDAQ Composite Index' },
    { value: 'dj',          label: 'Dow Jones Index' },
    { value: 'rus_1000',    label: 'Russell 1000 Index' },
    { value: 'tsx',         label: 'S&P/TSX Composite Index' },
    { value: 'tsx_60',      label: 'TSX 60 Index' },
    { value: 'rus_2000',    label: 'Russell 2000 Index' },
    { value: 'ftse',        label: 'FTSE 100 Index' },
    { value: 'nik',         label: 'Nikkei 225 Index' },
    { value: 'nsei',        label: 'Nifty 50' },
    { value: 'hsi',         label: 'Hang Seng Index' },
    { value: 'vix',         label: 'CBOE Volatility Index' },
    { value: 'short_term',  label: '13 Week Treasury Bill Index' },
    { value: 'ten_year',    label: 'Treasury Yield 10 Years Index' },
    { value: 'thirty_year', label: 'Treasury Yield 30 Years Index' },
]

export const constituentIndexMaps = [
    {
        "value":"sp500",
        "label":"S&P 500"
    },
    {
        "value":"nasdaq",
        "label":"NASDAQ"
    },
    {
        "value":"r2000",
        "label":"Russell 2000"
    },
    {
        "value":"rmicro",
        "label":"Russell Microcap"
    },
    {
        "value":"tsx",
        "label":"TSX"
    },
    {
        "value":"tsx_small_cap",
        "label":"TSX Small Cap"
    }
]
