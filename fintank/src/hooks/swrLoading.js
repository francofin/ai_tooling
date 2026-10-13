/**
 * SWR here is 1.3.0, which does not return `isLoading` (added in 2.0), so any
 * caller destructuring it gets `undefined` and renders its empty state while
 * the request is still in flight.
 *
 * Wraps a raw SWR response with a derived `isLoading` that matches 2.x
 * semantics: true only while a request is enabled (non-null key) and has
 * neither data nor an error yet. A null key is idle, not loading.
 *
 * Spreading reads SWR 1's dependency-tracking getters, so the caller re-renders
 * on data, error and isValidating changes -- harmless for these hooks.
 */
export const withIsLoading = (key, swrRes) => ({
  ...swrRes,
  isLoading: key !== null && key !== undefined && !swrRes.data && !swrRes.error,
})
