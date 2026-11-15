"""TerraTrend Spatial Exploration Service.

Queries precomputed territorial grid suitability to find optimal growing areas and state summaries.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from db.base import get_session
from db.repositories.grid_repo import GridRepository
from db.repositories.reference_repo import ReferenceRepository

log = logging.getLogger("teratrend.services.explore")


class ExploreService:
    """Service querying territorial grid suitability and state summaries."""

    def get_best_places(
        self,
        crop_key: str,
        state_name: Optional[str] = None,
        limit: int = 20,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Fetch highest scoring grid cells across India or within a state for a crop."""
        def _exec(s: Session) -> Dict[str, Any]:
            grid_repo = GridRepository(s)
            state_id = None
            if state_name:
                ref_repo = ReferenceRepository(s)
                st = ref_repo.get_state_by_name(state_name)
                if st:
                    state_id = st.id

            cells = grid_repo.best_cells_for_crop(crop_key=crop_key, state_id=state_id, limit=limit)
            return {
                "crop": crop_key,
                "state": state_name,
                "count": len(cells),
                "cells": cells,
                "precomputed": len(cells) > 0,
            }

        if session is not None:
            return _exec(session)
        with get_session() as s:
            return _exec(s)

    def get_state_summary(
        self,
        crop_key: str,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Fetch average and peak suitability scores grouped by state for a crop."""
        def _exec(s: Session) -> Dict[str, Any]:
            grid_repo = GridRepository(s)
            summaries = grid_repo.state_summary(crop_key=crop_key)
            return {
                "crop": crop_key,
                "count": len(summaries),
                "states": summaries,
                "precomputed": len(summaries) > 0,
            }

        if session is not None:
            return _exec(session)
        with get_session() as s:
            return _exec(s)
