import React from "react"
import { faBell } from "@fortawesome/free-solid-svg-icons"
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
      title: "Create Alerts",
    },
  }
}

const CreateAlerts = () => (
  <ProfileLayout>
    <ComingSoon
      icon={faBell}
      title="Create Alerts"
      description="Get notified when a symbol crosses the levels you set."
      plannedItems={[
        "Price and percentage-move triggers",
        "Delivery by email or in-app",
        "Manage and pause existing alerts",
      ]}
    />
  </ProfileLayout>
)

export default CreateAlerts
