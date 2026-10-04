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
USER_AGENT = "Agent-History-Index/0.5 (+https://github.com/Vulgarcin/agent-history-index)"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_RECORDS = 100_000
MAX_CURSOR_LENGTH = 4096
MAX_RECORD_BYTES = 1024 * 1024
MAX_TOTAL_SERIALIZED_BYTES = 512 * 1024 * 1024


def _read_bounded(response, limit: int) -> bytes:
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > limit:
                raise RuntimeError(f"Response too large: Content-Length={declared} > {limit}")
        except ValueError:
            pass
    data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"Response exceeded {limit} byte safety limit")
    return data


def fetch_json(url: str) -> dict:
    """Fetch JSON with retry, content-type checking and bounded response size."""
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type and "json" not in content_type:
                    raise RuntimeError(f"Unexpected content type: {content_type}")
                raw = _read_bounded(response, MAX_PAGE_BYTES)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("Registry returned invalid UTF-8/JSON") from exc
                if not isinstance(payload, dict):
                    raise RuntimeError("Registry response root must be a JSON object")
                return payload
        except urllib.error.HTTPError as exc:
            retryable = exc.code in RETRYABLE_HTTP
            if not retryable or attempt == MAX_RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else None
            except (TypeError, ValueError):
                delay = None
            if delay is None or delay < 0 or delay > 120:
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
        if len(cursor) > MAX_CURSOR_LENGTH:
            raise RuntimeError("Cursor exceeds safety limit")
        params["cursor"] = cursor
    return f"{API_BASE}?{urllib.parse.urlencode(params)}"


def extract_items(payload: dict) -> list:
    for key in ("servers", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("servers", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def extract_cursor(payload: dict) -> str | None:
    containers = [payload, payload.get("pagination", {}), payload.get("metadata", {})]
    data = payload.get("data")
    if isinstance(data, dict):
        containers.extend([data, data.get("pagination", {}), data.get("metadata", {})])
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ("next_cursor", "nextCursor", "cursor"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                value = value.strip()
                if len(value) > MAX_CURSOR_LENGTH:
                    raise RuntimeError("Registry cursor exceeds safety limit")
                return value
    return None


def collect() -> dict:
    items: list = []
    cursor: str | None = None
    seen: set[str] = set()
    started_at = datetime.now(timezone.utc)
    total_serialized_bytes = 0

    for page in range(1, MAX_PAGES + 1):
        payload = fetch_json(build_url(cursor))
        page_items = extract_items(payload)
        if len(page_items) > PAGE_LIMIT * 5:
            raise RuntimeError(f"Unexpectedly large page: {len(page_items)} records")
        for record in page_items:
            record_size = len(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if record_size > MAX_RECORD_BYTES:
                raise RuntimeError(f"Registry record exceeds {MAX_RECORD_BYTES} byte safety limit")
            total_serialized_bytes += record_size
        if total_serialized_bytes > MAX_TOTAL_SERIALIZED_BYTES:
            raise RuntimeError("Snapshot serialized-size ceiling exceeded")
        items.extend(page_items)
        if len(items) > MAX_TOTAL_RECORDS:
            raise RuntimeError(f"Record ceiling exceeded: {len(items)} > {MAX_TOTAL_RECORDS}")
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
        "schema_version": "1.1",
        "source": "MCP Registry",
        "source_url": API_BASE,
        "collector": "ahi-mcp-registry",
        "collector_version": "0.5",
        "collection_started_at": started_at.isoformat(),
        "collected_at": finished_at.isoformat(),
        "record_count": len(items),
        "data": items,
    }


def _next_available_path(date: str) -> Path:
    base = OUTPUT_DIR / f"mcp-registry-{date}.json"
    if not base.exists():
        return base
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
    candidate = OUTPUT_DIR / f"mcp-registry-{date}-{stamp}.json"
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = OUTPUT_DIR / f"mcp-registry-{date}-{stamp}-{counter}.json"
    return candidate


def save_snapshot(snapshot: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    base = OUTPUT_DIR / f"mcp-registry-{date}.json"

    if base.exists():
        try:
            existing = json.loads(base.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if existing == snapshot:
            print(f"[save] identical snapshot already exists: {base}")
            return base

    path = _next_available_path(date)
    rendered = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    temp.replace(path)
    print(f"[save] snapshot saved to {path} ({path.stat().st_size} bytes)")
    return path


if __name__ == "__main__":
    save_snapshot(collect())
