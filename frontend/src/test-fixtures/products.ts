// Test data only. The app loads its products from the backend.
import type { Product } from '@/engine/types'

const P = (id: string, name: string, family: Product['family'], r: [number, number, number, number, number], c: [number, number, number, number], extra: Partial<Product> = {}): Product => ({
  id, name, family,
  recipe: Object.fromEntries(Object.entries({ ammonia: r[0], kcl: r[1], rockDry: r[2], rockWet: r[3], sulphur: r[4] }).filter(([, q]) => q > 0)),
  composition: { N: c[0], P2O5: c[1], K2O: c[2], S: c[3] },
  pcf: null, appRate: null, yieldGain: null,
  ...extra,
})

export const PRODUCTS: Product[] = [
  P('phos-65-35', 'Phosfusion 65-35', 'phosfusion', [0, 0, 0.738233, 0.65309725, 0.15993], [0, 0.225625, 0, 0], { pcf: 0.5, pcfPlaceholder: true, appRate: 0.162, yieldGain: 0.12 }),
  P('phos-50-50', 'Phosfusion 50-50', 'phosfusion', [0, 0, 0.98, 0.5023825, 0.102719], [0, 0.190754, 0, 0], { pcf: 0.5, pcfPlaceholder: true, appRate: 0.162, yieldGain: 0.12 }),
  P('phos-65-35-cr', 'Phosfusion 65-35 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.704405, 0.65309725, 0.267099], [0, 0.249315, 0, 0]),
  P('phos-50-50-cr', 'Phosfusion 50-50 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.552, 0.5023825, 0.179], [0, 0.301735, 0, 0]),
  P('phos-45-55-cr', 'Phosfusion avg 45-55 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.680225, 0.427025125, 0.19418], [0, 0.277017, 0, 0]),
  P('TSP', 'TSP', 'reference', [0, 0, 0.608, 1.004765, 0.512938], [0, 0.46, 0, 0], { pcf: 0.7, appRate: 0.13 }),
  P('DAP', 'DAP', 'reference', [0.262068, 0, 0, 1.847652, 0.65215], [0.18, 0.46, 0, 0], { pcf: 0.7 }),
  P('MAP', 'MAP', 'reference', [0.073502, 0, 0, 1.584554, 0.613128], [0.11, 0.52, 0, 0], { pcf: 0.7 }),
  P('NPK', 'NPK', 'other', [0.131755, 0.291069, 0, 0.909452, 0.211749], [0.15, 0.15, 0.15, 0]),
  P('NPS', 'NPS', 'other', [0.10125, 0, 0, 2.176, 0.414862], [0.12, 0.45, 0.05, 0]),
  P('phosgold', 'PhosGold 3 30 9S', 'other', [0.024729, 0, 0.605266, 0.686938, 0.247016], [0.03, 0.3, 0, 0.09]),
  P('tsp-blend', 'TSP blendable 5 42', 'other', [0.070602, 0, 0.502314, 0.982566, 0.396659], [0.05, 0.42, 0, 0]),
]
