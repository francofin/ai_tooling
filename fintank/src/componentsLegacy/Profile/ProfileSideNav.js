import React from "react"
import Link from "next/link"
import { useRouter } from "next/router"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import {
  faTableColumns,
  faIdCard,
  faAddressBook,
  faShieldHalved,
  faEye,
  faChartLine,
  faBell,
} from "@fortawesome/free-solid-svg-icons"

// Single source of truth for the profile section's navigation.
// Reorder / relabel here and every page that renders the side nav follows.
export const PROFILE_NAV_ITEMS = [
  { href: "/user-account", label: "Account info", icon: faIdCard },
  { href: "/personal-info", label: "Personal info", icon: faAddressBook },
  { href: "/security", label: "Security info", icon: faShieldHalved },
  { href: "/watchlist", label: "Watchlist", icon: faEye, built: false },
  { href: "/backtest-portfolio", label: "Backtest Portfolio", icon: faChartLine },
  { href: "/create-alerts", label: "Create Alerts", icon: faBell, built: false },
  { href: "/profile", label: "Dashboard", icon: faTableColumns },
]

const ProfileSideNav = () => {
  const router = useRouter()

  return (
    <nav className="profile-nav" aria-label="Profile sections">
      <ul className="nav flex-column">
        {PROFILE_NAV_ITEMS.map((item) => {
          const isActive = router.pathname === item.href
          return (
            <li className="nav-item" key={item.href}>
              <Link
                href={item.href}
                className={`nav-link${isActive ? " active" : ""}`}
                aria-current={isActive ? "page" : undefined}
              >
                <FontAwesomeIcon icon={item.icon} className="profile-nav-icon" fixedWidth />
                <span className="profile-nav-label">{item.label}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export default ProfileSideNav
