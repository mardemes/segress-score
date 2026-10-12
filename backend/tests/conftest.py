import os
import sys
import tempfile
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SEGRESS_DATA', tempfile.mkdtemp(prefix='segress-test-'))
os.environ['SEGRESS_SYNC'] = '1'
os.environ.pop('ANTHROPIC_API_KEY', None)

GOOD_REVIEW = [
    '''A Systematic Literature Review on Test Flakiness in Software Engineering
Abstract
Background: Flaky tests undermine regression testing. Objective: We aim to synthesise evidence on causes of flakiness.
Method: We conducted a systematic literature review following Kitchenham guidelines. Results: 48 primary studies were selected.
Conclusion: Concurrency and order dependency dominate the reported causes.
Keywords: flaky tests, systematic review
1 Introduction
Flaky tests are a known problem. No systematic review exists that synthesises their causes, which motivates this study.
We address the following research questions: RQ1: What causes flakiness? RQ2: How is flakiness detected? RQ3: Which mitigations exist?
The objective of this study is to answer these questions.''',
    '''2 Method
We searched Scopus, IEEE Xplore, ACM Digital Library and Web of Science. The searches were conducted in March 2024 and the last search was on 2024-03-15.
The search string was (flaky OR flakiness OR "non-deterministic") AND (test OR testing) AND (software OR code). We also performed snowballing.
Inclusion criteria: peer-reviewed papers in English published between 2010 and 2023. Exclusion criteria: grey literature and short papers.
Two reviewers screened each paper independently and disagreements were resolved by consensus; Cohen's kappa was 0.82.
Data extraction was performed by one author and checked by a second author. Quality assessment used a checklist with 8 criteria.
The review protocol was registered on OSF (osf.io/abcde) and is available online.
We assessed the certainty of the evidence using GRADE.''',
    '''3 Results
The search returned 1,203 records. After removing duplicates 812 papers remained; 140 studies were read in full and 48 primary studies were included.
A flow diagram (Figure 1) summarises the PRISMA selection process. Table 3 lists the characteristics of the included primary studies.
RQ1: concurrency was the most common cause. Quality scores per study are in Table 4.
4 Discussion
Our results are consistent with previous reviews. Implications for practitioners include isolating tests. Future research should address detection.
Threats to validity: we used a single search engine for snowballing and the language restriction may bias the results.
Acknowledgments
This work was funded by grant 123 from a national agency. The authors declare no conflict of interest.
Data availability: the replication package is available at Zenodo (zenodo.org/record/1234).
References
[1] Someone. A paper. 2020.''',
]

NOT_REVIEW = [
    '''An Opinion Piece on Code Review Culture
Abstract
We reflect on how teams discuss pull requests and why culture matters more than tooling for lasting results.
1 Introduction
In this essay we share anecedotes about teams we have worked with. ''' + ('Culture shapes practice in many ways. ' * 30),
]


def make_pdf(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9)
    doc.save(str(path))
    return path


@pytest.fixture(scope='session')
def good_pdf(tmp_path_factory):
    return make_pdf(tmp_path_factory.mktemp('pdf') / 'good.pdf', GOOD_REVIEW)


@pytest.fixture(scope='session')
def bad_pdf(tmp_path_factory):
    return make_pdf(tmp_path_factory.mktemp('pdf') / 'bad.pdf', NOT_REVIEW)
