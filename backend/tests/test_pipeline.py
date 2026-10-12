from app import llm, pipeline
from app.classify import classify_rules
from app.extract import extract, normalize
from app.rules import RULES


def test_extract_finds_title_abstract_and_sections(good_pdf):
    doc = extract(str(good_pdf))
    assert 'Test Flakiness' in doc.title
    assert 'Flaky tests undermine' in doc.abstract
    assert 'references' not in {c.section for c in doc.chunks if 'Scopus' in c.text}
    assert 'Someone' not in doc.body            # referências ficam fora do corpo


def test_classify_good_review_is_supported_quant(good_pdf):
    doc = extract(str(good_pdf))
    c = classify_rules(doc)
    assert c['type'] == 'quant' and c['is_systematic']


def test_classify_non_review_is_not_supported(bad_pdf):
    doc, cls = pipeline.analyze(str(bad_pdf))
    assert not cls['supported'] and 'message' in cls


def test_rules_on_good_review(good_pdf):
    doc = extract(str(good_pdf))
    assert RULES['title_type'](doc).score == 1
    assert RULES['abstract_structured'](doc).score == 1
    assert RULES['research_questions'](doc).score == 1
    assert RULES['search_sources'](doc).score == 1
    assert RULES['search_strings'](doc).score == 1
    assert RULES['certainty'](doc).score == 1
    assert RULES['selection_flow'](doc).score == 1
    assert RULES['registration'](doc).score == 1
    assert RULES['funding'](doc).score == 1
    assert RULES['coi'](doc).score == 1
    assert RULES['data_availability'](doc).score == 1


def test_rules_on_non_review(bad_pdf):
    doc = extract(str(bad_pdf))
    assert RULES['search_sources'](doc).score == 0
    assert RULES['registration'](doc).score == 0
    assert RULES['certainty'](doc).score == 0


def test_normalize_handles_hyphenation_and_quotes():
    assert normalize('non-\ndeterministic  “tests”') == normalize('nondeterministic "tests"')


def test_rules_only_mode_marks_llm_items_unverified(good_pdf):
    doc = extract(str(good_pdf))
    res = pipeline.run_checks(doc, 'quant')
    assert res['3']['method'] == 'unverified' and res['3']['score'] is None
    assert res['6']['method'] == 'rule' and res['6']['needs_review']      # RL sem LLM: nota provisória
    assert res['1']['method'] == 'rule' and not res['1']['needs_review']  # R puro: definitiva


def test_llm_mode_drops_hallucinated_quotes(good_pdf, monkeypatch):
    doc = extract(str(good_pdf))
    calls = {}

    class FakeBlock:
        type = 'tool_use'

        def __init__(self, inp):
            self.input = inp

    class FakeMsg:
        def __init__(self, inp):
            self.content = [FakeBlock(inp)]

    def fake_call(tool, system, prompt, max_tokens=700):
        calls['n'] = calls.get('n', 0) + 1
        if 'Two reviewers screened' in prompt or 'item codigo="8"' in prompt:
            return {'score': 1, 'evidence': 'Two reviewers screened each paper independently', 'missing': '', 'confidence': 0.9}
        return {'score': 1, 'evidence': 'texto inventado que não existe no artigo', 'missing': '', 'confidence': 0.9}

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'x')
    monkeypatch.setattr(llm, '_call', fake_call)
    res = pipeline.run_checks(doc, 'quant')
    assert res['8']['score'] == 1 and res['8']['verified'] and res['8']['page'] == 2
    assert res['3']['score'] == 0 and not res['3']['verified'] and res['3']['needs_review']
    assert calls['n'] > 30
