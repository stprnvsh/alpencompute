from datetime import datetime

from alpencompute.control_plane import InventoryIngestionService, OperatorRegistry
from alpencompute.mesh.site_operator import SiteHeartbeat


def test_operator_registration_and_inventory_ingestion_round_trip():
    registry = OperatorRegistry()
    operator = registry.register_operator(
        name="Nine.ch",
        contact_email="ops@nine.ch",
        jurisdiction="CH",
        metadata={"vat": "CHE-123"},
    )

    site = registry.register_site(
        operator_id=operator.operator_id,
        name="Zurich GPU Room",
        region="ch-zrh-1",
        allowed_cidrs=["10.0.0.0/24"],
    )

    token = site.issue_token(ttl_seconds=120)
    authenticated = registry.authenticate_site(token)
    assert authenticated is site

    ingestion = InventoryIngestionService(registry)
    payload = {
        "site_id": site.site_id,
        "generated_at": datetime.utcnow().isoformat(),
        "nodes": [
            {
                "serial": "NODE-123",
                "sku": "h100x8",
                "state": "available",
                "datacenter": "ch-zrh-1",
                "rack": "R1",
                "capabilities": {"gpus": 8},
                "mesh_node_id": None,
                "last_seen": datetime.utcnow().isoformat(),
            }
        ],
    }

    snapshot = ingestion.ingest_inventory(site_id=site.site_id, payload=payload)
    assert snapshot.nodes[0]["serial"] == "NODE-123"

    heartbeat = SiteHeartbeat(
        site_id=site.site_id,
        sent_at=datetime.utcnow(),
        inventory_digest="digest",
        warm_pool_available=1,
        tasks_in_flight=0,
    )
    ingestion.record_heartbeat(site_id=site.site_id, heartbeat=heartbeat)
    assert registry.get_site(site.site_id).last_heartbeat == heartbeat

    ingestion.record_task_status(site_id=site.site_id, payload={"task_id": "task-1", "status": "running"})
    events = ingestion.task_events()
    assert events[0]["site_id"] == site.site_id
    assert events[0]["task_id"] == "task-1"
