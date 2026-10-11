"""Raw material costing, D&A, and marketing unit costs."""
from .types import CostLine

INGREDIENT_LABELS = {
    'ammonia': 'Ammonia',
    'kcl': 'KCl',
    'rockDry': 'Rock (dry)',
    'rockWet': 'Rock (wet)',
    'sulphur': 'Sulphur',
    'acp': 'ACP (intermediate)',
}


def calc_raw_material_lines(recipe: dict[str, float], prices: dict[str, float]) -> list[CostLine]:
    """Calculate individual cost lines for ingredients with non-zero consumption.
    ACP is an intermediate and remains unpriced (0 USD/t).
    """
    lines: list[CostLine] = []
    for ing_id, qty in recipe.items():
        if qty > 0:
            price = 0.0 if ing_id == 'acp' else prices.get(ing_id, 0.0)
            lines.append(CostLine(
                id=ing_id,
                label=INGREDIENT_LABELS.get(ing_id, ing_id),
                qty=qty,
                price=price,
                usd=qty * price,
            ))
    return lines


def calc_raw_material_cost(lines: list[CostLine]) -> float:
    """Sum total raw material expense per ton of product."""
    return sum(line.usd for line in lines)


def calc_unit_costs(
    raw_material: float,
    dna_per_ton: float,
    include_dna: bool,
    marketing_pct: float,
) -> tuple[float, float, float, float]:
    """Calculate full unit cost breakdown.
    Returns:
        (dna, marketing, base_cost, total_unit_cost)
    """
    dna = dna_per_ton if include_dna else 0.0
    base_cost = raw_material + dna
    marketing = marketing_pct * base_cost
    total_unit_cost = base_cost + marketing
    return dna, marketing, base_cost, total_unit_cost

