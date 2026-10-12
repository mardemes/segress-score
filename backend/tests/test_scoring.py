from app.checklist import load_checklist
from app.scoring import score


def results_all(value, items=None, study_type='quant'):
    return {it['code']: {'score': value, 'method': 'llm'} for it in (items or load_checklist())}


def test_checklist_has_42_items():
    items = load_checklist()
    assert len(items) == 42
    assert len({it['code'] for it in items}) == 42
    assert all(it['weight'] in (1, 2, 3) for it in items)


def test_perfect_score_is_100_level_a():
    r = score(load_checklist(), results_all(1.0), 'quant')
    assert r['score'] == 100.0 and r['level'] == 'A' and not r['capped'] and r['coverage'] == 1.0


def test_all_zero_is_level_e():
    r = score(load_checklist(), results_all(0.0), 'quant')
    assert r['score'] == 0 and r['level'] == 'E' and r['capped']


def test_critical_cap_limits_level_to_c():
    res = results_all(1.0)
    res['6']['score'] = 0.0      # item crítico (peso 3) ausente
    r = score(load_checklist(), res, 'quant')
    assert r['capped'] and r['score'] <= 74.99 and r['level'] == 'C' and '6' in r['critical_missing']


def test_not_applicable_items_leave_the_denominator():
    items = load_checklist()
    res = results_all(1.0)
    r = score(items, res, 'mapping')
    applicable = [i for i in r['items'] if i['applies'] != '-']
    assert len(applicable) < 42
    assert r['score'] == 100.0    # itens N/A não penalizam


def test_tertiary_drops_items_14_and_15():
    r = score(load_checklist(), results_all(1.0), 'quant', tertiary=True)
    by = {i['code']: i for i in r['items']}
    assert by['14']['applies'] == '-' and by['15']['applies'] == '-'


def test_optional_items_only_add_bonus_up_to_5():
    res = results_all(1.0)
    for code in ('24a', '27'):
        res[code]['score'] = 0.0
    r = score(load_checklist(), res, 'quant')
    assert r['base'] == 100.0 and r['bonus'] == 0.0 and r['score'] == 100.0
    res2 = results_all(0.5)
    r2 = score(load_checklist(), res2, 'quant')
    assert r2['bonus'] == 2.5 and r2['base'] == 50.0


def test_unverified_items_are_excluded_and_lower_coverage():
    res = results_all(None)
    res['1'] = {'score': 1.0}
    r = score(load_checklist(), res, 'quant')
    assert r['coverage'] < 0.7 and r['partial'] and r['level'] is None


def test_human_override_wins():
    res = results_all(0.0)
    res['4']['override'] = 1.0
    r = score(load_checklist(), res, 'quant')
    assert {i['code']: i for i in r['items']}['4']['score'] == 1.0
