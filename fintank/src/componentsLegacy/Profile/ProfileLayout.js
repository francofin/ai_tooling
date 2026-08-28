import React, { useEffect, useState } from "react"
import Image from "next/image"
import { useRouter } from "next/router"
import { Card, Container } from "react-bootstrap"
import ProfileSideNav from "./ProfileSideNav"
import AvatarPicker from "./AvatarPicker"
import useProfileUser from "./useProfileUser"

/**
 * Shared shell for every page in the /profile section.
 *
 * Owns the auth guard, the full-width frame and the sidebar (avatar, username,
 * email, side nav) so the individual pages only supply their content area.
 *
 * @param children      main content column
 * @param sidebarExtra  optional extra blocks rendered under the side nav
 */
const ProfileLayout = ({ children, sidebarExtra }) => {
  const router = useRouter()
  const { user, loading, fullName, handle, avatar } = useProfileUser()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [chosenAvatar, setChosenAvatar] = useState(null)

  // `user` is only ever set by a successful /api/auth/user call, so it is a more
  // reliable signal than `isAuthenticated` — the profile fetch clears that flag on
  // its own failure even when the user lookup succeeded.
  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login")
    }
  }, [loading, user, router])

  // Keeps the `profile-page` wrapper so the background image is already painted
  // while the user resolves — without it the section flashes white first.
  if (loading || !user) {
    return (
      <section className="profile-page py-4">
        <Container fluid className="py-5 text-center">
          <div className="spinner-border text-primary" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
        </Container>
      </section>
    )
  }

  return (
    <section className="profile-page py-4">
      <Container fluid className="px-3 px-xl-4">
        <Card className="border-0 shadow-sm">
          <Card.Body className="p-0">
            <div className="profile">
              <div className="profile-container">
                <div className="profile-sidebar">
                  <div className="desktop-sticky-top">
                    {/* `chosenAvatar` holds the pick until the profile refetches,
                        so the new image appears immediately rather than after the
                        auth context next reloads. */}
                    <button
                      type="button"
                      className="profile-img profile-img-button"
                      onClick={() => setPickerOpen(true)}
                      aria-label="Change your avatar"
                      title="Change your avatar"
                    >
                      <Image
                        src={chosenAvatar || avatar}
                        width={300}
                        height={300}
                        style={{ width: "100%", height: "100%" }}
                        alt={fullName}
                      />
                      <span className="profile-img-overlay">Change</span>
                    </button>

                    <AvatarPicker
                      show={pickerOpen}
                      onHide={() => setPickerOpen(false)}
                      current={chosenAvatar || avatar}
                      onSaved={setChosenAvatar}
                    />

                    <h4 className="mb-1">{fullName}</h4>
                    <div className="text-inverse text-opacity-50 fw-bold fs-13px">@{handle}</div>
                    <div className="text-inverse text-opacity-50 fs-13px text-break mb-3">
                      {user.email}
                    </div>

                    <ProfileSideNav />

                    {sidebarExtra}
                  </div>
                </div>

                <div className="profile-content">{children}</div>
              </div>
            </div>
          </Card.Body>
        </Card>
      </Container>
    </section>
  )
}

export default ProfileLayout
