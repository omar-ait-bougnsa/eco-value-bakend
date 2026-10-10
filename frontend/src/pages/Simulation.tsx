import { useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { PanelLeft, PanelRightClose } from 'lucide-react'
import { toast } from 'sonner'
import { Thread } from '@/components/sim/Thread'
import { SimHeader } from '@/components/sim/SimHeader'
import { useSimData } from '@/components/sim/sim-context'
import { Pill, bannerAction } from '@/components/sim/atoms'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { MascotIcon } from '@/components/app/MascotIcon'
import { api, jobEnded, report, type AgentStatus } from '@/lib/api'
import { cancelJob, retryJob, sendMessage, watchJob } from '@/agent/chat'
import type { Simulation } from '@/store/types'
import { cn } from '@/lib/utils'
import { useApp } from '@/store/app'
import { useMedia } from '@/lib/hooks'
import Overview, { ComparePanel } from './tabs/Overview'
import Pricing from './tabs/Pricing'
import Costing from './tabs/Costing'
import Margin from './tabs/Margin'

const FAILED = { failed: 'The request failed', timed_out: 'The request timed out', cancelled: 'The request was cancelled' } as const

/**
 * A simulation without a run yet. What it shows is the stored state of its agent job, never a guess:
 * running (with a way to stop it), waiting for an answer, failed with the reason and Retry, or simply nothing run yet.
 */
function Pending({ sim, question }: { sim: Simulation; question: boolean }) {
  const ui = useApp((s) => s.ui); const setUI = useApp((s) => s.setUI); const prompts = useApp((s) => s.prompts)
  const job = sim.job
  const active = !!sim.busy || (!!job && !jobEnded(job))
  const failure = !active && job && job.state in FAILED ? job : null
  const state = question ? 'question' : active ? 'running' : failure ? (failure.state as keyof typeof FAILED) : 'idle'
  const examples = prompts.supported.length ? prompts.supported.map((c) => c.example) : prompts.start
  return (
    <div className="flex min-w-0 flex-1 flex-col" data-testid="sim-pending" data-state={state}>
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4 sm:px-8">
        <button aria-label="Toggle sidebar" onClick={() => setUI({ sidebarOpen: !ui.sidebarOpen })} title="Show or hide the sidebar" className="hidden rounded-md border bg-background p-2 text-foreground hover:bg-accent md:block"><PanelLeft className="size-4" /></button>
        <span className="text-sm text-muted-foreground">Simulations</span><span className="text-subtle">/</span><span className="truncate text-sm font-medium">{sim.title}</span>
      </div>
      <div className="space-y-6 px-4 py-6 sm:px-8">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[28px] font-semibold leading-9 tracking-tight">{sim.title}</h1>
          <Pill tone={failure ? 'warning' : 'default'}>{{ question: 'Waiting for your answer', running: 'Running', failed: 'Failed', timed_out: 'Timed out', cancelled: 'Cancelled', idle: 'No run yet' }[state]}</Pill>
          {state === 'running' && job && !jobEnded(job) && <Button size="sm" variant="outline" onClick={() => void cancelJob(sim.id)}>Cancel</Button>}
        </div>
        {state === 'question' && <p className="text-sm text-muted-foreground">The agent found a conflict in the sources and needs your answer in the Ask AI panel.</p>}
        {state === 'running' && (
          <>
            <p className="text-sm text-muted-foreground" aria-live="polite">The agent is working on this request. It is stopped after {job ? Math.round(job.timeoutSeconds) : '…'} seconds at most, and this page then says why.</p>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px] rounded-[10px]" />)}</div>
            <Skeleton className="h-[190px] rounded-xl" />
          </>
        )}
        {failure && (
          <div className="max-w-[640px] space-y-3 rounded-xl border bg-card p-5" role="alert" data-testid="job-failure">
            <div className="text-base font-semibold">{FAILED[failure.state as keyof typeof FAILED]}</div>
            <p className="text-sm">{failure.error ?? 'No reason was recorded.'}</p>
            <p className="font-mono text-[12px] text-muted-foreground">Job {failure.id}{failure.failureCode ? ` · ${failure.failureCode}` : ''}</p>
            <div className="flex gap-2"><Button onClick={() => void retryJob(sim.id)}>Retry</Button><Button variant="outline" onClick={() => setUI({ runFormOpen: true })}>Configure run</Button></div>
          </div>
        )}
        {state === 'idle' && (
          <div className="max-w-[640px] space-y-3" data-testid="sim-idle">
            <p className="text-sm text-muted-foreground">Nothing has been priced in this simulation yet. Ask for a pricing in the Ask AI panel, or start from one of these:</p>
            <div className="flex flex-wrap gap-2">{examples.slice(0, 6).map((e) => <Button key={e} size="sm" variant="outline" onClick={() => void sendMessage(sim.id, e)}>{e}</Button>)}</div>
          </div>
        )}
      </div>
    </div>
  )
}

const ASK_MIN = 360, ASK_MAX = 480, ASK_DEFAULT = 400
const clampAsk = (w: number) => Math.min(ASK_MAX, Math.max(ASK_MIN, Math.round(w)))
const savedAskWidth = () => { try { const w = Number(localStorage.getItem('evs.askWidth')); return w ? clampAsk(w) : ASK_DEFAULT } catch { return ASK_DEFAULT } }

/** Drag the panel's left edge to resize it. Arrow keys nudge it, double-click resets. */
function ResizeHandle({ width, onChange }: { width: number; onChange: (w: number) => void }) {
  const start = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    document.body.style.userSelect = 'none'
    const move = (ev: PointerEvent) => onChange(window.innerWidth - ev.clientX)
    const stop = () => { document.body.style.userSelect = ''; el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', stop); el.removeEventListener('pointercancel', stop) }
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', stop); el.addEventListener('pointercancel', stop)
  }
  return (
    <div
      role="separator" aria-orientation="vertical" aria-label="Resize Ask AI panel" aria-valuemin={ASK_MIN} aria-valuemax={ASK_MAX} aria-valuenow={width} tabIndex={0}
      title="Drag to resize"
      onPointerDown={start}
      onDoubleClick={() => onChange(ASK_DEFAULT)}
      onKeyDown={(e) => { if (e.key === 'ArrowLeft') { e.preventDefault(); onChange(width + 16) } if (e.key === 'ArrowRight') { e.preventDefault(); onChange(width - 16) } }}
      className="group absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none outline-none"
    >
      <span className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-transparent transition-colors group-hover:bg-primary group-focus-visible:bg-primary group-active:bg-primary" />
    </div>
  )
}

/** Who answers in the chat, in the backend's own words: a model, or the rule-based assistant and why. Null while asking, 'down' when it cannot be reached. */
function useAgentStatus(idle: boolean) {
  const [status, setStatus] = useState<AgentStatus | 'down' | null>(null)
  useEffect(() => {
    let current = true
    api.agentStatus().then((s) => current && setStatus(s), () => current && setStatus('down'))
    return () => { current = false }
  }, [idle])
  return status
}

export default function Simulation() {
  const { id } = useParams()
  const sim = useApp((s) => (id ? s.sims[id] : undefined))
  const ui = useApp((s) => s.ui); const setUI = useApp((s) => s.setUI)
  const data = useSimData(sim)
  const wide = useMedia('(min-width: 1280px)')
  const [askMobile, setAskMobile] = useState(false)
  const [askWidth, setAskWidthState] = useState(savedAskWidth)
  const setAskWidth = (w: number) => { const c = clampAsk(w); setAskWidthState(c); try { localStorage.setItem('evs.askWidth', String(c)) } catch { /* width just won't be remembered */ } }
  const agent = useAgentStatus(!sim?.busy)
  // A job that is not streamed here (the page was reloaded while it ran) is followed until the server says it ended.
  const jobKey = `${sim?.id}:${sim?.job?.id}:${sim?.job?.state}:${!!sim?.busy}`
  useEffect(() => { if (id) void watchJob(id) }, [jobKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const tabKey = sim?.view.tab
  // A new tab starts at its top, so its first section title is never left scrolled out of view under the tabs.
  useEffect(() => { document.getElementById('sim-scroll')?.scrollTo({ top: 0 }) }, [tabKey, id])
  // The overlay version closes on Escape.
  useEffect(() => {
    if (wide || !askMobile) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setAskMobile(false) }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [wide, askMobile])
  if (!sim) return <Navigate to="/" replace />

  const pending = !data
  const askOpen = pending ? true : wide ? ui.askOpen : askMobile
  const toggleAsk = () => (wide ? setUI({ askOpen: !ui.askOpen }) : setAskMobile((v) => !v))
  const closeAsk = () => (wide ? setUI({ askOpen: false }) : setAskMobile(false))
  const question = sim.thread.some((m) => m.kind === 'question' && !m.answered)

  const askPanel = (
    <aside id="ask-ai" className="flex h-full w-full shrink-0 flex-col overflow-hidden border-l bg-background [&_*]:[scrollbar-color:var(--border)_transparent] [&_*]:[scrollbar-width:thin]" aria-label="Ask AI">
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b pl-4 pr-2">
        <MascotIcon size={22} />
        <div className="min-w-0">
          <h2 className="text-sm font-semibold leading-5">Ask AI</h2>
          <p className="flex items-center gap-1.5 truncate text-[12px] leading-4 text-muted-foreground" data-testid="agent-status" aria-live="polite" title={agent && agent !== 'down' ? `Understands ${agent.capabilities}` : undefined}>
            <span className={cn('size-1.5 shrink-0 rounded-full', !agent ? 'bg-border' : agent === 'down' ? 'bg-danger-dot' : agent.mode === 'llm' ? 'bg-primary' : 'bg-warning-dot')} />{!agent ? 'Checking…' : agent === 'down' ? 'Backend not reachable' : agent.mode === 'llm' ? `${agent.label} · ${agent.model}` : agent.label}
          </p>
        </div>
        <span className="flex-1" />
        {!pending && <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={closeAsk} aria-label="Close Ask AI" title="Close the AI panel (⌘/)" data-testid="ask-close"><PanelRightClose className="size-4" />Close</Button>}
      </div>
      <Thread simId={sim.id} compact ruleBased={!!agent && agent !== 'down' && agent.mode === 'script'} />
    </aside>
  )

  const tab = sim.view.tab
  const stale = data?.run.productSig ? data.run.input.productIds.filter((pid) => { const pr = data.ctx.products.find((x) => x.id === pid); return JSON.stringify([pr?.recipe, pr?.composition]) !== JSON.stringify(JSON.parse(data.run.productSig![pid])) }) : []
  return (
    <div className="flex min-h-0 flex-1">
      {pending ? <Pending sim={sim} question={question} /> : (
        <div className="flex min-w-0 flex-1 flex-col">
          <SimHeader data={data} askOpen={askOpen} onToggleAsk={toggleAsk} />
          {stale.length > 0 && (
            <div className="flex items-center gap-2.5 border-b bg-warning-bg px-4 py-2.5 text-sm text-warning-fg sm:px-8" data-testid="stale-banner">
              <span className="font-medium">Recipe changed since v{data.run.version}.</span><span className="flex-1">The product definition was edited after this run.</span>
              <button className={bannerAction} onClick={() => { useApp.getState().addRun(sim.id, { ...data.run.input, comment: 'Re-run after product change' }, 'user', 'Re-run after product change').then((r) => toast('Re-ran as v' + r.version), report) }}>Re-run</button>
            </div>
          )}
          <div className={cn('@container min-h-0 flex-1 scroll-pt-5 space-y-12 overflow-y-auto px-4 pt-5 transition-opacity sm:px-8', askOpen ? 'pb-5' : 'pb-24', data.loading && 'opacity-50')} id="sim-scroll" aria-busy={data.loading}>
            {data.compare && <ComparePanel data={data} />}
            {tab !== 'overview' && data.input.productIds.length > 1 && <p className="text-[13px] text-muted-foreground">Showing <b className="font-medium text-foreground">{data.result.name}</b> · change the product on the Overview tab</p>}
            {tab === 'costing' && <Costing data={data} />}
            {tab === 'pricing' && <Pricing data={data} />}
            {tab === 'margin' && <Margin data={data} />}
            {tab === 'overview' && <Overview data={data} />}
          </div>
        </div>
      )}
      {askOpen && wide && <div className="relative hidden h-full shrink-0 xl:block" style={{ width: askWidth }}><ResizeHandle width={askWidth} onChange={setAskWidth} />{askPanel}</div>}
      {/* Closed: the way back in sits where the panel was, on every screen size. The page keeps room under it (pb-24 above). */}
      {!askOpen && (
        <button onClick={toggleAsk} title="Open the AI panel (⌘/)" aria-label="Open Ask AI" aria-expanded={false} aria-controls="ask-ai" data-testid="ask-launcher"
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-primary py-2 pl-2 pr-4 text-sm font-medium text-primary-foreground shadow-lg outline-none ring-offset-2 ring-offset-background transition-transform duration-200 animate-in fade-in slide-in-from-bottom-2 hover:scale-[1.03] focus-visible:ring-2 focus-visible:ring-ring">
          <span className="flex size-8 items-center justify-center rounded-full bg-background"><MascotIcon size={20} /></span>Ask AI
        </button>
      )}
      {askOpen && !wide && <div className="fixed inset-0 z-40 flex justify-end bg-black/40 duration-200 animate-in fade-in" onClick={pending ? undefined : closeAsk}><div className="h-full w-full max-w-[400px] bg-background shadow-xl duration-200 animate-in slide-in-from-right" role="dialog" aria-modal="true" aria-label="Ask AI" onClick={(e) => e.stopPropagation()}>{askPanel}</div></div>}
    </div>
  )
}
