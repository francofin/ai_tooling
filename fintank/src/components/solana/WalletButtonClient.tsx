import dynamic from 'next/dynamic'
import React from 'react'

const WalletButton = dynamic(
  () =>
    import('./solana-provider').then((mod) => mod.WalletButton),
  { ssr: false }
)

export function WalletButtonClient() {
  return <WalletButton />
}
