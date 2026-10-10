import { Check, FileText, PanelLeft, Upload as UploadIcon } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { FlagBanner, Pill } from '@/components/sim/atoms'
import { useFreshness } from '@/components/app/FreshnessChip'
import { pendingFile } from '@/dialogs/UploadReviewSheet'
import { dayLong } from '@/lib/format'
import { useApp } from '@/store/app'
import { cn } from '@/lib/utils'

const TYPES = [['all', 'All'], ['prices', 'Prices'], ['freight', 'Freight'], ['agro', 'Agro tests'], ['crop', 'Crop prices']] as const
const TL = { prices: 'Prices', freight: 'Freight', agro: 'Agro tests', crop: 'Crop prices' } as const

export default function Uploads() {
  const uploads = useApp((s) => s.uploads); const setUI = useApp((s) => s.setUI); const ui = useApp((s) => s.ui)
  const fresh = useFreshness()
  const [t, setT] = useState<string>('all'); const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const rows = useMemo(() => uploads.filter((u) => t === 'all' || u.type === t), [uploads, t])
  const openWith = (f?: File) => { pendingFile.current = f ?? null; setUI({ uploadReviewOpen: true }) }
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto" onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) openWith(f) }}>
      <div className="hidden h-14 shrink-0 items-center border-b px-8 md:flex"><button aria-label="Toggle sidebar" onClick={() => setUI({ sidebarOpen: !ui.sidebarOpen })} title="Show or hide the sidebar" className="rounded-md border bg-background p-2 text-foreground hover:bg-accent"><PanelLeft className="size-4" /></button></div>
      <div className="mx-auto w-full max-w-[1280px] space-y-6 px-4 py-8 sm:px-8">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1"><h1 className="text-[28px] font-semibold leading-9 tracking-tight">Uploads</h1><p className="mt-1 text-sm text-muted-foreground">Data the simulator reads. Freshness is checked on every run.</p></div>
          <Button className="gap-1.5" onClick={() => input.current?.click()}><UploadIcon className="size-4" />Upload document</Button>
          <input ref={input} type="file" hidden accept=".xlsx,.csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) openWith(f); e.target.value = '' }} />
        </div>
        {fresh.d1 && <FlagBanner flag={{ ...fresh.d1, title: `${fresh.d1.title}. ${fresh.d1.detail ?? ''}`, detail: undefined, action: { label: 'Upload newer prices', kind: 'dismiss' } }} onAction={() => openWith()} />}
        <button onClick={() => openWith()} className={cn('flex h-[84px] w-full items-center justify-center gap-3.5 rounded-xl border border-dashed bg-muted/60 transition-colors hover:bg-accent', drag && 'border-foreground bg-accent')}>
          <UploadIcon className="size-5" /><span className="text-left"><span className="block text-sm font-medium">Drop a file here, or choose one</span><span className="block text-[13px] text-muted-foreground">.xlsx or .csv · Prices, freight, agro tests, crop prices — the type is detected automatically</span></span>
        </button>
        <ToggleGroup type="single" value={t} onValueChange={(v) => v && setT(v)} variant="outline" size="sm" className="w-fit">
          {TYPES.map(([k, l]) => <ToggleGroupItem key={k} value={k} className="px-3 text-sm">{l} {uploads.filter((u) => k === 'all' || u.type === k).length}</ToggleGroupItem>)}
        </ToggleGroup>
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="tbl tbl-flush w-full min-w-[860px] text-sm" data-testid="uploads-table">
            <thead><tr className="border-b bg-muted/60 text-[13px] text-muted-foreground"><th className="px-3 py-2.5 text-left font-medium">Filename</th><th className="px-3 py-2.5 text-left font-medium">Type</th><th className="px-3 py-2.5 text-left font-medium">Upload date</th><th className="px-3 py-2.5 text-left font-medium">File date</th><th className="px-3 py-2.5 text-left font-medium">Data through</th><th className="px-3 py-2.5 text-left font-medium">Status</th></tr></thead>
            <tbody>
              {rows.map((u) => {
                const behind = fresh.behind[u.id]
                return (
                  <tr key={u.id} className="border-b last:border-0">
                    <td className="max-w-[420px] px-3 py-3"><div className="flex items-center gap-2"><FileText className="size-4 shrink-0 text-muted-foreground" /><span className="truncate font-medium" title={u.name}>{u.name}</span></div></td>
                    <td className="px-3 py-3"><Pill>{TL[u.type]}</Pill></td>
                    <td className="num px-3 py-3 text-muted-foreground">{dayLong(u.uploadedAt)}</td>
                    <td className="num px-3 py-3 text-muted-foreground">{dayLong(u.fileDate)}</td>
                    <td className="num px-3 py-3 font-medium">{dayLong(u.dataThrough)}</td>
                    <td className="px-3 py-3">{behind ? <Pill tone="warning"><span className="size-1.5 rounded-full bg-warning-dot" />{behind} months behind freight</Pill> : <Pill><Check className="size-3" />Current</Pill>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
