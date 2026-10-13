import useSWR from 'swr';
import { fetchStatements } from '@utils/stockApi';

/**
 * Statements are large (~180 KB per type) so they load on demand rather than
 * shipping in the page's server-rendered props. Passing a null key defers the
 * request until the section is actually opened.
 */
export const useFinancialStatements = (symbol, statementType, enabled = true) => {
  const key = enabled && symbol && statementType ? ['statements', symbol, statementType] : null;

  // SWR here is 1.3.0: an array key is spread into the fetcher's arguments
  // (fetcher('statements', symbol, type)), not passed as one array as in 2.x.
  // Destructuring it as an array would read the characters of 'statements'.
  // 1.3.0 also has no `isLoading`, so loading is derived, and only while the
  // request is enabled -- a null key is idle, not loading.
  const { data, error } = useSWR(key, (_, s, type) => fetchStatements(s, type), {
    revalidateOnFocus: false,
  });
  const isLoading = key !== null && !data && !error;

  return {
    rows: data?.data || null,
    universe: data?.universe || null,
    error,
    isLoading,
  };
};
