/**
 * Master switch for the Solana / wallet-adapter UI.
 *
 * The wallet stack in this app is currently inert: `SolanaProvider` (which owns
 * `WalletProvider` / `ConnectionProvider` / `WalletModalProvider`) is never
 * mounted, but components that call `useWallet()` and `useConnection()` render
 * on every App Router route. The adapter responds to a missing context by
 * emitting a `console.error` per property read, which is pure noise.
 *
 * Rather than mount the providers -- which would initialize the Wallet Standard
 * registry and actively invite wallet extensions to run their connection
 * handshakes -- we simply don't render the Solana UI until it's wanted.
 *
 * Flip it on with `NEXT_PUBLIC_ENABLE_SOLANA=true` in `.env`.
 */
export const SOLANA_ENABLED = process.env.NEXT_PUBLIC_ENABLE_SOLANA === 'true'
