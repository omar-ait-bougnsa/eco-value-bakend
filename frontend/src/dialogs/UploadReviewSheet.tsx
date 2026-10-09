import { Check, FileText, TriangleAlert, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Pill, SourceChip } from '@/components/sim/atoms'
import { api, report, type UploadDetection } from '@/lib/api'
import { dayLong } from '@/lib/format'
import { useApp } from '@/store/app'

export const pendingFile: { current: File | null } = { current: null }

type Found = UploadDetection

export function UploadReviewSheet() {
  const open = useApp((s) => s.ui.uploadReviewOpen); const setUI = useApp((s) => s.setUI); const add = useApp((s) => s.addUpload)
  const [stage, setStage] = useState<'pick' | 'reading' | 'found'>('pick')
  const [found, setFound] = useState<Found | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const [reading, setReading] = useState('')
  const [picked, setPicked] = useState<File | null>(null) // the built-in sample has no content, so it is not kept
  const start = async (file: File, sample = false) => {
    setStage('reading'); setFound(null); setReading(file.name); setPicked(sample ? null : file)
    try { setFound(await api.detectUpload(file)); setStage('found') } catch (e) { report(e); setStage('pick') }
  }
  useEffect(() => {
    if (!open) return
    if (pendingFile.current) { const f = pendingFile.current; pendingFile.current = null; void start(f) } else { setStage('pick'); setFound(null) }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const close = () => setUI({ uploadReviewOpen: false })
  const use = async () => {
    if (!found) return
    let saved
    try { saved = await add({ name: found.name, type: found.type, fileDate: found.fileDate, dataThrough: found.dataThrough, detail: found.series }) } catch (e) { report(e); return }
    // The file also goes to the knowledge base, so the agent can cite it. The data is in use either way.
    if (picked) api.indexDocument(picked, saved.id).catch(report)
    close(); toast('Data added', { description: found.resolves ? 'The prices/freight discrepancy flag is resolved.' : found.name })
  }
  return (
    <Sheet open={open} onOpenChange={(o) => !o && close()}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[480px]">
        <SheetDescription className="sr-only">Review an uploaded file before using it</SheetDescription>
        <div className="flex h-16 shrink-0 flex-col justify-center border-b pl-5 pr-14"><SheetTitle className="text-base">{stage === 'found' ? 'What I found' : 'Upload document'}</SheetTitle><p className="text-[13px] text-muted-foreground">{stage === 'found' ? 'Review before this data is used in simulations' : 'The type is detected automatically'}</p></div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {stage === 'pick' && (
            <div className="space-y-3">
              <button onClick={() => input.current?.click()} className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center hover:bg-accent"><Upload className="size-5" /><span className="text-sm font-medium">Choose a file</span><span className="text-[13px] text-muted-foreground">.xlsx or .csv · Prices, freight, agro tests, crop prices</span></button>
              <input ref={input} type="file" accept=".xlsx,.xls,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void start(f) }} />
              <div className="text-center text-[13px] text-muted-foreground">or try a sample</div>
              <Button variant="outline" className="w-full justify-start gap-2" onClick={() => void start(new File([new Uint8Array(48 * 1024)], 'argus-fob-morocco-30-09-2026.xlsx'), true)}><FileText className="size-4" />argus-fob-morocco-30-09-2026.xlsx</Button>
            </div>
          )}
          {stage === 'reading' && <p className="text-sm text-muted-foreground">Reading “{reading}”…</p>}
          {found && stage === 'found' && (
            <>
              <div className="flex items-center gap-3 rounded-[10px] border p-3"><FileText className="size-5" /><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{found.name}</div><div className="text-[13px] text-muted-foreground">{found.size}</div></div><Pill><Check className="size-3" />Read</Pill></div>
              {stage === 'found' && (
                <>
                  <div className="overflow-hidden rounded-[10px] border text-sm">
                    {([['Detected type', found.typeLabel, false], ['File date', dayLong(found.fileDate), true], ['Data through', `${dayLong(found.dataThrough)} (last row)`, true], ['Series', found.series, false]] as const).map(([k, v, mono]) => (
                      <div key={k} className="flex gap-3 border-b px-3.5 py-2.5"><span className="w-[110px] shrink-0 text-muted-foreground">{k}</span><span className={`font-medium ${mono ? 'num' : ''}`}>{v}</span></div>))}
                    <div className="flex gap-3 px-3.5 py-2.5"><span className="w-[110px] shrink-0 text-muted-foreground">Affects</span><span className="flex flex-wrap gap-1.5">{found.affects.map((a) => <SourceChip key={a}>{a}</SourceChip>)}</span></div>
                  </div>
                  {found.resolves && <div className="flex items-start gap-2.5 rounded-lg bg-muted p-3"><Check className="mt-0.5 size-4" /><div><div className="text-sm font-medium">Resolves a flag</div><div className="text-[13px] text-muted-foreground">With this file, prices and freight are close enough in date: the discrepancy warning goes away.</div></div></div>}
                  {found.warn && <div className="flex items-start gap-2.5 rounded-lg bg-warning-bg p-3 text-warning-fg"><TriangleAlert className="mt-0.5 size-4" /><div><div className="text-sm font-medium">{found.warn.split('. ')[0]}</div><div className="text-[13px] opacity-80">{found.warn.split('. ').slice(1).join('. ')}</div></div></div>}
                </>
              )}
            </>
          )}
        </div>
        <div className="flex h-16 shrink-0 items-center justify-end gap-2 border-t px-5"><Button variant="ghost" onClick={close}>Cancel</Button><Button onClick={use} disabled={stage !== 'found'}>Use this data</Button></div>
      </SheetContent>
    </Sheet>
  )
}
