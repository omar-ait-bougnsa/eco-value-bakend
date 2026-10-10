import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Run, RunInput } from '@/engine/types'
import type { AgentEvent, TurnExtra } from '@/lib/api'

type On = (e: AgentEvent) => void | Promise<void>

const INPUT = { productIds: ['phos-65-35'], referenceId: 'TSP', periodFrom: '2026-01-01', periodTo: '2026-10-02', methods: ['costPlus', 'refMinus'], valueShare: 1 / 3 } as unknown as RunInput
const run = (version: number, input: Partial<RunInput> = {}): Run => ({ id: `r${version}`, version, input: { ...INPUT, ...input }, output: { perProduct: {}, flags: [] }, createdAt: '2026-10-02T09:00:00Z', createdBy: 'agent', summary: '', changed: [], editedKeys: [] })

// The backend as the chat sees it: what its agent streams for a turn, and the simulations it holds.
const backend = vi.hoisted(() => ({
  events: [] as unknown[],
  turns: [] as { simId: string; text: string; extra: unknown }[],
  sims: {} as Record<string, { title: string; runs: unknown[] }>,
  staged: new Set<string>(),
  calls: [] as string[],
  job: null as null | (() => unknown), // what GET /jobs/{id} answers, or throws
}))

vi.mock('@/lib/api', () => ({
  jobEnded: (j: { state: string } | null | undefined) => !!j && j.state !== 'queued' && j.state !== 'running',
  report: (e: unknown) => { throw e },
  api: {
    createSim: async (title: string) => { const id = `s${Object.keys(backend.sims).length + 1}`; backend.sims[id] = { title, runs: [] }; return { id, title, createdAt: '2026-10-02T09:00:00Z', runs: [] } },
    sim: async (id: string) => ({ id, createdAt: '2026-10-02T09:00:00Z', ...backend.sims[id], runs: [...backend.sims[id].runs] }), // a response is a copy, as over the network
    agentTurn: async (simId: string, text: string, on: On, extra: TurnExtra = {}) => { backend.turns.push({ simId, text, extra }); for (const e of backend.events) await on(e as AgentEvent) },
    addRun: async (simId: string, input: RunInput) => { backend.calls.push('addRun'); const r = run(backend.sims[simId].runs.length + 1, input); backend.sims[simId].runs.push(r); return r },
    applyChange: async (changeId: string) => { backend.calls.push(`apply ${changeId}`); if (!backend.staged.has(changeId)) throw new Error('not found or expired'); const r = run(2, { valueShare: 0.5 }); backend.sims.s1.runs.push(r); return r },
    dismissChange: async (changeId: string) => { backend.calls.push(`dismiss ${changeId}`) },
    job: async (id: string) => { backend.calls.push(`job ${id}`); return backend.job!() },
    cancelJob: async (id: string) => { backend.calls.push(`cancel ${id}`); return { ...(backend.job!() as object), state: 'cancelled' } },
  },
}))

const thread = async (id: string) => (await import('@/store/app')).useApp.getState().sims[id].thread
const kinds = async (id: string) => (await thread(id)).map((m) => m.kind)

beforeAll(async () => {
  // Minimal browser shims so the zustand store (persist) works under node.
  const mem = new Map<string, string>()
  ;(globalThis as unknown as { localStorage: Storage }).localStorage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => void mem.set(k, v), removeItem: (k) => void mem.delete(k), clear: () => mem.clear(), key: () => null, length: 0 } as Storage
  ;(globalThis as unknown as { __EVS_FAST__: boolean }).__EVS_FAST__ = true
})

beforeEach(async () => {
  const { useApp } = await import('@/store/app')
  backend.events = []; backend.turns = []; backend.sims = {}; backend.staged.clear(); backend.calls = []; backend.job = null
  useApp.setState({ status: 'ready', sims: {}, order: [], defaultInput: INPUT, params: { defaultReference: 'TSP' } as never })
})

/** A simulation the chat has open, with one run saved by the backend. */
async function open() {
  const { useApp } = await import('@/store/app')
  const id = await useApp.getState().createSim('Demo', INPUT)
  backend.sims[id].runs.push(run(1))
  await useApp.getState().syncRuns(id)
  return id
}

describe('chat', () => {
  it('sends every message to the backend agent and turns its events into the thread', async () => {
    const { useApp } = await import('@/store/app'); const { sendMessage } = await import('./chat')
    const id = await useApp.getState().createSim('price it', INPUT)
    backend.sims[id] = { title: 'Phosfusion 65-35 vs TSP', runs: [run(1)] } // what the agent saves during the turn
    backend.events = [
      { type: 'step', payload: { label: 'Checking sources and data freshness', status: 'running' } },
      { type: 'tool', payload: { name: 'run_engine', label: 'Pricing engine · 4 methods · v1 · 0.1 s', latencyMs: 80 } },
      { type: 'text', payload: { content: 'Recommended anchor: 313.91 USD/t.', sources: ['Prices · 21 Apr'] } },
      { type: 'result', payload: { runId: 'r1', version: 1 } },
      { type: 'flag', payload: { id: 'U1', code: 'U1', severity: 'warning', title: 'Yield unit' } },
      { type: 'flag', payload: { id: 'A1', code: 'A1', severity: 'info', title: 'Assumption' } },
      { type: 'flag', payload: { id: 'U1', code: 'U1', severity: 'warning', title: 'Yield unit' } },
      { type: 'suggest', payload: { items: ['Show the sulphur break-even'] } },
      { type: 'done', payload: { mode: 'script' } },
    ]
    await sendMessage(id, '  Price Phosfusion 65-35 against TSP ')
    expect(backend.turns).toEqual([{ simId: id, text: 'Price Phosfusion 65-35 against TSP', extra: {} }])
    expect(await kinds(id)).toEqual(['user', 'steps', 'tool', 'text', 'result', 'flag', 'suggest']) // warnings once, no info flags
    const t = await thread(id)
    expect(t[1]).toMatchObject({ steps: [{ label: 'Checking sources and data freshness', done: true }] })
    expect(t[3]).toMatchObject({ text: 'Recommended anchor: 313.91 USD/t.', sources: ['Prices · 21 Apr'] })
    const sim = useApp.getState().sims[id]
    expect(sim.runs).toHaveLength(1) // read back from the backend
    expect(sim.title).toBe('Phosfusion 65-35 vs TSP')
    expect(sim.busy).toBe(false)
  })

  it('from the home page, creates the simulation and starts the turn', async () => {
    const { sendMessage } = await import('./chat')
    backend.events = [{ type: 'text', payload: { content: 'Nothing looks off.' } }]
    const id = await sendMessage(null, 'Check my data for gaps')
    expect(backend.sims[id].title).toBe('Check my data for gaps')
    await vi.waitFor(async () => expect(await kinds(id)).toEqual(['user', 'text']))
  })

  it('sends a question’s answer back with what the agent gave to resume from', async () => {
    const { useApp } = await import('@/store/app'); const { sendMessage, answerQuestion } = await import('./chat')
    const id = await useApp.getState().createSim('Demo', INPUT)
    const resume = { productIds: ['phos-65-35'], referenceId: 'TSP' }
    backend.events = [{ type: 'question', payload: { text: 'Which cost should I use?', flag: 'S1', resume, summary: 'Initial run', options: [{ id: 'standard', label: 'Use 655.18', sub: 'Standard cost 2026', primary: true }, { id: 'deck', label: 'Use 494', sub: 'Business-case deck' }, { id: 'sources', label: 'Open sources' }] } }]
    await sendMessage(id, 'Price Phosfusion 65-35 against TSP')
    const q = (await thread(id)).find((m) => m.kind === 'question')!
    backend.events = []

    await answerQuestion(id, q.id, 'sources') // looking at the sources is not an answer
    expect((await thread(id)).find((m) => m.kind === 'question')).not.toHaveProperty('answered')
    await answerQuestion(id, q.id, 'deck')
    expect((await thread(id)).find((m) => m.kind === 'question')).toMatchObject({ answered: 'deck' })
    expect(backend.turns[2]).toEqual({ simId: id, text: 'Which cost should I use?\n\nAnswer: Use 494', extra: { answer: { option: 'deck', question: 'Which cost should I use?', resume, summary: 'Initial run' } } })
    expect((await thread(id)).at(-1)).toMatchObject({ kind: 'user', text: 'Use 494 · Business-case deck' })
    await answerQuestion(id, q.id, 'standard') // already answered
    expect(backend.turns).toHaveLength(3)
  })

  it('prices the Configure run form’s input through the agent', async () => {
    const { startRun } = await import('./chat')
    const id = await open()
    await startRun(id, 'Run: Phosfusion 65-35 vs DAP', { ...INPUT, referenceId: 'DAP' })
    expect(backend.turns[0].extra).toEqual({ input: { ...INPUT, referenceId: 'DAP' } })
  })

  it('shows a staged change with the agent’s previews, and applies it through the backend', async () => {
    const { useApp } = await import('@/store/app'); const { sendMessage, applyChange, dismissChange } = await import('./chat')
    const id = await open()
    const change = { id: 'c1', label: 'Value share kept by OCP', reason: '', patch: { valueShare: 0.5 }, before: { valueShare: 1 / 3 }, after: { valueShare: 0.5 }, previews: [{ label: 'Value pricing', before: '740.99', after: '791.48' }] }
    backend.events = [{ type: 'change', payload: change }, { type: 'change', payload: { ...change, id: 'c2' } }, { type: 'change', payload: { ...change, id: 'c3' } }]
    await sendMessage(id, 'What if the value share is 50%?')
    const [a, b, c] = (await thread(id)).filter((m) => m.kind === 'change')
    expect(a).toMatchObject({ before: '33.3%', after: '50%', previews: change.previews, status: 'staged', changeId: 'c1' })

    backend.staged.add('c1')
    await applyChange(id, a.id)
    expect(backend.calls).toEqual(['apply c1'])
    expect(useApp.getState().sims[id].runs).toHaveLength(2)
    expect((await thread(id)).find((m) => m.id === a.id)).toMatchObject({ status: 'applied', appliedVersion: 2 })
    expect((await thread(id)).at(-1)).toMatchObject({ kind: 'result', version: 2 })

    await applyChange(id, b.id) // the backend no longer holds c2: the same patch is run on the latest input
    expect(backend.calls).toEqual(['apply c1', 'apply c2', 'addRun'])
    expect(useApp.getState().sims[id].runs.at(-1)!.input.valueShare).toBe(0.5)

    dismissChange(id, c.id)
    expect((await thread(id)).find((m) => m.id === c.id)).toMatchObject({ status: 'dismissed' })
    expect(backend.calls.at(-1)).toBe('dismiss c3')
  })

  it('follows the agent’s view: another analysis period, the memo', async () => {
    const { useApp } = await import('@/store/app'); const { sendMessage } = await import('./chat')
    const id = await open()
    backend.events = [{ type: 'view', payload: { period: { from: '2025-01-01', to: '2025-12-31' }, tab: 'overview' } }, { type: 'view', payload: { memo: true } }]
    await sendMessage(id, 'Show the 2025 analysis period')
    expect(useApp.getState().sims[id].view).toMatchObject({ period: { from: '2025-01-01', to: '2025-12-31' }, tab: 'overview' })
    expect(useApp.getState().ui.memoOpen).toBe(true)
  })

  it('attaches citations to the text that follows them, and shows an error as text', async () => {
    const { sendMessage } = await import('./chat')
    const id = await open()
    backend.events = [
      { type: 'citation', payload: { index: 1, label: 'argus.xlsx, 30 Sep 2026', source: 'argus.xlsx', passage: '…' } },
      { type: 'text', payload: { content: 'Freight is 25.5 USD/t [1].' } },
      { type: 'text', payload: { content: 'Anything else?' } },
      { type: 'error', payload: { message: 'The language model did not answer.' } },
    ]
    await sendMessage(id, 'What do the reports say about freight?')
    const texts = (await thread(id)).filter((m) => m.kind === 'text')
    expect(texts[0]).toMatchObject({ sources: ['[1] argus.xlsx, 30 Sep 2026'] })
    expect(texts[1]).toMatchObject({ text: 'Anything else?', sources: [] })
    expect(texts[2]).toMatchObject({ text: 'The language model did not answer.' })
  })
})

const job = (state: string, over: object = {}) => ({ id: 'j1', simulationId: 's1', kind: 'message', state, mode: 'script', request: { text: 'Price it', input: { referenceId: 'DAP' } }, result: null, failureCode: null, error: null, transitions: [], createdAt: new Date().toISOString(), startedAt: null, finishedAt: null, timeoutSeconds: 120, ...over })

describe('agent jobs', () => {
  it('keeps the job the server reports, and leaves a failed one to its Retry instead of a chat line', async () => {
    const { useApp } = await import('@/store/app'); const { sendMessage, retryJob } = await import('./chat')
    const id = await open()
    const failed = job('failed', { failureCode: 'invalid_input', error: 'costPlusMargin: must be between 0 and 2 (fraction)' })
    backend.events = [{ type: 'job', payload: job('running') }, { type: 'error', payload: { message: failed.error, code: 'invalid_input', fatal: true } }, { type: 'job', payload: failed }]
    await sendMessage(id, 'Price it')
    expect(useApp.getState().sims[id].job).toMatchObject({ state: 'failed', error: 'costPlusMargin: must be between 0 and 2 (fraction)' })
    expect(await kinds(id)).toEqual(['user']) // the failure is the job's, shown with Retry: not also a line of chat
    expect(useApp.getState().sims[id].busy).toBe(false)

    backend.events = [{ type: 'job', payload: job('completed', { id: 'j2' }) }]
    await retryJob(id) // the same request, as the server kept it
    expect(backend.turns.at(-1)).toEqual({ simId: id, text: 'Price it', extra: { input: { referenceId: 'DAP' }, answer: undefined } })
    expect(useApp.getState().sims[id].job).toMatchObject({ id: 'j2', state: 'completed' })
  })

  it('follows a job it is not streaming until the server says it ended, and shows the run it saved', async () => {
    const { useApp } = await import('@/store/app'); const { watchJob } = await import('./chat')
    const id = await open()
    useApp.getState().setJob(id, job('running') as never) // a reloaded page: the job is the server's
    let asked = 0
    backend.job = () => (++asked < 3 ? job('running') : job('completed', { result: { outcome: 'run', runVersion: 2 } }))
    backend.sims[id].runs.push(run(2))
    await watchJob(id)
    expect(asked).toBe(3)
    expect(useApp.getState().sims[id]).toMatchObject({ job: { state: 'completed' } })
    expect(useApp.getState().sims[id].runs).toHaveLength(2)
    expect((await thread(id)).at(-1)).toMatchObject({ kind: 'result', version: 2 })
  })

  it('never waits forever: a missing job, an unreachable server and a silent one all end as a failure', async () => {
    const { useApp } = await import('@/store/app'); const { watchJob } = await import('./chat')
    const id = await open()
    const state = () => useApp.getState().sims[id].job!

    useApp.getState().setJob(id, job('running') as never)
    backend.job = () => { throw new Error("Job 'j1' not found") }
    await watchJob(id)
    expect(state()).toMatchObject({ state: 'failed', failureCode: 'job_missing' })

    useApp.getState().setJob(id, job('running', { id: 'j3' }) as never)
    backend.job = () => { throw new Error('Cannot reach the backend. Is it running?') }
    await watchJob(id)
    expect(state()).toMatchObject({ state: 'failed', failureCode: 'unreachable' })
    expect(backend.calls.filter((c) => c === 'job j3')).toHaveLength(3)

    useApp.getState().setJob(id, job('running', { id: 'j4', timeoutSeconds: -20 }) as never) // already past its time
    backend.job = () => job('running', { id: 'j4', timeoutSeconds: -20 })
    await watchJob(id)
    expect(state()).toMatchObject({ state: 'timed_out', failureCode: 'no_response' })
  })

  it('cancels a running job', async () => {
    const { useApp } = await import('@/store/app'); const { cancelJob } = await import('./chat')
    const id = await open()
    useApp.getState().setJob(id, job('running') as never)
    backend.job = () => job('running')
    await cancelJob(id)
    expect(backend.calls).toContain('cancel j1')
    expect(useApp.getState().sims[id].job).toMatchObject({ state: 'cancelled' })
  })
})
