# Bring-Your-Own GPU Cluster Blueprint

This document explains how to layer partner-supplied multi-GPU clusters on top
of the existing bring-your-own hardware modules. The goal is to let operators
publish clustered GPU capacity (e.g. 8x H100 nodes with NVSwitch) and deliver a
serverless user experience where distributed training workloads run with a
single command—no manual NCCL or CUDA wiring required.

## Reusable Building Blocks

- **Inventory & driver abstraction** – `CustomerHardwareController` already
  tracks per-node capabilities and plugs into vendor-specific management drivers.
  Enrich each `HardwareNode.capabilities` entry with GPU topology metadata such
  as NVSwitch domains, InfiniBand fabrics, and preferred MIG layouts.
- **Warm-pool & secure bootstrap** – `ProvisioningManager` and
  `SecureBootstrapPipeline` prepare nodes, install drivers, and validate health
  before marking them ready. This ensures cluster slots can be staged in
  sub-minute timeframes.
- **Control-plane handshake** – `MeshSiteOperatorAgent`, `OperatorRegistry`, and
  `InventoryIngestionService` already authenticate operators, publish inventory
  snapshots, and enforce token-based updates.
- **Operator starter kit** – the provider-agnostic template under
  `examples/operators/partner_template` shows how to plug partner APIs and
  manifests into the control-plane handshake.

## Implementation Plan

1. **Extend hardware catalogues** – capture GPU-cluster metadata in the site
   manifests (e.g. NVSwitch domains, RDMA fabrics, MIG profiles) and persist the
   data in each `HardwareNode.capabilities` map.
2. **Cluster compositor module** – add `alpencompute.mesh.gpu_clusters` to group
   compatible nodes into logical capacity slots (e.g. `h100x8-nvswitch`). Use the
   existing warm-pool hooks to stage all constituent nodes simultaneously and tag
   them with a cluster identifier.
3. **Advertise cluster slots** – publish synthetic inventory records via
   `InventoryIngestionService` once a cluster slot is healthy. Include metadata
   such as GPU count, topology, residency constraints, and pricing so the global
   scheduler can reason about availability.
4. **Runtime surface** – expose a multi-GPU accelerator descriptor in the
   developer surface (CLI/SDK) and implement a launcher that automatically wires
   NCCL rendezvous data, hostfiles, and driver versions before invoking
   `torchrun`, `mpirun`, or equivalent.
5. **Developer experience** – ensure tenants can request complex training runs
   with a declarative payload (e.g. `alpencompute run train.py --accelerator
   h100x8`). The scheduler selects a ready cluster slot while the runtime hides
   low-level CUDA/NCCL configuration.
6. **Policy & pricing integration** – store allow-lists, residency tags, and
   price sheets alongside the cluster definitions so scheduling, compliance, and
   billing respect operator-specific requirements.

## Validation Steps

- Start from the partner template example, replace the sample manifest with a
  cluster-aware inventory, and confirm the agent reports aggregated capacity.
- Extend the integration tests to cover cluster slot creation, publication, and
  lifecycle transitions.
- Run end-to-end training smoke tests using the new accelerator descriptor to
  guarantee the runtime launcher correctly configures NCCL and CUDA across nodes.
