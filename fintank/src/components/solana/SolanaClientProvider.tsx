import dynamic from 'next/dynamic'
import React from 'react'

const SolanaProvider = dynamic(
  () => import('./solana-provider'),
  { ssr: false }
)

export function SolanaClientProvider({ children }: { children: React.ReactNode }) {
  return <SolanaProvider>{children}</SolanaProvider>
}
