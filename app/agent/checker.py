"""Server-side numeric validator and safety net (zero hallucinations)."""
import re
from typing import Optional
from .types import ToolFact

# Numbers allowed without explicit ToolFact matching
ALLOWED_YEARS = set(range(2000, 2045))
ALLOWED_SMALL_INTS = set(range(0, 13))
PRODUCT_GRADES = {
    '65-35', '50-50', '45-55', '3-30-9', '5-42', '65/35', '50/50',
}


def _extract_numbers(text: str) -> list[float]:
    """Extract standalone numbers from text, ignoring dates, grades, and versions."""
    # Strip grade patterns like 65-35 or 50-50 first
    cleaned = text
    for g in PRODUCT_GRADES:
        cleaned = cleaned.replace(g, ' ')

    # Strip version patterns like v1, v2
    cleaned = re.sub(r'\bv\d+\b', ' ', cleaned, flags=re.IGNORECASE)

    # Match currency values like $313.91 or numbers like 313.91, -15.18, 1,391.30
    pattern = r'[-+]?\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b'
    matches = re.findall(pattern, cleaned)

    numbers: list[float] = []
    for m in matches:
        num_str = m.replace(',', '')
        try:
            val = float(num_str)
            # Exclude calendar years
            if int(val) in ALLOWED_YEARS and float(val).is_integer():
                continue
            # Exclude small counting integers
            if int(val) in ALLOWED_SMALL_INTS and float(val).is_integer():
                continue
            numbers.append(val)
        except ValueError:
            continue
    return numbers


class ValidationResult:
    def __init__(self, is_valid: bool, errors: list[str]):
        self.is_valid = is_valid
        self.errors = errors


def validate_agent_text(
    text: str,
    allowed_facts: dict[str, ToolFact],
    tolerance: float = 0.05,
) -> ValidationResult:
    """Verify that all figures in the agent's prose are backed by engine tool facts."""
    errors: list[str] = []
    numbers = _extract_numbers(text)
    fact_values = [f.value for f in allowed_facts.values()]

    # 1. Fact matching
    for num in numbers:
        matched = any(abs(num - f_val) <= tolerance for f_val in fact_values)
        if not matched:
            errors.append(f'Number {num:g} is not grounded in any tool output.')

    # 2. Currency unit enforcement
    # If the text quotes prices/costs, ensure USD/t or USD/yr is mentioned
    if numbers and not re.search(r'USD\s*/\s*t|USD\s*/\s*yr|\$', text, re.IGNORECASE):
        errors.append('Currency figures must include explicit units (e.g. USD/t).')

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)


def render_fallback_template(facts: dict[str, ToolFact], intent: str = 'hero') -> str:
    """Deterministic safe template generated when LLM validation repeatedly fails."""
    anchor = facts.get('anchor_price')
    floor = facts.get('floor')
    cgm = facts.get('cgm')
    cgm_ref = facts.get('cgm_ref')
    added_val = facts.get('added_value')
    val_price = facts.get('value_price')

    anchor_val = f'{anchor.value:.2f} USD/t' if anchor else 'N/A'
    floor_val = f'{floor.value:.2f} USD/t' if floor else 'N/A'
    cgm_val = f'{cgm.value:.2f} USD/t' if cgm else 'N/A'
    cgm_ref_val = f'{cgm_ref.value:.2f} USD/t' if cgm_ref else 'N/A'
    added_val_str = f'{added_val.value:.2f} USD/t' if added_val else 'N/A'
    val_price_str = f'{val_price.value:.2f} USD/t' if val_price else 'N/A'

    return (
        f'Recommended anchor: {anchor_val} (Reference-minus). '
        f'That is below the cost-plus floor of {floor_val}. '
        f'At this price, the new product earns {cgm_val} against the reference CGM of {cgm_ref_val}. '
        f'Value pricing allows up to {val_price_str} based on {added_val_str} of agronomic value created.'
    )

