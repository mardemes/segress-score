"""Cálculo da nota (ver a seção "Escala de pontuação" do documento de design)."""
from __future__ import annotations

from .checklist import SECTION_NAMES, SECTION_ORDER, applicability

LEVELS = [
    (90, 'A', 'Excelente'), (75, 'B', 'Bom'), (60, 'C', 'Adequado'), (40, 'D', 'Fraco'), (0, 'E', 'Insuficiente'),
]
CAP_WHEN_CRITICAL_MISSING = 74.9    # nível máximo C quando um item crítico obrigatório tem nota 0
MIN_COVERAGE = 0.7                  # abaixo disso a nota é parcial e o nível não é atribuído


def effective_score(res: dict | None) -> float | None:
    """Nota efetiva de um item: override humano, se houver; senão a automática (None = não verificado)."""
    if not res:
        return None
    if res.get('override') is not None:
        return float(res['override'])
    return res.get('score')


def level_for(total: float) -> tuple[str, str]:
    for floor, letter, name in LEVELS:
        if total >= floor:
            return letter, name
    return 'E', 'Insuficiente'


def score(items: list[dict], results: dict[str, dict], study_type: str, tertiary: bool = False) -> dict:
    req_num = req_den = opt_num = opt_den = 0.0
    verified_w = applicable_w = 0.0
    critical_zero: list[str] = []
    sec: dict[str, list[float]] = {}
    rows = []

    for it in items:
        kind = applicability(it, study_type, tertiary)
        res = results.get(it['code'])
        s = effective_score(res)
        w = it['weight']
        row = {
            'code': it['code'], 'title': it['title'], 'section': it['section'], 'weight': w, 'applies': kind,
            'score': s, 'auto_score': res.get('score') if res else None, 'override': res.get('override') if res else None,
            'evidence': (res or {}).get('evidence', ''), 'page': (res or {}).get('page'),
            'missing': (res or {}).get('missing', ''), 'confidence': (res or {}).get('confidence'),
            'method': (res or {}).get('method', 'none'), 'needs_review': (res or {}).get('needs_review', False),
            'verified': (res or {}).get('verified', False), 'question': it['q'], 'note': (res or {}).get('note', ''),
        }
        rows.append(row)
        if kind == '-':
            continue
        if kind == 'O':
            applicable_w += w
        if s is None:
            continue        # não verificado: fora do cálculo
        if kind == 'O':
            verified_w += w
            req_num += w * s
            req_den += w
            a = sec.setdefault(it['section'], [0.0, 0.0])
            a[0] += w * s
            a[1] += w
            if w == 3 and s == 0:
                critical_zero.append(it['code'])
        else:
            opt_num += w * s
            opt_den += w

    coverage = verified_w / applicable_w if applicable_w else 0.0
    base = 100 * req_num / req_den if req_den else 0.0
    bonus = 5 * opt_num / opt_den if opt_den else 0.0
    total = min(100.0, base + bonus)
    capped = bool(critical_zero)
    if capped:
        total = min(total, CAP_WHEN_CRITICAL_MISSING)
    partial = coverage < MIN_COVERAGE
    letter, name = (None, 'Indeterminado (cobertura insuficiente)') if partial else level_for(total)
    return {
        'score': round(total, 1), 'base': round(base, 1), 'bonus': round(bonus, 1),
        'level': letter, 'level_name': name, 'capped': capped, 'critical_missing': critical_zero,
        'coverage': round(coverage, 2), 'partial': partial,
        'by_section': {
            k: {'name': SECTION_NAMES[k], 'score': round(100 * sec[k][0] / sec[k][1], 1)}
            for k in SECTION_ORDER if k in sec and sec[k][1]
        },
        'items': rows, 'study_type': study_type, 'tertiary': tertiary,
    }
