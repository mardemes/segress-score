"""Orquestra extração, classificação e verificações (regras + LLM)."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import llm
from .checklist import applicability, load_checklist
from .classify import classify
from .extract import Chunk, Doc, extract
from .rules import RULES, RuleResult

log = logging.getLogger('segress')
MAX_CONTEXT_CHARS = 7000
TOP_CHUNKS = 6


def analyze(pdf_path: str) -> tuple[Doc, dict]:
    doc = extract(pdf_path)
    llm_res = None
    if llm.available() and doc.pages:
        try:
            llm_res = llm.classify(doc)
        except Exception as e:  # classificação por regras continua valendo
            log.warning('classificação por LLM falhou: %s', e)
    return doc, classify(doc, llm_res)


def retrieve(doc: Doc, item: dict) -> list[str]:
    """Trechos mais relevantes: palavras-chave do item + bônus para as seções indicadas."""
    kws = [k.lower() for k in item.get('kw', [])]
    wanted = set(item.get('sec', []))
    scored: list[tuple[float, Chunk]] = []
    for c in doc.chunks:
        if c.section == 'references':
            continue
        low = c.text.lower()
        hits = sum(1 for k in kws if k in low)
        bonus = 1.5 if c.section in wanted else 0
        sc = hits + (bonus if hits or not kws else 0)
        if sc > 0:
            scored.append((sc, c))
    scored.sort(key=lambda x: -x[0])
    out, total = [], 0
    for _, c in scored[:TOP_CHUNKS]:
        part = f'[p.{c.page}][{c.section}] {c.text}'
        if total + len(part) > MAX_CONTEXT_CHARS:
            break
        out.append(part)
        total += len(part)
    if not out:   # fallback: início das seções indicadas, para o modelo concluir "ausente" com contexto
        for name in item.get('sec', []):
            txt = doc.sections.get(name)
            if txt:
                out.append(f'[{name}] {txt[:2500]}')
    if not out:
        out.append('[início do texto] ' + doc.text[:2500])
    return out


def _from_rule(rr: RuleResult, doc: Doc, provisional: bool) -> dict:
    page = doc.page_of(rr.evidence) if rr.evidence else None
    return {
        'score': rr.score, 'evidence': rr.evidence, 'page': page, 'missing': '' if rr.score == 1 else rr.note,
        'note': rr.note, 'confidence': 0.5 if provisional else (0.9 if rr.score in (0, 1) else 0.6),
        'method': 'rule', 'verified': True, 'needs_review': provisional or rr.score == 0.5,
    }


def run_item(item: dict, doc: Doc, study_type: str, use_llm: bool) -> dict:
    rr = RULES[item['rule']](doc) if item.get('rule') else None
    method = item['method']
    if method == 'R':
        return _from_rule(rr, doc, provisional=False)
    if use_llm:
        try:
            passages = retrieve(doc, item)
            if rr and rr.snippets:
                passages = [f'[regra] {s}' for s in rr.snippets[:2]] + passages
            out = llm.check_item(item, passages, doc, study_type)
            out['method'] = 'llm'
            if rr:
                out['rule_score'] = rr.score
            return out
        except Exception as e:
            log.warning('item %s: LLM falhou (%s); usando regra', item['code'], e)
            if rr:
                res = _from_rule(rr, doc, provisional=True)
                res['note'] = f'LLM indisponível ({type(e).__name__}); nota provisória por regra.'
                return res
    elif rr:
        return _from_rule(rr, doc, provisional=True)
    return {'score': None, 'evidence': '', 'page': None, 'missing': '', 'confidence': None, 'method': 'unverified',
            'verified': False, 'needs_review': True,
            'note': 'Item verificável apenas por LLM; defina ANTHROPIC_API_KEY para avaliá-lo.'}


def run_checks(doc: Doc, study_type: str, tertiary: bool = False,
               progress: Callable[[int, int], None] | None = None, workers: int = 4) -> dict[str, dict]:
    items = [it for it in load_checklist() if applicability(it, study_type, tertiary) != '-']
    use_llm = llm.available()
    results: dict[str, dict] = {}
    done = 0

    def work(it):
        return it['code'], run_item(it, doc, study_type, use_llm)

    with ThreadPoolExecutor(max_workers=workers if use_llm else 1) as ex:
        for code, res in ex.map(work, items):
            results[code] = res
            done += 1
            if progress:
                progress(done, len(items))
    return results
