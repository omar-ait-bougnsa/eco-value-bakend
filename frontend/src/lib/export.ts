import { jsPDF } from 'jspdf'
import * as XLSX from 'xlsx'
import type { Ctx } from '@/engine/run'
import { METHOD_LABEL } from '@/engine/run'
import type { Run } from '@/engine/types'
import { buildMemo, leadResult, memoMarkdown } from '@/agent/memo'

function download(name: string, blob: Blob) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

export function exportMarkdown(title: string, run: Run, ctx: Ctx) {
  download(`${slug(title)}-v${run.version}.md`, new Blob([memoMarkdown(buildMemo(run, ctx))], { type: 'text/markdown' }))
}

export function exportPdf(title: string, run: Run, ctx: Ctx) {
  const m = buildMemo(run, ctx)
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const W = 595, M = 56
  let y = 72
  const clean = (s: string) => s.replace(/\*\*/g, '').replace(/−/g, '-').replace(/₂/g, '2').replace(/→/g, '->')
  doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(113, 113, 122); doc.text('ECO VALUE SIMULATOR', M, y); y += 22
  doc.setFontSize(20); doc.setTextColor(9, 9, 11); doc.text(clean(title), M, y); y += 18
  doc.setFont('helvetica', 'normal'); doc.setFontSize(10); doc.setTextColor(113, 113, 122); doc.text(`${m.title} · ${new Date().toLocaleDateString('en-GB')}`, M, y); y += 30
  const block = (h: string, lines: string[]) => {
    doc.setFont('helvetica', 'bold'); doc.setFontSize(9); doc.setTextColor(113, 113, 122); doc.text(h.toUpperCase(), M, y); y += 14
    doc.setFont('helvetica', 'normal'); doc.setFontSize(11); doc.setTextColor(9, 9, 11)
    for (const l of lines) { const wrapped = doc.splitTextToSize(clean(l), W - M * 2) as string[]; doc.text(wrapped, M, y); y += wrapped.length * 15 + 4 }
    y += 10
  }
  for (const s of m.sections) block(s.title, [...(s.paragraphs ?? []), ...(s.items?.map((i) => '• ' + i.text) ?? [])])
  block('Sources', [m.sources.join('  ·  ')])
  doc.save(`${slug(title)}-v${run.version}.pdf`)
}

export function exportXlsx(title: string, run: Run, ctx: Ctx) {
  const wb = XLSX.utils.book_new()
  const i = run.input
  const inputs = Object.entries(i).filter(([k]) => !['resolved', 'productIds', 'methods'].includes(k)).map(([k, v]) => ({ Input: k, Value: typeof v === 'object' ? JSON.stringify(v) : v }))
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet([{ Input: 'products', Value: i.productIds.join(', ') }, { Input: 'methods', Value: i.methods.join(', ') }, ...inputs]), 'Inputs')
  const out = i.productIds.flatMap((id) => {
    const r = run.output.perProduct[id]
    return r.methods.map((m) => ({ Product: r.name, Method: METHOD_LABEL[m.method], 'Price USD/t': m.price, 'Unit cost USD/t': r.unitCost, 'CGM USD/t': m.cgm, 'CGM USD/t P2O5': m.cgmP2O5, 'Total margin USD/yr': m.totalMargin, 'Δ vs ref CGM': m.deltaVsRef, Anchor: m.method === i.anchor ? 'yes' : '' }))
  })
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(out), 'Outputs')
  const lead = leadResult(run)
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(lead.lines.map((l) => ({ Ingredient: l.label, 't/t': l.qty, 'USD/t': l.price, 'USD per t product': l.usd }))), 'Costing')
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(run.output.flags.map((f) => ({ Code: f.code, Severity: f.severity, Flag: f.title, Detail: f.detail }))), 'Flags')
  void ctx
  XLSX.writeFile(wb, `${slug(title)}-v${run.version}.xlsx`)
}
