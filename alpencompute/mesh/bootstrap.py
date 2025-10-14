"""Secure bootstrap pipeline for preparing nodes for the mesh."""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..hardware.customer_control import HardwareNode


@dataclass(slots=True)
class CertificateBundle:
    """Represents the certificates issued to a node."""

    certificate: str
    private_key: str
    issued_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class PKIManager:
    """Lightweight PKI helper issuing per-node certificates."""

    def __init__(self, *, ca_name: str, default_ttl: int = 24 * 3600) -> None:
        self._ca_name = ca_name
        self._default_ttl = default_ttl
        self._issued: Dict[str, CertificateBundle] = {}

    async def issue_node_certificate(self, node: HardwareNode) -> CertificateBundle:
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(seconds=self._default_ttl)
        bundle = CertificateBundle(
            certificate=f"cert-{self._ca_name}-{node.serial}",
            private_key=secrets.token_urlsafe(48),
            issued_at=issued_at,
            expires_at=expires_at,
            metadata={"ca": self._ca_name},
        )
        self._issued[node.serial] = bundle
        return bundle

    async def revoke_certificate(self, node_serial: str) -> None:
        self._issued.pop(node_serial, None)

    def get_certificate(self, node_serial: str) -> Optional[CertificateBundle]:
        return self._issued.get(node_serial)


@dataclass(slots=True)
class WireGuardConfig:
    """WireGuard configuration issued to a node."""

    public_key: str
    private_key: str
    mesh_ip: str
    endpoint: str
    allowed_ips: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WireGuardManager:
    """Issues WireGuard peer configuration for mesh nodes."""

    def __init__(self, *, mesh_endpoint: str, cidr_prefix: str = "10.100") -> None:
        self._mesh_endpoint = mesh_endpoint
        self._cidr_prefix = cidr_prefix
        self._peers: Dict[str, WireGuardConfig] = {}
        self._counter = 10

    async def enrol_node(self, node: HardwareNode, certificate: CertificateBundle) -> WireGuardConfig:
        private_key = secrets.token_urlsafe(32)
        public_key = f"pub-{private_key[:16]}"
        mesh_ip = f"{self._cidr_prefix}.{self._counter}.1"
        self._counter += 1
        config = WireGuardConfig(
            public_key=public_key,
            private_key=private_key,
            mesh_ip=mesh_ip,
            endpoint=self._mesh_endpoint,
            allowed_ips=[f"{mesh_ip}/32"],
            metadata={"certificate": certificate.certificate},
        )
        self._peers[node.serial] = config
        return config

    async def remove_peer(self, node_serial: str) -> None:
        self._peers.pop(node_serial, None)

    def get_peer(self, node_serial: str) -> Optional[WireGuardConfig]:
        return self._peers.get(node_serial)


class HealthCheckSuite:
    """Runs health checks on a node before it enters the warm pool."""

    def __init__(self, checks: Optional[List[Callable[[HardwareNode], Awaitable[Dict[str, Any]]]]] = None) -> None:
        self._checks = checks or []

    def register_check(self, check: Callable[[HardwareNode], Awaitable[Dict[str, Any]]]) -> None:
        self._checks.append(check)

    async def run(self, node: HardwareNode) -> Dict[str, Any]:
        report: Dict[str, Any] = {}
        for check in self._checks:
            result = await check(node)
            report.update(result)
        return report


@dataclass(slots=True)
class BootstrapResult:
    """Result returned by the secure bootstrap pipeline."""

    node_serial: str
    certificate: CertificateBundle
    wireguard: WireGuardConfig
    health_report: Dict[str, Any]
    completed_at: datetime


class SecureBootstrapPipeline:
    """Coordinates PKI, WireGuard, and health checks during provisioning."""

    def __init__(
        self,
        *,
        pki: PKIManager,
        wireguard: WireGuardManager,
        health_checks: HealthCheckSuite,
        join_retry_interval: int = 5,
        join_attempts: int = 3,
    ) -> None:
        self._pki = pki
        self._wireguard = wireguard
        self._health_checks = health_checks
        self._join_retry_interval = join_retry_interval
        self._join_attempts = join_attempts

    async def execute(self, node: HardwareNode) -> BootstrapResult:
        certificate = await self._pki.issue_node_certificate(node)
        wireguard_config = await self._wireguard.enrol_node(node, certificate)

        # Simulate join retries (e.g., waiting for the agent to connect)
        for attempt in range(1, self._join_attempts + 1):
            await asyncio.sleep(self._join_retry_interval / 10)
            # In a real implementation we would verify the node handshake here
            node.notes.setdefault("bootstrap", {})["join_attempt"] = attempt

        health_report = await self._health_checks.run(node)
        node.notes.setdefault("bootstrap", {}).update(
            {
                "certificate": certificate.certificate,
                "mesh_ip": wireguard_config.mesh_ip,
                "health": health_report,
            }
        )
        node.state = "ready"
        node.last_seen = datetime.utcnow()
        return BootstrapResult(
            node_serial=node.serial,
            certificate=certificate,
            wireguard=wireguard_config,
            health_report=health_report,
            completed_at=datetime.utcnow(),
        )

    async def teardown(self, node: HardwareNode) -> None:
        await self._wireguard.remove_peer(node.serial)
        await self._pki.revoke_certificate(node.serial)
        node.notes.pop("bootstrap", None)

