"""연속된 두 사업보고서의 대응 본문에서 서술 변경 후보와 원문을 제공합니다."""
import asyncio
import hashlib
import json
import re
from difflib import SequenceMatcher

from cache import changes_cache
from config import (RAG_INDEX_VERSION, RAG_CHUNK_OVERLAP,
                    CHANGES_VERSION, CHANGES_TOPICS, CHANGES_MIN_SENTENCE_CHARS,
                    CHANGES_MIN_TOPIC_TERMS,
                    CHANGES_MAX_SECTION_SENTENCES, CHANGES_MIN_SIMILARITY,
                    CHANGES_MAX_SECTION_CHARS, CHANGES_MAX_SENTENCE_CHARS,
                    CHANGES_MAX_SIMILARITY, CHANGES_QUOTE_CHARS,
                    CHANGES_PHRASE_CHARS, CHANGES_MIN_EDIT_LETTERS)
from services.report_retrieval import annual_comparison_documents


def _heading_key(text: str) -> str:
    text = re.sub(r'^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+|\d+|[가-힣])\s*[.．)]\s*', '', text)
    return re.sub(r'\s+', '', text).casefold()


def _content_key(text: str) -> str:
    # 숫자·날짜·구두점만 바뀐 문장은 사업 내용 변화로 선정하지 않습니다.
    return re.sub(r'[\W_\d]+', '', text).casefold()


def _grams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _sentences(document: dict) -> tuple[dict, set[str]]:
    groups, identities, limited = {}, set(), set()
    blocks, lengths, capped = [], {}, set()
    for passage in document['passages']:
        heading = _heading_key(passage['heading'])
        lengths[heading] = lengths.get(heading, 0) + len(passage['body'])
        if heading in capped or lengths[heading] > CHANGES_MAX_SECTION_CHARS:
            limited.add(heading)
            capped.add(heading)
            continue
        if blocks and blocks[-1]['heading'] == passage['heading'] and blocks[-1]['filename'] == passage['filename'] and blocks[-1]['last_ordinal'] + 1 == passage['ordinal']:
            block = blocks[-1]
            overlap = next((n for n in range(min(RAG_CHUNK_OVERLAP, len(passage['body'])), 29, -1)
                            if block['body'].endswith(passage['body'][:n])), 0)
            start = len(block['body']) - overlap
            block['body'] += passage['body'][overlap:] if overlap else ' ' + passage['body']
            block['spans'].append((start, len(block['body']), passage['ordinal']))
            block['last_ordinal'] = passage['ordinal']
        else:
            blocks.append({**passage, 'last_ordinal': passage['ordinal'],
                           'spans': [(0, len(passage['body']), passage['ordinal'])]})
    for block in blocks:
        heading = _heading_key(block['heading'])
        offset = 0
        for text in re.split(r'(?<=[다요]\.)\s*|(?<=[.!?])\s+(?=[가-힣A-Z])', block['body']):
            start = block['body'].find(text, offset)
            offset = start + len(text)
            ordinal = next((n for a, b, n in block['spans'] if a <= start < b), block['ordinal'])
            ordinal_end = next((n for a, b, n in reversed(block['spans']) if a < offset <= b), ordinal)
            text = text.strip()
            if len(text) > CHANGES_MAX_SENTENCE_CHARS:
                limited.add(heading)
                continue
            key = _content_key(text)
            if len(key) < CHANGES_MIN_SENTENCE_CHARS or (heading, key) in identities:
                continue
            identities.add((heading, key))
            group = groups.setdefault(heading, [])
            if len(group) >= CHANGES_MAX_SECTION_SENTENCES:
                limited.add(heading)
                continue
            group.append({**block, 'ordinal': ordinal, 'ordinal_end': ordinal_end,
                          'body': text, 'key': key, 'grams': _grams(key)})
    return groups, limited


def _topic(heading: str, text: str) -> str | None:
    scores = {}
    for key, (_, headings, terms) in CHANGES_TOPICS.items():
        title_score = sum(10 for word in headings if word in heading)
        term_score = sum(word in text for word in terms)
        score = title_score + term_score
        if title_score or term_score >= CHANGES_MIN_TOPIC_TERMS:
            scores[key] = score
    return max(scores, key=scores.get) if scores else None


def _quote(text: str, anchor: int) -> str:
    if len(text) <= CHANGES_QUOTE_CHARS:
        return text
    start = max(0, anchor - CHANGES_QUOTE_CHARS // 3)
    if start:
        boundary = text.rfind(' ', 0, start)
        start = boundary + 1 if boundary >= 0 else 0
    end = min(start + CHANGES_QUOTE_CHARS, len(text))
    if end < len(text):
        boundary = text.rfind(' ', start, end)
        if boundary > start:
            end = boundary
    return ('…' if start else '') + text[start:end] + ('…' if end < len(text) else '')


def compare_documents(documents: list[dict]) -> dict:
    """같은 절의 유사 문장을 대응시켜 수치 변경을 제외한 후보를 주제별로 고릅니다."""
    old, new = documents
    previous, old_limited = _sentences(old)
    current, new_limited = _sentences(new)
    common = previous.keys() & current.keys()
    candidates = []
    covered = {key: set() for key in CHANGES_TOPICS}
    for heading in sorted(common):
        old_keys = {r['key'] for r in previous[heading]}
        new_keys = {r['key'] for r in current[heading]}
        old_rows = [r for r in previous[heading] if r['key'] not in new_keys]
        new_rows = [r for r in current[heading] if r['key'] not in old_keys]
        topic = _topic(heading, ' '.join(r['body'] for r in current[heading]))
        if topic is None:
            continue
        covered[topic].add(heading)
        used = set()
        for before in old_rows:
            ranked = []
            for i, after in enumerate(new_rows):
                if i in used:
                    continue
                union = before['grams'] | after['grams']
                score = len(before['grams'] & after['grams']) / max(1, len(union))
                if score >= CHANGES_MIN_SIMILARITY:
                    ranked.append((score, i, after))
            if not ranked:
                continue
            similarity, index, after = max(ranked, key=lambda item: (item[0], -item[1]))
            if similarity >= CHANGES_MAX_SIMILARITY:
                continue
            matcher = SequenceMatcher(None, before['body'], after['body'], autojunk=False)
            edits = [op for op in matcher.get_opcodes() if op[0] != 'equal' and
                     (_content_key(before['body'][op[1]:op[2]]) or _content_key(after['body'][op[3]:op[4]]))]
            if not edits:
                continue
            pair_topic = _topic(heading, before['body'] + ' ' + after['body'])
            if pair_topic is None:
                continue
            used.add(index)
            first = edits[0]
            evidence = []
            for row, doc, anchor in ((before, old, first[1]), (after, new, first[3])):
                evidence.append({k: row[k] for k in ('heading', 'filename', 'ordinal', 'ordinal_end')} | {
                    'fiscal_year': doc['report']['fiscal_year'], 'kind': 'text',
                    'excerpt': _quote(row['body'], anchor)})
            candidates.append({'topic': pair_topic, 'label': CHANGES_TOPICS[pair_topic][0],
                               'similarity': round(similarity, 3), 'evidence': evidence,
                               'priority': (1 - similarity) * min(len(before['key']), len(after['key'])) *
                                           (3 if any(term in heading for term in CHANGES_TOPICS[pair_topic][1]) else .25)})
    selected = []
    for topic in CHANGES_TOPICS:
        options = [c for c in candidates if c['topic'] == topic]
        if not options:
            continue
        chosen = max(options, key=lambda c: c['priority'])
        chosen.pop('priority')
        chosen['id'] = f'C{len(selected) + 1}'
        selected.append(chosen)
    for index, source in enumerate(s for c in selected for s in c['evidence']):
        source['id'] = f'R{index + 1}'
    return {'changes': selected, 'coverage': {
        'matched_sections': len(common),
        'unmatched_sections': len(previous.keys() ^ current.keys()),
        'limited_sections': len(old_limited | new_limited),
        'topics': {key: {'label': CHANGES_TOPICS[key][0], 'matched_sections': len(covered[key]),
                         'candidate_count': sum(c['topic'] == key for c in candidates)} for key in CHANGES_TOPICS}}}


def changed_phrases(sources: list[dict]) -> dict[str, str]:
    """대응 발췌에서 의미 있는 차이 주변의 실제 연속 구절만 추출합니다."""
    before, after = (s['excerpt'] for s in sources)
    edits = [op for op in SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
             if op[0] != 'equal' and
             (_content_key(before[op[1]:op[2]]) != _content_key(after[op[3]:op[4]]))]
    if not edits:
        return {'previous': before, 'current': after}
    edit = next((op for op in edits if max(len(_content_key(before[op[1]:op[2]])),
                                           len(_content_key(after[op[3]:op[4]]))) >= CHANGES_MIN_EDIT_LETTERS), edits[0])
    phrases = []
    for text, start, end in ((before, edit[1], edit[2]), (after, edit[3], edit[4])):
        left = max(0, start - CHANGES_PHRASE_CHARS // 4)
        if left:
            boundary = text.rfind(' ', 0, left)
            left = boundary + 1 if boundary >= 0 else 0
        right = min(len(text), max(end, start + 1) + CHANGES_PHRASE_CHARS // 4, left + CHANGES_PHRASE_CHARS)
        if right < len(text):
            boundary = text.rfind(' ', left, right)
            if boundary > start:
                right = boundary
        phrases.append(text[left:right].strip())
    return dict(zip(('previous', 'current'), phrases))


async def annual_changes_data(company: str, corp_code: str, display_name: str) -> dict:
    """수정 공시·비교 버전을 확인해 두 해의 서술 변경 결과를 캐시합니다."""
    documents = await annual_comparison_documents(company, corp_code)
    reports = [d['report'] for d in documents]
    fingerprint = hashlib.sha256(json.dumps({'corp': corp_code,
        'receipts': [r['receipt_no'] for r in reports], 'version': CHANGES_VERSION,
        'index_version': RAG_INDEX_VERSION}, sort_keys=True).encode()).hexdigest()
    async with changes_cache.lock(company):
        cached = await changes_cache.get(company)
        if cached and cached.get('fingerprint') == fingerprint:
            return {**cached['result'], 'cached': True}
        comparison = await asyncio.to_thread(compare_documents, documents)
        for change in comparison['changes']:
            phrases = changed_phrases(change['evidence'])
            change['phrases'] = phrases
            change['summary'] = f"“{phrases['previous']}” → “{phrases['current']}”"
        result = {'company_name': display_name, 'corp_code': corp_code,
            'previous_year': reports[0]['fiscal_year'], 'current_year': reports[1]['fiscal_year'],
            'reports': reports, **comparison, 'ai_used': False,
            'warnings': ['같은 제목 아래 대응 가능한 본문의 서술 변경 후보입니다. 실제 사업의 신규 진출·중단이나 위험 증감을 확정한 결과가 아닙니다.',
                         '수치만 바뀐 문장·표·첨부 문서와 대응하지 못한 절은 비교에서 제외합니다. 사업부 이름이나 보고서 구성이 바뀌면 일부 변화를 놓칠 수 있습니다.']}
        if comparison['coverage']['limited_sections']:
            result['warnings'].append('일부 긴 절·문장은 글자 수·문장 수 제한으로 비교 범위를 줄였습니다.')
        await changes_cache.set(company, {'fingerprint': fingerprint, 'result': result})
        return {**result, 'cached': False}


def format_change_blocks(result: dict) -> list[str]:
    """텔레그램에 보낼 요약·변경 후보·공시 출처를 읽기 쉬운 문단으로 만듭니다."""
    blocks = [f"🔎 {result['company_name']} 사업보고서 서술 변화\n"
              f"{result['previous_year']}년 → {result['current_year']}년 · 연간 기준\n"
              '주요 제품·사업 / 사업 방향·투자 / 위험 요인을 비교했습니다.']
    for change in result['changes']:
        refs = ' '.join(f"[{s['id']}]" for s in change['evidence'])
        label = '달라진 원문 표현'
        lines = [f"▸ {change['label']} — 서술 변경 후보", f"{label}: {change['summary']} {refs}"]
        for source in change['evidence']:
            lines.append(f"\n[{source['id']}] {source['fiscal_year']}년 · {source['heading']}\n{source['excerpt']}")
        blocks.append('\n'.join(lines))
    for key, topic in result['coverage']['topics'].items():
        if not any(c['topic'] == key for c in result['changes']):
            reason = '비교할 대응 본문이 부족합니다.' if not topic['matched_sections'] else '선정 기준을 충족한 서술 변경 후보가 없습니다.'
            blocks.append(f"▸ {topic['label']}: {reason} 실제 변화가 없다는 의미는 아닙니다.")
    lines = ['📎 비교한 사업보고서']
    for report in result['reports']:
        lines.extend([f"{report['report_name']} / 공시일 {report['filed_at']}", report['source']])
    for change in result['changes']:
        lines.extend(f"[{s['id']}] {s['fiscal_year']}년 {s['filename']} · 조각 {s['ordinal']}~{s['ordinal_end']}" for s in change['evidence'])
    coverage = result['coverage']
    lines.append(f"대응 절 {coverage['matched_sections']}개 / 대응하지 못한 절 {coverage['unmatched_sections']}개")
    lines.extend(result['warnings'])
    if result['cached']:
        lines.append('저장된 비교 결과를 재사용했습니다.')
    blocks.append('\n'.join(lines))
    return blocks
