"""Classificação do tipo de estudo secundário (quantitativa, mapeamento, qualitativa).

Regras no título/resumo/início do texto; se houver LLM, ele confirma (ver llm.classify).
Também decide se o artigo é uma revisão sistemática (o SEGRESS só se aplica a elas).
"""
from __future__ import annotations

import re

from .extract import Doc

TYPES = {'quant': 'Revisão sistemática quantitativa', 'mapping': 'Mapeamento sistemático', 'qual': 'Revisão qualitativa'}

_MAPPING = r'systematic mapping|mapping study|systematic map\b|scoping (review|study)|mapping review'
_QUAL = (r'thematic synthesis|meta-?ethnograph|qualitative (evidence )?synthesis|meta-?synthesis|'
         r'realist (synthesis|review)|framework synthesis|qualitative (systematic )?review|meta-?narrative')
_QUANT = r'meta-?analysis|systematic (literature )?review|\bSLR\b|effect sizes?|rapid review'
_ANY_REVIEW = _MAPPING + '|' + _QUAL + '|' + _QUANT + r'|tertiary (study|review)|literature (review|survey)|\bsurvey\b'
_METHOD_SIGNALS = [
    r'inclusion criteria', r'exclusion criteria', r'search string', r'search (query|strategy)',
    r'primary studies', r'selected studies', r'data extraction', r'quality assessment',
    r'(digital libraries|databases)', r'snowballing', r'research questions?',
]


_EXECUTED = (r'\b(we|authors?|reviewers?) (independently )?(searched|selected|screened|included|excluded|extracted|retrieved|queried|collected)|'
             r'\bwere (included|excluded|selected|screened|retrieved)|searches? (was|were) (conducted|performed|executed|carried)|'
             r'\b(two|three|both) (reviewers|authors|researchers) (independently )?(screened|selected|extracted|assessed)')


def _count(rx: str, text: str) -> int:
    return len(re.findall(rx, text, re.I))


def classify_rules(doc: Doc) -> dict:
    head = f'{doc.title}\n{doc.abstract}'
    early = ' '.join(doc.pages[:3])
    reasons: list[str] = []

    review_in_head = bool(re.search(_ANY_REVIEW, head, re.I))
    tertiary = bool(re.search(r'tertiary (study|review)|(systematic )?review of (systematic )?reviews|mapping of (systematic )?(reviews|secondary studies)', head, re.I))
    signals = sum(1 for s in _METHOD_SIGNALS if re.search(s, doc.body, re.I))
    # o artigo precisa EXECUTAR uma revisão (não apenas falar sobre revisões, como um artigo de diretrizes)
    executed = _count(_EXECUTED, doc.body)
    guideline_title = bool(re.search(r'guidelines?|checklist|reporting standards?|framework for|protocol for|manifesto|position paper', doc.title, re.I))
    is_systematic = review_in_head and signals >= 4 and executed >= 2 and not (guideline_title and executed < 5)

    s_map = _count(_MAPPING, head) * 3 + _count(_MAPPING, early)
    s_qual = _count(_QUAL, head) * 3 + _count(_QUAL, early)
    s_quant = _count(_QUANT, head) * 3 + _count(_QUANT, early)

    if s_map and s_map >= s_qual and re.search(_MAPPING, head, re.I):
        stype = 'mapping'
        reasons.append('Título/resumo citam mapeamento sistemático ou scoping review.')
    elif s_qual and s_qual >= s_quant:
        stype = 'qual'
        reasons.append('Termos de síntese qualitativa no título/resumo.')
    elif s_quant or review_in_head:
        stype = 'quant'
        reasons.append('Revisão sistemática/meta-análise; sem sinais de mapeamento ou síntese qualitativa.')
    else:
        stype = None
    if tertiary:
        reasons.append('Estudo terciário: itens 14 e 15 deixam de se aplicar.')
    if not is_systematic:
        reasons.append(f'Poucos sinais de uma revisão executada pelos autores ({signals} de {len(_METHOD_SIGNALS)} marcadores de método; {executed} passagens de execução).')

    conf = 0.5
    if stype and review_in_head:
        conf = 0.75 if is_systematic else 0.5
    if not review_in_head:
        conf = 0.3
    return {
        'type': stype, 'tertiary': tertiary, 'is_systematic': is_systematic,
        'is_secondary_study': review_in_head or signals >= 4, 'confidence': conf,
        'reasons': reasons, 'source': 'rules',
    }


def classify(doc: Doc, llm_result: dict | None = None) -> dict:
    res = classify_rules(doc)
    if llm_result and llm_result.get('confidence', 0) >= 0.6:
        res.update(
            type=llm_result.get('type') or res['type'],
            tertiary=bool(llm_result.get('tertiary', res['tertiary'])),
            is_systematic=bool(llm_result.get('is_systematic', res['is_systematic'])),
            is_secondary_study=bool(llm_result.get('is_secondary_study', res['is_secondary_study'])),
            confidence=llm_result['confidence'], source='rules+llm',
        )
        if llm_result.get('reason'):
            res['reasons'].append(llm_result['reason'])
    res['supported'] = bool(res['type']) and res['is_systematic']
    if not res['supported']:
        res['message'] = ('O artigo não parece ser uma revisão sistemática (quantitativa, mapeamento ou qualitativa). '
                          'O SEGRESS não se aplica a revisões narrativas ou ad hoc; a nota pode não fazer sentido. '
                          'Você pode forçar o tipo, ciente dessa limitação.')
    return res
