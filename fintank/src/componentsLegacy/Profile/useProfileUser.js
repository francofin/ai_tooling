import { useContext } from "react"
import { DjangoAuthContext } from "@context/authContext"

// `placehold.co` is already whitelisted in next.config.ts.
export const AVATAR_FALLBACK = "https://placehold.co/300x300?text=Avatar"

/**
 * Derives the display fields the profile section needs from the auth context,
 * so the layout and the page content can't drift apart.
 */
export default function useProfileUser() {
  const { user, userProfile, loading } = useContext(DjangoAuthContext)

  if (!user) {
    return { user: null, userProfile, loading, fullName: "", handle: "", avatar: AVATAR_FALLBACK }
  }

  return {
    user,
    userProfile,
    loading,
    fullName: [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username,
    handle: user.username || user.email,
    avatar: userProfile?.avatar_url || user.avatar_url || AVATAR_FALLBACK,
  }
}
