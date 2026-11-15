"""Provenance and operations data models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class DatasetProvenance(Base):
    """Satellite and reanalysis data layer provenance."""
    __tablename__ = "dataset_provenance"
    __table_args__ = (
        UniqueConstraint("dataset_key", "cube_sha256", name="uq_dataset_provenance_key_sha256"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_key: Mapped[str] = mapped_column(String(50), nullable=False)
    short_names: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    versions: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    concept_ids: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    cmr_extent_start: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cmr_extent_end: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    used_extent_start: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    used_extent_end: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    granule_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    access_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    backend: Mapped[str] = mapped_column(String(50), default="offline", nullable=False)
    variables: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    regrid_method: Mapped[str] = mapped_column(String(50), nullable=False)
    cube_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cube_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)


class BoundaryProvenance(Base):
    """Administrative boundary source and hash records."""
    __tablename__ = "boundary_provenance"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    license: Mapped[str] = mapped_column(String(100), nullable=False)
    retrieved_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)


class PipelineRun(Base):
    """Pipeline command run log and execution statistics."""
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running, success, failed
    stats: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
