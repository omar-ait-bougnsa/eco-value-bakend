import { Copy, Download, FileType2, Sheet as SheetIcon, ThumbsDown, ThumbsUp, TriangleAlert } from 'lucide-react'
import { useMatch } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { buildMemo, memoMarkdown } from '@/agent/memo'
import { Pill, SourceChip } from '@/components/sim/atoms'
import { exportMarkdown, exportPdf, exportXlsx } from '@/lib/export'
import { useApp } from '@/store/app'

export function MemoSheet() {
  const open = useApp((s) => s.ui.memoOpen); const setUI = useApp((s) => s.setUI)
  const m = useMatch('/s/:id')
  const sim = useApp((s) => (m?.params.id ? s.sims[m.params.id] : undefined))
  const products = useApp((s) => s.products); const uploads = useApp((s) => s.uploads); const params = useApp((s) => s.params)
  const run = sim?.runs[Math.min(sim.view.version, sim.runs.length) - 1]
  const snapshots = useApp((s) => s.snapshots)
  const ctx = { products, snapshots, uploads, params }
  const memo = run ? buildMemo(run, ctx, sim!.view.product) : null
  return (
    <Sheet open={open} onOpenChange={(o) => setUI({ memoOpen: o })}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[560px]">
        <SheetDescription className="sr-only">Decision memo for the selected run</SheetDescription>
        <div className="flex h-16 shrink-0 items-center gap-2.5 border-b pl-6 pr-14">
          <SheetTitle className="text-base">Decision memo</SheetTitle>{run && <Pill className="font-mono">v{run.version}</Pill>}
          <span className="flex-1" />
          {run && memo && (<>
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { void navigator.clipboard?.writeText(memoMarkdown(memo)); toast('Memo copied') }}><Copy className="size-3.5" />Copy</Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button size="sm" variant="outline" className="gap-1.5"><Download className="size-3.5" />Export</Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => exportPdf(sim!.title, run, ctx)}><FileType2 className="size-4" />Memo as PDF</DropdownMenuItem>
                <DropdownMenuItem onClick={() => exportMarkdown(sim!.title, run, ctx)}><Copy className="size-4" />Memo as Markdown</DropdownMenuItem>
                <DropdownMenuItem onClick={() => exportXlsx(sim!.title, run, ctx)}><SheetIcon className="size-4" />Numbers as .xlsx</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu></>)}
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-6" data-testid="memo-body">
          {!memo && <p className="text-sm text-muted-foreground">Run a simulation to get a decision memo.</p>}
          {memo?.sections.map((s) => (
            <section key={s.title} className="space-y-1.5">
              <h4 className="text-[13px] font-medium uppercase tracking-wider text-muted-foreground">{s.title}</h4>
              {s.paragraphs?.map((p, i) => <p key={i} className="text-sm leading-[22px]">{p}</p>)}
              {s.items?.map((it, i) => <div key={i} className="flex items-start gap-2 text-sm"><TriangleAlert className={`mt-0.5 size-3.5 shrink-0 ${it.tone === 'warning' ? 'text-warning-fg' : 'text-muted-foreground'}`} />{it.text}</div>)}
            </section>
          ))}
          {memo && <section className="space-y-2"><h4 className="text-[13px] font-medium uppercase tracking-wider text-muted-foreground">Sources</h4><div className="flex flex-wrap gap-1.5">{memo.sources.map((s) => <SourceChip key={s}>{s}</SourceChip>)}</div></section>}
        </div>
        <div className="flex h-14 shrink-0 items-center gap-2 border-t px-6 text-[13px] text-muted-foreground">Was this memo useful?<span className="flex-1" /><Button size="sm" variant="ghost" className="gap-1.5"><ThumbsUp className="size-3.5" />Helpful</Button><Button size="sm" variant="ghost" className="gap-1.5"><ThumbsDown className="size-3.5" />Not helpful</Button></div>
      </SheetContent>
    </Sheet>
  )
}
