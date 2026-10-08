"""API models.

Field names are camelCase on purpose: they mirror `src/engine/types.ts` one-to-one,
so the frontend can swap its mock data for these responses without a mapping layer.
"""
from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

# t ingredient / t product. The upper bound only keeps costs finite.
Quantity = Annotated[float, Field(ge=0, le=1000)]

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
    name: str = Field(min_length=1)
    family: Family = 'phosfusion'
    recipe: dict[IngredientId, Quantity] = Field(default_factory=dict, description='t ingredient / t product')
    composition: Composition = Field(default_factory=Composition)
    pcf: Optional[float] = Field(None, description='t CO2 / t product')
    pcfPlaceholder: Optional[bool] = None
    appRate: Optional[float] = Field(None, description='t product / ha')
    yieldGain: Optional[float] = Field(None, description='t crop / ha vs reference')


class Product(ProductIn):
    id: str


class Ingredient(Base):
    id: IngredientId
    label: str


class CostLine(Base):
    id: IngredientId
    label: str
    qty: float
    price: float
    usd: float


class RecipeCost(Base):
    snapshotId: str
    snapshotLabel: str
    lines: list[CostLine]
    rawMaterial: float


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
    yieldGain: float
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


class Flag(Base):
    id: str
    code: str
    severity: FlagSeverity
    title: str
    detail: Optional[str] = None
    action: Optional[FlagAction] = None


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


class Simulation(Base):
    id: str
    title: str
    createdAt: datetime
    runs: list[Run]


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
