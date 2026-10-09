// Test data only. The app loads its market snapshots from the backend.
import type { Snapshot } from '@/engine/types'

const S = (id: string, label: string, asOf: string, nh3: number, kcl: number, sulphur: number, tsp: [number, number | null], dap: [number, number | null], map: [number, number | null], source: string): Snapshot => ({
  id, label, asOf, source,
  inputs: { ammonia: nh3, kcl, rockDry: 120, rockWet: 120, sulphur, acp: 0 },
  refPrices: { TSP: { low: tsp[0], high: tsp[1] }, DAP: { low: dap[0], high: dap[1] }, MAP: { low: map[0], high: map[1] } },
})

const CRU = 'CRU annual averages (Morocco FOB; ammonia & sulphur Middle East; potash Vancouver)'

export const SNAPSHOTS: Snapshot[] = [
  S('today', 'Today', '2026-10-02', 460, 340, 900, [640, null], [820, 855], [853, 880], 'Standard cost 2026 inputs · Argus FOB Morocco (21 Apr)'),
  S('2025', '2025', '2025-12-31', 356.9, 304.8, 299.2, [529.3, null], [713.4, null], [698.9, null], CRU),
  S('2024', '2024', '2024-12-31', 360.1, 259.5, 102.8, [436.1, null], [585.5, null], [593.8, null], CRU),
  S('2023', '2023', '2023-12-31', 432.6, 380.8, 100.0, [449.4, null], [588.7, null], [574.2, null], CRU),
  S('2022', '2022', '2022-12-31', 991.3, 624.2, 277.3, [820.9, null], [968.9, null], [969.9, null], CRU),
  S('2021', '2021', '2021-12-31', 566.9, 277.0, 187.8, [549.2, null], [650.8, null], [674.6, null], CRU),
]
