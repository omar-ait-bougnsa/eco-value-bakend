import { useMemo, useRef } from 'react'
import type { Ctx } from '@/engine/run'
import { periodLabel, samePeriod } from '@/engine/period'
import type { ProductResult, Run, RunInput, RunOutput } from '@/engine/types'
import { api } from '@/lib/api'
import { useQuery } from '@/lib/query'
import { useApp } from '@/store/app'
import type { Simulation } from '@/store/types'

export interface SimData {
  sim: Simulation
  run: Run
  input: RunInput
  out: RunOutput
  derived: boolean
  derivedLabel: string
  /** A derived view the backend is still calculating: `out` is what was on screen before. */
  loading: boolean
  /** Why the backend could not calculate the derived view. `out` is then the run as saved. */
  error: string | null
  result: ProductResult
  compare: Run | null
  ctx: Ctx
}

/** The active run, optionally re-derived by the backend for another analysis period / reference (view switches, not new runs). */
export function useSimData(sim: Simulation | undefined): SimData | null {
  const products = useApp((s) => s.products)
  const uploads = useApp((s) => s.uploads)
  const params = useApp((s) => s.params)
  const snapshots = useApp((s) => s.snapshots)
  const compareWith = useApp((s) => s.ui.compareWith)
  const run = sim?.runs.length ? sim.runs[Math.min(sim.view.version, sim.runs.length) - 1] ?? sim.runs[sim.runs.length - 1] : undefined
  const per = sim?.view.period, ref = sim?.view.ref
  const periodChanged = !!run && !!per && !samePeriod(per, { from: run.input.periodFrom, to: run.input.periodTo })
  const derived = !!run && (periodChanged || ref !== run.input.referenceId)
  const input = useMemo<RunInput | undefined>(
    () => (run && derived && per && ref ? { ...run.input, periodFrom: per.from, periodTo: per.to, referenceId: ref } : run?.input),
    [run, derived, per?.from, per?.to, ref], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const q = useQuery(derived && input ? `run:${JSON.stringify(input)}` : null, () => api.engineRun(input!).then((r) => r.output))
  // While a derived view is on its way, the numbers on screen stay those of the view before it.
  const shown = useRef<{ key: string; out: RunOutput } | null>(null)
  return useMemo(() => {
    if (!sim || !run || !input) return null
    const ctx: Ctx = { products, snapshots, uploads, params }
    const key = `${sim.id}:${run.id}`
    const out = !derived ? run.output : q.data ?? (shown.current?.key === key && !q.error ? shown.current.out : run.output)
    shown.current = { key, out }
    const pid = input.productIds.includes(sim.view.product) ? sim.view.product : input.productIds[0]
    const bits: string[] = []
    if (periodChanged && per) bits.push(`analysis period ${periodLabel(per)}`)
    if (ref !== run.input.referenceId) bits.push(`vs ${ref}`)
    const compare = compareWith ? sim.runs[compareWith - 1] ?? null : null
    return { sim, run, input, out, derived, derivedLabel: bits.join(' · '), loading: derived && q.loading, error: derived ? q.error : null, result: out.perProduct[pid], compare, ctx }
  }, [sim, run, input, derived, periodChanged, q.data, q.loading, q.error, products, snapshots, uploads, params, compareWith]) // eslint-disable-line react-hooks/exhaustive-deps
}
