# Bring-Your-Own Bare Metal Serverless Platform

## Vision

Deliver a turnkey serverless experience on top of customer-owned GPU and CPU servers. Operators onboard their hardware into the Swiss Compute Mesh and instantly expose it as elastic, policy-governed capacity to developers. Users receive Vast.ai-like self-service access with the safeguards and compliance posture expected from sovereign Swiss infrastructure.

## Goals

1. **Self-service onboarding** of heterogeneous bare metal nodes from multiple data centres or private server rooms.
2. **<1 minute allocation time** for workloads by maintaining warm pools and automated provisioning pipelines.
3. **Serverless developer experience**: run code with a single command, API call, or directly from IDEs without dealing with infrastructure plumbing.
4. **Sovereign control**: data never leaves Swiss territory; full audit trails and policy enforcement across the mesh.
5. **Provider marketplace & billing**: operators can expose capacity with fine-grained controls (price, tenant allow-lists) while enterprises retain predictability.

## Architecture Overview

```
+---------------------+        +------------------------------+
| Customer Hardware   |        |  Alpencompute Control Plane  |
| (GPU / CPU servers) |        |------------------------------|
|  - BMC / Redfish    |  API   |  - Mesh Federation API       |
|  - PXE / iPXE       +------->|  - Scheduler & Queue         |
|  - Out-of-band mgmt |        |  - Billing & Marketplace     |
+----+----------------+        |  - Secrets & PKI             |
     ^                         |  - Observability & Auditing  |
     |                         +----+-------------------------+
     |                              |
     |                              | WireGuard mesh
     |                              v
+----+----------------+        +----+--------------------------+
| Mesh Site Operator  |        | Serverless Runtime Layer      |
| Agent & Provisioner |        |------------------------------ |
|---------------------|        |  - Function/Job Runtime       |
| - Warm pool manager |        |  - Endpoint autoscaler        |
| - Node agent daemons|        |  - Image builder & registry   |
| - Policy enforcement|        |  - Data services (bucket/KV)  |
+---------------------+        +-------------------------------+
```

## Key Workflows

### 1. Operator Onboarding

1. Operator registers through the Control Plane Marketplace and verifies Swiss jurisdiction.
2. Install the **Site Operator Appliance** (VM or container) inside the operator network.
3. Appliance connects to BMC/Redfish endpoints and PXE infrastructure, authenticating using per-site PKI certificates issued by Vault.
4. Appliance continuously syncs hardware inventory (GPU model, RAM, NIC, firmware) into the global registry, flagging nodes eligible for serverless pools.
5. Operators define policies: pricing, tenant allowlists, maintenance windows, data locality constraints.

### 2. Warm Pool Preparation

1. Scheduler maintains target warm pool size per hardware SKU and tenant demand forecasts.
2. When additional nodes are needed, the appliance triggers automated provisioning via Ironic/Tinkerbell:
   - Power-cycle node via BMC, set PXE boot order.
   - Boot into alpine-based provisioning image.
   - Flash verified OS image with NVIDIA drivers, container runtime, and mesh agent.
3. After imaging, node joins the WireGuard mesh, fetches short-lived certificates, and runs conformance checks (GPU burn-in, network throughput, security baseline).
4. Node transitions to `ready` state, carrying a clean snapshot (or overlay FS) that enables <60s workload allocation.

### 3. Tenant Allocation (Serverless Experience)

1. Developer invokes `alpencompute run myscript.py --accelerator h100` or uses SDK/VSCode extension.
2. Control Plane scheduler selects an appropriate ready node considering policies (tenant/operator affinity, compliance tags, cost, latency).
3. Node agent pulls workload container/image, injects secrets, and executes within Firecracker or container sandbox with enforced network policies (default deny + allowlist).
4. Telemetry (GPU utilization, runtime logs) streams back to the Control Plane for billing and observability.
5. On completion, data is persisted to tenant storage, node is sanitized (disk wipe, credential rotation) and optionally returned to warm pool.

## Core Components

### Site Operator Appliance

- **Provisioner Integrations**: pluggable drivers for Ironic, Tinkerbell, MAAS; generic Redfish/IPMI adapter.
- **Warm Pool Manager**: predictive model to maintain ready capacity; handles lifecycle hooks (health checks, security patching).
- **Compliance Guardrails**: ensure every node bootstraps with secure boot, measured attestations (TPM), and vulnerability scanning.
- **Observability Gateway**: exports metrics/logs to mesh; caches locally during outages.

### Control Plane Enhancements

- **Marketplace Service**: onboarding flows, contract management, SLA configurations, revenue sharing.
- **Multi-Tenant Scheduler**: GPU-aware scheduling with policy constraints (data residency, cost ceilings, GPU topology).
- **Billing & Credits Engine**: metered usage per second; supports pre-purchased reservations and spot-style auctions.
- **Security Services**: Vault-backed PKI, OPA policies for network/egress, audit log pipeline to Swiss-compliant storage.

### Serverless Runtime Layer

- **Primitives**: function, endpoint, job, workflow (as in Swiss Compute Mesh) extended with BYO hardware annotations.
- **Image Service**: multi-architecture builder (BuildKit) plus curated base images; supports tenant-provided Dockerfiles.
- **Execution Sandboxes**: choose between containerd + gVisor, Firecracker microVMs, or MIG-partitioned GPUs.
- **Data Services**: Swiss-resident object/KV/SQL storage with per-tenant isolation and cross-site replication.

## Security & Compliance

- **Zero Trust Mesh**: WireGuard overlay, mTLS per workload, policy-managed service mesh (SPIFFE IDs).
- **Attestation & Trust**: integrate with Nitric/Keylime for remote attestation of operator nodes before accepting workloads.
- **Data Lifecycle**: mandatory disk wiping, encrypted scratch space, and tenant-specific encryption keys via KMS.
- **Auditability**: append-only audit logs stored in Swiss S3-compatible storage; exportable reports for FINMA, GDPR, FADP.

## Developer Experience

- **CLI & SDK**: `alpencompute run`, `deploy`, `invoke`; Python and Go SDKs for programmatic control.
- **VSCode Extension**: run/debug functions against remote GPUs, manage secrets, monitor jobs.
- **Templates**: ready-to-use stacks (LLM fine-tuning, CFD simulations, genomics pipelines) configured for Swiss Mesh resources.
- **Observability**: real-time dashboards, log streaming, cost estimation before launch.

## Operator Experience

- **Operator Console**: web UI for hardware inventory, policy definitions, revenue analytics.
- **Health Monitoring**: integrates with Prometheus; alerts for degraded GPUs, network issues, or compliance drifts.
- **Capacity Forecasting**: insights based on workload demand to plan hardware purchases or maintenance windows.

## Implementation Roadmap

### Phase 0 – Foundations (Weeks 0-4)
- Build Site Operator Appliance prototype with Ironic integration. *(Implemented via `alpencompute.mesh.site_operator` and `alpencompute.mesh.provisioner`.)*
- Implement secure bootstrap (PKI, WireGuard join, health checks). *(Delivered through `alpencompute.mesh.bootstrap` and integrated in the provisioning manager.)*
- Extend Control Plane APIs for operator registration and inventory ingestion. *(Available in `alpencompute.control_plane.operator_api` with in-memory registry services.)*

### Phase 1 – Warm Pool & Serverless Runtime (Weeks 5-10)
- Implement warm pool manager with predictive sizing.
- Integrate Firecracker/gVisor sandboxing into runtime layer.
- Deliver CLI/SDK updates for unified `run` workflow targeting BYO nodes.

### Phase 2 – Marketplace & Billing (Weeks 11-16)
- Launch operator marketplace with pricing, policy, and contract modules.
- Add real-time metering, invoice generation, and credit purchases.
- Implement SLA monitoring and automated remediation workflows.

### Phase 3 – Compliance & Enterprise Features (Weeks 17-24)
- Add remote attestation, vulnerability scanning, and mandatory disk wipe automation.
- Deliver enterprise IAM (SCIM, SSO), audit exports, and private marketplace support.
- Release VSCode extension and advanced observability dashboards.

### Phase 4 – Scale-Out & Ecosystem (Weeks 25-36)
- Optimize scheduler for multi-site, multi-operator scaling (latency-aware placement).
- Introduce spot/auction-style capacity and reservation contracts.
- Expand integrations (Terraform provider, GitHub Actions runner, air-gapped deployments).

## KPIs

- Time from `run` command to workload start < 60 seconds.
- Operator onboarding completion within 1 day.
- 99.9% availability for Control Plane APIs.
- ≥95% of workloads confined to Swiss infrastructure verified via attestation logs.
- Operator NPS ≥ 40, Developer NPS ≥ 50.

## Next Steps

1. Draft detailed technical design docs for the Site Operator Appliance and warm pool pipeline.
2. Stand up pilot with two Swiss operators (e.g., Nine.ch, Phoenix Systems) to validate provisioning and compliance workflow.
3. Build developer preview of CLI/SDK with BYO node targeting.
4. Establish go-to-market plan outlining pricing, contracts, and support tiers for operators and tenants.

