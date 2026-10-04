# AHI Security Hardening — Rounds 1–4

Date: 2026-10-01

## Scope
This hardening cycle covers the public/free AHI surface that actually exists:
- static web application
- public catalog/status generator
- MCP Registry collector
- snapshot comparator
- append-only evidence ledger
- Merkle checkpoints
- GitHub Actions collection pipeline
- local Demo/account-preview state

The production account backend, real sessions, private Pro API and PayPal do not exist yet, so attacks against those components cannot honestly be executed yet.

## Round 1 — Frontend and public-data attack surface
Attacks/review:
- DOM/XSS sinks
- malicious external URLs
- malformed catalog data
- localStorage corruption
- excessive client-side catalog content
- prototype password handling
- basic CSP/referrer protections

Hardening:
- HTTPS-only link allowlist
- javascript:/data:/http: blocked
- noopener+noreferrer
- entity sanitization and field length caps
- guarded localStorage parsing
- public catalog ceiling
- CSP and no-referrer policy
- prototype passwords bounded/cleared

Regression result: 20/20 checks passed.

## Round 2 — Collector / evidence / CI
Attacks/review:
- oversized HTTP pages
- cursor abuse
- runaway record counts
- same-path historical mutation
- overly broad workflow credentials
- dependency drift

Hardening:
- response/page byte limit
- total record ceiling
- cursor length ceiling
- immutable snapshot/change mutation detection
- exact Python dependency version
- checkout credentials not persisted
- automated security regression execution

## Round 3 — History comparison and checkpoint chain
Attacks/review:
- timestamp-suffixed snapshots
- duplicate same-day captures
- oversized compare inputs
- checkpoint tampering
- relative/credential-bearing URLs
- oversized search input

Hardening:
- comparator supports normal, timestamped and microsecond snapshot names
- compares latest capture for the last two distinct dates
- record and file ceilings
- atomic comparison writes
- checkpoint chain verification
- optional pinned Ed25519 public key
- optional required-signing mode
- absolute HTTPS URLs only; embedded URL credentials rejected
- search bounded to 200 characters

## Round 4 — Deletion attacks and append-only event history
Destructive simulations were executed on isolated copies:
- rewrite an existing historical event row -> BLOCKED
- delete an existing historical event row -> BLOCKED
- rewrite an immutable snapshot -> BLOCKED
- delete an immutable snapshot -> BLOCKED
- alter a chained checkpoint -> BLOCKED
- malicious URL/XSS fuzz set -> BLOCKED
- timestamped same-day snapshot parsing -> PASSED

Additional hardening:
- events.csv is now protected at immutable row/event_id level, while allowing new rows to be appended
- historical immutable-file deletion is rejected, not only mutation
- per-record and total serialized collector limits
- events.csv and JSON input size limits
- duplicate event IDs rejected
- generated symlinks rejected before CI commit
- Git hooks disabled during automated commit
- exact GitHub Action release versions replace floating major tags
- browser saved-item/alert growth capped

Regression result after Round 4:
- 20/20 frontend/public-data checks passed
- 33/33 pipeline/security checks passed
- Python compilation passed
- JavaScript syntax check passed
- public-index generator smoke test passed

## What resisted after four rounds
- common HTML/script injection through catalog text
- unsafe URL protocols
- relative/credential-bearing external links
- corrupted browser preview state
- oversized search/local preview state
- oversized collector pages/records/cursors
- in-place historical snapshot/change mutation
- historical snapshot/change deletion
- mutation/deletion of already-recorded events
- chained checkpoint modification once a later checkpoint exists
- repeated same-day snapshot filename handling
- accidental execution of Git hooks during bot commits

## Residual risks / intentionally unfinished
1. Real authentication does not exist yet. Demo/account preview is not a security boundary.
2. Free/Pro authorization is not server-side yet.
3. PayPal/webhooks do not exist yet.
4. API keys do not exist yet.
5. Checkpoint signing remains optional until the owner configures an Ed25519 secret/public-key pair.
6. The newest unsigned checkpoint cannot be independently authenticated until signing/external anchoring is enabled.
7. Merkle roots are not yet anchored outside the GitHub repository.
8. Static-host response headers such as HSTS/frame protections still depend on the final hosting/CDN.
9. Semantic data poisoning cannot be solved by escaping alone: AHI must continue showing provenance and DECLARED/OBSERVED/VERIFIED distinctions.
10. GitHub Actions use exact release tags, not full commit-SHA pins; full SHA pinning remains a further supply-chain hardening step.

## Security posture
This build is materially stronger for a public/read-only launch than V7. It is not being labeled "unbreakable" or production-safe for paid accounts. The next major security boundary should be tested only after the private authentication/authorization backend exists.
