import asyncio

from alpencompute.hardware.customer_control import (
    BaseManagementDriver,
    CustomerHardwareController,
    HardwareCredential,
    HardwareHealth,
    HardwareNode,
)
from alpencompute.mesh.bootstrap import (
    HealthCheckSuite,
    PKIManager,
    SecureBootstrapPipeline,
    WireGuardManager,
)
from alpencompute.mesh.provisioner import ProvisioningManager


class FakeDriver(BaseManagementDriver):
    def __init__(self) -> None:
        self._power_states = {}

    async def identify(self, node: HardwareNode) -> str:
        return f"fake-{node.serial}"

    async def power_state(self, node: HardwareNode) -> str:
        return self._power_states.get(node.serial, "off")

    async def set_power_state(self, node: HardwareNode, state: str) -> None:
        self._power_states[node.serial] = state

    async def set_boot_device(self, node: HardwareNode, device: str) -> None:
        node.notes["boot_device"] = device

    async def collect_health(self, node: HardwareNode) -> HardwareHealth:
        return HardwareHealth(
            power_state=self._power_states.get(node.serial, "on"),
            temperature_c=42.0,
            fan_speed_rpm=1200,
            bmc_version="1.0",
        )

    async def run_firmware_sync(self, node: HardwareNode, *, inventory: dict) -> None:
        node.notes["firmware"] = inventory


async def _run_pipeline_flow():
    driver = FakeDriver()
    controller = CustomerHardwareController(default_driver=driver)
    node = HardwareNode(
        serial="NODE-001",
        sku="h100x8",
        management_endpoint="https://bmc.local",
        credential=HardwareCredential(kind="password", username="admin", secret="secret"),
        datacenter="ch-zrh-1",
        rack="R1",
        capabilities={"gpus": 8},
        state="available",
    )
    controller.add_or_update_node(node)

    health_suite = HealthCheckSuite(
        checks=[lambda node: asyncio.sleep(0, result={"gpu_burnin": "ok"})]
    )
    pipeline = SecureBootstrapPipeline(
        pki=PKIManager(ca_name="vault-root"),
        wireguard=WireGuardManager(mesh_endpoint="mesh.alpencompute.local:51820"),
        health_checks=health_suite,
        join_retry_interval=1,
        join_attempts=2,
    )

    manager = ProvisioningManager(controller=controller, bootstrap_pipeline=pipeline)
    task = manager.create_prepare_task(node, auto_start=False)
    await manager._run_prepare_workflow(task, node)

    assert node.notes["bootstrap"]["health"]["gpu_burnin"] == "ok"
    assert "mesh_ip" in node.notes["bootstrap"]
    assert task.status == "completed"
    assert await manager.count_ready_nodes() == 1

    # Ensure teardown clears certificates and mesh peers
    await pipeline.teardown(node)
    assert "bootstrap" not in node.notes


def test_secure_bootstrap_pipeline_integration():
    asyncio.run(_run_pipeline_flow())
