const initState = {"stocks":[], "query":{}}

const bucketReducer = (state = initState, action) => {
    
    
    if(action.type ==='showbucket'){
        // console.log(action)
        return action.payload
        // let newState = [...action?.payload?.screenResults]
        // if(action.payload.screenResults){
        //    return action.payload.screenResults
        // }
        // return state
    } else {
        return state
    }

    
}


export default bucketReducer