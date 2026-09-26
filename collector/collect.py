import json
import urllib.request
import urllib.parse
import time
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://registry.modelcontextprotocol.io/v0.1/servers"
LIMIT = 100
MAX_PAGES = 500

OUTPUT_DIR = Path("data/snapshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
output_file = OUTPUT_DIR / f"mcp-registry-{today}.json"

headers = {"User-Agent": "Agent-History-Index/0.1"}

all_servers = []
cursor = None
seen_cursors = set()
pages_fetched = 0

while True:
    params = {
        "limit": LIMIT,
        "version": "latest",
    }

    if cursor:
        params["cursor"] = cursor

    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(request, timeout=60) as response:
        page = json.load(response)

    servers = page.get("servers", [])
    all_servers.extend(servers)
    pages_fetched += 1

    next_cursor = page.get("metadata", {}).get("nextCursor")

    print(
        f"Page {pages_fetched}: "
        f"{len(servers)} servers, "
        f"nextCursor={next_cursor!r}"
    )

    if not next_cursor:
        break

    if next_cursor in seen_cursors:
        raise RuntimeError(
            f"Pagination cursor repeated: {next_cursor!r}"
        )

    seen_cursors.add(next_cursor)
    cursor = next_cursor

    if pages_fetched >= MAX_PAGES:
        raise RuntimeError(
            f"Stopped after {MAX_PAGES} pages."
        )

snapshot = {
    "source": "Official MCP Registry",
    "source_url": f"{API_BASE}?limit={LIMIT}&version=latest",
    "collected_at": datetime.now(timezone.utc).isoformat(),
    "data": {
        "servers": all_servers,
        "metadata": {
            "count": len(all_servers),
            "pages_fetched": pages_fetched,
            "complete": True,
        },
    },
}
with output_file.open("w", encoding="utf-8") as file:
    json.dump(snapshot, file, ensure_ascii=False, indent=2)

print(f"Snapshot saved to {output_file}")
page = None

for attempt in range(1, 6):
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            page = json.load(response)

        break

    except Exception as error:
        print(
            f"Request failed on attempt {attempt}/3: "
            f"{error}"
        )

        if attempt == 3:
            raise

        time.sleep(5 * attempt)
