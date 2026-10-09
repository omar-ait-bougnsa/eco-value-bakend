import { useNavigate } from 'react-router-dom'
import { defaultRunInput, useApp } from '@/store/app'
import { runEngine } from '@/engine/run'
import { dayLong, dayShort } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Dot } from '@/components/sim/atoms'

export function useFreshness() {
  const uploads = useApp((s) => s.uploads); const products = useApp((s) => s.products); const params = useApp((s) => s.params); const snapshots = useApp((s) => s.snapshots)
  const latest = [...uploads].sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt))[0]
  const through = [...uploads].filter((u) => u.type === 'prices' || u.type === 'freight').sort((a, b) => b.dataThrough.localeCompare(a.dataThrough))[0]
  const flags = runEngine(defaultRunInput(params), { products, snapshots, uploads, params }).flags
  const d1 = flags.find((f) => f.code === 'D1'); const d2 = flags.find((f) => f.code === 'D2')
  return { latest, through, warn: !!(d1 || d2), d1, d2 }
}

export function FreshnessChip({ className }: { className?: string }) {
  const f = useFreshness(); const nav = useNavigate()
  if (!f.latest) return null
  return (
    <button onClick={() => nav('/uploads')} className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent', className)} title="Open Uploads">
      <Dot tone={f.warn ? 'warning' : 'fg'} />
      Latest upload · {dayLong(f.latest.uploadedAt)}{f.through ? ` · Data through ${dayShort(f.through.dataThrough)}` : ''}
    </button>
  )
}
