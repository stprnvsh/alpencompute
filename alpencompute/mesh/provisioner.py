"""Provisioning helpers used by the mesh site operator."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ..hardware.customer_control import (
    CustomerHardwareController,
    HardwareNode,
    HardwareOperationError,
    ProvisioningTask,
)
from .bootstrap import BootstrapResult, SecureBootstrapPipeline

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WarmPoolNode:
    """Represents a node that is staged in the warm pool."""

    serial: str
    prepared_at: datetime
    ready: bool
    metadata: Dict[str, str] = field(default_factory=dict)


class ProvisioningManager:
    """Coordinates provisioning operations for a site."""

    def __init__(
        self,
        *,
        controller: CustomerHardwareController,
        bootstrap_pipeline: Optional[SecureBootstrapPipeline] = None,
    ) -> None:
        self._controller = controller
        self._bootstrap_pipeline = bootstrap_pipeline
        self._warm_pool: Dict[str, WarmPoolNode] = {}
        self._tasks: Dict[str, ProvisioningTask] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Warm pool management
    # ------------------------------------------------------------------
    async def ensure_warm_pool(self, *, target: int) -> None:
        async with self._lock:
            available_nodes = [n for n in self._controller.list_nodes() if n.state in {"available", "unknown"}]
            staged = list(self._warm_pool.values())
            deficit = max(0, target - len([n for n in staged if n.ready]))
            if deficit <= 0:
                return
            logger.info("Warm pool deficit detected (%s). Preparing nodes", deficit)
            for node in available_nodes[:deficit]:
                await self._prepare_node(node)

    async def count_ready_nodes(self) -> int:
        return len([n for n in self._warm_pool.values() if n.ready])

    def list_tasks(self) -> List[ProvisioningTask]:
        return list(self._tasks.values())

    # ------------------------------------------------------------------
    # Provisioning operations
    # ------------------------------------------------------------------
    def create_prepare_task(self, node: HardwareNode, *, auto_start: bool = True) -> ProvisioningTask:
        task = self._controller.create_task(node.serial, metadata={"kind": "prepare"})
        task.log("Starting prepare workflow")
        self._tasks[task.task_id] = task
        if auto_start:
            asyncio.create_task(self._run_prepare_workflow(task, node))
        return task

    async def _prepare_node(self, node: HardwareNode) -> None:
        task = self.create_prepare_task(node, auto_start=False)
        await self._run_prepare_workflow(task, node)

    async def _run_prepare_workflow(self, task: ProvisioningTask, node: HardwareNode) -> None:
        try:
            task.status = "running"
            task.log("Ensuring machine is powered off")
            await self._controller.ensure_power_state(node, "off")

            task.log("Setting PXE boot")
            await self._controller.configure_boot(node, "pxe")

            task.log("Powering on for imaging")
            await self._controller.ensure_power_state(node, "on")

            task.log("Waiting for secure bootstrap pipeline")
            bootstrap_result = await self._execute_bootstrap(node)
            if bootstrap_result:
                task.log(
                    "Issued certificate %(certificate)s and mesh IP %(mesh_ip)s"
                    % {
                        "certificate": bootstrap_result.certificate.certificate,
                        "mesh_ip": bootstrap_result.wireguard.mesh_ip,
                    }
                )

            task.status = "completed"
            task.log("Node ready for allocation")
            self._warm_pool[node.serial] = WarmPoolNode(
                serial=node.serial,
                prepared_at=datetime.utcnow(),
                ready=True,
                metadata={"last_task_id": task.task_id},
            )
        except HardwareOperationError as exc:
            task.status = "failed"
            task.log(f"Hardware error: {exc}")
            logger.error("Provisioning workflow failed for %s: %s", node.serial, exc)
            await self._controller.release_node(node.serial)
        except Exception as exc:  # pragma: no cover - defensive
            task.status = "failed"
            task.log(f"Unexpected error: {exc}")
            logger.exception("Unexpected provisioning error for %s", node.serial)
            await self._controller.release_node(node.serial)
        finally:
            await self._cleanup_node_state(node)

    async def _execute_bootstrap(self, node: HardwareNode) -> Optional[BootstrapResult]:
        if self._bootstrap_pipeline is None:
            # In production this would execute via SSH or the mesh agent bootstrap
            # channel.  For the reference implementation we simply simulate a wait
            # with retries.
            for attempt in range(5):
                await asyncio.sleep(2)
                logger.debug("Bootstrap attempt %s for %s", attempt + 1, node.serial)
            logger.info("Bootstrap script executed for %s", node.serial)
            return None

        result = await self._bootstrap_pipeline.execute(node)
        logger.info(
            "Secure bootstrap completed for %s (mesh_ip=%s)",
            node.serial,
            result.wireguard.mesh_ip,
        )
        return result

    async def _cleanup_node_state(self, node: HardwareNode) -> None:
        self._warm_pool[node.serial] = WarmPoolNode(
            serial=node.serial,
            prepared_at=datetime.utcnow(),
            ready=True,
        )
        await self._controller.release_node(node.serial)

