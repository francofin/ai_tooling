import Document, { Html, Head, Main, NextScript } from "next/document"
import footerContent from "@data/footer.json"
import { WALLET_NOISE_FILTER_SCRIPT } from "@/lib/wallet-noise-filter"
class MyDocument extends Document {
  static async getInitialProps(ctx) {
    const initialProps = await Document.getInitialProps(ctx)
    return { ...initialProps }
  }

  render() {
    return (
      <Html lang="en">
        <Head>
          {/* Must run before Next's client bundle installs its error handlers. */}
          <script dangerouslySetInnerHTML={{ __html: WALLET_NOISE_FILTER_SCRIPT }} />
          <link rel="icon" type="image/svg+xml" href="/content/svg/fintank-mark.svg" />
          <link rel="icon" type="image/png" sizes="32x32" href="/favicon.png" />
          <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
          <link
            href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Poppins:ital,wght@0,300;0,400;0,700;1,400&display=swap"
            rel="stylesheet"
          />
          <meta
            name="description"
            content="Financial News, Stock and Capital Makrkets Research, research individual equitites and stock universes to help you better manage your portfolio."
          />
          <meta
            property="og:image"
            content="/images/homepageImages/fintank-og.png"
          />
        </Head>
        <body>
          <Main />
          <NextScript />
        </body>
      </Html>
    )
  }
}

export default MyDocument
