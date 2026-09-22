import json
from pathlib import Path
from datetime import datetime, timezone

SNAPSHOT_DIR = Path("data/snapshots")
CHANGES_DIR = Path("data/changes")
CHANGES_DIR.mkdir(parents=True, exist_ok=True)

snapshot_files = sorted(SNAPSHOT_DIR.glob("mcp-registry-*.json"))

if len(snapshot_files) < 2:
    print(
        "Not enough snapshots to compare yet. "
        "At least two snapshots are required."
    )
    raise SystemExit(0)

previous_file = snapshot_files[-2]
current_file = snapshot_files[-1]

with previous_file.open("r", encoding="utf-8") as f:
    previous_snapshot = json.load(f)

with current_file.open("r", encoding="utf-8") as f:
    current_snapshot = json.load(f)


def index_servers(snapshot):
    result = {}

    for entry in snapshot.get("data", {}).get("servers", []):
        server = entry.get("server", {})
        name = server.get("name")

        if name:
            result[name] = entry

    return result


previous_servers = index_servers(previous_snapshot)
current_servers = index_servers(current_snapshot)

previous_names = set(previous_servers)
current_names = set(current_servers)

added_names = sorted(current_names - previous_names)
removed_names = sorted(previous_names - current_names)
common_names = sorted(previous_names & current_names)

added = [current_servers[name] for name in added_names]
removed = [previous_servers[name] for name in removed_names]

version_changed = []
status_changed = []
other_changed = []

for name in common_names:
    before = previous_servers[name]
    after = current_servers[name]

    if before == after:
        continue

    before_server = before.get("server", {})
    after_server = after.get("server", {})

    before_meta = before.get("_meta", {}).get(
        "io.modelcontextprotocol.registry/official", {}
    )
    after_meta = after.get("_meta", {}).get(
        "io.modelcontextprotocol.registry/official", {}
    )

    before_version = before_server.get("version")
    after_version = after_server.get("version")

    before_status = before_meta.get("status")
    after_status = after_meta.get("status")

    if before_version != after_version:
        version_changed.append(
            {
                "name": name,
                "before": before_version,
                "after": after_version,
            }
        )

    if before_status != after_status:
        status_changed.append(
            {
                "name": name,
                "before": before_status,
                "after": after_status,
            }
        )

    other_changed.append(
        {
            "name": name,
            "before": before,
            "after": after,
        }
    )

comparison_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
output_file = CHANGES_DIR / f"changes-{comparison_date}.json"

result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "previous_snapshot": previous_file.name,
    "current_snapshot": current_file.name,
    "summary": {
        "previous_count": len(previous_servers),
        "current_count": len(current_servers),
        "added": len(added),
        "removed": len(removed),
        "version_changed": len(version_changed),
        "status_changed": len(status_changed),
        "changed_entries": len(other_changed),
    },
    "changes": {
        "added": added,
        "removed": removed,
        "version_changed": version_changed,
        "status_changed": status_changed,
        "changed_entries": other_changed,
    },
}

with output_file.open("w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(
    f"Comparison saved to {output_file}: "
    f"{len(added)} added, "
    f"{len(removed)} removed, "
    f"{len(version_changed)} version changes, "
    f"{len(status_changed)} status changes."
)
