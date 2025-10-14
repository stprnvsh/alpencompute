"""Mesh site operator agent.

This module provides the long running service that sits inside a partner data
centre.  It watches the customer hardware controller, maintains the warm pool
and synchronises state with the global control plane.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

from ..control_plane.operator_api import InventoryIngestionService
from ..hardware.customer_control import (
    CustomerHardwareController,
    HardwareNode,
    ProvisioningTask,
)
from .provisioner import ProvisioningManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SiteHeartbeat:
    """Heartbeats sent to the global control plane."""

    site_id: str
    sent_at: datetime
    inventory_digest: str
    warm_pool_available: int
    tasks_in_flight: int
    extra: Dict[str, Any] = field(default_factory=dict)


class MeshControlPlaneClient:
    """Interface the site agent expects from the control plane."""

    def __init__(self, *, send: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None):
        self._send = send

    async def send_heartbeat(self, payload: Dict[str, Any]) -> None:
        if not self._send:
            raise NotImplementedError("send_heartbeat not implemented")
        await self._send("heartbeat", payload)

    async def publish_inventory(self, payload: Dict[str, Any]) -> None:
        if not self._send:
            raise NotImplementedError("publish_inventory not implemented")
        await self._send("inventory", payload)

    async def publish_task_status(self, payload: Dict[str, Any]) -> None:
        if not self._send:
            raise NotImplementedError("publish_task_status not implemented")
        await self._send("task_status", payload)


class InProcessControlPlaneClient(MeshControlPlaneClient):
    """Control plane client backed by in-memory registry services."""

    def __init__(
        self,
        *,
        site_id: str,
        inventory_service: InventoryIngestionService,
    ) -> None:
        super().__init__(send=None)
        self._site_id = site_id
        self._inventory_service = inventory_service

    async def send_heartbeat(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        heartbeat = SiteHeartbeat(**payload)
        self._inventory_service.record_heartbeat(site_id=self._site_id, heartbeat=heartbeat)

    async def publish_inventory(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        self._inventory_service.ingest_inventory(site_id=self._site_id, payload=payload)

    async def publish_task_status(self, payload: Dict[str, Any]) -> None:  # type: ignore[override]
        self._inventory_service.record_task_status(site_id=self._site_id, payload=payload)


class MeshSiteOperatorAgent:
    """Coordinates the site components.

    Responsibilities:
    - Reserve and release nodes on behalf of the global control plane.
    - Maintain a warm pool of ready to allocate machines.
    - Report health and inventory updates.
    - Drive provisioning workflows via :class:`ProvisioningManager`.
    """

    def __init__(
        self,
        *,
        site_id: str,
        controller: CustomerHardwareController,
        provisioner: ProvisioningManager,
        control_plane: MeshControlPlaneClient,
        warm_pool_target: int = 3,
        heartbeat_interval: int = 30,
    ) -> None:
        self.site_id = site_id
        self._controller = controller
        self._provisioner = provisioner
        self._control_plane = control_plane
        self._warm_pool_target = warm_pool_target
        self._heartbeat_interval = heartbeat_interval
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    async def run(self) -> None:
        logger.info("Starting mesh site operator agent for %s", self.site_id)
        tasks = [
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
            asyncio.create_task(self._inventory_loop(), name="inventory"),
            asyncio.create_task(self._warm_pool_loop(), name="warm_pool"),
        ]
        try:
            await self._stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Mesh site operator agent stopped")

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Reservation operations - used by API handlers
    # ------------------------------------------------------------------
    async def allocate_node(self, *, node_serial: Optional[str] = None, mesh_node_id: str) -> HardwareNode:
        candidates = self._select_candidates(node_serial=node_serial)
        if not candidates:
            raise RuntimeError("No hardware available")
        node = candidates[0]
        reserved = await self._controller.reserve_node(node.serial, mesh_node_id=mesh_node_id)
        task = self._provisioner.create_prepare_task(reserved)
        await self._publish_task(task)
        return reserved

    async def release_node(self, serial: str) -> None:
        await self._controller.release_node(serial)
        await self._control_plane.publish_inventory(self._serialise_inventory())

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------
    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                heartbeat = await self._build_heartbeat()
                await self._control_plane.send_heartbeat(heartbeat.__dict__)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to send heartbeat: %s", exc)
            await asyncio.sleep(self._heartbeat_interval)

    async def _inventory_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._control_plane.publish_inventory(self._serialise_inventory())
                await self._controller.expire_reservations()
            except Exception as exc:  # pragma: no cover
                logger.exception("Failed to publish inventory: %s", exc)
            await asyncio.sleep(self._heartbeat_interval * 2)

    async def _warm_pool_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._provisioner.ensure_warm_pool(target=self._warm_pool_target)
            except Exception as exc:  # pragma: no cover
                logger.exception("Warm pool maintenance error: %s", exc)
            await asyncio.sleep(20)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _select_candidates(self, *, node_serial: Optional[str]) -> Iterable[HardwareNode]:
        inventory = [n for n in self._controller.list_nodes() if n.state in {"available", "unknown"}]
        if node_serial:
            inventory = [n for n in inventory if n.serial == node_serial]
        inventory.sort(key=lambda n: (n.datacenter, n.rack, n.serial))
        return inventory

    async def _build_heartbeat(self) -> SiteHeartbeat:
        warm_pool_available = await self._provisioner.count_ready_nodes()
        tasks_in_flight = len(self._provisioner.list_tasks())
        digest_payload = {
            "nodes": [n.serial for n in self._controller.list_nodes()],
            "timestamp": datetime.utcnow().isoformat(),
        }
        inventory_digest = json.dumps(digest_payload, sort_keys=True)
        heartbeat = SiteHeartbeat(
            site_id=self.site_id,
            sent_at=datetime.utcnow(),
            inventory_digest=inventory_digest,
            warm_pool_available=warm_pool_available,
            tasks_in_flight=tasks_in_flight,
        )
        logger.debug("Heartbeat built: %s", heartbeat)
        return heartbeat

    async def _publish_task(self, task: ProvisioningTask) -> None:
        payload = {
            "task_id": task.task_id,
            "status": task.status,
            "node_serial": task.node_serial,
            "site_id": self.site_id,
            "logs": task.logs[-20:],
        }
        await self._control_plane.publish_task_status(payload)

    def _serialise_inventory(self) -> Dict[str, Any]:
        nodes = []
        for node in self._controller.list_nodes():
            nodes.append(
                {
                    "serial": node.serial,
                    "sku": node.sku,
                    "state": node.state,
                    "datacenter": node.datacenter,
                    "rack": node.rack,
                    "capabilities": node.capabilities,
                    "mesh_node_id": node.mesh_node_id,
                    "last_seen": node.last_seen.isoformat(),
                }
            )
        payload = {
            "site_id": self.site_id,
            "generated_at": datetime.utcnow().isoformat(),
            "nodes": nodes,
        }
        logger.debug("Inventory payload: %s", payload)
        return payload

