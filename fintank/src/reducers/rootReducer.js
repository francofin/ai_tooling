import { combineReducers } from "redux";
import fmpReducer from './fmp';
import idxReducer from "./idxData";
import bucketReducer from "./bucketReducer";

const rootReducer = combineReducers({
    // fmp: fmpReducer,
    idx: idxReducer,
    bucket:bucketReducer
})


export default rootReducer;