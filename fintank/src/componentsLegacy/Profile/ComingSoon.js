import React from "react"
import Link from "next/link"
import { Card } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"

/**
 * Placeholder body for profile-section pages that are routed but not yet built.
 * Drop it for the real content once the feature lands.
 */
const ComingSoon = ({ icon, title, description, plannedItems = [] }) => (
  <div className="profile-content-container">
    <div className="profile-coming-soon">
      <div className="profile-coming-soon-icon">
        <FontAwesomeIcon icon={icon} />
      </div>
      <h3 className="mb-2">{title}</h3>
      <p className="text-inverse text-opacity-50 mb-4">{description}</p>

      {plannedItems.length > 0 && (
        <Card className="text-start mb-4 profile-coming-soon-card">
          <Card.Header className="fw-bold bg-transparent">Planned for this page</Card.Header>
          <div className="list-group list-group-flush">
            {plannedItems.map((item) => (
              <div className="list-group-item px-3" key={item}>
                <FontAwesomeIcon
                  icon={icon}
                  className="me-2 text-inverse text-opacity-25"
                  fixedWidth
                />
                {item}
              </div>
            ))}
          </div>
        </Card>
      )}

      <Link href="/profile" className="btn btn-outline-theme">
        Back to Dashboard
      </Link>
    </div>
  </div>
)

export default ComingSoon
