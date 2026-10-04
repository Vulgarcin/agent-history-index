# AHI External Source Policy

Checked: 2026-10-04

AHI separates native observations from imported or externally observed data. External data never becomes "AHI observed in the past" merely because AHI imports it later.

## Evidence classes

- `OBSERVED`: captured directly by AHI's native collector at observation time.
- `HISTORICAL_IMPORTED`: older or third-party historical material imported later with source attribution.
- `OBSERVED_EXTERNAL`: current third-party measurement observed by AHI through an external API.
- `DECLARED`: publisher/developer claim.
- `VERIFIED`: reserved for independently reproduced or validated results.

## Sources enabled in V12

### ecosyste.ms Repositories / Packages
- Data license: CC BY-SA 4.0.
- Attribution: `ecosyste.ms` must remain visible.
- AHI keeps ecosyste.ms captures in a separate external evidence layer.
- If AHI ever republishes all or a substantial portion of the ecosyste.ms database as part of a commercial proprietary database, the share-alike/database-right implications must be reviewed; ecosyste.ms also offers commercial licenses.
- AHI V12 performs targeted entity enrichment rather than bulk mirroring the whole database.

### OpenSSF Scorecard
- Result data: CDLA Permissive 2.0 according to the Scorecard infrastructure project.
- AHI stores current score/check measurements with source/date attribution.
- A score is a security signal, not a guarantee that a project is secure.

### OSV.dev
- OSV is an aggregator. Individual records come from upstream databases with different licenses (for example CC BY 4.0, CC0, MIT, Apache-2.0, BSD and CC BY-SA depending on source).
- AHI preserves advisory IDs and upstream provenance and does not treat the aggregate as having one blanket content license.
- V12 queries relevant package/version records rather than blindly copying the entire OSV corpus.

### Hugging Face Hub
- V12 imports public repository metadata only: model ID, dates, downloads, likes, tags, pipeline category and declared license metadata.
- It does not mirror model weights or repository files.
- Individual model/content licenses remain authoritative and are stored when declared.

## No silent relicensing

Every external capture stores source ID, source URL, license label/URL, attribution, observation timestamp and payload hash. AHI-native analysis may be derived from these observations, but the original source metadata remains attached.
