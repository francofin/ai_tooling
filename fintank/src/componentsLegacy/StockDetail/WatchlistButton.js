import React, { useState } from 'react';
import Link from 'next/link';
import { Button, Spinner } from 'react-bootstrap';
import { useWatchlistEntry } from '@hooks/useWatchlistEntry';

// Every label the signed-in button can show. All are rendered in the same grid
// cell and only the current one is visible, so the button is always as wide as
// the longest label. If the width changed on hover, the edge could move out from
// under the pointer, fire mouseleave, shrink back under it, and loop (flicker).
const LABELS = {
  add: { icon: '+', text: 'Add to Watchlist' },
  saved: { icon: '✓', text: 'On Watchlist' },
  remove: { icon: '✕', text: 'Remove from Watchlist' },
};

/**
 * "+ Add to Watchlist" beside a symbol's title.
 *
 * Renders nothing until the membership check resolves, so it never flashes
 * "Add" for something already saved.
 *
 * The button is a toggle. Once the symbol is saved, hovering or focusing it
 * shows what a click will do ("Remove from Watchlist") instead of only the
 * saved state, which read as a status badge rather than a button.
 */
const WatchlistButton = ({ symbol }) => {
  const { onWatchlist, signedOut, loading, saving, error, toggle } = useWatchlistEntry(symbol);
  const [armed, setArmed] = useState(false);

  if (loading) {
    return (
      <Button variant="outline-secondary" size="sm" disabled>
        <Spinner animation="border" size="sm" className="me-2" />
        Watchlist
      </Button>
    );
  }

  if (signedOut) {
    return (
      <Link href="/login" passHref legacyBehavior>
        <Button variant="outline-primary" size="sm">
          <span className="me-1">+</span> Add to Watchlist
        </Button>
      </Link>
    );
  }

  let current = 'add';
  if (onWatchlist) current = armed ? 'remove' : 'saved';
  const variant = { add: 'outline-primary', saved: 'primary', remove: 'outline-danger' }[current];
  const actionText = onWatchlist
    ? `Remove ${symbol} from your watchlist`
    : `Add ${symbol} to your watchlist`;

  return (
    <div>
      <Button
        variant={variant}
        size="sm"
        onClick={() => {
          // Drop the hover state so the new status shows straight away,
          // not "Add" under a pointer that is still over the button.
          setArmed(false);
          toggle();
        }}
        onMouseEnter={() => setArmed(true)}
        onMouseLeave={() => setArmed(false)}
        onFocus={() => setArmed(true)}
        onBlur={() => setArmed(false)}
        disabled={saving}
        aria-pressed={onWatchlist}
        aria-label={actionText}
        title={actionText}
      >
        <span style={{ display: 'inline-grid' }}>
          {Object.entries(LABELS).map(([key, { icon, text }]) => (
            <span
              key={key}
              aria-hidden={key !== current}
              style={{ gridArea: '1 / 1', visibility: key === current ? 'visible' : 'hidden' }}
            >
              <span className="me-1" aria-hidden="true">{icon}</span>
              {text}
            </span>
          ))}
        </span>
      </Button>
      {error && <div className="text-danger text-sm mt-1">{error}</div>}
    </div>
  );
};

export default WatchlistButton;
