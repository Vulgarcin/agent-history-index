from pathlib import Path
from datetime import datetime

SNAPSHOT_DIR = Path("data/snapshots")
CHANGES_DIR = Path("data/changes")

PROTECTED_BASELINE = "mcp-registry-2026-09-22.json"

snapshot_files = sorted(SNAPSHOT_DIR.glob("mcp-registry-*.json"))

if len(snapshot_files) < 2:
    print("Not enough snapshots to evaluate cleanup.")
    raise SystemExit(0)

latest_snapshot = snapshot_files[-1]

print(f"Latest snapshot protected: {latest_snapshot.name}")
print(f"Baseline protected: {PROTECTED_BASELINE}")
print()

for snapshot in snapshot_files:
    if snapshot.name == PROTECTED_BASELINE:
        print(f"KEEP baseline: {snapshot.name}")
        continue

    if snapshot == latest_snapshot:
        print(f"KEEP latest: {snapshot.name}")
        continue

    date_text = snapshot.stem.replace("mcp-registry-", "")
    change_file = CHANGES_DIR / f"changes-{date_text}.json"

    if not change_file.exists():
        print(
            f"KEEP no comparison found: "
            f"{snapshot.name}"
        )
        continue

    try:
        snapshot_date = datetime.strptime(
            date_text,
            "%Y-%m-%d"
        )
    except ValueError:
        print(
            f"KEEP invalid date format: "
            f"{snapshot.name}"
        )
        continue

    # Future rule:
    # Sunday snapshots can be kept as weekly checkpoints.
    is_weekly_checkpoint = snapshot_date.weekday() == 6

    # First day of month can be kept as monthly checkpoint.
    is_monthly_checkpoint = snapshot_date.day == 1

    if is_weekly_checkpoint:
        print(f"KEEP weekly checkpoint: {snapshot.name}")
        continue

    if is_monthly_checkpoint:
        print(f"KEEP monthly checkpoint: {snapshot.name}")
        continue

        snapshot.unlink()

    print(
        f"DELETED: {snapshot.name} "
        f"(comparison exists: {change_file.name})"
    )

print()
print("Cleanup complete.")
