# AHI Architecture v4

AHI is designed as a historical transparency and verification layer for the AI ecosystem.
The public directory is an interface over a deeper evidence system.

## Non-negotiable rule
Historical evidence is never silently overwritten or deleted. Corrections are new records
that supersede earlier observations while preserving the earlier state.

## Layers

### 1. Sources
Official registries, specifications, repositories, release notes, documentation, status
pages, security advisories, public APIs, market disclosures, and later standardized AHI
verification tests.

### 2. Raw Observation Layer
Collectors store the original observation with source, collection time, collector version,
and record count. A failed collection never produces a partial daily snapshot.

### 3. Evidence Registry
`collector/integrity.py` records artifact hashes in `data/evidence/ledger.jsonl`.
Each ledger record contains the SHA-256 hash of the artifact and the hash of the previous
ledger record. Integrity runs also create Merkle checkpoints in `data/checkpoints/`.

When `AHI_SIGNING_KEY_B64` is configured, checkpoints receive an Ed25519 signature.
The private key must live only in the deployment secret store, never in Git.

This is **tamper-evident**, not a claim that deletion is physically impossible. Later
checkpoints can be anchored to an independent timestamp/transparency service or a
distributed network.

### 4. Normalized Identity / Knowledge Graph
Every persistent entity receives an AHI identity. The target entity types include agents,
models, frameworks, protocols, MCP servers, tools, APIs, companies, repositories, datasets,
benchmarks, incidents, and standards.

The normalized state is mutable for fast queries; historical observations are not.

### 5. Drift Engine
Current `compare.py` detects additions, removals, version changes, status changes, and any
record-content hash change. Future drift modules expand this to capabilities, permissions,
license, pricing, protocol, governance, security, reliability, and performance.

### 6. Verification Nodes
Future AHI verification nodes run versioned tests against publicly exposed agents and APIs.
Every result stores the test version, environment, region, input/output hashes, timing,
result, node identity, and signature. AHI distinguishes developer claims from AHI-observed
and AHI-verified results.

### 7. Indexed Query State
A separate database/index serves the latest state quickly. Every material field should
reference its evidence. Rebuilding this layer must be possible from retained observations.

### 8. Public / Pro Products
The public site exposes discovery, current factual state, recent activity, methodology, and
proof that historical evidence exists. Paid products can later expose full timelines,
comparisons, capability drift, market/reliability history, evidence proofs, exports, alerts,
and API access.

## Evidence classes
- `declared`: stated by the developer/operator.
- `observed`: directly captured by an AHI collector.
- `verified`: reproduced by a standardized AHI verification procedure.
- `third_party`: reported by an identified external source.
- `estimated`: calculated by AHI from explicit assumptions.

AHI must never present one class as another.

## Information retention tiers
- **Critical evidence:** retain full original artifact when legally and technically allowed.
- **Contextual evidence:** retain structured summary + source + before/after hashes when full
  retention has low value or redistribution restrictions.
- **Discardable noise:** omit only when it cannot materially improve historical,
  technical, market, security, or operational reconstruction.

## Planned data domains
Identity, developer/owner, code/model/service licensing, operational/security state,
architecture, base model/provider, interoperability protocols and versions, integrations,
execution permissions, context-window metrics, latency distributions, version/release
history, governance, market traction, pricing/cost, SLA and observed reliability, incidents,
vulnerabilities, benchmarks, and signed attestations.

## Security boundaries
The public front-end is not the product secret. Collectors, normalizers, verification logic,
private keys, premium datasets, and privileged APIs should migrate to private repositories
or private deployment environments before production monetization.
