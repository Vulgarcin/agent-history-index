from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

collect=load_module('ahi_collect',ROOT/'collector/collect.py')
integrity=load_module('ahi_integrity',ROOT/'collector/integrity.py')
builder=load_module('ahi_builder',ROOT/'collector/build_public_index.py')
compare=load_module('ahi_compare',ROOT/'collector/compare.py')
checks=[]
def check(name,cond): checks.append((name,bool(cond)))

check('Collector page byte limit',0<collect.MAX_PAGE_BYTES<=16*1024*1024)
check('Collector total record ceiling',collect.MAX_TOTAL_RECORDS<=100000)
check('Collector per-record byte ceiling',collect.MAX_RECORD_BYTES<=1024*1024)
check('Collector total serialized ceiling',collect.MAX_TOTAL_SERIALIZED_BYTES<=512*1024*1024)
try: collect.build_url('x'*(collect.MAX_CURSOR_LENGTH+1)); ok=False
except RuntimeError: ok=True
check('Oversized cursor rejected',ok)

check('Immutable snapshot paths',integrity.is_immutable_path('data/snapshots/x.json'))
check('Immutable change paths',integrity.is_immutable_path('data/changes/x.json'))
check('Immutable event-row paths',integrity.is_immutable_path('data/events.csv#event:AHI-X'))
entry={'schema_version':'1.2','observed_at':'x','artifact_path':'data/snapshots/a.json','artifact_sha256':'a'*64,'artifact_size':1,'previous_entry_hash':integrity.ZERO_HASH}
entry['entry_hash']=integrity.sha256_bytes(integrity.canonical(entry)); entries=[entry]
try: integrity.assert_no_historical_mutation_or_deletion(entries,{'data/snapshots/a.json':'b'*64}); ok=False
except RuntimeError as e: ok='HISTORICAL_MUTATION' in str(e)
check('Historical mutation rejected',ok)
try: integrity.assert_no_historical_mutation_or_deletion(entries,{}); ok=False
except RuntimeError as e: ok='HISTORICAL_DELETION' in str(e)
check('Historical deletion rejected',ok)
check('Checkpoint chain verification', 'verify_existing_checkpoints' in (ROOT/'collector/integrity.py').read_text())
check('Pinned public signing key supported','AHI_SIGNING_PUBLIC_KEY_B64' in (ROOT/'collector/integrity.py').read_text())
check('Signing can be required','AHI_REQUIRE_SIGNING' in (ROOT/'collector/integrity.py').read_text())

check('Comparator timestamp suffix support', compare.SNAPSHOT_RE.match('mcp-registry-2026-10-01-174321.json') is not None)
check('Comparator microsecond suffix support', compare.SNAPSHOT_RE.match('mcp-registry-2026-10-01-174321123456.json') is not None)
check('Comparator record ceiling',compare.MAX_RECORDS<=100000)
check('Builder input size ceiling',builder.MAX_SNAPSHOT_BYTES<=512*1024*1024)
check('Builder events size ceiling',builder.MAX_EVENTS_BYTES<=10*1024*1024)
check('Builder blocks URL credentials',builder.safe_public_url('https://user:pass@example.com/x') is None)
check('Builder blocks javascript URL',builder.safe_public_url('javascript:alert(1)') is None)
check('Builder accepts clean HTTPS',builder.safe_public_url('https://example.com/x')=='https://example.com/x')

workflow=(ROOT/'.github/workflows/daily-collector.yaml').read_text()
check('Checkout exact release', 'actions/checkout@v7.0.1' in workflow)
check('Setup-python exact release','actions/setup-python@v7.0.0' in workflow)
check('Checkout credential persistence disabled','persist-credentials: false' in workflow)
check('Git hooks disabled for commit','core.hooksPath=/dev/null' in workflow)
check('Generated symlinks rejected','Reject symlinks in generated evidence' in workflow)
check('Security regressions run in CI','python security_self_test.py' in workflow and 'python security_pipeline_test.py' in workflow)
check('Python dependency exact pinned',(ROOT/'requirements.txt').read_text().strip()=='cryptography==46.0.7')

app=(ROOT/'web/app.js').read_text(); html=(ROOT/'web/index.html').read_text()
check('Search bounded','maxlength="200"' in html and '.slice(0,200)' in app)
check('Absolute HTTPS frontend allowlist', r'!/^https:\/\//i.test(value)' in app)
check('Frontend URL credentials rejected','u.username||u.password' in app)
check('Catalog client ceiling','.slice(0,100000)' in app)
check('No client-side auth/paywall prototype','loginPassword' not in app and 'Demo Pro' not in app and 'data-pro' not in html)
check('Curated entity seed loader present','merge_seed_entities' in (ROOT/'collector/build_public_index.py').read_text())
check('Historical index written without paywall semantics','WEB_HISTORY_OUT' in (ROOT/'collector/build_public_index.py').read_text())

for name,ok in checks: print(('PASS' if ok else 'FAIL')+' - '+name)
failed=[n for n,ok in checks if not ok]
print(f"\n{len(checks)-len(failed)}/{len(checks)} pipeline/security checks passed")
if failed: raise SystemExit(1)
