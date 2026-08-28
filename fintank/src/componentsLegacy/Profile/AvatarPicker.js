import React, { useState } from "react"
import Image from "next/image"
import { Modal, Button, Spinner, Alert } from "react-bootstrap"
import useSWR from "swr"
import axios from "axios"

const fetcher = async (url) => {
  const res = await axios.get(url)
  return res.data
}

/**
 * Modal grid for choosing one of the preset avatars.
 *
 * The list comes from the server rather than reading the public directory, so a
 * preset deactivated in the admin disappears here without a frontend change.
 *
 * @param show     whether the modal is open
 * @param onHide   close handler
 * @param current  the avatar URL in use, so the active one can be marked
 * @param onSaved  called with the new avatar URL after a successful save
 */
const AvatarPicker = ({ show, onHide, current, onSaved }) => {
  // Only fetch once the modal has been opened at least once.
  const { data: presets, error: loadError, isLoading } = useSWR(
    show ? "/api/auth/avatar" : null,
    fetcher,
    { revalidateOnFocus: false }
  )

  const [saving, setSaving] = useState(null)
  const [saveError, setSaveError] = useState(null)

  const choose = async (preset) => {
    setSaving(preset.slug)
    setSaveError(null)
    try {
      await axios.patch("/api/auth/avatar", { preset_avatar_slug: preset.slug })
      onSaved?.(preset.url)
      onHide?.()
    } catch (error) {
      setSaveError(
        error?.response?.data?.detail || "Could not save that avatar. Please try again."
      )
    } finally {
      setSaving(null)
    }
  }

  const options = Array.isArray(presets) ? presets : []

  return (
    <Modal show={show} onHide={onHide} centered size="lg" scrollable>
      <Modal.Header closeButton>
        <Modal.Title className="fs-5">Choose your avatar</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {isLoading && (
          <div className="text-center py-4">
            <Spinner animation="border" role="status">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
          </div>
        )}

        {loadError && <Alert variant="warning">Could not load the avatar list.</Alert>}
        {saveError && <Alert variant="danger">{saveError}</Alert>}

        {!isLoading && !loadError && options.length === 0 && (
          <p className="text-muted mb-0">
            No avatars are available yet. Run <code>seed_avatar_presets</code> on the
            backend to register them.
          </p>
        )}

        <div className="avatar-picker-grid">
          {options.map((preset) => {
            const isCurrent = current && preset.url === current
            const isSaving = saving === preset.slug

            return (
              <button
                key={preset.slug}
                type="button"
                className={`avatar-picker-option${isCurrent ? " is-current" : ""}`}
                onClick={() => choose(preset)}
                disabled={saving !== null}
                aria-pressed={isCurrent || undefined}
                aria-label={preset.name}
                title={preset.name}
              >
                <Image src={preset.url} alt="" width={96} height={96} />
                {isSaving && (
                  <span className="avatar-picker-saving">
                    <Spinner animation="border" size="sm" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide} disabled={saving !== null}>
          Cancel
        </Button>
      </Modal.Footer>
    </Modal>
  )
}

export default AvatarPicker
