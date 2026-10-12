from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

TYPE_INDEX = {'quant': 0, 'mapping': 1, 'qual': 2}
SECTION_NAMES = {
    'titulo_resumo': 'Título e resumo', 'introducao': 'Introdução', 'metodos': 'Métodos',
    'resultados': 'Resultados', 'discussao': 'Discussão', 'outras': 'Outras informações',
}
SECTION_ORDER = list(SECTION_NAMES)


@lru_cache(maxsize=1)
def _load() -> dict:
    data = yaml.safe_load(Path(__file__).with_name('checklist.yaml').read_text(encoding='utf-8'))
    ids = {it['id'] for it in data['items']}
    for c in data['checks']:
        c['code'] = str(c['code'])
        c.setdefault('kw', [])
        c.setdefault('absent', 'Não há informação sobre isso no artigo.')
        assert len(c['applies']) == 3 and c['item'] in ids, c['code']
    return data


def load_items() -> list[dict]:
    """Os 28 itens da Tabela 9 do SEGRESS (27 do PRISMA 2020 + Opening)."""
    return _load()['items']


def load_checklist() -> list[dict]:
    """Os subitens verificados (checks); cada um pertence a um item."""
    return _load()['checks']


def applicability(check: dict, study_type: str, practice: bool = False) -> str:
    """'O' (obrigatório), 'P' (opcional) ou '-' (não se aplica) para o tipo de estudo.

    practice=True: o estudo investiga práticas de pesquisa em ES; itens 14 e 15 não se aplicam (Tabela 9).
    """
    if practice and check['item'] in ('14', '15'):
        return '-'
    return check['applies'][TYPE_INDEX[study_type]]
