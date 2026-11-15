"""Reference data models: administrative regions, crops, rules, and amendments."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class State(Base):
    """Indian States and Union Territories master record."""
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_union_territory: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    districts: Mapped[List[District]] = relationship(
        "District", back_populates="state", cascade="all, delete-orphan"
    )


class District(Base):
    """District boundary reference within a state."""
    __tablename__ = "districts"
    __table_args__ = (
        UniqueConstraint("state_id", "name", name="uq_districts_state_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_id: Mapped[int] = mapped_column(
        ForeignKey("states.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lgd_code: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    state: Mapped[State] = relationship("State", back_populates="districts")


class Crop(Base):
    """Agronomic crop master specification."""
    __tablename__ = "crops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    local_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    group: Mapped[str] = mapped_column(String(50), nullable=False)
    seasons: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    cycle_days: Mapped[int] = mapped_column(nullable=False)
    water_demand: Mapped[str] = mapped_column(String(20), nullable=False)
    base_yield_cv: Mapped[float] = mapped_column(nullable=False)
    salinity_ece_max: Mapped[float] = mapped_column(nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    requirements: Mapped[List[CropRequirement]] = relationship(
        "CropRequirement", back_populates="crop", cascade="all, delete-orphan"
    )
    soil_preferences: Mapped[List[CropSoilPreference]] = relationship(
        "CropSoilPreference", back_populates="crop", cascade="all, delete-orphan"
    )


class CropRequirement(Base):
    """Agronomic continuous 4-knot trapezoid bounds for temperature, rainfall, and pH."""
    __tablename__ = "crop_requirements"
    __table_args__ = (
        CheckConstraint(
            "abs_min <= opt_min AND opt_min <= opt_max AND opt_max <= abs_max",
            name="ck_crop_requirements_trapezoid_order",
        ),
        UniqueConstraint("crop_id", "factor", "season", name="uq_crop_requirements_crop_factor_season"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    factor: Mapped[str] = mapped_column(String(50), nullable=False)  # temperature, rainfall, ph
    season: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    abs_min: Mapped[float] = mapped_column(nullable=False)
    opt_min: Mapped[float] = mapped_column(nullable=False)
    opt_max: Mapped[float] = mapped_column(nullable=False)
    abs_max: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    crop: Mapped[Crop] = relationship("Crop", back_populates="requirements")


class CropSoilPreference(Base):
    """Categorical soil texture and drainage tolerance per crop."""
    __tablename__ = "crop_soil_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    crop_id: Mapped[int] = mapped_column(
        ForeignKey("crops.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # texture, drainage
    class_name: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # preferred, tolerated
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    crop: Mapped[Crop] = relationship("Crop", back_populates="soil_preferences")


class AmendmentRule(Base):
    """Rule-driven soil amendment conditions and interventions."""
    __tablename__ = "amendment_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    factor: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False)  # lt, lte, gt, gte, between
    threshold_low: Mapped[float] = mapped_column(nullable=False)
    threshold_high: Mapped[Optional[float]] = mapped_column(nullable=True)
    issue: Mapped[str] = mapped_column(String(255), nullable=False)
    actions: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class TrendRule(Base):
    """Rules mapping statistically verified climate shifts to rotational recommendations."""
    __tablename__ = "trend_rules"
    __table_args__ = (
        UniqueConstraint("indicator", "direction", name="uq_trend_rules_indicator_direction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    indicator: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # increasing, decreasing
    crops: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    avoid: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    practices: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)
