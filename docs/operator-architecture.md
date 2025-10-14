# Bring-Your-Own Hardware Control Architecture

## Do we need a "mother" control node?

The platform uses a **global control plane** that is deployed in a highly-available
configuration (3+ replicas across Swiss regions).  It is responsible for
certificate issuance, global inventory, scheduling and billing APIs.  There is
no single irreplaceable "mother" node—if one controller fails, the remaining
replicas continue to operate thanks to Raft-based consensus in etcd and
Vault's integrated storage.  Operators only need outbound HTTPS access from
their site appliance to the control plane URL.

```
+-----------------------------+           +------------------------------+
|  Control Plane Replicas     |  HTTPS    |  Operator Site Appliance     |
|-----------------------------|<--------->|------------------------------|
| - Inventory Registry (etcd) |           | - Mesh Site Operator Agent   |
| - PKI / Token Authority     |           | - Provisioner + Warm Pool    |
| - Scheduler & Marketplace   |           | - Node Agents (per machine)  |
| - API / CLI Gateway         |           | - Local policy definitions   |
+-----------------------------+           +------------------------------+
```

## Organisation-specific hardware catalogues

Every organisation installs a **site appliance** inside its network.  The
appliance reads a declarative catalogue file and discovers hardware via BMC or
provider APIs.  The catalogue lets operators describe racks, contact points,
allowed tenants, billing rate cards and custom health checks.

Example directory structure on the appliance:

```
/etc/alpencompute/
├── site.yaml              # site identity, control plane endpoint, tokens
├── inventory/
│   ├── nine-zrh.yaml      # Nine.ch rack description
│   └── phoenix-gva.yaml   # Phoenix Systems nodes
└── policies/
    ├── allowlists.yaml    # tenant allow lists per SKU
    └── pricing.yaml       # hourly price definitions
```

Each `inventory/*.yaml` file contains:

```yaml
sku: h100x8-nvswitch-2tb
provider: nine
region: ch-zrh-1
nodes:
  - serial: NINE-H100-01
    bmc:
      endpoint: https://10.0.0.15/redfish
      username: admin
      password: ${vault:site/nine-h100-01}
    tags:
      racks: [zrh-row5]
      purpose: production
    warm_pool:
      target: 2
      imaging_profile: ubuntu22-nvidia535
  - serial: NINE-H100-02
    ...
```

The site agent ingests these manifests, validates access to each node, and
publishes sanitized inventory records to the control plane via the
`OperatorRegistryClient`.  Custom fields (tags, warm-pool targets, policies)
are preserved so the scheduler can honour them.

## Publishing into the global availability pool

1. **Registration** – the appliance authenticates with a per-site token issued
   through the control plane onboarding workflow (`alpencompute.control_plane.operator_api`).
2. **Inventory Sync** – for each manifest, the site agent runs hardware probes
   (GPU model, firmware, NIC speed) and posts a `HardwareReservation` object to
   the control plane.  Nodes are initially marked `inventory_only` until the
   bootstrap pipeline passes.
3. **Bootstrap & Warm Pool** – the provisioning manager images nodes and runs
   the secure bootstrap checks.  Once a node is in `ready` state it advertises a
   `capacity_slot` with constraints (SKU, allowed tenants, price).
4. **Scheduler Integration** – tenants requesting GPUs see all `capacity_slot`
   entries that match their policies.  Slots remain attributed to the operator
   so usage, billing and audit logs stay partitioned by organisation.
5. **Customisation** – organisations can:
   - Define custom imaging profiles (different OS builds, driver stacks).
   - Attach metadata tags used by scheduling policies (e.g., "air-gapped",
     "university-only").
   - Set minimum warm-pool targets per SKU or per tenant.
   - Override pricing or promotional credits.

## Roll-out Plan

1. **Pilot (Phase 0 complete)** – use existing Nine/Phoenix manifests to ingest
   their racks and exercise the bootstrap workflow end-to-end.  Validate HA by
   failing individual control plane replicas.
2. **Phase 1** – add declarative policy files and expose them via the
   `OperatorRegistry` API so the global scheduler respects organisation-specific
   rules.  Deliver CLI tooling (`alpencompute operators sync`) to push catalogue
   updates from git-managed repositories.
3. **Phase 2** – integrate billing, metering and customer-facing marketplace.
   Operators can update price books and see utilisation dashboards.
4. **Phase 3** – expand to more providers, add attestation and compliance
   extensions (TPM, Keylime), and publish Terraform/Ansible modules for automated
   catalogue generation.

This approach keeps the control plane resilient while letting each organisation
curate its own bare-metal fleet and expose it as elastic, serverless capacity.
