# AHI External Source Matrix

| Source | What AHI imports in V12 | Historical value | License / terms handling | Default mode |
|---|---|---|---|---|
| ecosyste.ms Repositories | repository identity, stars, forks, issues, language, license, dates, topics, commit summary when present | older repository creation/activity metadata + current ecosystem metrics | CC BY-SA 4.0; attribution retained; kept in separate external layer | targeted enrichment of known repo URLs |
| ecosyste.ms Packages | package identity, versions count, release dates, download total when supplied, repository/registry links, declared licenses | release dates can predate AHI; current download total becomes an observed external metric | CC BY-SA 4.0; attribution retained | targeted enrichment of packages already linked to AHI entities |
| OpenSSF Scorecard | current aggregate score + named checks/reasons | security posture observation from the date AHI imports it; not retroactively fabricated | Scorecard result data identified by project as CDLA Permissive 2.0 | GitHub-linked entities only |
| OSV.dev | advisory IDs, summaries, aliases, published/modified dates for specific package/version | true historical vulnerability dates where upstream advisories provide them | upstream-specific licenses; preserve ID/source/provenance | known package + version only |
| Hugging Face Hub | public model metadata: model ID, author, dates, downloads, likes, trending score, pipeline tag, tags, declared license | can bootstrap older model creation dates; download/like totals are observed from import date | public Hub terms + repository-specific content license; no weights/files mirrored | existing models + optional bounded discovery |

## Explicitly not copied in V12

- model weights
- complete Hugging Face repositories
- the entire ecosyste.ms database
- the entire OSV dump
- proprietary/private API data
- credentials, tokens, private repositories
- financial prices that do not exist
- fabricated ratings or SLA values

V12 is designed for targeted enrichment and historical attribution, not indiscriminate mirroring.
