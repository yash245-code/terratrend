"""Economics models: CACP costs, benchmark yields, MSP, mandi prices, inputs, and policy."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class CropCost(Base):
    """CACP Cost of Cultivation benchmarks (A2, A2+FL, C2) by crop, state and year."""
    __tablename__ = "crop_costs"
    __table_args__ = (
        UniqueConstraint("crop_id", "state_id", "reference_year", name="uq_crop_costs_crop_state_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("states.id", ondelete="SET NULL"), nullable=True
    )
    reference_year: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_a2: Mapped[float] = mapped_column(Float, nullable=False)
    cost_a2_fl: Mapped[float] = mapped_column(Float, nullable=False)
    cost_c2: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    yield_reference_q_ha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class BenchmarkYield(Base):
    """Directorate of Economics and Statistics (DES) district/state historical yields."""
    __tablename__ = "benchmark_yields"
    __table_args__ = (
        CheckConstraint("yield_q_ha > 0", name="ck_benchmark_yields_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("states.id", ondelete="SET NULL"), nullable=True
    )
    district_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), nullable=True
    )
    yield_q_ha: Mapped[float] = mapped_column(Float, nullable=False)
    period_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    period_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class Msp(Base):
    """Minimum Support Price (MSP) statutory floor prices."""
    __tablename__ = "msp"
    __table_args__ = (
        UniqueConstraint("crop_id", "marketing_year", name="uq_msp_crop_marketing_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    marketing_year: Mapped[str] = mapped_column(String(20), nullable=False)
    msp_per_q: Mapped[float] = mapped_column(Float, nullable=False)
    is_frp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class MandiPrice(Base):
    """Agmarknet modal prices and monthly seasonality indices."""
    __tablename__ = "mandi_prices"
    __table_args__ = (
        UniqueConstraint("crop_id", "state_id", "as_of", name="uq_mandi_prices_crop_state_as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[int] = mapped_column(
        ForeignKey("states.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[str] = mapped_column(String(20), nullable=False)  # ISO date string YYYY-MM-DD
    trailing_avg_modal_per_q: Mapped[float] = mapped_column(Float, nullable=False)
    yoy_change_pct: Mapped[float] = mapped_column(Float, nullable=False)
    price_cv: Mapped[float] = mapped_column(Float, nullable=False)
    seasonal_index: Mapped[List[float]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class InputRequirement(Base):
    """Agronomic input quantities (seed, NPK, irrigation, labour) per hectare."""
    __tablename__ = "input_requirements"
    __table_args__ = (
        UniqueConstraint("crop_id", name="uq_input_requirements_crop_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    seed_rate_kg_ha: Mapped[float] = mapped_column(Float, nullable=False)
    npk_kg_ha: Mapped[Dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    irrigation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    season_water_mm: Mapped[float] = mapped_column(Float, nullable=False)
    man_days_ha: Mapped[float] = mapped_column(Float, nullable=False)
    sprays: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class PolicyScheme(Base):
    """Institutional schemes (PMFBY, KCC, Soil Health Card, subsidies)."""
    __tablename__ = "policy_schemes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    as_of: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verify_before_use: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)
