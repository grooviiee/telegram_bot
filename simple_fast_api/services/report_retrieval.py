"""공시 전체를 CPU에서 색인하고 질문에 필요한 원문만 검색합니다."""
import asyncio
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from lxml import html

from cache import rag_manifest_cache
from config import (DART_LIST_URL, DART_DOCUMENT_URL, DART_VIEWER_URL, YEAR_RANGE,
                    RAG_DB_PATH, RAG_INDEX_VERSION, RAG_CHUNK_CHARS, RAG_CHUNK_OVERLAP,
                    RAG_EVIDENCE_CHARS, RAG_PASSAGE_COUNT, RAG_MAX_REPORTS, RAG_QUERY_TERMS, RAG_CANDIDATE_COUNT, RAG_HEADING_FACETS,
                    RAG_DOCUMENT_TIMEOUT, RAG_MAX_DOCUMENT_BYTES, RAG_MAX_INDEX_CHARS,
                    RAG_DB_TIMEOUT, RAG_QUERY_SYNONYMS, RAG_STOP_WORDS,
                    RAG_SYSTEM_RULES, RAG_OUTPUT_TOKENS, RAG_RETRY_TOKENS, OLLAMA_MAX_INPUT_CHARS,
                    OLLAMA_SYSTEM_RULES)
from services.dart import _dart_get, _dart_get_raw
from services.dart import resolve_corp_code
from utils import call_gemini

_index_slots = asyncio.Semaphore(1)


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _terms(text: str) -> list[str]:
    result = []
    text = re.sub(r'h\s*&\s*a', 'handabusiness', text, flags=re.IGNORECASE)
    for word in re.findall(r'[가-힣]+|[a-zA-Z][a-zA-Z0-9]*|\d{4}', text.lower()):
        if word in RAG_STOP_WORDS or len(word) < 2:
            continue
        result.append(word)
        if re.fullmatch('[가-힣]+', word):
            result.extend(word[i:i + n] for n in (2, 3) for i in range(len(word) - n + 1))
    return list(dict.fromkeys(result))


def _query_terms(query: str) -> list[str]:
    cleaned = query
    for word in RAG_STOP_WORDS:
        cleaned = cleaned.replace(word, ' ')
    expanded = []
    for word, aliases in RAG_QUERY_SYNONYMS.items():
        if word.lower() in cleaned.lower():
            expanded.extend(aliases)
    # 원 질문의 단어를 먼저 보존하고 확장 검색어는 예산 안에서 추가합니다.
    return list(dict.fromkeys(_terms(cleaned) + _terms(' '.join(expanded))))[:RAG_QUERY_TERMS]


def _split(text: str, size: int = RAG_CHUNK_CHARS) -> list[str]:
    text = _normalize(text)
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + size // 2, end)
            if boundary > start:
                end = boundary
        pieces.append(text[start:end])
        if end == len(text):
            break
        start = max(start + 1, end - RAG_CHUNK_OVERLAP)
    return pieces


def _table_text(table) -> list[str]:
    """병합 셀을 확장하고 각 조각에 표 헤더를 반복합니다."""
    occupied, rows = {}, []
    for r, row in enumerate(table.xpath('.//tr')):
        if next((p for p in row.iterancestors() if p.tag == 'table'), None) is not table:
            continue
        c, values = 0, []
        for cell in row:
            if cell.tag not in ('td', 'th', 'te'):
                continue
            while c in occupied.get(r, {}):
                c += 1
            try:
                rs, cs = min(int(cell.get('rowspan', 1)), 200), min(int(cell.get('colspan', 1)), 50)
            except (ValueError, TypeError):
                rs, cs = 1, 1
            text = _normalize(' '.join(cell.itertext()))
            for dr in range(max(1, rs)):
                for dc in range(max(1, cs)):
                    occupied.setdefault(r + dr, {})[c + dc] = text
            c += max(1, cs)
        width = max(occupied.get(r, {}), default=-1) + 1
        values = [occupied.get(r, {}).get(col, '') for col in range(width)]
        if any(values):
            rows.append(values)
    if not rows:
        return _split(' '.join(table.itertext()))
    head = table.find('thead')
    count = min(len(head.xpath('.//tr')) if head is not None else 1, len(rows))
    header = '표 헤더: ' + ' / '.join(' | '.join(row) for row in rows[:count])
    target = RAG_CHUNK_CHARS - 250
    prefix = header[:target // 3]
    room = target - len(prefix) - 1
    pieces, pending = [], ''
    labels = [' > '.join(dict.fromkeys(row[c] for row in rows[:count] if c < len(row) and row[c]))
              for c in range(max(map(len, rows[:count])))]
    for row in rows[count:]:
        name = row[0]
        if len(name) > room // 2:
            if pending:
                pieces.append(pending)
                pending = ''
            pieces.extend(_split(' | '.join(row), room))
            continue
        fields = [f"{labels[c] if c < len(labels) else '항목'}: {value}" for c, value in enumerate(row[1:], 1) if value]
        row_pieces, part = [], name + ': '
        for field in fields:
            for fragment in _split(field, max(120, room - len(name) - 3)):
                if len(part) + len(fragment) + 2 > room and len(part) > len(name) + 2:
                    row_pieces.append(part)
                    part = name + ': '
                part += fragment + '; '
        if part.strip():
            row_pieces.append(part)
        for part in row_pieces:
            if pending and len(pending) + len(part) + 1 > room:
                pieces.append(pending)
                pending = ''
            pending = (pending + '\n' + part).strip()
    if pending:
        pieces.append(pending)
    full_headers = ['표 전체 헤더: ' + piece for piece in _split(header, target)]
    body = [prefix + '\n' + piece for piece in pieces] if pieces else _split(' | '.join(' | '.join(row) for row in rows))
    return full_headers + body


def parse_report_chunks(document: bytes, filename: str) -> list[dict]:
    """본문 전체와 표를 제목·원문 파일·순번을 가진 검색 조각으로 나눕니다."""
    text = None
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            text = document.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None:
        raise ValueError('공시 문자 인코딩을 확인하지 못했습니다.')
    parser = html.HTMLParser(encoding='utf-8', recover=True, no_network=True, remove_comments=True, huge_tree=True)
    root = html.fromstring(text.encode('utf-8'), parser=parser)
    chunks, heading, pending, recent = [], '공시 본문', [], []

    def emit(body: str, kind: str) -> None:
        body = _normalize(body)
        if not body:
            return
        for part in _split(body):
            chunks.append({'heading': heading, 'kind': kind, 'body': part,
                           'filename': filename, 'ordinal': len(chunks) + 1})

    def flush() -> None:
        if pending:
            emit(' '.join(pending), 'text')
            pending.clear()

    def visit(node) -> None:
        nonlocal heading
        if not isinstance(node.tag, str) or node.tag in ('script', 'style', 'head'):
            return
        tag = node.tag.lower()
        body = _normalize(' '.join(node.itertext())) if tag in ('title', 'subtitle', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p') else ''
        is_heading = tag in ('title', 'subtitle', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6') or (tag == 'p' and len(body) < 150 and
            bool(re.match(r'^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+[.．]|\d+[.．]\s*|[가-힣][.]\s*|[-–]\s*\S+\s*\(|[-–]\s*[A-Z&]{2,8}\b|[-–]\s*[가-힣A-Z&]{2,12}\s*$)', body)))
        if is_heading:
            flush()
            heading = body[:200] or heading
            return
        if tag == 'table':
            flush()
            context = ' '.join(re.findall(r'(?:단위\s*[:：][^)]{1,30}|당기|전기|전전기)', ' '.join(recent[-2:])))[:100]
            for part in _table_text(node):
                emit(context + '\n' + part, 'table_header' if part.startswith('표 전체 헤더:') else 'table')
            return
        if tag == 'p':
            if body:
                pending.append(body)
                recent.append(body[-250:])
                if sum(map(len, pending)) >= RAG_CHUNK_CHARS:
                    flush()
            return
        if node.text and node.text.strip():
            pending.append(_normalize(node.text))
        for child in node:
            visit(child)
            if child.tail and child.tail.strip():
                pending.append(_normalize(child.tail))
    visit(root)
    flush()
    seen, unique = set(), []
    for chunk in chunks:
        digest = hashlib.sha256((chunk['heading'] + chunk['body']).encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append(chunk)
    return unique


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    Path(RAG_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(RAG_DB_PATH, timeout=RAG_DB_TIMEOUT)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE IF NOT EXISTS reports (corp TEXT, receipt TEXT, version INTEGER, metadata TEXT, PRIMARY KEY(corp, receipt))')
    connection.execute('CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(corp UNINDEXED, receipt UNINDEXED, heading UNINDEXED, kind UNINDEXED, filename UNINDEXED, ordinal UNINDEXED, body UNINDEXED, tokens)')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _listing(corp_code: str) -> dict:
    now = datetime.now()
    result = _dart_get(DART_LIST_URL, {'corp_code': corp_code, 'pblntf_detail_ty': 'A001',
        'last_reprt_at': 'Y', 'bgn_de': f'{now.year - YEAR_RANGE}0101',
        'end_de': now.strftime('%Y%m%d'), 'sort': 'date', 'sort_mth': 'desc', 'page_count': 100})
    if result.get('status') not in ('000', '013'):
        raise HTTPException(502, 'DART 사업보고서 목록을 조회하지 못했습니다.')
    reports = []
    for report in result.get('list', []):
        period = re.search(r'사업보고서\s*\((\d{4})\.(\d{2})\)', report.get('report_nm', ''))
        if period and re.fullmatch(r'\d{14}', report.get('rcept_no', '')):
            reports.append({**report, 'fiscal_year': int(period[1]), 'fiscal_month': int(period[2])})
    if not reports:
        raise HTTPException(404, '검색할 사업보고서를 찾지 못했습니다.')
    return {'reports': sorted(reports, key=lambda r: (r['fiscal_year'], r['fiscal_month'], r.get('rcept_dt', '')), reverse=True)}


def _index_report(corp_code: str, report: dict) -> tuple[dict, bool]:
    receipt = report['rcept_no']
    with _connect() as connection:
        row = connection.execute('SELECT version, metadata FROM reports WHERE corp=? AND receipt=?', (corp_code, receipt)).fetchone()
        if row and row['version'] == RAG_INDEX_VERSION:
            return json.loads(row['metadata']), True
    archive = _dart_get_raw(DART_DOCUMENT_URL, {'rcept_no': receipt}, timeout=RAG_DOCUMENT_TIMEOUT)
    chunks = []
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        documents = [i for i in bundle.infolist() if i.filename.lower().endswith(('.xml', '.html', '.htm')) and not i.filename.startswith('__')]
        if sum(i.file_size for i in documents) > RAG_MAX_DOCUMENT_BYTES:
            raise HTTPException(413, '공시 원문이 현재 색인 용량 제한을 초과했습니다. 자료 일부만 읽은 것으로 대신하지 않습니다.')
        for item in documents:
            chunks.extend(parse_report_chunks(bundle.read(item), item.filename))
    if not chunks or sum(len(c['body']) for c in chunks) > RAG_MAX_INDEX_CHARS:
        raise HTTPException(422, '공시 본문을 완전하게 색인할 수 없어 검색 결과를 제공하지 않습니다.')
    metadata = {'report_name': report['report_nm'], 'receipt_no': receipt,
        'fiscal_year': report['fiscal_year'], 'fiscal_month': report['fiscal_month'],
        'filed_at': report.get('rcept_dt'), 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'source': DART_VIEWER_URL + receipt, 'indexed_chunks': len(chunks),
        'indexed_chars': sum(len(c['body']) for c in chunks), 'index_version': RAG_INDEX_VERSION}
    with _connect() as connection:
        connection.execute('DELETE FROM chunks WHERE corp=? AND receipt=?', (corp_code, receipt))
        connection.executemany('INSERT INTO chunks(corp,receipt,heading,kind,filename,ordinal,body,tokens) VALUES(?,?,?,?,?,?,?,?)',
            [(corp_code, receipt, c['heading'], c['kind'], c['filename'], c['ordinal'], c['body'],
              ' '.join(_terms(c['heading']) * 2 + _terms(c['body']))) for c in chunks])
        connection.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)', (corp_code, receipt, RAG_INDEX_VERSION, json.dumps(metadata, ensure_ascii=False)))
    return metadata, False


def expand_followup_query(message: str, history: list[dict]) -> str:
    """짧은 후속 질문에 직전 사용자 질문만 보태고 모델의 추측은 검색어로 쓰지 않습니다."""
    def followup(text: str) -> bool:
        return len(text) < 40 and bool(re.search(r'^(?:그럼|그러면|그(?:\s|위험|부분|내용|사업)|더|왜|자세|구체|이유|추가|이\s)', text.strip()))
    if followup(message) and not re.search(r'(?<![a-zA-Z])(HS|MS|VS|ES|H&A|HE|DX|DS)(?![a-zA-Z])', message, re.IGNORECASE):
        previous, additions = '', []
        for item in reversed(history):
            if item.get('role') != 'user':
                continue
            text = str(item.get('text', ''))
            if not followup(text):
                previous = text
                break
            if len(additions) < 1:
                additions.append(text)
        if re.search(r'(?:19|20)\d{2}\s*년|작년|재작년|올해|금년|최근\s*\d+\s*(?:개)?년', message):
            previous = re.sub(r'(?:19|20)\d{2}\s*년', '', previous)
            additions = []
        return ' '.join([previous, *reversed(additions), message]).strip()
    return message


def _search(corp_code: str, receipt: str, query: str) -> list[dict]:
    terms = _query_terms(query)
    if not terms:
        return []
    match = ' OR '.join('"' + term + '"' for term in terms)
    sector = re.search(r'(?<![a-zA-Z])(HS|MS|VS|ES|H&A|HE|DX|DS)(?![a-zA-Z])', query, re.IGNORECASE)
    if sector:
        identifier = 'handabusiness' if sector[1].lower() == 'h&a' else sector[1].lower()
        match = '"' + identifier + '" AND (' + match + ')'
    with _connect() as connection:
        rows = connection.execute('SELECT heading,kind,filename,ordinal,body,bm25(chunks) AS rank FROM chunks WHERE chunks MATCH ? AND corp=? AND receipt=? ORDER BY rank LIMIT ?',
            (match, corp_code, receipt, RAG_CANDIDATE_COUNT)).fetchall()
        rows = [dict(r) for r in rows]
        if sector is None:
            for facet, aliases in RAG_HEADING_FACETS.items():
                if facet in query:
                    for alias in aliases:
                        rows.extend(dict(r) for r in connection.execute(
                            'SELECT heading,kind,filename,ordinal,body,0 AS rank FROM chunks WHERE corp=? AND receipt=? AND heading LIKE ? AND kind=? AND length(body)>120 LIMIT 8',
                            (corp_code, receipt, '%' + alias + '%', 'text')).fetchall())
    def relevance(row) -> tuple:
        heading = re.sub(r'\s+', '', row['heading']).lower()
        overview = any(w in query for w in ('사업영역', '사업 영역', '사업구조', '사업 구조', '주요 제품', '주요제품'))
        overview_match = overview and any(w in heading for w in ('사업의개요', '주요제품', '사업개요')) and any(
            w in row['body'] for w in ('사업부문', '사업부', '주요 제품', '주요제품', '냉장고', 'HS', 'MS', '서비스'))
        sector_match = sector is not None and bool(re.search(r'(?<![a-z])' + re.escape(sector[1].lower()) + r'(?![a-z])', row['heading'].lower()))
        return (0 if overview_match or sector_match else 1, 0 if len(row['body']) >= 120 else 2,
                0 if row['kind'] == 'text' else 2 if row['kind'] == 'table_header' else 1, row['rank'])
    rows = sorted(rows, key=relevance)
    # 근접한 중복 조각 대신 서로 다른 절·표의 근거를 우선합니다.
    preferred = []
    if sector is None:
        for facet, aliases in RAG_HEADING_FACETS.items():
            if facet in query:
                hit = next((r for r in rows if len(r['body']) >= 120 and any(a in r['heading'] for a in aliases)), None)
                if hit:
                    preferred.append(hit)
    selected, seen, identities = [], set(), set()
    for row in preferred + rows:
        item = dict(row)
        identity = (item['filename'], item['ordinal'])
        if identity in identities:
            continue
        key = (item['filename'], item['heading'], item['kind'])
        if key in seen and len(selected) < RAG_PASSAGE_COUNT - 1:
            continue
        seen.add(key)
        identities.add(identity)
        item['id'] = f'R{len(selected) + 1}'
        selected.append(item)
        if len(selected) == RAG_PASSAGE_COUNT:
            break
    return selected


async def retrieve_report_evidence(company: str, corp_code: str, message: str,
                                   history: list[dict] | None = None) -> dict:
    """회사·공시·기간을 격리하여 전체 색인에서 관련 본문과 표를 검색합니다."""
    query = expand_followup_query(message, history or [])
    async def load() -> dict:
        return await asyncio.to_thread(_listing, corp_code)
    try:
        manifest, _ = await rag_manifest_cache.get_or_create(company, load)
        years = list(dict.fromkeys(int(y) for y in re.findall(r'((?:19|20)\d{2})\s*년', query)))
        span = re.search(r'((?:19|20)\d{2})\s*년?\s*(?:~|부터|-)\s*((?:19|20)\d{2})', message)
        if span:
            if not 1 <= int(span[2]) - int(span[1]) + 1 <= RAG_MAX_REPORTS:
                raise HTTPException(422, f'공시 비교 검색은 최대 {RAG_MAX_REPORTS}개 연도만 지정해주세요.')
            years = list(range(int(span[1]), int(span[2]) + 1))
        recent = re.search(r'최근\s*(\d+)\s*(?:개)?년', message)
        if recent:
            if not 1 <= int(recent[1]) <= RAG_MAX_REPORTS:
                raise HTTPException(422, f'공시 비교 검색은 최대 {RAG_MAX_REPORTS}개 연도만 지정해주세요.')
            latest = manifest['reports'][0]['fiscal_year']
            years = list(range(latest, latest - int(recent[1]), -1))
        if not years:
            if '재작년' in message:
                years = [datetime.now().year - 2]
            elif '작년' in message:
                years = [datetime.now().year - 1]
            elif '올해' in message or '금년' in message:
                years = [datetime.now().year]
        if len(years) > RAG_MAX_REPORTS or (span and not years):
            raise HTTPException(422, f'공시 비교 검색은 한 번에 최대 {RAG_MAX_REPORTS}개 연도를 지정해주세요.')
        chosen = []
        for wanted in years or [None]:
            report = next((r for r in manifest['reports'] if wanted is None or r['fiscal_year'] == wanted), None)
            if report is None:
                raise HTTPException(404, f'{wanted}년 사업보고서 근거를 찾지 못했습니다. 다른 연도 자료로 대신하지 않습니다.')
            chosen.append(report)
        metadatas, groups, cache_flags = [], [], []
        for report in chosen:
            async with _index_slots:
                metadata, cached = await asyncio.to_thread(_index_report, corp_code, report)
            hits = await asyncio.to_thread(_search, corp_code, report['rcept_no'], query.replace(company, ''))
            metadatas.append(metadata)
            cache_flags.append(cached)
            groups.append([{**h, 'fiscal_year': metadata['fiscal_year'], 'receipt_no': metadata['receipt_no']} for h in hits])
        if len(groups) > 1 and any(not group for group in groups):
            raise HTTPException(404, '지정한 연도 중 관련 근거를 찾지 못한 보고서가 있어 비교 답변을 제공하지 않습니다.')
        sources = [group[i] for i in range(RAG_PASSAGE_COUNT) for group in groups if len(group) > i][:RAG_PASSAGE_COUNT]
        for i, source in enumerate(sources):
            source['id'] = f'R{i + 1}'
        metadata, cached = metadatas[0], all(cache_flags)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '공시 근거를 수집·검색하지 못했습니다. 확인되지 않은 자료로 답변하지 않습니다.') from None
    return {'company_name': company, 'query': message, 'search_query': query,
            'report': metadata, 'reports': metadatas, 'evidence': sources, 'cached': cached,
            'warnings': ['검색된 일부 근거에 한정한 답변이며 공시 전체를 종합 분석한 결과가 아닙니다.'] +
                        (['각 근거의 재무 기준연도와 사업부 재편 여부를 구분해 비교해야 합니다.'] if len(years) > 1 else [])}


def _excerpt(body: str, query: str, limit: int) -> str:
    if len(body) <= limit:
        return body
    sector = re.search(r'(?<![a-zA-Z])(HS|MS|VS|ES|H&A|HE|DX|DS)(?![a-zA-Z])', query, re.IGNORECASE)
    sector_position = re.search(re.escape(sector[1]) + r'\s*(?:부문|사업|본부|\()', body, re.IGNORECASE) if sector else None
    positions = [body.lower().find(t) for t in _query_terms(query) if body.lower().find(t) >= 0]
    anchor = sector_position.start() if sector_position else min(positions) if positions else 0
    start = max(0, anchor - limit // 4)
    return ('…' if start else '') + body[start:start + limit] + '…'


def evidence_prompt(result: dict, question: str) -> tuple[str, list[dict]]:
    """현재 4K 문맥에 맞춰 근거 조각을 우선 배치하고 인용 목록을 확정합니다."""
    report = result['report']
    periods = ', '.join(f"{r['fiscal_year']}.{r['fiscal_month']:02d}" for r in result.get('reports', [report]))
    prefix = f"{RAG_SYSTEM_RULES}\n기업: {result['company_name']}. 재무 기준: {periods}.\n"
    budget = min(RAG_EVIDENCE_CHARS, OLLAMA_MAX_INPUT_CHARS - len(OLLAMA_SYSTEM_RULES) - len(question) - len(prefix) - 150)
    sources = result['evidence'][:RAG_PASSAGE_COUNT]
    if budget < 200 or not sources:
        return prefix, []
    used, passages = [], []
    remaining = budget
    for i, source in enumerate(sources):
        per_source = remaining // (len(sources) - i)
        label = f"[{source['id']}] {source.get('fiscal_year', report['fiscal_year'])}년 {source['heading'][:100]} / {source['kind']} / 조각 {source['ordinal']}\n"
        excerpt = _excerpt(source['body'], '' if source['kind'] == 'table' else result['search_query'], max(50, per_source - len(label)))
        passages.append(label + excerpt)
        remaining -= len(label) + len(excerpt)
        used.append({**source, 'excerpt': excerpt})
    return prefix + '\n'.join(passages), used


def _supported_answer(answer: str, sources: list[dict], report: dict) -> bool:
    citations = re.findall(r'\[R(\d+)\]', answer)
    if not citations or not set('R' + c for c in citations).issubset({s['id'] for s in sources}):
        return False
    def quantities(text: str, inherit_unit: bool = False) -> set[tuple[str, str]]:
        text = re.sub(r'\[R\d+\]|(?m:^\s*\d+[.)]\s+)', '', text)
        declared = re.search(r'단위\s*[:：]\s*(백만원|천원|억원|조원|원|달러)', text) if inherit_unit else None
        values = set()
        pattern = r'(?<![A-Za-z0-9])([+\-−△]?\s*(?:\([\d,]+(?:\.\d+)?\)|[\d,]+(?:\.\d+)?))\s*(조원|억원|백만원|천원|원|달러|퍼센트|%|년|월|분기|개|대|톤|명|배)?'
        for match in re.finditer(pattern, text):
            raw = re.sub(r'[\s,]', '', match[1]).replace('−', '-').replace('△', '-')
            if raw.startswith('(') and raw.endswith(')'):
                raw = '-' + raw[1:-1]
            try:
                number = str(Decimal(raw).normalize())
            except InvalidOperation:
                continue
            unit = '%' if match[2] == '퍼센트' else match[2] or ''
            values.add((number, unit))
            if not unit and declared:
                values.add((number, declared[1]))
        return values
    source_map = {s['id']: s for s in sources}
    start = 0
    for citation in re.finditer(r'(?:\[R\d+\]\s*)+', answer):
        claim = answer[start:citation.start()]
        cited = [source_map['R' + value] for value in re.findall(r'\[R(\d+)\]', citation[0])]
        allowed = set()
        grounded = ''
        for source in cited:
            text = source['excerpt'] + ' ' + source['heading']
            grounded += text
            allowed.update(quantities(text, True))
            allowed.update(quantities(f"{source.get('fiscal_year', report['fiscal_year'])}년 {report['fiscal_month']}월"))
        if not quantities(claim).issubset(allowed):
            return False
        # 원문에 없는 약어 풀이는 그럴듯한 사업부명을 만들어 내는 흔한 오류입니다.
        for definition in re.finditer(r'[A-Z][A-Z&]{1,7}\s*[（(][^）)\n]{2,80}[）)]', claim):
            canonical = lambda text: re.sub(r'[\s*]', '', text).lower()
            if canonical(definition[0]) not in canonical(grounded):
                return False
        start = citation.end()
    return not quantities(answer[start:])


def _source_footer(result: dict, sources: list[dict]) -> str:
    report = result['report']
    lines = ['\n[공시 근거]']
    for metadata in result.get('reports', [report]):
        lines.extend([f"{metadata['report_name']} / 공시일 {metadata['filed_at']} / 조회 {metadata['retrieved_at']}", metadata['source']])
    lines.extend(f"[{s['id']}] {s.get('fiscal_year', report['fiscal_year'])}년 {s['heading']} · {s['filename']} · 조각 {s['ordinal']} ({s['kind']})" for s in sources)
    lines.extend(result['warnings'])
    return '\n'.join(lines)


async def answer_from_report(company: str, corp_code: str, message: str, history: list[dict]) -> dict:
    """질문 관련 공시 근거로 답하고 무근거 인용·새 숫자는 원문 발췌로 대체합니다."""
    result = await retrieve_report_evidence(company, corp_code, message, history)
    query = message
    # 후속 질문의 대상을 명시하되 이전 모델 답변을 사실 근거로 전달하지 않습니다.
    if result['search_query'] != message:
        query = result['search_query']
    prompt, sources = evidence_prompt(result, query)
    if not sources:
        return {'answer': '질문에 맞는 공시 근거를 찾지 못했습니다. 사업·제품·위험 등 확인할 주제를 구체적으로 입력해주세요.',
                'ai_used': False, 'cached': result['cached'], 'evidence': [], 'retrieval': result['report']}
    answer = await call_gemini(query, system_instruction=prompt,
                               generation_config={'temperature': .15, 'maxOutputTokens': RAG_OUTPUT_TOKENS})
    valid = not answer.startswith('(AI 응답 생성 실패)') and _supported_answer(answer, sources, result['report'])
    if not valid and not answer.startswith('(AI 응답 생성 실패)'):
        answer = await call_gemini(query, system_instruction=prompt +
            '\n검증 요청: 답변에서 근거 번호 외의 숫자와 약어 풀이를 생략하세요. 원문의 사실만 한국어 두 단락으로 설명하고 각 문장에 [R1] 등 정확한 근거 번호를 붙이세요.',
            generation_config={'temperature': .1, 'maxOutputTokens': RAG_RETRY_TOKENS})
        valid = not answer.startswith('(AI 응답 생성 실패)') and _supported_answer(answer, sources, result['report'])
    if not valid:
        answer = '질문과 관련해 확인된 공시 원문입니다. 생성 답변 대신 근거를 직접 표시합니다.\n\n' + '\n\n'.join(
            f"[{s['id']}] {s['heading']}\n{s['excerpt']}" for s in sources)
    return {'answer': answer + _source_footer(result, sources), 'ai_used': valid,
            'cached': result['cached'], 'evidence': [{k: s[k] for k in ('id', 'heading', 'kind', 'filename', 'ordinal', 'excerpt')} for s in sources],
            'retrieval': result['report']}


async def report_index_status() -> dict:
    """영구 공시 색인의 보고서·근거 조각 수를 반환합니다."""
    def read() -> dict:
        with _connect() as connection:
            return {'reports': connection.execute('SELECT count(*) FROM reports').fetchone()[0],
                    'chunks': connection.execute('SELECT count(*) FROM chunks').fetchone()[0],
                    'index_version': RAG_INDEX_VERSION}
    return await asyncio.to_thread(read)


async def annual_comparison_documents(company: str, corp_code: str) -> list[dict]:
    """최근 결산연도와 직전 연도의 주본문을 동일한 색인에서 읽습니다."""
    async def load() -> dict:
        try:
            return await asyncio.to_thread(_listing, corp_code)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, '비교할 사업보고서 목록을 조회하지 못했습니다.') from None
    manifest, _ = await rag_manifest_cache.get_or_create(company, load)
    latest = manifest['reports'][0]
    previous = next((r for r in manifest['reports'] if r['fiscal_year'] == latest['fiscal_year'] - 1), None)
    if previous is None:
        raise HTTPException(404, '직전 결산연도의 사업보고서가 없어 연속된 두 해를 비교할 수 없습니다.')
    if previous['fiscal_month'] != latest['fiscal_month']:
        raise HTTPException(422, '두 보고서의 결산월이 달라 같은 기준으로 비교할 수 없습니다.')

    def read(metadata: dict) -> dict:
        with _connect() as connection:
            rows = [dict(r) for r in connection.execute(
                'SELECT heading,kind,filename,ordinal,body FROM chunks WHERE corp=? AND receipt=? AND kind=? ORDER BY ordinal',
                (corp_code, metadata['receipt_no'], 'text')).fetchall()]
        filenames = set(r['filename'] for r in rows)
        main = next((f for f in sorted(filenames) if Path(f).stem == metadata['receipt_no']), None)
        if main is None and len(filenames) == 1:
            main = next(iter(filenames))
        if main is None:
            raise HTTPException(422, '비교할 사업보고서 주본문을 식별하지 못했습니다. 첨부 문서를 임의로 비교하지 않습니다.')
        return {'report': metadata, 'passages': [r for r in rows if r['filename'] == main], 'filename': main}

    documents = []
    try:
        for report in (previous, latest):
            async with _index_slots:
                metadata, _ = await asyncio.to_thread(_index_report, corp_code, report)
                documents.append(await asyncio.to_thread(read, metadata))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '비교할 공시 본문을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.') from None
    return documents


async def clear_report_index(company: str | None = None) -> bool:
    """요청한 회사 또는 전체 공시 색인을 명시적으로 삭제합니다."""
    corp_code = None
    if company:
        try:
            corp_code = await resolve_corp_code(company)
        except HTTPException as exc:
            if exc.status_code == 404:
                return False
            raise
    def clear() -> bool:
        with _connect() as connection:
            if corp_code:
                deleted = connection.execute('DELETE FROM reports WHERE corp=?', (corp_code,)).rowcount
                connection.execute('DELETE FROM chunks WHERE corp=?', (corp_code,))
            else:
                deleted = connection.execute('DELETE FROM reports').rowcount
                connection.execute('DELETE FROM chunks')
            return deleted > 0
    async with _index_slots:
        return await asyncio.to_thread(clear)
