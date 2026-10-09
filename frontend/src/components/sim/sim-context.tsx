import { useMemo } from 'react'
import type { Ctx } from '@/engine/run'
import { runEngine } from '@/engine/run'
import { periodLabel, samePeriod } from '@/engine/period'
import type { ProductResult, Run, RunInput, RunOutput } from '@/engine/types'
import { useApp } from '@/store/app'
import type { Simulation } from '@/store/types'

export interface SimData {
  sim: Simulation
  run: Run
  input: RunInput
  out: RunOutput
  derived: boolean
  derivedLabel: string
  result: ProductResult
  compare: Run | null
  ctx: Ctx
}

/** The active run, optionally re-derived for another analysis period / reference (view switches, not new runs). */
export function useSimData(sim: Simulation | undefined): SimData | null {
  const products = useApp((s) => s.products)
  const uploads = useApp((s) => s.uploads)
  const params = useApp((s) => s.params)
  const snapshots = useApp((s) => s.snapshots)
  const compareWith = useApp((s) => s.ui.compareWith)
  return useMemo(() => {
    if (!sim || !sim.runs.length) return null
    const ctx: Ctx = { products, snapshots, uploads, params }
    const run = sim.runs[Math.min(sim.view.version, sim.runs.length) - 1] ?? sim.runs[sim.runs.length - 1]
    const per = sim.view.period, ref = sim.view.ref
    const runPer = { from: run.input.periodFrom, to: run.input.periodTo }
    const periodChanged = !samePeriod(per, runPer)
    const derived = periodChanged || ref !== run.input.referenceId
    const input: RunInput = derived ? { ...run.input, periodFrom: per.from, periodTo: per.to, referenceId: ref } : run.input
    const out = derived ? runEngine(input, ctx) : run.output
    const pid = input.productIds.includes(sim.view.product) ? sim.view.product : input.productIds[0]
    const bits: string[] = []
    if (periodChanged) bits.push(`analysis period ${periodLabel(per)}`)
    if (ref !== run.input.referenceId) bits.push(`vs ${ref}`)
    const compare = compareWith ? sim.runs[compareWith - 1] ?? null : null
    return { sim, run, input, out, derived, derivedLabel: bits.join(' · '), result: out.perProduct[pid], compare, ctx }
  }, [sim, products, snapshots, uploads, params, compareWith])
}
