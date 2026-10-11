"""Validation of Corrections X1 (Carbon) and X2 (Marketing)."""
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
    phos = ProductDef(
        id='phos-65-35',
        name='Phosfusion 65-35',
        recipe={'rockDry': 0.738233, 'rockWet': 0.65309725, 'sulphur': 0.15993},
        composition=Composition(P2O5=0.225625),
        pcf=0.5,
    )
    tsp = ProductDef(
        id='TSP',
        name='TSP',
        recipe={'rockDry': 0.608, 'rockWet': 1.004765, 'sulphur': 0.512938},
        composition=Composition(P2O5=0.46),
        pcf=0.7,
    )
    return EngineInput(
        products={'phos-65-35': phos, 'TSP': tsp},
        product_ids=['phos-65-35'],
        reference_id='TSP',
        cost_prices={'ammonia': 460.0, 'kcl': 340.0, 'rockDry': 120.0, 'rockWet': 120.0, 'sulphur': 900.0},
        reference_price=640.0,
        agronomy={
            'phos-65-35': AgronomyData(yield_gain=0.12, app_rate_new=0.162, app_rate_ref=0.13, crop_price=409.0)
        },
        params=EngineParams(anchor_method='refMinus'),
    )


def test_correction_x1_carbon(base_input: EngineInput):
    # At 40 USD/tCO2
    base_input.params.carbon_price = 40.0

    # In corrected mode: +2.47 USD/t
    base_input.mode = 'corrected'
    out_corr = evaluate(base_input)
    r_corr = out_corr.per_product['phos-65-35']
    assert r_corr.carbon_effect == pytest.approx(2.47, abs=0.01)
    assert r_corr.prices['value'] == pytest.approx(743.46, abs=0.01)

    # In workbook mode: +0.40 USD/t
    base_input.mode = 'workbook'
    out_wb = evaluate(base_input)
    r_wb = out_wb.per_product['phos-65-35']
    assert r_wb.carbon_effect == pytest.approx(0.40, abs=0.01)
    assert r_wb.prices['value'] == pytest.approx(741.39, abs=0.01)


def test_correction_x2_marketing(base_input: EngineInput):
    # At 10% marketing
    base_input.params.marketing_pct = 0.10

    # In corrected mode: marketing is kept as cost -> CGM = -28.07 USD/t
    base_input.mode = 'corrected'
    out_corr = evaluate(base_input)
    r_corr = out_corr.per_product['phos-65-35']
    assert r_corr.unit_cost == pytest.approx(341.99, abs=0.01)
    assert r_corr.prices['costPlus'] == pytest.approx(410.38, abs=0.01)
    assert r_corr.cgm == pytest.approx(-28.07, abs=0.01)

    # In workbook mode: marketing is added back -> legacy CGM = +3.02 USD/t
    base_input.mode = 'workbook'
    out_wb = evaluate(base_input)
    r_wb = out_wb.per_product['phos-65-35']
    assert r_wb.cgm == pytest.approx(3.02, abs=0.01)

