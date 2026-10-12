"""Verificações por regra (determinísticas, sem LLM).

Cada regra recebe o Doc e devolve RuleResult(score em {0, 0.5, 1}, evidência, trechos).
Para itens 'R' a regra é a nota final; para 'RL' ela pré-filtra trechos e serve de
nota provisória quando não há LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .extract import Doc

MONTHS = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'


@dataclass
class RuleResult:
    score: float
    evidence: str = ''
    snippets: list[str] = field(default_factory=list)
    note: str = ''


def _snip(text: str, m: re.Match, width: int = 160) -> str:
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return re.sub(r'\s+', ' ', text[a:b]).strip()


def _first(rx: str, text: str, flags=re.I) -> tuple[re.Match | None, str]:
    m = re.search(rx, text, flags)
    return (m, _snip(text, m)) if m else (None, '')


def title_type(doc: Doc) -> RuleResult:
    t = doc.title
    m, _ = _first(r'systematic (literature )?(review|mapping|map)|mapping study|scoping (review|study)|tertiary (study|review)|'
                  r'meta-?analysis|qualitative (evidence )?synthesis|meta-?synthesis|thematic synthesis|rapid review|'
                  r'realist (synthesis|review)|secondary stud', t)
    if m:
        return RuleResult(1, t, note='Título identifica o tipo de estudo.')
    m, _ = _first(r'review|survey|state of the art|literature|overview', t)
    if m:
        return RuleResult(0.5, t, note='Título diz revisão/survey, sem indicar que é sistemática.')
    return RuleResult(0, t, note='Título não identifica o tipo de estudo.')


def abstract_structured(doc: Doc) -> RuleResult:
    a = doc.abstract
    if not a:
        return RuleResult(0, note='Resumo não localizado no PDF.')
    sep = r'\s*[:\-–—]'
    labels = {
        'contexto': rf'\b(background|context|motivation|problem){sep}',
        'objetivo': rf'\b(objectives?|aims?|goals?|purpose){sep}',
        'métodos': rf'\b(methods?|methodology|approach|design){sep}',
        'resultados': rf'\b(results?|findings){sep}',
        'conclusão': rf'\b(conclusions?|implications?){sep}',
    }
    found = [k for k, rx in labels.items() if re.search(rx, a, re.I)]
    sc = 1 if len(found) >= 4 else 0.5 if len(found) >= 2 else 0
    return RuleResult(sc, a[:400], [a[:1200]], note=f'Rótulos encontrados no resumo: {", ".join(found) or "nenhum"}.')


def research_questions(doc: Doc) -> RuleResult:
    t = doc.body
    rqs = set(re.findall(r'\bRQ\s?-?(\d+)', t))
    m, sn = _first(r'research questions?', t)
    m2, sn2 = _first(r'(the )?(main )?(objective|aim|goal) of this (study|review|paper|work|article)|this (study|review|paper) aims', t)
    if len(rqs) >= 2 or (m and re.search(r'\?', sn)):
        return RuleResult(1, sn or sn2, [s for s in (sn, sn2) if s], f'{len(rqs)} questões RQn detectadas.')
    if m or m2:
        return RuleResult(0.5, sn or sn2, [s for s in (sn, sn2) if s], 'Objetivo/questões citados sem lista explícita.')
    return RuleResult(0, note='Nenhuma questão de pesquisa ou objetivo explícito encontrado.')


BASES = ['scopus', 'ieee xplore', 'acm digital library', 'acm dl', 'web of science', 'sciencedirect', 'springerlink',
         'springer link', 'google scholar', 'dblp', 'engineering village', 'compendex', 'inspec', 'wiley', 'ebsco',
         'semantic scholar', 'science direct']
_DATE_RE = re.compile(rf'\b{MONTHS}\.?\s+(?:\d{{1,2}},?\s+)?20\d{{2}}\b|\b20\d{{2}}[-/]\d{{1,2}}[-/]\d{{1,2}}\b|\b\d{{1,2}}[/.-]\d{{1,2}}[/.-]20\d{{2}}\b', re.I)


def search_sources(doc: Doc) -> RuleResult:
    t = doc.body
    low = t.lower()
    found = [b for b in BASES if b in low]
    snippets = []
    for b in found[:3]:
        i = low.find(b)
        snippets.append(re.sub(r'\s+', ' ', t[max(0, i - 160): i + 200]))
    date_ev = ''
    for m in _DATE_RE.finditer(t):
        ctx = t[max(0, m.start() - 220): m.end() + 220].lower()
        if 'search' in ctx or 'conducted' in ctx or 'retriev' in ctx:
            date_ev = _snip(t, m)
            break
    if date_ev:
        snippets.append(date_ev)
    if len(found) >= 2 and date_ev:
        return RuleResult(1, date_ev, snippets, f'{len(found)} bases e data de busca encontradas.')
    if found:
        return RuleResult(0.5, snippets[0], snippets, f'{len(found)} base(s) citada(s), sem data da busca.')
    return RuleResult(0, note='Nenhuma base de dados conhecida citada.')


def search_strings(doc: Doc) -> RuleResult:
    t = doc.body
    ops = re.findall(r'(?<![A-Za-z])(AND|OR)(?![A-Za-z])', t)
    m, sn = _first(r'search (string|query|strategy|terms?)', t)
    mb, snb = _first(r'\([^()]{3,200}\b(?:OR)\b[^()]{3,200}\)', t, 0)
    if len(ops) >= 3 and (mb or m):
        return RuleResult(1, snb or sn, [s for s in (snb, sn) if s], f'{len(ops)} operadores booleanos encontrados.')
    if ops or m:
        return RuleResult(0.5, sn or snb, [s for s in (sn, snb) if s], 'Estratégia citada, string completa não identificada.')
    return RuleResult(0, note='Nenhuma string ou estratégia de busca encontrada.')


def certainty(doc: Doc) -> RuleResult:
    t = doc.body
    m, sn = _first(r'\bGRADE\b|CERQual', t, 0)
    if m:
        return RuleResult(1, sn, [sn], 'GRADE ou GRADE-CERQual citado.')
    m, sn = _first(r'certainty of (the )?evidence|confidence in the (body of )?evidence|strength of (the )?evidence|quality of (the )?evidence', t)
    if m:
        return RuleResult(0.5, sn, [sn], 'Menção genérica à certeza/força da evidência.')
    return RuleResult(0, note='Sem menção a certeza da evidência.')


def selection_flow(doc: Doc) -> RuleResult:
    t = doc.body
    flow, sf = _first(r'flow (diagram|chart)|prisma|study selection process|selection process|selection procedure', t)
    counts = re.findall(r'\b\d{1,5}\s+(?:papers|studies|articles|records|publications|primary studies|candidate)', t, re.I)
    snippets = [sf] if sf else []
    m, sc = _first(r'\b\d{1,5}\s+(?:papers|studies|articles|records|publications|primary studies)', t)
    if sc:
        snippets.append(sc)
    if flow and re.search(r'flow (diagram|chart)|prisma', t, re.I) and len(counts) >= 3:
        return RuleResult(1, sf, snippets, f'Diagrama/fluxo citado e {len(counts)} contagens.')
    if flow or len(counts) >= 2:
        return RuleResult(0.5, sf or sc, snippets, f'Seleção citada com {len(counts)} contagens.')
    return RuleResult(0, note='Sem fluxo ou contagens de seleção.')


def registration(doc: Doc) -> RuleResult:
    m, sn = _first(r'PROSPERO|\bOSF\b|osf\.io|open science framework|registered (report|protocol|review)|pre-?regist\w+|'
                   r'(not|never) (been )?registered|was not registered|registration number', doc.body)
    return RuleResult(1, sn, [sn], 'Registro ou declaração de não registro.') if m else RuleResult(0, note='Sem informação de registro.')


def funding(doc: Doc) -> RuleResult:
    m, sn = _first(r'funded by|funding|financial support|supported by|\bgrants?\b|sponsor\w*|no (specific )?funding', doc.body)
    return RuleResult(1, sn, [sn], 'Declaração de financiamento encontrada.') if m else RuleResult(0, note='Sem declaração de financiamento.')


def coi(doc: Doc) -> RuleResult:
    m, sn = _first(r'conflicts? of interests?|competing interests?|declare[sd]? (that )?(they have )?no|no conflicts?', doc.body)
    return RuleResult(1, sn, [sn], 'Declaração de conflito de interesses encontrada.') if m else RuleResult(0, note='Sem declaração de conflitos.')


def data_availability(doc: Doc) -> RuleResult:
    m, sn = _first(r'zenodo|figshare|dryad|osf\.io|github\.com|gitlab|mendeley data|doi\.org/10\.5281', doc.body)
    if m:
        return RuleResult(1, sn, [sn], 'Repositório público citado.')
    m, sn = _first(r'replication package|supplementary material|data (is|are) available|available (online|at|upon)', doc.body)
    if m:
        return RuleResult(0.5, sn, [sn], 'Menciona disponibilidade sem repositório identificado.')
    return RuleResult(0, note='Sem informação de disponibilidade.')


RULES: dict[str, Callable[[Doc], RuleResult]] = {
    'title_type': title_type, 'abstract_structured': abstract_structured, 'research_questions': research_questions,
    'search_sources': search_sources, 'search_strings': search_strings, 'certainty': certainty,
    'selection_flow': selection_flow, 'registration': registration, 'funding': funding, 'coi': coi,
    'data_availability': data_availability,
}
