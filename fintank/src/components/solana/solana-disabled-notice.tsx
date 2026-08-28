import React from 'react'

/**
 * Placeholder shown on Solana routes while `NEXT_PUBLIC_ENABLE_SOLANA` is off.
 * Keeps the routes resolving (so they 200 rather than 404) without mounting any
 * component that reads wallet context.
 */
export function SolanaDisabledNotice({ feature }: { feature: string }) {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-bold">{feature} is disabled</h1>
      <p className="mt-2 text-neutral-500">
        Solana wallet features are turned off. Set{' '}
        <code className="rounded bg-neutral-100 px-1 py-0.5 dark:bg-neutral-800">NEXT_PUBLIC_ENABLE_SOLANA=true</code>{' '}
        and restart the dev server to re-enable them.
      </p>
    </div>
  )
}
