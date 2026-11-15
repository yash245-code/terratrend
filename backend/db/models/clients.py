"""Saved items and anonymous client models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


class Client(Base):
    """Anonymous client session identity (no PII, no IP, no password)."""
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    saved_locations: Mapped[List[SavedLocation]] = relationship(
        "SavedLocation", back_populates="client", cascade="all, delete-orphan"
    )
    saved_scenarios: Mapped[List[SavedScenario]] = relationship(
        "SavedScenario", back_populates="client", cascade="all, delete-orphan"
    )


class SavedLocation(Base):
    """Saved farm or plot coordinate."""
    __tablename__ = "saved_locations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    client: Mapped[Client] = relationship("Client", back_populates="saved_locations")
    scenarios: Mapped[List[SavedScenario]] = relationship(
        "SavedScenario", back_populates="location", cascade="all, delete-orphan"
    )


class SavedScenario(Base):
    """Saved economic sensitivity scenario and historical result snapshot."""
    __tablename__ = "saved_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("saved_locations.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    crop_key: Mapped[str] = mapped_column(String(50), nullable=False)
    options: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    client: Mapped[Client] = relationship("Client", back_populates="saved_scenarios")
    location: Mapped[Optional[SavedLocation]] = relationship("SavedLocation", back_populates="scenarios")
