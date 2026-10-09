"""Golden values, ported from `src/engine/engine.test.ts`."""
from datetime import date

import pytest

from app.data.seed import SNAPSHOTS
from app.engine.period import (
    YTD, Span, blend_snapshot, last_12_months, month_period, period_label, period_weights, year_period,
)
from app.engine.run import run_engine


@pytest.fixture
def run(store):
    return lambda **over: run_engine(store.make_input(over), store.ctx())


@pytest.fixture
def lead(run):
    return lambda **over: next(iter(run(**over).perProduct.values()))


def near(a, b, d=2):
    assert a == pytest.approx(b, abs=0.5 * 10 ** -d)


def year(y):
    return dict(periodFrom=f'{y}-01-01', periodTo=f'{y}-12-31')


def test_today_phosfusion_65_35_vs_tsp(run):
    out = run()
    r = out.perProduct['phos-65-35']
    near(r.unitCost, 310.9)
    near(r.prices['costPlus'], 373.08)
    near(r.refCost, 655.18)
    near(r.refPrice, 640, 6)
    near(r.prices['refMinus'], 313.91)
    near(r.prices['value'], 740.99)
    near(r.addedValue, 302.96)
    near(r.p2o5ValueRef, 1391.3, 1)
    assert r.prices['market'] is None
    near(r.cgm, 3.02)
    near(r.cgmRef, -15.18)
    near(r.cgmP2O5, 13.37)
    near(r.cgmS, 18.86)
    near(r.totalMargin / 1e6, 2.2, 1)
    w = r.waterfall
    near(w[0].to + w[1].value + w[2].value, w[3].to)
    assert {'P1', 'D1', 'S1', 'U1', 'C2', 'M1', 'A1'} <= {f.code for f in out.flags}


def test_flag_wording_matches_frontend(run):
    titles = {f.code: f.title for f in run().flags}
    assert titles['P1'] == 'Anchor is below the cost-plus floor (313.91 < 373.08)'
    assert titles['D1'] == 'Prices are 5 months older than freight'
    assert titles['A1'] == 'Agent assumption: market share 5%'
    assert titles['C2'] == 'Product carbon footprint 0.5 t CO₂/t is a placeholder'


def test_what_ifs(lead):
    near(lead(valueShare=0.5).prices['value'], 791.48)
    near(lead(refCostOverride=494).cgmRef, 146)


def test_2025_snapshot(lead):
    r = lead(**year(2025))
    near(r.unitCost, 214.81)
    near(r.prices['refMinus'], 259.62)
    near(r.cgmRef, 182.3, 1)


@pytest.mark.parametrize('y, anchor', [(2021, 269.38), (2022, 402.64), (2023, 220.43), (2024, 213.9)])
def test_anchor_trend(lead, y, anchor):
    near(lead(**year(y)).prices['refMinus'], anchor)


def test_dap_reference(lead):
    r = lead(referenceId='DAP')
    near(r.prices['refMinus'], 352.67, 1)
    near(r.prices['value'], 920.99)


def test_phosfusion_50_50(lead):
    r = lead(productIds=['phos-50-50'])
    near(r.unitCost, 270.33)
    near(r.prices['refMinus'], 265.4)


def test_periods():
    assert period_weights(YTD)['today'] == pytest.approx(1)
    assert blend_snapshot(SNAPSHOTS, YTD).id == 'today'
    assert period_label(YTD) == 'Year to date'
    assert period_weights(year_period(2024)) == {'2024': 1}
    assert period_label(year_period(2023)) == '2023'
    assert period_label(Span(date(2025, 3, 1), date(2025, 6, 30))) == '01 Mar 2025 – 30 Jun 2025'
    assert period_label(Span(date(2025, 3, 14), date(2025, 3, 14))) == '14 Mar 2025'
    assert month_period(2025, 2) == Span(date(2025, 2, 1), date(2025, 2, 28))
    assert period_label(month_period(2025, 2)) == 'Feb 2025'
    assert month_period(2026, 10).end == date(2026, 10, 2)  # current month is cut at today
    assert period_label(month_period(2026, 10)) == 'Oct 2026'


def test_period_spanning_two_years_is_day_weighted():
    p = Span(date(2024, 7, 1), date(2025, 6, 30))
    w = period_weights(p)
    assert w['2024'] + w['2025'] == pytest.approx(1)
    by_id = {s.id: s for s in SNAPSHOTS}
    blended = blend_snapshot(SNAPSHOTS, p).inputs['sulphur']
    assert blended == pytest.approx(w['2024'] * by_id['2024'].inputs['sulphur'] + w['2025'] * by_id['2025'].inputs['sulphur'])


def test_s1_only_asks_when_period_is_entirely_current(run):
    l12 = last_12_months()
    w = period_weights(l12)
    assert w['2025'] > 0.2 and w['today'] > 0.6
    assert not any(f.code == 'S1' for f in run(periodFrom=l12.start, periodTo=l12.end).flags)
    assert any(f.code == 'S1' and f.severity == 'warning' for f in run().flags)


def test_single_day_uses_its_year(lead):
    near(lead(periodFrom='2024-05-01', periodTo='2024-05-01').unitCost, 183.4)
