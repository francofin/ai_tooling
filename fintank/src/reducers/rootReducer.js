import { combineReducers } from "redux";
import fmpReducer from './fmp';
import idxReducer from "./idxData";
import screeneReducer from "./screenerReducer";
import bucketReducer from "./bucketReducer";

const rootReducer = combineReducers({
    // fmp: fmpReducer,
    idx: idxReducer,
    screener:screeneReducer,
    bucket:bucketReducer
})


export default rootReducer;