import AccountDetailFeature from '@/components/account/account-detail-feature'
import { SOLANA_ENABLED } from '@/components/solana/solana-enabled'
import { SolanaDisabledNotice } from '@/components/solana/solana-disabled-notice'

export default function Page() {
  if (!SOLANA_ENABLED) {
    return <SolanaDisabledNotice feature="Account detail" />
  }
  return <AccountDetailFeature />
}
