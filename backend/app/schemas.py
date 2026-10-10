"""API models.

Field names are camelCase on purpose: they mirror `src/engine/types.ts` one-to-one,
so the frontend can swap its mock data for these responses without a mapping layer.
"""
from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

# t ingredient / t product. The upper bound only keeps costs finite.
Quantity = Annotated[float, Field(ge=0)]  # t ingredient / t product; its upper bound is a business limit (limits.py)
YieldUnit = Literal['t/ha', '%']
RecordStatus = Literal['active', 'quarantined']

IngredientId = Literal['ammonia', 'kcl', 'rockDry', 'rockWet', 'sulphur', 'acp']
Method = Literal['costPlus', 'market', 'value', 'refMinus']
RefId = Literal['DAP', 'MAP', 'TSP']
PriceType = Literal['low', 'high']
CarbonMarket = Literal['voluntary', 'cbam']
Family = Literal['phosfusion', 'reference', 'other']
UploadType = Literal['prices', 'freight', 'agro', 'crop']
FlagSeverity = Literal['error', 'warning', 'info', 'resolved']
CreatedBy = Literal['user', 'agent']


class Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', from_attributes=True, allow_inf_nan=False)


def partial(model: type[BaseModel], name: str) -> type[BaseModel]:
    """Same fields as `model`, all optional. Constraints are enforced after merging onto a full object."""
    fields = {n: (Optional[f.annotation], None) for n, f in model.model_fields.items()}
    return create_model(name, __base__=Base, **fields)


# ───────────────────────── products ─────────────────────────

class Composition(Base):
    """Nutrient content as fractions (0.46 = 46 %)."""
    N: float = Field(0, ge=0, le=1)
    P2O5: float = Field(0, ge=0, le=1)
    K2O: float = Field(0, ge=0, le=1)
    S: float = Field(0, ge=0, le=1)


class ProductIn(Base):
    """A product as it is written. The types are checked here; the business bounds in `limits.product_errors`."""
    name: str = Field(min_length=1)
    family: Family = 'phosfusion'
    recipe: dict[IngredientId, Quantity] = Field(default_factory=dict, description='t ingredient / t product')
    composition: Composition = Field(default_factory=Composition)
    pcf: Optional[float] = Field(None, description='t CO2 / t product')
    pcfPlaceholder: Optional[bool] = None
    appRate: Optional[float] = Field(None, description='t product / ha')
    yieldGain: Optional[float] = Field(None, description='Yield gain vs the reference, in `yieldGainUnit`')
    yieldGainUnit: Optional[YieldUnit] = Field(None, description='Unit of `yieldGain`. Null on records made before the unit was stored: used as t/ha, with a flag until someone confirms it')
    baselineYield: Optional[float] = Field(None, description='t crop / ha without the product. Needed when the yield gain is in %')

    @model_validator(mode='before')
    @classmethod
    def _trim(cls, v):
        if not isinstance(v, dict):
            return v
        if cls is ProductIn:  # a product read from the API can be sent back as it is: what the server sets is dropped
            v = {k: x for k, x in v.items() if k not in ('id', 'status', 'issues')}
        return {**v, 'name': v['name'].strip()} if isinstance(v.get('name'), str) else v


class Product(ProductIn):
    id: str
    status: RecordStatus = Field('active', description='A quarantined product failed the validation rules: it is kept, shown for review, and cannot be priced')
    issues: list[str] = Field(default_factory=list, description='Why it is quarantined')

    @model_validator(mode='before')
    @classmethod
    def _stored(cls, v):
        # Rows written before these columns existed.
        if not isinstance(v, dict):
            v = {k: getattr(v, k, None) for k in cls.model_fields}
        return {**v, 'status': v.get('status') or 'active', 'issues': v.get('issues') or []}


class FieldProblem(Base):
    field: str
    message: str


class Validation(Base):
    """What the server would reject, without saving anything: the forms show it next to each field."""
    errors: list[FieldProblem]


class Ingredient(Base):
    id: IngredientId
    label: str


class CostLine(Base):
    """`price` and `usd` are null when the period has no price for the ingredient."""
    id: IngredientId
    label: str
    qty: float
    price: Optional[float]
    usd: Optional[float]


class RecipeCost(Base):
    """Recipe × input prices of a period: what the product list, the editor and the engine all show."""
    snapshotId: str
    snapshotLabel: str
    periodFrom: date
    periodTo: date
    asOf: date = Field(description='Day the input prices are as of')
    source: str = Field(description='Where the input prices come from')
    lines: list[CostLine]
    rawMaterial: Optional[float] = Field(description='USD / t product. Null when a price is missing: see `unavailable`')
    unavailable: Optional[str] = Field(None, description='Why there is no total')


class RecipeCostRequest(Base):
    recipe: dict[IngredientId, Quantity]
    periodFrom: Optional[date] = None
    periodTo: Optional[date] = None


# ───────────────────────── market data ─────────────────────────

class Quote(Base):
    low: Optional[float] = None
    high: Optional[float] = None


class Snapshot(Base):
    id: str
    label: str
    asOf: date
    inputs: dict[IngredientId, float]
    refPrices: dict[RefId, Quote]
    source: str


class Period(Base):
    from_: date = Field(alias='from')
    to: date


class PeriodPreset(Base):
    id: str
    label: str
    period: Period


class ResolvedSnapshot(Base):
    period: Period
    label: str
    weights: dict[str, float] = Field(description='Share of the period (by days) per yearly snapshot')
    snapshot: Snapshot


class Outlook(Base):
    years: list[int]
    ammonia: list[float]
    kcl: list[float]
    sulphur: list[float]


# ───────────────────────── parameters ─────────────────────────

class Parameters(Base):
    costPlusMargin: float = Field(ge=0)
    fullCost: bool
    valueShare: float = Field(ge=0, le=1)
    marketingPct: float = Field(ge=0)
    dnaPerTon: float = Field(ge=0)
    marketShare: float = Field(ge=0, le=1)
    rampTargetYear: int
    priceType: PriceType
    carbonMarket: CarbonMarket
    freshnessMonths: float = Field(gt=0)
    staleDays: int = Field(ge=0)
    defaultReference: RefId


ParametersPatch = partial(Parameters, 'ParametersPatch')


# ───────────────────────── uploads ─────────────────────────

class UploadIn(Base):
    name: str = Field(min_length=1)
    type: UploadType
    fileDate: date
    dataThrough: date
    detail: Optional[str] = None


class UploadRecord(UploadIn):
    id: str
    uploadedAt: date
    sizeBytes: Optional[int] = None
    contentHash: Optional[str] = Field(None, description='SHA-256 of the file. Null on the demo records, which have no file')
    status: RecordStatus = 'active'
    issues: list[str] = Field(default_factory=list)
    duplicate: bool = Field(False, description='On upload: this exact file was already there, and that record is returned')

    @model_validator(mode='before')
    @classmethod
    def _stored(cls, v):
        if not isinstance(v, dict):
            v = {k: getattr(v, k, None) for k in cls.model_fields}
        return {**v, 'status': v.get('status') or 'active', 'issues': v.get('issues') or [], 'duplicate': bool(v.get('duplicate'))}


class UploadDetection(Base):
    """What the review sheet shows before the data is used."""
    name: str
    size: str
    type: UploadType
    typeLabel: str
    fileDate: date
    dataThrough: date
    series: str
    affects: list[str]
    resolves: bool = Field(description='Adding this file clears the prices/freight freshness flag (D1)')
    warn: Optional[str] = None
    problems: list[str] = Field(default_factory=list, description='Why the file would be refused. Empty when it can be used')
    duplicateOf: Optional[str] = Field(None, description='Id of the upload that already holds this exact file')


# ───────────────────────── engine ─────────────────────────

class RunInput(Base):
    productIds: list[str] = Field(min_length=1)
    referenceId: RefId
    periodFrom: date
    periodTo: date
    methods: list[Method]
    costPlusMargin: float = Field(ge=0)
    marketingPct: float = Field(ge=0)
    fullCost: bool
    dnaPerTon: float = Field(ge=0)
    valueShare: float = Field(ge=0, le=1)
    priceType: PriceType
    cropPrice: float = Field(ge=0)
    yieldGain: float = Field(description='In `yieldGainUnit`')
    yieldGainUnit: YieldUnit = Field('t/ha', description='t/ha, or % of `baselineYield`')
    baselineYield: Optional[float] = Field(None, description='t crop / ha without the product: turns a gain in % into t/ha')
    appRateNew: float = Field(ge=0)
    appRateRef: float = Field(ge=0)
    pcfNew: float
    pcfRef: float
    carbonMarket: CarbonMarket
    carbonPrice: float = Field(ge=0)
    marketShare: float = Field(ge=0, le=1)
    rampTargetYear: int
    addressable: float = Field(ge=0)
    benchmark: Optional[float] = None
    anchor: Method
    refCostOverride: Optional[float] = None
    comment: str = ''
    resolved: dict[str, str | bool] = Field(default_factory=dict)

    @model_validator(mode='after')
    def _period_in_order(self):
        if self.periodFrom > self.periodTo:
            raise ValueError('periodFrom must not be after periodTo')
        return self


RunInputPatch = partial(RunInput, 'RunInputPatch')


class FlagAction(Base):
    label: str
    kind: Literal['answer', 'open-input', 'open-uploads', 'open-product', 'add-benchmark', 'review', 'dismiss']
    target: Optional[str] = None


class FlagOption(Base):
    """One answer to a flag that asks a question (action kind `answer`)."""
    id: str
    label: str
    sub: Optional[str] = None
    refCostOverride: Optional[float] = Field(None, description='Reference cost to send as `refCostOverride` with this answer; null keeps the computed cost')
    primary: bool = False


class Flag(Base):
    id: str
    code: str
    severity: FlagSeverity
    title: str
    detail: Optional[str] = None
    action: Optional[FlagAction] = None
    options: Optional[list[FlagOption]] = None


class MethodResult(Base):
    method: Method
    label: str
    price: Optional[float]
    cgm: Optional[float]
    cgmP2O5: Optional[float]
    totalMargin: Optional[float] = Field(description='USD / yr')
    deltaVsRef: Optional[float]


class WaterfallStep(Base):
    label: str
    from_: float = Field(alias='from')
    to: float
    value: float
    kind: Literal['total', 'delta']


class RampPoint(Base):
    year: int
    kt: float


class CarbonScenario(Base):
    id: str
    label: str
    price: float
    delta: float


class ProductResult(Base):
    productId: str
    name: str
    lines: list[CostLine]
    rawMaterial: float
    dna: float
    marketing: float
    unitCost: float
    refPrice: Optional[float]
    refCost: Optional[float]
    p2o5ValueRef: Optional[float]
    yieldGainTHa: Optional[float] = Field(None, description='The yield gain the value pricing used, in t crop / ha')
    addedValue: float
    carbonSavingPerT: float
    carbonEffect: float
    prices: dict[Method, Optional[float]]
    anchorPrice: Optional[float]
    floor: float
    ceiling: float
    cgm: Optional[float]
    cgmRef: Optional[float]
    cgmP2O5: Optional[float]
    cgmS: Optional[float]
    # Comparisons with the reference. Null on runs saved before these fields existed.
    cgmRefP2O5: Optional[float] = None
    deltaVsRef: Optional[float] = None
    costVsRef: Optional[float] = None
    sulphurShare: Optional[float] = Field(None, description='Share of the unit cost that is sulphur (0–1)')
    volume: float
    totalMargin: Optional[float]
    methods: list[MethodResult]
    waterfall: list[WaterfallStep]
    ramp: list[RampPoint]
    carbonScenarios: list[CarbonScenario]


class RunOutput(Base):
    perProduct: dict[str, ProductResult]
    flags: list[Flag]


class EngineResult(Base):
    input: RunInput
    output: RunOutput


class InputChange(Base):
    key: str
    before: object
    after: object


class DiffRequest(Base):
    before: RunInput
    after: RunInput


# ───────────────────────── simulations ─────────────────────────

class Run(Base):
    id: str
    version: int
    input: RunInput
    output: RunOutput
    createdAt: datetime
    createdBy: CreatedBy
    summary: str
    changed: list[str] = Field(description='Input keys changed vs the previous run')
    editedKeys: list[str] = Field(description='Input keys changed vs v1')
    productSig: dict[str, str] = Field(default_factory=dict)


class RunCreate(Base):
    input: RunInputPatch = Field(  # type: ignore[valid-type]
        default_factory=RunInputPatch,
        description='Applied on top of the previous run\'s input, or on the defaults for the first run',
    )
    replace: bool = Field(False, description='`input` is complete: use it as is instead of applying it on top of the previous run')
    createdBy: CreatedBy = 'user'
    summary: Optional[str] = None


JobState = Literal['queued', 'running', 'completed', 'failed', 'cancelled', 'timed_out']


class Job(Base):
    """A turn of the agent, with the state it is really in."""
    id: str = Field(description='Also the correlation id: quote it to find the turn in the server logs')
    simulationId: str
    kind: Literal['message', 'run', 'answer']
    state: JobState
    mode: Optional[Literal['llm', 'script']] = None
    request: dict = Field(description='What was asked (text, input, answer): send it again to retry')
    result: Optional[dict] = Field(None, description='outcome: run | question | change | answer | unsupported; runVersion when a run was saved')
    failureCode: Optional[str] = None
    error: Optional[str] = Field(None, description='Why it failed, in words that are safe to show')
    transitions: list[dict] = Field(description='[{state, at}], in order')
    createdAt: datetime
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    timeoutSeconds: float = Field(description='A job still running after this long is ended as timed_out')


class Simulation(Base):
    id: str
    title: str
    createdAt: datetime
    runs: list[Run]
    job: Optional[Job] = Field(None, description='Its latest agent job: what a reloaded page shows')


class SimulationSummary(Base):
    id: str
    title: str
    createdAt: datetime
    runCount: int


class SimulationCreate(Base):
    title: str = Field(min_length=1)


class SimulationPatch(Base):
    title: str = Field(min_length=1)


class Freshness(Base):
    latest: Optional[UploadRecord]
    through: Optional[UploadRecord]
    warn: bool
    d1: Optional[Flag]
    d2: Optional[Flag]
    behind: dict[str, int] = Field(default_factory=dict, description='Months behind the latest freight file, per Argus price upload that is too old (upload id → months)')
