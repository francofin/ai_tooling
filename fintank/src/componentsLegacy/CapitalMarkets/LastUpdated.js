import React from "react";

/**
 * Formatted in UTC off the ISO string rather than with toLocaleString: this
 * page is statically generated, so a locale/timezone-dependent string would
 * render one way on the server and another on the client and trip a hydration
 * mismatch.
 */
const formatUtc = (isoString) => {
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return null;
  const [date, time] = parsed.toISOString().split("T");
  return `${date} ${time.slice(0, 5)} UTC`;
};

const LastUpdated = ({ timestamp }) => {
  const formatted = timestamp ? formatUtc(timestamp) : null;
  if (!formatted) return null;

  return (
    <p className="text-muted fw-light small mb-0 pt-3">
      Data last updated {formatted}
    </p>
  );
};

export default LastUpdated;
