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
def load_checklist() -> list[dict]:
    path = Path(__file__).with_name('checklist.yaml')
    items = yaml.safe_load(path.read_text(encoding='utf-8'))
    for it in items:
        it['code'] = str(it['code'])
        it.setdefault('kw', [])
        it.setdefault('absent', 'Não há informação sobre isso no artigo.')
        assert len(it['applies']) == 3, it['code']
    return items


def applicability(item: dict, study_type: str, tertiary: bool = False) -> str:
    """'O' (obrigatório), 'P' (opcional) ou '-' (não se aplica) para o tipo de estudo."""
    if tertiary and item['code'] in ('14', '15'):
        return '-'   # estudos sobre práticas de pesquisa em ES (SEGRESS, itens 14 e 15)
    return item['applies'][TYPE_INDEX[study_type]]
