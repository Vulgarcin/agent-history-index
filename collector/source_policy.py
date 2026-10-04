from __future__ import annotations

"""Source policy registry for AHI external enrichment.

This module centralizes attribution, license notes, and host allowlists so the
collector does not silently mix third-party data with native AHI observations.
"""

SOURCES = {
    "ecosystems-repos": {
        "name": "ecosyste.ms Repositories",
        "homepage": "https://repos.ecosyste.ms/",
        "license": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "terms_url": "https://ecosyste.ms/terms",
        "attribution": "ecosyste.ms",
        "evidence_class": "HISTORICAL_IMPORTED",
        "notes": "Keep attribution. Substantial database reuse can trigger share-alike obligations; AHI stores this source separately and does not relabel it as native AHI data.",
    },
    "ecosystems-packages": {
        "name": "ecosyste.ms Packages",
        "homepage": "https://packages.ecosyste.ms/",
        "license": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "terms_url": "https://ecosyste.ms/terms",
        "attribution": "ecosyste.ms",
        "evidence_class": "HISTORICAL_IMPORTED",
        "notes": "Package metadata is kept with source attribution and separated from AHI-native observations.",
    },
    "openssf-scorecard": {
        "name": "OpenSSF Scorecard",
        "homepage": "https://securityscorecards.dev/",
        "license": "CDLA-Permissive-2.0",
        "license_url": "https://cdla.dev/permissive-2-0/",
        "terms_url": "https://api.securityscorecards.dev/",
        "attribution": "OpenSSF Scorecard",
        "evidence_class": "OBSERVED_EXTERNAL",
        "notes": "Scorecard result data is attributed to OpenSSF Scorecard. Current results are observations, not historical AHI measurements.",
    },
    "osv": {
        "name": "OSV.dev",
        "homepage": "https://osv.dev/",
        "license": "UPSTREAM-SPECIFIC",
        "license_url": "https://google.github.io/osv.dev/data/",
        "terms_url": "https://osv.dev/",
        "attribution": "OSV.dev and originating advisory database",
        "evidence_class": "HISTORICAL_IMPORTED",
        "notes": "OSV aggregates multiple upstream databases with different licenses. Preserve advisory IDs, source identity and upstream attribution; do not assume a single blanket data license.",
    },
    "huggingface-hub": {
        "name": "Hugging Face Hub",
        "homepage": "https://huggingface.co/",
        "license": "CONTENT-SPECIFIC",
        "license_url": "https://huggingface.co/terms-of-service",
        "terms_url": "https://huggingface.co/terms-of-service",
        "attribution": "Hugging Face Hub and repository owner",
        "evidence_class": "OBSERVED_EXTERNAL",
        "notes": "AHI imports public repository metadata only. Model weights/files are not mirrored. Each repository's declared content license remains authoritative.",
    },
}

ALLOWED_API_HOSTS = {
    "repos.ecosyste.ms",
    "packages.ecosyste.ms",
    "api.securityscorecards.dev",
    "api.scorecard.dev",
    "api.osv.dev",
    "huggingface.co",
}
