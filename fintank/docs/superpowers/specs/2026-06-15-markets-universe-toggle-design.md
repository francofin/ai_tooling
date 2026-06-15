# Markets Page — Universe Pill Toggle

**Date:** 2026-06-15
**Status:** Approved

## Summary

Add a centered pill toggle group to the top of the markets page (`src/pages/markets.js`) so users can switch between the Equity, Crypto, and ETF universes.

## Context

The data-switching logic is already fully implemented:

- `UNIVERSE_DATA_OPTIONS` array defines the three universes (`equity`, `crypto`, `etf`)
- `universeData` / `universeDataLabel` state tracks the active selection
- A `useEffect` watches `universeData` and swaps `allIndexData` between `indexData`, `etfData`, and `cryptoData`
- The `<h1>` already renders `universeDataLabel` as the page heading

The only missing piece is a UI control to drive `setUniverseData`.

## Design

### Component

A Bootstrap `ButtonGroup` containing three `Button` components, one per entry in `UNIVERSE_DATA_OPTIONS`.

- **Active button:** `variant="primary"`
- **Inactive buttons:** `variant="outline-primary"`
- Clicking a button calls `setUniverseData(option.value)`

### Placement

Inside the existing hero `<section>`, directly below the `<h1 className="hero-heading">`, centered via `text-center` or `d-flex justify-content-center`.

### Imports needed

`ButtonGroup` from `react-bootstrap` (not yet imported in the file).

## Scope

**One file only:** `src/pages/markets.js`

- Add `ButtonGroup` to the existing `react-bootstrap` import
- Render the `ButtonGroup` below the `<h1>` in the hero section

No new components, no new hooks, no backend changes.
