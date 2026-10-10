import { useNavigate } from 'react-router-dom'
import { useApp } from '@/store/app'
import { dayLong, dayShort } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Dot } from '@/components/sim/atoms'

/** Latest upload and the data-freshness flags, as the backend reports them (GET /uploads/freshness). */
export const useFreshness = () => useApp((s) => s.freshness)

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
