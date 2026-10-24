import io
import json
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from financial_brief.bundles import prepare, relative_name
from financial_brief.server import create_app


class BundleTests(unittest.TestCase):
    def test_preserves_subdirectories_and_deduplicates_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'deal.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for name in ['deal/docs/exhibit.htm', 'deal/servicer/report.htm', 'deal/servicer/report.txt',
                             'deal/tapes/pool.csv', 'deal/manifest.json', '__MACOSX/._report.htm']:
                    z.writestr(name, 'text')
            paths, warnings = prepare([archive], folder)
            self.assertEqual([str(p.relative_to(folder)) for p in paths],
                             ['deal/docs/exhibit.htm', 'deal/servicer/report.htm', 'deal/tapes/pool.csv'])
            self.assertTrue(any('duplicate' in w for w in warnings))

    def test_rejects_archive_traversal_collisions_and_expansion(self):
        for names, message in [(['../escape.htm'], 'Invalid path'),
                               (['report.htm', 'report.htm'], 'Duplicate'),
                               (['nested.zip'], 'Nested ZIP')]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / 'deal.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    for name in names:
                        z.writestr(name, 'text')
                with self.assertRaisesRegex(ValueError, message):
                    prepare([archive], folder)
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'deal.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('large.htm', '123456')
            with patch('financial_brief.bundles.MAX_BYTES', 5), self.assertRaisesRegex(ValueError, 'expanded'):
                prepare([archive], folder)
        self.assertIsNone(relative_name('deal/.DS_Store'))
        self.assertIsNone(relative_name('__MACOSX/report.htm'))

    def test_abs_mode_accepts_folder_paths_and_more_than_five_files(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'DATA_DIR': directory, 'BACKEND': 'link', 'SECRET_KEY': 'test'})
            client = app.test_client()
            client.get('/').close()
            captured = []
            def build(paths, folder, *args):
                captured.extend(str(p.relative_to(folder)) for p in paths)
                return {'type': 'deal', 'title': 'Test deal', 'deal': {
                    'documents': [], 'months': [], 'waterfall': None, 'tapes': [], 'notes': [], 'read': []}}
            with patch('financial_brief.server.bundles.build_deal', side_effect=build):
                response = client.post('/api/briefs', headers={'X-Brief-Request': '1'},
                    data={'mode': 'deal', 'files': [(io.BytesIO(b'Test' * 40000), f'deal/servicer/report-{i}.htm') for i in range(6)]})
                self.assertEqual(response.status_code, 202)
                jid = response.json['id']
                for _ in range(100):
                    state = client.get(f'/api/briefs/{jid}').json
                    if state['status'] not in {'queued', 'running'}: break
                    threading.Event().wait(.01)
                self.assertEqual(state['status'], 'done', state.get('error'))
                self.assertEqual(state['report']['type'], 'deal')
                self.assertEqual(len(captured), 6)
                self.assertTrue(all(p.startswith('deal/servicer/') for p in captured))
                self.assertFalse(list(Path(directory).glob('upload-*')))
