from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "public" / "status.json"
WEB_OUT = ROOT / "web" / "data" / "status.json"
CATALOG_OUT = DATA / "public" / "catalog.json"
WEB_CATALOG_OUT = ROOT / "web" / "data" / "catalog.json"
PRO_OUT = DATA / "public" / "pro.json"
WEB_PRO_OUT = ROOT / "web" / "data" / "pro.json"
HISTORY_OUT = DATA / "public" / "history.json"
WEB_HISTORY_OUT = ROOT / "web" / "data" / "history.json"
ENTITY_SEED_DIR = DATA / "entities"
MAX_SEED_FILES = 1000
MAX_SEED_BYTES = 256 * 1024
MARKET_OUT = DATA / "public" / "market.json"
WEB_MARKET_OUT = ROOT / "web" / "data" / "market.json"
SNAP_RE = re.compile(r"^mcp-registry-(\d{4}-\d{2}-\d{2})(?:-(\d{6}))?\.json$")
OFFICIAL_META = "io.modelcontextprotocol.registry/official"
MAX_TEXT = 5000
MAX_URL = 2048
MAX_ENTITIES = 100000
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
MAX_EVENTS_BYTES = 10 * 1024 * 1024
MAX_EVENT_ROWS = 100000
MAX_CHANGE_FILES = 4000
MAX_ENTITY_EVENTS = 200
MAX_EXTERNAL_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_EXTERNAL_RECORDS = 250000
MAX_ENTITY_EVIDENCE_OBSERVATIONS = 365


def snapshot_key(path: Path):
    m = SNAP_RE.match(path.name)
    return (m.group(1), m.group(2) or "000000", path.name) if m else ("0000-00-00", "000000", path.name)


def latest(pattern: str, folder: Path):
    files = list(folder.glob(pattern))
    if folder.name == "snapshots":
        files = [p for p in files if SNAP_RE.match(p.name)]
        files.sort(key=snapshot_key)
    else:
        files.sort(key=lambda p: (p.stat().st_mtime_ns, p.name))
    return files[-1] if files else None


def load(path: Path | None):
    if not path:
        return None
    try:
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise RuntimeError(f"Refusing oversized JSON input: {path.name}")
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except RuntimeError:
        raise
    except Exception:
        return None


def snapshot_items(snapshot):
    if not isinstance(snapshot, dict):
        return []
    data = snapshot.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("servers", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def server_record(item):
    if not isinstance(item, dict):
        return {}
    for key in ("server", "record", "item"):
        if isinstance(item.get(key), dict):
            return item[key]
    return item


def official_meta(item):
    """Find official Registry metadata without assuming only one historical response shape."""
    if not isinstance(item, dict):
        return {}
    queue = [item]
    seen = set()
    while queue:
        node = queue.pop(0)
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict):
            if OFFICIAL_META in node and isinstance(node[OFFICIAL_META], dict):
                return node[OFFICIAL_META]
            meta = node.get("_meta")
            if isinstance(meta, dict) and isinstance(meta.get(OFFICIAL_META), dict):
                return meta[OFFICIAL_META]
            for key, value in node.items():
                if key in ("server", "record", "item", "data", "metadata", "_meta") and isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(node, list):
            queue.extend(x for x in node if isinstance(x, (dict, list)))
    return {}


def first_text(record, keys, max_len=MAX_TEXT):
    if not isinstance(record, dict):
        return None
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:max_len]
    return None

def safe_public_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()[:MAX_URL]
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme.lower() != "https" or not parsed.netloc or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if any(ord(ch) < 32 for ch in value) or "\\" in value:
        return None
    return parsed.geturl()


def entity_name(item):
    return first_text(server_record(item), ("name", "id", "slug", "serverName", "server_name"))


def entity_version(item):
    return first_text(server_record(item), ("version", "currentVersion", "latestVersion"))


def normalize_status(value):
    if not isinstance(value, str):
        return "unknown"
    value = value.strip().lower().replace(" ", "_")
    aliases = {
        "active": "active", "deprecated": "deprecated", "deleted": "deleted",
        "retired": "retired", "degraded": "degraded", "compromised": "compromised",
        "forked": "forked"
    }
    return aliases.get(value, "unknown")


def entity_status(item):
    meta = official_meta(item)
    status = first_text(meta, ("status", "state"))
    if status:
        return normalize_status(status), "MCP Registry official metadata"
    record = server_record(item)
    fallback = first_text(record, ("status", "state"))
    if fallback:
        return normalize_status(fallback), "publisher/server record"
    return "unknown", None


def repository_info(item):
    record = server_record(item)
    repo = record.get("repository")
    if isinstance(repo, str):
        return safe_public_url(repo), None
    if isinstance(repo, dict):
        url = safe_public_url(first_text(repo, ("url", "webUrl", "homepage"), MAX_URL))
        owner = first_text(repo, ("owner", "organization", "publisher"))
        if not owner and url:
            try:
                parsed = urlparse(url)
                parts = [p for p in parsed.path.split("/") if p]
                if (parsed.hostname or "").lower() in {"github.com","www.github.com","gitlab.com","www.gitlab.com"} and parts:
                    owner = parts[0]
            except Exception:
                pass
        return url, owner
    return None, None


def publisher_namespace(name):
    return name.split("/", 1)[0] if name and "/" in name else None


def entity_org(item):
    record = server_record(item)
    direct = first_text(record, ("organization","organisation","publisher","developer","owner","vendor"))
    if direct:
        return direct
    _, owner = repository_info(item)
    return owner


def entity_license(item):
    record = server_record(item)
    value = record.get("license") or record.get("licenseInfo") or record.get("codeLicense")
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return first_text(value, ("name","id","spdx","license","identifier"))
    return None


def package_types(item):
    record = server_record(item)
    packages = record.get("packages")
    out = []
    if isinstance(packages, list):
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            kind = first_text(pkg, ("registryType","registry_type","type"))
            if kind and kind not in out:
                out.append(kind)
    return out[:30]


def package_details(item):
    record = server_record(item)
    packages = record.get("packages")
    out = []
    if not isinstance(packages, list):
        return out
    for pkg in packages[:30]:
        if not isinstance(pkg, dict):
            continue
        registry = first_text(pkg, ("registryType", "registry_type", "type"), 80)
        identifier = first_text(pkg, ("identifier", "name", "package", "packageName"), 500)
        version = first_text(pkg, ("version", "packageVersion"), 200)
        if registry and identifier:
            out.append({"registry_type": registry, "identifier": identifier, "version": version})
    return out


def canonical_record_hash(value):
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def merkle_root_hex(hashes):
    level = [bytes.fromhex(h) for h in hashes if isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)]
    if not level:
        return None
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i+1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


def event_entities():
    """Use AHI's own historical event ledger for entity types already explicitly represented there."""
    path = DATA / "events.csv"
    if not path.exists():
        return []
    if path.stat().st_size > MAX_EVENTS_BYTES:
        raise RuntimeError("events.csv exceeds safety limit")
    out = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row_number, row in enumerate(csv.DictReader(fh), 1):
            if row_number > MAX_EVENT_ROWS:
                raise RuntimeError("events.csv row ceiling exceeded")
            project = (row.get("project") or "").strip()
            if not project:
                continue
            lower = project.lower()
            if "protocol" in lower:
                entity_type = "protocol"
            else:
                # Do not guess that a project is an agent/model/framework merely from its name.
                continue
            event_date = (row.get("event_date") or "").strip() or None
            observed_at = (row.get("observed_at") or "").strip() or event_date
            out.append({
                "name": project,
                "title": project,
                "description": (row.get("summary") or "").strip() or None,
                "entity_type": entity_type,
                "organization": (row.get("organization") or "").strip() or None,
                "repository_owner": None,
                "publisher_namespace": None,
                "status": "unknown",
                "status_source": None,
                "status_message": None,
                "license": None,
                "first_observed": event_date or observed_at,
                "last_observed": observed_at,
                "current_version": None,
                "repository_url": None,
                "website_url": safe_public_url((row.get("source_url") or "").strip()),
                "published_at": event_date,
                "registry_updated_at": None,
                "server_id": None,
                "version_id": None,
                "source": "AHI events.csv",
                "evidence_class": "third_party",
                "years": [int((event_date or observed_at)[:4])] if (event_date or observed_at) and len((event_date or observed_at)) >= 4 else [],
                "versions": [],
                "versions_indexed": 0,
                "package_types": [],
                "market_metrics": {},
            })
    return out


def build_catalog(snapshot_paths):
    entities = {}
    versions = defaultdict(set)
    years = defaultdict(set)
    package_kinds = defaultdict(set)
    packages_by_name = defaultdict(dict)
    evidence_hashes = defaultdict(list)
    evidence_observations = defaultdict(list)

    for path in snapshot_paths:
        match = SNAP_RE.match(path.name)
        if not match:
            continue
        observed_date = match.group(1)
        observed_year = int(observed_date[:4])
        snapshot = load(path)
        if not snapshot:
            continue

        for raw in snapshot_items(snapshot):
            if not isinstance(raw, dict):
                continue
            record = server_record(raw)
            name = entity_name(raw)
            if not name:
                continue
            version = entity_version(raw)
            meta = official_meta(raw)
            status, status_source = entity_status(raw)
            repo_url, repo_owner = repository_info(raw)
            years[name].add(observed_year)
            if version:
                versions[name].add(version)
            for kind in package_types(raw):
                package_kinds[name].add(kind)
            for pkg in package_details(raw):
                key = (pkg.get("registry_type"), pkg.get("identifier"), pkg.get("version"))
                packages_by_name[name][key] = pkg

            # Per-entity evidence is derived from the exact observed server record,
            # not from the global checkpoint summary.
            record_hash = canonical_record_hash(record)
            evidence_hashes[name].append(record_hash)
            if len(evidence_observations[name]) < MAX_ENTITY_EVIDENCE_OBSERVATIONS:
                evidence_observations[name].append({
                    "date": observed_date,
                    "snapshot": path.name,
                    "record_sha256": record_hash,
                    "version": version,
                    "status": status,
                })

            observed = {
                "name": name,
                "title": first_text(record, ("title","displayName","display_name")),
                "description": first_text(record, ("description","summary")),
                "entity_type": "mcp_server",
                "organization": entity_org(raw),
                "repository_owner": repo_owner,
                "publisher_namespace": publisher_namespace(name),
                "status": status,
                "status_source": status_source,
                "status_message": first_text(meta, ("statusMessage","status_message")),
                "license": entity_license(raw),
                "first_observed": observed_date,
                "last_observed": observed_date,
                "current_version": version,
                "repository_url": repo_url,
                "website_url": safe_public_url(first_text(record, ("websiteUrl","website_url","homepage"), MAX_URL)),
                "published_at": first_text(meta, ("publishedAt","published_at")),
                "registry_updated_at": first_text(meta, ("updatedAt","updated_at")),
                "server_id": first_text(meta, ("serverId","server_id","id")),
                "version_id": first_text(meta, ("versionId","version_id")),
                "source": "MCP Registry",
                "evidence_class": "observed",
                "market_metrics": {},
            }

            current = entities.get(name)
            if current is None:
                entities[name] = observed
            else:
                current["last_observed"] = observed_date
                current["status"] = observed["status"]
                current["status_source"] = observed["status_source"]
                for key in (
                    "title","description","organization","repository_owner","publisher_namespace",
                    "status_message","license","current_version","repository_url","website_url",
                    "published_at","registry_updated_at","server_id","version_id"
                ):
                    value = observed.get(key)
                    if value not in (None, ""):
                        current[key] = value

    rows = []
    evidence_index = {}
    for name, row in entities.items():
        row["years"] = sorted(years[name], reverse=True)
        row["versions"] = sorted(versions[name], reverse=True)[:50]
        row["versions_indexed"] = len(versions[name])
        row["package_types"] = sorted(package_kinds[name])
        row["packages"] = list(packages_by_name[name].values())[:30]
        rows.append(row)
        hashes = evidence_hashes.get(name, [])
        observations = evidence_observations.get(name, [])
        evidence_index[name] = {
            "observation_count": len(hashes),
            "distinct_record_hashes": len(set(hashes)),
            "entity_merkle_root_sha256": merkle_root_hex(hashes),
            "latest_record_sha256": hashes[-1] if hashes else None,
            "first_observation": observations[0] if observations else None,
            "latest_observation": observations[-1] if observations else None,
            "observations": observations[-MAX_ENTITY_EVIDENCE_OBSERVATIONS:],
        }

    existing={(r["entity_type"], r["name"]) for r in rows}
    for event_row in event_entities():
        key=(event_row["entity_type"], event_row["name"])
        if key not in existing:
            rows.append(event_row)
            existing.add(key)
            evidence_index.setdefault(event_row["name"], {
                "observation_count": 1,
                "distinct_record_hashes": 1,
                "entity_merkle_root_sha256": canonical_record_hash(event_row),
                "latest_record_sha256": canonical_record_hash(event_row),
                "first_observation": {"date": event_row.get("first_observed"), "snapshot": "events.csv", "record_sha256": canonical_record_hash(event_row), "version": None, "status": event_row.get("status")},
                "latest_observation": {"date": event_row.get("last_observed"), "snapshot": "events.csv", "record_sha256": canonical_record_hash(event_row), "version": None, "status": event_row.get("status")},
                "observations": [{"date": event_row.get("last_observed"), "snapshot": "events.csv", "record_sha256": canonical_record_hash(event_row), "version": None, "status": event_row.get("status")}],
            })

    rows.sort(key=lambda x: (x.get("title") or x["name"]).lower())
    if len(rows) > MAX_ENTITIES:
        raise RuntimeError(f"Catalog entity ceiling exceeded: {len(rows)} > {MAX_ENTITIES}")
    type_counts=Counter(r.get("entity_type","unknown") for r in rows)
    status_counts=Counter(r.get("status","unknown") for r in rows)

    catalog = {
        "schema_version": "1.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(rows),
        "type_counts": dict(type_counts),
        "status_counts": dict(status_counts),
        "source_coverage": {
            "mcp_server": "MCP Registry snapshots",
            "protocol": "AHI historical events (partial)",
            "agent": None,
            "model": None,
            "framework": None
        },
        "note": "Missing categories are shown as integration gaps rather than fabricated data. External enrichments remain source-attributed and separate from native AHI observations.",
        "entities": rows,
    }
    return catalog, evidence_index



def load_seed_entities():
    """Load curated, source-attributed entity seeds from data/entities/**/*.json.

    Seeds are discovery records, not retroactive AHI observations. Unknown fields
    remain null until a collector or verified source fills them.
    """
    rows = []
    if not ENTITY_SEED_DIR.exists():
        return rows
    paths = sorted(ENTITY_SEED_DIR.rglob("*.json"))
    if len(paths) > MAX_SEED_FILES:
        raise RuntimeError("Entity seed file ceiling exceeded")
    for path in paths:
        if path.is_symlink():
            raise RuntimeError(f"Refusing symlinked entity seed: {path}")
        if path.stat().st_size > MAX_SEED_BYTES:
            raise RuntimeError(f"Entity seed exceeds safety limit: {path.name}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        name = first_text(raw, ("name", "title"), 300)
        entity_type = first_text(raw, ("entity_type",), 80)
        if not name or not entity_type:
            continue
        aliases = [str(x).strip()[:200] for x in raw.get("aliases", []) if isinstance(x, str) and x.strip()][:30]
        capabilities = [str(x).strip()[:120] for x in raw.get("capabilities", []) if isinstance(x, str) and x.strip()][:80]
        modalities = [str(x).strip()[:120] for x in raw.get("modalities", []) if isinstance(x, str) and x.strip()][:40]
        protocols = [str(x).strip()[:120] for x in raw.get("protocols", []) if isinstance(x, str) and x.strip()][:40]
        sources = []
        for src in raw.get("sources", []) if isinstance(raw.get("sources"), list) else []:
            if not isinstance(src, dict):
                continue
            url = safe_public_url(src.get("url"))
            if not url:
                continue
            sources.append({
                "label": first_text(src, ("label",), 160) or "Source",
                "url": url,
                "kind": first_text(src, ("kind",), 80) or "reference",
            })
            if len(sources) >= 20:
                break
        official_url = safe_public_url(raw.get("official_url"))
        repository_url = safe_public_url(raw.get("repository_url"))
        rows.append({
            "entity_id": first_text(raw, ("entity_id",), 200) or f"seed:{name}",
            "name": name,
            "title": first_text(raw, ("title",), 300) or name,
            "aliases": aliases,
            "description": first_text(raw, ("description",), MAX_TEXT),
            "entity_type": entity_type,
            "category": first_text(raw, ("category",), 120),
            "organization": first_text(raw, ("organization",), 300),
            "repository_owner": None,
            "publisher_namespace": None,
            "status": normalize_status(first_text(raw, ("status",), 80) or "unknown"),
            "status_source": "curated official-source seed",
            "status_message": None,
            "license": first_text(raw, ("license",), 200),
            "first_observed": None,
            "last_observed": None,
            "current_version": first_text(raw, ("current_version",), 200),
            "repository_url": repository_url,
            "website_url": official_url,
            "official_url": official_url,
            "published_at": first_text(raw, ("launch_date",), 80),
            "registry_updated_at": None,
            "server_id": None,
            "version_id": None,
            "source": first_text(raw, ("source",), 200) or "AHI curated seed",
            "evidence_class": first_text(raw, ("evidence_class",), 80) or "DECLARED_OR_CURATED",
            "verification_state": first_text(raw, ("verification_state",), 80) or "needs_enrichment",
            "pricing_model": first_text(raw, ("pricing_model",), 120),
            "capabilities": capabilities,
            "modalities": modalities,
            "protocols": protocols,
            "sources": sources,
            "years": [],
            "versions": [],
            "versions_indexed": 0,
            "package_types": [],
            "packages": [],
            "market_metrics": {},
        })
    return rows


def merge_seed_entities(catalog, evidence_index):
    existing = {r.get("name") for r in catalog.get("entities", []) if isinstance(r, dict)}
    added = 0
    for row in load_seed_entities():
        name = row.get("name")
        if name in existing:
            continue
        catalog["entities"].append(row)
        evidence_index.setdefault(name, {
            "observation_count": 0,
            "distinct_record_hashes": 0,
            "entity_merkle_root_sha256": None,
            "latest_record_sha256": None,
            "first_observation": None,
            "latest_observation": None,
            "observations": [],
        })
        existing.add(name)
        added += 1
    catalog["entities"].sort(key=lambda x: (x.get("title") or x.get("name") or "").lower())
    catalog["entity_count"] = len(catalog["entities"])
    catalog["type_counts"] = dict(Counter(r.get("entity_type", "unknown") for r in catalog["entities"] if isinstance(r, dict)))
    catalog["status_counts"] = dict(Counter(r.get("status", "unknown") for r in catalog["entities"] if isinstance(r, dict)))
    catalog.setdefault("source_coverage", {})["curated_ai_index"] = f"{added} source-attributed seed entities"
    return added

def load_external_captures():
    captures_dir = DATA / "external" / "captures"
    by_entity = defaultdict(list)
    discovered = {}
    if not captures_dir.exists():
        return by_entity, discovered
    total = 0
    for path in sorted(captures_dir.glob("external-backfill-*.jsonl")):
        if path.stat().st_size > MAX_EXTERNAL_CAPTURE_BYTES:
            raise RuntimeError(f"External capture exceeds safety limit: {path.name}")
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                total += 1
                if total > MAX_EXTERNAL_RECORDS:
                    raise RuntimeError("External evidence record ceiling exceeded")
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                name = rec.get("entity_name")
                if not isinstance(name, str) or not name.strip():
                    continue
                by_entity[name].append(rec)
                if rec.get("source_id") == "huggingface-hub" and rec.get("entity_type") == "model":
                    discovered[name] = rec
    for rows in by_entity.values():
        rows.sort(key=lambda r: (r.get("observed_at") or "", r.get("source_id") or ""))
    return by_entity, discovered


def merge_discovered_external_entities(catalog, discovered):
    existing = {r.get("name") for r in catalog.get("entities", []) if isinstance(r, dict)}
    for name, rec in discovered.items():
        if name in existing:
            continue
        data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
        created = data.get("created_at") or (rec.get("observed_at") or "")[:10]
        modified = data.get("last_modified") or (rec.get("observed_at") or "")[:10]
        year = None
        try:
            year = int(str(created)[:4])
        except Exception:
            pass
        catalog["entities"].append({
            "name": name,
            "title": name,
            "description": None,
            "entity_type": "model",
            "organization": data.get("author"),
            "repository_owner": data.get("author"),
            "publisher_namespace": data.get("author"),
            "status": "unknown",
            "status_source": None,
            "status_message": None,
            "license": data.get("declared_license"),
            "first_observed": (rec.get("observed_at") or "")[:10],
            "last_observed": (rec.get("observed_at") or "")[:10],
            "current_version": None,
            "repository_url": safe_public_url(rec.get("repository_url")),
            "website_url": safe_public_url(rec.get("repository_url")),
            "published_at": created,
            "registry_updated_at": modified,
            "server_id": None,
            "version_id": None,
            "source": "Hugging Face Hub",
            "evidence_class": "OBSERVED_EXTERNAL",
            "years": [year] if year else [],
            "versions": [],
            "versions_indexed": 0,
            "package_types": [],
            "packages": [],
            "market_metrics": {},
        })
        existing.add(name)
    catalog["entities"].sort(key=lambda x: (x.get("title") or x.get("name") or "").lower())
    catalog["entity_count"] = len(catalog["entities"])
    catalog["type_counts"] = dict(Counter(r.get("entity_type", "unknown") for r in catalog["entities"] if isinstance(r, dict)))
    catalog["status_counts"] = dict(Counter(r.get("status", "unknown") for r in catalog["entities"] if isinstance(r, dict)))
    if any(r.get("entity_type") == "model" for r in catalog["entities"] if isinstance(r, dict)):
        catalog.setdefault("source_coverage", {})["model"] = "Hugging Face Hub public metadata (external, source-attributed)"



def change_date(path: Path) -> str | None:
    m = re.match(r"^changes-(\d{4}-\d{2}-\d{2})(?:-\d+)?\.json$", path.name)
    return m.group(1) if m else None


def build_history_products(catalog: dict, checkpoint: dict | None, evidence_index: dict, external_by_entity: dict) -> tuple[dict, dict]:
    """Build compact real historical products from AHI comparison artifacts.

    No financial prices, downloads, ratings or SLA values are invented here.
    """
    changes_dir = DATA / "changes"
    paths = [p for p in changes_dir.glob("changes-*.json") if change_date(p)] if changes_dir.exists() else []
    paths.sort(key=lambda x: (change_date(x) or "", x.name))
    if len(paths) > MAX_CHANGE_FILES:
        paths = paths[-MAX_CHANGE_FILES:]

    entity_events = defaultdict(list)
    daily_entity_scores = defaultdict(lambda: defaultdict(float))
    comparisons = []
    weights = {"added": 8.0, "removed": 8.0, "version": 5.0, "status": 7.0, "content": 2.0}

    def add_event(name, day, kind, payload=None):
        if not isinstance(name, str) or not name.strip():
            return
        name = name.strip()[:500]
        if len(entity_events[name]) < MAX_ENTITY_EVENTS:
            event = {"date": day, "type": kind}
            if isinstance(payload, dict):
                for k in ("before", "after", "before_hash", "after_hash"):
                    if k in payload:
                        val = payload.get(k)
                        event[k] = (str(val)[:500] if val is not None else None)
            entity_events[name].append(event)
        daily_entity_scores[name][day] += weights[kind]

    for path in paths:
        obj = load(path)
        if not obj:
            continue
        day = change_date(path)
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        comparisons.append({
            "date": day,
            "file": path.name,
            "added": int(summary.get("added") or 0),
            "removed": int(summary.get("removed") or 0),
            "version_changes": int(summary.get("version_changes") or 0),
            "status_changes": int(summary.get("status_changes") or 0),
            "content_changes": int(summary.get("content_changes") or 0),
        })
        for item in obj.get("added", []) if isinstance(obj.get("added"), list) else []:
            if isinstance(item, dict): add_event(item.get("name"), day, "added")
        for item in obj.get("removed", []) if isinstance(obj.get("removed"), list) else []:
            if isinstance(item, dict): add_event(item.get("name"), day, "removed")
        for item in obj.get("version_changes", []) if isinstance(obj.get("version_changes"), list) else []:
            if isinstance(item, dict): add_event(item.get("name"), day, "version", item)
        for item in obj.get("status_changes", []) if isinstance(obj.get("status_changes"), list) else []:
            if isinstance(item, dict): add_event(item.get("name"), day, "status", item)
        for item in obj.get("content_changes", []) if isinstance(obj.get("content_changes"), list) else []:
            if isinstance(item, dict): add_event(item.get("name"), day, "content", item)

    rows_by_name = {r.get("name"): r for r in catalog.get("entities", []) if isinstance(r, dict) and isinstance(r.get("name"), str)}
    pro_entities = {}
    all_days = sorted({d for scores in daily_entity_scores.values() for d in scores})
    for name, row in rows_by_name.items():
        events = sorted(entity_events.get(name, []), key=lambda e: (e.get("date") or "", e.get("type") or ""))
        counts = Counter(e.get("type") for e in events)
        external_rows = external_by_entity.get(name, []) if isinstance(external_by_entity, dict) else []
        latest_by_source = {}
        source_history = defaultdict(list)
        for ext in external_rows:
            sid = ext.get("source_id")
            if not isinstance(sid, str):
                continue
            latest_by_source[sid] = ext
            source_history[sid].append(ext)
        pro_entities[name] = {
            "first_observed": row.get("first_observed"),
            "last_observed": row.get("last_observed"),
            "current_version": row.get("current_version"),
            "current_status": row.get("status"),
            "versions": row.get("versions", [])[:50],
            "event_counts": dict(counts),
            "timeline": events[-MAX_ENTITY_EVENTS:],
            "evidence": evidence_index.get(name, {}),
            "external_latest": latest_by_source,
            "external_history_counts": {sid: len(values) for sid, values in source_history.items()},
        }

    market_entities = {}
    # Build an observation calendar from real AHI snapshots/comparisons.  The
    # market chart must represent states observed on dates, not only dates on
    # which a change happened.  Otherwise a perfectly valid entity with one
    # change and four later unchanged observations collapses to a single dot.
    snapshot_days = []
    snapshots_dir = DATA / "snapshots"
    if snapshots_dir.exists():
        snapshot_days = sorted({
            m.group(1)
            for p in snapshots_dir.glob("mcp-registry-*.json")
            if (m := SNAP_RE.match(p.name))
        })
    observation_days = sorted(set(snapshot_days) | set(all_days))

    # Native AHI activity/growth series.  Activity is cumulative observed
    # change weight.  A day with no change keeps the previous value; it is
    # still a genuine observation and therefore produces a chart point.
    for name, row in rows_by_name.items():
        scores = daily_entity_scores.get(name, {})
        first_seen = str(row.get("first_observed") or "")[:10]
        last_seen = str(row.get("last_observed") or "")[:10]
        # Curated discovery seeds are not retroactive AHI observations. They
        # enter the market only after AHI has real observations or attributed
        # external measurements for them.
        if first_seen or last_seen or scores:
            days = [d for d in observation_days if (not first_seen or d >= first_seen) and (not last_seen or d <= last_seen)]
            days = sorted(set(days) | set(scores.keys()))
        else:
            days = []
        running = 0.0
        series = []
        daily_values = []
        for d in days:
            delta = float(scores.get(d, 0.0))
            running += delta
            daily_values.append(delta)
            series.append({"date": d, "activity": round(running, 3), "daily_change": round(delta, 3), "source": "AHI_OBSERVED"})
        total = running
        # Growth is based on the change in cumulative activity over the
        # available observation window; daily deltas remain exposed to the UI.
        growth = (series[-1]["activity"] - series[0]["activity"]) if len(series) > 1 else 0.0

        # External observations are appended over time; they are never rewritten
        # into fake historical values. This lets downloads/stars/security become
        # genuine time series as AHI observes them from now on.
        ext_series = []
        for ext in external_by_entity.get(name, []) if isinstance(external_by_entity, dict) else []:
            data = ext.get("data") if isinstance(ext.get("data"), dict) else {}
            day = str(ext.get("observed_at") or "")[:10]
            if not day:
                continue
            point = {"date": day, "source_id": ext.get("source_id")}
            if ext.get("source_id") == "ecosystems-repos":
                point["stars"] = data.get("stars")
                point["forks"] = data.get("forks")
            elif ext.get("source_id") == "ecosystems-packages":
                point["downloads"] = data.get("downloads")
            elif ext.get("source_id") == "huggingface-hub":
                point["downloads"] = data.get("downloads_all_time") if data.get("downloads_all_time") is not None else data.get("downloads")
                point["likes"] = data.get("likes")
                point["trending_score"] = data.get("trending_score")
            elif ext.get("source_id") == "openssf-scorecard":
                point["security_score"] = data.get("score")
            ext_series.append(point)

        # Collapse same-day external records into one point, preferring latest.
        ext_by_day = {}
        for pt in ext_series:
            day = pt.get("date")
            ext_by_day.setdefault(day, {}).update({k: v for k, v in pt.items() if v is not None})
        external_series = [ext_by_day[d] for d in sorted(ext_by_day)]

        if series or external_series:
            market_entities[name] = {
                "series": series,
                "external_series": external_series,
                "activity_total": round(total, 3),
                "growth": round(growth, 3),
                "observations": len(series),
                "movement_days": sum(1 for v in daily_values if v != 0),
            }

    top_activity = sorted(market_entities, key=lambda n: (market_entities[n]["activity_total"], n), reverse=True)[:20]
    top_growth = sorted(market_entities, key=lambda n: (market_entities[n]["growth"], market_entities[n]["activity_total"], n), reverse=True)[:20]
    def latest_metric(name, key):
        pts = market_entities[name].get("external_series", [])
        vals = [p.get(key) for p in pts if isinstance(p.get(key), (int, float))]
        return vals[-1] if vals else None
    top_downloads = sorted([n for n in market_entities if latest_metric(n, "downloads") is not None], key=lambda n: (latest_metric(n, "downloads"), n), reverse=True)[:20]
    top_security = sorted([n for n in market_entities if latest_metric(n, "security_score") is not None], key=lambda n: (latest_metric(n, "security_score"), n), reverse=True)[:20]
    top_stars = sorted([n for n in market_entities if latest_metric(n, "stars") is not None], key=lambda n: (latest_metric(n, "stars"), n), reverse=True)[:20]

    selected_names = set(top_activity + top_growth + top_downloads + top_security + top_stars)
    market = {
        "schema_version": "1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dates": all_days,
        "methodology": {
            "activity": "AHI Activity Score: cumulative weighted changes observed by AHI. Each available snapshot date is retained as an observation; unchanged days keep the previous score instead of disappearing.",
            "growth": "AHI Growth Index: change in cumulative Activity Score across the available observed window. Daily movement is preserved separately and no missing history is fabricated.",
            "downloads": "Observed download totals from source-attributed external package/model metadata. AHI does not invent pre-import download history.",
            "rating": "No universal cross-ecosystem user rating source is integrated; no value is fabricated.",
            "security": "OpenSSF Scorecard result observed by AHI; a security signal, not a guarantee of security.",
            "stars": "Repository stars observed from source-attributed ecosyste.ms repository metadata."
        },
        "top_activity": top_activity,
        "top_growth": top_growth,
        "top_downloads": top_downloads,
        "top_security": top_security,
        "top_stars": top_stars,
        "entities": market_entities,
    }
    pro = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparisons": comparisons[-120:],
        "global_integrity_anchor": {
            "tree_size": (checkpoint or {}).get("tree_size", 0),
            "merkle_root_sha256": (checkpoint or {}).get("merkle_root_sha256"),
            "checkpoint": (checkpoint or {}).get("checkpoint") or None,
            "signed": bool((checkpoint or {}).get("signature")),
        },
        "entities": pro_entities,
    }
    return pro, market


def main():
    snapshot_paths = sorted(
        [p for p in (DATA/"snapshots").glob("mcp-registry-*.json") if SNAP_RE.match(p.name)],
        key=snapshot_key
    )
    snap_path = snapshot_paths[-1] if snapshot_paths else None
    change_path = latest("changes-*.json", DATA/"changes")
    checkpoint_path = latest("checkpoint-*.json", DATA/"checkpoints")
    snap, change, checkpoint = load(snap_path), load(change_path), load(checkpoint_path)
    items = snapshot_items(snap)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_snapshot": {
            "date": (snap or {}).get("collected_at"),
            "records": (snap or {}).get("record_count", len(items)),
            "file": snap_path.name if snap_path else None,
        },
        "latest_changes": (change or {}).get("summary", {}),
        "global_integrity_anchor": {
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

    catalog, evidence_index = build_catalog(snapshot_paths)
    seeded_count = merge_seed_entities(catalog, evidence_index)
    external_by_entity, discovered_external = load_external_captures()
    merge_discovered_external_entities(catalog, discovered_external)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUT.parent.mkdir(parents=True, exist_ok=True)
    rendered=json.dumps(payload, indent=2, ensure_ascii=False)
    OUT.write_text(rendered, encoding="utf-8")
    WEB_OUT.write_text(rendered, encoding="utf-8")
    catalog_rendered=json.dumps(catalog, ensure_ascii=False, separators=(",",":"))
    CATALOG_OUT.write_text(catalog_rendered, encoding="utf-8")
    WEB_CATALOG_OUT.write_text(catalog_rendered, encoding="utf-8")
    pro, market = build_history_products(catalog, checkpoint, evidence_index, external_by_entity)
    pro_rendered=json.dumps(pro, ensure_ascii=False, separators=(",",":"))
    market_rendered=json.dumps(market, ensure_ascii=False, separators=(",",":"))
    PRO_OUT.write_text(pro_rendered, encoding="utf-8")
    WEB_PRO_OUT.write_text(pro_rendered, encoding="utf-8")
    HISTORY_OUT.write_text(pro_rendered, encoding="utf-8")
    WEB_HISTORY_OUT.write_text(pro_rendered, encoding="utf-8")
    MARKET_OUT.write_text(market_rendered, encoding="utf-8")
    WEB_MARKET_OUT.write_text(market_rendered, encoding="utf-8")
    print(f"Public status written to {OUT} and {WEB_OUT}")
    print(f"Public catalog written to {CATALOG_OUT} and {WEB_CATALOG_OUT} ({catalog['entity_count']} entities)")
    print(f"Historical entity index written to {HISTORY_OUT} and {WEB_HISTORY_OUT} ({len(pro['entities'])} entities)")
    print(f"Curated AI seed entities merged: {seeded_count}")
    print(f"Market series written to {MARKET_OUT} and {WEB_MARKET_OUT} ({len(market['entities'])} ranked entities)")
    print("Type counts:", dict(catalog["type_counts"]))
    print("Status counts:", dict(catalog["status_counts"]))


if __name__ == "__main__":
    main()
