"""Validation of sulphur sensitivity sweeps and analytical break-evens."""
import pytest
from app.engine import (
    Composition,
    ProductDef,
    run_sulphur_sensitivity,
)


def test_sulphur_sensitivity_and_break_evens():
    phos = ProductDef(
        id='phos-65-35',
        name='Phosfusion 65-35',
        recipe={'rockDry': 0.738233, 'rockWet': 0.65309725, 'sulphur': 0.15993},
        composition=Composition(P2O5=0.225625),
    )
    tsp = ProductDef(
        id='TSP',
        name='TSP',
        recipe={'rockDry': 0.608, 'rockWet': 1.004765, 'sulphur': 0.512938},
        composition=Composition(P2O5=0.46),
    )
    cost_prices = {'rockDry': 120.0, 'rockWet': 120.0, 'sulphur': 900.0}

    # At parity fixture: anchor = 313.91, ref_price = 640.00
    res = run_sulphur_sensitivity(
        new_product=phos,
        ref_product=tsp,
        cost_prices=cost_prices,
        anchor_price=313.91304,
        ref_price=640.00,
        mode='corrected',
    )

    be_map = {(b.product_id, b.kind): b.sulphur_price for b in res.break_evens}

    # 1. Zero-margin break-even for Phosfusion 65-35 = 918.86 USD/t
    assert be_map[('phos-65-35', 'zero_margin')] == pytest.approx(918.86, abs=0.01)

    # 2. Zero-margin break-even for TSP = 870.41 USD/t
    assert be_map[('TSP', 'zero_margin')] == pytest.approx(870.41, abs=0.01)

    # 3. Parity crossover break-even = 848.46 USD/t
    assert be_map[('phos-65-35', 'crossover')] == pytest.approx(848.46, abs=0.01)

    # Check sweep points exist
    assert len(res.points) == 19  # 100 to 1000 step 50
    p_900 = next(p for p in res.points if p.sulphur_price == 900.0)
    assert p_900.cgm_new == pytest.approx(3.02, abs=0.01)
    assert p_900.cgm_ref == pytest.approx(-15.18, abs=0.01)

