from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://registry.modelcontextprotocol.io/v0.1/servers"
MAX_PAGES = 1000
PAGE_LIMIT = 100
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "snapshots"
USER_AGENT = "Agent-History-Index/0.4 (+https://github.com/Vulgarcin/agent-history-index)"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def fetch_json(url: str) -> dict:
    """Fetch JSON with bounded exponential backoff.

    A failed page is retried at the same cursor. The collector never writes a
    partial snapshot: save_snapshot() is called only after collect() completes.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in RETRYABLE_HTTP
            if not retryable or attempt == MAX_RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else None
            except (TypeError, ValueError):
                delay = None
            if delay is None:
                delay = min(30.0, (2 ** (attempt - 1)) + random.random())
            print(f"[retry] HTTP {exc.code}; attempt={attempt}/{MAX_RETRIES}; sleep={delay:.1f}s")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == MAX_RETRIES:
                raise
            delay = min(30.0, (2 ** (attempt - 1)) + random.random())
            print(f"[retry] network error={exc}; attempt={attempt}/{MAX_RETRIES}; sleep={delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError("unreachable")


def build_url(cursor: str | None = None) -> str:
    params = {"limit": PAGE_LIMIT, "version": "latest"}
    if cursor:
        params["cursor"] = cursor
    return f"{API_BASE}?{urllib.parse.urlencode(params)}"


def extract_items(payload: dict) -> list:
    for key in ("servers", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def extract_cursor(payload: dict) -> str | None:
    for container in (payload, payload.get("pagination", {}), payload.get("metadata", {})):
        if not isinstance(container, dict):
            continue
        for key in ("next_cursor", "nextCursor", "cursor"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def collect() -> dict:
    items: list = []
    cursor: str | None = None
    seen: set[str] = set()
    started_at = datetime.now(timezone.utc)

    for page in range(1, MAX_PAGES + 1):
        url = build_url(cursor)
        payload = fetch_json(url)
        page_items = extract_items(payload)
        items.extend(page_items)
        next_cursor = extract_cursor(payload)
        print(f"Page {page}: {len(page_items)} servers, nextCursor={next_cursor!r}")

        if not next_cursor:
            break
        if next_cursor in seen:
            raise RuntimeError(f"Repeated cursor detected: {next_cursor!r}")
        seen.add(next_cursor)
        cursor = next_cursor
        time.sleep(0.15)
    else:
        raise RuntimeError(f"MAX_PAGES={MAX_PAGES} reached before pagination ended")

    finished_at = datetime.now(timezone.utc)
    return {
        "schema_version": "1.0",
        "source": "MCP Registry",
        "source_url": API_BASE,
        "collector": "ahi-mcp-registry",
        "collector_version": "0.4",
        "collection_started_at": started_at.isoformat(),
        "collected_at": finished_at.isoformat(),
        "record_count": len(items),
        "data": items,
    }


def save_snapshot(snapshot: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    path = OUTPUT_DIR / f"mcp-registry-{date}.json"

    # Never silently overwrite historical evidence.
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == snapshot:
            print(f"[save] identical snapshot already exists: {path}")
            return path
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        path = OUTPUT_DIR / f"mcp-registry-{date}-{stamp}.json"

    path.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[save] snapshot saved to {path} ({path.stat().st_size} bytes)")
    return path


if __name__ == "__main__":
    save_snapshot(collect())
