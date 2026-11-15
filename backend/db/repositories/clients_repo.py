"""Anonymous client and saved farm scenario repository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db.models.clients import Client, SavedLocation, SavedScenario


class LimitExceededError(Exception):
    """Raised when a client exceeds max saved items."""
    pass


class ClientsRepository:
    """Access layer for anonymous client identity and saved plots/scenarios."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_touch_client(self, client_id: Optional[str] = None) -> str:
        """Create a new client or update last_seen_at for existing client."""
        now = datetime.now(timezone.utc)
        if client_id:
            client = self.session.get(Client, client_id)
            if client:
                client.last_seen_at = now
                return client.id
            new_id = client_id
        else:
            new_id = str(uuid.uuid4())

        client = Client(id=new_id, created_at=now, last_seen_at=now)
        self.session.add(client)
        self.session.flush()
        return client.id

    def list_saved_locations(self, client_id: str) -> List[Dict[str, Any]]:
        """List all saved locations for a client."""
        stmt = (
            select(SavedLocation)
            .where(SavedLocation.client_id == client_id)
            .order_by(SavedLocation.created_at.desc())
        )
        locations = self.session.scalars(stmt).all()
        return [
            {
                "id": loc.id,
                "label": loc.label,
                "lat": loc.lat,
                "lon": loc.lon,
                "created_at": loc.created_at.isoformat() if loc.created_at else None,
            }
            for loc in locations
        ]

    def save_location(
        self, client_id: str, label: str, lat: float, lon: float, max_limit: int = 50
    ) -> Dict[str, Any]:
        """Save a new plot location, enforcing per-client quota."""
        count = self.session.scalar(
            select(func.count(SavedLocation.id)).where(SavedLocation.client_id == client_id)
        ) or 0

        if count >= max_limit:
            raise LimitExceededError(
                f"Location limit of {max_limit} reached for this client session."
            )

        loc = SavedLocation(
            client_id=client_id,
            label=label.strip(),
            lat=lat,
            lon=lon,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(loc)
        self.session.flush()
        return {
            "id": loc.id,
            "label": loc.label,
            "lat": loc.lat,
            "lon": loc.lon,
            "created_at": loc.created_at.isoformat(),
        }

    def delete_location(self, client_id: str, location_id: int) -> bool:
        """Delete a saved location strictly owned by client_id."""
        stmt = delete(SavedLocation).where(
            SavedLocation.id == location_id,
            SavedLocation.client_id == client_id,
        )
        result = self.session.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)

    def list_saved_scenarios(self, client_id: str) -> List[Dict[str, Any]]:
        """List all saved economic scenarios for a client."""
        stmt = (
            select(SavedScenario)
            .where(SavedScenario.client_id == client_id)
            .order_by(SavedScenario.created_at.desc())
        )
        scenarios = self.session.scalars(stmt).all()
        return [
            {
                "id": s.id,
                "location_id": s.location_id,
                "label": s.label,
                "crop_key": s.crop_key,
                "options": dict(s.options or {}),
                "snapshot_json": dict(s.snapshot_json or {}),
                "data_version": s.data_version,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in scenarios
        ]

    def save_scenario(
        self,
        client_id: str,
        location_id: Optional[int],
        label: str,
        crop_key: str,
        options: Dict[str, Any],
        snapshot_json: Dict[str, Any],
        data_version: str,
        max_limit: int = 100,
    ) -> Dict[str, Any]:
        """Save a new scenario snapshot, enforcing per-client quota."""
        count = self.session.scalar(
            select(func.count(SavedScenario.id)).where(SavedScenario.client_id == client_id)
        ) or 0

        if count >= max_limit:
            raise LimitExceededError(
                f"Scenario limit of {max_limit} reached for this client session."
            )

        if location_id is not None:
            # Verify location belongs to client
            loc = self.session.scalars(
                select(SavedLocation).where(
                    SavedLocation.id == location_id,
                    SavedLocation.client_id == client_id,
                )
            ).first()
            if not loc:
                location_id = None

        scen = SavedScenario(
            client_id=client_id,
            location_id=location_id,
            label=label.strip(),
            crop_key=crop_key,
            options=options,
            snapshot_json=snapshot_json,
            data_version=data_version,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(scen)
        self.session.flush()
        return {
            "id": scen.id,
            "location_id": scen.location_id,
            "label": scen.label,
            "crop_key": scen.crop_key,
            "options": scen.options,
            "snapshot_json": scen.snapshot_json,
            "data_version": scen.data_version,
            "created_at": scen.created_at.isoformat(),
        }

    def get_saved_scenario(self, client_id: str, scenario_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific saved scenario, enforcing client ownership."""
        stmt = select(SavedScenario).where(
            SavedScenario.id == scenario_id,
            SavedScenario.client_id == client_id,
        )
        s = self.session.scalars(stmt).first()
        if not s:
            return None
        return {
            "id": s.id,
            "location_id": s.location_id,
            "label": s.label,
            "crop_key": s.crop_key,
            "options": dict(s.options or {}),
            "snapshot_json": dict(s.snapshot_json or {}),
            "data_version": s.data_version,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    def delete_scenario(self, client_id: str, scenario_id: int) -> bool:
        """Delete a saved scenario strictly owned by client_id."""
        stmt = delete(SavedScenario).where(
            SavedScenario.id == scenario_id,
            SavedScenario.client_id == client_id,
        )
        result = self.session.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)

    def delete_client_data(self, client_id: str) -> bool:
        """Purge all data associated with an anonymous client identity."""
        self.session.execute(delete(SavedScenario).where(SavedScenario.client_id == client_id))
        self.session.execute(delete(SavedLocation).where(SavedLocation.client_id == client_id))
        res = self.session.execute(delete(Client).where(Client.id == client_id))
        return bool(res.rowcount and res.rowcount > 0)
