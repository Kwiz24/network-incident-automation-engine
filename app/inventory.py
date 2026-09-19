"""Versioned, bundled mock network inventory; NOT connected to NetBox."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_INVENTORY = Path(__file__).resolve().parent.parent / "samples" / "inventory.json"


def load_inventory(source=DEFAULT_INVENTORY):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    devices, circuits = data["devices"], data["circuits"]
    if not isinstance(devices, list) or not isinstance(circuits, list):
        raise ValueError("inventory lists required")
    device_ids = set()
    for item in devices:
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("device_id", "site", "role", "owner_team")):
            raise ValueError("device has missing fields")
        if item["device_id"] in device_ids:
            raise ValueError("duplicate device ID")
        device_ids.add(item["device_id"])
    circuit_ids = set()
    for item in circuits:
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("circuit_id", "device_id", "interface_name", "provider", "owner_team")):
            raise ValueError("circuit has missing fields")
        if item["circuit_id"] in circuit_ids or item["device_id"] not in device_ids:
            raise ValueError("duplicate circuit ID or unknown device")
        circuit_ids.add(item["circuit_id"])
    return data


def seed_inventory(conn, source=DEFAULT_INVENTORY):
    """Seed once per database; existing local inventory entries remain untouched."""
    data = load_inventory(source)
    count = conn.execute("SELECT COUNT(*) FROM inventory_devices").fetchone()[0]
    if count:
        return
    conn.executemany("INSERT INTO inventory_devices(device_id,site,role,owner_team) VALUES(:device_id,:site,:role,:owner_team)", data["devices"])
    conn.executemany("INSERT INTO inventory_circuits(circuit_id,device_id,interface_name,provider,owner_team) VALUES(:circuit_id,:device_id,:interface_name,:provider,:owner_team)",data["circuits"])


def lookup(conn, circuit_id):
    row = conn.execute("""SELECT c.circuit_id,c.device_id,c.interface_name,c.provider,
                           c.owner_team,d.site,d.role AS device_role
                           FROM inventory_circuits c JOIN inventory_devices d
                           ON c.device_id=d.device_id WHERE c.circuit_id=?""", (circuit_id,)).fetchone()
    return dict(zip(("circuit_id","device_id","interface_name","provider","owner_team","site","device_role"),row)) if row else None


def inventory_snapshot(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return {
            "source": "bundled mock inventory (not live NetBox)",
            "devices": [dict(r) for r in conn.execute("SELECT * FROM inventory_devices ORDER BY device_id")],
            "circuits": [dict(r) for r in conn.execute("""SELECT c.*,d.site,d.role AS device_role FROM inventory_circuits c
                                 JOIN inventory_devices d ON c.device_id=d.device_id ORDER BY c.circuit_id""")]
        }
