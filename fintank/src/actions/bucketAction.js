// Deliberately NOT async. An async action creator returns a Promise, which
// redux-promise only unwraps on a microtask -- so the store was still empty
// when handlBucketData() called window.open() on the very next line. Returning
// the action object directly makes the dispatch synchronous, so the bucket is
// committed (and queued for persistence) before the new tab is opened.
const bucketAction = (bucketData, bucketKeys, bucketName, indexName, factorName) => {
    return{
        type:'showbucket',
        payload:{
            bucketData,
            bucketKeys,
            bucketName,
            indexName,
            factorName
        }
    }
}


export default bucketAction
