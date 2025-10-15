# Partner Operator Template

This directory contains a **provider-agnostic starter kit** that shows how to
wire the bring-your-own hardware modules into a mesh site appliance.  It replaces
the earlier Nine/Phoenix examples with a template you can customise for any
partner or on-premise environment.

## What the template demonstrates

- **Inventory import** – load servers from a JSON manifest or call a partner
  API and normalise them into `HardwareNode` objects managed by
  `CustomerHardwareController`.
- **Secure bootstrap** – run the `SecureBootstrapPipeline` so each node receives
  certificates, WireGuard configuration, and health checks before it enters the
  warm pool.
- **Control plane handshake** – create an in-memory control plane, register the
  site, and publish capacity snapshots through `InventoryIngestionService`.
- **Warm pool automation** – keep a configurable number of nodes ready to
  allocate by driving `ProvisioningManager` through the
  `MeshSiteOperatorAgent`.

## Running the template

```bash
export PARTNER_NAME="Example Partner"
export PARTNER_SITE_NAME="Example Partner – ZRH"
export PARTNER_REGION="ch-zrh-1"

# Optional: point at your own inventory file (JSON array of servers)
# export PARTNER_INVENTORY_FILE="/path/to/partner-inventory.json"

python -m examples.operators.partner_template.partner_site
```

The script prints the latest inventory snapshot along with the site token that
needs to be shared with the global control plane during onboarding.

## Customising for a real partner

1. **Inventory source** – replace the JSON loader with calls to the partner API
   or generate the manifest from your CMDB.
2. **Credentials** – update how `HardwareCredential` is populated (Redfish,
   IPMI, vendor secrets, etc.).
3. **Capabilities** – extend the `capabilities` dictionary to capture partner
   specifics such as NVSwitch domains, MIG layouts, storage tier labels.
4. **Policy hooks** – add pricing, allow-list, or compliance metadata before
   publishing inventory snapshots so the control plane can enforce them.
5. **Packaging** – wrap the script into a systemd service or container to run on
   the partner’s site appliance.

The surrounding modules (`CustomerHardwareController`,
`ProvisioningManager`, `MeshSiteOperatorAgent`) remain unchanged, allowing you
to focus on integrating partner-specific APIs and workflows.
