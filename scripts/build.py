"""Explicit local README snapshot refresh; deterministic, offline HTML generation."""
import argparse
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def plain(text):
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    return re.sub(r'^[*\-]\s+', '', re.sub(r'[*`]', '', text)).strip()


def paragraph(lines, start, end):
    while start < end and not lines[start].strip():
        start += 1
    stop = start
    while stop < end and lines[stop].strip() and (stop == start or not re.match(r'^[-*] ', lines[stop])):
        stop += 1
    return {'text': plain(' '.join(x.strip() for x in lines[start:stop])),
            'start': start + 1, 'end': stop, 'raw': '\n'.join(lines[start:stop])}


def extract(text):
    lines = text.splitlines()
    fields = {}
    title = next((i for i, line in enumerate(lines) if line.startswith('# ')), None)
    if title is not None:
        fields['title'] = dict(text=plain(lines[title][2:]), start=title+1,
                               end=title+1, raw=lines[title])
    headings = list(re.finditer(r'^## (.+)$', text, re.M))
    for heading in headings:
        key = heading.group(1).lower().strip()
        if key in ('question', 'results', 'limitations'):
            start = text[:heading.end()].count('\n') + 1
            end = next((i for i in range(start, len(lines)) if lines[i].startswith('## ')), len(lines))
            fields[key] = paragraph(lines, start, end)
            if key == 'results':
                # Prefer an interpretable measured paragraph over a table caption
                # or provenance preamble. Never rewrite a source claim.
                candidates = []
                i = start
                while i < end:
                    block = paragraph(lines, i, end)
                    if block['text'] and not block['raw'].lstrip().startswith(('|', '#', '![', '```')):
                        candidates.append(block)
                    i = max(i + 1, block['end'])
                fields[key] = next((b for b in candidates if re.search(r'\d', b['text']) and re.search(r'[.!?](?:\s|$)', b['text']) and not b['text'].endswith(':')), fields[key])
    if 'question' not in fields:
        for i, line in enumerate(lines):
            if line.startswith('**Question.**'):
                fields['question'] = paragraph(lines, i, len(lines))
                fields['question']['text'] = plain(fields['question']['text'].removeprefix('Question.').strip())
                break
    if re.search(r'(?im)^\s*(?:Planned\b|Status:\s*(?:\*\*)?Planned\b)', text):
        return None, 'Planned status'
    missing = [k for k in ('title', 'question', 'results', 'limitations') if not fields.get(k, {}).get('text')]
    if missing:
        return None, 'Missing evidence section: ' + ', '.join(missing)
    if re.search(r'(?i)^(?:not done|planned|not yet|pending)\b', fields['results']['text']):
        return None, 'Results explicitly unfinished'
    return fields, 'README question, results and limitations present'


def refresh(parent):
    inventory = json.loads((ROOT/'data/repositories.json').read_text())
    projects, audit = [], []
    for n, name in enumerate(inventory, 1):
        path = parent/name/'README.md'
        if name in ('portfolio-site', 'egfr-umbrella-sampling'):
            audit.append(dict(id=f'P{n:02}', repo=name, included=False, reason=('Self excluded' if name == 'portfolio-site' else 'README: atomistic EGFR profile not established; model-only result')))
            continue
        text = path.read_text()
        fields, reason = extract(text)
        audit.append(dict(id=f'P{n:02}', repo=name, included=fields is not None, reason=reason))
        if fields:
            commit = subprocess.check_output(['git', '-C', str(path.parent), 'rev-parse', 'HEAD'], text=True).strip()
            # A commit permalink must describe the actual file, not an uncommitted edit.
            committed = subprocess.check_output(['git', '-C', str(path.parent), 'show', f'{commit}:README.md'])
            if committed != path.read_bytes():
                raise ValueError(f'{name}: README differs from HEAD; commit source first')
            projects.append(dict(id=f'P{n:02}', repo=name, fields=fields, commit=commit,
                                 readme_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 url=f'https://github.com/Akkaya-Furkan/{name}/blob/{commit}/README.md'))
    payload = dict(schema=1, projects=projects, audit=audit)
    (ROOT/'data/projects.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n')
    return payload


def esc(value):
    return html.escape(value, quote=True)


def page(title, body, css='style.css'):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Furkan Akkaya — molecular biology, structural bioinformatics and computational drug discovery.">
<title>{esc(title)}</title><link rel="stylesheet" href="{css}"></head><body>
<a class="skip" href="#main">Skip to content</a>
<header><a class="wordmark" href="index.html">FA<span> / Research &amp; code</span></a><nav aria-label="Main"><a href="index.html#projects">Projects</a><a href="index.html#approach">Approach</a></nav></header>
{body}<footer>Furkan Akkaya <span>Evidence before interpretation.</span></footer></body></html>\n'''


def build(data, output):
    output.mkdir(parents=True, exist_ok=True)
    expected_html = {'index.html'} | {p['repo'] + '.html' for p in data['projects']}
    for stale in output.glob('*.html'):
        if stale.name not in expected_html:
            stale.unlink()
    cards = []
    for p in data['projects']:
        f = p['fields']
        cards.append(f'''<article class="card" aria-labelledby="{p['repo']}"><div class="card-top"><span>{p['id']}</span><span>README evidence</span></div>
<h3 id="{p['repo']}">{esc(f['title']['text'])}</h3><p class="question">{esc(f['question']['text'])}</p>
<h4>Reported result</h4><p>{esc(f['results']['text'])}</p><details><summary>Scope &amp; limitation</summary><p>{esc(f['limitations']['text'])}</p></details>
<div class="card-links"><a href="{esc(p['url'])}">Source README<span class="sr-only">: {esc(f['title']['text'])}</span> ↗</a><a href="{p['repo']}.html">Evidence excerpt<span class="sr-only">: {esc(f['title']['text'])}</span></a></div></article>''')
        excerpt = ''.join(f'<section><h2>{k.title()}</h2><p>{esc(v["text"])}</p><p class="meta">README lines {v["start"]}–{v["end"]}</p></section>' for k,v in f.items())
        body = f'<main id="main" class="evidence"><p class="eyebrow">{p["id"]} / Source record</p><h1>{esc(f["title"]["text"])}</h1><p>Verbatim README excerpts with Markdown formatting removed. Results are reported by the source repository.</p><a href="{p["url"]}">Read the original README</a>{excerpt}<p class="meta">Source commit: {p["commit"]}<br>Full README SHA-256: {p["readme_sha256"]}</p></main>'
        (output/f'{p["repo"]}.html').write_text(page(f['title']['text'], body))
    body = f'''<main id="main"><section class="hero"><p class="eyebrow">Furkan Akkaya / Scientific portfolio</p><h1>Biology, explored<br>through computation<span class="accent">.</span></h1><p class="intro">Molecular biology · Structural bioinformatics · Computational drug discovery</p><p class="hero-note">A collection of research questions, reproducible analyses and scientific software. Each project begins with a question and keeps its limits in view.</p><a class="button" href="#projects">Explore the work <span aria-hidden="true">↓</span></a><div class="hero-index" aria-hidden="true"><span>01 / Ask</span><span>02 / Build</span><span>03 / Examine</span></div></section>
<section id="projects" aria-labelledby="project-heading"><div class="section-heading"><div><p class="eyebrow">Selected work</p><h2 id="project-heading">Questions into evidence</h2></div><p>{len(cards):02} source-backed projects<br>from a 30-project inventory</p></div><p class="section-note">Included when a README reports results and limitations. Negative findings count. Planned work stays out. Source links may require GitHub access.</p><div class="grid">{''.join(cards)}</div></section>
<section id="approach" class="approach"><p class="eyebrow">Working approach</p><h2>Make the evidence inspectable.</h2><p>Cards quote source README passages, including a reported result and an explicit limitation. These are repository-reported outcomes, not independent validation. Follow the evidence excerpt for line references and a pinned source commit.</p><p>This is a static snapshot. Projects without the required evidence sections are omitted, even if some software is implemented.</p></section></main>'''
    (output/'index.html').write_text(page('Furkan Akkaya | Biology through computation', body))
    (output/'style.css').write_text((ROOT/'assets/style.css').read_text())
    (output/'.nojekyll').touch()
    print(f"Audited {len(data['audit'])}/30 repositories; rendered {len(cards)} cards and {len(cards)+1} HTML pages")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', type=Path, metavar='SIBLING_REPO_ROOT')
    parser.add_argument('--output', type=Path, default=ROOT/'site')
    args = parser.parse_args()
    data = refresh(args.refresh.resolve()) if args.refresh else json.loads((ROOT/'data/projects.json').read_text())
    build(data, args.output)
