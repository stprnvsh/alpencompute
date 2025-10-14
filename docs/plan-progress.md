# Swiss Compute Mesh – Bring-Your-Own Hardware Progress Tracker

This tracker mirrors the roadmap described in `docs/byo-bare-metal.md` and captures the execution status across phases. Tasks are grouped by milestone and reference the responsible modules or documents when applicable.

## Phase 0 – Foundations (Weeks 0-4)

- [x] Document site operator appliance architecture and onboarding workflow (`docs/byo-bare-metal.md`).
- [x] Implement initial site operator agent, provisioning manager, and customer hardware control modules (`alpencompute/mesh/site_operator.py`, `alpencompute/mesh/provisioner.py`, `alpencompute/hardware/customer_control.py`).
- [x] Extend control plane APIs for operator registration and inventory ingestion (`alpencompute/control_plane/operator_api.py`).
- [x] Deliver secure bootstrap pipeline (PKI wiring, WireGuard join automation, health checks) with integration tests (`alpencompute/mesh/bootstrap.py`, `tests/test_secure_bootstrap_pipeline.py`).

## Phase 1 – Warm Pool & Serverless Runtime (Weeks 5-10)

- [ ] Enhance warm pool manager with predictive sizing based on demand telemetry.
- [ ] Integrate sandboxed runtimes (Firecracker/gVisor) into workload execution path.
- [ ] Ship CLI/SDK updates enabling unified `alpencompute run` targeting BYO nodes.

## Phase 2 – Marketplace & Billing (Weeks 11-16)

- [ ] Launch operator marketplace service with pricing, policy, and contract management.
- [ ] Implement real-time metering pipeline plus invoice and credit workflows.
- [ ] Add SLA monitoring hooks and automated remediation runbooks.

## Phase 3 – Compliance & Enterprise Features (Weeks 17-24)

- [ ] Integrate remote attestation and vulnerability scanning during provisioning.
- [ ] Provide enterprise IAM connectors (SCIM/SSO) and audit export pipelines.
- [ ] Release VSCode extension and observability dashboards for BYO workloads.

## Phase 4 – Scale-Out & Ecosystem (Weeks 25-36)

- [ ] Optimize scheduler for multi-site, latency-aware placement across operators.
- [ ] Introduce spot/auction capacity mechanics and reservation contracts.
- [ ] Expand ecosystem integrations (Terraform provider, CI runners, air-gapped deployments).

## Cross-Cutting Initiatives

- [ ] Establish metrics/KPI dashboard tracking onboarding time, workload latency, availability, and residency compliance.
- [ ] Formalize go-to-market plan with pricing, contracts, and operator support tiers.
- [ ] Run pilot with at least two Swiss operators to validate provisioning and compliance workflows.

