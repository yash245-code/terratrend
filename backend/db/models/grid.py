"""Precomputed spatial grid models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class GridCell(Base):
    """Precomputed 0.25-degree India territorial grid cell assessment."""
    __tablename__ = "grid_cells"
    __table_args__ = (
        UniqueConstraint("cell_lat", "cell_lon", "data_version", name="uq_grid_cells_coords_version"),
        Index("ix_grid_cells_version", "data_version"),
        Index("ix_grid_cells_state", "state_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cell_lat: Mapped[float] = mapped_column(Float, nullable=False)
    cell_lon: Mapped[float] = mapped_column(Float, nullable=False)
    state_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("states.id", ondelete="SET NULL"), nullable=True
    )
    district_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_score: Mapped[float] = mapped_column(Float, nullable=False)
    moisture_score: Mapped[float] = mapped_column(Float, nullable=False)
    soil_ph_score: Mapped[float] = mapped_column(Float, nullable=False)
    soil_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    climate_score: Mapped[float] = mapped_column(Float, nullable=False)
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    crop_scores: Mapped[list[GridCropScore]] = relationship(
        "GridCropScore", back_populates="cell", cascade="all, delete-orphan"
    )


class GridCropScore(Base):
    """Precomputed crop suitability and baseline economics for a grid cell."""
    __tablename__ = "grid_crop_scores"
    __table_args__ = (
        UniqueConstraint("cell_id", "crop_key", name="uq_grid_crop_scores_cell_crop"),
        Index("ix_grid_crop_scores_crop_score", "crop_key", "suitability_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cell_id: Mapped[int] = mapped_column(
        ForeignKey("grid_cells.id", ondelete="CASCADE"), nullable=False
    )
    crop_key: Mapped[str] = mapped_column(String(50), nullable=False)
    suitability_score: Mapped[float] = mapped_column(Float, nullable=False)
    roi_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    probability_of_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    cell: Mapped[GridCell] = relationship("GridCell", back_populates="crop_scores")
