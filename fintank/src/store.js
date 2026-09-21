import { legacy_createStore as createStore, applyMiddleware } from "redux";
import { persistReducer } from "redux-persist";
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

export const makeStore = () =>
  createStore(
    persistedReducer,
    composeWithDevTools(applyMiddleware(...middleware))
  );

// next-redux-wrapper calls makeStore() itself and keeps the result on window,
// so the store the <Provider> renders from is created here and nowhere else.
// This module used to also export `theStore = makeStore()` and a persistor
// built from it -- a SECOND, independent store that nothing rendered. The
// persistor was subscribed to that orphan, so no dispatch from the UI was
// ever written to localStorage and nothing was ever rehydrated back into the
// store the app actually reads. /rankings/<slug>, which is opened in a new
// document by window.open() and depends entirely on that rehydrate, therefore
// always booted empty. The persistor is now created in _app.js from the store
// useWrappedStore() returns, so there is exactly one store and it is the one
// that gets persisted.
export const wrapper = createWrapper(makeStore);
