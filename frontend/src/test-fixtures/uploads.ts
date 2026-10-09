// Test data only. The app loads its uploads from the backend.
import type { UploadFile } from '@/engine/types'

export const SEED_UPLOADS: UploadFile[] = [
  { id: 'u1', name: 'argus-fob-morocco.xlsx', type: 'prices', uploadedAt: '2026-10-02', fileDate: '2026-04-21', dataThrough: '2026-04-21', detail: 'DAP, MAP, TSP FOB quotes' },
  { id: 'u2', name: 'fertilizer-week-historical-prices-averages-24-09-2026.xlsx', type: 'prices', uploadedAt: '2026-10-02', fileDate: '2026-09-24', dataThrough: '2026-09-24', detail: '338 price series · 1987→2026' },
  { id: 'u3', name: 'fertilizer-week-historical-freights-24-09-2026.xlsx', type: 'freight', uploadedAt: '2026-10-02', fileDate: '2026-09-24', dataThrough: '2026-09-24', detail: '10 commodity tabs' },
  { id: 'u4', name: 'agro-trials-phosfusion.xlsx', type: 'agro', uploadedAt: '2026-08-14', fileDate: '2026-08-12', dataThrough: '2026-08-12', detail: 'Yield gain 0.12 t/ha · rate 0.162 t/ha' },
  { id: 'u5', name: 'crop-prices.csv', type: 'crop', uploadedAt: '2026-09-30', fileDate: '2026-09-30', dataThrough: '2026-09-30', detail: 'Target crop 409 USD/t' },
]
