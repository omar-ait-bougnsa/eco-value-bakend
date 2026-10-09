import { ArrowUp, Check, ChevronDown, Copy, Paperclip, Settings2, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ChatContainerContent, ChatContainerRoot } from '@/components/ui/chat-container'
import { PromptInput, PromptInputAction, PromptInputActions, PromptInputTextarea } from '@/components/ui/prompt-input'
import { PromptSuggestion } from '@/components/ui/prompt-suggestion'
import { ScrollButton } from '@/components/ui/scroll-button'
import { Steps, StepsContent, StepsItem, StepsTrigger } from '@/components/ui/steps'
import { TextShimmer } from '@/components/ui/text-shimmer'
import { SystemMessage } from '@/components/ui/system-message'
import { applyChange, answerQuestion, dismissChange, handleMessage, SUGGESTIONS } from '@/agent/script'
import { useApp } from '@/store/app'
import type { Msg } from '@/store/types'
import { f2 } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Flag } from '@/engine/types'
import { Pill, bannerAction } from './atoms'
import { AnswerText } from './AnswerText'
import { ResultCard } from './ResultCard'
import { openFlagTarget } from './flag-actions'
import { MascotIcon } from '@/components/app/MascotIcon'

/** An agent message. The first one of a turn (`lead`) carries the mascot, level with its first line; the rest use the full width. */
function Assistant({ children, lead }: { children: ReactNode; lead?: boolean }) {
  if (!lead) return <div className="min-w-0 space-y-3">{children}</div>
  return (
    <div className="flex items-start gap-2">
      <MascotIcon size={18} className="mt-px" />
      <div className="min-w-0 flex-1 space-y-3">{children}</div>
    </div>
  )
}

function ToolRow({ label }: { label: string }) {
  const running = /running/.test(label)
  return (
    <div className="inline-flex items-center gap-2 rounded-lg border bg-muted px-2.5 py-1.5 font-mono text-[13px] text-muted-foreground">
      <Settings2 className="size-3.5" />
      <span>{label}</span>
      {running ? <TextShimmer className="text-[13px]">running</TextShimmer> : <Check className="size-3 text-foreground" />}
    </div>
  )
}

function Row({ m, simId, compact, lead }: { m: Msg; simId: string; compact?: boolean; lead?: boolean }) {
  const send = (t: string) => void handleMessage(simId, t)
  if (m.kind === 'user')
    return (
      <div className="flex justify-end pt-4 first:pt-0">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-3.5 py-2 text-sm">{m.text}</div>
      </div>
    )
  if (m.kind === 'text')
    return (
      <Assistant lead={lead}>
        <AnswerText text={m.text} sources={m.sources} />
        {m.feedback && (
          <div className="flex gap-1 text-muted-foreground">
            <Button variant="ghost" size="icon" className="size-8" aria-label="Copy answer" title="Copy" onClick={() => { void navigator.clipboard?.writeText(m.text); toast('Copied') }}><Copy className="size-4" /></Button>
            <Button variant="ghost" size="icon" className="size-8" aria-label="Good answer" title="Good answer"><ThumbsUp className="size-4" /></Button>
            <Button variant="ghost" size="icon" className="size-8" aria-label="Bad answer" title="Bad answer"><ThumbsDown className="size-4" /></Button>
          </div>
        )}
      </Assistant>
    )
  if (m.kind === 'steps') {
    const done = m.steps.every((s) => s.done)
    return (
      <Assistant lead={lead}>
        <Steps defaultOpen className="rounded-[10px] border bg-background px-3 py-2.5" aria-live="polite">
          <StepsTrigger className="text-[13px] font-medium text-muted-foreground">{done ? `Finished in ${m.steps.length} steps` : 'Working…'}</StepsTrigger>
          <StepsContent>
            <div className="mt-2 space-y-1.5">
              {m.steps.map((s, i) => {
                const active = i === m.steps.findIndex((x) => !x.done)
                return (
                  <StepsItem key={i} className="flex items-center gap-2 text-sm">
                    {s.done ? <Check className="size-3.5" /> : active ? <span className="size-3.5 animate-spin rounded-full border-[1.5px] border-foreground border-t-transparent" /> : <span className="size-3.5 rounded-full border-[1.5px] border-border" />}
                    {s.done ? <span className="text-muted-foreground">{s.label}</span> : active ? <TextShimmer className="text-sm">{s.label}</TextShimmer> : <span className="text-subtle">{s.label}</span>}
                  </StepsItem>
                )
              })}
            </div>
          </StepsContent>
        </Steps>
      </Assistant>
    )
  }
  if (m.kind === 'flag') return <Assistant lead={lead}><FlagMessage flag={m.flag} simId={simId} /></Assistant>
  if (m.kind === 'tool') return <Assistant lead={lead}><ToolRow label={m.label} /></Assistant>
  if (m.kind === 'question')
    return (
      <Assistant lead={lead}>
        <p className={cn('leading-[22px]', compact ? 'text-sm' : 'text-sm')}>{m.text}</p>
        <div className="flex flex-wrap gap-2">
          {m.options.map((o) => {
            const picked = m.answered === o.id
            return (
              <button
                key={o.id}
                disabled={!!m.answered && o.id !== 'sources'}
                onClick={() => void answerQuestion(simId, m.id, o.id)}
                className={cn('rounded-lg border px-3 py-2 text-left text-sm transition-colors', o.primary && !m.answered ? 'border-foreground' : '', picked ? 'border-foreground bg-accent' : 'hover:bg-accent', m.answered && !picked && 'opacity-50', o.id === 'sources' && 'border-transparent text-muted-foreground')}
              >
                <span className={cn('font-medium', o.sub && 'num')}>{o.label}</span>
                {o.sub && <span className="ml-2 text-[13px] text-muted-foreground">{o.sub}</span>}
              </button>
            )
          })}
        </div>
      </Assistant>
    )
  if (m.kind === 'result')
    return (
      <Assistant lead={lead}>
        <ResultCard simId={simId} version={m.version} compact={compact} />
      </Assistant>
    )
  if (m.kind === 'change')
    return (
      <Assistant lead={lead}>
        <div className="rounded-[10px] border bg-card p-3.5">
          <div className="mb-2.5 flex items-center justify-between">
            <span className="text-[13px] font-medium text-muted-foreground">Proposed change</span>
            <Pill>{m.status === 'staged' ? 'Staged' : m.status === 'applied' ? `Applied · v${m.appliedVersion}` : 'Dismissed'}</Pill>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span>{m.label}</span>
            <span className="flex-1" />
            <span className="num text-muted-foreground line-through">{m.before}</span>
            <span className="text-muted-foreground">→</span>
            <span className="num font-semibold">{m.after}</span>
          </div>
          {m.previews.length > 0 && (
            <div className="mt-2 space-y-1 border-t pt-2">
              {m.previews.map((p) => (
                <div key={p.label} className="flex items-center justify-between text-[13px]"><span className="text-muted-foreground">{p.label} (preview)</span><span className="num font-medium">{p.before} → {p.after}</span></div>
              ))}
            </div>
          )}
          {m.status === 'staged' && (
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => void applyChange(simId, m.id)}>Apply &amp; re-run</Button>
              <Button size="sm" variant="ghost" onClick={() => dismissChange(simId, m.id)}>Dismiss</Button>
            </div>
          )}
        </div>
      </Assistant>
    )
  if (m.kind === 'suggest')
    return (
      <div className="flex flex-wrap gap-2">
        {m.items.map((i) => (
          <PromptSuggestion key={i} onClick={() => send(i)} className="h-auto rounded-lg py-1.5 text-sm">{i}</PromptSuggestion>
        ))}
      </div>
    )
  return null
}

function FlagMessage({ flag, simId }: { flag: Flag; simId: string }) {
  const nav = useNavigate()
  const variant = flag.severity === 'error' ? 'error' : flag.severity === 'warning' ? 'warning' : 'action'
  return (
    <SystemMessage variant={variant} fill className="items-start">
      <div>
        <div className="font-medium">{flag.title}</div>
        {flag.detail && <div className="mt-0.5 text-[13px] opacity-80">{flag.detail}</div>}
      </div>
      {flag.action && flag.action.kind !== 'answer' && (
        <button className={cn(bannerAction, 'ml-3')} onClick={() => openFlagTarget(flag, simId, nav)}>{flag.action.label}</button>
      )}
    </SystemMessage>
  )
}

export function Composer({ simId, placeholder, onSend, disabled, compact, autoFocus }: { simId: string | null; placeholder: string; onSend?: (t: string) => Promise<string | void> | void; disabled?: boolean; compact?: boolean; autoFocus?: boolean }) {
  const [v, setV] = useState('')
  const nav = useNavigate()
  const setUI = useApp((s) => s.setUI)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (autoFocus) ref.current?.querySelector('textarea')?.focus() }, [autoFocus])
  const submit = async () => {
    const t = v.trim()
    if (!t || disabled) return
    setV('')
    if (onSend) { await onSend(t); return }
    const id = await handleMessage(simId, t)
    if (!simId && id) nav(`/s/${id}`)
  }
  return (
    <div ref={ref}>
      <PromptInput value={v} onValueChange={setV} onSubmit={submit} disabled={disabled} className={cn('rounded-2xl border bg-card shadow-none', compact ? 'p-2' : 'p-3')}>
        <PromptInputTextarea placeholder={placeholder} className={cn('placeholder:text-subtle', compact ? 'min-h-[36px] text-sm' : 'min-h-[44px] text-base')} />
        <PromptInputActions className="mt-1 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <PromptInputAction tooltip="Attach a file"><Button variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-foreground" aria-label="Attach a file" onClick={() => nav('/uploads')}><Paperclip className="size-4" />{!compact && 'Attach'}</Button></PromptInputAction>
            <PromptInputAction tooltip="Configure run (⌘⇧R)"><Button variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-foreground" aria-label="Configure run" onClick={() => setUI({ runFormOpen: true })}><Settings2 className="size-4" />{!compact && 'Configure run'}</Button></PromptInputAction>
          </div>
          <div className="flex items-center gap-2">
            {!compact && <span className="hidden text-[13px] text-subtle sm:block">⌘⏎</span>}
            <PromptInputAction tooltip="Send">
              <Button size="icon" className="size-8 rounded-full" disabled={!v.trim() || disabled} onClick={() => void submit()} aria-label="Send"><ArrowUp className="size-4" /></Button>
            </PromptInputAction>
          </div>
        </PromptInputActions>
      </PromptInput>
    </div>
  )
}

export function Thread({ simId, compact, className }: { simId: string; compact?: boolean; className?: string }) {
  const sim = useApp((s) => s.sims[simId])
  const pendingQ = sim?.thread.some((m) => m.kind === 'question' && !m.answered)
  if (!sim) return null
  return (
    <div className={cn('relative flex min-h-0 flex-1 flex-col', className)}>
      <ChatContainerRoot className="relative min-h-0 flex-1 overflow-hidden">
        <ChatContainerContent className={cn('mx-auto w-full space-y-3 px-4 py-5', compact ? 'max-w-full' : 'max-w-[760px]')}>
          {sim.thread.length === 0 && !sim.busy && (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center" data-testid="thread-empty">
              <MascotIcon size={48} />
              <div>
                <div className="text-[15px] font-semibold">Ask about this simulation</div>
                <p className="mx-auto mt-1 max-w-[300px] text-[13px] leading-5 text-muted-foreground">I can price a product, test a what-if, explain a figure, or look in your documents. Nothing changes until you confirm it.</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2 pt-1">
                {(sim.runs.length ? SUGGESTIONS : ['Price Phosfusion 65-35 against TSP', 'What do the reports say about freight?']).map((s) => (
                  <PromptSuggestion key={s} onClick={() => void handleMessage(simId, s)} className="h-auto rounded-lg py-1.5 text-sm">{s}</PromptSuggestion>
                ))}
              </div>
            </div>
          )}
          {sim.thread.map((m, i) => <Row key={m.id} m={m} simId={simId} compact={compact} lead={i === 0 || sim.thread[i - 1].kind === 'user'} />)}
          {sim.busy && !pendingQ && sim.thread[sim.thread.length - 1]?.kind === 'user' && (
            <Assistant lead><TextShimmer className="text-sm">Thinking…</TextShimmer></Assistant>
          )}
        </ChatContainerContent>
        <div className="pointer-events-none absolute bottom-3 right-4"><ScrollButton className="pointer-events-auto" /></div>
      </ChatContainerRoot>
      <div className={cn('mx-auto w-full px-4 pb-4 pt-1', compact ? 'max-w-full' : 'max-w-[760px]')}>
        <Composer simId={simId} compact={compact} disabled={sim.busy || pendingQ} placeholder={pendingQ ? 'Answer the question above to continue' : 'Ask about this simulation…'} />
      </div>
    </div>
  )
}

export { Sparkles, ChevronDown, f2 }
