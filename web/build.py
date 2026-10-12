"""Gera segress-score.html (página única) a partir do template e do checklist do backend."""
import json, pathlib, yaml
here = pathlib.Path(__file__).parent
items = yaml.safe_load((here.parent / 'backend/app/checklist.yaml').read_text(encoding='utf-8'))
for it in items:
    it['code'] = str(it['code']); it.setdefault('kw', []); it.setdefault('absent', 'Não há informação sobre isso no artigo.')
html = (here / 'app.template.html').read_text(encoding='utf-8')
html = html.replace('/*__CHECKLIST__*/null', json.dumps(items, ensure_ascii=False))
(here / 'segress-score.html').write_text(html, encoding='utf-8')
print('ok', len(items), 'itens,', len(html) // 1024, 'KB')
