"""Seed data, ported from `src/data/*.ts` (Pricing model.xlsx and the CRU price files)."""
from datetime import date

from ..schemas import Composition, Ingredient, Outlook, Parameters, Product, Quote, Snapshot, UploadRecord

# "Today" in the demo data set: the 2026 snapshot covers 1 Jan → this date.
TODAY = date(2026, 10, 2)
DATA_START = date(2021, 1, 1)

ADDRESSABLE_MARKET_T = 14_630_675
TARGET_CROP_PRICE = 409  # USD/t (placeholder target crop)
DECK_TSP_COST = 494  # business-case deck, conflicts with Standard cost 655.18

INGREDIENTS = [
    Ingredient(id='ammonia', label='Ammonia'),
    Ingredient(id='kcl', label='KCl'),
    Ingredient(id='rockDry', label='Rock (dry)'),
    Ingredient(id='rockWet', label='Rock (wet)'),
    Ingredient(id='sulphur', label='Sulphur'),
    Ingredient(id='acp', label='ACP (intermediate)'),
]


def _p(id, name, family, r, c, **extra) -> Product:
    recipe = {k: q for k, q in zip(('ammonia', 'kcl', 'rockDry', 'rockWet', 'sulphur'), r) if q > 0}
    return Product(id=id, name=name, family=family, recipe=recipe,
                   composition=Composition(N=c[0], P2O5=c[1], K2O=c[2], S=c[3]), **extra)


def products() -> list[Product]:
    new = dict(pcf=0.5, pcfPlaceholder=True, appRate=0.162, yieldGain=0.12)
    return [
        _p('phos-65-35', 'Phosfusion 65-35', 'phosfusion', [0, 0, 0.738233, 0.65309725, 0.15993], [0, 0.225625, 0, 0], **new),
        _p('phos-50-50', 'Phosfusion 50-50', 'phosfusion', [0, 0, 0.98, 0.5023825, 0.102719], [0, 0.190754, 0, 0], **new),
        _p('phos-65-35-cr', 'Phosfusion 65-35 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.704405, 0.65309725, 0.267099], [0, 0.249315, 0, 0]),
        _p('phos-50-50-cr', 'Phosfusion 50-50 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.552, 0.5023825, 0.179], [0, 0.301735, 0, 0]),
        _p('phos-45-55-cr', 'Phosfusion avg 45-55 · Controlled R. Confirmed', 'phosfusion', [0, 0, 0.680225, 0.427025125, 0.19418], [0, 0.277017, 0, 0]),
        _p('TSP', 'TSP', 'reference', [0, 0, 0.608, 1.004765, 0.512938], [0, 0.46, 0, 0], pcf=0.7, appRate=0.13),
        _p('DAP', 'DAP', 'reference', [0.262068, 0, 0, 1.847652, 0.65215], [0.18, 0.46, 0, 0], pcf=0.7),
        _p('MAP', 'MAP', 'reference', [0.073502, 0, 0, 1.584554, 0.613128], [0.11, 0.52, 0, 0], pcf=0.7),
        _p('NPK', 'NPK', 'other', [0.131755, 0.291069, 0, 0.909452, 0.211749], [0.15, 0.15, 0.15, 0]),
        _p('NPS', 'NPS', 'other', [0.10125, 0, 0, 2.176, 0.414862], [0.12, 0.45, 0.05, 0]),
        _p('phosgold', 'PhosGold 3 30 9S', 'other', [0.024729, 0, 0.605266, 0.686938, 0.247016], [0.03, 0.3, 0, 0.09]),
        _p('tsp-blend', 'TSP blendable 5 42', 'other', [0.070602, 0, 0.502314, 0.982566, 0.396659], [0.05, 0.42, 0, 0]),
    ]


def _s(id, label, as_of, nh3, kcl, sulphur, tsp, dap, map_, source) -> Snapshot:
    return Snapshot(
        id=id, label=label, asOf=as_of, source=source,
        inputs={'ammonia': nh3, 'kcl': kcl, 'rockDry': 120, 'rockWet': 120, 'sulphur': sulphur, 'acp': 0},
        refPrices={'TSP': Quote(low=tsp[0], high=tsp[1]), 'DAP': Quote(low=dap[0], high=dap[1]), 'MAP': Quote(low=map_[0], high=map_[1])},
    )


_CRU = 'CRU annual averages (Morocco FOB; ammonia & sulphur Middle East; potash Vancouver)'

SNAPSHOTS: list[Snapshot] = [
    _s('today', 'Today', TODAY, 460, 340, 900, (640, None), (820, 855), (853, 880), 'Standard cost 2026 inputs · Argus FOB Morocco (21 Apr)'),
    _s('2025', '2025', date(2025, 12, 31), 356.9, 304.8, 299.2, (529.3, None), (713.4, None), (698.9, None), _CRU),
    _s('2024', '2024', date(2024, 12, 31), 360.1, 259.5, 102.8, (436.1, None), (585.5, None), (593.8, None), _CRU),
    _s('2023', '2023', date(2023, 12, 31), 432.6, 380.8, 100.0, (449.4, None), (588.7, None), (574.2, None), _CRU),
    _s('2022', '2022', date(2022, 12, 31), 991.3, 624.2, 277.3, (820.9, None), (968.9, None), (969.9, None), _CRU),
    _s('2021', '2021', date(2021, 12, 31), 566.9, 277.0, 187.8, (549.2, None), (650.8, None), (674.6, None), _CRU),
]

# Input price outlook 2026-2034 (Standard Production cost sheet, rows 31-35)
OUTLOOK = Outlook(
    years=[2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034],
    ammonia=[460, 410, 402, 350, 346, 353, 360, 367, 375],
    kcl=[340, 323, 314, 320, 346, 346, 346, 346, 346],
    sulphur=[900, 285, 245, 250, 279, 284, 290, 296, 301],
)


def uploads() -> list[UploadRecord]:
    u = lambda id, name, type, up, d, detail: UploadRecord(id=id, name=name, type=type, uploadedAt=up, fileDate=d, dataThrough=d, detail=detail)
    return [
        u('u1', 'argus-fob-morocco.xlsx', 'prices', TODAY, date(2026, 4, 21), 'DAP, MAP, TSP FOB quotes'),
        u('u2', 'fertilizer-week-historical-prices-averages-24-09-2026.xlsx', 'prices', TODAY, date(2026, 9, 24), '338 price series · 1987→2026'),
        u('u3', 'fertilizer-week-historical-freights-24-09-2026.xlsx', 'freight', TODAY, date(2026, 9, 24), '10 commodity tabs'),
        u('u4', 'agro-trials-phosfusion.xlsx', 'agro', date(2026, 8, 14), date(2026, 8, 12), 'Yield gain 0.12 t/ha · rate 0.162 t/ha'),
        u('u5', 'crop-prices.csv', 'crop', date(2026, 9, 30), date(2026, 9, 30), 'Target crop 409 USD/t'),
    ]


def default_params() -> Parameters:
    return Parameters(
        costPlusMargin=0.2, fullCost=False, valueShare=1 / 3, marketingPct=0, dnaPerTon=96,
        marketShare=0.05, rampTargetYear=2030, priceType='low', carbonMarket='voluntary',
        freshnessMonths=2, staleDays=30, defaultReference='TSP',
    )
