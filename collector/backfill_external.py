from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from source_policy import ALLOWED_API_HOSTS, SOURCES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOG_PATHS = [DATA / "public" / "catalog.json", ROOT / "web" / "data" / "catalog.json"]
CAPTURE_DIR = DATA / "external" / "captures"
STATE_PATH = DATA / "external" / "state.json"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 512 * 1024
MAX_CAPTURE_RECORDS = 5000
DEFAULT_TIMEOUT = 25
DEFAULT_RETRIES = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def canonical_hash(value) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def safe_text(value, limit=5000):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()[:limit]
    return None


def safe_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except Exception:
        return None


def clean_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()[:2048]
    try:
        p = urlparse(value)
    except Exception:
        return None
    if p.scheme.lower() != "https" or not p.hostname or p.username or p.password:
        return None
    if any(ord(c) < 32 for c in value) or "\\" in value:
        return None
    return p.geturl()


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_API_HOSTS:
            raise RuntimeError(f"Blocked redirect to unapproved host: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = build_opener(SafeRedirect)


def user_agent(contact_email: str | None):
    if contact_email:
        return f"Agent-History-Index/0.12 (mailto:{contact_email})"
    return "Agent-History-Index/0.12"


def request_json(url: str, *, contact_email=None, method="GET", body=None, retries=DEFAULT_RETRIES):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_API_HOSTS:
        raise RuntimeError(f"Blocked API host: {url}")
    payload = None
    headers = {"Accept": "application/json", "User-Agent": user_agent(contact_email)}
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        try:
            req = Request(url, data=payload, headers=headers, method=method)
            with OPENER.open(req, timeout=DEFAULT_TIMEOUT) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "json" not in content_type and content_type:
                    raise RuntimeError(f"Unexpected content type from {host}: {content_type}")
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"External response too large from {host}")
                return json.loads(data.decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(min(8, 1.5 * (attempt + 1)))
                continue
            raise
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt + 1 < retries:
                time.sleep(min(8, 1.5 * (attempt + 1)))
                continue
            raise RuntimeError(f"External request failed: {url}: {exc}") from exc


def load_catalog():
    for path in CATALOG_PATHS:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            entities = obj.get("entities") if isinstance(obj, dict) else None
            if isinstance(entities, list):
                return entities
    raise RuntimeError("catalog.json not found. Run collector/build_public_index.py first.")


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def append_capture(records):
    if not records:
        return None
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / f"external-backfill-{stamp()}-{uuid.uuid4().hex[:8]}.jsonl"
    if path.exists():
        raise RuntimeError("Refusing to overwrite external evidence capture")
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        for record in records[:MAX_CAPTURE_RECORDS]:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            if len(line.encode("utf-8")) > MAX_RECORD_BYTES:
                raise RuntimeError("External normalized record exceeds safety ceiling")
            fh.write(line + "\n")
    return path


def make_record(entity, source_id, source_url, normalized, *, effective_at=None, entity_type=None, declared_content_license=None):
    policy = SOURCES[source_id]
    clean_source = clean_url(source_url)
    if not clean_source:
        raise RuntimeError("Unsafe source URL generated internally")
    return {
        "schema_version": "1.0",
        "observation_id": str(uuid.uuid4()),
        "entity_name": safe_text(entity.get("name"), 500),
        "entity_type": entity_type or safe_text(entity.get("entity_type"), 80),
        "repository_url": clean_url(entity.get("repository_url")),
        "observed_at": now_iso(),
        "effective_at": safe_text(effective_at, 80),
        "source_id": source_id,
        "source_name": policy["name"],
        "source_url": clean_source,
        "source_homepage": policy["homepage"],
        "source_license": policy["license"],
        "source_license_url": policy["license_url"],
        "source_attribution": policy["attribution"],
        "evidence_class": policy["evidence_class"],
        "declared_content_license": safe_text(declared_content_license, 300),
        "payload_sha256": canonical_hash(normalized),
        "data": normalized,
    }


def repo_parts(repo_url):
    url = clean_url(repo_url)
    if not url:
        return None
    p = urlparse(url)
    parts = [quote(x, safe="") for x in p.path.strip("/").split("/") if x]
    if len(parts) < 2:
        return None
    raw_parts = [x for x in p.path.strip("/").split("/") if x]
    return p.hostname.lower(), raw_parts[0], raw_parts[1].removesuffix(".git")


def fetch_ecosystems_repo(entity, contact_email):
    repo = clean_url(entity.get("repository_url"))
    if not repo:
        return None
    url = "https://repos.ecosyste.ms/api/v1/repositories/lookup?" + urlencode({"url": repo})
    obj = request_json(url, contact_email=contact_email)
    if not isinstance(obj, dict):
        return None
    normalized = {
        "full_name": safe_text(obj.get("full_name"), 500),
        "description": safe_text(obj.get("description")),
        "stars": safe_number(obj.get("stargazers_count")),
        "forks": safe_number(obj.get("forks_count")),
        "open_issues": safe_number(obj.get("open_issues_count")),
        "archived": bool(obj.get("archived")) if isinstance(obj.get("archived"), bool) else None,
        "fork": bool(obj.get("fork")) if isinstance(obj.get("fork"), bool) else None,
        "license": safe_text(obj.get("license"), 300),
        "language": safe_text(obj.get("language"), 200),
        "created_at": safe_text(obj.get("created_at"), 80),
        "updated_at": safe_text(obj.get("updated_at"), 80),
        "pushed_at": safe_text(obj.get("pushed_at"), 80),
        "default_branch": safe_text(obj.get("default_branch"), 300),
        "homepage": clean_url(obj.get("homepage")),
        "topics": [safe_text(x, 120) for x in (obj.get("topics") or []) if safe_text(x, 120)][:100],
    }
    cs = obj.get("commit_stats")
    if isinstance(cs, dict):
        normalized["commit_stats"] = {
            "total_commits": safe_number(cs.get("total_commits") or cs.get("commits")),
            "total_committers": safe_number(cs.get("total_committers") or cs.get("authors")),
            "dds": safe_number(cs.get("dds") or cs.get("development_distribution_score")),
        }
    return make_record(entity, "ecosystems-repos", url, normalized, effective_at=normalized.get("created_at"))


def package_candidates(entity):
    packages = entity.get("packages")
    if not isinstance(packages, list):
        return []
    out = []
    for pkg in packages[:20]:
        if not isinstance(pkg, dict):
            continue
        registry = safe_text(pkg.get("registry_type") or pkg.get("registryType") or pkg.get("type"), 80)
        identifier = safe_text(pkg.get("identifier") or pkg.get("name") or pkg.get("package"), 500)
        version = safe_text(pkg.get("version"), 200)
        if registry and identifier:
            out.append((registry.lower(), identifier, version))
    return out


def ecosystem_name(registry):
    mapping = {
        "npm": "npm",
        "npmjs": "npm",
        "pypi": "pypi",
        "python": "pypi",
        "nuget": "nuget",
        "crates": "cargo",
        "cargo": "cargo",
        "rubygems": "rubygems",
        "gem": "rubygems",
        "maven": "maven",
        "docker": "docker",
        "dockerhub": "docker",
    }
    return mapping.get(registry)


def fetch_ecosystems_packages(entity, contact_email):
    rows = []
    for registry, identifier, version in package_candidates(entity):
        ecosystem = ecosystem_name(registry)
        if not ecosystem:
            continue
        url = "https://packages.ecosyste.ms/api/v1/packages/lookup?" + urlencode({"ecosystem": ecosystem, "name": identifier})
        obj = request_json(url, contact_email=contact_email)
        candidates = obj if isinstance(obj, list) else []
        selected = None
        for item in candidates:
            if isinstance(item, dict) and str(item.get("name") or "").lower() == identifier.lower():
                selected = item
                break
        if not selected and candidates and isinstance(candidates[0], dict):
            selected = candidates[0]
        if not selected:
            continue
        normalized = {
            "ecosystem": ecosystem,
            "package": identifier,
            "version_observed": version,
            "description": safe_text(selected.get("description")),
            "downloads": safe_number(selected.get("downloads") or selected.get("downloads_count")),
            "versions_count": safe_number(selected.get("versions_count")),
            "first_release_published_at": safe_text(selected.get("first_release_published_at"), 80),
            "latest_release_published_at": safe_text(selected.get("latest_release_published_at"), 80),
            "latest_release_number": safe_text(selected.get("latest_release_number"), 200),
            "repository_url": clean_url(selected.get("repository_url")),
            "registry_url": clean_url(selected.get("registry_url")),
            "licenses": selected.get("licenses") if isinstance(selected.get("licenses"), (list, dict, str)) else None,
        }
        rows.append(make_record(entity, "ecosystems-packages", url, normalized, effective_at=normalized.get("first_release_published_at")))
    return rows


def fetch_scorecard(entity, contact_email):
    parts = repo_parts(entity.get("repository_url"))
    if not parts or parts[0] not in {"github.com", "www.github.com"}:
        return None
    _, owner, repo = parts
    url = f"https://api.securityscorecards.dev/projects/github.com/{quote(owner, safe='')}/{quote(repo, safe='')}"
    obj = request_json(url, contact_email=contact_email)
    if not isinstance(obj, dict):
        return None
    checks = []
    for check in obj.get("checks", []) if isinstance(obj.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        checks.append({
            "name": safe_text(check.get("name"), 200),
            "score": safe_number(check.get("score")),
            "reason": safe_text(check.get("reason"), 1000),
        })
    normalized = {
        "score": safe_number(obj.get("score")),
        "date": safe_text(obj.get("date"), 80),
        "commit": safe_text(obj.get("repo", {}).get("commit") if isinstance(obj.get("repo"), dict) else None, 200),
        "checks": checks[:30],
    }
    return make_record(entity, "openssf-scorecard", url, normalized, effective_at=normalized.get("date"))


def osv_ecosystem(registry):
    mapping = {"npm": "npm", "npmjs": "npm", "pypi": "PyPI", "python": "PyPI", "cargo": "crates.io", "crates": "crates.io", "nuget": "NuGet", "rubygems": "RubyGems", "gem": "RubyGems", "maven": "Maven"}
    return mapping.get(registry)


def fetch_osv(entity, contact_email):
    rows = []
    for registry, identifier, version in package_candidates(entity):
        ecosystem = osv_ecosystem(registry)
        if not ecosystem or not version:
            continue
        url = "https://api.osv.dev/v1/query"
        obj = request_json(url, contact_email=contact_email, method="POST", body={"package": {"ecosystem": ecosystem, "name": identifier}, "version": version})
        if not isinstance(obj, dict):
            continue
        vulns = []
        for vuln in obj.get("vulns", []) if isinstance(obj.get("vulns"), list) else []:
            if not isinstance(vuln, dict):
                continue
            vulns.append({
                "id": safe_text(vuln.get("id"), 200),
                "summary": safe_text(vuln.get("summary"), 1000),
                "published": safe_text(vuln.get("published"), 80),
                "modified": safe_text(vuln.get("modified"), 80),
                "aliases": [safe_text(x, 200) for x in (vuln.get("aliases") or []) if safe_text(x, 200)][:30],
            })
        normalized = {"ecosystem": ecosystem, "package": identifier, "version": version, "vulnerability_count": len(vulns), "vulnerabilities": vulns[:100]}
        rows.append(make_record(entity, "osv", url, normalized, effective_at=min((v.get("published") for v in vulns if v.get("published")), default=None)))
    return rows


def hf_model_id(entity):
    repo = clean_url(entity.get("repository_url"))
    if repo:
        p = urlparse(repo)
        if p.hostname == "huggingface.co":
            parts = [x for x in p.path.strip("/").split("/") if x]
            if len(parts) >= 2 and parts[0] not in {"datasets", "spaces"}:
                return f"{parts[0]}/{parts[1]}"
    if entity.get("entity_type") == "model" and isinstance(entity.get("name"), str) and "/" in entity["name"]:
        return entity["name"][:500]
    return None


def normalize_hf_model(obj):
    tags = [safe_text(x, 150) for x in (obj.get("tags") or []) if safe_text(x, 150)][:100]
    declared = None
    for tag in tags:
        if tag and tag.startswith("license:"):
            declared = tag.split(":", 1)[1][:200]
            break
    return {
        "model_id": safe_text(obj.get("id") or obj.get("modelId"), 500),
        "author": safe_text(obj.get("author"), 300),
        "downloads": safe_number(obj.get("downloads")),
        "downloads_all_time": safe_number(obj.get("downloadsAllTime")),
        "likes": safe_number(obj.get("likes")),
        "trending_score": safe_number(obj.get("trendingScore")),
        "created_at": safe_text(obj.get("createdAt"), 80),
        "last_modified": safe_text(obj.get("lastModified"), 80),
        "pipeline_tag": safe_text(obj.get("pipeline_tag") or obj.get("pipelineTag"), 200),
        "tags": tags,
        "declared_license": declared,
    }


def fetch_hf_model(entity, contact_email):
    model_id = hf_model_id(entity)
    if not model_id:
        return None
    url = f"https://huggingface.co/api/models/{quote(model_id, safe='/')}"
    obj = request_json(url, contact_email=contact_email)
    if not isinstance(obj, dict):
        return None
    normalized = normalize_hf_model(obj)
    return make_record(entity, "huggingface-hub", url, normalized, effective_at=normalized.get("created_at"), entity_type="model", declared_content_license=normalized.get("declared_license"))


def discover_hf(limit, contact_email):
    if limit <= 0:
        return []
    limit = min(limit, 500)
    url = "https://huggingface.co/api/models?" + urlencode({"sort": "trendingScore", "direction": "-1", "limit": limit, "full": "true"})
    obj = request_json(url, contact_email=contact_email)
    out = []
    for item in obj if isinstance(obj, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = normalize_hf_model(item)
        model_id = normalized.get("model_id")
        if not model_id:
            continue
        entity = {"name": model_id, "entity_type": "model", "repository_url": f"https://huggingface.co/{model_id}"}
        out.append(make_record(entity, "huggingface-hub", f"https://huggingface.co/api/models/{quote(model_id, safe='/')}", normalized, effective_at=normalized.get("created_at"), entity_type="model", declared_content_license=normalized.get("declared_license")))
    return out


def select_batch(entities, source, limit, state):
    eligible = []
    for e in entities:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str):
            continue
        if source in {"ecosystems-repos", "openssf-scorecard"} and not e.get("repository_url"):
            continue
        if source in {"ecosystems-packages", "osv"} and not package_candidates(e):
            continue
        if source == "huggingface-hub" and not hf_model_id(e):
            continue
        eligible.append(e)
    eligible.sort(key=lambda e: e["name"].lower())
    if not eligible:
        return []
    last = state.get(source, {}).get("last_entity")
    start = 0
    if last:
        for i, e in enumerate(eligible):
            if e["name"].lower() > str(last).lower():
                start = i
                break
        else:
            start = 0
    return eligible[start:start + limit]


def main():
    parser = argparse.ArgumentParser(description="Append-only external historical enrichment for AHI")
    parser.add_argument("--source", default="ecosystems-repos,ecosystems-packages,openssf-scorecard,osv,huggingface-hub", help="comma-separated source IDs")
    parser.add_argument("--limit", type=int, default=100, help="max existing entities per source in this run")
    parser.add_argument("--discover-hf", type=int, default=0, help="also import metadata for N public trending Hugging Face models (max 500)")
    parser.add_argument("--sleep", type=float, default=0.15, help="delay between external requests")
    parser.add_argument("--contact-email", default=os.environ.get("AHI_SOURCE_CONTACT_EMAIL"), help="contact email for polite API identification")
    args = parser.parse_args()

    sources = [s.strip() for s in args.source.split(",") if s.strip()]
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        raise SystemExit(f"Unknown source IDs: {', '.join(unknown)}")
    if args.limit < 1 or args.limit > 5000:
        raise SystemExit("--limit must be between 1 and 5000")

    entities = load_catalog()
    state = load_state()
    records = []
    stats = {s: {"ok": 0, "miss": 0, "error": 0} for s in sources}

    for source in sources:
        batch = select_batch(entities, source, args.limit, state)
        last_name = None
        for entity in batch:
            last_name = entity.get("name")
            try:
                if source == "ecosystems-repos":
                    value = fetch_ecosystems_repo(entity, args.contact_email)
                    values = [value] if value else []
                elif source == "ecosystems-packages":
                    values = fetch_ecosystems_packages(entity, args.contact_email)
                elif source == "openssf-scorecard":
                    value = fetch_scorecard(entity, args.contact_email)
                    values = [value] if value else []
                elif source == "osv":
                    values = fetch_osv(entity, args.contact_email)
                else:
                    value = fetch_hf_model(entity, args.contact_email)
                    values = [value] if value else []
                values = [v for v in values if v]
                if values:
                    records.extend(values)
                    stats[source]["ok"] += 1
                else:
                    stats[source]["miss"] += 1
            except Exception as exc:
                stats[source]["error"] += 1
                print(f"WARN {source} {entity.get('name')}: {exc}")
            if args.sleep:
                time.sleep(max(0.0, min(args.sleep, 5.0)))
        if last_name:
            state[source] = {"last_entity": last_name, "updated_at": now_iso()}

    if args.discover_hf:
        try:
            discovered = discover_hf(args.discover_hf, args.contact_email)
            records.extend(discovered)
            stats.setdefault("huggingface-discovery", {})["ok"] = len(discovered)
        except Exception as exc:
            print(f"WARN huggingface discovery: {exc}")

    path = append_capture(records)
    save_state(state)
    print("External enrichment summary:", json.dumps(stats, ensure_ascii=False))
    if path:
        print(f"Append-only external capture saved: {path}")
        print(f"Records: {len(records)}")
    else:
        print("No external records captured in this run.")


if __name__ == "__main__":
    main()
