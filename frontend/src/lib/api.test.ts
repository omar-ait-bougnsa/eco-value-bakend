import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type AgentEvent } from './api'

// A what-if turn as the backend sends it (POST /api/simulations/{id}/messages).
const FRAMES = [
  'event: step\ndata: {"id":"step_76534c24","type":"step","payload":{"label":"Staging what-if for value share 50%...","status":"running"}}\n\n',
  'event: change\ndata: {"id":"change_40d7aa32","type":"change","payload":{"id":"c_80ee0dcb","simulationId":"s093dfd1cfe","baseVersion":1,"label":"Value share 50%","reason":"Test agronomic value capture increase to 50%","patch":{"valueShare":0.5},"before":{"valueShare":0.3333333333333333},"after":{"valueShare":0.5},"status":"staged"}}\n\n',
  'event: text\ndata: {"id":"text_79a41003","type":"text","payload":{"content":"Sulphur 100 → 1,000 USD/t.\\n\\n• **Apply & re-run** to create version 2."}}\n\n',
  'event: done\ndata: {"id":"done_49d5cdcd","type":"done","payload":{"mode":"script"}}\n\n',
]

/** A response whose body arrives in pieces of `size` bytes, wherever that cuts the frames (or a character). */
function streamed(text: string, size: number, init?: ResponseInit) {
  const bytes = new TextEncoder().encode(text)
  return new Response(new ReadableStream({ start(c) { for (let i = 0; i < bytes.length; i += size) c.enqueue(bytes.slice(i, i + size)); c.close() } }), init)
}

afterEach(() => vi.unstubAllGlobals())

describe('api.agentTurn', () => {
  it.each([1, 7, 64, 100_000])('reads the events in order from a stream cut every %i bytes', async (size) => {
    const fetch = vi.fn(async () => streamed(FRAMES.join(''), size))
    vi.stubGlobal('fetch', fetch)
    const seen: AgentEvent[] = []
    // A slow handler must not let the next event overtake it.
    await api.agentTurn('s1', 'What if the value share is 50%?', async (e) => { await new Promise((r) => setTimeout(r, e.type === 'step' ? 5 : 0)); seen.push(e) })
    expect(fetch).toHaveBeenCalledWith('/api/simulations/s1/messages', expect.objectContaining({ method: 'POST', body: JSON.stringify({ text: 'What if the value share is 50%?' }) }))
    expect(seen.map((e) => e.type)).toEqual(['step', 'change', 'text', 'done'])
    expect(seen[1]).toMatchObject({ payload: { id: 'c_80ee0dcb', patch: { valueShare: 0.5 }, before: { valueShare: 0.3333333333333333 } } })
    expect(seen[2]).toMatchObject({ payload: { content: 'Sulphur 100 → 1,000 USD/t.\n\n• **Apply & re-run** to create version 2.' } })
  })

  it('reads a last event that has no blank line after it, and CRLF line ends', async () => {
    vi.stubGlobal('fetch', async () => streamed(FRAMES.join('').replaceAll('\n', '\r\n').trimEnd(), 16))
    const seen: string[] = []
    await api.agentTurn('s1', 'x', (e) => void seen.push(e.type))
    expect(seen).toEqual(['step', 'change', 'text', 'done'])
  })

  it('fails with the backend’s message when the simulation is unknown', async () => {
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ detail: "Simulation 'nope' not found" }), { status: 404 }))
    await expect(api.agentTurn('nope', 'x', () => {})).rejects.toThrow("Simulation 'nope' not found")
  })
})
