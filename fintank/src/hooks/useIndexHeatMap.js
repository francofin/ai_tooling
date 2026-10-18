import React, {useState, useEffect} from 'react';
import { useRouter } from 'next/router';
import {fetcher} from '../utils/helpers';

/**
 * Treemap render cost, measured in headless Chromium against this exact
 * option set (ApexCharts 4.5), every tile labelled:
 *
 *    504 tiles (S&P 500)        781 ms   <- the bar that feels fine today
 *    500 tiles (capped Russell) ~1.0 s
 *   1000 tiles                 2385 ms
 *   1955 tiles (full Russell)  5006 ms   <- this is what froze the page
 *
 * Only the two Russell universes are big enough to matter: 1,955 and 1,350
 * names against 504 for the S&P. They are cut to their strongest and weakest
 * movers; every other universe is drawn whole and untouched.
 *
 * Labels are NOT suppressed. An earlier pass dropped the text on middle tiles
 * to buy speed, but it applied to every universe -- including the S&P, which
 * is never capped -- and left a visibly blank band through the middle of the
 * map. Capping the two Russells at 250 a side gets them to roughly the S&P's
 * cost with every tile still labelled, which is the better trade.
 */
const MAX_TILES_PER_SIDE = 250   // top 250 + bottom 250, Russell universes only

// Keys come from `constituentIndexMaps` in utils/IndexMappings.js.
const CAPPED_UNIVERSES = new Set(['r2000', 'rmicro'])

/**
 * Reduce a Russell universe to its extremes. `heat_map` arrives already sorted
 * by `y` descending, so the strongest and weakest movers are just the two ends
 * of the array.
 *
 * Universes outside CAPPED_UNIVERSES pass through whole, whatever their size:
 * the cap is deliberately keyed on which index was selected, not on a length
 * threshold, so adding a mid-size universe later cannot silently start
 * truncating it.
 *
 * Returns the tiles to draw plus what was left out, for the disclosure.
 */
export const capHeatMapTiles = (rows, universe, perSide = MAX_TILES_PER_SIDE) => {
  const all = Array.isArray(rows) ? rows : []
  if (!CAPPED_UNIVERSES.has(universe) || all.length <= perSide * 2) {
    return { tiles: all, total: all.length, omitted: 0, capped: false }
  }
  return {
    tiles: [...all.slice(0, perSide), ...all.slice(-perSide)],
    total: all.length,
    omitted: all.length - perSide * 2,
    capped: true,
  }
}

export const useIndexHeatMaps = (index, initialIndexName) => {
    const [loading, setLoading] = useState(true)
    const [series, setSeries] = useState([])
    const [options, setOptions] = useState(undefined)
    const [indexUniverseData, setIndexUniverseData] = useState([])
    const [disclosure, setDisclosure] = useState(null)
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

                const {tiles, total, omitted, capped} = capHeatMapTiles(heatMapData, index)
                setSeries([{data: tiles}])
                setDisclosure(
                  capped
                    ? {
                        total,
                        omitted,
                        shown: tiles.length,
                        perSide: MAX_TILES_PER_SIDE,
                      }
                    : null
                )

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

    return { options, series, loading, indexUniverseData, disclosure }
}
