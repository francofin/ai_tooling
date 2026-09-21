import React, { useMemo } from "react"
import Layout from "@componentsLegacy/Layout"
import { DjangoAuthProvider } from '@context/authContext';
// import { AccountContextProvider } from "@context/accountContext";
import { Provider } from "react-redux";
import { persistStore } from "redux-persist";
import { wrapper } from "@/store";
import { PersistGate } from 'redux-persist/integration/react'
import "swiper/css/bundle"
// swiper core styles
import "swiper/css"

// modules styles
import "swiper/css/pagination"
import "swiper/css/navigation"

import "@fortawesome/fontawesome-svg-core/styles.css"
import "../scss/style.default.scss"

const App = ({ Component, pageProps, ...rest }) => {
  const { store, props } = wrapper.useWrappedStore(rest);

  // The persistor MUST be built from this exact store. It used to be created
  // in store.js from a separate makeStore() call, so it persisted a store no
  // component rendered from -- see the note there.
  const persistor = useMemo(() => persistStore(store), [store]);

  return (
      <Provider store={store}>
        <PersistGate loading={null} persistor={persistor}>
          <DjangoAuthProvider>
            <Layout {...pageProps}>
              <Component {...pageProps} />
            </Layout>
          </DjangoAuthProvider>
        </PersistGate>
      </Provider>
  )
}


// export default wrapper.withRedux(App);
export default App;
