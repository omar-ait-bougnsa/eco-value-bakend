"""Tests for server-side numeric validation and safety ladder."""
from app.agent.checker import render_fallback_template, validate_agent_text
from app.agent.types import ToolFact


def test_validator_accepts_grounded_numbers():
    facts = {
        'anchor': ToolFact(key='anchor', value=313.91, unit='USD/t', label='Anchor'),
        'cgm': ToolFact(key='cgm', value=3.02, unit='USD/t', label='CGM'),
    }
    text = 'The anchor price is 313.91 USD/t and the resulting CGM is 3.02 USD/t.'
    res = validate_agent_text(text, facts)
    assert res.is_valid
    assert len(res.errors) == 0


def test_validator_rejects_hallucinated_numbers():
    facts = {
        'anchor': ToolFact(key='anchor', value=313.91, unit='USD/t', label='Anchor'),
    }
    text = 'The recommended price is 350.00 USD/t with an estimated margin of 50.00 USD/t.'
    res = validate_agent_text(text, facts)
    assert not res.is_valid
    assert any('350' in e for e in res.errors)


def test_validator_rejects_missing_units():
    facts = {
        'anchor': ToolFact(key='anchor', value=313.91, unit='USD/t', label='Anchor'),
    }
    text = 'The anchor price is 313.91 without any currency denomination.'
    res = validate_agent_text(text, facts)
    assert not res.is_valid
    assert any('units' in e for e in res.errors)


def test_validator_ignores_years_and_product_grades():
    facts = {
        'anchor': ToolFact(key='anchor', value=313.91, unit='USD/t', label='Anchor'),
    }
    # 2026 is a year, 65-35 is a grade: both must be allowed without matching facts
    text = 'In 2026, Phosfusion 65-35 reaches an anchor price of 313.91 USD/t.'
    res = validate_agent_text(text, facts)
    assert res.is_valid


def test_render_fallback_template():
    facts = {
        'anchor_price': ToolFact(key='anchor_price', value=313.91, unit='USD/t', label='Anchor'),
        'floor': ToolFact(key='floor', value=373.08, unit='USD/t', label='Floor'),
        'cgm': ToolFact(key='cgm', value=3.02, unit='USD/t', label='CGM'),
        'cgm_ref': ToolFact(key='cgm_ref', value=-15.18, unit='USD/t', label='Ref CGM'),
    }
    out = render_fallback_template(facts)
    assert '313.91 USD/t' in out
    assert '373.08 USD/t' in out
    assert '3.02 USD/t' in out
    assert '-15.18 USD/t' in out

