import { beforeAll, describe, expect, it, vi } from 'vitest'
import { PRODUCTS } from '@/test-fixtures/products'
import { SNAPSHOTS } from '@/test-fixtures/snapshots'
import { SEED_UPLOADS } from '@/test-fixtures/uploads'
import { DEFAULT_PARAMS, defaultRunInput } from '@/test-fixtures/defaults'
import { runEngine } from '@/engine/run'
import type { Run, RunInput } from '@/engine/types'
import type { AgentEvent, Passage, Sensitivity } from '@/lib/api'

type On = (e: AgentEvent) => void | Promise<void>

// What the stand-in backend's agent and sensitivity endpoint do: set by the tests that go through them.
const backend = vi.hoisted(() => ({
  mode: 'script' as 'llm' | 'script',
  turn: null as null | ((simId: string, text: string, on: On) => Promise<void>),
  staged: {} as Record<string, { simId: string; patch: Partial<RunInput> }>,
  sensitivity: null as Sensitivity | null,
  passages: [] as Passage[],
  calls: [] as string[],
}))

// Stand-in for the backend: simulations and runs are kept in memory and priced with the local engine.
vi.mock('@/lib/api', () => {
  const runs: Record<string, Run[]> = {}
  let n = 0
  const addRun = async (simId: string, input: RunInput, createdBy: Run['createdBy'], summary: string): Promise<Run> => {
    const output = runEngine(input, { products: PRODUCTS, snapshots: SNAPSHOTS, uploads: SEED_UPLOADS, params: DEFAULT_PARAMS })
    const run: Run = { id: `r${++n}`, version: runs[simId].length + 1, input, output, createdAt: '2026-10-02T09:00:00Z', createdBy, summary, changed: [], editedKeys: [] }
    runs[simId].push(run)
    return run
  }
  return {
    report: (e: unknown) => { throw e },
    api: {
      createSim: async (title: string) => { const id = `t${++n}`; runs[id] = []; return { id, title, createdAt: '2026-10-02T09:00:00Z', runs: [] } },
      renameSim: async () => ({}),
      addRun,
      sim: async (id: string) => ({ id, title: '', createdAt: '2026-10-02T09:00:00Z', runs: [...runs[id]] }),
      sensitivity: async (productId: string, referenceId: string) => { backend.calls.push(`sensitivity ${productId} ${referenceId}`); return backend.sensitivity },
      searchKnowledge: async (query: string, limit: number) => { backend.calls.push(`search ${limit} ${query}`); return { results: backend.passages, model: 'hash-1536' } },
      agentStatus: async () => ({ mode: backend.mode, budget: { spent_usd: 0, cap_usd: 40, remaining_usd: 40 } }),
      agentTurn: async (simId: string, text: string, on: On) => { backend.calls.push(`turn ${text}`); await backend.turn!(simId, text, on) },
      // Like the backend: the patch goes on top of the latest run, and a change it no longer holds is a 404.
      applyChange: async (changeId: string, summary: string) => {
        backend.calls.push(`apply ${changeId}`)
        const c = backend.staged[changeId]
        if (!c) throw new Error(`Staged change '${changeId}' not found or expired`)
        return addRun(c.simId, { ...runs[c.simId][runs[c.simId].length - 1].input, ...c.patch }, 'agent', summary)
      },
      dismissChange: async (changeId: string) => { backend.calls.push(`dismiss ${changeId}`) },
    },
  }
})

// Minimal browser shims so the zustand store (persist) works under node.
beforeAll(async () => {
  const mem = new Map<string, string>()
  ;(globalThis as unknown as { localStorage: Storage }).localStorage = {
    getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => void mem.set(k, v), removeItem: (k) => void mem.delete(k), clear: () => mem.clear(), key: () => null, length: 0,
  } as Storage
  ;(globalThis as unknown as { __EVS_FAST__: boolean }).__EVS_FAST__ = true
  const { useApp } = await import('@/store/app')
  useApp.setState({ status: 'ready', products: PRODUCTS, snapshots: SNAPSHOTS, uploads: SEED_UPLOADS, params: DEFAULT_PARAMS, defaultParams: DEFAULT_PARAMS, defaultInput: defaultRunInput(DEFAULT_PARAMS) })
})

describe('scripted agent · hero path', () => {
  it('prices Phosfusion 65-35 vs TSP, asks the S1 question, then runs v1; what-if creates v2', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage, answerQuestion, applyChange } = await import('./script')
    const id = await handleMessage(null, 'Price Phosfusion 65-35 against TSP')
    // wait for the question
    const waitFor = async (fn: () => boolean, ms = 4000) => { const t0 = Date.now(); while (!fn()) { if (Date.now() - t0 > ms) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 10)) } }
    await waitFor(() => useApp.getState().sims[id].thread.some((m) => m.kind === 'question'))
    let sim = useApp.getState().sims[id]
    expect(sim.runs).toHaveLength(0)
    expect(sim.thread.some((m) => m.kind === 'flag' && m.flag.code === 'D1')).toBe(true)
    const q = sim.thread.find((m) => m.kind === 'question')!
    await answerQuestion(id, q.id, 'standard')
    await waitFor(() => useApp.getState().sims[id].runs.length === 1 && !useApp.getState().sims[id].busy)
    sim = useApp.getState().sims[id]
    const r1 = sim.runs[0].output.perProduct['phos-65-35']
    expect(r1.anchorPrice).toBeCloseTo(313.91, 2)
    expect(r1.prices.costPlus).toBeCloseTo(373.08, 2)
    expect(sim.thread.some((m) => m.kind === 'result')).toBe(true)

    await handleMessage(id, 'What if the value share is 50%?')
    await waitFor(() => useApp.getState().sims[id].thread.some((m) => m.kind === 'change'))
    const ch = useApp.getState().sims[id].thread.find((m) => m.kind === 'change')!
    await applyChange(id, ch.id)
    sim = useApp.getState().sims[id]
    expect(sim.runs).toHaveLength(2)
    expect(sim.runs[1].output.perProduct['phos-65-35'].prices.value).toBeCloseTo(791.48, 2)
    expect(sim.runs[0].output.perProduct['phos-65-35'].prices.value).toBeCloseTo(740.99, 2) // v1 immutable
  })

  it('choosing the deck cost (494) flips the reference margin to +146', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage, answerQuestion } = await import('./script')
    const id = await handleMessage(null, 'Price Phosfusion 65-35 against TSP')
    const waitFor = async (fn: () => boolean) => { const t0 = Date.now(); while (!fn()) { if (Date.now() - t0 > 4000) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 10)) } }
    await waitFor(() => useApp.getState().sims[id].thread.some((m) => m.kind === 'question'))
    const q = useApp.getState().sims[id].thread.find((m) => m.kind === 'question')!
    await answerQuestion(id, q.id, 'deck')
    await waitFor(() => useApp.getState().sims[id].runs.length === 1)
    expect(useApp.getState().sims[id].runs[0].output.perProduct['phos-65-35'].cgmRef).toBeCloseTo(146, 2)
  })
})

const waitFor = async (fn: () => boolean, ms = 4000) => { const t0 = Date.now(); while (!fn()) { if (Date.now() - t0 > ms) throw new Error('timeout'); await new Promise((r) => setTimeout(r, 10)) } }

/** A simulation with its first run (v1), priced through the scripted hero path. */
async function pricedSim() {
  const { useApp } = await import('@/store/app')
  const { handleMessage, answerQuestion } = await import('./script')
  const id = await handleMessage(null, 'Price Phosfusion 65-35 against TSP')
  await waitFor(() => useApp.getState().sims[id].thread.some((m) => m.kind === 'question'))
  await answerQuestion(id, useApp.getState().sims[id].thread.find((m) => m.kind === 'question')!.id, 'standard')
  await waitFor(() => useApp.getState().sims[id].runs.length === 1 && !useApp.getState().sims[id].busy)
  return id
}

describe('backend engine · sulphur sensitivity', () => {
  // POST /api/engine/sensitivity for Phosfusion 65-35 vs TSP on the demo data, 700 → 1,000 USD/t.
  const point = (sulphurPrice: number, cgmNew: number, cgmRef: number) => ({ sulphurPrice, cgmNew, cgmRef, deltaCgm: cgmNew - cgmRef })
  const real: Sensitivity = {
    variable: 'sulphur',
    points: [point(700, 35.0, 87.41), point(750, 27.01, 61.76), point(800, 19.01, 36.12), point(850, 11.01, 10.47), point(900, 3.02, -15.18), point(950, -4.98, -40.82), point(1000, -12.98, -66.47)],
    breakEvens: [
      { productId: 'phos-65-35', sulphurPrice: 918.86, kind: 'zero_margin', note: '' },
      { productId: 'TSP', sulphurPrice: 870.41, kind: 'zero_margin', note: '' },
      { productId: 'phos-65-35', sulphurPrice: 848.46, kind: 'crossover', note: '' },
    ],
  }
  const lastText = async (id: string) => { const { useApp } = await import('@/store/app'); const texts = useApp.getState().sims[id].thread.filter((m) => m.kind === 'text'); return texts[texts.length - 1].text }

  it('quotes the break-evens of the run’s product and reference, and who earns more on each side of the crossover', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage } = await import('./script')
    const id = await pricedSim()
    backend.sensitivity = real; backend.calls.length = 0
    await handleMessage(id, 'Show the sulphur break-even')
    expect(backend.calls).toEqual(['sensitivity phos-65-35 TSP'])
    const sim = useApp.getState().sims[id]
    expect(sim.busy).toBe(false)
    expect(sim.runs).toHaveLength(1) // a derived answer, not a new version
    expect(sim.thread.some((m) => m.kind === 'tool' && m.label === 'Sulphur sensitivity · 7 points')).toBe(true)
    const text = await lastText(id)
    expect(text).toContain('**Phosfusion 65-35** breaks even (zero margin) at **918.86 USD/t** sulphur')
    expect(text).toContain('**TSP** breaks even at **870.41 USD/t**')
    expect(text).toContain('Both earn the same margin at **848.46 USD/t**: above it Phosfusion 65-35 earns more, below it TSP does')
    expect(text).toContain('Sulphur swept from 700 to 1,000 USD/t')
  })

  it('reads the direction from the curve, and says so when there is no break-even', async () => {
    const { handleMessage } = await import('./script')
    const id = await pricedSim()
    // The mirror image: the reference gains on the product as sulphur rises.
    backend.sensitivity = { ...real, points: real.points.map((p) => point(p.sulphurPrice, p.cgmRef!, p.cgmNew!)) }
    await handleMessage(id, 'sulphur sensitivity?')
    expect(await lastText(id)).toContain('above it TSP earns more, below it Phosfusion 65-35 does')
    backend.sensitivity = { ...real, breakEvens: real.breakEvens.map((b) => ({ ...b, sulphurPrice: null })) }
    await handleMessage(id, 'sulphur sensitivity?')
    expect(await lastText(id)).toContain('No break-even in that range.')
  })
})

describe('backend agent', () => {
  const question = 'Why is this margin so thin compared with last quarter?' // nothing the script recognises

  it('without a model on the backend, an unrecognised question stays with the script', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage } = await import('./script')
    const id = await pricedSim()
    backend.mode = 'script'; backend.calls.length = 0
    await handleMessage(id, question)
    expect(backend.calls).toEqual([])
    const sim = useApp.getState().sims[id]
    expect(sim.runs).toHaveLength(1)
    expect(sim.thread[sim.thread.length - 1]).toMatchObject({ kind: 'text', text: expect.stringContaining('I only quote numbers the engine has produced') })
  })

  it('with a model, the question goes to the backend agent and its events become the thread', async () => {
    const { useApp } = await import('@/store/app')
    const { api } = await import('@/lib/api')
    const { handleMessage, applyChange, dismissChange } = await import('./script')
    const id = await pricedSim()
    const before = useApp.getState().sims[id].thread.length
    const flag = (code: string, severity: 'warning' | 'info') => ({ type: 'flag' as const, payload: { id: code, code, severity, title: code } })
    backend.mode = 'llm'; backend.calls.length = 0
    backend.turn = async (simId, _text, on) => {
      await on({ type: 'step', payload: { label: 'Calling run_engine...', status: 'running' } })
      await on({ type: 'step', payload: { label: 'Pricing phos-65-35 against TSP...', status: 'running' } })
      const run = await api.addRun(simId, useApp.getState().sims[simId].runs[0].input, 'agent', 'Re-run') // the agent saves the run itself
      await on({ type: 'tool', payload: { name: 'run_engine', label: 'Pricing engine · 4 methods (v2)', latencyMs: 45 } })
      await on({ type: 'result', payload: { runId: run.id, version: run.version } })
      for (const e of [flag('P1', 'warning'), flag('C1', 'info'), flag('P1', 'warning')]) await on(e)
      for (const cid of ['c_live', 'c_gone']) await on({ type: 'change', payload: { id: cid, label: 'Value share 50%', reason: 'Test a higher value capture', patch: { valueShare: 0.5 }, before: { valueShare: 1 / 3 }, after: { valueShare: 0.5 } } })
      backend.staged.c_live = { simId, patch: { valueShare: 0.5 } } // c_gone: forgotten, as after a backend restart
      await on({ type: 'text', payload: { content: 'The margin is thin because the anchor sits below the floor.' } })
      await on({ type: 'done', payload: { mode: 'llm' } })
    }
    await handleMessage(id, question)
    expect(backend.calls).toEqual([`turn ${question}`])

    let sim = useApp.getState().sims[id]
    const turn = sim.thread.slice(before)
    expect(turn.map((m) => m.kind)).toEqual(['user', 'steps', 'tool', 'result', 'flag', 'change', 'change', 'text'])
    expect(turn[1]).toMatchObject({ steps: [{ label: 'Calling run_engine', done: true }, { label: 'Pricing phos-65-35 against TSP', done: true }] })
    expect(turn[3]).toMatchObject({ kind: 'result', version: 2 })
    expect(turn[4]).toMatchObject({ flag: { code: 'P1' } }) // warnings only, once
    expect(turn[5]).toMatchObject({ changeId: 'c_live', label: 'Value share 50%', before: '33.3%', after: '50%', status: 'staged', previews: [{ label: 'Value pricing', before: '740.99', after: '791.48' }] })
    expect(sim.busy).toBe(false)
    expect(sim.runs.map((r) => r.version)).toEqual([1, 2]) // the agent's run was read back
    expect(sim.view.version).toBe(2)

    // Applying goes through the backend's change…
    await applyChange(id, turn[5].id)
    sim = useApp.getState().sims[id]
    expect(backend.calls).toContain('apply c_live')
    expect(sim.runs.map((r) => r.version)).toEqual([1, 2, 3])
    expect(sim.runs[2].output.perProduct['phos-65-35'].prices.value).toBeCloseTo(791.48, 2)
    expect(sim.thread.find((m) => m.id === turn[5].id)).toMatchObject({ status: 'applied', appliedVersion: 3 })
    expect(sim.view.version).toBe(3)

    // …and one it has forgotten is still applied, from here.
    await applyChange(id, turn[6].id)
    sim = useApp.getState().sims[id]
    expect(backend.calls).toContain('apply c_gone')
    expect(sim.runs.map((r) => r.version)).toEqual([1, 2, 3, 4])
    expect(sim.runs[3].input.valueShare).toBe(0.5)
    expect(sim.thread.find((m) => m.id === turn[6].id)).toMatchObject({ status: 'applied', appliedVersion: 4 })

    backend.turn = async (_simId, _text, on) => { await on({ type: 'change', payload: { id: 'c_no', label: 'Value share 60%', reason: '', patch: { valueShare: 0.6 }, before: { valueShare: 0.5 }, after: { valueShare: 0.6 } } }) }
    await handleMessage(id, question)
    sim = useApp.getState().sims[id]
    const card = sim.thread[sim.thread.length - 1]
    dismissChange(id, card.id)
    expect(backend.calls).toContain('dismiss c_no')
    expect(useApp.getState().sims[id].thread.find((m) => m.id === card.id)).toMatchObject({ status: 'dismissed' })
    expect(useApp.getState().sims[id].runs).toHaveLength(4)
  })

  it('answering the agent’s question starts its next turn, with the question', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage, answerQuestion } = await import('./script')
    const id = await pricedSim()
    backend.mode = 'llm'; backend.calls.length = 0
    backend.turn = async (_simId, _text, on) => { await on({ type: 'question', payload: { text: 'Netback or FOB Morocco?', options: [{ id: 'netback', label: 'Use netback', sub: null }, { id: 'fob', label: 'Use FOB Morocco', sub: 'Spot quote' }] } }) }
    await handleMessage(id, question)
    const q = useApp.getState().sims[id].thread.filter((m) => m.kind === 'question').pop()!
    backend.turn = async (_simId, _text, on) => { await on({ type: 'text', payload: { content: 'Using the FOB quote.' } }) }
    await answerQuestion(id, q.id, 'fob')
    expect(backend.calls[1]).toBe('turn Netback or FOB Morocco?\n\nAnswer: Use FOB Morocco')
    const thread = useApp.getState().sims[id].thread
    expect(thread.find((m) => m.id === q.id)).toMatchObject({ answered: 'fob' })
    expect(thread.slice(-2)).toMatchObject([{ kind: 'user', text: 'Use FOB Morocco · Spot quote' }, { kind: 'text', text: 'Using the FOB quote.' }])
    expect(useApp.getState().sims[id].runs).toHaveLength(1)
  })
})

describe('knowledge base', () => {
  const ask = 'What do the reports say about freight from Jorf Lasfar to Santos?'
  const passage = (over: Partial<Passage>): Passage => ({ passage: 'Table.', source: 'freights.xlsx', date: '2026-10-01', page: null, pageEnd: null, section: 'Phosphates', docType: 'freight', relevanceScore: 0.3, documentId: 'd1', chunkId: 'k1', ...over })

  it('without a model, a question about the documents is answered with their passages and where they are from', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage } = await import('./script')
    const id = await pricedSim()
    const before = useApp.getState().sims[id].thread.length
    backend.mode = 'script'; backend.calls.length = 0
    backend.passages = [
      passage({ passage: 'Table from freights.xlsx.\n\n| Route | USD/t |\n| --- | --- |\n| Jorf Lasfar – Santos | 25.5 |' }),
      passage({ passage: `${'Supramax rates eased. '.repeat(60)}`, source: 'CRU Fertilizer Week', date: '2026-09-24', page: 4, pageEnd: 5, section: null }),
      passage({ passage: 'Undated note.', source: 'note.txt', date: null, section: null }),
    ]
    await handleMessage(id, ask)
    expect(backend.calls).toEqual([`search 3 ${ask}`])
    const sim = useApp.getState().sims[id]
    const turn = sim.thread.slice(before)
    expect(turn.map((m) => m.kind)).toEqual(['user', 'tool', 'text'])
    expect(turn[1]).toMatchObject({ label: 'Knowledge search · 3 passages' })
    const answer = turn[2] as Extract<typeof turn[number], { kind: 'text' }>
    expect(answer.sources).toEqual(['[1] freights.xlsx, 01 Oct 2026, Phosphates', '[2] CRU Fertilizer Week, 24 Sep 2026, p.4–5', '[3] note.txt'])
    expect(answer.text).toContain('[1] Table from freights.xlsx.\n\n| Route | USD/t |')
    expect(answer.text).toMatch(/\[2\] Supramax rates eased\. .* Supramax rates …\n\n\[3\] Undated note\.$/) // a long passage is cut at a word
    expect(answer.text.length).toBeLessThan(1100)
    expect(sim.runs).toHaveLength(1)
    expect(sim.busy).toBe(false)

    backend.passages = []
    await handleMessage(id, ask)
    const thread = useApp.getState().sims[id].thread
    expect(thread.slice(-2)).toMatchObject([{ kind: 'tool', label: 'Knowledge search · 0 passages' }, { kind: 'text', text: 'I found nothing about that in the indexed documents.' }])
  })

  it('with a model, the agent answers and its citations become the chips of its text', async () => {
    const { useApp } = await import('@/store/app')
    const { handleMessage } = await import('./script')
    const id = await pricedSim()
    const before = useApp.getState().sims[id].thread.length
    backend.mode = 'llm'; backend.calls.length = 0
    backend.turn = async (_simId, _text, on) => {
      await on({ type: 'step', payload: { label: 'Searching the indexed documents...', status: 'running' } })
      await on({ type: 'tool', payload: { name: 'search_knowledge', label: 'Knowledge search · 2 passages', latencyMs: 12 } })
      await on({ type: 'citation', payload: { index: 1, label: 'freights.xlsx, 01-Oct-2026, Phosphates', source: 'freights.xlsx', passage: 'Table.' } })
      await on({ type: 'citation', payload: { index: 2, label: 'CRU Fertilizer Week, 24-Sep-2026, p.4', source: 'CRU Fertilizer Week', passage: 'Rates eased.' } })
      await on({ type: 'text', payload: { content: 'The rate is 25.5 USD/t [1]; rates eased in September [2].' } })
      await on({ type: 'text', payload: { content: 'Anything else?' } })
      await on({ type: 'done', payload: { mode: 'llm' } })
    }
    await handleMessage(id, ask)
    expect(backend.calls).toEqual([`turn ${ask}`]) // not the search endpoint: the agent searches itself
    const turn = useApp.getState().sims[id].thread.slice(before)
    expect(turn.map((m) => m.kind)).toEqual(['user', 'steps', 'tool', 'text', 'text'])
    expect(turn[3]).toMatchObject({ text: 'The rate is 25.5 USD/t [1]; rates eased in September [2].', sources: ['[1] freights.xlsx, 01-Oct-2026, Phosphates', '[2] CRU Fertilizer Week, 24-Sep-2026, p.4'] })
    expect(turn[4]).toMatchObject({ text: 'Anything else?', sources: [] }) // the citations belong to the text they came before
  })
})
