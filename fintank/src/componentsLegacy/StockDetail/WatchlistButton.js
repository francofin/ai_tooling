import React, { useState } from 'react';
import Link from 'next/link';
import { Button, Spinner } from 'react-bootstrap';
import { useWatchlistEntry } from '@hooks/useWatchlistEntry';

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

  const showRemove = onWatchlist && armed;
  let variant = 'outline-primary';
  let icon = '+';
  let label = 'Add to Watchlist';
  if (showRemove) {
    variant = 'outline-danger';
    icon = '✕';
    label = 'Remove from Watchlist';
  } else if (onWatchlist) {
    variant = 'primary';
    icon = '✓';
    label = 'On Watchlist';
  }
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
        <span className="me-1" aria-hidden="true">{icon}</span>
        {label}
      </Button>
      {error && <div className="text-danger text-sm mt-1">{error}</div>}
    </div>
  );
};

export default WatchlistButton;
