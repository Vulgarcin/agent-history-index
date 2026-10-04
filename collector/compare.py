from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
CHANGE_DIR = ROOT / "data" / "changes"
SNAPSHOT_RE = re.compile(r"^mcp-registry-(\d{4}-\d{2}-\d{2})(?:-(\d{6,20})(?:-\d+)?)?\.json$")
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
MAX_RECORDS = 100_000


def load(path: Path) -> dict:
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise RuntimeError(f"Snapshot too large to compare safely: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Snapshot root must be an object: {path.name}")
    return value


def stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def snapshot_parts(path: Path) -> tuple[str, str]:
    match = SNAPSHOT_RE.match(path.name)
    if not match:
        raise ValueError(f"Unexpected snapshot filename: {path.name}")
    return match.group(1), match.group(2) or "000000"


def unwrap_record(item: dict) -> dict:
    for key in ("server", "record", "item"):
        nested = item.get(key)
        if isinstance(nested, dict):
            return nested
    return item


def key_for(item: dict) -> str:
    record = unwrap_record(item)
    for key in ("name", "id", "slug", "server_name", "serverName"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    # Last-resort identity is a hash, not a huge attacker-controlled key.
    return "anon:" + sha256_text(stable_json(record))


def version_of(item: dict):
    record = unwrap_record(item)
    for key in ("version", "currentVersion", "latestVersion"):
        if key in record:
            return record.get(key)
    return None


def official_meta(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    for node in (item, unwrap_record(item)):
        meta = node.get("_meta") if isinstance(node, dict) else None
        if isinstance(meta, dict):
            official = meta.get("io.modelcontextprotocol.registry/official")
            if isinstance(official, dict):
                return official
    return {}


def status_of(item: dict):
    meta = official_meta(item)
    for key in ("status", "state"):
        if key in meta:
            return meta.get(key)
    record = unwrap_record(item)
    for key in ("status", "state"):
        if key in record:
            return record.get(key)
    return None


def snapshot_items(snapshot: dict) -> list:
    data = snapshot.get("data")
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("servers"), list):
        items = data["servers"]
    else:
        raise ValueError("Unsupported snapshot schema: expected data[] or data.servers[].")
    if len(items) > MAX_RECORDS:
        raise RuntimeError(f"Snapshot record ceiling exceeded: {len(items)} > {MAX_RECORDS}")
    return items


def index(items):
    out = {}
    for x in items:
        if not isinstance(x, dict):
            continue
        key = key_for(x)
        # Keep first occurrence to make duplicate upstream identities explicit/stable.
        out.setdefault(key, x)
    return out


def compare(old: dict, new: dict, old_file: Path, new_file: Path) -> dict:
    old_items, new_items = snapshot_items(old), snapshot_items(new)
    a, b = index(old_items), index(new_items)
    ak, bk = set(a), set(b)
    added_keys, removed_keys = sorted(bk-ak), sorted(ak-bk)
    version_changes, status_changes, content_changes = [], [], []
    for name in sorted(ak & bk):
        before, after = a[name], b[name]
        ov, nv = version_of(before), version_of(after)
        os, ns = status_of(before), status_of(after)
        if ov != nv: version_changes.append({"name": name, "before": ov, "after": nv})
        if os != ns: status_changes.append({"name": name, "before": os, "after": ns})
        before_json, after_json = stable_json(before), stable_json(after)
        if before_json != after_json:
            content_changes.append({"name":name,"before_hash":sha256_text(before_json),"after_hash":sha256_text(after_json)})
    return {
        "schema_version":"2.2","generated_at":datetime.now(timezone.utc).isoformat(),
        "old_snapshot":old_file.name,"new_snapshot":new_file.name,
        "old_collected_at":old.get("collected_at"),"new_collected_at":new.get("collected_at"),
        "summary":{"old_records":len(old_items),"new_records":len(new_items),"added":len(added_keys),"removed":len(removed_keys),"version_changes":len(version_changes),"status_changes":len(status_changes),"content_changes":len(content_changes)},
        "added":[{"name":n,"record":b[n]} for n in added_keys],
        "removed":[{"name":n,"last_record":a[n]} for n in removed_keys],
        "version_changes":version_changes,"status_changes":status_changes,"content_changes":content_changes,
    }


def latest_per_day() -> list[Path]:
    candidates=[p for p in SNAPSHOT_DIR.glob("mcp-registry-*.json") if SNAPSHOT_RE.match(p.name)]
    by_day={}
    for p in candidates:
        day, stamp=snapshot_parts(p)
        current=by_day.get(day)
        if current is None or snapshot_parts(current)[1] < stamp:
            by_day[day]=p
    return [by_day[d] for d in sorted(by_day)]


def main():
    files=latest_per_day()
    if len(files)<2:
        print("Not enough distinct-date snapshots to compare yet."); return
    old,new=files[-2],files[-1]
    old_day,_=snapshot_parts(old); new_day,_=snapshot_parts(new)
    if old_day>=new_day: raise RuntimeError(f"Invalid snapshot order: {old.name} -> {new.name}")
    result=compare(load(old),load(new),old,new)
    CHANGE_DIR.mkdir(parents=True,exist_ok=True)
    out=CHANGE_DIR/f"changes-{new_day}.json"
    if out.exists():
        existing=load(out)
        if existing.get("old_snapshot")==old.name and existing.get("new_snapshot")==new.name:
            print(f"Comparison already exists for {old.name} -> {new.name}: {out}"); return
        print(f"Historical comparison already exists at {out}; preserving it unchanged. No duplicate comparison was written."); return
    temp=out.with_suffix(out.suffix+".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); temp.replace(out)
    s=result["summary"]
    print(f"Compared {old.name} -> {new.name}\nComparison saved to {out}: {s['added']} added, {s['removed']} removed, {s['version_changes']} version changes, {s['status_changes']} status changes, {s['content_changes']} content changes.")

if __name__=="__main__": main()
