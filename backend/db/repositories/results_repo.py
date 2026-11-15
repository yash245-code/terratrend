"""Assessment and geocode results caching repository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db.base import upsert
from db.models.results import AssessmentCache, GeocodeCache


class ResultsRepository:
    """Access layer for query caches and pre-calculated assessment results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Fetch cached assessment result and increment hit count atomically."""
        stmt = select(AssessmentCache).where(AssessmentCache.cache_key == cache_key)
        entry = self.session.scalars(stmt).first()
        if not entry:
            return None

        entry.last_hit_at = datetime.now(timezone.utc)
        entry.hit_count += 1
        return dict(entry.result_json)

    def put_cached(
        self,
        cache_key: str,
        cell_lat: float,
        cell_lon: float,
        state_id: Optional[int],
        district_id: Optional[int],
        crop_key: Optional[str],
        season: str,
        irrigation: str,
        options_hash: str,
        data_version: str,
        result_json: Dict[str, Any],
    ) -> None:
        """Store assessment result into cache."""
        values = {
            "cache_key": cache_key,
            "cell_lat": cell_lat,
            "cell_lon": cell_lon,
            "state_id": state_id,
            "district_id": district_id,
            "crop_key": crop_key,
            "season": season,
            "irrigation": irrigation,
            "options_hash": options_hash,
            "data_version": data_version,
            "result_json": result_json,
            "created_at": datetime.now(timezone.utc),
            "last_hit_at": datetime.now(timezone.utc),
            "hit_count": 1,
        }

        upsert(
            self.session,
            AssessmentCache,
            values,
            conflict_cols=["cache_key"],
            update_cols=["last_hit_at", "result_json", "hit_count"],
        )

    def prune(self, max_rows: int = 100000) -> int:
        """Prune least recently hit cache entries when total exceeds max_rows."""
        total = self.session.scalar(select(func.count(AssessmentCache.id))) or 0
        if total <= max_rows:
            return 0

        excess = total - max_rows
        # Identify oldest IDs by last_hit_at
        oldest_ids = self.session.scalars(
            select(AssessmentCache.id)
            .order_by(AssessmentCache.last_hit_at.asc())
            .limit(excess)
        ).all()

        if oldest_ids:
            self.session.execute(
                delete(AssessmentCache).where(AssessmentCache.id.in_(oldest_ids))
            )
            return len(oldest_ids)
        return 0

    def clear(self) -> int:
        """Wipe entire assessments cache."""
        result = self.session.execute(delete(AssessmentCache))
        return result.rowcount or 0

    def get_geocode(self, query_norm: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch cached geocoding response."""
        stmt = select(GeocodeCache).where(GeocodeCache.query_norm == query_norm)
        entry = self.session.scalars(stmt).first()
        if entry:
            return list(entry.results)
        return None

    def put_geocode(self, query_norm: str, results: List[Dict[str, Any]]) -> None:
        """Store geocoding results."""
        values = {
            "query_norm": query_norm,
            "results": list(results),
            "created_at": datetime.now(timezone.utc),
        }
        upsert(
            self.session,
            GeocodeCache,
            values,
            conflict_cols=["query_norm"],
            update_cols=["results", "created_at"],
        )
