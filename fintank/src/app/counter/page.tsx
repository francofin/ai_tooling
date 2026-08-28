import { SOLANA_ENABLED } from '@/components/solana/solana-enabled'
import { SolanaDisabledNotice } from '@/components/solana/solana-disabled-notice'

export default async function Page() {
  if (!SOLANA_ENABLED) {
    return <SolanaDisabledNotice feature="Counter program" />
  }
  // Imported lazily and only when enabled: this module pulls in
  // `@coral-xyz/anchor`, whose `camelcase` dependency currently fails to
  // compile under this project's Babel config (`.babelrc` disables SWC).
  // A top-level import would drag that failure into every App Router route.
  const { default: CounterFeature } = await import('@/components/counter/counter-feature')
  return <CounterFeature />
}
