"""Provenance and pipeline operations repository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.base import upsert
from db.models.provenance import (
    BoundaryProvenance,
    DatasetProvenance,
    PipelineRun,
)


class ProvenanceRepository:
    """Access layer for dataset provenance, checksums, and pipeline run logs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_dataset(
        self,
        dataset_key: str,
        short_names: List[str],
        versions: List[str],
        provider: str,
        citation: str,
        cube_sha256: str,
        regrid_method: str = "bilinear",
        variables: Optional[List[str]] = None,
        doi: Optional[str] = None,
        concept_ids: Optional[List[str]] = None,
        cmr_extent_start: Optional[str] = None,
        cmr_extent_end: Optional[str] = None,
        used_extent_start: Optional[str] = None,
        used_extent_end: Optional[str] = None,
        granule_count: int = 0,
        access_date: Optional[str] = None,
        backend: str = "offline",
        cube_path: Optional[str] = None,
    ) -> DatasetProvenance:
        """Upsert a dataset provenance record."""
        values = {
            "dataset_key": dataset_key,
            "short_names": list(short_names or []),
            "versions": list(versions or []),
            "doi": doi,
            "concept_ids": list(concept_ids or []),
            "provider": provider,
            "citation": citation,
            "cmr_extent_start": cmr_extent_start,
            "cmr_extent_end": cmr_extent_end,
            "used_extent_start": used_extent_start,
            "used_extent_end": used_extent_end,
            "granule_count": granule_count,
            "access_date": access_date,
            "backend": backend,
            "variables": list(variables or []),
            "regrid_method": regrid_method,
            "cube_path": cube_path,
            "cube_sha256": cube_sha256,
        }

        upsert(
            self.session,
            DatasetProvenance,
            values,
            conflict_cols=["dataset_key", "cube_sha256"],
            update_cols=[
                "short_names",
                "versions",
                "doi",
                "concept_ids",
                "provider",
                "citation",
                "cmr_extent_start",
                "cmr_extent_end",
                "used_extent_start",
                "used_extent_end",
                "granule_count",
                "access_date",
                "backend",
                "variables",
                "regrid_method",
                "cube_path",
            ],
        )

        return self.session.scalars(
            select(DatasetProvenance)
            .where(
                DatasetProvenance.dataset_key == dataset_key,
                DatasetProvenance.cube_sha256 == cube_sha256,
            )
        ).one()

    def record_boundary(
        self,
        name: str,
        source: str,
        license: str,
        sha256: str,
        source_url: Optional[str] = None,
        retrieved_at: Optional[str] = None,
    ) -> BoundaryProvenance:
        """Upsert a boundary polygon provenance entry."""
        values = {
            "name": name,
            "source": source,
            "license": license,
            "sha256": sha256,
            "source_url": source_url,
            "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        }

        upsert(
            self.session,
            BoundaryProvenance,
            values,
            conflict_cols=["name"],
            update_cols=["source", "license", "sha256", "source_url", "retrieved_at"],
        )

        return self.session.scalars(
            select(BoundaryProvenance).where(BoundaryProvenance.name == name)
        ).one()

    def latest_per_dataset(self) -> Dict[str, Dict[str, Any]]:
        """Return the latest provenance record for each dataset key."""
        stmt = select(DatasetProvenance).order_by(
            DatasetProvenance.dataset_key, DatasetProvenance.created_at.desc()
        )
        all_records = self.session.scalars(stmt).all()

        latest: Dict[str, Dict[str, Any]] = {}
        for r in all_records:
            if r.dataset_key not in latest:
                latest[r.dataset_key] = {
                    "dataset_key": r.dataset_key,
                    "short_names": list(r.short_names or []),
                    "versions": list(r.versions or []),
                    "doi": r.doi,
                    "concept_ids": list(r.concept_ids or []),
                    "provider": r.provider,
                    "citation": r.citation,
                    "cmr_extent_start": r.cmr_extent_start,
                    "cmr_extent_end": r.cmr_extent_end,
                    "used_extent_start": r.used_extent_start,
                    "used_extent_end": r.used_extent_end,
                    "granule_count": r.granule_count,
                    "access_date": r.access_date,
                    "backend": r.backend,
                    "variables": list(r.variables or []),
                    "regrid_method": r.regrid_method,
                    "cube_path": r.cube_path,
                    "cube_sha256": r.cube_sha256,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
        return latest

    def export_json(self) -> Dict[str, Any]:
        """Export provenance dataset records matching the format of provenance.json."""
        datasets = self.latest_per_dataset()
        boundaries = {
            b.name: {
                "source": b.source,
                "source_url": b.source_url,
                "license": b.license,
                "retrieved_at": b.retrieved_at,
                "sha256": b.sha256,
            }
            for b in self.session.scalars(select(BoundaryProvenance)).all()
        }

        return {
            "datasets": datasets,
            "boundaries": boundaries,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def start_run(
        self,
        command: str,
        dataset_key: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log the start of a pipeline or batch execution."""
        run = PipelineRun(
            command=command,
            dataset_key=dataset_key,
            started_at=datetime.now(timezone.utc),
            status="running",
            stats=stats or {},
        )
        self.session.add(run)
        self.session.flush()
        return run.id

    def finish_run(
        self,
        run_id: int,
        status: str = "success",
        stats: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a pipeline run as finished."""
        run = self.session.get(PipelineRun, run_id)
        if run:
            run.finished_at = datetime.now(timezone.utc)
            run.status = status
            if stats:
                curr = dict(run.stats or {})
                curr.update(stats)
                run.stats = curr
            if error_message:
                run.error_message = error_message
