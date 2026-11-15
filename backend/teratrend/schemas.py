"""TeraTrend data structures and JSON serialization schemas.

Clean, strongly-typed dataclasses for backend domain objects.
Provides `.to_dict()` on all schemas ensuring JSON-safe output.
Does NOT import Flask or any external serialization library.
"""
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Union

def _clean_val(v: Any) -> Any:
    """Recursively clean floats (NaN, inf) to None for JSON compatibility."""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    elif isinstance(v, dict):
        return {k: _clean_val(val) for k, val in v.items()}
    elif isinstance(v, list):
        return [_clean_val(elem) for elem in v]
    return v


@dataclass
class Region:
    """Geographic administrative region within India."""
    state: str
    is_union_territory: bool = False
    district: Optional[str] = None
    agro_climatic_zone: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class GridPoint:
    """Resolved grid point with coordinate snap and layer fallback metadata."""
    requested_lat: float
    requested_lon: float
    snapped_lat: float
    snapped_lon: float
    snap_distance_km: float
    region: Region
    place_name: Optional[str] = None
    fallback_used: bool = False
    fallback_distance_km: float = 0.0
    layer_status: Dict[str, str] = field(default_factory=dict)  # "OK", "FALLBACK", "NO_DATA"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested": {"lat": round(self.requested_lat, 4), "lon": round(self.requested_lon, 4)},
            "snapped": {"lat": round(self.snapped_lat, 4), "lon": round(self.snapped_lon, 4)},
            "snap_distance_km": round(self.snap_distance_km, 2),
            "region": self.region.to_dict(),
            "place_name": self.place_name,
            "fallback": {
                "used": self.fallback_used,
                "distance_km": round(self.fallback_distance_km, 2) if self.fallback_used else 0.0,
                "layers": self.layer_status
            }
        }


@dataclass
class TrendResult:
    """Modified Mann-Kendall and Sen's slope trend test result."""
    indicator: str
    source: str
    n_years: int
    start_year: int
    end_year: int
    p_value: float
    significant: bool
    direction: str  # "increasing", "decreasing", "no_trend"
    sens_slope_per_year: float
    sens_slope_per_decade: float
    total_change_pct: Optional[float]
    standardized_change: Optional[float]
    tau: float
    intercept: float
    baseline_mean: float
    recent_mean: float
    annual_values: List[Dict[str, Any]] = field(default_factory=list)
    trend_line: List[Dict[str, Any]] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class SourceTrend:
    """Single-dataset trend summary within a multi-source consensus group."""
    dataset: str
    p_value: float
    significant: bool
    direction: str
    sens_slope_per_decade: float
    standardized_change: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class ConsensusResult:
    """Multi-dataset consensus evaluation on overlapping observation years."""
    group: str
    consensus_level: str  # "STRONG", "MODERATE", "WEAK", "CONFLICTING", "SINGLE_SOURCE"
    sources_used: List[str]
    sources_excluded: List[Dict[str, str]]
    overlap_years: int
    direction: str
    individual_trends: Dict[str, SourceTrend]
    pairwise_correlations: Dict[str, float]
    vegetation_confirms: Optional[bool] = None
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val({
            "group": self.group,
            "consensus_level": self.consensus_level,
            "sources_used": self.sources_used,
            "sources_excluded": self.sources_excluded,
            "overlap_years": self.overlap_years,
            "direction": self.direction,
            "individual_trends": {k: v.to_dict() for k, v in self.individual_trends.items()},
            "pairwise_correlations": self.pairwise_correlations,
            "vegetation_confirms": self.vegetation_confirms,
            "summary": self.summary
        })


@dataclass
class FactorReport:
    """Individual agricultural suitability factor assessment."""
    factor: str  # "temperature", "moisture", "soil_ph", "soil_quality", "climate"
    score: float
    rating: str  # "GOOD", "MODERATE", "POOR"
    values: Dict[str, Any]
    ideal: Dict[str, Any]
    explanation: str
    trend: Optional[Dict[str, Any]] = None  # Outlook, slope, projected value in 10y
    consensus: Optional[Dict[str, Any]] = None
    components: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    sources: List[str] = field(default_factory=list)
    confidence: str = "high"  # "high", "medium", "low", "no_data"

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class CropEconomicsSummary:
    """Compact economics summary attached to suited crops."""
    available: bool
    net_return_per_ha: Optional[float] = None
    roi_pct: Optional[float] = None
    probability_of_loss_pct: Optional[float] = None
    verdict: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class CropScore:
    """Suitability and economic scoring for a specific crop."""
    key: str
    name: str
    local_name: str
    group: str
    score: float
    rating: str
    limiting_factor: str
    season: str
    reason: str
    economics_summary: Optional[CropEconomicsSummary] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.economics_summary:
            d["economics_summary"] = self.economics_summary.to_dict()
        return _clean_val(d)


@dataclass
class Improvement:
    """Actionable land and soil management intervention."""
    factor: str
    issue: str
    actions: List[str]
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class Advice:
    """Long-term trend adaptation advisory."""
    status: str  # "STABLE_BASELINE", "SIGNIFICANT_INCREASE", "SIGNIFICANT_DECREASE"
    evidence_confidence: str  # "high", "medium", "low"
    headline: str
    message: str
    crops: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    practices: List[str] = field(default_factory=list)
    disclaimer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class EconomicsReport:
    """Comprehensive agricultural enterprise economics report."""
    available: bool
    crop: str
    currency: str = "INR"
    area_ha: float = 1.0
    tenure: str = "owned"
    cost_basis: str = "a2_fl"
    price_basis: str = "market"
    yield_data: Dict[str, Any] = field(default_factory=dict)
    price_data: Dict[str, Any] = field(default_factory=dict)
    costs_data: Dict[str, Any] = field(default_factory=dict)
    returns_data: Dict[str, Any] = field(default_factory=dict)
    totals_for_area: Dict[str, Any] = field(default_factory=dict)
    risk_data: Dict[str, Any] = field(default_factory=dict)
    sensitivity_data: List[Dict[str, Any]] = field(default_factory=list)
    verdict: Dict[str, str] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    disclaimer: str = ""
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        if not self.available:
            return {
                "available": False,
                "crop": self.crop,
                "reason": self.reason or "Economic data not available for this crop and region.",
                "disclaimer": self.disclaimer
            }
        return _clean_val({
            "available": True,
            "crop": self.crop,
            "currency": self.currency,
            "area_ha": self.area_ha,
            "tenure": self.tenure,
            "cost_basis": self.cost_basis,
            "price_basis": self.price_basis,
            "yield": self.yield_data,
            "price": self.price_data,
            "costs": self.costs_data,
            "returns": self.returns_data,
            "totals_for_area": self.totals_for_area,
            "risk": self.risk_data,
            "sensitivity": self.sensitivity_data,
            "verdict": self.verdict,
            "data_quality": self.data_quality,
            "warnings": self.warnings,
            "disclaimer": self.disclaimer
        })


@dataclass
class IndustryFactors:
    """Production and industry driver factors (market, inputs, water, risk, policy, logistics)."""
    market: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    water: Dict[str, Any] = field(default_factory=dict)
    climate_risk: Dict[str, Any] = field(default_factory=dict)
    policy_support: Dict[str, Any] = field(default_factory=dict)
    logistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _clean_val(asdict(self))


@dataclass
class AssessmentReport:
    """Complete TeraTrend Land Assessment and Crop Decision Report."""
    location: GridPoint
    mode: Dict[str, Any]
    overall: Dict[str, Any]
    factors: Dict[str, FactorReport]
    suited_crops: List[CropScore]
    not_recommended: List[CropScore]
    rankings: Dict[str, Any]
    economics: EconomicsReport
    industry_factors: IndustryFactors
    improvements: List[Improvement]
    trend_advice: Advice
    coverage_notes: List[str]
    disclaimer: str
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location.to_dict(),
            "mode": _clean_val(self.mode),
            "overall": _clean_val(self.overall),
            "factors": {k: v.to_dict() for k, v in self.factors.items()},
            "suited_crops": [c.to_dict() for c in self.suited_crops],
            "not_recommended": [c.to_dict() for c in self.not_recommended],
            "rankings": _clean_val(self.rankings),
            "economics": self.economics.to_dict(),
            "industry_factors": self.industry_factors.to_dict(),
            "improvements": [imp.to_dict() for imp in self.improvements],
            "trend_advice": self.trend_advice.to_dict(),
            "coverage_notes": self.coverage_notes,
            "disclaimer": self.disclaimer,
            "meta": _clean_val(self.meta)
        }
