from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CHANGE_DIR = ROOT / "data" / "changes"
SNAPSHOT_RE = re.compile(r"^mcp-registry-(\d{4}-\d{2}-\d{2})\.json$")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def snapshot_date(path: Path) -> date:
    """Read the observation date from the snapshot filename, never filesystem mtime."""
    match = SNAPSHOT_RE.match(path.name)
    if not match:
        raise ValueError(f"Unexpected snapshot filename: {path.name}")
    return date.fromisoformat(match.group(1))


def unwrap_record(item: dict) -> dict:
    """Return the canonical server payload when a registry result wraps it."""
    for key in ("server", "record", "item"):
        nested = item.get(key)
        if isinstance(nested, dict):
            return nested
    return item


def key_for(item: dict) -> str:
    """Prefer stable identity fields; fall back to a stable representation only as a last resort."""
    record = unwrap_record(item)
    for key in ("name", "id", "slug", "server_name", "serverName"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Preserve compatibility with the original AHI comparator.  Do not use the
    # full-record hash here: a content change must remain the same entity so it
    # can be reported as drift rather than as remove+add.
    return "anon:" + stable_json(record)[:220]


def version_of(item: dict):
    record = unwrap_record(item)
    for key in ("version", "currentVersion", "latestVersion"):
        if key in record:
            return record.get(key)
    return None


def status_of(item: dict):
    record = unwrap_record(item)
    for key in ("status", "state"):
        if key in record:
            return record.get(key)
    return None


def index(items):
    return {key_for(x): x for x in items if isinstance(x, dict)}


def snapshot_items(snapshot: dict) -> list:
    """Return server records from both legacy and V4 snapshot schemas.

    Legacy snapshots store records at data.servers, while V4 stores the list
    directly in data. Historical snapshots are never rewritten; the reader
    remains backward-compatible instead.
    """
    data = snapshot.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        servers = data.get("servers")
        if isinstance(servers, list):
            return servers
    raise ValueError(
        "Unsupported snapshot schema: expected 'data' as a list or 'data.servers' as a list."
    )


def compare(old: dict, new: dict, old_file: Path, new_file: Path) -> dict:
    old_items = snapshot_items(old)
    new_items = snapshot_items(new)

    a, b = index(old_items), index(new_items)
    ak, bk = set(a), set(b)

    added_keys = sorted(bk - ak)
    removed_keys = sorted(ak - bk)
    version_changes, status_changes, content_changes = [], [], []

    for name in sorted(ak & bk):
        before, after = a[name], b[name]
        ov, nv = version_of(before), version_of(after)
        os, ns = status_of(before), status_of(after)
        if ov != nv:
            version_changes.append({"name": name, "before": ov, "after": nv})
        if os != ns:
            status_changes.append({"name": name, "before": os, "after": ns})

        before_json, after_json = stable_json(before), stable_json(after)
        if before_json != after_json:
            content_changes.append({
                "name": name,
                "before_hash": sha256_text(before_json),
                "after_hash": sha256_text(after_json),
            })

    return {
        "schema_version": "2.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "old_snapshot": old_file.name,
        "new_snapshot": new_file.name,
        "old_collected_at": old.get("collected_at"),
        "new_collected_at": new.get("collected_at"),
        "summary": {
            "old_records": len(old_items),
            "new_records": len(new_items),
            "added": len(added_keys),
            "removed": len(removed_keys),
            "version_changes": len(version_changes),
            "status_changes": len(status_changes),
            "content_changes": len(content_changes),
        },
        "added": [{"name": name, "record": b[name]} for name in added_keys],
        "removed": [{"name": name, "last_record": a[name]} for name in removed_keys],
        "version_changes": version_changes,
        "status_changes": status_changes,
        "content_changes": content_changes,
    }


def main():
    files = [p for p in SNAPSHOT_DIR.glob("mcp-registry-*.json") if SNAPSHOT_RE.match(p.name)]
    files = sorted(files, key=snapshot_date)
    if len(files) < 2:
        print("Not enough snapshots to compare yet.")
        return

    old, new = files[-2], files[-1]
    old_date, new_date = snapshot_date(old), snapshot_date(new)
    if old_date >= new_date:
        raise RuntimeError(f"Invalid snapshot order: {old.name} -> {new.name}")

    result = compare(load(old), load(new), old, new)
    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    out = CHANGE_DIR / f"changes-{new_date.isoformat()}.json"

    # If this exact historical comparison already exists, do not overwrite it.
    # Historical records are append-only. A future recalculation should use a
    # distinct explicit migration/reprocessing workflow rather than silently
    # replacing evidence.
    if out.exists():
        existing = load(out)
        existing_old = existing.get("old_snapshot")
        existing_new = existing.get("new_snapshot")
        if existing_old == old.name and existing_new == new.name:
            print(f"Comparison already exists for {old.name} -> {new.name}: {out}")
            return
        print(
            f"Historical comparison already exists at {out}; preserving it unchanged. "
            "No duplicate comparison was written."
        )
        return

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(
        f"Compared {old.name} -> {new.name}\n"
        f"Comparison saved to {out}: {s['added']} added, {s['removed']} removed, "
        f"{s['version_changes']} version changes, {s['status_changes']} status changes, "
        f"{s['content_changes']} content changes."
    )


if __name__ == "__main__":
    main()
