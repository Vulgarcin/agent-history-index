# External Backfill / Enrichment

V12 introduces a rate-limited, append-only external enrichment collector.

## First run

Generate the current AHI catalog first:

```powershell
python collector\build_public_index.py
```

Then import a conservative first batch:

```powershell
python collector\backfill_external.py --limit 100 --discover-hf 100
```

After the collector finishes, rebuild the public indexes:

```powershell
python collector\build_public_index.py
```

The external collector never overwrites previous captures. It writes timestamped JSONL under:

`data/external/captures/`

A mutable cursor file under `data/external/state.json` only controls where the next polite batch resumes; it is not historical evidence.

## Contact email

ecosyste.ms recommends identifying polite API clients. Once the official AHI email exists:

```powershell
$env:AHI_SOURCE_CONTACT_EMAIL="contact@agenthistoryindex.com"
python collector\backfill_external.py --limit 250 --discover-hf 100
```

Use the actual created address; do not use the example before the mailbox exists.

## Why batches?

AHI has tens of thousands of MCP records. The external services are public infrastructure, so V12 intentionally avoids hammering them. Repeated batches gradually enrich the catalog while preserving every capture.
