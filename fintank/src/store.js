import { legacy_createStore as createStore, applyMiddleware } from "redux";
import { persistStore, persistReducer } from "redux-persist";
import thunk from "redux-thunk";
import reduxPromise from "redux-promise";
import { composeWithDevTools } from "redux-devtools-extension";
import { createWrapper } from "next-redux-wrapper";
import rootReducer from "./reducers/rootReducer";
import storage from "redux-persist/lib/storage";

const persistConfig = {
  key: "root",
  storage,
};

const middleware = [thunk, reduxPromise];

const persistedReducer = persistReducer(persistConfig, rootReducer);

const makeStore = () =>
  createStore(
    persistedReducer,
    composeWithDevTools(applyMiddleware(...middleware))
  );

export const wrapper = createWrapper(makeStore);
export const theStore = makeStore();
export const persistor = persistStore(theStore);
