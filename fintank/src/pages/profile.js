import React from "react"
import Image from "next/image"
import { Card } from "react-bootstrap"
import ProfileLayout from "@componentsLegacy/Profile/ProfileLayout"
import useProfileUser from "@componentsLegacy/Profile/useProfileUser"
import IndexHeatMap from "@componentsLegacy/Markets/IndexHeatMap"
import IndexChartPicker from "@componentsLegacy/Markets/IndexChartPicker"
import NewsFeed from "@componentsLegacy/Markets/NewsFeed"
import IndexMoversPanel from "@componentsLegacy/Markets/IndexMoversPanel"
import WatchlistPerformance from "@componentsLegacy/Markets/WatchlistPerformance"
import { useIndex } from "@hooks/UseIndex"

export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      loggedUser: true,
      title: "Profile",
    },
  }
}

// --- Building blocks -------------------------------------------------------

const PostHeader = ({ avatar, name, context, date }) => (
  <div className="d-flex align-items-center mb-3">
    <a href="#/">
      <Image src={avatar} alt="" width={50} height={50} className="rounded-circle" />
    </a>
    <div className="flex-fill ps-2">
      <div className="fw-bold">
        <a href="#/" className="text-decoration-none">{name}</a>
        {context}
      </div>
      <div className="small text-inverse text-opacity-50">{date}</div>
    </div>
  </div>
)

// Rendered under the side nav. Replaces the HUD template's bio / location /
// "People to follow" placeholders.
const SidebarExtra = () => (
  <>
    <hr className="mt-4 mb-4" />
    <IndexMoversPanel />
  </>
)

// --- Page ------------------------------------------------------------------

const Profile = () => {
  const { fullName, avatar } = useProfileUser()
  const { data: indexData } = useIndex()

  const posts = [
    {
      date: "Today",
      body: "Index performance",
      heatMap: true,
    },
    {
      date: "Today",
      body: "Index charts",
      indexChart: true,
    },
    {
      date: "Today",
      body: "Watchlist performance",
      watchlist: true,
    },
  ]

  return (
    <ProfileLayout sidebarExtra={<SidebarExtra />}>
      <div className="profile-content-container">
        <div className="row gx-4">
          <div className="col-xl-8">
            <div id="profile-posts">
              {posts.map((post, i) => (
                <Card className="mb-3" key={i}>
                  <Card.Body>
                    <PostHeader
                      avatar={avatar}
                      name={fullName}
                      context={post.context}
                      date={post.date}
                    />
                    <p>{post.body}</p>
                    {post.heatMap && (
                      <IndexHeatMap
                        quotes={indexData}
                        title={null}
                        loading={indexData == null}
                      />
                    )}
                    {post.indexChart && <IndexChartPicker />}
                    {post.watchlist && <WatchlistPerformance />}
                  </Card.Body>
                </Card>
              ))}
            </div>
          </div>

          {/* ---------------- Right rail ---------------- */}
          <div className="col-xl-4">
            <div className="desktop-sticky-top d-none d-lg-block">
              <NewsFeed />
            </div>
          </div>
        </div>
      </div>
    </ProfileLayout>
  )
}

export default Profile
