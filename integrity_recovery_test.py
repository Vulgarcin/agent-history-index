"""Regression tests for explicit, hash-proved legacy newline transitions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collector import integrity as i

class LegacyLineEndingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(i, "ROOT", root).start()
        patch.object(i, "DATA", root / "data").start()
        self.rel = "data/snapshots/legacy.json"
        self.path = root / self.rel
        self.path.parent.mkdir(parents=True)
        self.raw = b'{\n  "value": 1\n}\n'
        self.path.write_bytes(self.raw)
        self.old = i.sha256_bytes(self.raw.replace(b"\n", b"\r\n"))
        self.new = i.sha256_bytes(self.raw)
        self.entries = []
        previous = i.ZERO_HASH
        for digest in (self.old, self.new):
            entry = {"artifact_path": self.rel, "artifact_sha256": digest,
                     "previous_entry_hash": previous}
            entry["entry_hash"] = i.sha256_bytes(i.canonical(entry))
            previous = entry["entry_hash"]
            self.entries.append(entry)
        self.manifest = i.DATA / "corrections/legacy-line-endings-2026-10-04.json"
        self.manifest.parent.mkdir()
        self.manifest.write_text(json.dumps({"correction_type": "verified_crlf_to_lf", "artifacts": [{
            "artifact_path": self.rel, "original_sha256": self.old,
            "normalized_sha256": self.new, "original_entry_hash": self.entries[0]["entry_hash"],
            "normalized_entry_hash": self.entries[1]["entry_hash"]}]}))

    def test_documented_transition(self):
        i.verify_chain(self.entries)
        i.assert_no_historical_mutation_or_deletion(self.entries, {self.rel: self.new})

    def test_undocumented_conflict(self):
        self.manifest.unlink()
        with self.assertRaises(RuntimeError): i.immutable_history(self.entries)

    def test_content_change(self):
        self.path.write_bytes(self.raw.replace(b"1", b"2"))
        with self.assertRaises(RuntimeError): i.immutable_history(self.entries)

    def test_additional_version(self):
        with self.assertRaises(RuntimeError): i.immutable_history(self.entries + [self.entries[-1]])

    def test_entry_binding(self):
        self.entries[1] = {**self.entries[1], "entry_hash": "0" * 64}
        with self.assertRaises(RuntimeError): i.immutable_history(self.entries)

    def test_deletion(self):
        with self.assertRaises(RuntimeError): i.assert_no_historical_mutation_or_deletion(self.entries, {})

    def test_post_correction_mutation(self):
        with self.assertRaises(RuntimeError):
            i.assert_no_historical_mutation_or_deletion(self.entries, {self.rel: "f" * 64})

if __name__ == "__main__": unittest.main()
