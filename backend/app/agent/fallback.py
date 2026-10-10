"""Built-in agent: answers a turn with the engine and the stored data, without a language model.

Every number it writes comes from the engine or the store, never from this file. It prices a product (asking first
when the sources disagree), stages what-ifs, shows another analysis period, explains a run, opens the memo, checks
the uploads, runs the sulphur sensitivity and quotes the indexed documents.
"""
import re
import time
from datetime import date
from typing import Any, AsyncIterator, Iterator, Optional
from uuid import uuid4

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from ..limits import FieldError
from ..engine.period import CURRENT_YEAR, MON, YTD, Span, is_current_period, period_label, period_presets
from ..engine.run import METHOD_LABEL, freshness_flags
from ..routers.engine import sulphur_sweep
from ..schemas import Flag, ProductResult, RunInput
from ..store import Store
from .citations import cited, knowledge_answer
from .tools import tool_search_knowledge, tool_stage_change
from .types import AgentEvent

PRICING = re.compile(r'price|prix|calcul|run|simulate|compar')
WHAT_IF = re.compile(r'what if|set|change|use|make|try|update|if')
KNOWLEDGE = re.compile(r'\b(sources?|reports?|documents?|stud(y|ies)|according to|cite|citations?|knowledge|rapports?|selon)\b')


def _ev(type: str, **payload: Any) -> AgentEvent:
    return AgentEvent(id=f'{type}_{uuid4().hex[:8]}', type=type, payload=payload)  # type: ignore[arg-type]


def _text(content: str, sources: Optional[list[str]] = None) -> AgentEvent:
    return _ev('text', content=content, **({'sources': sources} if sources else {}))


def f2(n: Optional[float]) -> str:
    return '—' if n is None else f'{n:,.2f}'.replace('-', '−')


def pct(n: float, digits: int = 1) -> str:
    return f'{round(n * 100, digits):g}%'


def _num(n: float) -> str:
    return f'{n:g}'


def _day(d: date, year: bool = True) -> str:
    return f'{d.day:02d} {MON[d.month - 1]}' + (f' {d.year}' if year else '')


# ───────────────────────── what the text names ─────────────────────────

def parse_products(store: Store, t: str) -> list[str]:
    """The Phosfusion grades named by their ratio (`65-35`, `65 35`), in the order they are named.
    `phosfusion` alone means the product a run starts from."""
    found: list[tuple[int, str]] = []
    ratios: set[tuple[str, str]] = set()
    for p in store.products():
        m = re.search(r'(\d+)[-\s](\d+)', p.name) if p.family == 'phosfusion' else None
        if not m or m.groups() in ratios:  # the first product of a ratio is the plain grade
            continue
        ratios.add(m.groups())
        at = re.search(rf'{m.group(1)}[-\s]?{m.group(2)}', t)
        if at:
            found.append((at.start(), p.id))
    ids = [i for _, i in sorted(found)]
    if not ids and 'phos' in t:
        ids = store.default_input()['productIds'][:1]
    return ids


def parse_reference(store: Store, t: str) -> Optional[str]:
    return next((p.id for p in store.products() if p.family == 'reference' and re.search(rf'\b{re.escape(p.id.lower())}\b', t)), None)


def find_products(store: Store, t: str) -> list[str]:
    """Products the text names: by id or full name, or a Phosfusion grade by its ratio."""
    named = [p.id for p in store.products() if re.search(rf'(?<![\w-]){re.escape(p.id.lower())}(?![\w-])', t) or p.name.lower() in t]
    return list(dict.fromkeys([*named, *(parse_products(store, t) if re.search(r'\d', t) else [])]))


def product_card(store: Store, product_id: str) -> str:
    """What the library holds about a product, and its raw-material cost at this year's prices."""
    from ..routers.products import _recipe_cost
    p = store.product(product_id)
    cost = _recipe_cost(store, p.recipe, None, None)
    recipe = ', '.join(f'{l.label} {_num(l.qty)} t/t' for l in cost.lines) or 'no ingredient'
    nutrients = ', '.join(f'{label} {pct(v, 2)}' for label, v in (('N', p.composition.N), ('P2O5', p.composition.P2O5), ('K2O', p.composition.K2O), ('S', p.composition.S)) if v) or 'none stored'
    lines = [
        f'**{p.name}** ({p.family}{", set aside for review" if p.status == "quarantined" else ""})',
        f'- Recipe: {recipe}',
        f'- Composition: {nutrients}',
        f'- Raw-material cost: {f2(cost.rawMaterial) + " USD/t" if cost.rawMaterial is not None else "unavailable (" + (cost.unavailable or "no price") + ")"} · {cost.snapshotLabel} prices, as of {_day(cost.asOf)}',
    ]
    if p.pcf is not None:
        lines.append(f'- Carbon footprint: {_num(p.pcf)} t CO₂/t' + (' (placeholder)' if p.pcfPlaceholder else ''))
    if p.appRate is not None:
        lines.append(f'- Application rate: {_num(p.appRate)} t/ha')
    if p.yieldGain is not None:
        lines.append(f'- Yield gain vs reference: {_num(p.yieldGain)} {p.yieldGainUnit or "(unit not stored: used as t/ha)"}')
    return '\n'.join(lines)


def supported_commands(store: Store) -> list[dict[str, str]]:
    """What the rule-based assistant understands, each with a request that works as it is."""
    reference = store.default_input()['referenceId']
    year = next((label for id, label, _ in period_presets() if id.isdigit()), None)
    return [
        {'label': 'Price a product', 'example': price_prompt(store)},
        {'label': 'Product information', 'example': f'Show product {reference}'},
        {'label': 'What-if on an input', 'example': 'What if the value share is 50%?'},
        *([{'label': 'Another analysis period', 'example': f'Show the {year} analysis period'}] if year else []),
        {'label': 'Explain a run', 'example': 'Why is the anchor below the floor?'},
        {'label': 'Sulphur break-even', 'example': 'Show the sulphur break-even'},
        {'label': 'Data freshness', 'example': 'Check my data for gaps'},
        {'label': 'Latest uploads', 'example': 'What changed since the last upload?'},
        {'label': 'Decision memo', 'example': 'Draft the memo'},
        {'label': 'Search the documents', 'example': 'What do the reports say about freight?'},
    ]


def price_prompt(store: Store) -> str:
    d = store.default_input()
    return f'Price {store.product(d["productIds"][0]).name} against {d["referenceId"]}'


def start_prompts(store: Store) -> list[str]:
    """What to ask first."""
    grades = [p.name for p in store.products() if p.family == 'phosfusion'][:2]
    compare = [f'Compare {grades[0]} and {grades[1]}'] if len(grades) == 2 else []
    return [price_prompt(store), *compare, 'Check my data for gaps', 'What changed since the last upload?']


def next_prompts(store: Store) -> list[str]:
    """What to ask once a simulation has a run."""
    year = next((label for id, label, _ in period_presets() if id.isdigit()), None)
    return ['What if the value share is 50%?', 'Why is the anchor below the floor?',
            *([f'Show the {year} analysis period'] if year else []), 'Show the sulphur break-even']


def title_for(store: Store, input: RunInput) -> str:
    names = [store.product(i).name for i in input.productIds]
    base = names[0] if len(names) == 1 else 'Phosfusion ' + ' & '.join(n.replace('Phosfusion ', '') for n in names)
    per = Span(input.periodFrom, input.periodTo)
    return f'{base} vs {input.referenceId}' + ('' if per == YTD else f' · {period_label(per)}')


def sources_for(store: Store, input: RunInput) -> list[str]:
    """The uploads a run's numbers rest on."""
    uploads = store.uploads()
    per = Span(input.periodFrom, input.periodTo)
    out: list[str] = []
    if is_current_period(per):
        argus = max((u for u in uploads if 'argus' in u.name.lower()), key=lambda u: u.fileDate, default=None)
        if argus:
            out.append(f'Prices · {_day(argus.fileDate, year=False)}')
        out.append(f'Standard cost · {CURRENT_YEAR}')
    else:
        out.append(f'CRU averages · {period_label(per)}')
    for type, label in (('agro', 'Agro trials'), ('crop', 'Crop prices')):
        u = next((u for u in uploads if u.type == type), None)
        if u:
            out.append(f'{label} · {_day(u.fileDate, year=False)}')
    return out


def summary_text(input: RunInput, r: ProductResult) -> str:
    below = r.anchorPrice is not None and r.anchorPrice < r.floor
    first = (
        f'**Recommended anchor: {f2(r.anchorPrice)} USD/t ({METHOD_LABEL[input.anchor].lower()}).** '
        + (f'That is below the cost-plus floor of {f2(r.floor)}, so at this price' if below else f'That sits above the cost-plus floor of {f2(r.floor)}. At this price')
        + f' {r.name} earns {f2(r.cgm)} USD/t against {input.referenceId}’s {f2(r.cgmRef)} USD/t.'
    )
    second = (
        f'Value pricing allows up to {f2(r.ceiling)} USD/t if OCP keeps {pct(input.valueShare)} of the {f2(r.addedValue)} USD/t of crop value created.'
        + (' Market pricing needs a competitor benchmark.' if input.benchmark is None else f' The competitor benchmark is {f2(input.benchmark)} USD/t.')
    )
    return f'{first}\n\n{second}'


# ───────────────────────── pricing ─────────────────────────

def _price(store: Store, sim, input: RunInput, summary: str) -> Iterator[AgentEvent]:
    """Check the sources of an input, ask when they disagree, else run it as the next version."""
    yield _ev('step', label='Checking sources and data freshness', status='running')
    flags = store.run(input).flags
    for f in flags:
        if f.code == 'D1':
            yield _ev('flag', **f.model_dump())
    ask = next((f for f in flags if f.severity == 'warning' and f.options), None)
    if ask:
        # The run waits for the answer. `resume` comes back with it, so nothing about the question is kept here.
        yield _ev(
            'question', text=f'{ask.title}: {ask.detail or ""} Which should I use?', flag=ask.code,
            options=[*({'id': o.id, 'label': o.label, 'sub': o.sub, 'primary': o.primary} for o in ask.options), {'id': 'sources', 'label': 'Open sources'}],
            resume=input.model_dump(mode='json'), summary=summary,
        )
        return
    yield from _run(store, sim, input, summary)


def _run(store: Store, sim, input: RunInput, summary: str) -> Iterator[AgentEvent]:
    first = not sim.runs
    started = time.perf_counter()
    run = store.add_run(sim, input, by='user', summary=summary)
    if first:
        store.rename_sim(sim, title_for(store, input))
    ms = round((time.perf_counter() - started) * 1000)
    yield _ev('tool', name='run_engine', label=f'Pricing engine · {len(input.methods)} methods · v{run.version} · {ms / 1000:.1f} s', latencyMs=ms)
    out = run.output
    if len(input.productIds) > 1:
        lines = '\n'.join(
            f'- **{r.name}**: anchor {f2(r.anchorPrice)} USD/t, CGM {f2(r.cgm)} USD/t (floor {f2(r.floor)}, ceiling {f2(r.ceiling)})'
            for r in (out.perProduct[i] for i in input.productIds)
        )
        content = f'{len(input.productIds)} products priced against {input.referenceId}:\n\n{lines}\n\nThe pivot bar lets you pin a product and compare strategies, or pin a strategy and compare products.'
    else:
        content = summary_text(input, out.perProduct[input.productIds[0]])
    yield _text(content, sources_for(store, input))
    yield _ev('result', runId=run.id, version=run.version)
    # The assumptions of this run that still wait for a confirmation.
    for f in out.flags:
        if f.severity in ('warning', 'error') and f.action and f.action.kind in ('open-input', 'open-product'):
            yield _ev('flag', **f.model_dump())
    yield _ev('suggest', items=next_prompts(store))


def _answer(store: Store, sim, answer: dict[str, Any], user_text: str) -> Iterator[AgentEvent]:
    """The user's answer to the question `_price` asked."""
    if answer['option'] == 'sources':
        yield from _knowledge(store, answer.get('question') or user_text)
        return
    if answer['option'] == 'discard':
        yield _text('Nothing was saved.')
        return
    input = store.make_input(answer.get('resume') or {})
    ask = next((f for f in store.run(input).flags if f.options and any(o.id == answer['option'] for o in f.options)), None)
    if ask:
        opt = next(o for o in ask.options if o.id == answer['option'])
        input = store.make_input({'resolved': {ask.code: opt.id}, 'refCostOverride': opt.refCostOverride}, input)
    yield from _run(store, sim, input, answer.get('summary') or 'Initial run')


# ───────────────────────── a simulation with a run ─────────────────────────

def parse_what_if(t: str, last: RunInput) -> Optional[tuple[dict[str, Any], str, str, str]]:
    """(patch, label, before, after) of the one input the text changes."""
    def num(rx: str) -> Optional[float]:
        m = re.search(rx, t)
        return float(m.group(1)) if m else None

    yes_no = lambda b: 'Yes' if b else 'No'
    if re.search(r'value\s*shar', t) and (n := num(r'(\d+(?:\.\d+)?)\s*%?')) is not None:
        return {'valueShare': n / 100}, 'Value share kept by OCP', pct(last.valueShare), pct(n / 100)
    if re.search(r'cost[- ]?plus|margin', t) and (n := num(r'(\d+(?:\.\d+)?)\s*%')) is not None:
        return {'costPlusMargin': n / 100}, 'Cost-plus margin', pct(last.costPlusMargin), pct(n / 100)
    if re.search(r'carbon\s*price', t) and (n := num(r'(\d+(?:\.\d+)?)')) is not None:
        return {'carbonPrice': n}, 'Carbon price', f'{_num(last.carbonPrice)} USD/t CO₂', f'{_num(n)} USD/t CO₂'
    if re.search(r'market\s*share', t) and (n := num(r'(\d+(?:\.\d+)?)\s*%?')) is not None:
        return {'marketShare': n / 100}, 'Market share captured', pct(last.marketShare), pct(n / 100)
    if re.search(r'benchmark|competitor', t) and (n := num(r'(\d+(?:\.\d+)?)')) is not None:
        return {'benchmark': n}, 'Market benchmark', 'not set' if last.benchmark is None else f'{f2(last.benchmark)} USD/t', f'{f2(n)} USD/t'
    if re.search(r'full\s*cost|d&a|depreciation', t):
        return {'fullCost': not last.fullCost}, 'Include manufacturing & D&A', yes_no(last.fullCost), yes_no(not last.fullCost)
    if 'anchor' in t and 'value' in t:
        return {'anchor': 'value'}, 'Anchor method', METHOD_LABEL[last.anchor], METHOD_LABEL['value']
    if 'anchor' in t and 'cost' in t:
        return {'anchor': 'costPlus'}, 'Anchor method', METHOD_LABEL[last.anchor], METHOD_LABEL['costPlus']
    return None


def _named_period(t: str) -> Optional[tuple[str, Span]]:
    """The preset the text asks for: the last 12 months, or a past year."""
    presets = {id: (label, span) for id, label, span in period_presets()}
    if re.search(r'last 12 months|past year|trailing', t) and re.search(r'period|compare|under|show|switch|use|what', t):
        return presets.get('l12')
    year = re.search(r'\b(20\d{2})\b', t)
    if year and re.search(r'condition|compare|year|snapshot|under|vs|period', t):
        return presets.get(year.group(1))
    return None


def _on_last_run(store: Store, sim, last: RunInput, t: str) -> Optional[Iterator[AgentEvent]]:
    """The requests that are about the latest run. None when the text is not one of them."""
    r = sim_result(sim, last)
    if re.search(r'\buse\s*\d', t) and last.resolved.get('S1'):
        return iter([_text('That question has already been resolved. Use the Hypotheses tab to change the reference cost.')])

    w = parse_what_if(t, last)
    if w and WHAT_IF.search(t):
        patch, label, before, after = w
        _, events = tool_stage_change(store, sim.id, patch, label, f'{label}: {before} → {after}')
        return iter([_text(f'That changes only **{label}**. Here is the proposed change — nothing is applied until you confirm.'), *events])

    named = _named_period(t)
    if named:
        label, span = named
        x = store.run(store.make_input({'periodFrom': span.start, 'periodTo': span.end}, last)).perProduct[last.productIds[0]]
        return iter([
            _ev('view', period={'from': span.start.isoformat(), 'to': span.end.isoformat()}, tab='overview'),
            _text(f'Switched the analysis period to **{label}** — a derived view, not a new run. Anchor {f2(x.anchorPrice)} USD/t against a cost-plus floor of {f2(x.floor)}; '
                  f'{last.referenceId} earns {f2(x.cgmRef)} USD/t. Use “Back” in the banner to return to the run’s period.'),
        ])

    sources = sources_for(store, last)
    if re.search(r'(why|explain).*(floor|below)', t):
        p2o5 = store.product(r.productId).composition.P2O5
        verdict = ('So the anchor sits below the floor: the nutrients are worth less than the cost plus margin.'
                   if r.anchorPrice is not None and r.anchorPrice < r.floor else 'The anchor clears the floor.')
        return iter([_text(
            f'The anchor is reference-minus: it values P2O5 at {last.referenceId}’s price ({f2(r.p2o5ValueRef)} USD per t P2O5) and applies that to the product’s {pct(p2o5, 2)} P2O5. '
            f'That gives {f2(r.prices["refMinus"])} USD/t. The cost-plus floor is unit cost {f2(r.unitCost)} × (1 + {pct(last.costPlusMargin, 0)}) = {f2(r.floor)}. {verdict}', sources)])
    if re.search(r'(why|explain).*value|value pric', t):
        return iter([_text(
            f'Value pricing = reference price {f2(r.refPrice)} + {pct(last.valueShare)} × {f2(r.addedValue)} USD/t of crop value created '
            f'({_num(last.yieldGain)} t/ha ÷ {_num(last.appRateNew)} t/ha × {_num(last.cropPrice)} USD/t) = **{f2(r.prices["value"])} USD/t**.', sources)])
    if re.search(r'memo|summar|résumé', t):
        version = sim.runs[-1].version
        return iter([
            _ev('view', memo=True),
            _text(f'I opened the decision memo for v{version}. Analysis period: {period_label(Span(last.periodFrom, last.periodTo))}. '
                  f'Anchor {r.name} at {f2(r.anchorPrice)} USD/t, in a corridor from {f2(r.floor)} (cost-plus floor) to {f2(r.ceiling)} USD/t (value ceiling).'),
        ])
    return None


def sim_result(sim, last: RunInput) -> ProductResult:
    """The lead product's result of the latest saved run."""
    return ProductResult.model_validate(sim.runs[-1].output['perProduct'][last.productIds[0]])


# ───────────────────────── the workspace ─────────────────────────

def _knowledge(store: Store, question: str) -> Iterator[AgentEvent]:
    """Without a model the passages are the answer."""
    data, _, events = tool_search_knowledge(store, question, limit=3)
    yield from events
    if 'error' in data:
        yield _text(data['error'])
        return
    content, citations = cited(knowledge_answer(data['results']), {r['ref']: r for r in data['results']})
    yield from citations
    yield _text(content)


def _sensitivity(store: Store, last: Optional[RunInput]) -> Iterator[AgentEvent]:
    d = store.default_input()
    pid, ref = (last.productIds[0], last.referenceId) if last else (d['productIds'][0], d['referenceId'])
    name = store.product(pid).name
    yield _ev('step', label='Running the sulphur price sensitivity', status='running')
    started = time.perf_counter()
    res = sulphur_sweep(store, pid, ref)
    yield _ev('tool', name='run_sulphur_sensitivity', label=f'Sulphur sensitivity · {len(res.points)} points', latencyMs=round((time.perf_counter() - started) * 1000))
    at = lambda id, kind: next((b.sulphur_price for b in res.break_evens if b.product_id == id and b.kind == kind), None)
    lo, hi = res.points[0], res.points[-1]
    zero, zero_ref, cross = at(pid, 'zero_margin'), at(ref, 'zero_margin'), at(pid, 'crossover')
    # The margin gap moves in a straight line with the sulphur price, so its two ends tell which product earns more above the crossover.
    above, under = (name, ref) if (hi.delta_cgm or 0) > (lo.delta_cgm or 0) else (ref, name)
    lines = [
        zero is not None and f'- **{name}** breaks even (zero margin) at **{f2(zero)} USD/t** sulphur',
        zero_ref is not None and f'- **{ref}** breaks even at **{f2(zero_ref)} USD/t**',
        cross is not None and f'- Both earn the same margin at **{f2(cross)} USD/t**: above it {above} earns more, below it {under} does',
    ]
    today = next((s.inputs.get('sulphur') for s in store.snapshots() if s.id == 'today'), None)
    yield _text(
        f'Sulphur swept from {lo.sulphur_price:,.0f} to {hi.sulphur_price:,.0f} USD/t, with {name} at its reference-minus anchor and the other inputs from today’s prices and the workspace parameters.\n\n'
        + ('\n'.join(l for l in lines if l) or 'No break-even in that range.')
        + (f'\n\nSulphur is at {f2(today)} USD/t today.' if today is not None else '')
    )


def _data_check(store: Store) -> Iterator[AgentEvent]:
    """Prices against freight (D1) and the age of the latest upload (D2), as the engine flags them."""
    flags: list[Flag] = freshness_flags(store.uploads(), store.params(), YTD)
    cards = [f for f in flags if f.severity in ('warning', 'error')]
    notes = ' '.join(f'Also: {f.title}.' for f in flags if f not in cards)
    verdict = 'Nothing looks off.' if not flags else 'One point needs attention:' if len(cards) == 1 else f'{len(cards)} points need attention:' if cards else ''
    yield _text(' '.join(x for x in ('I checked the data you have uploaded.', verdict, notes) if x))
    for f in cards:
        yield _ev('flag', **f.model_dump())
    yield _ev('suggest', items=[price_prompt(store)])


def _latest_uploads(store: Store) -> Iterator[AgentEvent]:
    latest = store.uploads()[:2]  # newest first
    if not latest:
        yield _text('Nothing has been uploaded yet.')
        return
    yield _text('The most recent uploads are ' + ' and '.join(f'**{u.name}** (file dated {_day(u.fileDate)}, data through {_day(u.dataThrough)})' for u in latest) + '.')


# ───────────────────────── a turn ─────────────────────────

def _turn(store: Store, sim, user_text: str, input: Optional[dict[str, Any]], answer: Optional[dict[str, Any]]) -> Iterator[AgentEvent]:
    last = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None
    if answer:
        yield from _answer(store, sim, answer, user_text)
        return
    if input is not None:  # the Configure run form
        yield from _price(store, sim, store.make_input(input), 'Configured run' if last else 'Initial run')
        return

    t = user_text.lower().strip()
    products = parse_products(store, t)
    named = {'productIds': products, **({'referenceId': ref} if (ref := parse_reference(store, t)) else {})}
    pricing = bool(products) and bool(PRICING.search(t))
    if pricing and not last:
        yield from _price(store, sim, store.make_input(named), 'Initial run')
        return
    about_run = _on_last_run(store, sim, last, t) if last else None
    described = [] if pricing else find_products(store, t)
    if about_run:
        yield from about_run
    elif described and re.search(r'\b(info|information|details?|about|describe|show|composition|recipe|what is|tell me)\b', t):
        yield _text('\n\n'.join(product_card(store, i) for i in described[:3]))
    elif re.search(r'sensitiv|sensibilit|break[- ]?even|seuil', t):
        yield from _sensitivity(store, last)
    elif KNOWLEDGE.search(t):
        yield from _knowledge(store, user_text)
    elif re.search(r'changed|new|latest', t) and 'upload' in t:
        yield from _latest_uploads(store)
    elif re.search(r'gap|check|données|inconsisten|fresh|stale|upload', t):
        yield from _data_check(store)
    elif re.search(r'\b(hello|hi|help)\b|what can', t):
        yield _text('I can price a product against a reference, check your data for gaps, re-run what-ifs (value share, margin, carbon price, market share), '
                    f'find the sulphur break-even, compare past years, and draft the decision memo. Try “{price_prompt(store)}”.')
    elif pricing:  # other products on a simulation that already has runs: its next version
        fresh = store.make_input(named)
        yield from _price(store, sim, fresh, f'Priced {title_for(store, fresh)}')
    else:
        # Not one of the requests this assistant knows. It says so, in a form a client can act on, and offers the ones it does.
        commands = supported_commands(store)
        yield _ev('text', code='unsupported_request', suggestions=commands,
                  content='I did not recognise that request, so nothing was run. I am a rule-based assistant, not an AI model: I only answer the requests below, worded like their examples. '
                          'I only quote numbers the engine has produced.')
        yield _ev('suggest', items=[c['example'] for c in commands])


async def run_scripted_turn(
    store: Store,
    simulation_id: str,
    user_text: str,
    input: Optional[dict[str, Any]] = None,
    answer: Optional[dict[str, Any]] = None,
) -> AsyncIterator[AgentEvent]:
    """One turn of the built-in agent. `input` prices a given run input; `answer` answers the question a pricing asked."""
    try:
        for event in _turn(store, store.sim(simulation_id), user_text, input, answer):
            yield event
    except RequestValidationError as e:
        yield _ev('error', message='; '.join(f'{".".join(str(x) for x in err["loc"][2:])}: {err["msg"]}' for err in e.errors()), code='invalid_input', fatal=True)
    except FieldError as e:
        yield _ev('error', message=str(e), code='invalid_input', fatal=True)
    except (HTTPException, ValueError) as e:
        yield _ev('error', message=str(getattr(e, 'detail', e)), code='request_refused', fatal=True)
    yield _ev('done', mode='script')
