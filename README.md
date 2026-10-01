# Agent History Index (AHI) — v4

**AHI is a historical transparency and verification layer for the AI ecosystem.**

The public directory is the discovery surface. Under it, AHI is being built to preserve
sourced observations, detect drift, verify integrity, and eventually provide historical,
market, reliability, security, and benchmark intelligence.

## V4 foundations
- resilient MCP Registry collector with retry/backoff
- complete-snapshot rule: failed collections do not save partial daily evidence
- historical snapshots are retained; no cleanup deletion
- comparison engine: added / removed / version / status / generic content drift
- append-only JSONL evidence ledger
- SHA-256 artifact digests and chained evidence-entry hashes
- Merkle-tree checkpoints
- optional Ed25519 signatures via deployment secret
- public status JSON generated from real repository data
- launchable static informational web front-end
- architecture and roadmap documentation

## Run the pipeline locally
```bash
python collector/collect.py
python collector/compare.py
python collector/integrity.py
python collector/build_public_index.py
python collector/cleanup.py
```

## Optional checkpoint signing
Generate/manage the private key outside the repository. Set only its raw 32-byte Ed25519
private-key value as base64 in `AHI_SIGNING_KEY_B64`. Never commit private keys.

If the environment variable is absent, checkpoints remain hash/Merkle verified but unsigned.

## Web
Open `web/index.html` for a local preview. For `web/data/status.json` to be loaded by the
browser reliably, serve the `web` folder with a tiny local web server:

```bash
cd web
python -m http.server 8000
```

Then visit `http://localhost:8000`.

## Important production boundary
Before monetization, collectors, signing keys, premium datasets, normalization logic,
verification nodes, and privileged APIs should be moved behind private infrastructure.
Do not put payment secrets or authentication credentials into the public front-end.

See `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and `Methodology.md`.
