# Operator Integration Examples: Nine.ch & Phoenix Systems

These examples demonstrate how to plug customer-owned bare-metal GPUs into the
Swiss Compute Mesh using the modules that ship with this repository.  Both
scripts can talk to the real provider APIs (Nine.ch and Phoenix Systems) or run
with in-memory sample inventory for quick experimentation.

## Directory Structure

- `common.py` – shared helpers for building a secure bootstrap pipeline, wiring
  the in-memory control plane, and running a mesh site operator agent.
- `nine_site.py` – example site appliance for Nine.ch racks, including an async
  wrapper around the Nine bare-metal API and inventory ingestion helpers.
- `phoenix_site.py` – equivalent implementation targeting Phoenix Systems
  machines.

## Prerequisites

1. Python 3.10+
2. Install the optional HTTP dependency used by the examples:
   ```bash
   pip install requests
   ```
3. Clone this repository and run the commands from its root so Python can
   resolve the `alpencompute` package.

## Running the Nine.ch example

```bash
export PYTHONPATH=$(pwd)
export NINE_API_TOKEN="<nine-api-token>"
export NINE_REGION="ch-zrh-1"            # optional region filter
export MESH_ENDPOINT="mesh.example.ch:51820"  # WireGuard endpoint used in certificates

python -m examples.operators.nine_phoenix.nine_site
```

If `NINE_API_TOKEN` is omitted the script will fall back to the bundled demo
inventory so you can test the workflows without hitting the production API.

The example will:

1. Fetch or synthesise the hardware inventory from Nine.
2. Register the nodes with `CustomerHardwareController` and run the secure
   bootstrap pipeline.
3. Start the mesh site operator agent for ~30 seconds, emitting heartbeats and
   inventory snapshots to the in-memory control plane client.
4. Print the site token you would share with the global control plane.

Useful environment variables:

- `NINE_API_BASE` – override the API base URL (defaults to `https://api.nine.ch/v1`).
- `NINE_WARM_POOL_TARGET` – number of machines to keep staged in the warm pool.
- `NINE_AGENT_DURATION` – how long (in seconds) to keep the agent running.

## Running the Phoenix Systems example

```bash
export PYTHONPATH=$(pwd)
export PHOENIX_API_TOKEN="<phoenix-api-token>"
export PHOENIX_FACILITY="ch-lug-1"       # optional site filter
export MESH_ENDPOINT="mesh.example.ch:51820"

python -m examples.operators.nine_phoenix.phoenix_site
```

Environment overrides:

- `PHOENIX_API_BASE` – change the API endpoint (default `https://api.phoenixsystems.ch/v1`).
- `PHOENIX_WARM_POOL_TARGET` – desired warm pool size.
- `PHOENIX_AGENT_DURATION` – demo runtime before the agent shuts down.

Just like the Nine example, leaving `PHOENIX_API_TOKEN` unset will run in sample
mode with mock inventory data.

## Integrating with a Real Control Plane

The helper functions currently wire everything to the in-memory control plane
services that ship with the repository.  When moving to production you would:

1. Replace `setup_in_memory_control_plane` with RPC calls to the real control
   plane to register the site and obtain tokens.
2. Swap the sample bootstrap pipeline with the production configuration (real
   CA, WireGuard orchestrator, and health checks).
3. Feed the inventory snapshots and task status events into your central
   observability stack.

These examples provide a concrete starting point for operators to adapt the
bring-your-own hardware modules to their own automation and facilities.
