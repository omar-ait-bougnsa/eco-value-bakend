"""Server-side numeric validator and safety net (zero hallucinations)."""
import re
from datetime import date
from typing import Any, Iterable, Optional

from .citations import MARKER
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
    # A hyphen is a minus sign unless it follows a figure: 24.5-25.5 is a range, not 24.5 and minus 25.5.
    pattern = r'(?:(?<![\w.])[-+])?\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b'
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


_NAMES = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
_MONTHS = {name[:3].lower(): i for i, name in enumerate(_NAMES, 1)}
# A month in full or as its first three letters (and "Sept"): "10 marginal" is not the 10th of March.
_MONTH = '(' + '|'.join(f'{n[:3]}(?:{n[3:]})?' if n != 'September' else 'Sep(?:t(?:ember)?)?' for n in _NAMES) + r')\.?(?![a-z])'
_month = lambda m, group: _MONTHS[m[group][:3].lower()]
# Each gives (year or None, month, day). The forms with a year come first, so "24 Sep 2026" is not read as "24 Sep".
# Without a year the month must be capitalised: "option 2 may apply" is not the 2nd of May.
_DATE_FORMS = (
    (re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf'\b(\d{{1,2}})[ -]{_MONTH}[ ,-]+(\d{{4}})\b', re.I), lambda m: (int(m[3]), _month(m, 2), int(m[1]))),
    (re.compile(rf'\b{_MONTH} (\d{{1,2}}),? (\d{{4}})\b', re.I), lambda m: (int(m[3]), _month(m, 1), int(m[2]))),
    (re.compile(rf'\b(\d{{1,2}})[ -]{_MONTH}'), lambda m: (None, _month(m, 2), int(m[1]))),
)


def _take_dates(text: str) -> tuple[list[tuple[str, tuple[Optional[int], int, int]]], str]:
    """The dates written in `text` (as written, and as year / month / day), and the text without them."""
    found: list[tuple[str, tuple[Optional[int], int, int]]] = []
    for pattern, read in _DATE_FORMS:
        def take(m: re.Match) -> str:
            year, month, day = read(m)
            try:
                date(year or 2000, month, day)
            except ValueError:
                return m[0]  # 2026-13-45 is not a date: left for the number check
            found.append((m[0], (year, month, day)))
            return ' '
        text = pattern.sub(take, text)
    return found, text


# Models set numbers in typographic characters: 2026‑09‑17 with non-breaking hyphens, ‑15.18 with one for the minus sign,
# 313.91 USD/t with a narrow space. Read as plain ASCII they are the same figures.
_TYPOGRAPHY = str.maketrans({**{c: '-' for c in '‐‑‒–—―−'}, **{c: ' ' for c in '\u00a0\u2007\u2009\u200a\u202f'}})


def _ascii(text: str) -> str:
    return text.translate(_TYPOGRAPHY)


def _plain(text: str) -> str:
    """For comparing a quotation with its source: lower case, no Markdown marks, single spaces."""
    return ' '.join(re.sub(r'\\n|[*_`|>#]', ' ', text.lower()).split())


def _check_provenance(text: str, citations: dict[str, dict[str, Any]], grounding: str, sources: Iterable[str]) -> list[str]:
    """RAG.md §5: a citation, a document name, a date or a quotation in the answer must come from what was retrieved."""
    errors: list[str] = []
    passages = ' '.join(c['passage'] for c in citations.values())

    for ref in dict.fromkeys(MARKER.findall(text)):
        if ref not in citations:
            errors.append(f'Citation [{ref}] does not match a retrieved passage.')

    retrieved = {c['source'].lower() for c in citations.values()}
    for source in sources:
        if len(source) > 5 and source.lower() in text.lower() and source.lower() not in retrieved:
            errors.append(f'"{source}" is named, but none of its passages was retrieved. Search for it first, or do not name it.')

    grounded = {when for _, when in _take_dates(f'{grounding} {passages}')[0]}
    grounded |= {(None, month, day) for _, month, day in grounded}
    for written, when in _take_dates(text)[0]:
        if when not in grounded:
            errors.append(f'Date {written} is not in any tool output.')

    known = _plain(f'{grounding} {passages}')
    for quote in re.findall(r'[“"]([^“”"]{20,})[”"]', text):
        if len(quote.split()) >= 5 and _plain(quote).rstrip('.,;') not in known:
            errors.append(f'The quotation "{quote[:60]}…" is not in a retrieved passage. Quote it exactly, or rephrase without quotation marks.')
    return errors


class ValidationResult:
    def __init__(self, is_valid: bool, errors: list[str]):
        self.is_valid = is_valid
        self.errors = errors


def validate_agent_text(
    text: str,
    allowed_facts: dict[str, ToolFact],
    tolerance: float = 0.05,
    citations: Optional[dict[str, dict[str, Any]]] = None,
    grounding: str = '',
    sources: Iterable[str] = (),
) -> ValidationResult:
    """Verify that all figures in the agent's prose are backed by engine tool facts, and its citations by retrieved passages.

    `citations`: the passages `search_knowledge` returned this turn, by ref. `grounding`: everything the tools
    returned this turn, as text. `sources`: the titles of all indexed documents.
    """
    citations = citations or {}
    text, grounding = _ascii(text), _ascii(grounding)
    citations = {ref: {**c, 'passage': _ascii(c['passage'])} for ref, c in citations.items()}
    errors = _check_provenance(text, citations, grounding, sources)
    # Dates and citation markers are checked above: what is left of the text is checked for its numbers.
    numbers = _extract_numbers(_take_dates(MARKER.sub(' ', text))[1])
    # A figure may come from an engine fact, from a retrieved passage, or from anything else a tool returned this turn
    # (a parameter, for instance). A share the tools give as a fraction may be written as a percentage: 0.2 as 20 %.
    returned = _extract_numbers(' '.join([grounding, *(f'{c["passage"]} {c["label"]}' for c in citations.values())]))
    fact_values = [f.value for f in allowed_facts.values()] + returned + [x * 100 for x in returned if 0 < abs(x) <= 1]

    # 1. Fact matching
    for num in numbers:
        matched = any(abs(num - f_val) <= tolerance for f_val in fact_values)
        if not matched:
            errors.append(f'Number {num:g} is not grounded in any tool output.')

    # 2. Currency unit enforcement
    # If the text quotes prices/costs, ensure USD/t or USD/yr is mentioned
    if numbers and re.search(r'price|cost|margin|anchor|cgm|floor|ceiling', text, re.IGNORECASE) and not re.search(r'USD\s*/\s*t|USD\s*/\s*yr|\$', text, re.IGNORECASE):
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
        f'Recommended anchor: {anchor_val}. '
        + ('' if not (anchor and floor) else f'That is below the cost-plus floor of {floor_val}. ' if anchor.value < floor.value else f'That sits above the cost-plus floor of {floor_val}. ')
        +
        f'At this price, the new product earns {cgm_val} against the reference CGM of {cgm_ref_val}. '
        f'Value pricing allows up to {val_price_str} based on {added_val_str} of agronomic value created.'
    )

