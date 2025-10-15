# Alpen Compute

Reference implementation for the Swiss Compute Mesh.  This repository now
contains executable modules for bring-your-own hardware operators in addition
to the architecture documentation.

## Modules

- `alpencompute.hardware.customer_control` – register, audit and manage
  customer provided bare-metal nodes.
- `alpencompute.mesh.bootstrap` – secure bootstrap pipeline wiring PKI,
  WireGuard enrolment, and health checks.
- `alpencompute.mesh.provisioner` – warm pool orchestration and imaging
  workflows with secure bootstrap integration.
- `alpencompute.mesh.site_operator` – site agent that connects a facility to
  the global control plane.
- `alpencompute.control_plane.operator_api` – in-memory operator registry and
  inventory ingestion endpoints powering the bring-your-own flow.

Refer to `docs/byo-bare-metal.md` for a full design overview, `docs/operator-architecture.md`
for control-plane vs. site responsibilities, `docs/byo-gpu-clusters.md` for the
bring-your-own multi-GPU cluster blueprint, and `docs/plan-progress.md` for
roadmap execution status. The day-to-day validation workflow is captured in
`docs/testing-guide.md`.
## Examples

- `examples/operators/partner_template` – provider-agnostic site operator
  template showcasing control plane wiring, secure bootstrap, and warm pool
  orchestration for any partner or on-premise fleet.


