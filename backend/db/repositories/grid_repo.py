"""Precomputed spatial grid repository."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from db.models.grid import GridCell, GridCropScore
from db.models.reference import State


class GridRepository:
    """Access layer for precomputed territorial grid assessments."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_insert_cells_and_scores(
        self, cells_data: List[Dict[str, Any]], batch_size: int = 500
    ) -> int:
        """Batch insert precomputed grid cells and their crop suitability scores."""
        total = 0
        for i in range(0, len(cells_data), batch_size):
            chunk = cells_data[i : i + batch_size]
            for item in chunk:
                cell = GridCell(
                    cell_lat=item["cell_lat"],
                    cell_lon=item["cell_lon"],
                    state_id=item.get("state_id"),
                    district_id=item.get("district_id"),
                    overall_score=item["overall_score"],
                    temperature_score=item["temperature_score"],
                    moisture_score=item["moisture_score"],
                    soil_ph_score=item["soil_ph_score"],
                    soil_quality_score=item["soil_quality_score"],
                    climate_score=item["climate_score"],
                    data_version=item["data_version"],
                )
                self.session.add(cell)
                self.session.flush()

                for cs in item.get("crop_scores", []):
                    score = GridCropScore(
                        cell_id=cell.id,
                        crop_key=cs["crop_key"],
                        suitability_score=cs["suitability_score"],
                        roi_pct=cs.get("roi_pct"),
                        probability_of_loss_pct=cs.get("probability_of_loss_pct"),
                    )
                    self.session.add(score)

                total += 1
            self.session.flush()
        return total

    def best_cells_for_crop(
        self,
        crop_key: str,
        state_id: Optional[int] = None,
        data_version: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the highest suitability grid cells for a given crop."""
        stmt = (
            select(GridCell, GridCropScore)
            .join(GridCropScore, GridCell.id == GridCropScore.cell_id)
            .where(GridCropScore.crop_key == crop_key)
        )

        if state_id is not None:
            stmt = stmt.where(GridCell.state_id == state_id)
        if data_version is not None:
            stmt = stmt.where(GridCell.data_version == data_version)

        stmt = stmt.order_by(desc(GridCropScore.suitability_score)).limit(limit)
        results = self.session.execute(stmt).all()

        return [
            {
                "cell_lat": cell.cell_lat,
                "cell_lon": cell.cell_lon,
                "state_id": cell.state_id,
                "district_id": cell.district_id,
                "overall_score": cell.overall_score,
                "crop_key": score.crop_key,
                "suitability_score": score.suitability_score,
                "roi_pct": score.roi_pct,
                "probability_of_loss_pct": score.probability_of_loss_pct,
            }
            for cell, score in results
        ]

    def state_summary(
        self, crop_key: str, data_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return average and peak suitability scores per state for a crop."""
        stmt = (
            select(
                State.name.label("state_name"),
                State.code.label("state_code"),
                func.avg(GridCropScore.suitability_score).label("avg_suitability"),
                func.max(GridCropScore.suitability_score).label("max_suitability"),
                func.avg(GridCropScore.roi_pct).label("avg_roi"),
                func.count(GridCell.id).label("cell_count"),
            )
            .join(GridCell, State.id == GridCell.state_id)
            .join(GridCropScore, GridCell.id == GridCropScore.cell_id)
            .where(GridCropScore.crop_key == crop_key)
        )

        if data_version is not None:
            stmt = stmt.where(GridCell.data_version == data_version)

        stmt = stmt.group_by(State.name, State.code).order_by(
            desc("avg_suitability")
        )
        rows = self.session.execute(stmt).all()

        return [
            {
                "state": r.state_name,
                "state_code": r.state_code,
                "avg_suitability": round(float(r.avg_suitability or 0.0), 1),
                "max_suitability": round(float(r.max_suitability or 0.0), 1),
                "avg_roi": round(float(r.avg_roi or 0.0), 1) if r.avg_roi is not None else None,
                "cell_count": int(r.cell_count),
            }
            for r in rows
        ]

    def delete_old_versions(self, current_data_version: str) -> int:
        """Remove grid cells and cascade scores from older data versions."""
        stmt = delete(GridCell).where(GridCell.data_version != current_data_version)
        result = self.session.execute(stmt)
        return result.rowcount or 0
