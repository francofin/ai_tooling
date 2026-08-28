import useSWR from 'swr';
import { fetchStatements } from '@utils/stockApi';

/**
 * Statements are large (~180 KB per type) so they load on demand rather than
 * shipping in the page's server-rendered props. Passing a null key defers the
 * request until the section is actually opened.
 */
export const useFinancialStatements = (symbol, statementType, enabled = true) => {
  const { data, error, isLoading } = useSWR(
    enabled && symbol && statementType ? ['statements', symbol, statementType] : null,
    ([, s, type]) => fetchStatements(s, type),
    { revalidateOnFocus: false }
  );

  return {
    rows: data?.data || null,
    universe: data?.universe || null,
    error,
    isLoading,
  };
};
