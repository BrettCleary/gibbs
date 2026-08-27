"""Pydantic API schemas (the OpenAPI surface the TypeScript client is generated from)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CampaignStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StrategyName(str, Enum):
    agent = "agent"
    random = "random"
    grid = "grid"
    uncertainty = "uncertainty"


class ProblemType(str, Enum):
    ising_v0 = "ising_v0"
    alloy_v1 = "alloy_v1"
    fcc_v2 = "fcc_v2"
    phase_v2 = "phase_v2"
    dft_v3 = "dft_v3"
    property_v3 = "property_v3"


DEFAULT_OBJECTIVES = {
    ProblemType.ising_v0: "Locate the critical-temperature region of the 2D Ising "
    "model with a finite Monte Carlo budget.",
    ProblemType.alloy_v1: "Discover the stable ordered structures of a binary alloy "
    "with a hidden Hamiltonian, using as few oracle energy queries as possible.",
    ProblemType.fcc_v2: "Discover the stable ordered FCC Ni-Al structures governed "
    "by a hidden cluster expansion, using as few oracle energy queries as possible.",
    ProblemType.phase_v2: "Map the order/disorder phase boundary Tc(x) of an FCC "
    "Ni-Al alloy with a finite canonical Monte Carlo budget, prioritising the "
    "most uncertain boundaries.",
    ProblemType.dft_v3: "Discover the stable ordered FCC Ni-Al structures with real "
    "first-principles calculations, using as few expensive runs as possible.",
    ProblemType.property_v3: "Find the FCC Ni-Al ordering with the highest bulk modulus "
    "that is thermodynamically stable and remains ordered below the threshold temperature.",
}


class PropertyEngine(str, Enum):
    hidden = "hidden"
    emt = "emt"


class DftEngine(str, Enum):
    emt = "emt"
    espresso = "espresso"


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    problem_type: ProblemType = ProblemType.ising_v0
    objective: str = Field(
        default="",
        description="Defaults to the problem's canonical objective when empty.",
    )
    composition_min: float | None = Field(default=None, ge=0.0, le=1.0)
    composition_max: float | None = Field(default=None, ge=0.0, le=1.0)
    composition_slices: list[float] | None = Field(
        default=None,
        description="Composition slices for phase-diagram campaigns "
        "(each strictly between 0 and 1; default [0.25, 0.5, 0.75]).",
    )
    strategy: StrategyName = StrategyName.agent
    property_engine: PropertyEngine = Field(
        default=PropertyEngine.hidden,
        description="Energy/property engine for property_v3 campaigns: hidden synthetic "
        "oracle (benchmarkable) or EMT (real classical potential).",
    )
    temperature_threshold: float = Field(
        default=1200.0, gt=0, description="Property campaigns: candidates must stay ordered below this T (K)."
    )
    dft_engine: DftEngine = Field(
        default=DftEngine.emt,
        description="Energy engine for dft_v3 campaigns: 'emt' (fast classical "
        "potential) or 'espresso' (real Quantum ESPRESSO DFT; needs pw.x + pseudos).",
    )
    temperature_min: float = 1.5
    temperature_max: float = 3.5
    lattice_size: int = Field(default=24, ge=8, le=64)
    simulation_budget: int = Field(default=20, ge=4, le=200)
    target_uncertainty: float | None = Field(
        default=None,
        description="Stop early when the Tc-estimate std drops below this value.",
    )
    failure_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=0.9,
        description="Injected simulation-failure probability (for failure-recovery demos).",
    )

    @model_validator(mode="after")
    def _check_range(self):
        if self.temperature_max <= self.temperature_min:
            raise ValueError("temperature_max must exceed temperature_min")
        if (
            self.composition_min is not None
            and self.composition_max is not None
            and self.composition_max <= self.composition_min
        ):
            raise ValueError("composition_max must exceed composition_min")
        if self.composition_slices is not None:
            if not self.composition_slices or any(
                not 0.0 < x < 1.0 for x in self.composition_slices
            ):
                raise ValueError("composition_slices must be non-empty, each in (0, 1)")
        if not self.objective:
            self.objective = DEFAULT_OBJECTIVES[self.problem_type]
        return self


class CampaignRead(BaseModel):
    id: str
    name: str
    objective: str
    problem_type: str
    strategy: str
    temperature_min: float
    temperature_max: float
    composition_min: float | None = None
    composition_max: float | None = None
    lattice_size: int
    simulation_budget: int
    simulations_used: int
    target_uncertainty: float | None
    failure_rate: float
    status: CampaignStatus
    stopping_rationale: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CalculationRead(BaseModel):
    id: str
    campaign_id: str
    structure_id: str | None = None
    calculation_type: str
    engine: str
    status: str
    input_parameters: dict[str, Any]
    output: dict[str, Any] | None
    provenance: dict[str, Any] | None
    failure_category: str | None
    failure_metadata: dict[str, Any] | None
    retry_of: str | None
    changed_parameters: dict[str, Any] | None
    reason_for_change: str | None
    resolution: str | None
    stdout_artifact: str | None = None
    stderr_artifact: str | None = None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class SurrogateModelRead(BaseModel):
    id: str
    campaign_id: str
    type: str
    version: int
    training_calculation_ids: list[str]
    parameters: dict[str, Any]
    validation_metrics: dict[str, Any]
    artifact: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentEventRead(BaseModel):
    id: str
    agent_run_id: str | None
    campaign_id: str
    event_type: str
    hypothesis: str | None
    reasoning_summary: str | None
    action: str | None
    tool_name: str | None
    tool_input: dict[str, Any] | None
    tool_output_reference: str | None
    payload: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignSurrogateView(BaseModel):
    """Everything the dashboard needs to draw chi(T) with uncertainty."""

    campaign_id: str
    model_version: int | None
    temperatures: list[float]
    mean: list[float]
    std: list[float]
    measured_temperatures: list[float]
    measured_values: list[float]
    measured_errors: list[float]
    measured_calculation_ids: list[str]
    tc_mean: float | None
    tc_std: float | None


class StructureRead(BaseModel):
    id: str
    campaign_id: str
    label: str
    chemical_formula: str
    composition: float
    n_sites: int
    occupations: list[list[int]]
    shape: list[int]
    lattice: list[list[float]] | None = None
    positions: list[list[float]] | None = None
    atomic_numbers: list[int] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HullPoint(BaseModel):
    structure_id: str
    label: str
    x: float
    e_form: float | None = None
    e_form_std: float | None = None
    measured: bool = False
    predicted_stable: bool = False


class AlloyHullView(BaseModel):
    """Everything the dashboard needs to draw the formation-energy hull."""

    campaign_id: str
    model_version: int | None
    loocv_rmse: float | None
    points: list[HullPoint]
    hull_x: list[float]
    hull_e: list[float]
    stable_labels: list[str]
    endpoints_measured: bool


class PhaseMeasurementView(BaseModel):
    calculation_id: str
    temperature: float
    heat_capacity: float
    heat_capacity_err: float
    sro: float


class PhaseSliceView(BaseModel):
    x: float
    tc_mean: float | None = None
    tc_std: float | None = None
    tc_edge_pinned: bool = False
    curve_t: list[float] = []
    curve_mean: list[float] = []
    curve_std: list[float] = []
    measured: list[PhaseMeasurementView] = []


class PhaseDiagramView(BaseModel):
    """Everything the dashboard needs to draw the T-x phase diagram."""

    campaign_id: str
    model_version: int | None
    temperature_min: float
    temperature_max: float
    slices: list[PhaseSliceView]


class CandidateRead(BaseModel):
    label: str
    x: float
    e_form: float
    e_form_std: float
    e_above_hull: float
    bulk_modulus: float
    bulk_modulus_std: float
    measured: bool
    stable_0k: bool
    stability_at_threshold: str
    score: float


class CandidatesView(BaseModel):
    """Plan section 14: the ranked candidate table."""

    campaign_id: str
    temperature_threshold: float
    model_version: int | None
    top_candidate_label: str | None
    candidates: list[CandidateRead]


class BenchmarkProblem(str, Enum):
    ising = "ising"
    alloy = "alloy"
    fcc = "fcc"
    phase = "phase"
    property = "property"


class BenchmarkCreate(BaseModel):
    problem: BenchmarkProblem = BenchmarkProblem.ising
    strategies: list[StrategyName] = Field(
        default=[StrategyName.random, StrategyName.grid, StrategyName.uncertainty]
    )
    budget: int = Field(default=12, ge=4, le=60)
    seeds: list[int] = Field(default=[1, 2, 3])
    lattice_size: int = Field(default=16, ge=8, le=48)
    temperature_min: float = 1.5
    temperature_max: float = 3.5


class BenchmarkRead(BaseModel):
    id: str
    status: str
    config: dict[str, Any]
    results: list[dict[str, Any]] | None
    summary: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class StartResponse(BaseModel):
    campaign_id: str
    status: CampaignStatus
    agent_run_id: str | None = None
