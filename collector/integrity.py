"""AHI tamper-evident evidence log.

This module does not claim magical immutability. It provides:
- canonical SHA-256 digests for captured artifacts
- an append-only JSONL evidence ledger
- a hash chain across ledger entries
- Merkle roots/checkpoints for each integrity run
- optional Ed25519 signatures when AHI_SIGNING_KEY_B64 is configured

Corrections are appended as new evidence; historical entries are never rewritten.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LEDGER = DATA / "evidence" / "ledger.jsonl"
CHECKPOINT_DIR = DATA / "checkpoints"
TRACK_DIRS = (DATA / "snapshots", DATA / "changes", DATA / "events.csv")
ZERO_HASH = "0" * 64


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def iter_artifacts() -> Iterable[Path]:
    for target in TRACK_DIRS:
        if target.is_file():
            yield target
        elif target.is_dir():
            yield from sorted(p for p in target.rglob("*") if p.is_file() and p.name != ".gitkeep")


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def verify_chain(entries: list[dict]) -> None:
    previous = ZERO_HASH
    for idx, entry in enumerate(entries):
        if entry.get("previous_entry_hash") != previous:
            raise RuntimeError(f"Evidence chain broken at entry {idx}")
        material = dict(entry)
        actual = material.pop("entry_hash", None)
        expected = sha256_bytes(canonical(material))
        if actual != expected:
            raise RuntimeError(f"Evidence entry hash mismatch at entry {idx}")
        previous = actual


def merkle_root(hex_hashes: list[str]) -> str:
    if not hex_hashes:
        return ZERO_HASH
    level = [bytes.fromhex(h) for h in hex_hashes]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def optional_sign(message: bytes) -> dict | None:
    key_b64 = os.getenv("AHI_SIGNING_KEY_B64")
    if not key_b64:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise RuntimeError("cryptography is required when AHI_SIGNING_KEY_B64 is set") from exc

    raw = base64.b64decode(key_b64)
    private_key = Ed25519PrivateKey.from_private_bytes(raw)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature = private_key.sign(message)
    return {
        "algorithm": "Ed25519",
        "public_key_b64": base64.b64encode(public_key).decode(),
        "signature_b64": base64.b64encode(signature).decode(),
    }


def main() -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    entries = read_ledger()
    verify_chain(entries)
    known_artifact_hashes = {(e.get("artifact_path"), e.get("artifact_sha256")) for e in entries}
    previous_entry_hash = entries[-1]["entry_hash"] if entries else ZERO_HASH
    new_entries = []

    for path in iter_artifacts():
        rel = path.relative_to(ROOT).as_posix()
        artifact_hash = sha256_file(path)
        if (rel, artifact_hash) in known_artifact_hashes:
            continue
        stat = path.stat()
        entry = {
            "schema_version": "1.0",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "artifact_path": rel,
            "artifact_sha256": artifact_hash,
            "artifact_size": stat.st_size,
            "previous_entry_hash": previous_entry_hash,
        }
        entry_hash = sha256_bytes(canonical(entry))
        entry["entry_hash"] = entry_hash
        new_entries.append(entry)
        previous_entry_hash = entry_hash

    if new_entries:
        with LEDGER.open("a", encoding="utf-8", newline="\n") as fh:
            for entry in new_entries:
                fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")

    all_entries = entries + new_entries
    verify_chain(all_entries)
    leaves = [e["entry_hash"] for e in all_entries]
    root_hash = merkle_root(leaves)
    now = datetime.now(timezone.utc)
    checkpoint = {
        "schema_version": "1.0",
        "generated_at": now.isoformat(),
        "tree_size": len(leaves),
        "merkle_root_sha256": root_hash,
        "latest_entry_hash": leaves[-1] if leaves else ZERO_HASH,
        "new_entries": len(new_entries),
    }
    signature = optional_sign(canonical(checkpoint))
    if signature:
        checkpoint["signature"] = signature

    name = now.strftime("checkpoint-%Y-%m-%dT%H%M%SZ.json")
    out = CHECKPOINT_DIR / name
    out.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Integrity checkpoint: {out} | tree_size={len(leaves)} | new={len(new_entries)} | root={root_hash}")


if __name__ == "__main__":
    main()
