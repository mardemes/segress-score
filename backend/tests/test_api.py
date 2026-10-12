from fastapi.testclient import TestClient

from app.main import app


def test_full_flow_rules_only(good_pdf):
    with TestClient(app) as c:
        h = c.get('/health').json()
        assert h['items'] == 28 and h['llm'] is False
        with open(good_pdf, 'rb') as f:
            r = c.post('/evaluations', files={'file': ('good.pdf', f, 'application/pdf')})
        assert r.status_code == 202
        eid = r.json()['id']
        ev = c.get(f'/evaluations/{eid}').json()
        assert ev['status'] == 'needs_confirmation' and ev['classification']['type'] == 'quant'
        assert c.get(f'/evaluations/{eid}/report').status_code == 409

        r = c.post(f'/evaluations/{eid}/confirm', json={'study_type': 'quant', 'practice': False})
        assert r.status_code == 202
        rep = c.get(f'/evaluations/{eid}/report').json()['report']
        assert rep['study_type'] == 'quant' and len(rep['items']) == 28
        assert rep['rating'] == 'ind'                        # sem LLM, cobertura baixa

        # ajuste humano muda a nota efetiva
        before = {i['id']: i for i in rep['items']}['3']['score']
        r = c.patch(f'/evaluations/{eid}/items/3', json={'score': 1})
        assert r.status_code == 200
        after = {i['id']: i for i in r.json()['report']['items']}['3']
        assert before is None and after['verdict'] == 'Sim' and after['override'] == 1

        # mudar o tipo reavalia
        c.patch(f'/evaluations/{eid}/study-type', json={'study_type': 'mapping', 'practice': False})
        rep2 = c.get(f'/evaluations/{eid}/report').json()['report']
        assert rep2['study_type'] == 'mapping'


def test_auto_mode_and_rejects(good_pdf, bad_pdf, tmp_path):
    with TestClient(app) as c:
        with open(good_pdf, 'rb') as f:
            eid = c.post('/evaluations', files={'file': ('g.pdf', f, 'application/pdf')}, data={'auto': 'true'}).json()['id']
        assert c.get(f'/evaluations/{eid}').json()['status'] == 'done'

        with open(bad_pdf, 'rb') as f:
            eid = c.post('/evaluations', files={'file': ('b.pdf', f, 'application/pdf')}, data={'auto': 'true'}).json()['id']
        ev = c.get(f'/evaluations/{eid}').json()
        assert ev['status'] == 'needs_confirmation' and not ev['classification']['supported']

        assert c.post('/evaluations', files={'file': ('x.pdf', b'not a pdf', 'application/pdf')}).status_code == 415
        assert c.get('/evaluations/' + 'a' * 32).status_code == 404
        assert c.get('/evaluations/../etc').status_code in (404, 405)
        assert c.get('/').status_code == 200
