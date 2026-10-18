import React from "react"
import Head from "next/head"
import NextNProgress from "@componentsLegacy/NextNProgress"
import Header from "./Header"
import Footer from "./Footer"
import { FormProvider } from "@componentsLegacy/FormContext"
import { BookingProvider } from "@componentsLegacy/BookingContext"
import SvgIcons from "@componentsLegacy/SvgIcons"
import SSRProvider from "react-bootstrap/SSRProvider"
const Layout = (pageProps) => {
  const headerProps = {
    nav: {
      classes: pageProps.nav && pageProps.nav.classes,
      fixed: pageProps.nav && pageProps.nav.fixed,
      color: pageProps.nav && pageProps.nav.color,
      light: pageProps.nav && pageProps.nav.light,
      dark: pageProps.nav && pageProps.nav.dark,
    },
    loggedUser: pageProps.loggedUser,
    headerClasses: pageProps.headerClasses,
  }
  return (
    <SSRProvider>
      <div
        style={{ paddingTop: pageProps.noPaddingTop ? "0" : "100px" }}
        className={pageProps.className}
      >
        <Head>
          <title>{pageProps.title} - Portfolio Manager</title>
          <link rel="icon" type="image/svg+xml" href="/content/svg/fintank-mark.svg" />
          <link rel="icon" type="image/png" sizes="32x32" href="/favicon.png" />
          <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
          <meta charset="UTF-8" />
        </Head>
        <NextNProgress color="#4E66F8" options={{ showSpinner: false }} />
        {!pageProps.hideHeader && <Header {...headerProps} />}
        {pageProps.listingForm || pageProps.bookingForm ? (
          <React.Fragment>
            {pageProps.listingForm && (
              <FormProvider>
                <main>{pageProps.children}</main>
              </FormProvider>
            )}
            {pageProps.bookingForm && (
              <BookingProvider>
                <main>{pageProps.children}</main>
              </BookingProvider>
            )}
          </React.Fragment>
        ) : (
          <main>{pageProps.children}</main>
        )}

        {!pageProps.hideFooter && <Footer />}
        <SvgIcons />
      </div>
    </SSRProvider>
  )
}

export default Layout
