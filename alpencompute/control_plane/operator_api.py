"""Operator registration and inventory APIs for the control plane."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from ..mesh.site_operator import SiteHeartbeat

@dataclass(slots=True)
class OperatorAccount:
    """Represents an operator providing hardware into the mesh."""

    operator_id: str
    name: str
    contact_email: str
    jurisdiction: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    sites: Dict[str, "SiteRegistration"] = field(default_factory=dict)


@dataclass(slots=True)
class SiteRegistration:
    """Represents a registered site operated by an operator."""

    site_id: str
    operator_id: str
    name: str
    region: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    allowed_cidrs: List[str] = field(default_factory=list)
    tokens: Dict[str, datetime] = field(default_factory=dict)
    last_heartbeat: Optional["SiteHeartbeat"] = None

    def issue_token(self, *, ttl_seconds: int = 3600) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens[token] = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        return token

    def validate_token(self, token: str) -> bool:
        expiry = self.tokens.get(token)
        if not expiry:
            return False
        if expiry < datetime.utcnow():
            self.tokens.pop(token, None)
            return False
        return True


@dataclass(slots=True)
class InventorySnapshot:
    """Represents the latest inventory payload for a site."""

    site_id: str
    received_at: datetime
    nodes: List[Dict[str, Any]]
    raw_payload: Dict[str, Any]


class OperatorRegistry:
    """In-memory registry managing operator accounts and site registrations."""

    def __init__(self) -> None:
        self._operators: Dict[str, OperatorAccount] = {}
        self._sites: Dict[str, SiteRegistration] = {}

    # ------------------------------------------------------------------
    # Operator lifecycle
    # ------------------------------------------------------------------
    def register_operator(
        self,
        *,
        name: str,
        contact_email: str,
        jurisdiction: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OperatorAccount:
        operator_id = f"op-{len(self._operators) + 1}"
        account = OperatorAccount(
            operator_id=operator_id,
            name=name,
            contact_email=contact_email,
            jurisdiction=jurisdiction,
            metadata=metadata or {},
        )
        self._operators[operator_id] = account
        return account

    def get_operator(self, operator_id: str) -> Optional[OperatorAccount]:
        return self._operators.get(operator_id)

    # ------------------------------------------------------------------
    # Site lifecycle
    # ------------------------------------------------------------------
    def register_site(
        self,
        *,
        operator_id: str,
        name: str,
        region: str,
        allowed_cidrs: Optional[List[str]] = None,
    ) -> SiteRegistration:
        if operator_id not in self._operators:
            raise KeyError(f"Unknown operator {operator_id}")
        site_id = f"site-{len(self._sites) + 1}"
        site = SiteRegistration(
            site_id=site_id,
            operator_id=operator_id,
            name=name,
            region=region,
            allowed_cidrs=allowed_cidrs or [],
        )
        self._sites[site_id] = site
        self._operators[operator_id].sites[site_id] = site
        return site

    def get_site(self, site_id: str) -> Optional[SiteRegistration]:
        return self._sites.get(site_id)

    def authenticate_site(self, token: str) -> Optional[SiteRegistration]:
        for site in self._sites.values():
            if site.validate_token(token):
                return site
        return None


class InventoryIngestionService:
    """Handles inventory, heartbeat, and task status ingestion from sites."""

    def __init__(self, registry: OperatorRegistry) -> None:
        self._registry = registry
        self._inventories: Dict[str, InventorySnapshot] = {}
        self._task_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------
    def _get_site_or_raise(self, site_id: str) -> SiteRegistration:
        site = self._registry.get_site(site_id)
        if not site:
            raise KeyError(f"Unknown site {site_id}")
        return site

    # ------------------------------------------------------------------
    # Inventory ingestion
    # ------------------------------------------------------------------
    def ingest_inventory(self, *, site_id: str, payload: Dict[str, Any]) -> InventorySnapshot:
        site = self._get_site_or_raise(site_id)
        nodes = payload.get("nodes", [])
        snapshot = InventorySnapshot(
            site_id=site_id,
            received_at=datetime.utcnow(),
            nodes=nodes,
            raw_payload=payload,
        )
        self._inventories[site_id] = snapshot
        return snapshot

    def record_heartbeat(self, *, site_id: str, heartbeat: SiteHeartbeat) -> None:
        site = self._get_site_or_raise(site_id)
        site.last_heartbeat = heartbeat

    def record_task_status(self, *, site_id: str, payload: Dict[str, Any]) -> None:
        payload = dict(payload)
        payload["site_id"] = site_id
        payload["received_at"] = datetime.utcnow().isoformat()
        self._task_log.append(payload)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def latest_inventory(self, site_id: str) -> Optional[InventorySnapshot]:
        return self._inventories.get(site_id)

    def task_events(self) -> List[Dict[str, Any]]:
        return list(self._task_log)

