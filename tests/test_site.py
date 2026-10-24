import copy
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder', ROOT/'scripts/build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
DATA = json.loads((ROOT/'data/projects.json').read_text())


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags, self.ids, self.links, self.articles = [], [], [], []
        self.stack = []
        self.errors = []
        self.feed(text)
        assert not self.stack, self.stack
        assert not self.errors, self.errors

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs['href'])
        if tag == 'article':
            self.articles.append(attrs)
        if tag not in ('meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'col', 'embed', 'param', 'track'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.errors.append(tag)


@pytest.fixture
def built(tmp_path):
    builder.build(DATA, tmp_path)
    return tmp_path


def test_inventory_and_selection():
    inventory = json.loads((ROOT/'data/repositories.json').read_text())
    assert len(inventory) == len(set(inventory)) == 30
    assert [a['repo'] for a in DATA['audit']] == inventory
    assert [a['id'] for a in DATA['audit']] == [f'P{i:02}' for i in range(1, 31)]
    assert {a['repo'] for a in DATA['audit'] if a['included']} == {p['repo'] for p in DATA['projects']}
    assert all(a['reason'] for a in DATA['audit'])
    assert not {'egfr-resistance-docking', 'egfr-umbrella-sampling', 'portfolio-site'} & {p['repo'] for p in DATA['projects']}


@pytest.mark.parametrize('project', DATA['projects'], ids=lambda p:p['repo'])
def test_each_card_has_source_evidence(project, built):
    assert re.fullmatch('[0-9a-f]{40}', project['commit'])
    assert re.fullmatch('[0-9a-f]{64}', project['readme_sha256'])
    expected = f"https://github.com/Akkaya-Furkan/{project['repo']}/blob/{project['commit']}/README.md"
    assert project['url'] == expected
    doc = Document((built/'index.html').read_text())
    assert doc.links.count(expected) == 1
    assert project['repo'] in doc.ids
    assert f"{project['repo']}.html" in doc.links
    for name, field in project['fields'].items():
        assert field['text'] and field['raw']
        assert field['end'] - field['start'] + 1 == len(field['raw'].splitlines())
        text = builder.plain(field['raw'])
        if name == 'title':
            text = text.removeprefix('# ')
        if name == 'question':
            text = text.removeprefix('Question.').strip()
        assert ' '.join(text.split()) == ' '.join(field['text'].split())
        assert builder.esc(field['text']) in (built/f"{project['repo']}.html").read_text()


def test_all_links_and_fragments_resolve(built):
    docs = {p.name: Document(p.read_text()) for p in built.glob('*.html')}
    assert len(docs) == len(DATA['projects']) + 1
    allowed = {p['url'] for p in DATA['projects']}
    for filename, doc in docs.items():
        assert len(doc.ids) == len(set(doc.ids))
        assert sum(tag == 'h1' for tag, _ in doc.tags) == 1
        assert sum(tag == 'main' for tag, _ in doc.tags) == 1
        assert ('html', {'lang':'en'}) in doc.tags
        assert any(tag == 'meta' and attrs.get('name') == 'viewport' for tag, attrs in doc.tags)
        targets = doc.links + [a['href'] for t,a in doc.tags if t == 'link']
        for href in targets:
            url = urlsplit(href)
            if url.scheme:
                assert href in allowed
                continue
            target = unquote(url.path) or filename
            assert (built/target).is_file(), (filename, href)
            if url.fragment:
                assert unquote(url.fragment) in docs[target].ids, (filename, href)
    assert len(docs['index.html'].articles) == len(DATA['projects'])


def test_deterministic_build(built, tmp_path):
    other = tmp_path/'second'
    builder.build(DATA, other)
    def hashes(folder):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    assert hashes(built) == hashes(other)


@pytest.mark.parametrize('status,expected', [('', True), ('## Status\nPlanned — next steps', False), ('Status: **Planned**', False)])
def test_planned_status_is_never_an_achievement(status, expected):
    text = '# Example\n\n## Question\nCan it work?\n\n## Results\n3 outputs observed.\n\n## Limitations\nSmall sample.\n\n' + status
    fields, reason = builder.extract(text)
    assert bool(fields) == expected


@pytest.mark.parametrize('missing', ['Question', 'Results', 'Limitations'])
def test_missing_evidence_is_excluded(missing):
    text = '# Tool\n\n' + '\n\n'.join('## '+k+'\nActual text.' for k in ['Question','Results','Limitations'] if k != missing)
    assert builder.extract(text)[0] is None


def test_unfinished_result_is_excluded():
    assert builder.extract('# Tool\n## Question\nQuestion?\n## Results\nNot done yet.\n## Limitations\nNone evaluated.')[0] is None


def test_negative_result_is_eligible():
    fields, _ = builder.extract('# Tool\n## Question\nBenefit?\n## Results\n0/3 endpoints support improvement.\n## Limitations\nOne split.')
    assert fields['results']['text'] == '0/3 endpoints support improvement.'


def test_tables_preambles_and_list_boundaries():
    fields, _ = builder.extract('# Test\n## Question\nWorks?\n## Results\nSource table follows.\n\n| N |\n|---|\n| 9 |\n\n- 3/9 cases failed.\n- 6 passed.\n## Limitations\n- One cohort\n  only.\n- Not validated.')
    assert fields['results']['text'] == '3/9 cases failed.'
    assert fields['limitations']['text'] == 'One cohort only.'


def test_untrusted_readme_text_is_escaped(tmp_path):
    data = copy.deepcopy(DATA)
    data['projects'][0]['fields']['title']['text'] = '<script>alert("x")</script>'
    builder.build(data, tmp_path)
    assert '<script>' not in (tmp_path/'index.html').read_text()
    assert '&lt;script&gt;' in (tmp_path/'index.html').read_text()


def test_remote_verification_matches_snapshot():
    report = json.loads((ROOT/'docs/source-verification.json').read_text())
    assert report['verified'] == report['expected'] == len(DATA['projects'])
    assert {c['url'] for c in report['checks']} == {p['url'] for p in DATA['projects']}
    assert all(c['sha256_match'] and c['excerpts_match'] for c in report['checks'])


def test_pages_is_inert():
    text = (ROOT/'.github/workflows/pages.yml').read_text()
    assert 'workflow_dispatch:' in text
    assert 'if: ${{ false }}' in text
    assert not re.search(r'^\s+(push|schedule|pull_request):', text, re.M)


def test_no_external_runtime_or_contacts(built):
    for path in built.glob('*.html'):
        text = path.read_text()
        assert '<script' not in text
        assert 'mailto:' not in text and 'tel:' not in text
        assert not re.search(r'\b(?:192\.168\.|10\.\d+\.\d+\.|172\.(?:1[6-9]|2\d|3[01])\.)', text)
        assert not re.search(r'\b(?:[\w-]+\.)+(?:local|internal|home|lan)\b', text)


def test_refresh_removes_stale_generated_pages(built):
    stale = built/'removed-project.html'
    stale.write_text('<h1>Outdated claim</h1>')
    builder.build(DATA, built)
    assert not stale.exists()
    assert len(list(built.glob('*.html'))) == len(DATA['projects']) + 1
