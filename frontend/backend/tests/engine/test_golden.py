"""Golden value acceptance tests against Pricing model.xlsx benchmarks.
Validates the 25 acceptance values from Doc 09 §8 / Doc 10 §B8.
"""
import pytest
from app.engine import (
    AgronomyData,
    Composition,
    EngineInput,
    EngineParams,
    ProductDef,
    evaluate,
)


@pytest.fixture
def base_input() -> EngineInput:
    """Parity baseline fixture: Phosfusion 65-35 vs TSP."""
    phos = ProductDef(
        id='phos-65-35',
        name='Phosfusion 65-35',
        family='phosfusion',
        recipe={
            'rockDry': 0.738233,
            'rockWet': 0.65309725,
            'sulphur': 0.15993,
        },
        composition=Composition(P2O5=0.225625),
        pcf=0.5,
        pcf_placeholder=True,
    )
    tsp = ProductDef(
        id='TSP',
        name='TSP',
        family='reference',
        recipe={
            'rockDry': 0.608,
            'rockWet': 1.004765,
            'sulphur': 0.512938,
        },
        composition=Composition(P2O5=0.46),
        pcf=0.7,
    )
    cost_prices = {
        'ammonia': 460.0,
        'kcl': 340.0,
        'rockDry': 120.0,
        'rockWet': 120.0,
        'sulphur': 900.0,
    }
    agronomy = {
        'phos-65-35': AgronomyData(
            yield_gain=0.12,
            app_rate_new=0.162,
            app_rate_ref=0.13,
            crop_price=409.0,
            status='placeholder',
        )
    }
    return EngineInput(
        products={'phos-65-35': phos, 'TSP': tsp},
        product_ids=['phos-65-35'],
        reference_id='TSP',
        cost_prices=cost_prices,
        reference_price=640.0,
        agronomy=agronomy,
        params=EngineParams(
            cost_plus_margin=0.20,
            value_share=1.0 / 3.0,
            marketing_pct=0.0,
            carbon_price=0.0,
            include_dna=False,
            dna_per_ton=96.0,
            anchor_method='refMinus',
        ),
        mode='corrected',
    )


def test_parity_baseline_acceptance(base_input: EngineInput):
    out = evaluate(base_input)
    r = out.per_product['phos-65-35']

    assert r.raw_material == pytest.approx(310.90, abs=0.01)
    assert r.ref_cost == pytest.approx(655.18, abs=0.01)
    assert r.prices['costPlus'] == pytest.approx(373.08, abs=0.01)
    assert r.p2o5_value_ref == pytest.approx(1391.30, abs=0.01)
    assert r.prices['refMinus'] == pytest.approx(313.91, abs=0.01)
    assert r.added_value == pytest.approx(302.96, abs=0.01)
    assert r.prices['value'] == pytest.approx(740.99, abs=0.01)
    assert r.cgm == pytest.approx(3.02, abs=0.01)
    assert r.cgm_ref == pytest.approx(-15.18, abs=0.01)
    assert r.cgm_p2o5 == pytest.approx(13.37, abs=0.01)
    assert r.cgm_s == pytest.approx(18.86, abs=0.01)


def test_value_share_50_pct(base_input: EngineInput):
    base_input.params.value_share = 0.50
    out = evaluate(base_input)
    r = out.per_product['phos-65-35']
    assert r.prices['value'] == pytest.approx(791.48, abs=0.01)


def test_budget_2027_conditions(base_input: EngineInput):
    # In 2027: sulphur drops to 285 USD/t
    base_input.cost_prices['sulphur'] = 285.0
    out = evaluate(base_input)
    r = out.per_product['phos-65-35']

    assert r.unit_cost == pytest.approx(212.54, abs=0.01)
    assert r.cgm == pytest.approx(101.37, abs=0.01)
    assert r.ref_cost == pytest.approx(339.72, abs=0.01)
    assert r.cgm_ref == pytest.approx(300.28, abs=0.01)

