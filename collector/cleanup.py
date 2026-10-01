"""AHI historical retention guard.

This script intentionally deletes nothing. It exists as a safety check and reports
how many historical artifacts are being preserved.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count(folder: str, pattern: str) -> int:
    return len(list((ROOT / folder).glob(pattern)))


if __name__ == "__main__":
    snapshots = count("data/snapshots", "mcp-registry-*.json")
    changes = count("data/changes", "changes-*.json")
    checkpoints = count("data/checkpoints", "checkpoint-*.json")
    print(f"Retention policy: preserve all history. snapshots={snapshots}, changes={changes}, checkpoints={checkpoints}")
