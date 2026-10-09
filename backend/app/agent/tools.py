"""Agent tool definitions and engine wrappers aligned with architecture spec.

Catalog of tools:
- read_inputs: Load sources + current parameters, with provenance.
- check_inputs: Return flags (P1, S1, D1, D2, W1, M1, A1, etc.) computed by code.
- run_engine: Pure engine execution; returns RunOutput; persists new run (alias: run_pricing).
- compare_runs: Input diff + output delta between two runs.
- snapshot_view: Derived output under another snapshot without persisting.
- draft_memo: Structured memo blocks with source references.
- stage_change: Interrupt / propose an input change card for human confirmation.
- ask_user: Interrupt / present interactive decision chips to the human.
- run_sulphur_sensitivity: Sulphur price sweep and analytical break-evens.
- explain_flags: Plain-language audit explanation of engine flags.
- explain_run: Plain-language explanation of pricing methods and CGM margins.
- search_knowledge: Passages of the indexed documents (reports, trials, methodology) with their source.
"""
import time
from typing import Any, Optional
from uuid import uuid4

from ..engine import (
    Composition,
    EngineInput,
    EngineParams,
    ProductDef,
    evaluate,
    run_sulphur_sensitivity as calc_sensitivity,
)
from ..engine.run import diff_inputs
from ..rag import EmbeddingError, search
from ..schemas import RunInput, RunOutput
from ..store import Store
from .types import AgentEvent, QuestionOption, StagedChange, ToolFact


def _uid(prefix: str = 'e') -> str:
    return f'{prefix}_{uuid4().hex[:8]}'


def _get_output(run: Any) -> RunOutput:
    out = getattr(run, 'output', run)
    if isinstance(out, dict):
        return RunOutput.model_validate(out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tool Implementations
# ─────────────────────────────────────────────────────────────────────────────

def tool_read_inputs(
    store: Store,
    simulation_id: Optional[str] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Load sources, active snapshot raw materials, and parameters with provenance."""
    events: list[AgentEvent] = []
    events.append(AgentEvent(
        id=_uid('step'),
        type='step',
        payload={'label': 'Reading active datasets, inputs, and parameter provenance...', 'status': 'running'},
    ))
    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'read_inputs', 'label': 'Read Inputs & Provenance', 'latencyMs': 12},
    ))

    snap = store.snapshots()[0]
    params = store.params()
    uploads = store.uploads()

    facts: list[ToolFact] = []
    for ing_id, price in snap.inputs.items():
        facts.append(ToolFact(
            key=f'input_price_{ing_id}',
            value=round(price, 2),
            unit='USD/t',
            label=f'{ing_id.capitalize()} price ({snap.label})',
        ))

    tsp_quote = snap.refPrices.get('TSP')
    if tsp_quote and tsp_quote.low is not None:
        facts.append(ToolFact(
            key='ref_price_TSP',
            value=round(tsp_quote.low, 2),
            unit='USD/t',
            label='TSP Reference Price (Morocco FOB / CRU Netback)',
        ))

    current_run_version = None
    if simulation_id:
        try:
            sim = store.sim(simulation_id)
            if sim.runs:
                current_run_version = sim.runs[-1].version
        except LookupError:
            pass

    data = {
        'activeSnapshot': snap.label,
        'asOf': str(snap.asOf),
        'uploadsCount': len(uploads),
        'parameters': params.model_dump(),
        'inputs': snap.inputs,
        'currentVersion': current_run_version,
    }
    return data, facts, events


def tool_check_inputs(
    store: Store,
    simulation_id: str,
    input_data: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Evaluate flags and data freshness consistency for the simulation."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    if not sim.runs and not input_data:
        return {'flags': []}, [], []

    if input_data:
        run_input = store.make_input(input_data)
    else:
        run_input = RunInput.model_validate(sim.runs[-1].input)

    ctx = store.ctx()
    output_data = store.run(run_input, ctx)

    for f in output_data.flags:
        events.append(AgentEvent(
            id=_uid('flag'),
            type='flag',
            payload=f.model_dump(),
        ))

    facts = [
        ToolFact(
            key='warning_count',
            value=float(sum(1 for f in output_data.flags if f.severity == 'warning')),
            unit='flags',
            label='Warning Flags Count',
        ),
        ToolFact(
            key='total_flags_count',
            value=float(len(output_data.flags)),
            unit='flags',
            label='Total Flags Count',
        ),
    ]
    data = {
        'flags': [f.code for f in output_data.flags],
        'flagDetails': [f.model_dump() for f in output_data.flags],
    }
    return data, facts, events


def tool_run_engine(
    store: Store,
    simulation_id: str,
    product_ids: Optional[list[str]] = None,
    reference_id: Optional[str] = None,
    overrides: Optional[dict[str, Any]] = None,
    create_version: bool = True,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Execute engine pricing calculation and optionally persist as a new run version."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    prev = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None

    # Merge overrides on top of previous run or default
    body_overrides: dict[str, Any] = dict(overrides or {})
    if product_ids:
        body_overrides['productIds'] = product_ids
    if reference_id:
        body_overrides['referenceId'] = reference_id

    run_input = store.make_input(body_overrides, prev)

    lead_name = run_input.productIds[0]
    events.append(AgentEvent(
        id=_uid('step'),
        type='step',
        payload={'label': f'Pricing {lead_name} against {run_input.referenceId}...', 'status': 'running'},
    ))

    if create_version:
        summary = body_overrides.get('summary') or ('Re-run' if prev else 'Initial run')
        run = store.add_run(sim, run_input, by='agent', summary=summary)
        run_output = run.output
        run_id = run.id
        version = run.version
    else:
        run_output = store.run(run_input)
        run_id = 'preview'
        version = (len(sim.runs) + 1) if sim.runs else 1

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'run_engine', 'label': f'Pricing engine · 4 methods (v{version})', 'latencyMs': 45},
    ))

    # Build ToolFacts from the lead product
    lead_id = run_input.productIds[0]
    lead_res = run_output.perProduct[lead_id]
    facts: list[ToolFact] = [
        ToolFact(key='unit_cost', value=round(lead_res.unitCost, 2), unit='USD/t', label=f'{lead_res.name} Total Unit Cost'),
        ToolFact(key='raw_material', value=round(lead_res.rawMaterial, 2), unit='USD/t', label=f'{lead_res.name} Raw Material Cost'),
        ToolFact(key='anchor_price', value=round(lead_res.anchorPrice, 2) if lead_res.anchorPrice else 0.0, unit='USD/t', label=f'{lead_res.name} Anchor Price'),
        ToolFact(key='cost_plus', value=round(lead_res.prices.get('costPlus') or 0.0, 2), unit='USD/t', label=f'{lead_res.name} Cost-Plus Price'),
        ToolFact(key='floor', value=round(lead_res.floor, 2), unit='USD/t', label=f'{lead_res.name} Floor Price'),
        ToolFact(key='cgm', value=round(lead_res.cgm or 0.0, 2), unit='USD/t', label=f'{lead_res.name} CGM at Anchor'),
    ]
    if lead_res.refCost:
        facts.append(ToolFact(key='ref_cost', value=round(lead_res.refCost, 2), unit='USD/t', label=f'{run_input.referenceId} Cost'))
    if lead_res.refPrice:
        facts.append(ToolFact(key='ref_price', value=round(lead_res.refPrice, 2), unit='USD/t', label=f'{run_input.referenceId} Reference Price'))
    if lead_res.cgmRef is not None:
        facts.append(ToolFact(key='cgm_ref', value=round(lead_res.cgmRef, 2), unit='USD/t', label=f'{run_input.referenceId} Reference CGM'))
    if lead_res.prices.get('refMinus'):
        facts.append(ToolFact(key='ref_minus', value=round(lead_res.prices['refMinus'], 2), unit='USD/t', label=f'{lead_res.name} Reference-Minus Price'))
    if lead_res.prices.get('value'):
        facts.append(ToolFact(key='value_price', value=round(lead_res.prices['value'], 2), unit='USD/t', label=f'{lead_res.name} Value Price'))
    if lead_res.addedValue:
        facts.append(ToolFact(key='added_value', value=round(lead_res.addedValue, 2), unit='USD/t', label=f'{lead_res.name} Agronomic Value Created'))
    if lead_res.cgmP2O5:
        facts.append(ToolFact(key='cgm_p2o5', value=round(lead_res.cgmP2O5, 2), unit='USD/t', label=f'{lead_res.name} CGM per ton P2O5'))
    if lead_res.cgmS:
        facts.append(ToolFact(key='cgm_s', value=round(lead_res.cgmS, 2), unit='USD/t', label=f'{lead_res.name} CGM per ton Sulphur'))

    events.append(AgentEvent(
        id=_uid('result'),
        type='result',
        payload={
            'runId': run_id,
            'version': version,
            'anchorPrice': lead_res.anchorPrice,
            'floor': lead_res.floor,
            'cgm': lead_res.cgm,
            'cgmRef': lead_res.cgmRef,
            'flags': [f.model_dump() for f in run_output.flags],
        },
    ))

    data = {
        'version': version,
        'runId': run_id,
        'leadProduct': lead_res.name,
        'anchorPrice': lead_res.anchorPrice,
        'cgm': lead_res.cgm,
        'cgmRef': lead_res.cgmRef,
        'flags': [f.code for f in run_output.flags],
    }
    return data, facts, events


# Backward-compatible alias
tool_run_pricing = tool_run_engine


def tool_compare_runs(
    store: Store,
    simulation_id: str,
    run_id_a: Optional[str] = None,
    run_id_b: Optional[str] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Compute input diff and output delta between two runs."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    if len(sim.runs) < 2 and (run_id_a is None or run_id_b is None):
        return {'diffs': [], 'deltas': {}}, [], []

    if run_id_a and run_id_b:
        run_a = next(r for r in sim.runs if r.id == run_id_a)
        run_b = next(r for r in sim.runs if r.id == run_id_b)
    else:
        run_a = sim.runs[-2]
        run_b = sim.runs[-1]

    input_a = RunInput.model_validate(run_a.input)
    input_b = RunInput.model_validate(run_b.input)
    diffs = diff_inputs(input_a, input_b)

    lead_id = input_b.productIds[0]
    out_a = _get_output(run_a).perProduct.get(lead_id)
    out_b = _get_output(run_b).perProduct.get(lead_id)

    deltas: dict[str, float] = {}
    facts: list[ToolFact] = []
    if out_a and out_b:
        d_price = (out_b.anchorPrice or 0.0) - (out_a.anchorPrice or 0.0)
        d_cgm = (out_b.cgm or 0.0) - (out_a.cgm or 0.0)
        d_cost = out_b.unitCost - out_a.unitCost
        deltas = {'deltaPrice': round(d_price, 2), 'deltaCGM': round(d_cgm, 2), 'deltaCost': round(d_cost, 2)}
        facts.append(ToolFact(key='delta_price', value=round(d_price, 2), unit='USD/t', label='Anchor Price Delta'))
        facts.append(ToolFact(key='delta_cgm', value=round(d_cgm, 2), unit='USD/t', label='CGM Delta'))

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'compare_runs', 'label': f'Compare runs (v{run_a.version} → v{run_b.version})', 'latencyMs': 20},
    ))

    data = {
        'versionA': run_a.version,
        'versionB': run_b.version,
        'inputDiffs': [d.model_dump() for d in diffs],
        'outputDeltas': deltas,
    }
    return data, facts, events


def tool_snapshot_view(
    store: Store,
    simulation_id: str,
    snapshot_id: str,
    product_ids: Optional[list[str]] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Evaluate current inputs under another historical snapshot without saving."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    prev = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None
    overrides: dict[str, Any] = {}
    if product_ids:
        overrides['productIds'] = product_ids

    # Find requested snapshot
    snaps = store.snapshots()
    target_snap = next((s for s in snaps if s.id == snapshot_id), None)
    if not target_snap:
        raise ValueError(f'Snapshot {snapshot_id} not found')

    # Create temporary input with period bounds or snapshot
    run_input = store.make_input(overrides, prev)
    ctx = store.ctx()
    # Replace snapshot in ctx temporarily
    ctx_override = store.ctx()
    ctx_override.snapshots = [target_snap] + [s for s in snaps if s.id != target_snap.id]
    output = store.run(run_input, ctx_override)

    lead_id = run_input.productIds[0]
    lead_res = output.perProduct[lead_id]

    facts = [
        ToolFact(key=f'snapshot_{snapshot_id}_anchor', value=round(lead_res.anchorPrice or 0.0, 2), unit='USD/t', label=f'Anchor under {target_snap.label}'),
        ToolFact(key=f'snapshot_{snapshot_id}_cgm', value=round(lead_res.cgm or 0.0, 2), unit='USD/t', label=f'CGM under {target_snap.label}'),
    ]

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'snapshot_view', 'label': f'Snapshot View · {target_snap.label}', 'latencyMs': 35},
    ))

    data = {
        'snapshot': target_snap.label,
        'anchorPrice': lead_res.anchorPrice,
        'cgm': lead_res.cgm,
        'unitCost': lead_res.unitCost,
    }
    return data, facts, events


def tool_draft_memo(
    store: Store,
    simulation_id: str,
    run_id: Optional[str] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Generate structured memo blocks with source references and verified figures."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    if not sim.runs:
        raise ValueError('No runs to draft memo from')

    run = next((r for r in sim.runs if r.id == run_id), sim.runs[-1]) if run_id else sim.runs[-1]
    input_data = RunInput.model_validate(run.input)
    lead_id = input_data.productIds[0]
    res = _get_output(run).perProduct[lead_id]

    blocks = [
        {
            'title': 'Executive Pricing Summary',
            'content': f'Proposed commercial positioning for {res.name} benchmarked against {input_data.referenceId}. Recommended anchor: {res.anchorPrice:.2f} USD/t.',
        },
        {
            'title': 'Cost Structure & Floor',
            'content': f'Raw material cost is {res.rawMaterial:.2f} USD/t with total unit cost {res.unitCost:.2f} USD/t, defining a cost-plus floor of {res.floor:.2f} USD/t.',
        },
        {
            'title': 'Value Creation & Agronomic Capture',
            'content': f'Agronomic value created is {res.addedValue:.2f} USD/t. Sharing {input_data.valueShare*100:.1f}% yields a value price of {res.prices.get("value", 0.0):.2f} USD/t.',
        },
        {
            'title': 'Contribution Gross Margin (CGM)',
            'content': f'At anchor price {res.anchorPrice:.2f} USD/t, product CGM is {res.cgm:.2f} USD/t compared to reference CGM of {res.cgmRef:.2f} USD/t.',
        },
    ]

    facts = [
        ToolFact(key='memo_anchor', value=round(res.anchorPrice or 0.0, 2), unit='USD/t', label='Memo Anchor Price'),
        ToolFact(key='memo_cgm', value=round(res.cgm or 0.0, 2), unit='USD/t', label='Memo CGM'),
    ]

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'draft_memo', 'label': f'Draft Executive Memo (v{run.version})', 'latencyMs': 25},
    ))

    return {'blocks': blocks, 'version': run.version}, facts, events


def tool_stage_change(
    store: Store,
    simulation_id: str,
    patch: dict[str, Any],
    label: str,
    reason: str,
) -> tuple[StagedChange, list[AgentEvent]]:
    """Propose an input change card requiring user confirmation before re-running."""
    sim = store.sim(simulation_id)
    if not sim.runs:
        raise ValueError('Cannot stage changes on an empty simulation')

    last_run = sim.runs[-1]
    base_input = RunInput.model_validate(last_run.input)
    candidate_input = store.make_input(patch, base_input)

    diffs = diff_inputs(base_input, candidate_input)
    before_map = {d.key: d.before for d in diffs}
    after_map = {d.key: d.after for d in diffs}

    change = StagedChange(
        id=_uid('c'),
        simulationId=simulation_id,
        baseVersion=last_run.version,
        label=label,
        reason=reason,
        patch=patch,
        before=before_map,
        after=after_map,
        status='staged',
    )

    event = AgentEvent(
        id=_uid('change'),
        type='change',
        payload=change.model_dump(by_alias=True),
    )
    return change, [event]


def tool_ask_user(
    question: str,
    options: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[AgentEvent]]:
    """Pause execution and render selectable option chips in the thread."""
    opts = [QuestionOption(**o) for o in options]
    event = AgentEvent(
        id=_uid('question'),
        type='question',
        payload={
            'text': question,
            'options': [o.model_dump() for o in opts],
        },
    )
    return {'question': question, 'options': [o.id for o in opts]}, [event]


def tool_run_sulphur_sensitivity(
    store: Store,
    product_id: str = 'phos-65-35',
    reference_id: str = 'TSP',
    from_price: float = 100.0,
    to_price: float = 1000.0,
    step: float = 50.0,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Execute sulphur sensitivity parameter sweep and resolve analytical break-evens."""
    events: list[AgentEvent] = []
    events.append(AgentEvent(
        id=_uid('step'),
        type='step',
        payload={'label': f'Calculating sulphur sensitivity ({from_price:.0f} → {to_price:.0f} USD/t)...', 'status': 'running'},
    ))

    p_row = store.product(product_id)
    ref_row = store.product(reference_id)
    snap = store.snapshots()[0]
    params = store.params()

    p_def = ProductDef(
        id=p_row.id,
        name=p_row.name,
        recipe=p_row.recipe,
        composition=Composition(**p_row.composition.model_dump()),
        pcf=p_row.pcf,
    )
    ref_def = ProductDef(
        id=ref_row.id,
        name=ref_row.name,
        recipe=ref_row.recipe,
        composition=Composition(**ref_row.composition.model_dump()),
        pcf=ref_row.pcf,
    )
    cost_prices = dict(snap.inputs)
    ref_quote = snap.refPrices.get(ref_row.id)
    ref_price = ref_quote.low if ref_quote else 640.0

    res = evaluate(EngineInput(
        products={p_def.id: p_def, ref_def.id: ref_def},
        product_ids=[p_def.id],
        reference_id=ref_def.id,
        cost_prices=cost_prices,
        reference_price=ref_price,
        params=EngineParams(
            cost_plus_margin=params.costPlusMargin,
            marketing_pct=params.marketingPct,
            anchor_method='refMinus',
        ),
    ))
    anchor_price = res.per_product[p_def.id].anchor_price

    sens_res = calc_sensitivity(
        new_product=p_def,
        ref_product=ref_def,
        cost_prices=cost_prices,
        anchor_price=anchor_price,
        ref_price=ref_price,
        marketing_pct=params.marketingPct,
        from_price=from_price,
        to_price=to_price,
        step=step,
    )

    facts: list[ToolFact] = []
    for be in sens_res.break_evens:
        if be.sulphur_price is not None:
            k = f'break_even_{be.product_id}_{be.kind}'
            facts.append(ToolFact(
                key=k,
                value=round(be.sulphur_price, 2),
                unit='USD/t',
                label=be.note,
            ))

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'run_sulphur_sensitivity', 'label': f'Sulphur sensitivity ({len(sens_res.points)} points)', 'latencyMs': 20},
    ))

    data = {
        'breakEvens': [b.model_dump() for b in sens_res.break_evens],
        'pointCount': len(sens_res.points),
    }
    return data, facts, events


def tool_explain_flags(
    store: Store,
    simulation_id: str,
    flag_codes: Optional[list[str]] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Plain-language audit explanation of engine flags (Data Checker specialist tool)."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    if not sim.runs:
        return {'explanations': []}, [], []

    output = _get_output(sim.runs[-1])
    flags = [f for f in output.flags if not flag_codes or f.code in flag_codes]

    explanations = []
    flag_meanings = {
        'P1': 'Anchor price is below the cost-plus floor. Commercial margin is compressed.',
        'W1': 'Agronomic yield gain unit discrepancy (0.12 marked % but treated as absolute t/ha in recipe).',
        'S1': 'Sulphur raw material input prices may be out of date relative to current benchmark.',
        'D1': 'CRU/Argus dataset date freshness gap between price inputs and ocean freight quotes.',
        'M1': 'Market pricing method requested but no competitor benchmark was provided.',
    }
    for f in flags:
        meaning = flag_meanings.get(f.code, f.title)
        explanations.append({'code': f.code, 'severity': f.severity, 'explanation': meaning})

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'explain_flags', 'label': 'Explain Flags & Data Freshness', 'latencyMs': 10},
    ))
    return {'explanations': explanations}, [], events


def tool_explain_run(
    store: Store,
    simulation_id: str,
    question: Optional[str] = None,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Explain valuation results and formula provenance (Explainer specialist tool)."""
    events: list[AgentEvent] = []
    sim = store.sim(simulation_id)
    if not sim.runs:
        return {'explanation': 'No simulation run available.'}, [], []

    run = sim.runs[-1]
    input_data = RunInput.model_validate(run.input)
    lead_id = input_data.productIds[0]
    res = _get_output(run).perProduct[lead_id]

    explanation = (
        f'For {res.name} vs {input_data.referenceId}, the Reference-Minus price is {res.anchorPrice:.2f} USD/t, '
        f'delivering a CGM of {res.cgm:.2f} USD/t compared to {res.cgmRef:.2f} USD/t for {input_data.referenceId}. '
        f'Unit cost is {res.unitCost:.2f} USD/t with cost-plus floor at {res.floor:.2f} USD/t.'
    )

    facts = [
        ToolFact(key='explainer_anchor', value=round(res.anchorPrice or 0.0, 2), unit='USD/t', label='Explainer Anchor Price'),
        ToolFact(key='explainer_cgm', value=round(res.cgm or 0.0, 2), unit='USD/t', label='Explainer CGM'),
    ]

    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={'name': 'explain_run', 'label': 'Explain Valuation Logic', 'latencyMs': 15},
    ))
    return {'explanation': explanation, 'question': question}, facts, events


def tool_search_knowledge(
    store: Store,
    query: str,
    doc_type: Optional[str] = None,
    limit: int = 4,
    first_ref: int = 1,
) -> tuple[dict[str, Any], list[ToolFact], list[AgentEvent]]:
    """Search uploaded reports, market commentary, freight indices, and agronomic field trial papers.

    Each result carries a `ref` (K1, K2…, numbered from `first_ref`) that the answer cites it by.
    """
    events: list[AgentEvent] = [AgentEvent(
        id=_uid('step'),
        type='step',
        payload={'label': 'Searching the indexed documents...', 'status': 'running'},
    )]
    started = time.perf_counter()
    try:
        passages = search(store.db, query, doc_type, max(1, min(limit, 8)))
    except EmbeddingError as e:
        return {'results': [], 'error': f'Knowledge search is unavailable: {e}'}, [], events

    results = [
        {
            'ref': f'K{first_ref + i}',
            'passage': p.passage,
            'source': p.source,
            'date': p.date.isoformat() if p.date else None,
            'page': p.page,
            'section': p.section,
            'relevance_score': p.relevanceScore,
            'label': p.label,
            'documentId': p.documentId,
            'chunkId': p.chunkId,
        }
        for i, p in enumerate(passages)
    ]
    events.append(AgentEvent(
        id=_uid('tool'),
        type='tool',
        payload={
            'name': 'search_knowledge',
            'label': f'Knowledge search · {len(results)} passage{"" if len(results) == 1 else "s"}',
            'latencyMs': round((time.perf_counter() - started) * 1000),
        },
    ))
    return {'results': results}, [], events


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tool Definitions for LLM Function Calling (OpenAI / OpenRouter JSON Schema)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        'type': 'function',
        'function': {
            'name': 'read_inputs',
            'description': 'Load data sources, active snapshot raw material costs, and current parameters with provenance.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'simulation_id': {
                        'type': 'string',
                        'description': 'Optional simulation ID to check current active version',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'check_inputs',
            'description': 'Check active simulation inputs for warnings, open items, and freshness gaps (P1, S1, D1, W1).',
            'parameters': {
                'type': 'object',
                'properties': {},
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_engine',
            'description': 'Execute pricing engine calculations for the specified product and reference fertilizer, persisting a new immutable run.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'product_ids': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'List of product IDs to price (e.g. ["phos-65-35"])',
                    },
                    'reference_id': {
                        'type': 'string',
                        'description': 'Reference fertilizer product ID (e.g. "TSP", "DAP")',
                    },
                    'overrides': {
                        'type': 'object',
                        'description': 'Optional input overrides (e.g. valueShare, marketingPct, carbonPrice)',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'compare_runs',
            'description': 'Compare input parameters and output KPIs (price, CGM, unit cost) between two simulation run versions.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'run_id_a': {'type': 'string', 'description': 'First run ID (defaults to previous run)'},
                    'run_id_b': {'type': 'string', 'description': 'Second run ID (defaults to latest run)'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'snapshot_view',
            'description': 'Derived output calculation under another historical snapshot (e.g. "2023", "2024") without persisting.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'snapshot_id': {'type': 'string', 'description': 'Historical snapshot ID (e.g. "2023", "2024", "period")'},
                    'product_ids': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Product IDs to evaluate',
                    },
                },
                'required': ['snapshot_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'draft_memo',
            'description': 'Generate structured pricing memo blocks with source references for executive review.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'run_id': {'type': 'string', 'description': 'Optional run ID (defaults to latest run)'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'stage_change',
            'description': 'Propose an input modification to the user via an interactive staged change card (human-in-the-loop).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'patch': {'type': 'object', 'description': 'The input fields to modify (e.g. {"valueShare": 0.5})'},
                    'label': {'type': 'string', 'description': 'User-facing label for the change'},
                    'reason': {'type': 'string', 'description': 'Business rationale for the proposed change'},
                },
                'required': ['patch', 'label', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ask_user',
            'description': 'Ask the user a question with selectable option chips and pause execution (human-in-the-loop).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string', 'description': 'The question to ask'},
                    'options': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'string'},
                                'label': {'type': 'string'},
                                'sub': {'type': 'string'},
                            },
                            'required': ['id', 'label'],
                        },
                        'description': 'Option chips to present to the user',
                    },
                },
                'required': ['question', 'options'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_sulphur_sensitivity',
            'description': 'Run sulphur price sweep and calculate zero-margin and parity crossover break-evens.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'product_id': {'type': 'string', 'default': 'phos-65-35'},
                    'reference_id': {'type': 'string', 'default': 'TSP'},
                    'from_price': {'type': 'number', 'default': 100.0},
                    'to_price': {'type': 'number', 'default': 1000.0},
                    'step': {'type': 'number', 'default': 50.0},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'explain_flags',
            'description': 'Data checker specialist tool: Plain-language explanation of open warnings and audit flags.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'flag_codes': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Optional specific flag codes to explain (e.g. ["P1", "W1"])',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_knowledge',
            'description': (
                'Search uploaded reports, market commentary, freight indices, agronomic field trial papers and methodology. '
                'Use it whenever explaining WHY a price, freight rate, or yield assumption was chosen, or when citing source documentation.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'What to look for, in plain words'},
                    'doc_type': {
                        'type': 'string',
                        'enum': ['market_report', 'freight', 'agronomy', 'methodology'],
                        'description': 'Optional: only this kind of document',
                    },
                    'limit': {'type': 'integer', 'default': 4, 'description': 'Number of passages (1 to 8)'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'explain_run',
            'description': 'Explainer specialist tool: Plain-language explanation of valuation and CGM results.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string', 'description': 'Optional specific question about the run'},
                },
                'required': [],
            },
        },
    },
]
