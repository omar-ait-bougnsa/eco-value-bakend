"""Data contracts and Pydantic v2 schemas for evs.engine."""
from typing import Annotated, Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

Method = Literal['costPlus', 'market', 'value', 'refMinus']
Mode = Literal['corrected', 'workbook']
Severity = Literal['error', 'warning', 'info', 'resolved']
IngredientId = Literal['ammonia', 'kcl', 'rockDry', 'rockWet', 'sulphur', 'acp']


class BaseSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid', allow_inf_nan=False)


class Composition(BaseSchema):
    N: float = Field(0.0, ge=0.0, le=1.0)
    P2O5: float = Field(0.0, ge=0.0, le=1.0)
    K2O: float = Field(0.0, ge=0.0, le=1.0)
    S: float = Field(0.0, ge=0.0, le=1.0)


class ProductDef(BaseSchema):
    id: str
    name: str
    family: str = 'phosfusion'
    recipe: dict[str, float] = Field(default_factory=dict)
    composition: Composition = Field(default_factory=Composition)
    pcf: Optional[float] = None
    pcf_placeholder: bool = False
    dna_override: Optional[float] = None


class NutrientFactors(BaseSchema):
    n_per_nh3: float = 0.82
    k2o_per_kcl: float = 0.60


class AgronomyData(BaseSchema):
    yield_gain: float = 0.0
    app_rate_new: float = 0.0
    app_rate_ref: float = 0.0
    crop_price: float = 0.0
    status: Literal['real', 'placeholder'] = 'real'


class EngineParams(BaseSchema):
    cost_plus_margin: float = Field(0.20, ge=0.0)
    marketing_pct: float = Field(0.0, ge=0.0)
    include_dna: bool = False
    dna_per_ton: float = Field(96.0, ge=0.0)
    value_share: float = Field(1.0 / 3.0, ge=0.0, le=1.0)
    anchor_method: Method = 'refMinus'
    carbon_price: float = Field(0.0, ge=0.0)
    nutrient_factors: NutrientFactors = Field(default_factory=NutrientFactors)
    include_ref_marketing: bool = False


class EngineInput(BaseSchema):
    products: dict[str, ProductDef]
    product_ids: list[str] = Field(min_length=1)
    reference_id: str
    methods: list[Method] = Field(default_factory=lambda: ['costPlus', 'refMinus', 'value', 'market'])
    cost_prices: dict[str, float]
    nutrient_prices: Optional[dict[str, float]] = None
    reference_price: Optional[float] = None
    benchmark_price: Optional[float] = None
    agronomy: dict[str, Optional[AgronomyData]] = Field(default_factory=dict)
    volume: Optional[float] = None
    params: EngineParams = Field(default_factory=EngineParams)
    mode: Mode = 'corrected'


class CostLine(BaseSchema):
    id: str
    label: str
    qty: float
    price: float
    usd: float


class MethodResult(BaseSchema):
    method: Method
    label: str
    price: Optional[float]
    cgm: Optional[float]
    cgm_p2o5: Optional[float] = Field(default=None, alias='cgmP2O5')
    total_margin: Optional[float] = Field(default=None, alias='totalMargin')
    delta_vs_ref: Optional[float] = Field(default=None, alias='deltaVsRef')


class WaterfallStep(BaseSchema):
    label: str
    from_: float = Field(alias='from')
    to: float
    value: float
    kind: Literal['total', 'delta']


class RampPoint(BaseSchema):
    year: int
    kt: float


class CarbonScenario(BaseSchema):
    id: str
    label: str
    price: float
    delta: float


class ProductResult(BaseSchema):
    product_id: str = Field(alias='productId')
    name: str
    lines: list[CostLine]
    raw_material: float = Field(alias='rawMaterial')
    dna: float
    marketing: float
    unit_cost: float = Field(alias='unitCost')
    ref_price: Optional[float] = Field(default=None, alias='refPrice')
    ref_cost: Optional[float] = Field(default=None, alias='refCost')
    p2o5_value_ref: Optional[float] = Field(default=None, alias='p2o5ValueRef')
    added_value: float = Field(alias='addedValue')
    carbon_saving_per_t: float = Field(alias='carbonSavingPerT')
    carbon_effect: float = Field(alias='carbonEffect')
    prices: dict[Method, Optional[float]]
    anchor_price: Optional[float] = Field(default=None, alias='anchorPrice')
    floor: float
    ceiling: float
    cgm: Optional[float]
    cgm_ref: Optional[float] = Field(default=None, alias='cgmRef')
    cgm_p2o5: Optional[float] = Field(default=None, alias='cgmP2O5')
    cgm_s: Optional[float] = Field(default=None, alias='cgmS')
    volume: Optional[float] = None
    total_margin: Optional[float] = Field(default=None, alias='totalMargin')
    methods: list[MethodResult]
    waterfall: list[WaterfallStep]
    ramp: list[RampPoint]
    carbon_scenarios: list[CarbonScenario] = Field(default_factory=list, alias='carbonScenarios')


class FlagAction(BaseSchema):
    label: str
    kind: str
    target: Optional[str] = None


class Flag(BaseSchema):
    id: str
    code: str
    severity: Severity
    title: str
    detail: Optional[str] = None
    action: Optional[FlagAction] = None


class Note(BaseSchema):
    code: str
    title: str
    cell: str
    workbook_val: Any = Field(alias='workbookVal')
    engine_val: Any = Field(alias='engineVal')
    impact: str


class TraceEntry(BaseSchema):
    key: str
    formula: str
    value: Any
    inputs: dict[str, Any] = Field(default_factory=dict)


class SensitivityPoint(BaseSchema):
    sulphur_price: float = Field(alias='sulphurPrice')
    cgm_new: Optional[float] = Field(default=None, alias='cgmNew')
    cgm_ref: Optional[float] = Field(default=None, alias='cgmRef')
    delta_cgm: Optional[float] = Field(default=None, alias='deltaCgm')


class BreakEven(BaseSchema):
    product_id: str = Field(alias='productId')
    sulphur_price: Optional[float] = Field(default=None, alias='sulphurPrice')
    kind: Literal['zero_margin', 'crossover']
    note: str


class SensitivityResult(BaseSchema):
    variable: str = 'sulphur'
    points: list[SensitivityPoint]
    break_evens: list[BreakEven] = Field(alias='breakEvens')


class EngineOutput(BaseSchema):
    per_product: dict[str, ProductResult] = Field(alias='perProduct')
    flags: list[Flag]
    notes: list[Note] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)

