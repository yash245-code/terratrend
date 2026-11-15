"""Results and cache data models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class AssessmentCache(Base):
    """Cached assessment core outputs for fast sub-30ms repeat retrieval."""
    __tablename__ = "assessments_cache"
    __table_args__ = (
        Index("ix_assessments_cache_data_version", "data_version"),
        Index("ix_assessments_cache_last_hit_at", "last_hit_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    cell_lat: Mapped[float] = mapped_column(Float, nullable=False)
    cell_lon: Mapped[float] = mapped_column(Float, nullable=False)
    state_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    district_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crop_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    season: Mapped[str] = mapped_column(String(20), nullable=False)
    irrigation: Mapped[str] = mapped_column(String(20), nullable=False)
    options_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_hit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class GeocodeCache(Base):
    """Cached geocoding query results."""
    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    query_norm: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    results: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
