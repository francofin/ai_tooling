import { useMemo } from 'react';

/**
 * Keep only the series that actually carry data.
 *
 * The price parquets ship every metric column whether or not it was computable
 * for the symbol's history -- 200_day_ma is all-null across the current data,
 * for instance. Charting those produces empty axes and misleading legends, so
 * the components ask for what's available rather than hardcoding exclusions.
 * Columns light up on their own once the underlying data is backfilled.
 */
export const hasData = (values) =>
  Array.isArray(values) && values.some((v) => v !== null && v !== undefined);

export const useAvailableSeries = (series, requested) =>
  useMemo(() => {
    if (!series) return [];
    return requested.filter((key) => hasData(series[key]));
  }, [series, requested]);
