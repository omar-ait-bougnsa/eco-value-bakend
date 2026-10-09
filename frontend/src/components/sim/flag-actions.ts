import type { NavigateFunction } from 'react-router-dom'
import type { Flag } from '@/engine/types'
import { useApp } from '@/store/app'

/** Opens the Hypotheses drawer, optionally focusing one input once the drawer has mounted. */
export function openHypotheses(key?: string) {
  useApp.getState().setUI({ hypothesesOpen: true })
  if (key) setTimeout(() => window.dispatchEvent(new CustomEvent('evs:focus-input', { detail: key })), 450)
}

export function openFlagTarget(flag: Flag, simId: string | null, nav: NavigateFunction) {
  const a = flag.action
  if (!a) return
  const s = useApp.getState()
  switch (a.kind) {
    case 'open-uploads': nav('/uploads'); break
    case 'open-product': s.setUI({ productSheetId: a.target ?? null }); nav('/products'); break
    case 'open-input': if (simId) openHypotheses(a.target); break
    case 'add-benchmark': if (simId) openHypotheses('benchmark'); break
    case 'review': if (simId) s.setView(simId, { tab: 'pricing' }); break
    default: break
  }
}
