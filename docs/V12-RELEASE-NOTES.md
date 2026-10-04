# AHI V12 — Historical Backfill & Entity Intelligence

## Why this release exists

V11 exposed two important limitations during manual review:

1. Entity Evidence/Merkle showed the same global checkpoint values for every entity.
2. Market data was not yet reliably entity-selectable or sufficiently sourced for downloads/security/history.

V12 fixes those design errors and introduces a licensed external evidence layer.

## Entity-specific evidence

Each entity now gets its own evidence summary derived from the exact records observed in preserved AHI snapshots:

- observation count
- number of distinct record hashes
- latest record SHA-256
- per-entity Merkle root across observed record hashes
- first and latest evidence observation
- bounded observation list with snapshot/date/version/status

The global AHI checkpoint remains visible, but is explicitly labeled as a separate global anchor.

## Market terminal

- selected entity is highlighted in neon green
- other series are subdued
- max/min points are marked
- up to three strongest changes are marked with delta points
- details include max/min dates, latest value and largest observed movement
- flat/single-point series render visibly instead of appearing blank
- Activity and Growth remain AHI-native
- Downloads can be populated from source-attributed package/model metadata
- Stars can be populated from repository metadata
- Security can be populated from OpenSSF Scorecard
- Valuation remains empty until a defensible cross-ecosystem source/definition exists

## External historical enrichment

New append-only collector:

`collector/backfill_external.py`

Sources enabled:

- ecosyste.ms Repositories
- ecosyste.ms Packages
- OpenSSF Scorecard
- OSV.dev
- Hugging Face Hub public model metadata

Every capture carries source attribution, license metadata, observation time, evidence class and payload hash.

## License boundary

External captures are deliberately kept under `data/external/` rather than being silently relabeled as native AHI observations.

The product can use those records to fill historical gaps and build analysis, while preserving source/license provenance.

## Model directory bootstrap

The external collector can optionally discover a bounded number of public Hugging Face model metadata records. This begins populating the previously empty Model category without downloading model weights or repository files.

## Security

V12 retains the V10 security controls and adds a third regression suite for external enrichment.

Validated offline:

- 20/20 frontend/public security checks
- 33/33 pipeline/history checks
- 18/18 external-source/backfill checks
- Python compilation passed
- JavaScript syntax validation passed
- synthetic end-to-end builder smoke test passed
