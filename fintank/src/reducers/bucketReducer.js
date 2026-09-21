// The shape src/pages/rankings/[slug].js actually reads: the holdings keyed by
// bucket, the ordered bucket keys, and the three labels. The initial state used
// to be the unrelated screener shape ({stocks, query}), so a store that had
// never seen a 'showbucket' dispatch — every /rankings/<slug> tab opened by
// window.open() before redux-persist rehydrates — handed the page an object
// with no bucketKeys at all.
const initState = {
    bucketData: {},
    bucketKeys: [],
    bucketName: '',
    indexName: '',
    factorName: '',
}

const bucketReducer = (state = initState, action) => {


    if(action.type ==='showbucket'){
        // Still a full replace, as before, but normalised so consumers can rely
        // on the types even when the dispatch was made with a half-loaded screen.
        const payload = action.payload || {}
        return {
            bucketData: payload.bucketData || {},
            bucketKeys: Array.isArray(payload.bucketKeys) ? payload.bucketKeys : [],
            bucketName: payload.bucketName || '',
            indexName: payload.indexName || '',
            factorName: payload.factorName || '',
        }
    } else {
        return state
    }


}


export default bucketReducer
