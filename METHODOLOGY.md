# AHI Methodology

## Mission
AHI is a historical transparency and verification layer for the AI ecosystem. It records
what existed, what changed, when it changed, where the information came from, and what level
of evidence supports the claim.

## Core rules
1. Every factual record must be traceable to a source or a documented AHI measurement.
2. Event time, observation time, verification time, and publication time are distinct.
3. Historical evidence is never silently rewritten or deleted.
4. Corrections are additive: a new observation supersedes an earlier one while preserving it.
5. Declared, observed, verified, third-party, and estimated data are never conflated.
6. Missing data is represented as unknown, not guessed.

## Source priority
1. Specifications and standards
2. Signed/official registries, repositories, releases, and status pages
3. Official documentation and API references
4. Official announcements and public company disclosures
5. Reliable secondary sources
6. Community sources used as leads, not as silent substitutes for primary evidence

## Historical state
Operational state is modeled separately from security and project lineage.

Operational examples: `active`, `degraded`, `deprecated`, `retired`, `discontinued`, `archived`.
Security examples: `normal`, `vulnerable`, `compromised`, `under_investigation`, `patched`.
Lineage examples: `original`, `fork`, `community_fork`, `official_fork`.

## Integrity
AHI records SHA-256 hashes for captured artifacts, chains evidence entries to the previous
entry hash, and creates Merkle-root checkpoints. Checkpoints can be signed with Ed25519 and,
in later phases, externally timestamped/anchored.

This makes retroactive modification detectable. AHI does not use the term "immutable" to
claim that storage can never be destroyed; it uses append-only retention plus independent
proofs to make silent historical rewriting detectable.

## Benchmarks and verification
Benchmarks must include the test specification version, environment, relevant model or
agent version, timestamp, region when material, inputs/outputs or their hashes, and the
measurement method. Advertised maximums are not treated as measured maximums.

## Market and financial data
AHI may store factual sourced values such as pricing, market capitalization, reported
private valuation, funding rounds, API usage claims, active-user claims, installations,
downloads, repository activity, and token metrics.

Every metric must identify whether it is reported, observed, verified, third-party, or
estimated and include its measurement window when known. AHI does not recommend investments.

## Code and proprietary artifacts
AHI does not redistribute proprietary source code merely because it was observed. It may
retain permitted metadata such as repository/commit identifiers, release signatures,
container digests, artifact hashes, license terms, source availability, and timestamps.

## Retention
The intended policy is preserve history. `collector/cleanup.py` deletes nothing.
