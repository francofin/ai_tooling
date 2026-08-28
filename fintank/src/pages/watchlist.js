import React from "react"
import { faEye } from "@fortawesome/free-solid-svg-icons"
import ProfileLayout from "@componentsLegacy/Profile/ProfileLayout"
import ComingSoon from "@componentsLegacy/Profile/ComingSoon"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Watchlist",
    },
  }
}

const Watchlist = () => (
  <ProfileLayout>
    <ComingSoon
      icon={faEye}
      title="Watchlist"
      description="Track the tickers you care about in one place."
      plannedItems={[
        "Symbols saved through the existing /addtowatchlist/ endpoint",
        "Live price, day change and volume per holding",
        "Remove and reorder entries",
      ]}
    />
  </ProfileLayout>
)

export default Watchlist
