"""Example integration for onboarding Nine.ch bare-metal servers."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from alpencompute.hardware.customer_control import (
    BaseManagementDriver,
    CustomerHardwareController,
    HardwareCredential,
    HardwareHealth,
    HardwareNode,
)

from .common import (
    build_secure_pipeline,
    create_site_agent,
    run_agent_for_duration,
    setup_in_memory_control_plane,
)

logger = logging.getLogger(__name__)


_SAMPLE_SERVERS: List[Dict[str, Any]] = [
    {
        "serial_number": "NINE-DEMO-H100-01",
        "type": "h100x8-nvswitch-2tb",
        "datacenter": "ch-zrh-1",
        "rack": "ZRH-ROW-7",
        "bmc_endpoint": "https://bmc-demo-01.nine.ch",
        "bmc_username": "admin",
        "bmc_password": "changeme",
        "gpu_count": 8,
        "gpu_model": "h100",
        "cpu_cores": 128,
        "memory_gb": 2048,
        "nvme_count": 8,
        "nvme_size_gb": 3200,
        "nic_speed_gbps": 100,
        "power_state": "off",
        "hostname": "nine-h100-demo-01",
    }
]


class NineAPIClient:
    """Minimal async wrapper around the Nine bare-metal API."""

    def __init__(
        self,
        *,
        token: Optional[str],
        base_url: str = "https://api.nine.ch/v1",
        sample_inventory: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session: Optional[requests.Session] = None
        if token:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
            )
        self._inventory: Dict[str, Dict[str, Any]] = {}
        for server in sample_inventory or []:
            self._inventory[server["serial_number"]] = dict(server)

    async def list_servers(self, *, region: Optional[str] = None) -> List[Dict[str, Any]]:
        servers: List[Dict[str, Any]]
        if self._session is None:
            servers = list(self._inventory.values())
        else:
            servers = await self._request("GET", "/servers")
        if region:
            servers = [srv for srv in servers if srv.get("datacenter") == region]
        return servers

    async def get_server(self, serial: str) -> Dict[str, Any]:
        if self._session is None:
            return self._inventory[serial]
        return await self._request("GET", f"/servers/{serial}")

    async def set_power_state(self, serial: str, state: str) -> None:
        if self._session is None:
            server = self._inventory[serial]
            server["power_state"] = state
            return
        await self._request("POST", f"/servers/{serial}/actions/power", json={"state": state})

    async def set_boot_device(self, serial: str, device: str) -> None:
        if self._session is None:
            server = self._inventory[serial]
            server["boot_device"] = device
            return
        await self._request(
            "POST",
            f"/servers/{serial}/actions/boot",
            json={"device": device},
        )

    async def collect_health(self, serial: str) -> Dict[str, Any]:
        if self._session is None:
            server = self._inventory[serial]
            return server.setdefault(
                "last_health",
                {
                    "power_state": server.get("power_state", "unknown"),
                    "temperature_c": 24.0,
                    "fan_speed_rpm": 4800,
                    "bmc_version": "demo-1.0",
                },
            )
        return await self._request("GET", f"/servers/{serial}/health")

    async def update_firmware(self, serial: str, *, inventory: Dict[str, str]) -> None:
        if self._session is None:
            server = self._inventory[serial]
            server.setdefault("firmware", {}).update(inventory)
            return
        await self._request(
            "POST",
            f"/servers/{serial}/actions/firmware",
            json={"inventory": inventory},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        assert self._session is not None, "HTTP session only available when using the real API"
        url = f"{self._base_url}{path}"
        loop = asyncio.get_running_loop()

        def _call() -> Any:
            response = self._session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

        return await loop.run_in_executor(None, _call)


class NineManagementDriver(BaseManagementDriver):
    """Adapter between the Nine API and the :class:`CustomerHardwareController`."""

    def __init__(self, client: NineAPIClient) -> None:
        self._client = client

    async def identify(self, node: HardwareNode) -> str:  # pragma: no cover - demo wrapper
        server = await self._client.get_server(node.serial)
        return server.get("hostname") or node.serial

    async def power_state(self, node: HardwareNode) -> str:
        server = await self._client.get_server(node.serial)
        return server.get("power_state", "unknown")

    async def set_power_state(self, node: HardwareNode, state: str) -> None:
        await self._client.set_power_state(node.serial, state)

    async def set_boot_device(self, node: HardwareNode, device: str) -> None:
        await self._client.set_boot_device(node.serial, device)

    async def collect_health(self, node: HardwareNode) -> HardwareHealth:
        raw = await self._client.collect_health(node.serial)
        return HardwareHealth(
            power_state=raw.get("power_state", "unknown"),
            temperature_c=raw.get("temperature_c"),
            fan_speed_rpm=raw.get("fan_speed_rpm"),
            bmc_version=raw.get("bmc_version"),
        )

    async def run_firmware_sync(self, node: HardwareNode, *, inventory: Dict[str, str]) -> None:
        await self._client.update_firmware(node.serial, inventory=inventory)


def _to_hardware_node(data: Dict[str, Any]) -> HardwareNode:
    credential = HardwareCredential(
        kind="redfish",
        username=data.get("bmc_username", "admin"),
        secret=data.get("bmc_password", "password"),
    )
    return HardwareNode(
        serial=data["serial_number"],
        sku=data.get("type", "unknown"),
        management_endpoint=data.get("bmc_endpoint", "https://bmc.local"),
        credential=credential,
        datacenter=data.get("datacenter", "unknown"),
        rack=data.get("rack", "rack-0"),
        capabilities={
            "gpu_count": data.get("gpu_count", 0),
            "gpu_model": data.get("gpu_model"),
            "cpu_cores": data.get("cpu_cores", 0),
            "memory_gb": data.get("memory_gb", 0),
            "nvme_count": data.get("nvme_count", 0),
            "nvme_size_gb": data.get("nvme_size_gb", 0),
            "nic_speed_gbps": data.get("nic_speed_gbps", 10),
        },
        state=data.get("power_state", "unknown"),
    )


async def load_inventory(
    controller: CustomerHardwareController,
    client: NineAPIClient,
    *,
    region: Optional[str],
) -> None:
    servers = await client.list_servers(region=region)
    for payload in servers:
        node = _to_hardware_node(payload)
        controller.add_or_update_node(node)
    logger.info("Loaded %s Nine servers into the controller", len(servers))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    api_token = os.getenv("NINE_API_TOKEN")
    base_url = os.getenv("NINE_API_BASE", "https://api.nine.ch/v1")
    region = os.getenv("NINE_REGION")
    warm_pool_target = int(os.getenv("NINE_WARM_POOL_TARGET", "1"))
    mesh_endpoint = os.getenv("MESH_ENDPOINT", "mesh.alpencompute.local:51820")

    if api_token:
        client = NineAPIClient(token=api_token, base_url=base_url)
    else:
        logger.warning("NINE_API_TOKEN not provided – falling back to sample inventory")
        client = NineAPIClient(token=None, sample_inventory=_SAMPLE_SERVERS)

    driver = NineManagementDriver(client)
    controller = CustomerHardwareController(default_driver=driver)
    await load_inventory(controller, client, region=region)

    _, inventory_service, site, site_token, control_plane_client = setup_in_memory_control_plane(
        operator_name="Nine.ch Demo",
        contact_email="ops@nine.ch",
        site_name="Nine Zurich",
        region=region or "ch-zrh-1",
    )
    pipeline = build_secure_pipeline(site_name=site.site_id, mesh_endpoint=mesh_endpoint)
    agent = create_site_agent(
        site=site,
        controller=controller,
        pipeline=pipeline,
        control_plane_client=control_plane_client,
        warm_pool_target=warm_pool_target,
    )

    await run_agent_for_duration(agent, seconds=int(os.getenv("NINE_AGENT_DURATION", "30")))

    snapshot = inventory_service.latest_inventory(site.site_id)
    if snapshot:
        logger.info("Latest inventory snapshot: %s", snapshot.raw_payload)
    logger.info("Issued site token (share with control plane): %s", site_token)


if __name__ == "__main__":
    asyncio.run(main())
