"""Extração de texto de PDFs científicos com PyMuPDF.

Produz um objeto Doc com título, resumo, páginas, trechos (chunks) rotulados por
seção e página, e o corpo do texto sem a lista de referências.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pymupdf

HEADINGS = [
    ('abstract', r'abstract'),
    ('keywords', r'(index terms|keywords?)'),
    ('introduction', r'introduction'),
    ('background', r'(background|related work|literature review|motivation)'),
    ('methods', r'((research|review|study|search|systematic)\s+)?(method\w*|approach|protocol)(\s+and\s+\w+)?|review process|planning the review|conducting the review'),
    ('results', r'(results?|findings|analysis( of results)?|data synthesis|synthesis of results)(\s+and\s+discussion)?'),
    ('discussion', r'(discussion|implications?|answers? to research questions)'),
    ('threats', r'(threats to validity|limitations?)'),
    ('conclusion', r'(conclusions?|concluding remarks)(\s+and\s+future work)?'),
    ('acknowledgments', r'(acknowledg\w+|funding|declarations?|conflicts? of interest|competing interests?|data availability( statement)?)'),
    ('references', r'(references|bibliography)'),
]
_HEAD_RE = [
    (name, re.compile(r'^\s*(?:[0-9IVX]+(?:\.[0-9]+)*\.?\s+)?' + pat + r'\s*[:.]?\s*$', re.I))
    for name, pat in HEADINGS
]


def normalize(s: str) -> str:
    """Normalização usada para conferir se uma citação existe no texto."""
    s = unicodedata.normalize('NFKC', s)
    s = s.replace('­', '').replace('’', "'").replace('‘', "'")
    s = s.replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
    s = re.sub(r'(\w)-\s+(\w)', r'\1\2', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()


@dataclass
class Chunk:
    page: int
    section: str
    text: str


@dataclass
class Doc:
    title: str = ''
    abstract: str = ''
    pages: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    text: str = ''
    body: str = ''           # texto sem referências
    sections: dict[str, str] = field(default_factory=dict)
    num_pages: int = 0
    _norm_pages: list[str] = field(default_factory=list, repr=False)

    def page_of(self, quote: str) -> int | None:
        q = normalize(quote)
        if not q:
            return None
        if not self._norm_pages:
            self._norm_pages = [normalize(p) for p in self.pages]
        for i, p in enumerate(self._norm_pages):
            if q in p:
                return i + 1
        return None

    def contains(self, quote: str) -> bool:
        return normalize(quote) in normalize(self.text)


def _heading_of(line: str) -> str | None:
    line = line.strip()
    if not line or len(line) > 70:
        return None
    for name, rx in _HEAD_RE:
        if rx.match(line):
            return name
    return None


def _dehyphenate(text: str) -> str:
    return re.sub(r'(\w)-\n(\w)', r'\1\2', text)


def _guess_title(page: pymupdf.Page) -> str:
    try:
        spans = []
        for b in page.get_text('dict')['blocks']:
            for ln in b.get('lines', []):
                for sp in ln['spans']:
                    t = sp['text'].strip()
                    if t:
                        spans.append((round(sp['size'], 1), sp['origin'][1], t))
        if not spans:
            return ''
        top = max(s[0] for s in spans)
        ordered = sorted(spans, key=lambda s: s[1])
        parts = [t for size, y, t in ordered if size >= top - 0.6]
        title = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
        if len(title) > 250:   # fonte uniforme: usa só a primeira linha
            title = ordered[0][2]
        return title[:250]
    except Exception:
        return ''


def extract(pdf_path: str, max_pages: int = 80) -> Doc:
    pdf = pymupdf.open(pdf_path)
    doc = Doc(num_pages=len(pdf))
    if len(pdf) == 0:
        return doc
    doc.title = _guess_title(pdf[0])

    section = 'front'
    buf: list[str] = []
    buf_page = 1

    def flush():
        nonlocal buf
        text = re.sub(r'\s+', ' ', ' '.join(buf)).strip()
        if text:
            doc.chunks.append(Chunk(buf_page, section, text))
        buf = []

    for i, page in enumerate(pdf):
        if i >= max_pages:
            break
        raw = _dehyphenate(page.get_text('text'))
        doc.pages.append(raw)
        for line in raw.split('\n'):
            h = _heading_of(line)
            if h:
                flush()
                section = h
                buf_page = i + 1
                continue
            if not buf:
                buf_page = i + 1
            buf.append(line)
            joined_len = sum(len(x) + 1 for x in buf)
            if joined_len >= 900 and line.rstrip().endswith(('.', '?', ')')):
                flush()
        flush()

    doc.text = '\n'.join(doc.pages)
    by_sec: dict[str, list[str]] = {}
    for c in doc.chunks:
        by_sec.setdefault(c.section, []).append(c.text)
    doc.sections = {k: ' '.join(v) for k, v in by_sec.items()}

    doc.body = ' '.join(c.text for c in doc.chunks if c.section != 'references')
    doc.abstract = _extract_abstract(doc)
    return doc


def _extract_abstract(doc: Doc) -> str:
    early = [c.text for c in doc.chunks if c.section == 'abstract' and c.page <= 2]
    if early:
        return ' '.join(early)[:3000]
    first = ' '.join(doc.pages[:2])
    m = re.search(r'abstract\W{0,3}(.{200,3000}?)(?:index terms|keywords?|\n\s*(?:1\.?\s+)?introduction)', first, re.I | re.S)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()
    return ''
