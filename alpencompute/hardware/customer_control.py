"""Customer hardware control module.

This module provides the primitives that a customer operated data centre
needs to expose bare-metal hardware into the Swiss Compute Mesh.  It wraps
BMC/Redfish/SSH management actions, exposes inventory reconciliation helpers
and offers an audit friendly API that higher level services can call.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


class HardwareOperationError(RuntimeError):
    """Raised when a remote management action fails."""


@dataclass(slots=True)
class HardwareCredential:
    """Credentials used to talk to a management controller."""

    kind: str
    username: str
    secret: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HardwareNode:
    """Metadata about a customer's server."""

    serial: str
    sku: str
    management_endpoint: str
    credential: HardwareCredential
    datacenter: str
    rack: str
    capabilities: Dict[str, Any]
    last_seen: datetime = field(default_factory=datetime.utcnow)
    state: str = "unknown"  # available, reserved, provisioning, error
    mesh_node_id: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HardwareHealth:
    """Health snapshot returned by :class:`BaseManagementDriver`."""

    power_state: str
    temperature_c: Optional[float]
    fan_speed_rpm: Optional[int]
    bmc_version: Optional[str]
    collected_at: datetime = field(default_factory=datetime.utcnow)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProvisioningTask:
    """Represents an in-flight provisioning operation."""

    task_id: str
    node_serial: str
    requested_at: datetime = field(default_factory=datetime.utcnow)
    user: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    logs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def log(self, message: str) -> None:
        timestamp = datetime.utcnow().isoformat()
        entry = f"[{timestamp}] {message}"
        logger.debug(entry)
        self.logs.append(entry)


class BaseManagementDriver(ABC):
    """Abstract base class for hardware management drivers."""

    @abstractmethod
    async def identify(self, node: HardwareNode) -> str:
        """Return a friendly name for the node."""

    @abstractmethod
    async def power_state(self, node: HardwareNode) -> str:
        """Return the node's power state."""

    @abstractmethod
    async def set_power_state(self, node: HardwareNode, state: str) -> None:
        """Set the node power state (on/off/reboot)."""

    @abstractmethod
    async def set_boot_device(self, node: HardwareNode, device: str) -> None:
        """Configure the boot device (pxe/disk/cdrom)."""

    @abstractmethod
    async def collect_health(self, node: HardwareNode) -> HardwareHealth:
        """Return a health report."""

    @abstractmethod
    async def run_firmware_sync(self, node: HardwareNode, *, inventory: Dict[str, str]) -> None:
        """Ensure the firmware matches the provided versions."""


class CustomerHardwareController:
    """Coordinates customer hardware interactions.

    The controller keeps a lightweight in-memory registry of nodes so that the
    site operator agent and the global control plane can query the hardware
    inventory.  It wraps management drivers and exposes higher level helper
    methods that take care of retries, jitter and audit logging.
    """

    def __init__(self, *, default_driver: BaseManagementDriver, reconciliation_interval: int = 300):
        self._nodes: Dict[str, HardwareNode] = {}
        self._driver_registry: Dict[str, BaseManagementDriver] = {
            "default": default_driver,
        }
        self._tasks: Dict[str, ProvisioningTask] = {}
        self._reconciliation_interval = reconciliation_interval
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------
    def register_management_driver(self, name: str, driver: BaseManagementDriver) -> None:
        logger.debug("registering management driver %s", name)
        self._driver_registry[name] = driver

    def add_or_update_node(self, node: HardwareNode, *, driver: str = "default") -> None:
        if driver not in self._driver_registry:
            raise KeyError(f"Unknown management driver '{driver}'")
        node.notes["driver"] = driver
        self._nodes[node.serial] = node
        logger.info("Registered node %s (%s)", node.serial, node.sku)

    def remove_node(self, serial: str) -> None:
        self._nodes.pop(serial, None)
        logger.info("Removed node %s", serial)

    def list_nodes(self) -> Iterable[HardwareNode]:
        return list(self._nodes.values())

    def get_node(self, serial: str) -> Optional[HardwareNode]:
        return self._nodes.get(serial)

    # ------------------------------------------------------------------
    # Provisioning task lifecycle
    # ------------------------------------------------------------------
    def create_task(self, node_serial: str, *, user: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ProvisioningTask:
        task_id = f"task-{len(self._tasks) + 1}-{int(datetime.utcnow().timestamp())}"
        task = ProvisioningTask(task_id=task_id, node_serial=node_serial, user=user)
        if metadata:
            task.metadata.update(metadata)
        self._tasks[task_id] = task
        logger.debug("Created provisioning task %s for node %s", task_id, node_serial)
        return task

    def get_task(self, task_id: str) -> Optional[ProvisioningTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[ProvisioningTask]:
        return list(self._tasks.values())

    # ------------------------------------------------------------------
    # Remote actions
    # ------------------------------------------------------------------
    async def ensure_power_state(self, node: HardwareNode, state: str, *, driver: Optional[str] = None, timeout: int = 180) -> None:
        drv = self._resolve_driver(node, driver)
        deadline = datetime.utcnow() + timedelta(seconds=timeout)
        desired = state.lower()
        while datetime.utcnow() < deadline:
            current = (await drv.power_state(node)).lower()
            if current == desired:
                node.state = "available" if desired == "on" else "off"
                node.last_seen = datetime.utcnow()
                logger.info("Node %s reached power state %s", node.serial, desired)
                return
            logger.debug("Node %s power state %s != %s, toggling", node.serial, current, desired)
            await drv.set_power_state(node, desired)
            await asyncio.sleep(5)
        raise HardwareOperationError(f"Timed out waiting for {node.serial} to reach power state {desired}")

    async def configure_boot(self, node: HardwareNode, device: str, *, driver: Optional[str] = None) -> None:
        drv = self._resolve_driver(node, driver)
        await drv.set_boot_device(node, device)
        logger.info("Node %s boot device set to %s", node.serial, device)

    async def reconcile_health(self, *, limit: Optional[int] = None) -> Dict[str, HardwareHealth]:
        results: Dict[str, HardwareHealth] = {}
        for idx, node in enumerate(self._nodes.values()):
            if limit is not None and idx >= limit:
                break
            drv = self._resolve_driver(node)
            health = await drv.collect_health(node)
            results[node.serial] = health
            node.last_seen = health.collected_at
            node.notes["health"] = {
                "power_state": health.power_state,
                "temperature_c": health.temperature_c,
                "fan_speed_rpm": health.fan_speed_rpm,
            }
            logger.debug("Collected health for %s: %s", node.serial, health)
        return results

    async def run_reconciliation_loop(self, *, stop_event: Optional[asyncio.Event] = None) -> None:
        logger.info("Starting hardware reconciliation loop")
        while stop_event is None or not stop_event.is_set():
            try:
                await self.reconcile_health()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Hardware reconciliation error: %s", exc)
            await asyncio.sleep(self._reconciliation_interval)
        logger.info("Stopping hardware reconciliation loop")

    async def apply_firmware_baseline(self, node: HardwareNode, baseline: Dict[str, str], *, driver: Optional[str] = None) -> None:
        drv = self._resolve_driver(node, driver)
        await drv.run_firmware_sync(node, inventory=baseline)
        logger.info("Applied firmware baseline to %s", node.serial)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_driver(self, node: HardwareNode, driver_name: Optional[str] = None) -> BaseManagementDriver:
        name = driver_name or node.notes.get("driver", "default")
        try:
            return self._driver_registry[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise HardwareOperationError(f"No management driver named '{name}' configured") from exc

    async def reserve_node(self, serial: str, *, mesh_node_id: str, ttl: int = 900) -> HardwareNode:
        async with self._lock:
            node = self._nodes.get(serial)
            if not node:
                raise KeyError(f"Unknown node {serial}")
            if node.state not in {"available", "unknown"}:
                raise HardwareOperationError(f"Node {serial} is currently {node.state}")
            node.state = "reserved"
            node.mesh_node_id = mesh_node_id
            node.notes["reservation_expires_at"] = datetime.utcnow() + timedelta(seconds=ttl)
            logger.info("Reserved node %s for mesh node %s", serial, mesh_node_id)
            return node

    async def release_node(self, serial: str) -> None:
        async with self._lock:
            node = self._nodes.get(serial)
            if not node:
                return
            node.state = "available"
            node.mesh_node_id = None
            node.notes.pop("reservation_expires_at", None)
            logger.info("Released node %s", serial)

    async def expire_reservations(self) -> None:
        now = datetime.utcnow()
        for node in self._nodes.values():
            expires_at = node.notes.get("reservation_expires_at")
            if expires_at and expires_at < now:
                logger.warning("Reservation for node %s expired", node.serial)
                node.state = "available"
                node.mesh_node_id = None
                node.notes.pop("reservation_expires_at", None)

