// The chat carries messages and shows what comes back. Understanding a request, pricing, checking and wording the
// answer are the backend agent's job (POST /simulations/{id}/messages): its events become the thread.
import type { Run, RunInput } from '@/engine/types'
import { defaultRunInput, uid, useApp } from '@/store/app'
import type { Msg, NewMsg } from '@/store/types'
import { pct, sleep } from '@/lib/format'
import { api, jobEnded, report, type Job, type TurnExtra } from '@/lib/api'

const S = () => useApp.getState()
const push = (simId: string, m: NewMsg) => S().pushMsg(simId, { id: uid(), ...m } as Msg)

/** A text of the agent, typed out a few words at a time. */
async function streamText(simId: string, text: string, extra: { sources?: string[] } = {}) {
  const id = push(simId, { kind: 'text', text: '', ...extra })
  const words = text.split(/(\s+)/)
  let acc = ''
  for (let i = 0; i < words.length; i++) {
    acc += words[i]
    if (i % 3 === 0 || i === words.length - 1) { S().patchMsg(simId, id, { text: acc }); await sleep(22) }
  }
  return id
}

const SHARES = ['valueShare', 'costPlusMargin', 'marketShare', 'marketingPct']
const shown = (k: string, v: unknown) => (v == null ? 'not set' : SHARES.includes(k) ? pct(v as number) : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : Array.isArray(v) ? v.join(', ') : String(v))

/** One turn of the backend agent: its events become thread messages, and the runs it saved are read back. */
async function turn(simId: string, text: string, extra?: TurnExtra) {
  S().setBusy(simId, true)
  const steps: string[] = []; const flagged = new Set<string>()
  let sources: string[] = [] // citations of the text that follows them
  let stepsId: string | null = null
  const showSteps = (finished: boolean) => {
    const list = steps.map((label, i) => ({ label, done: finished || i < steps.length - 1 }))
    if (stepsId) S().patchMsg(simId, stepsId, { steps: list }); else stepsId = push(simId, { kind: 'steps', steps: list })
  }
  try {
    await api.agentTurn(simId, text, async (e) => {
      if (e.type === 'job') S().setJob(simId, e.payload) // the server's word on where the turn is
      else if (e.type === 'step') { steps.push(e.payload.label.replace(/\.+$/, '')); showSteps(false) }
      else if (e.type === 'tool') { if (steps.length) showSteps(true); push(simId, { kind: 'tool', label: e.payload.label }) }
      else if (e.type === 'flag') {
        // The agent may send every flag of a run, each time it checks: the thread keeps the warnings, once.
        if (['warning', 'error'].includes(e.payload.severity) && !flagged.has(e.payload.code)) { flagged.add(e.payload.code); push(simId, { kind: 'flag', flag: e.payload }) }
      }
      else if (e.type === 'question') push(simId, { kind: 'question', flagId: e.payload.flag ?? 'agent', text: e.payload.text, options: e.payload.options.map((o) => ({ id: o.id, label: o.label, sub: o.sub ?? undefined, primary: o.primary })), resume: e.payload.resume, summary: e.payload.summary })
      else if (e.type === 'result') { await S().syncRuns(simId); push(simId, { kind: 'result', version: e.payload.version }) }
      else if (e.type === 'change') {
        const side = (o: Record<string, unknown>) => Object.entries(o).map(([k, v]) => shown(k, v)).join(', ')
        push(simId, { kind: 'change', label: e.payload.label, before: side(e.payload.before), after: side(e.payload.after), previews: e.payload.previews ?? [], patch: e.payload.patch, status: 'staged', changeId: e.payload.id })
      }
      else if (e.type === 'citation') sources.push(`[${e.payload.index}] ${e.payload.label}`)
      else if (e.type === 'text') { await streamText(simId, e.payload.content, { sources: [...sources, ...(e.payload.sources ?? [])] }); sources = [] }
      else if (e.type === 'view') {
        // The agent points the screen at what it talks about: another analysis period, a tab, the memo.
        const { period, tab, memo } = e.payload
        if (period || tab) S().setView(simId, { ...(period ? { period } : {}), ...(tab ? { tab } : {}) })
        if (memo) S().setUI({ memoOpen: true })
      }
      else if (e.type === 'suggest') push(simId, { kind: 'suggest', items: e.payload.items })
      else if (e.type === 'error' && !e.payload.fatal) await streamText(simId, e.payload.message) // a failed job is shown from its stored state, with Retry
    }, extra)
  } catch (e) { if (!S().sims[simId]?.job || jobEnded(S().sims[simId].job)) report(e) } // a stream that broke mid-job is not the job's end: the watch below finds that out
  if (steps.length) showSteps(true)
  S().setBusy(simId, false)
  void watchJob(simId)
}

const POLL_MS = 1500
const watching = new Set<string>()

/**
 * Follow a job that is not being streamed here (a reloaded page, a stream that broke) until the server says it ended.
 * It never waits forever: past the job's own timeout plus a margin, or when the server cannot be reached or no longer
 * knows the job, the simulation shows a failure with Retry instead of "Running".
 */
export async function watchJob(simId: string) {
  const first = S().sims[simId]?.job
  if (!first || jobEnded(first) || S().sims[simId]?.busy || watching.has(first.id)) return
  watching.add(first.id)
  const give = (failureCode: string, error: string): Job => ({ ...first, state: failureCode === 'no_response' ? 'timed_out' : 'failed', failureCode, error, finishedAt: new Date().toISOString() })
  const deadline = Date.now() + (first.timeoutSeconds + 20) * 1000
  let misses = 0
  try {
    for (;;) {
      if (S().sims[simId]?.job?.id !== first.id) return // another turn took over
      let job: Job | null = null
      try { job = await api.job(first.id); misses = 0 } catch (e) {
        if (e instanceof Error && /not found/i.test(e.message)) { S().setJob(simId, give('job_missing', `The server no longer knows this request (job ${first.id}). Run it again.`)); return }
        if (++misses >= 3) { S().setJob(simId, give('unreachable', 'The server cannot be reached, so the state of this request is unknown. Check that the backend is running, then retry.')); return }
      }
      if (job) {
        S().setJob(simId, job)
        if (jobEnded(job)) {
          const before = S().sims[simId]?.runs.length ?? 0
          const runs = await S().syncRuns(simId).catch(() => null)
          // A run saved while nobody was listening still gets its card in the thread.
          if (runs && runs.length > before && job.result?.runVersion) push(simId, { kind: 'result', version: job.result.runVersion })
          return
        }
      }
      if (Date.now() > deadline) { S().setJob(simId, give('no_response', `The server did not report the end of this request in time (job ${first.id}). It may still finish: reload, or run it again.`)); return }
      await new Promise((r) => setTimeout(r, sleepMs()))
    }
  } finally { watching.delete(first.id) }
}
const sleepMs = () => ((globalThis as { __EVS_FAST__?: boolean }).__EVS_FAST__ ? 5 : POLL_MS)

/** Run a failed, timed-out or cancelled job again: the same request, as the server kept it. */
export async function retryJob(simId: string) {
  const job = S().sims[simId]?.job
  if (!job || !jobEnded(job) || S().sims[simId]?.busy) return
  await turn(simId, job.request.text, { input: job.request.input, answer: job.request.answer })
}

export async function cancelJob(simId: string) {
  const job = S().sims[simId]?.job
  if (!job || jobEnded(job)) return
  try { S().setJob(simId, await api.cancelJob(job.id)) } catch (e) { report(e) }
}

/** A message typed in the chat. Without a simulation one is created for it; its id comes back ('' when that failed). */
export async function sendMessage(simIdIn: string | null, raw: string): Promise<string> {
  const text = raw.trim()
  if (simIdIn) {
    push(simIdIn, { kind: 'user', text })
    await turn(simIdIn, text)
    return simIdIn
  }
  let simId: string
  // Named after the request for now: the agent names it after what it prices, on its first run.
  try { simId = await S().createSim(text.length > 40 ? text.slice(0, 38) + '…' : text, defaultRunInput(S().params)) } catch (e) { report(e); return '' }
  S().setUI({ askOpen: true })
  push(simId, { kind: 'user', text })
  void turn(simId, text) // the caller opens the simulation while the answer streams in
  return simId
}

/** The Configure run form: the agent prices this input as it is, after its usual check of the sources. */
export const startRun = (simId: string, text: string, input: RunInput) => turn(simId, text, { input })

export async function answerQuestion(simId: string, msgId: string, optionId: string) {
  const m = S().sims[simId].thread.find((x) => x.id === msgId)
  if (!m || m.kind !== 'question' || m.answered) return
  const opt = m.options.find((o) => o.id === optionId)
  if (!opt) return
  if (optionId !== 'sources') S().patchMsg(simId, msgId, { answered: optionId }) // looking at the sources leaves the question open
  push(simId, { kind: 'user', text: [opt.label, opt.sub].filter(Boolean).join(' · ') })
  // The agent keeps no history: the question goes back with the answer, and so does what it gave to resume from.
  await turn(simId, `${m.text}\n\nAnswer: ${opt.label}`, { answer: { option: optionId, question: m.text, resume: m.resume, summary: m.summary } })
}

export async function applyChange(simId: string, msgId: string) {
  const sim = S().sims[simId]; const m = sim.thread.find((x) => x.id === msgId)
  if (!m || m.kind !== 'change' || m.status !== 'staged') return
  const last = sim.runs[sim.runs.length - 1]
  const summary = `${m.label} ${m.before} → ${m.after}`
  S().setBusy(simId, true)
  let run: Run
  try {
    // The agent applies the change it staged. It keeps those in memory only, so once it has forgotten one the same patch is run on the latest input.
    const applied = m.changeId ? await api.applyChange(m.changeId, summary).catch(() => null) : null
    if (applied) await S().syncRuns(simId)
    run = applied ?? await S().addRun(simId, { ...last.input, ...m.patch, comment: `${m.label}: ${m.before} → ${m.after}` }, 'agent', summary)
  } catch (e) { S().setBusy(simId, false); report(e); return }
  S().patchMsg(simId, msgId, { status: 'applied', appliedVersion: run.version })
  await streamText(simId, `Re-ran as **v${run.version}**. Compare it with v${run.version - 1} from the version chip.`)
  push(simId, { kind: 'result', version: run.version })
  S().setBusy(simId, false)
}

export function dismissChange(simId: string, msgId: string) {
  const m = S().sims[simId].thread.find((x) => x.id === msgId)
  if (m?.kind === 'change' && m.changeId) api.dismissChange(m.changeId).catch(() => {}) // the card is dismissed here either way
  S().patchMsg(simId, msgId, { status: 'dismissed' })
}
