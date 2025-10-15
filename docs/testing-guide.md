# Testing and Validation Guide

This guide explains how to exercise the bring-your-own hardware modules, run the
included automated tests, and dry-run the site operator examples that ship with
this repository.

## 1. Environment Setup

The codebase targets Python 3.11 or newer. Create an isolated environment and
install the minimal development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

The development requirements currently only include the tooling that is needed
for the automated test-suite (pytest) and the example integrations (requests,
click).

## 2. Automated Tests

Run the full suite from the project root:

```bash
pytest
```

To focus on a specific behaviour you can target an individual module or test
case. Examples:

```bash
# Control plane registration and inventory ingestion flow
pytest tests/test_control_plane_operator_api.py

# Secure bootstrap and provisioning warm-pool workflow
pytest tests/test_secure_bootstrap_pipeline.py::test_secure_bootstrap_pipeline_integration
```

These tests create in-memory registries and fake drivers, so they do not require
external infrastructure. They cover the critical flows that keep the warm pool
ready and ensure the operator registry authenticates sites correctly.

## 3. Static Checks (Optional)

For a quick syntax verification you can compile the package:

```bash
python -m compileall alpencompute
```

## 4. Running the Operator Template

The `examples/operators/partner_template` directory provides a provider-agnostic
site appliance starter. It loads inventory from a JSON file (or the bundled
sample), brings up an in-memory control plane, provisions a node, and runs the
agent loop for a short duration.

```bash
python examples/operators/partner_template/partner_site.py
```

Customise the runtime with environment variables such as
`PARTNER_INVENTORY_FILE`, `PARTNER_REGION`, `PARTNER_WARM_POOL_TARGET`, and
`PARTNER_AGENT_DURATION`. You can also point the simulation at a specific mesh
endpoint by setting `MESH_ENDPOINT`.

## 5. Next Steps

When integrating with real hardware you will need to provide the appropriate API
tokens, BMC endpoints, and PXE infrastructure. The example scripts are designed
to be adapted—replace the sample inventory with live data and plug in the real
credentials once you are ready to move beyond the sandbox.
