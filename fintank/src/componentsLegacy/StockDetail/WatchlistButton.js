import React from 'react';
import Link from 'next/link';
import { Button, Spinner } from 'react-bootstrap';
import { useWatchlistEntry } from '@hooks/useWatchlistEntry';

/**
 * "+ Add to Watchlist" beside a symbol's title.
 *
 * Renders nothing until the membership check resolves, so it never flashes
 * "Add" for something already saved.
 */
const WatchlistButton = ({ symbol }) => {
  const { onWatchlist, signedOut, loading, saving, error, toggle } = useWatchlistEntry(symbol);

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

  return (
    <div>
      <Button
        variant={onWatchlist ? 'primary' : 'outline-primary'}
        size="sm"
        onClick={toggle}
        disabled={saving}
        aria-pressed={onWatchlist}
      >
        <span className="me-1">{onWatchlist ? '✓' : '+'}</span>
        {onWatchlist ? 'On Watchlist' : 'Add to Watchlist'}
      </Button>
      {error && <div className="text-danger text-sm mt-1">{error}</div>}
    </div>
  );
};

export default WatchlistButton;
