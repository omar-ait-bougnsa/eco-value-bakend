import type { Ctx } from '@/engine/run'
import type { Run } from '@/engine/types'
import { leadResult } from './memo'

// Optional LLM fallback via OpenRouter. The key is read from the environment only (.env, never committed).
export async function askLLM(question: string, grounding: { run: Run; ctx: Ctx } | null): Promise<string | null> {
  const key = import.meta.env.VITE_OPENROUTER_API_KEY as string | undefined
  if (!key) return null
  const model = (import.meta.env.VITE_OPENROUTER_MODEL as string | undefined) ?? 'anthropic/claude-sonnet-4.5'
  const context = grounding
    ? JSON.stringify({ reference: grounding.run.input.referenceId, analysisPeriod: `${grounding.run.input.periodFrom} → ${grounding.run.input.periodTo}`, result: (({ lines, ramp, waterfall, carbonScenarios, methods, ...rest }) => rest)(leadResult(grounding.run)), flags: grounding.run.output.flags.map((f) => f.title) })
    : 'No run yet.'
  try {
    const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: 'You are the Eco Value Simulator agent for OCP pricing managers. You gather, check and explain; the engine calculates; people decide. Never invent or compute numbers: quote only figures present in CONTEXT. If asked for something not in CONTEXT, say so. Be brief and plain. Answer in English.' },
          { role: 'user', content: `CONTEXT: ${context}\n\nQUESTION: ${question}` },
        ],
      }),
    })
    if (!res.ok) return null
    const j = await res.json()
    return j.choices?.[0]?.message?.content ?? null
  } catch { return null }
}
