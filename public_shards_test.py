import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from collector.build_public_index import write_public_product

class PublicShardsTest(unittest.TestCase):
    def roundtrip(self, entities):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'history.json'
            product={'entities':entities,'schema_version':'test'}
            write_public_product(p,product,2048)
            manifest=json.loads(p.read_bytes())
            restored=[] if isinstance(entities,list) else {}
            for part in manifest['parts']:
                raw=(p.parent/part['path']).read_bytes()
                self.assertLessEqual(len(raw),2048)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),part['sha256'])
                self.assertEqual(len(raw),part['bytes'])
                row=json.loads(raw)['entities']
                if isinstance(restored,list):restored.extend(row)
                else:restored.update(row)
            self.assertEqual(restored,entities)
            before={f.name:f.read_bytes() for f in (p.parent/'chunks').iterdir()}
            write_public_product(p,{'entities':entities,'schema_version':'changed'},2048)
            self.assertTrue(all((p.parent/'chunks'/n).read_bytes()==v for n,v in before.items()))
    def test_dict(self):self.roundtrip({str(i):{'text':'á✨'*40} for i in range(15)})
    def test_list_order(self):self.roundtrip([{'name':str(i),'text':'ñ'*80} for i in range(15)])
    def test_small(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'catalog.json';v={'entities':[{'name':'a'}]}
            write_public_product(p,v,512);self.assertEqual(json.loads(p.read_bytes()),v)
    def test_large_entity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):write_public_product(Path(d)/'x.json',{'entities':{'a':{'text':'x'*1000}}},512)
if __name__=='__main__':unittest.main()
