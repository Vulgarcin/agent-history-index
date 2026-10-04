from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLLECTOR = ROOT / "collector"
sys.path.insert(0, str(COLLECTOR))

import backfill_external as b
from source_policy import SOURCES, ALLOWED_API_HOSTS

checks = []

def check(name, condition):
    checks.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)

check("All external API hosts HTTPS allowlisted", {"repos.ecosyste.ms","packages.ecosyste.ms","api.securityscorecards.dev","api.osv.dev","huggingface.co"}.issubset(ALLOWED_API_HOSTS))
check("ecosyste.ms attribution policy present", SOURCES["ecosystems-repos"]["license"] == "CC-BY-SA-4.0" and SOURCES["ecosystems-repos"]["attribution"] == "ecosyste.ms")
check("OSV upstream-specific license policy present", SOURCES["osv"]["license"] == "UPSTREAM-SPECIFIC")
check("Hugging Face content-specific policy present", SOURCES["huggingface-hub"]["license"] == "CONTENT-SPECIFIC")
check("Reject javascript URL", b.clean_url("javascript:alert(1)") is None)
check("Reject HTTP URL", b.clean_url("http://github.com/a/b") is None)
check("Reject URL credentials", b.clean_url("https://user:pass@github.com/a/b") is None)
check("Accept HTTPS URL", b.clean_url("https://github.com/a/b") == "https://github.com/a/b")
try:
    b.request_json("https://example.com/x")
    blocked = False
except RuntimeError:
    blocked = True
check("Unapproved external host blocked before network", blocked)
check("npm ecosystem mapping", b.ecosystem_name("npm") == "npm")
check("PyPI OSV mapping", b.osv_ecosystem("pypi") == "PyPI")
check("Hugging Face model ID extraction", b.hf_model_id({"repository_url":"https://huggingface.co/org/model","entity_type":"model","name":"org/model"}) == "org/model")
check("External response byte ceiling", b.MAX_RESPONSE_BYTES <= 4 * 1024 * 1024)
check("External record byte ceiling", b.MAX_RECORD_BYTES <= 512 * 1024)

builder = (COLLECTOR / "build_public_index.py").read_text(encoding="utf-8")
check("Builder creates per-entity Merkle root", "entity_merkle_root_sha256" in builder)
check("Builder separates global integrity anchor", "global_integrity_anchor" in builder)
check("Builder indexes external captures", "load_external_captures" in builder)
check("Builder exposes external market series", "external_series" in builder)

failed = [n for n, ok in checks if not ok]
print(f"\n{len(checks)-len(failed)}/{len(checks)} external/backfill checks passed")
if failed:
    raise SystemExit("Failed: " + ", ".join(failed))
