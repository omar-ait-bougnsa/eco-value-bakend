import { ChevronRight, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useApp } from '@/store/app'
import { arrow, f2, millions, sign } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Pill, FlagIcon } from './atoms'
import { PriceLadder } from './PriceLadder'
import { leadResult } from '@/agent/memo'
import { periodLabel } from '@/engine/period'

export function ResultCard({ simId, version, compact }: { simId: string; version: number; compact?: boolean }) {
  const sim = useApp((s) => s.sims[simId])
  const setUI = useApp((s) => s.setUI)
  const setView = useApp((s) => s.setView)
  const run = sim?.runs[version - 1]
  if (!run) return null
  const r = leadResult(run)
  const top = run.output.flags.filter((f) => f.severity === 'warning' || f.severity === 'error').slice(0, 2)
  const kpis: [string, string, string, string][] = [
    ['Recommended', f2(r.anchorPrice), 'USD/t', 'Reference minus'],
    ['CGM', f2(r.cgm), 'USD/t', `${arrow((r.cgm ?? 0) - (r.cgmRef ?? 0))} ${f2(Math.abs((r.cgm ?? 0) - (r.cgmRef ?? 0)))} vs ${run.input.referenceId} ${f2(r.cgmRef)}`],
    ['Total margin', millions(r.totalMargin), 'M USD/yr', `${Math.round(run.input.marketShare * 1000) / 10}% share`],
  ]
  return (
    <div className="w-full max-w-[680px] rounded-xl border bg-card p-4" data-testid="result-card">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{sim.title.replace(/ · .*/, '')}</span>
        <Pill className="font-mono">v{version}</Pill>
        <span className="flex-1" />
        <span className="text-[13px] text-muted-foreground">{periodLabel({ from: run.input.periodFrom, to: run.input.periodTo })} · price type {run.input.priceType}</span>
      </div>
      <PriceLadder r={r} refLabel={run.input.referenceId} benchmark={run.input.benchmark} mini />
      <div className={cn('mt-2 grid gap-2.5', compact ? 'grid-cols-1' : 'grid-cols-3')}>
        {kpis.map(([l, v, u, d]) => (
          <div key={l} className="rounded-lg border p-3">
            <div className="text-[13px] text-muted-foreground">{l}</div>
            <div className="mt-0.5 flex items-end gap-1"><span className="num text-[22px] font-semibold leading-7 tracking-tight">{v}</span><span className="pb-0.5 text-[13px] text-muted-foreground">{u}</span></div>
            <div className="num text-[13px] text-muted-foreground">{d}</div>
          </div>
        ))}
      </div>
      {top.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {top.map((f) => (
            <div key={f.id} className={cn('flex items-start gap-2 rounded-lg px-3 py-2 text-sm', f.severity === 'error' ? 'bg-danger-bg text-danger-fg' : 'bg-warning-bg text-warning-fg')}>
              <FlagIcon sev={f.severity} className="mt-0.5 size-4 text-current" />
              <div><div className="font-medium">{f.title}</div>{f.detail && <div className="text-[13px] opacity-80">{f.detail}</div>}</div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setView(simId, { version }); setUI({ memoOpen: true }) }}><FileText className="size-3.5" />Memo</Button>
        <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => setView(simId, { version, tab: 'overview' })}>Overview <ChevronRight className="size-3.5" /></Button>
      </div>
    </div>
  )
}
export { sign }
