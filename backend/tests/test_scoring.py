from app.checklist import load_checklist, load_items
from app.scoring import rate, score


def results_all(value, overrides=None):
    return {c['code']: {'score': value, 'method': 'llm'} for c in load_checklist()}


def test_checklist_has_the_28_items_of_table_9():
    items = load_items()
    assert len(items) == 28
    assert [i['id'] for i in items][:2] == ['opening', '1'] and items[-1]['id'] == '27'
    assert {i['id'] for i in items if i['critical']} == {'5', '6', '7', '8', '11', '13', '15', '16', '22', '23'}
    assert {c['item'] for c in load_checklist()} == {i['id'] for i in items}


def test_amstar2_rating_rule():
    assert rate(0, 0) == 'otimo' and rate(0, 1) == 'otimo'
    assert rate(0, 2) == 'bom'
    assert rate(1, 0) == 'ruim' and rate(1, 9) == 'ruim'
    assert rate(2, 0) == 'mruim'


def test_all_yes_is_otimo_100():
    r = score(results_all(1.0), 'quant')
    assert r['score'] == 100.0 and r['rating'] == 'otimo' and not r['critical_flaws'] and r['coverage'] == 1.0


def test_all_no_is_muito_ruim_0():
    r = score(results_all(0.0), 'quant')
    assert r['score'] == 0 and r['rating'] == 'mruim'


def test_one_critical_flaw_is_ruim_with_weighted_points():
    res = results_all(1.0)
    res['6']['score'] = 0.0                           # item 6 é crítico (peso 2)
    r = score(res, 'quant')
    assert r['rating'] == 'ruim' and r['critical_flaws'] == ['6']
    assert r['points_possible'] - r['points'] == 2   # perdeu 2 pontos


def test_item_with_subitems_is_partial_when_only_some_are_met():
    res = results_all(1.0)
    res['13e']['score'] = 0.0
    r = score(res, 'quant')
    it13 = {x['id']: x for x in r['items']}['13']
    assert it13['verdict'] == 'Parcial' and it13['points'] == 1.0 and '13e ausente' in it13['justification']
    assert r['rating'] == 'otimo'                     # parcial não é falha


def test_mapping_applicability_follows_table_9():
    r = score(results_all(1.0), 'mapping')
    by = {x['id']: x['applies'] for x in r['items']}
    assert by['15'] == '-' and by['22'] == '-' and by['14'] == '-' and by['21'] == '-'
    assert by['11'] == 'P' and by['18'] == 'P' and by['27'] == 'P'
    assert by['13'] == 'O' and by['16'] == 'O'      # 13a/13c e 16a são obrigatórios em mapeamentos


def test_practice_flag_drops_items_14_and_15():
    r = score(results_all(1.0), 'quant', practice=True)
    by = {x['id']: x['applies'] for x in r['items']}
    assert by['14'] == '-' and by['15'] == '-'


def test_optional_items_do_not_count():
    res = results_all(1.0)
    res['27']['score'] = 0.0                          # 27 é opcional para todos
    r = score(res, 'quant')
    assert r['score'] == 100.0 and r['rating'] == 'otimo'


def test_unverified_items_lower_coverage_and_make_rating_indeterminate():
    res = results_all(None)
    res['1'] = {'score': 1.0}
    r = score(res, 'quant')
    assert r['coverage'] < 0.7 and r['rating'] == 'ind'


def test_human_override_on_item_wins():
    r = score(results_all(0.0), 'quant', overrides={'4': 1.0})
    assert {x['id']: x for x in r['items']}['4']['verdict'] == 'Sim'
