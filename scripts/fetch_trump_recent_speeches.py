from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
import re
import ssl
import time
import urllib.parse
import urllib.request

BASE = "https://www.presidency.ucsb.edu"
SEARCH_BASE = (
    "https://www.presidency.ucsb.edu/advanced-search?"
    "field-keywords=&field-keywords2=&field-keywords3=&from%5Bdate%5D=&to%5Bdate%5D=&"
    "person2=375125&items_per_page=100&order=field_docs_start_date_time_value&sort=desc"
)

OUT_DIR = Path("data/corpuses/trump/text")
MANIFEST = OUT_DIR / "_manifest.tsv"

TARGET_COUNT = 120
MAX_PAGES = 10
REQUEST_DELAY_SECONDS = 0.15

INCLUDE_TITLE_RE = re.compile(
    r"\b(speech|address|remarks?|interview|news conference|press conference|town hall|debate|fireside chat|exchange with reporters|conversation)\b",
    re.IGNORECASE,
)
EXCLUDE_TITLE_RE = re.compile(
    r"\b(press release|fact sheet|executive order|proclamation|memorandum|bill signed|pool reports?|statement by|statement on|veto|nomination)\b",
    re.IGNORECASE,
)

RE_RESULTS_ROW = re.compile(
    r'<td class="views-field views-field-field-docs-start-date-time-value[^>]*>\s*(.*?)\s*</td>\s*'
    r'<td class="views-field views-field-field-docs-person[^>]*>.*?</td>\s*'
    r'<td class="views-field views-field-title"[^>]*>\s*<a href="(/documents/[^"]+)">(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
RE_TITLE_H1 = re.compile(r'<div[^>]*class="field-ds-doc-title"[^>]*>\s*<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
RE_DATE = re.compile(r'<div[^>]*class="field-docs-start-date-time"[^>]*>\s*<span[^>]*>(.*?)</span>', re.IGNORECASE | re.DOTALL)
RE_CONTENT = re.compile(r'<div[^>]*class="field-docs-content"[^>]*>(.*?)</div>\s*</div>', re.IGNORECASE | re.DOTALL)
RE_TAG = re.compile(r"<[^>]+>")
RE_WHITESPACE = re.compile(r"[ \t]+")


@dataclass
class Candidate:
    url: str
    date_text: str
    title: str


@dataclass
class Document:
    url: str
    title: str
    date_text: str
    text: str


def fetch(url: str, context: ssl.SSLContext) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45, context=context) as resp:
        return resp.read().decode("utf-8", "ignore")


def strip_html(block: str) -> str:
    block = block.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    block = block.replace("</p>", "\n\n")
    block = block.replace("</li>", "\n")
    text = RE_TAG.sub("", block)
    text = unescape(text)

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        line = RE_WHITESPACE.sub(" ", line).strip()
        if line:
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")

    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)


def parse_doc(url: str, html: str) -> Document | None:
    m_title = RE_TITLE_H1.search(html)
    m_date = RE_DATE.search(html)
    m_content = RE_CONTENT.search(html)

    if not (m_title and m_content):
        return None

    title = strip_html(m_title.group(1)).replace("\n", " ").strip()
    date_text = strip_html(m_date.group(1)).strip() if m_date else ""
    text = strip_html(m_content.group(1))

    if not text or len(text) < 900:
        return None

    return Document(url=url, title=title, date_text=date_text, text=text)


def slugify(value: str) -> str:
    value = unescape(value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:120] if len(value) > 120 else value


def normalize_date_for_filename(date_text: str) -> str:
    date_text = date_text.strip()
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(date_text, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "undated"


def title_is_speech_like(title: str) -> bool:
    return bool(INCLUDE_TITLE_RE.search(title)) and not bool(EXCLUDE_TITLE_RE.search(title))


def gather_candidates(context: ssl.SSLContext) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()

    for page in range(MAX_PAGES):
        page_url = SEARCH_BASE if page == 0 else f"{SEARCH_BASE}&page={page}"
        html = fetch(page_url, context)

        rows = RE_RESULTS_ROW.findall(html)
        if not rows:
            break

        for date_raw, rel_url, title_raw in rows:
            url = urllib.parse.urljoin(BASE, rel_url)
            if url in seen:
                continue

            title = strip_html(title_raw).replace("\n", " ").strip()
            if not title_is_speech_like(title):
                continue

            seen.add(url)
            candidates.append(Candidate(url=url, date_text=strip_html(date_raw), title=title))

        if len(rows) < 20:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return candidates


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    context = ssl._create_unverified_context()
    candidates = gather_candidates(context)

    selected: list[Document] = []

    for idx, candidate in enumerate(candidates, start=1):
        if len(selected) >= TARGET_COUNT:
            break

        try:
            html = fetch(candidate.url, context)
        except Exception:
            continue

        doc = parse_doc(candidate.url, html)
        if doc is None:
            continue

        selected.append(doc)

        if idx % 20 == 0:
            print(f"Fetched {idx} candidate pages, kept {len(selected)}")

        time.sleep(REQUEST_DELAY_SECONDS)

    manifest_rows = []
    used_names: set[str] = set()

    for i, doc in enumerate(selected, start=1):
        date_slug = normalize_date_for_filename(doc.date_text)
        title_slug = slugify(doc.title)
        base_name = f"{date_slug}_{title_slug}" if title_slug else f"{date_slug}_document_{i:04d}"
        name = f"{base_name}.txt"

        suffix = 2
        while name in used_names:
            name = f"{base_name}_{suffix}.txt"
            suffix += 1

        used_names.add(name)

        text = (
            f"Title: {doc.title}\n"
            f"Date: {doc.date_text}\n"
            f"Source: {doc.url}\n\n"
            f"{doc.text}\n"
        )

        out_path = OUT_DIR / name
        out_path.write_text(text, encoding="utf-8")

        manifest_rows.append(
            "\t".join([
                name,
                doc.date_text,
                str(len(doc.text)),
                doc.title,
                doc.url,
            ])
        )

    MANIFEST.write_text(
        "filename\tdate\tchars\ttitle\turl\n" + "\n".join(manifest_rows) + "\n",
        encoding="utf-8",
    )

    print(f"Collected {len(candidates)} candidates; fetched {len(selected)} recent speech-like documents into {OUT_DIR}")


if __name__ == "__main__":
    main()
