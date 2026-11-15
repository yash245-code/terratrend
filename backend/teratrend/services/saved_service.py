"""TerraTrend Saved Locations and Scenarios Service.

Manages anonymous client state, saved farm plots, economic scenarios, and rerun comparisons.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from config import Config
from db.base import get_session
from db.repositories.clients_repo import ClientsRepository, LimitExceededError
from teratrend.services.assessment_service import AssessmentService

log = logging.getLogger("teratrend.services.saved")


class SavedService:
    """Service handling client sessions, saved plots, and rerun diffs."""

    def __init__(self, assessment_service: Optional[AssessmentService] = None) -> None:
        self.assessment_service = assessment_service or AssessmentService()

    def get_or_create_client(self, client_id: Optional[str] = None, session: Optional[Session] = None) -> str:
        """Ensure anonymous client session exists and update activity timestamp."""
        if session is not None:
            return ClientsRepository(session).create_or_touch_client(client_id)
        with get_session() as s:
            cid = ClientsRepository(s).create_or_touch_client(client_id)
            s.commit()
            return cid

    def list_locations(self, client_id: str, session: Optional[Session] = None) -> List[Dict[str, Any]]:
        """List all saved locations for a client."""
        if session is not None:
            return ClientsRepository(session).list_saved_locations(client_id)
        with get_session() as s:
            return ClientsRepository(s).list_saved_locations(client_id)

    def save_location(
        self,
        client_id: str,
        label: str,
        lat: float,
        lon: float,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Save a new location plot."""
        max_limit = Config.SAVED_LOCATION_LIMIT
        if session is not None:
            return ClientsRepository(session).save_location(client_id, label, lat, lon, max_limit=max_limit)
        with get_session() as s:
            loc = ClientsRepository(s).save_location(client_id, label, lat, lon, max_limit=max_limit)
            s.commit()
            return loc

    def delete_location(self, client_id: str, location_id: int, session: Optional[Session] = None) -> bool:
        """Delete a saved location owned by client."""
        if session is not None:
            return ClientsRepository(session).delete_location(client_id, location_id)
        with get_session() as s:
            deleted = ClientsRepository(s).delete_location(client_id, location_id)
            s.commit()
            return deleted

    def list_scenarios(self, client_id: str, session: Optional[Session] = None) -> List[Dict[str, Any]]:
        """List saved scenarios for a client."""
        if session is not None:
            return ClientsRepository(session).list_saved_scenarios(client_id)
        with get_session() as s:
            return ClientsRepository(s).list_saved_scenarios(client_id)

    def save_scenario(
        self,
        client_id: str,
        label: str,
        crop_key: str,
        options: Dict[str, Any],
        snapshot_json: Dict[str, Any],
        data_version: str,
        location_id: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Save a scenario snapshot."""
        max_limit = Config.SAVED_SCENARIO_LIMIT
        if session is not None:
            return ClientsRepository(session).save_scenario(
                client_id=client_id,
                location_id=location_id,
                label=label,
                crop_key=crop_key,
                options=options,
                snapshot_json=snapshot_json,
                data_version=data_version,
                max_limit=max_limit,
            )
        with get_session() as s:
            sc = ClientsRepository(s).save_scenario(
                client_id=client_id,
                location_id=location_id,
                label=label,
                crop_key=crop_key,
                options=options,
                snapshot_json=snapshot_json,
                data_version=data_version,
                max_limit=max_limit,
            )
            s.commit()
            return sc

    def get_scenario(
        self, client_id: str, scenario_id: int, session: Optional[Session] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch a saved scenario."""
        if session is not None:
            return ClientsRepository(session).get_saved_scenario(client_id, scenario_id)
        with get_session() as s:
            return ClientsRepository(s).get_saved_scenario(client_id, scenario_id)

    def delete_scenario(self, client_id: str, scenario_id: int, session: Optional[Session] = None) -> bool:
        """Delete a saved scenario."""
        if session is not None:
            return ClientsRepository(session).delete_scenario(client_id, scenario_id)
        with get_session() as s:
            deleted = ClientsRepository(s).delete_scenario(client_id, scenario_id)
            s.commit()
            return deleted

    def rerun_scenario(
        self,
        client_id: str,
        scenario_id: int,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Rerun a scenario against current data cubes and compute diff against snapshot."""
        scenario = self.get_scenario(client_id, scenario_id, session=session)
        if not scenario:
            return None

        snapshot = scenario.get("snapshot_json", {})
        opts = scenario.get("options", {})
        crop_key = scenario.get("crop_key")

        # Resolve lat/lon from snapshot location or options
        loc_meta = snapshot.get("location", {})
        lat = opts.get("lat") or loc_meta.get("requested_lat") or loc_meta.get("snapped_lat")
        lon = opts.get("lon") or loc_meta.get("requested_lon") or loc_meta.get("snapped_lon")

        if lat is None or lon is None:
            raise ValueError("Scenario does not contain coordinate data to rerun.")

        fresh = self.assessment_service.assess_location(
            lat=float(lat),
            lon=float(lon),
            crop_param=crop_key,
            season_param=opts.get("season", "annual"),
            irrigation_param=opts.get("irrigation", "rainfed"),
            options=opts,
            session=session,
        )

        # Compute Changes Block
        snap_overall = snapshot.get("overall", {})
        fresh_overall = fresh.get("overall", {})
        snap_econ = snapshot.get("selected_crop_economics", {})
        fresh_econ = fresh.get("selected_crop_economics", {})

        snap_score = snap_overall.get("score")
        fresh_score = fresh_overall.get("score")
        score_diff = round(fresh_score - snap_score, 1) if snap_score is not None and fresh_score is not None else None

        snap_roi = snap_econ.get("returns_data", {}).get("roi_pct", {}).get("chosen")
        fresh_roi = fresh_econ.get("returns_data", {}).get("roi_pct", {}).get("chosen")
        roi_diff = round(fresh_roi - snap_roi, 1) if snap_roi is not None and fresh_roi is not None else None

        snap_net = snap_econ.get("returns_data", {}).get("net_return_per_ha", {}).get("chosen")
        fresh_net = fresh_econ.get("returns_data", {}).get("net_return_per_ha", {}).get("chosen")
        net_diff = round(fresh_net - snap_net, 1) if snap_net is not None and fresh_net is not None else None

        changes = {
            "score_diff": score_diff,
            "roi_diff_pct": roi_diff,
            "net_return_diff_per_ha": net_diff,
            "data_version_changed": scenario.get("data_version") != fresh.get("meta", {}).get("data_version"),
            "snapshot_created_at": scenario.get("created_at"),
        }

        return {
            "scenario_id": scenario_id,
            "label": scenario.get("label"),
            "changes": changes,
            "fresh_assessment": fresh,
            "snapshot_summary": {
                "score": snap_score,
                "verdict": snap_overall.get("verdict"),
                "roi_pct": snap_roi,
                "net_return_per_ha": snap_net,
            },
        }

    def delete_client_data(self, client_id: str, session: Optional[Session] = None) -> bool:
        """Wipe all saved locations, scenarios, and client record."""
        if session is not None:
            return ClientsRepository(session).delete_client_data(client_id)
        with get_session() as s:
            deleted = ClientsRepository(s).delete_client_data(client_id)
            s.commit()
            return deleted
