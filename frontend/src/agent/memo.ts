import type { Ctx } from '@/engine/run'
import { METHOD_LABEL } from '@/engine/run'
import type { ProductResult, Run } from '@/engine/types'
import { f2, millions, pct } from '@/lib/format'
import { dayShort } from '@/lib/format'
import { isCurrentPeriod, periodLabel } from '@/engine/period'

export interface Memo { title: string; sections: { title: string; paragraphs?: string[]; items?: { text: string; tone?: 'warning' | 'info' }[] }[]; sources: string[] }

export function sourcesFor(run: Run, ctx: Ctx): string[] {
  const out: string[] = []
  const argus = ctx.uploads.filter((u) => /argus/i.test(u.name)).sort((a, b) => b.fileDate.localeCompare(a.fileDate))[0]
  const per = { from: run.input.periodFrom, to: run.input.periodTo }
  if (isCurrentPeriod(per)) {
    if (argus) out.push(`Prices · ${dayShort(argus.fileDate)}`)
    out.push('Standard cost · 2026')
  } else {
    out.push(`CRU averages · ${periodLabel(per)}`)
  }
  const agro = ctx.uploads.find((u) => u.type === 'agro'); if (agro) out.push(`Agro trials · ${dayShort(agro.fileDate)}`)
  const crop = ctx.uploads.find((u) => u.type === 'crop'); if (crop) out.push(`Crop prices · ${dayShort(crop.fileDate)}`)
  return out
}

export function leadResult(run: Run, productId?: string): ProductResult {
  return run.output.perProduct[productId ?? run.input.productIds[0]]
}

export function summaryText(run: Run, productId?: string): string {
  const r = leadResult(run, productId)
  const below = r.anchorPrice != null && r.anchorPrice < r.floor
  const method = METHOD_LABEL[run.input.anchor].toLowerCase()
  const first = `**Recommended anchor: ${f2(r.anchorPrice)} USD/t (${method}).** ${below ? `That is below the cost-plus floor of ${f2(r.floor)}, so at this price` : `That sits above the cost-plus floor of ${f2(r.floor)}. At this price`} ${r.name} earns ${f2(r.cgm)} USD/t against ${run.input.referenceId}’s ${f2(r.cgmRef)} USD/t.`
  const second = `Value pricing allows up to ${f2(r.ceiling)} USD/t if OCP keeps ${pct(run.input.valueShare)} of the ${f2(r.addedValue)} USD/t of crop value created.${run.input.benchmark == null ? ' Market pricing needs a competitor benchmark.' : ` The competitor benchmark is ${f2(run.input.benchmark)} USD/t.`}`
  return `${first}\n\n${second}`
}

export function buildMemo(run: Run, ctx: Ctx, productId?: string): Memo {
  const r = leadResult(run, productId)
  const i = run.input
  const p2o5 = ctx.products.find((x) => x.id === r.productId)?.composition.P2O5 ?? 0
  const sections: Memo['sections'] = []
  sections.push({ title: 'Recommendation', paragraphs: [`Analysis period: ${periodLabel({ from: i.periodFrom, to: i.periodTo })}.`, `Anchor ${r.name} at ${f2(r.anchorPrice)} USD/t (${METHOD_LABEL[i.anchor].toLowerCase()}). Corridor: ${f2(r.floor)} (cost-plus floor) to ${f2(r.ceiling)} USD/t (value ceiling).`] })
  const why: string[] = []
  if (r.p2o5ValueRef != null) why.push(`${r.name} holds ${pct(p2o5, 2)} P2O5. Valuing P2O5 at ${i.referenceId}’s price (${f2(r.p2o5ValueRef)} USD per t P2O5) gives ${f2(r.prices.refMinus)} USD/t.`)
  why.push(`Its unit cost is ${f2(r.unitCost)} USD/t, against ${f2(r.refCost)} USD/t for ${i.referenceId}${isCurrentPeriod({ from: i.periodFrom, to: i.periodTo }) ? ' — sulphur at 900 USD/t drives the reference cost' : ''}.`)
  sections.push({ title: 'Why', paragraphs: why })
  sections.push({ title: `Margin vs ${i.referenceId}`, paragraphs: [`CGM is ${f2(r.cgm)} USD/t at the anchor, against ${f2(r.cgmRef)} USD/t for ${i.referenceId}. At the ${pct(i.marketShare, 0)} market share assumed, that is about ${millions(r.totalMargin)} M USD per year.`] })
  const open = run.output.flags.filter((f) => f.severity === 'warning' || f.severity === 'error')
  sections.push({ title: 'Risks & open flags', items: open.length ? open.map((f) => ({ text: f.title, tone: 'warning' as const })) : [{ text: 'No open warnings.', tone: 'info' as const }] })
  return { title: `Decision memo · v${run.version}`, sections, sources: sourcesFor(run, ctx) }
}

export function memoMarkdown(m: Memo): string {
  const lines = [`# ${m.title}`, '']
  for (const s of m.sections) {
    lines.push(`## ${s.title}`)
    s.paragraphs?.forEach((p) => lines.push(p, ''))
    s.items?.forEach((it) => lines.push(`- ${it.text}`))
    lines.push('')
  }
  lines.push('## Sources', m.sources.map((s) => `- ${s}`).join('\n'))
  return lines.join('\n')
}
