import { Check, ChevronDown, Clock, Copy, Download, FileText, FileType2, Pin, PanelLeft, PanelRightClose, Sheet as SheetIcon, SlidersHorizontal, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { exportMarkdown, exportPdf, exportXlsx } from '@/lib/export'
import { dayShort, timeShort } from '@/lib/format'
import { useApp, useReferences } from '@/store/app'
import type { PinAxis, Tab } from '@/store/types'
import { METHOD_LABEL } from '@/engine/run'
import { cn } from '@/lib/utils'
import { Pill, bannerAction } from './atoms'
import { chipTrigger } from './PivotBar'
import { openHypotheses } from './flag-actions'
import type { SimData } from './sim-context'

const TABS: [Tab, string][] = [['costing', 'Costing'], ['pricing', 'Pricing'], ['margin', 'Margin'], ['overview', 'Overview']]

export function SimHeader({ data, onToggleAsk, askOpen }: { data: SimData; onToggleAsk: () => void; askOpen: boolean }) {
  const { sim, run, input, ctx, derived, derivedLabel } = data
  const v = sim.view
  const setView = useApp((s) => s.setView); const setUI = useApp((s) => s.setUI); const ui = useApp((s) => s.ui)
  const compareWith = ui.compareWith
  const refs = useReferences()
  const title = sim.title.replace(/ · .*/, '')
  const products = input.productIds.map((id) => ctx.products.find((p) => p.id === id)!)
  return (
    <div className="shrink-0">
      <div className="flex h-14 items-center gap-2 border-b px-4 sm:px-8">
        <button aria-label="Toggle sidebar" onClick={() => setUI({ sidebarOpen: !ui.sidebarOpen })} title="Show or hide the sidebar" className="hidden rounded-md border bg-background p-2 text-foreground hover:bg-accent md:block"><PanelLeft className="size-4" /></button>
        <nav className="hidden min-w-0 items-center gap-2 text-sm sm:flex"><Link to="/" className="text-muted-foreground hover:text-foreground">Simulations</Link><span className="text-subtle">/</span><span className="truncate font-medium">{title}</span></nav>
        <span className="flex-1" />
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setUI({ memoOpen: true })}><FileText className="size-3.5" /><span className="hidden sm:inline">Memo</span></Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="gap-1.5"><Download className="size-3.5" /><span className="hidden sm:inline">Export</span><ChevronDown className="size-3" /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => { exportPdf(title, run, ctx); toast('Memo exported as PDF') }}><FileType2 className="size-4" />Memo as PDF</DropdownMenuItem>
            <DropdownMenuItem onClick={() => { exportMarkdown(title, run, ctx); toast('Memo exported as Markdown') }}><Copy className="size-4" />Memo as Markdown</DropdownMenuItem>
            <DropdownMenuItem onClick={() => { exportXlsx(title, run, ctx); toast('Numbers exported as .xlsx') }}><SheetIcon className="size-4" />Numbers as .xlsx</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {/* Solid while the panel is closed, as the way in; quiet once it is open, when it is the way out. */}
        <Button size="sm" variant={askOpen ? 'outline' : 'default'} className="gap-1.5" onClick={onToggleAsk} aria-expanded={askOpen} aria-controls="ask-ai" title={`${askOpen ? 'Hide' : 'Open'} the AI panel (⌘/)`} data-testid="ask-toggle">
          {askOpen ? <PanelRightClose className="size-3.5" /> : <Sparkles className="size-3.5" />}<span className="hidden sm:inline">{askOpen ? 'Hide AI' : 'Ask AI'}</span>
        </Button>
      </div>
      {derived && (
        <div className="flex items-center gap-2.5 border-b bg-muted px-4 py-2.5 text-sm sm:px-8" data-testid="derived-banner">
          <Clock className="size-3.5" /><span className="font-medium">Viewing under {derivedLabel}</span><span className="hidden text-muted-foreground sm:inline">{data.error ? `Could not calculate this view: ${data.error}` : data.loading ? 'Calculating…' : 'Derived view — not a new run'}</span><span className="flex-1" />
          <button className={bannerAction} onClick={() => setView(sim.id, { period: { from: run.input.periodFrom, to: run.input.periodTo }, ref: run.input.referenceId })}>Back to the run’s period</button>
        </div>
      )}
      {compareWith && (
        <div className="flex items-center gap-2.5 border-b bg-muted px-4 py-2.5 text-sm sm:px-8" data-testid="compare-banner">
          <Clock className="size-3.5" /><span className="font-medium">Comparing v{run.version} with v{compareWith}</span><span className="flex-1" />
          <button className={bannerAction} onClick={() => setUI({ compareWith: null })}>Exit compare</button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2 px-4 pb-4 pt-4 sm:px-8">
        <h1 className="text-[28px] font-semibold leading-9 tracking-tight">{title}</h1>
        <Popover>
          <PopoverTrigger asChild>
            <button className="inline-flex h-8 items-center gap-1.5 rounded-md border bg-background px-2.5 font-mono text-sm font-medium hover:bg-accent" title="Switch version" data-testid="version-chip">v{run.version}<ChevronDown className="size-3.5" /></button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[340px] p-1.5">
            {[...sim.runs].reverse().map((r) => (
              <button key={r.id} onClick={() => setView(sim.id, { version: r.version })} className={cn('flex w-full items-start gap-2.5 rounded-lg p-2.5 text-left hover:bg-accent', r.version === run.version && 'bg-accent')}>
                <Pill tone={r.version === run.version ? 'solid' : 'default'} className="font-mono">v{r.version}</Pill>
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{r.summary}</span><span className="block text-[13px] text-muted-foreground">{r.createdBy === 'agent' ? 'Agent' : 'You'} · {dayShort(r.createdAt)} {timeShort(r.createdAt)}</span></span>
                {r.version === run.version && <Check className="size-3.5" />}
              </button>
            ))}
            {sim.runs.length > 1 && (<><div className="my-1 h-px bg-border" /><button onClick={() => setUI({ compareWith: run.version > 1 ? run.version - 1 : 2 })} className="flex w-full items-center gap-2 rounded-lg p-2.5 text-sm font-medium hover:bg-accent"><Copy className="size-3.5" />Compare with v{run.version > 1 ? run.version - 1 : 2}</button></>)}
          </PopoverContent>
        </Popover>
        <button onClick={() => openHypotheses()} className="inline-flex h-8 items-center gap-1.5 rounded-md border bg-background px-3 text-sm font-medium hover:bg-accent" data-testid="open-hypotheses"><SlidersHorizontal className="size-3.5" />Hypotheses</button>
        <span className="flex-1" />
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex h-[30px] items-center rounded-md border pl-2.5"><span className="text-[13px] text-muted-foreground">Compare to</span>
            <Select value={v.ref} onValueChange={(c) => setView(sim.id, { ref: c as typeof v.ref })}><SelectTrigger className={chipTrigger} aria-label="Compare to"><SelectValue /></SelectTrigger><SelectContent>{refs.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select></div>
          {(() => { const n = data.out.flags.filter((f) => f.severity !== 'resolved').length; return n ? <Pill tone="warning"><span className="size-1.5 rounded-full bg-warning-dot" />{n} flags</Pill> : null })()}
        </div>
      </div>
      <div className="flex gap-5 overflow-x-auto overflow-y-hidden border-b px-4 sm:px-8" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={v.tab === id} onClick={() => setView(sim.id, { tab: id })} className={cn('-mb-px whitespace-nowrap border-b-2 py-2.5 text-sm transition-colors', v.tab === id ? 'border-foreground font-semibold' : 'border-transparent font-medium text-muted-foreground hover:text-foreground')}>{label}</button>
        ))}
      </div>
    </div>
  )
}
