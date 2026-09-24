from pathlib import Path
from datetime import datetime

SNAPSHOT_DIR = Path("data/snapshots")
CHANGES_DIR = Path("data/changes")

snapshot_files = sorted(SNAPSHOT_DIR.glob("mcp-registry-*.json"))

if len(snapshot_files) < 2:
    print("Not enough snapshots to evaluate cleanup.")
    raise SystemExit(0)

latest_snapshot = snapshot_files[-1]

print(f"Latest snapshot protected: {latest_snapshot.name}")
print()

for index, snapshot in enumerate(snapshot_files):

    # Nunca borrar el snapshot más reciente
    if snapshot == latest_snapshot:
        print(f"KEEP latest: {snapshot.name}")
        continue

    date_text = snapshot.stem.replace("mcp-registry-", "")

    try:
        snapshot_date = datetime.strptime(
            date_text,
            "%Y-%m-%d"
        )
    except ValueError:
        print(f"KEEP invalid date format: {snapshot.name}")
        continue

    # Si no existe un snapshot posterior, no podemos comprobar
    # que este ya haya sido comparado correctamente.
    if index + 1 >= len(snapshot_files):
        print(f"KEEP no newer snapshot: {snapshot.name}")
        continue

    next_snapshot = snapshot_files[index + 1]

    next_date_text = next_snapshot.stem.replace(
        "mcp-registry-",
        ""
    )

    comparison_file = (
        CHANGES_DIR /
        f"changes-{next_date_text}.json"
    )

    # Nunca borrar si no existe la comparación
    # entre este snapshot y el siguiente.
    if not comparison_file.exists():
        print(
            f"KEEP no comparison found: "
            f"{snapshot.name}"
        )
        continue

    # Guardar domingos como checkpoint semanal.
    if snapshot_date.weekday() == 6:
        print(
            f"KEEP weekly checkpoint: "
            f"{snapshot.name}"
        )
        continue

    # Guardar primer día del mes como checkpoint mensual.
    if snapshot_date.day == 1:
        print(
            f"KEEP monthly checkpoint: "
            f"{snapshot.name}"
        )
        continue

    snapshot.unlink()

    print(
        f"DELETED: {snapshot.name} "
        f"(comparison exists: {comparison_file.name})"
    )

print()
print("Cleanup complete.")
