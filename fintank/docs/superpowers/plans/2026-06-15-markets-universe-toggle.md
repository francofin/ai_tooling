# Markets Universe Pill Toggle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a centered pill toggle group to `src/pages/markets.js` so users can switch between Equity, Crypto, and ETF universes.

**Architecture:** The state machine (`universeData`, `universeDataLabel`, `useEffect`) is already fully implemented. This plan only adds the `ButtonGroup` UI — one import change and one JSX block in the hero section.

**Tech Stack:** Next.js Pages Router, React Bootstrap (`ButtonGroup`, `Button`)

---

### Task 1: Add the Universe Pill Toggle to the Hero Section

**Files:**
- Modify: `src/pages/markets.js`

- [ ] **Step 1: Add `ButtonGroup` to the react-bootstrap import**

Open `src/pages/markets.js`. The current import (lines 2–12) is:

```js
import {
  Container,
  Row,
  Col,
  Card,
  Badge,
  InputGroup,
  Breadcrumb,
  Form,
  Button,
} from "react-bootstrap"
```

Add `ButtonGroup` to the list:

```js
import {
  Container,
  Row,
  Col,
  Card,
  Badge,
  InputGroup,
  Breadcrumb,
  Form,
  Button,
  ButtonGroup,
} from "react-bootstrap"
```

- [ ] **Step 2: Render the pill toggle below the `<h1>` in the hero section**

The hero section currently ends at (around line 88):

```jsx
<h1 className="hero-heading">{universeDataLabel}</h1>
```

Add the `ButtonGroup` immediately after it:

```jsx
<h1 className="hero-heading">{universeDataLabel}</h1>

<div className="d-flex justify-content-center mt-3">
  <ButtonGroup>
    {UNIVERSE_DATA_OPTIONS.map((option) => (
      <Button
        key={option.value}
        variant={universeData === option.value ? "primary" : "outline-primary"}
        onClick={() => setUniverseData(option.value)}
      >
        {option.label}
      </Button>
    ))}
  </ButtonGroup>
</div>
```

- [ ] **Step 3: Start the dev server and verify visually**

```bash
npm run dev
```

Open http://localhost:8020/markets in the browser. Confirm:
- Three buttons (Equity, Crypto, ETF) appear centered below the heading
- The active button is filled blue; the others are outlined
- Clicking each button updates the heading and swaps the card grid data
- Default selection on page load is Equity (filled)

- [ ] **Step 4: Commit**

```bash
git add src/pages/markets.js
git commit -m "feat: add universe pill toggle to markets page hero"
```
