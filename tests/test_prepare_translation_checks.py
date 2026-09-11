from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_translation_checks import prepare
from markdown_visibility import reader_visible_markdown
from normalize_translation_headers import normalize_text


class PrepareChecksTests(unittest.TestCase):
    def run_prepare(self, raw, *, headers=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        paper = root / 'paper'
        paper.mkdir()
        (paper / 'translation.md').write_text(raw)
        output = root / 'out'
        output.mkdir()
        manifest = root / 'manifest'
        manifest.write_text('header\n' + '\x1f'.join(['paper', str(paper), 'translated', '30', '', 'Title', 'warn']) + '\n')
        with patch('prepare_translation_checks.reader_visible_markdown', wraps=reader_visible_markdown) as parse:
            prepare(manifest, output, check_headers=headers)
        self.assertEqual(parse.call_count, 1)
        return output

    def test_prepares_shared_text_and_detects_noncanonical_header(self):
        raw = '# Title\n\n## 正文\n\n内容\n'
        output = self.run_prepare(raw)
        self.assertTrue((output / 'header-paper.error').exists())
        self.assertEqual((output / 'visible-paper.md').read_text(), reader_visible_markdown(raw))
        self.assertFalse((output / 'prepare-paper.error').exists())

    def test_canonical_hidden_and_fenced_text(self):
        raw = '# Title\n\n## 正文\n\n<!-- # Hidden -->\n\n```\n# Code\n```\n\n<div hidden>\n# Hidden HTML\n</div>\n\n## 正文\n内容\n'
        raw = normalize_text(raw, 'Title')
        output = self.run_prepare(raw)
        self.assertFalse(list(output.glob('*.error')))
        self.assertEqual(normalize_text(raw, 'Title', visible=reader_visible_markdown(raw)), raw)

    def test_empty_or_multiple_h1_fails_header_check(self):
        for raw in ('', '# First\n\n# Second\n'):
            output = self.run_prepare(raw)
            self.assertIn('expected exactly one H1', (output / 'prepare-paper.error').read_text())

    def test_standalone_validation_does_not_require_canonical_header(self):
        output = self.run_prepare('# Title\n', headers=False)
        self.assertFalse(list(output.glob('*.error')))
