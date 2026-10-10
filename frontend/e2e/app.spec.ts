import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const SAMPLE = path.resolve(import.meta.dirname, '../../backend/sample-uploads/argus-fob-morocco-30-09-2026.xlsx')

test.beforeEach(async ({ page, request }) => {
  await request.post('/api/reset')
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
})

const dialogs = (page: Page) => page.getByRole('dialog')

test('a product that breaks the rules cannot be saved, and says why next to each field', async ({ page }) => {
  await page.goto('/products')
  await page.getByRole('button', { name: 'Add product' }).click()
  const form = dialogs(page)
  const save = form.getByRole('button', { name: 'Save product' })
  await form.getByLabel('Product name').fill('ffffffff')
  await form.getByLabel('Sulphur quantity').fill('760')
  await expect(form.getByRole('alert').filter({ hasText: /Sulphur quantity must be between 0 and 3/ })).toBeVisible()
  await expect(form.getByText('Name is not a name: one character repeated')).toBeVisible()
  await expect(form.getByLabel('Sulphur quantity')).toHaveAttribute('aria-invalid', 'true')
  await expect(form.getByLabel('Sulphur quantity')).toHaveAttribute('max', '3')
  await expect(save).toBeDisabled()

  await form.getByLabel('Product name').fill('Phosfusion 70-30')
  await form.getByLabel('Rock (dry) quantity').fill('0.7')
  await form.getByLabel('Sulphur quantity').fill('0.1')
  await expect(form.getByTestId('live-cost')).toHaveText('174.00') // 0.7 × 120 + 0.1 × 900, priced by the server
  await expect(save).toBeEnabled()
  await save.click()
  await expect(dialogs(page)).toHaveCount(0)
  await expect(page.getByTestId('products-table')).toContainText('Phosfusion 70-30')
})

test('the product editor shows the cost the list shows, with where the prices come from', async ({ page }) => {
  await page.goto('/products')
  const row = page.getByTestId('products-table').locator('tbody tr').first()
  await expect(row).toContainText('Phosfusion 65-35')
  await expect(row.locator('td').nth(13)).toHaveText('310.90')
  await row.getByRole('button', { name: 'Edit' }).click()
  const form = dialogs(page)
  await expect(form.getByTestId('live-cost')).toHaveText('310.90')
  await expect(form.locator('tbody tr').filter({ hasText: 'Sulphur' })).toContainText('143.94')
  await expect(form.locator('tbody tr').filter({ hasText: 'Rock (dry)' })).toContainText('88.59')
  await expect(form.getByTestId('cost-source')).toContainText('as of 02 Oct 2026')
  await expect(form.locator('tbody')).not.toContainText('0.00')
})

test('a run outside the limits cannot be started', async ({ page }) => {
  await page.getByRole('button', { name: 'Configure run' }).click()
  const form = dialogs(page)
  const run = form.getByRole('button', { name: /^Run/ })
  await expect(run).toBeEnabled()
  await form.getByLabel('Cost-plus margin').fill('900')
  await expect(form.getByRole('alert').filter({ hasText: /Cost-plus margin must be between 0 and 200/ })).toBeVisible()
  await expect(run).toBeDisabled()
  await form.getByLabel('Cost-plus margin').fill('25')
  await expect(run).toBeEnabled()
})

test('an uploaded file is listed once, under its own name', async ({ page }) => {
  await page.goto('/uploads')
  const table = page.getByTestId('uploads-table')
  const upload = async () => {
    await page.locator('input[type=file]').first().setInputFiles(SAMPLE)
    await expect(dialogs(page)).toContainText('argus-fob-morocco-30-09-2026.xlsx')
    await dialogs(page).getByRole('button', { name: 'Use this data' }).click()
    await expect(dialogs(page)).toHaveCount(0)
  }
  await upload()
  await expect(table.getByText('argus-fob-morocco-30-09-2026.xlsx')).toHaveCount(1)
  await upload() // the same file again
  await expect(page.getByText('Already uploaded')).toBeVisible()
  await expect(table.getByText('argus-fob-morocco-30-09-2026.xlsx')).toHaveCount(1)
  await expect(table.getByText('string', { exact: true })).toHaveCount(0)
  await expect(table.locator('tbody tr')).toHaveCount(6)
})

test('a file that cannot be read is refused in the review', async ({ page }) => {
  await page.goto('/uploads')
  await page.locator('input[type=file]').first().setInputFiles({ name: 'prices.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('not a workbook') })
  await expect(dialogs(page).getByRole('alert')).toContainText('could not be read as a .xlsx file')
  await expect(dialogs(page).getByRole('button', { name: 'Use this data' })).toBeDisabled()
})

test('only one dialog is open at a time, and unsaved changes are not replaced', async ({ page }) => {
  await page.goto('/products')
  await page.getByRole('button', { name: 'Add product' }).click()
  await expect(dialogs(page)).toHaveCount(1)
  await page.keyboard.press('Control+Shift+R') // Configure run, while the product editor is open and untouched
  await expect(dialogs(page)).toHaveCount(1)
  await expect(dialogs(page)).toContainText('Configure run')
  await page.keyboard.press('Escape')
  await expect(dialogs(page)).toHaveCount(0)

  await page.getByRole('button', { name: 'Add product' }).click()
  await dialogs(page).getByLabel('Product name').fill('Half typed')
  await page.keyboard.press('Control+Shift+R')
  await expect(page.getByText('Save or close the open form first')).toBeVisible()
  await expect(dialogs(page)).toHaveCount(1)
  await expect(dialogs(page)).toContainText('New product')
  page.once('dialog', (d) => void d.dismiss()) // "Close without saving your changes?" → stay
  await page.keyboard.press('Escape')
  await expect(dialogs(page)).toContainText('New product')
  page.once('dialog', (d) => void d.accept())
  await page.keyboard.press('Escape')
  await expect(dialogs(page)).toHaveCount(0)
})

test('without a model the chat says it is rule-based, and answers a supported request', async ({ page }) => {
  await page.goto('/s/s2')
  await expect(page.getByTestId('agent-status')).toHaveText('Rule-based assistant (AI model switched off)')
  await page.getByPlaceholder('Type one of the supported requests…').fill('Check my data for gaps')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('#ask-ai')).toContainText('I checked the data you have uploaded. One point needs attention:')
  await expect(page.locator('#ask-ai')).toContainText('Prices are 5 months older than freight')
  await page.goto('/')
  await expect(page.getByTestId('home-agent')).toContainText('Rule-based assistant')
})

test('with a model configured the chat names it', async ({ page }) => {
  await page.route('**/api/agent/status', (route) => route.fulfill({ json: { mode: 'llm', provider: 'openrouter', model: 'anthropic/claude-sonnet-5.5', configured: true, enabled: true, fallbackReason: null, label: 'AI model connected', capabilities: 'free-text questions', budget: { spent_usd: 0, cap_usd: 40, remaining_usd: 40 } } }))
  await page.goto('/s/s2')
  await expect(page.getByTestId('agent-status')).toHaveText('AI model connected · anthropic/claude-sonnet-5.5')
  await expect(page.getByPlaceholder('Ask about this simulation…')).toBeVisible()
})

// ───────────────────────── agent jobs ─────────────────────────

const sse = (...frames: { type: string; payload: unknown }[]) => frames.map((f) => `event: ${f.type}\ndata: ${JSON.stringify(f)}\n\n`).join('')
const fakeJob = (state: string, over: object = {}) => ({ id: 'jfake', simulationId: 's', kind: 'message', state, mode: 'script', request: { text: 'Compare Phosfusion 65-35 and Phosfusion 50-50 against DAP' }, result: null, failureCode: null, error: null, transitions: [], createdAt: new Date().toISOString(), startedAt: null, finishedAt: null, timeoutSeconds: 120, ...over })
const ask = async (page: Page, text: string) => { await page.getByRole('textbox').first().fill(text); await page.getByRole('button', { name: 'Send' }).click() }

test('a pricing request runs to completed and its result is on the page', async ({ page, request }) => {
  await ask(page, 'Compare Phosfusion 65-35 and Phosfusion 50-50 against DAP')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Phosfusion 65-35 & 50-50 vs DAP') // named by the agent after its first run
  await expect(page.getByTestId('sim-pending')).toHaveCount(0)
  await expect(page.getByTestId('result-card')).toBeVisible()
  const id = page.url().split('/s/')[1]
  const saved = await (await request.get(`/api/simulations/${id}`)).json()
  expect(saved.job).toMatchObject({ state: 'completed', result: { outcome: 'run', runVersion: 1 } })
  expect(saved.job.transitions.map((t: { state: string }) => t.state)).toEqual(['queued', 'running', 'completed'])
})

for (const [state, pill, error, code] of [
  ['failed', 'Failed', 'costPlusMargin: must be between 0 and 2 (fraction)', 'invalid_input'],
  ['timed_out', 'Timed out', 'No answer after 120 seconds, so the request was stopped. Nothing was left half done: try it again.', 'timed_out'],
] as const) {
  test(`a ${state} job says why, and Retry runs it again`, async ({ page }) => {
    const ended = fakeJob(state, { failureCode: code, error })
    // The first attempt ends badly, as the server would report it. The retry goes to the real server.
    await page.route('**/api/simulations/*/messages', (route) => route.fulfill({ contentType: 'text/event-stream', body: sse({ type: 'job', payload: fakeJob('running') }, { type: 'error', payload: { message: error, code, fatal: true } }, { type: 'job', payload: ended }) }), { times: 1 })
    await ask(page, 'Compare Phosfusion 65-35 and Phosfusion 50-50 against DAP')
    const pending = page.getByTestId('sim-pending')
    await expect(pending).toHaveAttribute('data-state', state)
    await expect(pending).toContainText(pill)
    await expect(page.getByTestId('job-failure')).toContainText(error)
    await expect(page.getByTestId('job-failure')).toContainText(`Job jfake · ${code}`)
    await expect(pending).not.toContainText('Running')
    await page.getByTestId('job-failure').getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByTestId('result-card')).toBeVisible()
    await expect(page.getByTestId('sim-pending')).toHaveCount(0)
  })
}

test('a page reloaded while a job runs shows its stored state, then its end', async ({ page, request }) => {
  const sim = await (await request.post('/api/simulations', { data: { title: 'Reloaded' } })).json()
  let asked = 0
  // The server says the job is running, then, two questions later, that it completed.
  const done = fakeJob('completed', { result: { outcome: 'answer', runVersion: null } })
  await page.route(`**/api/simulations/${sim.id}`, async (route) => route.fulfill({ json: { ...(await (await route.fetch()).json()), job: asked < 3 ? fakeJob('running') : done } }))
  await page.route('**/api/jobs/jfake', (route) => route.fulfill({ json: ++asked < 3 ? fakeJob('running') : done }))
  await page.goto(`/s/${sim.id}`)
  const pending = page.getByTestId('sim-pending')
  await expect(pending).toHaveAttribute('data-state', 'running')
  await expect(pending.getByRole('button', { name: 'Cancel' })).toBeVisible()
  await expect(page.locator('#ask-ai')).toContainText('Still running on the server…')
  await expect(pending).toHaveAttribute('data-state', 'idle', { timeout: 10_000 }) // not "Running" forever
  await expect(page.getByTestId('sim-idle')).toContainText('Nothing has been priced in this simulation yet')
  expect(asked).toBeGreaterThanOrEqual(3)
})

test('a job the server no longer knows is a failure, not an endless "Running"', async ({ page, request }) => {
  const sim = await (await request.post('/api/simulations', { data: { title: 'Lost' } })).json()
  await page.route(`**/api/simulations/${sim.id}`, async (route) => route.fulfill({ json: { ...(await (await route.fetch()).json()), job: fakeJob('running') } }))
  await page.goto(`/s/${sim.id}`) // GET /api/jobs/jfake is a real 404
  await expect(page.getByTestId('sim-pending')).toHaveAttribute('data-state', 'failed')
  await expect(page.getByTestId('job-failure')).toContainText('The server no longer knows this request (job jfake)')
  await expect(page.getByTestId('job-failure').getByRole('button', { name: 'Retry' })).toBeVisible()
})

test('the rule-based assistant refuses what it does not know and offers what it does, as buttons', async ({ page }) => {
  await ask(page, 'write me a poem about fertilizer')
  const chat = page.locator('#ask-ai')
  await expect(chat).toContainText('I am a rule-based assistant, not an AI model')
  await expect(page.getByTestId('sim-pending')).toHaveAttribute('data-state', 'idle') // nothing is "Running"
  await chat.getByRole('button', { name: 'Show product TSP' }).click()
  await expect(chat).toContainText('Raw-material cost: 655.18 USD/t')
  await expect(chat).toContainText('Composition: P2O5 46%')
})
