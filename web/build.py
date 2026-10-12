"""Gera segress-score.html (página única) a partir do template e do checklist do backend."""
import json, pathlib, yaml
here = pathlib.Path(__file__).parent
cl = yaml.safe_load((here.parent / 'backend/app/checklist.yaml').read_text(encoding='utf-8'))
for c in cl['checks']:
    c['code'] = str(c['code']); c.setdefault('kw', []); c.setdefault('absent', 'Não há informação sobre isso no artigo.')
html = (here / 'app.template.html').read_text(encoding='utf-8')
html = html.replace('/*__CHECKLIST__*/null', json.dumps(cl, ensure_ascii=False))
(here / 'segress-score.html').write_text(html, encoding='utf-8')
print('ok', len(cl['items']), 'itens,', len(cl['checks']), 'subitens,', len(html) // 1024, 'KB')
