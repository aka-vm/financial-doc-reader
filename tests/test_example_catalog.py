"""Public example metadata and balanced selection regressions; no model calls."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class ExampleCatalogTests(unittest.TestCase):
    def test_public_assets_and_tags(self):
        items = json.loads((ROOT / 'financial_brief/examples/catalog.json').read_text())
        self.assertEqual(len(items), 53)
        self.assertEqual(len({i['id'] for i in items}), 53)
        for item in items:
            with self.subTest(example=item['id']):
                self.assertTrue(1 <= len(item['tags']) <= 3)
                self.assertEqual(item['tags'][0], item['report_type'])
                self.assertFalse(item['fictional'])
                asset = ROOT / 'financial_brief/examples' / item['asset']
                self.assertEqual(asset.stat().st_size, item['size_bytes'])
                self.assertTrue(item['source_url'].startswith('https://'))
        self.assertGreaterEqual(len({i['report_type'] for i in items}), 7)

    @unittest.skipUnless(shutil.which('node'), 'Node required for gallery selection checks')
    def test_sampling_balances_types_in_a_skewed_catalog(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync('financial_brief/static/data-views.js','utf8'));
const items=JSON.parse(fs.readFileSync('financial_brief/examples/catalog.json','utf8'));
const appearances=new Map();
for(let n=0;n<1000;n++){
 const selected=randomExamples(items);
 assert.equal(selected.length,6);
 assert.equal(new Set(selected.map(i=>i.id)).size,6);
 assert.equal(new Set(selected.map(i=>i.report_type)).size,6);
 for(const item of selected)appearances.set(item.report_type,(appearances.get(item.report_type)||0)+1);
}
assert.equal(appearances.size,9);
// Broad bounds catch weighting by item count without a fragile random assertion.
for(const count of appearances.values())assert(count>500 && count<1001);
assert.deepEqual(randomExamples([]),[]);
assert.equal(randomExamples(items.slice(0,2)).length,2);
assert.equal(randomExamples(items,0).length,0);
'''
        subprocess.run(['node', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
