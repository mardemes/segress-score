"""Avaliação dos 28 itens do SEGRESS.

- Cada item: Sim = 1, Parcial = 0,5, Não = 0 (pontuação de Kitchenham et al., 2009, em estudos terciários de ES).
  Itens com subitens recebem Sim só quando todos os subitens obrigatórios são atendidos, Não quando nenhum é.
- Peso 2 nos itens críticos (informações essenciais da Tabela 2 do SEGRESS); peso 1 nos demais.
- Score = pontos obtidos / pontos possíveis nos itens obrigatórios verificados.
- Classificação pela regra do AMSTAR 2 (Shea et al., 2017): falha crítica = item crítico com Não,
  fraqueza = item não crítico com Não.
"""
from __future__ import annotations

from .checklist import SECTION_NAMES, SECTION_ORDER, applicability, load_checklist, load_items

VERDICT = {1.0: 'Sim', 0.5: 'Parcial', 0.0: 'Não'}
RATINGS = {'otimo': 'Ótimo', 'bom': 'Bom', 'ruim': 'Ruim', 'mruim': 'Muito ruim', 'ind': 'Indeterminado'}
MIN_COVERAGE = 0.7


def rate(flaws: int, weaknesses: int) -> str:
    if flaws > 1:
        return 'mruim'
    if flaws == 1:
        return 'ruim'
    return 'otimo' if weaknesses <= 1 else 'bom'


def _justify(kind: str, basis: list[dict], auto: float | None) -> str:
    if kind == '-':
        return 'Não se aplica a este tipo de estudo (Tabela 9).'
    if auto is None:
        return 'Não verificado: este item exige leitura e precisa do julgamento do LLM.'
    word = VERDICT[auto]
    if len(basis) == 1:
        r = basis[0]['result']
        return f'{word}: o artigo relata o que o item pede.' if auto == 1 else f"{word}: {r.get('missing') or r.get('note') or 'informação insuficiente'}"
    parts = []
    for b in basis:
        r = b['result']
        v = {1: 'atendido', 0.5: 'parcial'}.get(r['score'], 'ausente')
        why = '' if r['score'] == 1 else f" ({(r.get('missing') or r.get('note') or 'informação insuficiente').rstrip('.')})"
        parts.append(f"{b['code']} {v}{why}")
    return f"{word}: {'; '.join(parts)}."


def judge_item(item: dict, study_type: str, practice: bool, results: dict, overrides: dict) -> dict:
    subs = []
    for c in load_checklist():
        if c['item'] != item['id']:
            continue
        subs.append({'code': c['code'], 'title': c['title'], 'applies': applicability(c, study_type, practice),
                     'question': c['q'], 'result': results.get(c['code'])})
    req = [s for s in subs if s['applies'] == 'O']
    opt = [s for s in subs if s['applies'] == 'P']
    kind = 'O' if req else 'P' if opt else '-'
    basis = req if kind == 'O' else opt
    scores = [s['result']['score'] if s['result'] else None for s in basis]
    auto = None
    if basis and all(x is not None for x in scores):
        auto = 1.0 if all(x == 1 for x in scores) else 0.0 if all(x == 0 for x in scores) else 0.5
    override = overrides.get(item['id'])
    s = float(override) if override is not None else auto
    weight = 2 if item['critical'] else 1
    review = any(b['result'] and b['result'].get('needs_review') for b in basis) or (auto is None and kind != '-')
    return {
        'id': item['id'], 'title': item['title'], 'section': item['section'], 'critical': item['critical'],
        'applies': kind, 'weight': weight, 'auto': auto, 'override': override, 'score': s,
        'verdict': VERDICT.get(s) if s is not None else None, 'points': None if s is None else s * weight,
        'needs_review': review, 'justification': _justify(kind, basis, auto),
        'subitems': [{**{k: v for k, v in sb.items() if k != 'result'}, **(sb['result'] or {'score': None})} for sb in subs],
    }


def score(results: dict[str, dict], study_type: str, practice: bool = False, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    items = [judge_item(it, study_type, practice, results, overrides) for it in load_items()]
    req = [x for x in items if x['applies'] == 'O']
    verified = [x for x in req if x['score'] is not None]
    possible = sum(x['weight'] for x in req)
    v_possible = sum(x['weight'] for x in verified)
    got = sum(x['points'] for x in verified)
    coverage = v_possible / possible if possible else 0.0
    pct = 100 * got / v_possible if v_possible else 0.0
    flaws = [x['id'] for x in req if x['critical'] and x['score'] == 0]
    weak = [x['id'] for x in req if not x['critical'] and x['score'] == 0]
    pending = [x['id'] for x in req if x['score'] is None]
    rating = 'ind' if coverage < MIN_COVERAGE else rate(len(flaws), len(weak))
    sec: dict[str, list[float]] = {}
    for x in verified:
        a = sec.setdefault(x['section'], [0.0, 0.0])
        a[0] += x['points']
        a[1] += x['weight']
    return {
        'rating': rating, 'rating_name': RATINGS[rating], 'provisional': rating != 'ind' and bool(pending),
        'score': round(pct, 1), 'points': got, 'points_possible_verified': v_possible, 'points_possible': possible,
        'coverage': round(coverage, 2), 'critical_flaws': flaws, 'weaknesses': weak, 'pending': pending,
        'required_items': len(req), 'items_met': sum(1 for x in req if x['score'] == 1),
        'by_section': {k: {'name': SECTION_NAMES[k], 'score': round(100 * sec[k][0] / sec[k][1], 1)}
                       for k in SECTION_ORDER if k in sec and sec[k][1]},
        'items': items, 'study_type': study_type, 'practice': practice,
    }
