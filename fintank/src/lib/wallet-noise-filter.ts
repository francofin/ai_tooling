/**
 * Suppresses known-benign wallet-extension error noise.
 *
 * The motivating case:
 *
 *   Failed to connect to MetaMask
 *     at Object.connect (chrome-extension://nkbihfbeogaeaoehlefnkodbefgpgknn/scripts/inpage.js)
 *
 * MetaMask's injected `inpage.js` throws this when its own internal provider
 * handshake fails. There are no application frames in the stack and this app
 * never calls MetaMask, so it cannot be fixed from application code -- only
 * filtered.
 *
 * It arrives as an *uncaught* error, not a `console.error` call, which is why
 * patching `console` alone does not stop it: Next.js's dev overlay catches it
 * via `window.addEventListener('error', uncaughtExceptionHandler)` and renders
 * the red "Runtime" panel.
 *
 * To beat that, this must
 *   1. register its listeners BEFORE Next's client bundle registers its own, and
 *   2. call `stopImmediatePropagation()` so Next's handler never runs.
 *
 * Both are why this ships as an inline `<head>` script rather than a React
 * component -- a component mounts long after Next's handlers are installed.
 *
 * Deliberately narrow: it matches MetaMask's extension ID plus a short list of
 * exact strings. Anything else propagates untouched, so real application errors
 * still reach the overlay and the console.
 *
 * To get the noise back, remove the `<script>` tags in `src/pages/_document.js`
 * and `src/app/layout.tsx`.
 */

// MetaMask's published Chrome extension ID -- the strongest available signal
// that an error originated inside the extension rather than in this app.
export const METAMASK_EXTENSION_ID = 'nkbihfbeogaeaoehlefnkodbefgpgknn'

export const MUTED_PATTERNS = [
  'Failed to connect to MetaMask',
  'on a WalletContext without providing one',
  'on a ConnectionContext without providing one',
] as const

/**
 * Self-contained ES5 IIFE. Kept as a string so it can be inlined into <head>
 * and run before any bundle. Must not reference anything outside itself.
 */
export const WALLET_NOISE_FILTER_SCRIPT = `
(function () {
  var EXT_ID = ${JSON.stringify(METAMASK_EXTENSION_ID)};
  var PATTERNS = ${JSON.stringify(MUTED_PATTERNS)};

  function toText(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    try {
      if (value instanceof Error) return (value.message || '') + '\\n' + (value.stack || '');
      return String(value);
    } catch (e) {
      return '';
    }
  }

  function isMuted(value) {
    var text = toText(value);
    if (!text) return false;
    if (text.indexOf(EXT_ID) !== -1) return true;
    for (var i = 0; i < PATTERNS.length; i++) {
      if (text.indexOf(PATTERNS[i]) !== -1) return true;
    }
    return false;
  }

  // Uncaught errors: what the Next.js dev overlay actually renders. Registered
  // in the capture phase and before Next's bundle, so stopImmediatePropagation
  // runs ahead of its uncaughtExceptionHandler.
  window.addEventListener('error', function (event) {
    if (isMuted(event && event.error) || isMuted(event && event.message)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  window.addEventListener('unhandledrejection', function (event) {
    if (isMuted(event && event.reason)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  // The same failure is sometimes additionally logged rather than thrown.
  ['error', 'warn'].forEach(function (level) {
    var original = console[level];
    if (typeof original !== 'function') return;
    console[level] = function () {
      for (var i = 0; i < arguments.length; i++) {
        if (isMuted(arguments[i])) return;
      }
      return original.apply(console, arguments);
    };
  });

  // Exposed purely so the filter logic can be exercised in tests.
  window.__walletNoiseIsMuted = isMuted;
})();
`
