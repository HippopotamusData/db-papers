#!/usr/bin/env python3
"""Compare production HTML/assets to this run's Pages artifact, with bounded retry."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


class Assets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'script' and values.get('src'):
            self.urls.add(values['src'])
        if tag == 'link' and values.get('rel') == 'stylesheet' and values.get('href'):
            self.urls.add(values['href'])


def valid_path(path: str) -> bool:
    return bool(path) and not path.startswith('/') and all(
        part not in {'', '.', '..'} for part in path.split('/')
    ) and not any(char in path for char in '?#\\')


def make_manifest(site: Path, sha: str) -> dict:
    pages = ['index.html', 'catalog/index.html']
    papers = sorted(site.glob('papers/*/*/index.html'))
    if not papers:
        raise ValueError('no representative paper in site artifact')
    pages.append(papers[0].relative_to(site).as_posix())
    paths = set(pages)
    for page in pages:
        parser = Assets()
        parser.feed((site / page).read_text(encoding='utf-8'))
        for value in parser.urls:
            # Ignore explicitly external dependencies; verify every local CSS/JS.
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            resolved = urlsplit(urljoin('https://artifact.invalid/' + page, value)).path.lstrip('/')
            if not valid_path(resolved):
                raise ValueError(f'unsafe asset path: {value}')
            paths.add(resolved)
    return {'sha': sha, 'files': {
        path: hashlib.sha256((site / path).read_bytes()).hexdigest()
        for path in sorted(paths)
    }}


def verify_once(manifest: dict, base_url: str) -> list[str]:
    failures = []
    for path, expected in manifest['files'].items():
        request = Request(urljoin(base_url.rstrip('/') + '/', path),
                          headers={'Cache-Control': 'no-cache', 'User-Agent': 'db-papers-release-smoke'})
        try:
            with urlopen(request, timeout=20) as response:
                digest = hashlib.sha256(response.read()).hexdigest()
            if digest != expected:
                failures.append(f'{path}: content differs from deployed artifact')
        except (OSError, URLError) as exc:
            failures.append(f'{path}: {exc}')
    return failures


def validate_manifest(manifest: dict, sha: str) -> None:
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or manifest.get('sha') != sha:
        raise ValueError('smoke expectations must belong to the current commit')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files or len(files) > 100:
        raise ValueError('invalid smoke file list')
    if not {'index.html', 'catalog/index.html'} <= files.keys():
        raise ValueError('required smoke pages missing')
    for path, digest in files.items():
        if not valid_path(path) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('invalid smoke path or digest')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    manifest = sub.add_parser('manifest')
    manifest.add_argument('--site', type=Path, required=True)
    manifest.add_argument('--sha', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--url', required=True)
    verify.add_argument('--sha', required=True)
    args = parser.parse_args()
    if args.command == 'manifest':
        result = make_manifest(args.site, args.sha)
        validate_manifest(result, args.sha)
        print('manifest=' + json.dumps(result, separators=(',', ':')))
        return
    result = json.loads(os.environ['SITE_SMOKE_MANIFEST'])
    validate_manifest(result, args.sha)
    if urlsplit(args.url).scheme != 'https':
        raise ValueError('production smoke requires HTTPS')
    failures = []
    for attempt in range(6):
        failures = verify_once(result, args.url)
        if not failures:
            break
        print(f'Smoke attempt {attempt + 1}/6: ' + '; '.join(failures), flush=True)
        if attempt < 5:
            time.sleep(10)
    summary = f"[Published site]({args.url}) — Pages smoke {'FAILED' if failures else 'passed'}: `{args.sha}`, {len(result['files'])} pages/assets.\n"
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(summary)
    print(summary)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
