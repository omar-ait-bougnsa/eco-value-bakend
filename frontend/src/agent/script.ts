import { DECK_TSP_COST, getProduct, resolveSnapshot, runEngine, fmtDay } from '@/engine/run'
import { PERIOD_PRESETS, periodLabel, yearPeriod, YTD, samePeriod } from '@/engine/period'
import type { Parameters, RefId, Run, RunInput } from '@/engine/types'
import { ctxOf, defaultRunInput, makeView, uid, useApp } from '@/store/app'
import type { Msg, NewMsg } from '@/store/types'
import { dayShort, f0, f2, pct, sleep } from '@/lib/format'
import { sourcesFor, summaryText, leadResult, buildMemo } from './memo'
import { askLLM } from './llm'
import { api, report, type Passage, type Sensitivity } from '@/lib/api'

const S = () => useApp.getState()
const push = (simId: string, m: NewMsg) => S().pushMsg(simId, { id: uid(), ...m } as Msg)

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

export const SUGGESTIONS = ['What if the value share is 50%?', 'Why is the anchor below the floor?', 'Show the 2025 analysis period', 'Show the sulphur break-even']

function titleFor(input: RunInput, ctx = ctxOf(S())) {
  const names = input.productIds.map((id) => getProduct(ctx, id).name.replace('Phosfusion ', ''))
  const base = input.productIds.length > 1 ? `Phosfusion ${names.join(' & ')}` : getProduct(ctx, input.productIds[0]).name
  const per = { from: input.periodFrom, to: input.periodTo }
  return `${base} vs ${input.referenceId}${samePeriod(per, YTD) ? '' : ` · ${periodLabel(per)}`}`
}

export function parseProducts(t: string): string[] {
  const ids: string[] = []
  if (/50[-\s]?50/.test(t)) ids.push('phos-50-50')
  if (/65[-\s]?35/.test(t)) ids.push('phos-65-35')
  if (/45[-\s]?55/.test(t)) ids.push('phos-45-55-cr')
  if (!ids.length && /phos/.test(t)) ids.push('phos-65-35')
  return ids
}
export function parseRef(t: string): RefId | null {
  if (/\bdap\b/.test(t)) return 'DAP'
  if (/\bmap\b/.test(t)) return 'MAP'
  if (/\btsp\b/.test(t)) return 'TSP'
  return null
}

/* ───────────────────────── pricing run ───────────────────────── */

export async function startPricing(simId: string, input: RunInput) {
  const st = S(); st.setBusy(simId, true)
  const ctx = ctxOf(st)
  const prod = getProduct(ctx, input.productIds[0]); const ref = input.referenceId
  const snap = resolveSnapshot(ctx, input)
  const per = periodLabel({ from: input.periodFrom, to: input.periodTo })
  const argus = st.uploads.filter((u) => /argus/i.test(u.name)).sort((a, b) => b.fileDate.localeCompare(a.fileDate))[0]
  const freight = st.uploads.filter((u) => u.type === 'freight').sort((a, b) => b.dataThrough.localeCompare(a.dataThrough))[0]
  const labels = snap.id === 'today'
    ? [`Reading Argus quotes (${argus ? dayShort(argus.fileDate) : '—'})`, `Reading CRU prices & freight (${freight ? dayShort(freight.dataThrough) : '—'})`, `Building recipe cost: ${prod.name}, ${ref}`, 'Reading agro trials & crop price', 'Checking sources']
    : [`Loading prices for ${per} (CRU averages)`, `Building recipe cost: ${prod.name}, ${ref}`, 'Reading agro trials & crop price', 'Checking sources']
  const stepsId = push(simId, { kind: 'steps', steps: labels.map((l) => ({ label: l, done: false })) })
  for (let i = 0; i < labels.length; i++) {
    await sleep(380)
    S().patchMsg(simId, stepsId, { steps: labels.map((l, j) => ({ label: l, done: j <= i })) })
  }
  const probe = runEngine(input, ctx)
  const d1 = probe.flags.find((f) => f.code === 'D1')
  if (d1) { await sleep(150); push(simId, { kind: 'flag', flag: d1 }) }
  const s1 = probe.flags.find((f) => f.code === 'S1' && f.severity === 'warning')
  if (s1) {
    await sleep(250)
    const std = probe.perProduct[input.productIds[0]].refCost ?? 0
    push(simId, {
      kind: 'question', flagId: 'S1', pending: { input },
      text: `${ref}’s full production cost differs between sources: ${DECK_TSP_COST} USD/t in the business-case deck, ${f2(std)} USD/t in Standard cost 2026. Which should I use?`,
      options: [
        { id: 'standard', label: `Use ${f2(std)}`, sub: 'Standard cost 2026', primary: true },
        { id: 'deck', label: `Use ${DECK_TSP_COST}`, sub: 'Business-case deck' },
        { id: 'sources', label: 'Open sources' },
      ],
    })
    st.setBusy(simId, false)
    return
  }
  await finishRun(simId, input, 'user', 'Initial run')
}

async function finishRun(simId: string, input: RunInput, by: Run['createdBy'], summary: string) {
  S().setBusy(simId, true)
  const ctx = ctxOf(S())
  await sleep(250)
  const toolId = push(simId, { kind: 'tool', label: `Pricing engine · ${input.methods.length} methods · running…` })
  await sleep(750)
  let run: Run
  try { run = await S().addRun(simId, input, by, summary) } catch (e) { S().patchMsg(simId, toolId, { label: 'Pricing engine · failed' }); S().setBusy(simId, false); report(e); return }
  S().patchMsg(simId, toolId, { label: `Pricing engine · ${input.methods.length} methods · v${run.version} · 1.2 s` })
  const multi = input.productIds.length > 1
  if (multi) {
    const lines = input.productIds.map((id) => { const r = run.output.perProduct[id]; return `- **${r.name}**: anchor ${f2(r.anchorPrice)} USD/t, CGM ${f2(r.cgm)} USD/t (floor ${f2(r.floor)}, ceiling ${f2(r.ceiling)})` }).join('\n')
    await streamText(simId, `Both products priced against ${input.referenceId}:\n\n${lines}\n\nThe pivot bar lets you pin a product and compare strategies, or pin a strategy and compare products.`, { sources: sourcesFor(run, ctx) })
  } else {
    await streamText(simId, summaryText(run), { sources: sourcesFor(run, ctx) })
  }
  push(simId, { kind: 'result', version: run.version })
  for (const f of run.output.flags.filter((x) => ['U1', 'C2', 'A1'].includes(x.code) && x.severity !== 'resolved')) { await sleep(180); push(simId, { kind: 'flag', flag: f }) }
  push(simId, { kind: 'suggest', items: SUGGESTIONS })
  S().setBusy(simId, false)
}

export async function answerQuestion(simId: string, msgId: string, optionId: string) {
  const sim = S().sims[simId]; const m = sim.thread.find((x) => x.id === msgId)
  if (!m || m.kind !== 'question' || m.answered) return
  if (optionId === 'sources' && m.pending) {
    await streamText(simId, `**Sources.** Standard cost 2026 (Pricing model.xlsx, “Standard Production cost” K45:N45) gives ${f2(runEngine(m.pending.input, ctxOf(S())).perProduct[m.pending.input.productIds[0]].refCost)} USD/t for TSP. The business-case deck (slide 2) quotes ${DECK_TSP_COST} USD/t. The workbook is the source of truth, but your call.`)
    return
  }
  const opt = m.options.find((o) => o.id === optionId)!
  S().patchMsg(simId, msgId, { answered: optionId })
  push(simId, { kind: 'user', text: [opt.label, opt.sub].filter(Boolean).join(' · ') })
  if (!m.pending) {
    // A question from the backend agent: the answer starts its next turn. It keeps no history, so the question goes with it.
    if (await agentLive()) await askAgent(simId, `${m.text}\n\nAnswer: ${opt.label}`)
    else await streamText(simId, 'The agent’s model is not available right now, so I cannot follow up on that answer. Ask again in a moment.')
    return
  }
  const base = m.pending.input
  const input: RunInput = { ...base, resolved: { ...base.resolved, S1: optionId }, refCostOverride: optionId === 'deck' ? DECK_TSP_COST : null }
  await finishRun(simId, input, 'user', 'Initial run')
}

/* ───────────────────────── what-ifs ───────────────────────── */

interface Parsed { patch: Partial<RunInput>; label: string; before: string; after: string }

export function parseWhatIf(t: string, last: RunInput): Parsed | null {
  const num = (re: RegExp) => { const m = t.match(re); return m ? parseFloat(m[1]) : null }
  let n: number | null
  if (/value\s*shar/.test(t) && (n = num(/(\d+(?:\.\d+)?)\s*%?/)) != null) return { patch: { valueShare: n / 100 }, label: 'Value share kept by OCP', before: pct(last.valueShare), after: pct(n / 100) }
  if (/(cost[- ]?plus|margin)/.test(t) && (n = num(/(\d+(?:\.\d+)?)\s*%/)) != null) return { patch: { costPlusMargin: n / 100 }, label: 'Cost-plus margin', before: pct(last.costPlusMargin), after: pct(n / 100) }
  if (/carbon\s*price/.test(t) && (n = num(/(\d+(?:\.\d+)?)/)) != null) return { patch: { carbonPrice: n }, label: 'Carbon price', before: `${last.carbonPrice} USD/t CO₂`, after: `${n} USD/t CO₂` }
  if (/market\s*share/.test(t) && (n = num(/(\d+(?:\.\d+)?)\s*%?/)) != null) return { patch: { marketShare: n / 100 }, label: 'Market share captured', before: pct(last.marketShare), after: pct(n / 100) }
  if (/(benchmark|competitor)/.test(t) && (n = num(/(\d+(?:\.\d+)?)/)) != null) return { patch: { benchmark: n }, label: 'Market benchmark', before: last.benchmark == null ? 'not set' : `${f2(last.benchmark)} USD/t`, after: `${f2(n)} USD/t` }
  if (/full\s*cost|d&a|depreciation/.test(t)) return { patch: { fullCost: !last.fullCost }, label: 'Include manufacturing & D&A', before: last.fullCost ? 'Yes' : 'No', after: last.fullCost ? 'No' : 'Yes' }
  if (/anchor/.test(t) && /value/.test(t)) return { patch: { anchor: 'value' }, label: 'Anchor method', before: last.anchor, after: 'value' }
  if (/anchor/.test(t) && /cost/.test(t)) return { patch: { anchor: 'costPlus' }, label: 'Anchor method', before: last.anchor, after: 'costPlus' }
  return null
}

/** `changeId` is set when the backend agent staged the change: applying and dismissing then go through it. */
export function stageChange(simId: string, p: Parsed, changeId?: string) {
  const sim = S().sims[simId]; const last = sim.runs[sim.runs.length - 1]
  const ctx = ctxOf(S())
  const next = { ...last.input, ...p.patch }
  const a = leadResult(last); const b = leadResult({ ...last, output: runEngine(next, ctx) } as Run)
  const previews: { label: string; before: string; after: string }[] = []
  const cmp = (label: string, x: number | null, y: number | null) => { if (x != null && y != null && Math.abs(x - y) > 0.004) previews.push({ label, before: f2(x), after: f2(y) }) }
  cmp('Value pricing', a.prices.value, b.prices.value); cmp('Cost-plus', a.prices.costPlus, b.prices.costPlus); cmp('Recommended anchor', a.anchorPrice, b.anchorPrice); cmp('CGM per t', a.cgm, b.cgm)
  if (a.totalMargin != null && b.totalMargin != null && Math.abs(a.totalMargin - b.totalMargin) > 1e3) previews.push({ label: 'Total margin (M USD/yr)', before: (a.totalMargin / 1e6).toFixed(1), after: (b.totalMargin / 1e6).toFixed(1) })
  push(simId, { kind: 'change', label: p.label, before: p.before, after: p.after, previews: previews.slice(0, 3), patch: p.patch, status: 'staged', changeId })
}

export async function applyChange(simId: string, msgId: string) {
  const sim = S().sims[simId]; const m = sim.thread.find((x) => x.id === msgId)
  if (!m || m.kind !== 'change' || m.status !== 'staged') return
  const last = sim.runs[sim.runs.length - 1]
  const input: RunInput = { ...last.input, ...m.patch, comment: `${m.label}: ${m.before} → ${m.after}` }
  const summary = `${m.label} ${m.before} → ${m.after}`
  S().setBusy(simId, true)
  let run: Run
  try {
    // A change the backend agent staged is applied there. It keeps those in memory only, so once it has forgotten one the same patch is run from here.
    const applied = m.changeId ? await api.applyChange(m.changeId, summary).catch(() => null) : null
    if (applied) await S().syncRuns(simId)
    run = applied ?? await S().addRun(simId, input, 'agent', summary)
  } catch (e) { S().setBusy(simId, false); report(e); return }
  S().patchMsg(simId, msgId, { status: 'applied', appliedVersion: run.version })
  const ctx = ctxOf(S())
  const a = leadResult(last); const b = leadResult(run)
  const bits: string[] = []
  if (b.prices.value != null && a.prices.value != null && Math.abs(b.prices.value - a.prices.value) > 0.004) bits.push(`value pricing ${f2(a.prices.value)} → ${f2(b.prices.value)}`)
  if (b.anchorPrice != null && a.anchorPrice != null && Math.abs(b.anchorPrice - a.anchorPrice) > 0.004) bits.push(`anchor ${f2(a.anchorPrice)} → ${f2(b.anchorPrice)}`)
  if (b.cgm != null && a.cgm != null && Math.abs(b.cgm - a.cgm) > 0.004) bits.push(`CGM ${f2(a.cgm)} → ${f2(b.cgm)} USD/t`)
  await streamText(simId, `Re-ran as **v${run.version}**. ${bits.length ? 'What changed: ' + bits.join(', ') + '.' : 'Nothing in the price corridor moved.'} Compare it with v${run.version - 1} from the version chip.`, { sources: sourcesFor(run, ctx) })
  S().setBusy(simId, false)
}

export function dismissChange(simId: string, msgId: string) {
  const m = S().sims[simId].thread.find((x) => x.id === msgId)
  if (m?.kind === 'change' && m.changeId) api.dismissChange(m.changeId).catch(() => {}) // the card is dismissed here either way
  S().patchMsg(simId, msgId, { status: 'dismissed' })
}

/* ───────────────────────── backend agent & engine ───────────────────────── */

/** The backend agent takes free text only when it has a model: without one, its scripted fallback knows fewer requests than the script here. */
const agentLive = () => api.agentStatus().then((s) => s.mode === 'llm', () => false)

const SHARES = ['valueShare', 'costPlusMargin', 'marketShare', 'marketingPct']
const shown = (k: string, v: unknown) => (v == null ? 'not set' : SHARES.includes(k) ? pct(v as number) : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : Array.isArray(v) ? v.join(', ') : String(v))

/** One turn of the backend agent: its events become thread messages, and the runs it saved are read back. */
async function askAgent(simId: string, text: string) {
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
      if (e.type === 'step') { steps.push(e.payload.label.replace(/\.+$/, '')); showSteps(false) }
      else if (e.type === 'tool') push(simId, { kind: 'tool', label: e.payload.label })
      else if (e.type === 'flag') {
        // The agent sends every flag of the run, each time it checks: the thread keeps the warnings, once.
        if (['warning', 'error'].includes(e.payload.severity) && !flagged.has(e.payload.code)) { flagged.add(e.payload.code); push(simId, { kind: 'flag', flag: e.payload }) }
      }
      else if (e.type === 'question') push(simId, { kind: 'question', flagId: 'agent', text: e.payload.text, options: e.payload.options.map((o) => ({ id: o.id, label: o.label, sub: o.sub ?? undefined })) })
      else if (e.type === 'result') { await S().syncRuns(simId); push(simId, { kind: 'result', version: e.payload.version }) }
      else if (e.type === 'change') {
        const side = (o: Record<string, unknown>) => Object.entries(o).map(([k, v]) => shown(k, v)).join(', ')
        stageChange(simId, { patch: e.payload.patch, label: e.payload.label, before: side(e.payload.before), after: side(e.payload.after) }, e.payload.id)
      }
      else if (e.type === 'citation') sources.push(`[${e.payload.index}] ${e.payload.label}`)
      else if (e.type === 'text') { await streamText(simId, e.payload.content, { sources }); sources = [] }
      else if (e.type === 'error') await streamText(simId, e.payload.message)
    })
  } catch (e) { report(e) }
  if (steps.length) showSteps(true)
  S().setBusy(simId, false)
}

/** `CRU Fertilizer Week, 24 Sep 2026, p.4`: the document, its date, and the page (or the sheet / heading) of the passage. */
function citation(p: Passage) {
  const where = p.page ? (p.pageEnd && p.pageEnd !== p.page ? `p.${p.page}–${p.pageEnd}` : `p.${p.page}`) : p.section
  return [p.source, p.date && fmtDay(p.date), where].filter(Boolean).join(', ')
}

/** What the indexed documents say, in their own words: the passages closest to the question, each with its source. */
async function searchDocuments(simId: string, question: string) {
  const toolId = push(simId, { kind: 'tool', label: 'Knowledge search · running…' })
  let found: Passage[]
  try { found = (await api.searchKnowledge(question, 3)).results } catch (e) { S().patchMsg(simId, toolId, { label: 'Knowledge search · failed' }); report(e); return }
  S().patchMsg(simId, toolId, { label: `Knowledge search · ${found.length} passage${found.length === 1 ? '' : 's'}` })
  if (!found.length) { await streamText(simId, 'I found nothing about that in the indexed documents.'); return }
  const excerpt = (t: string) => (t.length <= 700 ? t : t.slice(0, t.lastIndexOf(' ', 700)) + ' …')
  // The marker comes first: after a passage that ends in a table, Markdown would read it as one more cell.
  await streamText(simId, `Here is what the indexed documents say:\n\n${found.map((p, i) => `[${i + 1}] ${excerpt(p.passage)}`).join('\n\n')}`, { sources: found.map((p, i) => `[${i + 1}] ${citation(p)}`) })
}

/** Sulphur break-evens from the backend engine, for the simulation's product and reference (the defaults before a first run). */
async function sulphurSensitivity(simId: string) {
  const st = S(); const sim = st.sims[simId]; const last = sim.runs[sim.runs.length - 1]
  const productId = last?.input.productIds[0] ?? st.defaultInput.productIds[0]; const ref = last?.input.referenceId ?? st.params.defaultReference
  const name = getProduct(ctxOf(st), productId).name
  const toolId = push(simId, { kind: 'tool', label: 'Sulphur sensitivity · running…' })
  let r: Sensitivity
  try { r = await api.sensitivity(productId, ref) } catch (e) { S().patchMsg(simId, toolId, { label: 'Sulphur sensitivity · failed' }); report(e); return }
  S().patchMsg(simId, toolId, { label: `Sulphur sensitivity · ${r.points.length} points` })
  const at = (id: string, kind: 'zero_margin' | 'crossover') => r.breakEvens.find((b) => b.productId === id && b.kind === kind)?.sulphurPrice
  const lo = r.points[0]; const hi = r.points[r.points.length - 1]
  const zero = at(productId, 'zero_margin'); const zeroRef = at(ref, 'zero_margin'); const cross = at(productId, 'crossover')
  // The margin gap moves in a straight line with the sulphur price, so its two ends tell which product earns more above the crossover.
  const rising = (hi.deltaCgm ?? 0) > (lo.deltaCgm ?? 0)
  const today = st.snapshots.find((s) => s.id === 'today')?.inputs.sulphur
  const lines = [
    zero != null && `- **${name}** breaks even (zero margin) at **${f2(zero)} USD/t** sulphur`,
    zeroRef != null && `- **${ref}** breaks even at **${f2(zeroRef)} USD/t**`,
    cross != null && `- Both earn the same margin at **${f2(cross)} USD/t**: above it ${rising ? name : ref} earns more, below it ${rising ? ref : name} does`,
  ].filter(Boolean)
  await streamText(simId, `Sulphur swept from ${f0(lo.sulphurPrice)} to ${f0(hi.sulphurPrice)} USD/t, with ${name} at its reference-minus anchor and the other inputs from today’s prices and the workspace parameters.\n\n${lines.length ? lines.join('\n') : 'No break-even in that range.'}${today != null ? `\n\nSulphur is at ${f2(today)} USD/t today.` : ''}`)
}

/* ───────────────────────── free text ───────────────────────── */

export async function handleMessage(simIdIn: string | null, raw: string): Promise<string> {
  const text = raw.trim(); const t = text.toLowerCase()
  const st = S()
  let simId = simIdIn
  const isPricing = /(price|prix|calcul|run|simulate|compare|compar)/.test(t) && /(phos|50|65|45)/.test(t)

  if (!simId) {
    if (isPricing || /gap|data|données|upload|new/.test(t) || true) {
      const products = parseProducts(t); const ref = parseRef(t)
      if (isPricing && products.length) {
        const input = defaultRunInput(st.params, { productIds: products, referenceId: ref ?? st.params.defaultReference })
        simId = await st.createSim(titleFor(input), input)
        S().setUI({ askOpen: true })
        push(simId, { kind: 'user', text })
        void startPricing(simId, input)
        return simId
      }
      simId = await st.createSim(text.length > 40 ? text.slice(0, 38) + '…' : text, defaultRunInput(st.params))
      S().setUI({ askOpen: true })
      push(simId, { kind: 'user', text })
      await respondOther(simId, t, text)
      return simId
    }
  }
  push(simId!, { kind: 'user', text })
  S().setBusy(simId!, true)
  await sleep(250)

  const sim = S().sims[simId!]; const last = sim.runs[sim.runs.length - 1]
  if (isPricing && !sim.runs.length) {
    const products = parseProducts(t); const ref = parseRef(t)
    const input = defaultRunInput(S().params, { productIds: products.length ? products : ['phos-65-35'], referenceId: ref ?? S().params.defaultReference })
    S().renameSim(simId!, titleFor(input))
    await startPricing(simId!, input); return simId!
  }
  if (last) {
    const m = /use\s*(494|655)/.exec(t)
    if (m) { await streamText(simId!, 'That question has already been resolved. Use the Hypotheses tab to change the TSP cost.') ; S().setBusy(simId!, false); return simId! }
    const w = parseWhatIf(t, last.input)
    if (w && /(what if|set|change|use|make|try|update|if)/.test(t)) {
      await streamText(simId!, `That changes only **${w.label}**. Here is the proposed change — nothing is applied until you confirm.`)
      stageChange(simId!, w); S().setBusy(simId!, false); return simId!
    }
    const yr = /(2025|2024|2023|2022|2021)/.exec(t)
    const l12 = /last 12 months|past year|trailing/.test(t)
    if (l12 && /(period|compare|under|show|switch|use|what)/.test(t)) {
      const pp = PERIOD_PRESETS.find((x) => x.id === 'l12')!.period
      S().setView(simId!, { period: pp, tab: 'overview' })
      const r = runEngine({ ...last.input, periodFrom: pp.from, periodTo: pp.to }, ctxOf(S())).perProduct[last.input.productIds[0]]
      await streamText(simId!, `Switched the analysis period to **Last 12 months** — a derived view. Anchor ${f2(r.anchorPrice)} USD/t against a cost-plus floor of ${f2(r.floor)}.`)
      S().setBusy(simId!, false); return simId!
    }
    if (yr && /(condition|compare|year|snapshot|under|vs|period)/.test(t)) {
      const pp = yearPeriod(+yr[1])
      S().setView(simId!, { period: pp, tab: 'overview' })
      const r = runEngine({ ...last.input, periodFrom: pp.from, periodTo: pp.to }, ctxOf(S())).perProduct[last.input.productIds[0]]
      await streamText(simId!, `Switched the analysis period to **${yr[1]}** — a derived view, not a new run. Anchor ${f2(r.anchorPrice)} USD/t against a cost-plus floor of ${f2(r.floor)}; ${last.input.referenceId} earns ${f2(r.cgmRef)} USD/t. Use “Back” in the banner to return to the run’s period.`)
      S().setBusy(simId!, false); return simId!
    }
    if (/(why|explain).*(floor|below)/.test(t)) {
      const r = leadResult(last)
      await streamText(simId!, `The anchor is reference-minus: it values P2O5 at ${last.input.referenceId}’s price (${f2(r.p2o5ValueRef)} USD per t P2O5) and applies that to the product’s ${pct(getProduct(ctxOf(S()), r.productId).composition.P2O5, 2)} P2O5. That gives ${f2(r.prices.refMinus)} USD/t. The cost-plus floor is unit cost ${f2(r.unitCost)} × (1 + ${pct(last.input.costPlusMargin, 0)}) = ${f2(r.floor)}. ${r.anchorPrice! < r.floor ? 'So the anchor sits below the floor: the nutrients are worth less than the cost plus margin.' : 'The anchor clears the floor.'}`, { sources: sourcesFor(last, ctxOf(S())) })
      S().setBusy(simId!, false); return simId!
    }
    if (/(why|explain).*(value)/.test(t) || /value pric/.test(t)) {
      const r = leadResult(last)
      await streamText(simId!, `Value pricing = reference price ${f2(r.refPrice)} + ${pct(last.input.valueShare)} × ${f2(r.addedValue)} USD/t of crop value created (${last.input.yieldGain} t/ha ÷ ${last.input.appRateNew} t/ha × ${last.input.cropPrice} USD/t) = **${f2(r.prices.value)} USD/t**.`, { sources: sourcesFor(last, ctxOf(S())) })
      S().setBusy(simId!, false); return simId!
    }
    if (/(memo|summar|résumé)/.test(t)) {
      S().setUI({ memoOpen: true })
      const memo = buildMemo(last, ctxOf(S()))
      await streamText(simId!, `I opened the decision memo for v${last.version}. ${memo.sections[0].paragraphs?.[0]}`)
      S().setBusy(simId!, false); return simId!
    }
  }
  await respondOther(simId!, t, text)
  return simId!
}

async function respondOther(simId: string, t: string, raw: string) {
  const st = S()
  S().setBusy(simId, true)
  await sleep(200)
  if (/sensitiv|sensibilit|break[- ]?even|seuil/.test(t)) {
    await sulphurSensitivity(simId)
  } else if (/\b(sources?|reports?|documents?|stud(y|ies)|according to|cite|citations?|rapports?|selon)\b/.test(t)) {
    // With a model the agent reads the passages and answers in its own words; without one, the passages are the answer.
    if (await agentLive()) await askAgent(simId, raw); else await searchDocuments(simId, raw)
  } else if (/(gap|check|données|inconsisten|fresh|stale|upload)/.test(t)) {
    const probe = runEngine(defaultRunInput(st.params), ctxOf(st))
    const d1 = probe.flags.find((f) => f.code === 'D1')
    await streamText(simId, `I checked the data you have uploaded. ${d1 ? 'One discrepancy needs attention:' : 'Nothing looks off.'}`)
    if (d1) push(simId, { kind: 'flag', flag: d1 })
    push(simId, { kind: 'flag', flag: { id: 'Q1', code: 'Q1', severity: 'info', title: 'TSP FOB quote: low 710 > high 691 — check the Argus file' } })
    push(simId, { kind: 'suggest', items: ['Price Phosfusion 65-35 against TSP'] })
  } else if (/(changed|new|latest)/.test(t) && /upload/.test(t)) {
    const u = [...st.uploads].sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt)).slice(0, 2)
    await streamText(simId, `The most recent uploads are ${u.map((x) => `**${x.name}** (file dated ${fmtDay(x.fileDate)}, data through ${fmtDay(x.dataThrough)})`).join(' and ')}.`)
  } else if (/\b(hello|hi|help)\b|what can/.test(t) || !raw) {
    await streamText(simId, 'I can price a product against a reference, check your data for gaps, re-run what-ifs (value share, margin, carbon price, market share), find the sulphur break-even, compare past years, and draft the decision memo. Try “Price Phosfusion 65-35 against TSP”.')
  } else if (await agentLive()) {
    await askAgent(simId, raw)
  } else {
    const sim = S().sims[simId]; const last = sim.runs[sim.runs.length - 1]
    const answer = await askLLM(raw, last ? { run: last, ctx: ctxOf(S()) } : null)
    await streamText(simId, answer ?? 'I can price products against DAP, MAP or TSP, check data freshness, stage what-if changes and draft a memo. I only quote numbers the engine has produced — try “Price Phosfusion 65-35 against TSP”.')
  }
  S().setBusy(simId, false)
}

export { makeView }
export type { Parameters }
