"""Shared helpers for the Nine.ch and Phoenix Systems operator examples."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Tuple

from alpencompute.control_plane.operator_api import (
    InventoryIngestionService,
    OperatorRegistry,
    SiteRegistration,
)
from alpencompute.hardware.customer_control import CustomerHardwareController, HardwareNode
from alpencompute.mesh.bootstrap import (
    HealthCheckSuite,
    PKIManager,
    SecureBootstrapPipeline,
    WireGuardManager,
)
from alpencompute.mesh.provisioner import ProvisioningManager
from alpencompute.mesh.site_operator import (
    InProcessControlPlaneClient,
    MeshSiteOperatorAgent,
)

logger = logging.getLogger(__name__)


async def _check_management_endpoint(node: HardwareNode) -> Dict[str, str]:
    """Lightweight health check used by the demo bootstrap pipeline."""
    await asyncio.sleep(0)
    return {
        "management_endpoint": node.management_endpoint,
        "last_checked_at": datetime.utcnow().isoformat(),
    }


def build_secure_pipeline(*, site_name: str, mesh_endpoint: str) -> SecureBootstrapPipeline:
    """Return a :class:`SecureBootstrapPipeline` configured for the examples."""
    pki = PKIManager(ca_name=f"{site_name}-ca")
    wireguard = WireGuardManager(mesh_endpoint=mesh_endpoint)
    health_checks = HealthCheckSuite([_check_management_endpoint])
    return SecureBootstrapPipeline(
        pki=pki,
        wireguard=wireguard,
        health_checks=health_checks,
        join_retry_interval=5,
        join_attempts=3,
    )


def setup_in_memory_control_plane(
    *,
    operator_name: str,
    contact_email: str,
    site_name: str,
    region: str,
) -> Tuple[OperatorRegistry, InventoryIngestionService, SiteRegistration, str, InProcessControlPlaneClient]:
    """Create an in-memory control plane suitable for local demonstrations."""
    registry = OperatorRegistry()
    operator = registry.register_operator(
        name=operator_name,
        contact_email=contact_email,
        jurisdiction="CH",
    )
    site = registry.register_site(
        operator_id=operator.operator_id,
        name=site_name,
        region=region,
    )
    token = site.issue_token(ttl_seconds=24 * 3600)
    inventory_service = InventoryIngestionService(registry)
    control_plane_client = InProcessControlPlaneClient(
        site_id=site.site_id,
        inventory_service=inventory_service,
    )
    return registry, inventory_service, site, token, control_plane_client


def create_site_agent(
    *,
    site: SiteRegistration,
    controller: CustomerHardwareController,
    pipeline: SecureBootstrapPipeline,
    control_plane_client: InProcessControlPlaneClient,
    warm_pool_target: int = 1,
) -> MeshSiteOperatorAgent:
    """Build a :class:`MeshSiteOperatorAgent` for the demonstration environment."""
    provisioner = ProvisioningManager(controller=controller, bootstrap_pipeline=pipeline)
    agent = MeshSiteOperatorAgent(
        site_id=site.site_id,
        controller=controller,
        provisioner=provisioner,
        control_plane=control_plane_client,
        warm_pool_target=warm_pool_target,
        heartbeat_interval=10,
    )
    return agent


async def run_agent_for_duration(agent: MeshSiteOperatorAgent, *, seconds: int) -> None:
    """Run the site operator agent for a fixed amount of time."""
    task = asyncio.create_task(agent.run())
    try:
        await asyncio.sleep(seconds)
    finally:
        agent.stop()
        await task
