from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "public" / "status.json"
WEB_OUT = ROOT / "web" / "data" / "status.json"


def latest(pattern: str, folder: Path):
    files = sorted(folder.glob(pattern), key=lambda p: (p.stat().st_mtime_ns, p.name))
    return files[-1] if files else None


def load(path: Path | None):
    if not path:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    snap_path = latest("mcp-registry-*.json", DATA / "snapshots")
    change_path = latest("changes-*.json", DATA / "changes")
    checkpoint_path = latest("checkpoint-*.json", DATA / "checkpoints")
    snap, change, checkpoint = load(snap_path), load(change_path), load(checkpoint_path)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_snapshot": {
            "date": (snap or {}).get("collected_at"),
            "records": (snap or {}).get("record_count", len((snap or {}).get("data", []))),
            "file": snap_path.name if snap_path else None,
        },
        "latest_changes": (change or {}).get("summary", {}),
        "integrity": {
            "tree_size": (checkpoint or {}).get("tree_size", 0),
            "merkle_root_sha256": (checkpoint or {}).get("merkle_root_sha256"),
            "checkpoint": checkpoint_path.name if checkpoint_path else None,
            "signed": bool((checkpoint or {}).get("signature")),
        },
        "principles": {
            "historical_deletion": False,
            "append_only_evidence": True,
            "source_traceability": True,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    OUT.write_text(rendered, encoding="utf-8")
    WEB_OUT.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUT.write_text(rendered, encoding="utf-8")
    print(f"Public status written to {OUT} and {WEB_OUT}")


if __name__ == "__main__":
    main()
