import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts.site_smoke import make_manifest, validate_manifest, verify_once


class SiteSmokeTests(unittest.TestCase):
    def test_manifest_selects_paper_and_all_local_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = {'index.html': '<script src="a.js"></script><link rel="stylesheet" href="a.css">',
                     'catalog/index.html': '<script src="../a.js"></script>',
                     'papers/area/paper/index.html': '<script src="https://cdn.example/a.js"></script>',
                     'a.js': 'script', 'a.css': 'css'}
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            manifest = make_manifest(root, 'a' * 40)
            validate_manifest(manifest, 'a' * 40)
            self.assertEqual(set(manifest['files']), set(files))
            with self.assertRaises(ValueError):
                validate_manifest(manifest, 'b' * 40)

    def test_exact_match_stale_html_and_http_failure(self):
        manifest = {'files': {'index.html': hashlib.sha256(b'new').hexdigest()}}
        with patch('scripts.site_smoke.urlopen', return_value=io.BytesIO(b'new')):
            self.assertEqual(verify_once(manifest, 'https://example.com/db-papers/'), [])
        with patch('scripts.site_smoke.urlopen', return_value=io.BytesIO(b'old')):
            self.assertIn('differs', verify_once(manifest, 'https://example.com/')[0])
        with patch('scripts.site_smoke.urlopen', side_effect=URLError('unavailable')):
            self.assertIn('unavailable', verify_once(manifest, 'https://example.com/')[0])

    def test_rejects_empty_and_unsafe_manifest(self):
        for files in ({}, {'../secret': 'a' * 64}, {'index.html': 'a' * 64,
                       'catalog/index.html': 'b' * 64, '/absolute': 'a' * 64}):
            with self.subTest(files=files), self.assertRaises(ValueError):
                validate_manifest({'sha': 'a' * 40, 'files': files}, 'a' * 40)
