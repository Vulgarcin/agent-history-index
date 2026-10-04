"""AHI tamper-evident evidence log with mutation/deletion protection."""
from __future__ import annotations

import base64
import csv
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
TRACK_DIRS = (DATA / "snapshots", DATA / "changes")
EVENTS = DATA / "events.csv"
IMMUTABLE_PREFIXES = ("data/snapshots/", "data/changes/", "data/events.csv#event:")
ZERO_HASH = "0" * 64
MAX_LEDGER_BYTES = 128 * 1024 * 1024
MAX_EVENTS_BYTES = 10 * 1024 * 1024
MAX_EVENT_ROWS = 100_000


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
        if target.is_dir():
            yield from sorted(p for p in target.rglob("*") if p.is_file() and p.name != ".gitkeep")


def event_records() -> dict[str, tuple[str, int]]:
    if not EVENTS.exists():
        return {}
    if EVENTS.stat().st_size > MAX_EVENTS_BYTES:
        raise RuntimeError("events.csv exceeds safety limit")
    records = {}
    with EVENTS.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "event_id" not in reader.fieldnames:
            raise RuntimeError("events.csv must contain event_id")
        for row_number, row in enumerate(reader, 1):
            if row_number > MAX_EVENT_ROWS:
                raise RuntimeError("events.csv row ceiling exceeded")
            event_id = (row.get("event_id") or "").strip()
            if not event_id or len(event_id) > 160:
                raise RuntimeError(f"Invalid event_id at CSV row {row_number}")
            if event_id in records:
                raise RuntimeError(f"Duplicate event_id: {event_id}")
            normalized = {str(k): "" if v is None else str(v) for k, v in row.items()}
            material = canonical(normalized)
            records[event_id] = (sha256_bytes(material), len(material))
    return records


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    if LEDGER.stat().st_size > MAX_LEDGER_BYTES:
        raise RuntimeError("Evidence ledger exceeds configured safety limit")
    out = []
    for lineno, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid evidence JSON at line {lineno}") from exc
        if not isinstance(entry, dict):
            raise RuntimeError(f"Evidence entry {lineno} is not an object")
        out.append(entry)
    return out


def verify_chain(entries: list[dict]) -> None:
    previous = ZERO_HASH
    for idx, entry in enumerate(entries):
        if entry.get("previous_entry_hash") != previous:
            raise RuntimeError(f"Evidence chain broken at entry {idx}")
        material = dict(entry)
        actual = material.pop("entry_hash", None)
        expected = sha256_bytes(canonical(material))
        if actual != expected or not isinstance(actual, str) or len(actual) != 64:
            raise RuntimeError(f"Evidence entry hash mismatch at entry {idx}")
        previous = actual


def is_immutable_path(rel: str) -> bool:
    return rel.startswith(IMMUTABLE_PREFIXES)


def immutable_history(entries: list[dict]) -> dict[str, str]:
    history = {}
    for entry in entries:
        rel, digest = entry.get("artifact_path"), entry.get("artifact_sha256")
        if not isinstance(rel, str) or not isinstance(digest, str) or not is_immutable_path(rel):
            continue
        previous = history.setdefault(rel, digest)
        if previous != digest:
            raise RuntimeError(f"Ledger contains conflicting hashes for immutable evidence: {rel}")
    return history


def assert_no_historical_mutation_or_deletion(entries: list[dict], current: dict[str, str]) -> None:
    history = immutable_history(entries)
    for rel, old_digest in history.items():
        if rel not in current:
            raise RuntimeError(f"HISTORICAL_DELETION: immutable evidence missing: {rel}")
        if current[rel] != old_digest:
            raise RuntimeError(f"HISTORICAL_MUTATION: immutable evidence changed in place: {rel}")


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
        raw = base64.b64decode(key_b64, validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
    except Exception as exc:
        raise RuntimeError("Invalid Ed25519 signing configuration") from exc
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "algorithm": "Ed25519",
        "public_key_b64": base64.b64encode(public_key).decode(),
        "signature_b64": base64.b64encode(private_key.sign(message)).decode(),
    }


def verify_existing_checkpoints(expected_public_key_b64: str | None = None) -> None:
    files = sorted(CHECKPOINT_DIR.glob("checkpoint-*.json"))
    previous_file = None
    for path in files:
        try:
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Invalid checkpoint JSON: {path.name}") from exc
        if not isinstance(checkpoint, dict):
            raise RuntimeError(f"Checkpoint is not an object: {path.name}")
        if checkpoint.get("schema_version") == "1.1" and previous_file is not None:
            if checkpoint.get("previous_checkpoint_sha256") != sha256_file(previous_file):
                raise RuntimeError(f"CHECKPOINT_CHAIN_BROKEN: {path.name}")
        signature = checkpoint.get("signature")
        if signature:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                pub_b64 = signature["public_key_b64"]
                if expected_public_key_b64 and pub_b64 != expected_public_key_b64:
                    raise RuntimeError(f"Unexpected checkpoint signing key: {path.name}")
                key = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64, validate=True))
                unsigned = dict(checkpoint); unsigned.pop("signature", None)
                key.verify(base64.b64decode(signature["signature_b64"], validate=True), canonical(unsigned))
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Invalid checkpoint signature: {path.name}") from exc
        previous_file = path


def make_entry(rel: str, digest: str, size: int, previous_entry_hash: str) -> dict:
    entry = {
        "schema_version": "1.2",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "artifact_path": rel,
        "artifact_sha256": digest,
        "artifact_size": size,
        "previous_entry_hash": previous_entry_hash,
    }
    entry["entry_hash"] = sha256_bytes(canonical(entry))
    return entry


def main() -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    entries = read_ledger()
    verify_chain(entries)
    expected_public_key = os.getenv("AHI_SIGNING_PUBLIC_KEY_B64")
    verify_existing_checkpoints(expected_public_key)

    candidates: dict[str, tuple[str, int]] = {}
    for path in iter_artifacts():
        rel = path.relative_to(ROOT).as_posix()
        candidates[rel] = (sha256_file(path), path.stat().st_size)
    for event_id, (digest, size) in event_records().items():
        candidates[f"data/events.csv#event:{event_id}"] = (digest, size)

    current_hashes = {rel: digest for rel, (digest, _) in candidates.items()}
    assert_no_historical_mutation_or_deletion(entries, current_hashes)

    known_pairs = {(e.get("artifact_path"), e.get("artifact_sha256")) for e in entries}
    previous_entry_hash = entries[-1]["entry_hash"] if entries else ZERO_HASH
    new_entries = []
    for rel in sorted(candidates):
        digest, size = candidates[rel]
        if (rel, digest) in known_pairs:
            continue
        entry = make_entry(rel, digest, size, previous_entry_hash)
        new_entries.append(entry)
        previous_entry_hash = entry["entry_hash"]

    if new_entries:
        with LEDGER.open("a", encoding="utf-8", newline="\n") as fh:
            for entry in new_entries:
                fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush(); os.fsync(fh.fileno())

    all_entries = entries + new_entries
    verify_chain(all_entries)
    leaves = [e["entry_hash"] for e in all_entries]
    root_hash = merkle_root(leaves)
    now = datetime.now(timezone.utc)
    previous_checkpoints = sorted(CHECKPOINT_DIR.glob("checkpoint-*.json"))
    previous_checkpoint_hash = sha256_file(previous_checkpoints[-1]) if previous_checkpoints else ZERO_HASH
    checkpoint = {
        "schema_version": "1.1",
        "generated_at": now.isoformat(),
        "tree_size": len(leaves),
        "merkle_root_sha256": root_hash,
        "latest_entry_hash": leaves[-1] if leaves else ZERO_HASH,
        "new_entries": len(new_entries),
        "previous_checkpoint_sha256": previous_checkpoint_hash,
        "repository_commit": os.getenv("GITHUB_SHA"),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
    }
    signature = optional_sign(canonical(checkpoint))
    require_signing = os.getenv("AHI_REQUIRE_SIGNING", "0") == "1"
    if require_signing and not signature:
        raise RuntimeError("Signing is required but AHI_SIGNING_KEY_B64 is not configured")
    if signature:
        if expected_public_key and signature["public_key_b64"] != expected_public_key:
            raise RuntimeError("Configured signing key does not match AHI_SIGNING_PUBLIC_KEY_B64")
        checkpoint["signature"] = signature

    out = CHECKPOINT_DIR / now.strftime("checkpoint-%Y-%m-%dT%H%M%S%fZ.json")
    temp = out.with_suffix(out.suffix + ".tmp")
    temp.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(out)
    print(f"Integrity checkpoint: {out} | tree_size={len(leaves)} | new={len(new_entries)} | root={root_hash}")


if __name__ == "__main__":
    main()
