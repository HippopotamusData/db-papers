#!/usr/bin/env python3
"""Build and verify the reader-facing GitHub Pages site."""

from __future__ import annotations

import argparse
import html
import json
import posixpath
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import yaml

from project_config import load_taxonomy, load_yaml


ROOT = Path(__file__).resolve().parents[1]
SITE_SOURCE = ROOT / "site_src"
SITE_OUTPUT = ROOT / "site"
SITE_ASSETS = ROOT / "site_assets"
SITE_CONFIG = ROOT / "site.generated.toml"
SITE_BASE_PATH = "/db-papers/"
MAX_SITE_BYTES = 512 * 1024 * 1024
PAPER_STATUS_LABELS = {
    "translated": "已审阅译文",
    "draft": "译文草稿",
    "source_only": "仅有原文",
    "skipped": "暂不翻译",
    "unavailable": "原文不可用",
}
FORBIDDEN_PUBLISHED_NAMES = {
    "paper.yaml",
}


@dataclass(frozen=True)
class Paper:
    area: str
    paper_id: str
    title: str
    title_zh: str
    authors: tuple[str, ...]
    year: int | None
    source_url: str
    topics: tuple[str, ...]
    reading_status: str
    rating: float | None
    paper_dir: Path


class ReferenceParser(HTMLParser):
    """Collect local references from generated HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(
        self, _tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append(value)


def fail(message: str) -> ValueError:
    return ValueError(message)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise fail(f"{label} must be a mapping")
    return value


def load_papers(root: Path) -> tuple[dict[str, Any], list[Paper]]:
    """Load site records from canonical metadata without inventing values."""

    taxonomy = load_taxonomy(root / "config/taxonomy.yaml")
    topic_order = {
        topic: index for index, topic in enumerate(taxonomy["topics"].keys())
    }
    papers: list[Paper] = []
    seen_ids: set[str] = set()

    for metadata_path in sorted((root / "papers").glob("*/*/paper.yaml")):
        data = _mapping(load_yaml(metadata_path), str(metadata_path))
        paper_dir = metadata_path.parent
        paper_id = paper_dir.name
        area = paper_dir.parent.name
        if paper_id in seen_ids:
            raise fail(f"duplicate paper id: {paper_id}")
        seen_ids.add(paper_id)
        if area not in taxonomy["areas"]:
            raise fail(f"{metadata_path}: unknown area: {area}")

        topics = data.get("topics")
        if not isinstance(topics, list) or not all(
            isinstance(topic, str) and topic in taxonomy["topics"]
            for topic in topics
        ):
            raise fail(f"{metadata_path}: topics must use the controlled taxonomy")

        status = data.get("reading_status")
        if status not in PAPER_STATUS_LABELS:
            raise fail(f"{metadata_path}: unsupported reading status: {status!r}")
        if status == "translated":
            translation = paper_dir / "translation.md"
            if not translation.is_file() or translation.is_symlink():
                raise fail(
                    f"{translation}: translated paper must have a regular "
                    "translation file"
                )

        rating_data = data.get("rating")
        rating: float | None = None
        if isinstance(rating_data, dict):
            raw_rating = rating_data.get("score")
            if isinstance(raw_rating, (int, float)) and not isinstance(
                raw_rating, bool
            ):
                rating = float(raw_rating)

        authors = data.get("authors")
        if not isinstance(authors, list) or not all(
            isinstance(author, str) and author for author in authors
        ):
            raise fail(f"{metadata_path}: authors must be a list of names")
        title = data.get("title")
        title_zh = data.get("title_zh")
        source_url = data.get("source_url")
        year = data.get("year")
        if not isinstance(title, str) or not title:
            raise fail(f"{metadata_path}: title must be non-empty")
        if not isinstance(title_zh, str) or not title_zh:
            raise fail(f"{metadata_path}: title_zh must be non-empty")
        if not isinstance(source_url, str) or not source_url.startswith(
            ("http://", "https://")
        ):
            raise fail(f"{metadata_path}: source_url must be HTTP(S)")
        if year is not None and (
            isinstance(year, bool) or not isinstance(year, int)
        ):
            raise fail(f"{metadata_path}: year must be an integer or null")

        papers.append(
            Paper(
                area=area,
                paper_id=paper_id,
                title=title,
                title_zh=title_zh,
                authors=tuple(authors),
                year=year,
                source_url=source_url,
                topics=tuple(sorted(topics, key=topic_order.__getitem__)),
                reading_status=status,
                rating=rating,
                paper_dir=paper_dir,
            )
        )

    area_order = {
        area: index for index, area in enumerate(taxonomy["areas"].keys())
    }
    papers.sort(key=lambda paper: (area_order[paper.area], paper.title.casefold()))
    return taxonomy, papers


def strip_translation_front_matter(paper: Paper) -> str:
    """Remove repository-only front matter from a canonical translation copy."""

    path = paper.paper_dir / "translation.md"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise fail(f"{path}: missing translation front matter")
    try:
        closing = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration as exc:
        raise fail(f"{path}: unterminated translation front matter") from exc
    header = yaml.safe_load("".join(lines[1:closing]))
    if not isinstance(header, dict):
        raise fail(f"{path}: front matter must be a mapping")
    expected = {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "language": "zh-CN",
        "source": "source.pdf",
    }
    for key, value in expected.items():
        if header.get(key) != value:
            raise fail(f"{path}: front matter {key} does not match paper metadata")
    body = "".join(lines[closing + 1 :]).lstrip("\n")
    if not body.startswith("# "):
        raise fail(f"{path}: translation body must start with a level-one heading")
    return body


def site_front_matter(paper: Paper, taxonomy: dict[str, Any]) -> str:
    topic_labels = [
        taxonomy["topics"][topic]["label_zh"] for topic in paper.topics
    ]
    data = {
        "title": paper.title,
        "description": f"《{paper.title_zh}》的中文全文译文与论文原文",
        "tags": topic_labels,
    }
    return (
        "---\n"
        + yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )
        + "---\n\n"
    )


def issue_url(paper: Paper) -> str:
    title = quote(f"译文反馈：{paper.title}")
    body = quote(
        "论文 ID："
        f"`{paper.paper_id}`\n\n"
        "请描述错译、漏译、公式、图表、链接或排版问题，并附上章节位置。"
    )
    return (
        "https://github.com/HippopotamusData/db-papers/issues/new"
        f"?title={title}&body={body}"
    )


def render_paper_page(paper: Paper, taxonomy: dict[str, Any]) -> str:
    body = strip_translation_front_matter(paper)
    heading, separator, remainder = body.partition("\n")
    if not separator:
        raise fail(f"{paper.paper_dir / 'translation.md'}: empty translation body")
    topic_labels = [
        taxonomy["topics"][topic]["label_zh"] for topic in paper.topics
    ]
    topics = "".join(
        f'<span class="topic-chip">{html.escape(label)}</span>'
        for label in topic_labels
    )
    year = str(paper.year) if paper.year is not None else "待考证"
    rating = f"{paper.rating:.1f} / 5" if paper.rating is not None else "暂未评分"
    area_label = taxonomy["areas"][paper.area]["label_zh"]
    meta = f"""
<div class="paper-meta">
  <dl>
    <div><dt>年份</dt><dd>{year}</dd></div>
    <div><dt>领域</dt><dd>{html.escape(area_label)}</dd></div>
    <div><dt>阅读评分</dt><dd>{rating}</dd></div>
    <div class="paper-meta__topics"><dt>主题</dt><dd><div class="topic-row">{topics}</div></dd></div>
  </dl>
  <div class="paper-actions">
    <a class="md-button md-button--primary" href="source.pdf" target="_blank" rel="noopener noreferrer">阅读原文</a>
    <a class="md-button" href="{html.escape(paper.source_url, quote=True)}" target="_blank" rel="noopener noreferrer">官方链接</a>
    <a class="md-button" href="{html.escape(issue_url(paper), quote=True)}" target="_blank" rel="noopener noreferrer">反馈译文问题</a>
    <a class="md-button" href="../">返回领域目录</a>
  </div>
</div>
""".strip()
    return (
        site_front_matter(paper, taxonomy)
        + heading
        + f'\n\n<p class="paper-title-zh paper-title-zh--page">{html.escape(paper.title_zh)}</p>'
        + "\n\n"
        + meta
        + "\n\n"
        + remainder.lstrip("\n")
    )


def paper_card(
    paper: Paper,
    taxonomy: dict[str, Any],
    *,
    translated_prefix: str,
) -> str:
    area_label = taxonomy["areas"][paper.area]["label_zh"]
    topic_labels = [
        taxonomy["topics"][topic]["label_zh"] for topic in paper.topics
    ]
    topic_chips = "".join(
        f'<span class="topic-chip">{html.escape(label)}</span>'
        for label in topic_labels
    )
    authors = "、".join(paper.authors)
    year = str(paper.year) if paper.year is not None else "年份待考证"
    rating = (
        f'<span class="paper-score">{paper.rating:.1f} 分</span>'
        if paper.rating is not None
        else '<span class="paper-score paper-score--empty">暂未评分</span>'
    )
    status_label = PAPER_STATUS_LABELS[paper.reading_status]
    search_text = " ".join(
        [
            paper.title,
            paper.title_zh,
            authors,
            paper.paper_id,
            area_label,
            *topic_labels,
            year,
        ]
    ).casefold()
    pdf_target = f"{translated_prefix}{paper.paper_id}/source.pdf"
    if paper.reading_status == "translated":
        target = f"{translated_prefix}{paper.paper_id}/"
        target_attributes = ""
    else:
        target = pdf_target
        target_attributes = ' target="_blank" rel="noopener noreferrer"'
    return f"""
<article class="paper-card"
  data-area="{html.escape(paper.area, quote=True)}"
  data-status="{html.escape(paper.reading_status, quote=True)}"
  data-topics="{html.escape(' '.join(paper.topics), quote=True)}"
  data-year="{paper.year if paper.year is not None else ""}"
  data-rating="{paper.rating if paper.rating is not None else ""}"
  data-search="{html.escape(search_text, quote=True)}">
  <div class="paper-card__eyebrow">
    <span>{html.escape(area_label)}</span>
    <span class="status-pill status-pill--{html.escape(paper.reading_status)}">{html.escape(status_label)}</span>
  </div>
  <h3><a href="{html.escape(target, quote=True)}"{target_attributes}>{html.escape(paper.title)}</a></h3>
  <p class="paper-card__title-zh">{html.escape(paper.title_zh)}</p>
  <p class="paper-card__authors">{html.escape(authors)}</p>
  <div class="topic-row">{topic_chips}</div>
  <footer>
    <span>{year}</span>
    {rating}
    <a href="{html.escape(pdf_target, quote=True)}" target="_blank" rel="noopener noreferrer"
      aria-label="阅读原文：{html.escape(paper.title, quote=True)}">阅读原文</a>
  </footer>
</article>
""".strip()


def render_home(taxonomy: dict[str, Any], papers: list[Paper]) -> str:
    statuses = Counter(paper.reading_status for paper in papers)
    areas = Counter(paper.area for paper in papers)
    area_cards = []
    for area, details in taxonomy["areas"].items():
        count = areas[area]
        if not count:
            continue
        area_cards.append(
            f"""
<a class="area-card" href="papers/{html.escape(area, quote=True)}/">
  <strong>{html.escape(details["label_zh"])}</strong>
  <span>{count} 篇论文</span>
  <p>{html.escape(details["description"])}</p>
</a>
""".strip()
        )
    return f"""---
title: 数据库系统论文档案馆
description: 数据库系统论文中文全文翻译集
---

<section class="site-hero">
  <p class="site-hero__kicker">DB PAPERS</p>
  <h1>数据库系统论文档案馆</h1>
  <p>本档案馆收录数据库系统领域具有代表性的论文，按研究领域和主题整理。提供论文原文和经过审校的中文译文。</p>
  <div class="site-hero__actions">
    <a class="md-button md-button--primary" href="catalog/">浏览全部论文</a>
  </div>
</section>

<section class="stat-grid" aria-label="收录统计">
  <div><strong>{len(papers)}</strong><span>论文记录</span></div>
  <div><strong>{statuses["translated"]}</strong><span>已审阅译文</span></div>
  <div><strong>{len(taxonomy["areas"])}</strong><span>研究领域</span></div>
</section>

## 从领域开始

<div class="area-grid">
{chr(10).join(area_cards)}
</div>

## 如何使用本档案馆

你可以按领域浏览，也可以在论文目录中搜索标题、作者或主题。每篇已完成的译文都有独立阅读页；遇到公式、实验数据或引用等需要精确核对的内容，可以随时打开原文对照。

目录中的评分用于判断论文是否值得优先阅读，综合考虑影响广度、技术价值、实际应用、长期生命力和阅读回报。评分不评价译文质量，也不依据作者、机构或会议声望。它只是基于现有证据的阅读参考，无法精确体现论文对不同读者的全部价值。

如果阅读时发现错译、漏译或排版问题，可以通过论文页的“反馈译文问题”告诉我们。
"""


def render_catalog(taxonomy: dict[str, Any], papers: list[Paper]) -> str:
    statuses = Counter(paper.reading_status for paper in papers)
    area_options = "\n".join(
        f'<option value="{html.escape(area, quote=True)}">{html.escape(details["label_zh"])}</option>'
        for area, details in taxonomy["areas"].items()
        if any(paper.area == area for paper in papers)
    )
    topic_options = "\n".join(
        f'<option value="{html.escape(topic, quote=True)}">{html.escape(details["label_zh"])}</option>'
        for topic, details in taxonomy["topics"].items()
        if any(topic in paper.topics for paper in papers)
    )
    status_options = "\n".join(
        f'<option value="{status}">{PAPER_STATUS_LABELS[status]}（{statuses[status]}）</option>'
        for status in PAPER_STATUS_LABELS
        if statuses[status]
    )
    cards = "\n".join(
        paper_card(paper, taxonomy, translated_prefix=f"papers/{paper.area}/")
        for paper in papers
    )
    return f"""---
title: 论文目录
description: 按领域、主题、状态和关键词浏览数据库论文
---

# 论文目录

可按关键词、领域、主题和状态筛选。已完成的译文可直接阅读，其他论文提供原文入口。

<div class="catalog-controls" role="search" aria-label="筛选和排序论文">
  <label class="catalog-search-field">
    <span>关键词</span>
    <input id="catalog-search" type="search" placeholder="中英文标题、作者、论文 ID…" autocomplete="off">
  </label>
  <div class="catalog-advanced">
    <button class="catalog-advanced__toggle" type="button"
      aria-expanded="false" aria-controls="catalog-advanced-fields">
      <span class="catalog-advanced__label">更多筛选与排序</span>
      <span class="catalog-advanced__meta">
        <span class="catalog-active-filters" id="catalog-active-filters" hidden></span>
        <svg class="catalog-advanced__chevron" viewBox="0 0 24 24"
          aria-hidden="true" focusable="false">
          <path d="m6 9 6 6 6-6"></path>
        </svg>
      </span>
    </button>
    <div class="catalog-advanced__fields" id="catalog-advanced-fields">
      <label>
        <span>领域</span>
        <select id="catalog-area">
          <option value="">全部领域</option>
          {area_options}
        </select>
      </label>
      <label>
        <span>主题</span>
        <select id="catalog-topic">
          <option value="">全部主题</option>
          {topic_options}
        </select>
      </label>
      <label>
        <span>状态</span>
        <select id="catalog-status">
          <option value="">全部状态</option>
          {status_options}
        </select>
      </label>
      <label>
        <span>排序</span>
        <select id="catalog-sort">
          <option value="default">默认顺序</option>
          <option value="year-desc">年份：从新到旧</option>
          <option value="year-asc">年份：从旧到新</option>
          <option value="rating-desc">评分：从高到低</option>
          <option value="rating-asc">评分：从低到高</option>
        </select>
      </label>
    </div>
  </div>
</div>

<p class="catalog-result"><strong id="catalog-count">{len(papers)}</strong> 篇论文</p>

<div class="paper-grid" id="paper-grid">
{cards}
</div>

<p class="catalog-empty" id="catalog-empty" hidden>没有符合当前筛选条件的论文。</p>
"""


def render_area(
    area: str,
    taxonomy: dict[str, Any],
    papers: list[Paper],
) -> str:
    details = taxonomy["areas"][area]
    area_papers = [paper for paper in papers if paper.area == area]
    translated = sum(
        paper.reading_status == "translated" for paper in area_papers
    )
    cards = "\n".join(
        paper_card(paper, taxonomy, translated_prefix="")
        for paper in area_papers
    )
    return f"""---
title: {details["label_zh"]}
description: {details["description"]}
---

# {details["label_zh"]}

{details["description"]}

<p class="area-summary"><strong>{len(area_papers)}</strong> 篇论文 · <strong>{translated}</strong> 篇已审阅译文</p>

<div class="paper-grid">
{cards}
</div>
"""


def _copy_regular_tree(source: Path, destination: Path) -> int:
    copied = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise fail(f"{path}: site resources may not contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise fail(f"{path}: site resource must be a regular file")
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def write_generated_config(
    root: Path,
    taxonomy: dict[str, Any],
    papers: list[Paper],
) -> None:
    """Add taxonomy-derived navigation without duplicating it in source config."""

    base_path = root / "zensical.toml"
    generated_path = root / SITE_CONFIG.name
    if not base_path.is_file() or base_path.is_symlink():
        raise fail("zensical.toml must be a regular file")
    if generated_path.is_symlink():
        raise fail(f"{generated_path}: refusing to replace a symlink")
    base = base_path.read_text(encoding="utf-8")
    marker = "\n[project.theme]\n"
    if base.count(marker) != 1:
        raise fail("zensical.toml must contain exactly one [project.theme] table")

    present_areas = {paper.area for paper in papers}
    area_entries = []
    for area, details in taxonomy["areas"].items():
        if area not in present_areas:
            continue
        label = json.dumps(details["label_zh"], ensure_ascii=False)
        target = json.dumps(f"papers/{area}/index.md", ensure_ascii=False)
        area_entries.append(f"    {{ {label} = {target} }}")
    nav = (
        "\nnav = [\n"
        '  { "开始" = [\n'
        '    { "首页" = "index.md" },\n'
        '    { "论文目录" = "catalog.md" },\n'
        "  ] },\n"
        '  { "论文领域" = [\n'
        + ",\n".join(area_entries)
        + ",\n"
        "  ] },\n"
        "]\n"
    )
    generated_path.write_text(
        base.replace(marker, nav + marker),
        encoding="utf-8",
    )


def prepare_site(root: Path, output: Path) -> dict[str, int]:
    """Generate a disposable reader tree without changing canonical papers."""

    root = root.resolve()
    output = output.resolve()
    if not output.is_relative_to(root) or output == root:
        raise fail("site source output must be a dedicated directory inside the repo")
    if output.is_symlink():
        raise fail(f"{output}: refusing to replace a symlink")
    taxonomy, papers = load_papers(root)
    translated = [paper for paper in papers if paper.reading_status == "translated"]
    static_source = root / "site_assets"
    if not static_source.is_dir() or static_source.is_symlink():
        raise fail("site_assets must be a regular directory")

    staging = Path(tempfile.mkdtemp(prefix=".site-src.", dir=root))
    copied_assets = 0
    try:
        (staging / "index.md").write_text(
            render_home(taxonomy, papers),
            encoding="utf-8",
        )
        (staging / "catalog.md").write_text(
            render_catalog(taxonomy, papers),
            encoding="utf-8",
        )
        copied_assets += _copy_regular_tree(static_source, staging)

        for area in taxonomy["areas"]:
            area_papers = [paper for paper in papers if paper.area == area]
            if not area_papers:
                continue
            area_dir = staging / "papers" / area
            area_dir.mkdir(parents=True, exist_ok=True)
            (area_dir / "index.md").write_text(
                render_area(area, taxonomy, papers),
                encoding="utf-8",
            )

        for paper in papers:
            source_pdf = paper.paper_dir / "source.pdf"
            if (
                not source_pdf.is_file()
                or source_pdf.is_symlink()
            ):
                raise fail(f"{source_pdf}: source PDF must be a regular file")
            target = staging / "papers" / paper.area / paper.paper_id
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_pdf, target / "source.pdf")

        for paper in translated:
            target = staging / "papers" / paper.area / paper.paper_id
            target.mkdir(parents=True, exist_ok=True)
            (target / "index.md").write_text(
                render_paper_page(paper, taxonomy),
                encoding="utf-8",
            )
            assets = paper.paper_dir / "assets"
            if assets.exists():
                if not assets.is_dir() or assets.is_symlink():
                    raise fail(f"{assets}: paper assets must be a regular directory")
                copied_assets += _copy_regular_tree(assets, target / "assets")

        validate_site_source(staging, taxonomy, papers)
        if output.exists():
            if not output.is_dir():
                raise fail(f"{output}: generated site source is not a directory")
            shutil.rmtree(output)
        staging.replace(output)
        write_generated_config(root, taxonomy, papers)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    summary = {
        "records": len(papers),
        "translated_pages": len(translated),
        "published_pdfs": len(papers),
        "copied_assets": copied_assets,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def validate_site_source(
    source: Path,
    taxonomy: dict[str, Any],
    papers: list[Paper],
) -> None:
    required = {Path("index.md"), Path("catalog.md")}
    required.update(
        Path("papers") / area / "index.md"
        for area in taxonomy["areas"]
        if any(paper.area == area for paper in papers)
    )
    required.update(
        Path("papers") / paper.area / paper.paper_id / "index.md"
        for paper in papers
        if paper.reading_status == "translated"
    )
    required.update(
        Path("papers") / paper.area / paper.paper_id / "source.pdf"
        for paper in papers
    )
    missing = sorted(
        path.as_posix() for path in required if not (source / path).is_file()
    )
    if missing:
        raise fail("generated site source is missing: " + ", ".join(missing))

    expected_paper_pages = {
        (paper.area, paper.paper_id)
        for paper in papers
        if paper.reading_status == "translated"
    }
    actual_paper_pages = {
        (path.parent.parent.name, path.parent.name)
        for path in source.glob("papers/*/*/index.md")
    }
    if actual_paper_pages != expected_paper_pages:
        raise fail("generated paper pages do not match translated papers")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise fail(f"{path}: generated site source contains a symlink")
        if path.name in FORBIDDEN_PUBLISHED_NAMES:
            raise fail(f"{path}: forbidden repository file entered site source")


def _resolve_local_reference(
    site: Path,
    page: Path,
    reference: str,
) -> Path | None:
    if not reference or reference.startswith("#"):
        return None
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith(SITE_BASE_PATH):
        path = path[len(SITE_BASE_PATH) :]
        candidate = site / path
    elif path.startswith("/"):
        raise fail(f"{page}: unexpected root-relative URL: {reference}")
    else:
        relative_parent = page.relative_to(site).parent.as_posix()
        normalized = posixpath.normpath(posixpath.join(relative_parent, path))
        if normalized == ".." or normalized.startswith("../"):
            raise fail(f"{page}: local URL escapes site root: {reference}")
        candidate = site / normalized
    if path.endswith("/"):
        candidate = candidate / "index.html"
    elif candidate.is_dir():
        candidate = candidate / "index.html"
    elif not candidate.exists() and not candidate.suffix:
        candidate = candidate / "index.html"
    return candidate


def check_site(root: Path, source: Path, site: Path) -> dict[str, int]:
    """Verify content boundaries, expected pages, size, and local HTML links."""

    taxonomy, papers = load_papers(root)
    validate_site_source(source, taxonomy, papers)
    if not site.is_dir() or site.is_symlink():
        raise fail(f"{site}: built site must be a regular directory")

    translated = [paper for paper in papers if paper.reading_status == "translated"]
    expected_html = {
        site / "index.html",
        site / "catalog" / "index.html",
        *(
            site / "papers" / paper.area / paper.paper_id / "index.html"
            for paper in translated
        ),
    }
    missing = sorted(
        path.relative_to(site).as_posix()
        for path in expected_html
        if not path.is_file()
    )
    if missing:
        raise fail("built site is missing expected HTML: " + ", ".join(missing))

    expected_pdfs = {
        site / "papers" / paper.area / paper.paper_id / "source.pdf"
        for paper in papers
    }
    missing_pdfs = sorted(
        path.relative_to(site).as_posix()
        for path in expected_pdfs
        if not path.is_file()
    )
    if missing_pdfs:
        raise fail(
            "built site is missing expected source PDFs: "
            + ", ".join(missing_pdfs)
        )

    total_bytes = 0
    file_count = 0
    html_files: list[Path] = []
    for path in site.rglob("*"):
        if path.is_symlink():
            raise fail(f"{path}: built site contains a symlink")
        if not path.is_file():
            continue
        file_count += 1
        total_bytes += path.stat().st_size
        if path.name in FORBIDDEN_PUBLISHED_NAMES:
            raise fail(f"{path}: forbidden repository file entered Pages artifact")
        if path.suffix.lower() == ".html":
            html_files.append(path)
    if total_bytes > MAX_SITE_BYTES:
        raise fail(
            f"Pages artifact is {total_bytes} bytes; limit is {MAX_SITE_BYTES}"
        )

    broken: list[str] = []
    checked_links = 0
    for page in html_files:
        parser = ReferenceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for reference in parser.references:
            target = _resolve_local_reference(site, page, reference)
            if target is None:
                continue
            checked_links += 1
            if not target.is_file():
                broken.append(
                    f"{page.relative_to(site).as_posix()}: {reference}"
                )
    if broken:
        preview = "\n".join(broken[:50])
        suffix = f"\n... and {len(broken) - 50} more" if len(broken) > 50 else ""
        raise fail(f"broken local links:\n{preview}{suffix}")

    summary = {
        "html_files": len(html_files),
        "files": file_count,
        "bytes": total_bytes,
        "checked_local_links": checked_links,
        "translated_pages": len(translated),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, default=SITE_SOURCE)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--source", type=Path, default=SITE_SOURCE)
    check_parser.add_argument("--site", type=Path, default=SITE_OUTPUT)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare_site(ROOT, args.output)
        else:
            check_site(ROOT, args.source, args.site)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
