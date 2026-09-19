import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = (
    "https://registry.modelcontextprotocol.io/"
    "v0.1/servers?limit=100&version=latest"
)

OUTPUT_DIR = Path("data/snapshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
output_file = OUTPUT_DIR / f"mcp-registry-{today}.json"

request = urllib.request.Request(
    API_URL,
    headers={"User-Agent": "Agent-History-Index/0.1"}
)

with urllib.request.urlopen(request, timeout=30) as response:
    data = json.load(response)

snapshot = {
    "source": "Official MCP Registry",
    "source_url": API_URL,
    "collected_at": datetime.now(timezone.utc).isoformat(),
    "data": data,
}

with output_file.open("w", encoding="utf-8") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

print(f"Snapshot saved to {output_file}")
