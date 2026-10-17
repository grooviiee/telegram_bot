"""공시 전체 색인·회사/기간 격리·검색 인용·안전한 답변 폴백을 검증합니다."""
import asyncio
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from services import report_retrieval as rag, local_ai
from routes import ai


REPORT = {'rcept_no': '20260301000001', 'report_nm': '사업보고서 (2025.12)',
          'fiscal_year': 2025, 'fiscal_month': 12, 'rcept_dt': '20260301'}
DOCUMENT = '''<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><TITLE>1. 사업의 개요</TITLE>
<P>가전과 전장 제품을 제조하며 고객 수요에 맞춰 제품을 공급합니다. 주요 제품은 냉장고와 자동차 부품이며 서비스 사업도 운영합니다.</P>
<TITLE>2. 주요 제품 및 서비스</TITLE><P>(단위: 백만원)</P>
<TABLE><THEAD><TR><TH rowspan="2">제품</TH><TH colspan="2">매출</TH></TR>
<TR><TH>2025년</TH><TH>2024년</TH></TR></THEAD>
<TBODY><TR><TD>냉장고</TD><TD>120</TD><TD>100</TD></TR></TBODY></TABLE>
<TITLE>5. 위험관리</TITLE><P>환율과 원재료 가격의 변동이 수익성에 영향을 줄 수 있으며, 연결회사는 위험 노출을 모니터링하고 있습니다.</P>
<P>- MS (Media Entertainment Solution)</P><P>MS 부문은 TV와 모니터 제품을 공급하고 있습니다. 시장 경쟁 심화와 소비 수요의 불확실성이 존재하며 제품 경쟁력을 개선하고 있습니다.</P>
<P>- HS (Home Appliance Solution)</P><P>HS 부문은 냉장고와 세탁기를 공급하며 프리미엄 가전제품을 중심으로 연구개발과 브랜드 투자를 수행하고 있습니다.</P>
</DOCUMENT>'''.encode()


def archive(document: bytes = DOCUMENT) -> bytes:
    """가상 공시 ZIP을 만듭니다."""
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as bundle:
        bundle.writestr('report.xml', document)
    return target.getvalue()


def result() -> dict:
    """인용 검증용 검색 결과를 만듭니다."""
    return {'company_name': '회사', 'query': '사업과 위험', 'search_query': '사업과 위험',
            'cached': True, 'warnings': ['일부 근거만 검색했습니다.'],
            'report': {'report_name': '사업보고서 (2025.12)', 'fiscal_year': 2025, 'fiscal_month': 12,
                       'filed_at': '20260301', 'retrieved_at': '조회시각', 'source': '원문URL'},
            'evidence': [{'id': 'R1', 'heading': '사업 개요', 'kind': 'text', 'filename': 'report.xml',
                          'ordinal': 1, 'body': '냉장고를 제조하며 원재료 가격 변동에 노출됩니다. 매출은 120입니다.'}]}


class ParserTests(unittest.TestCase):
    def test_xml_declaration_tables_and_sector_headings(self):
        chunks = rag.parse_report_chunks(DOCUMENT, 'report.xml')
        self.assertTrue(any('냉장고' in c['body'] and c['kind'] == 'table' for c in chunks))
        table = next(c for c in chunks if c['kind'] == 'table')
        self.assertIn('2025', table['body'])
        self.assertIn('2024', table['body'])
        self.assertTrue(any('MS' in c['heading'] and 'TV' in c['body'] for c in chunks))
        self.assertTrue(any('HS' in c['heading'] and '세탁기' in c['body'] for c in chunks))

    def test_later_document_text_is_not_cut_at_500_characters(self):
        document = ('<html><p>' + '공시 자료입니다. ' * 1500 + '</p><h1>끝</h1><p>마지막고유근거</p></html>').encode()
        chunks = rag.parse_report_chunks(document, 'long.xml')
        self.assertTrue(any('마지막고유근거' in c['body'] for c in chunks))
        self.assertTrue(all(len(c['body']) <= rag.RAG_CHUNK_CHARS for c in chunks))

    def test_followup_uses_user_context_without_model_claims(self):
        history = [{'role': 'user', 'text': 'MS 부문의 경쟁력'},
                   {'role': 'model', 'text': '근거 없는 별도회사 주장'}]
        query = rag.expand_followup_query('그 위험은?', history)
        self.assertIn('MS', query)
        self.assertNotIn('별도회사', query)
        history.extend([{'role': 'user', 'text': '그 위험은?'}])
        self.assertIn('MS', rag.expand_followup_query('더 설명해줘', history))
        query = rag.expand_followup_query('그럼 2023년 사업구조는?', [{'role': 'user', 'text': '2022년 사업구조 알려줘'}])
        self.assertIn('2023년', query)
        self.assertNotIn('2022년', query)
        self.assertNotIn('2022년', rag.expand_followup_query('그럼 작년은?', [{'role': 'user', 'text': '2022년 사업구조'}]))

    def test_korean_subheading_does_not_inherit_previous_sector(self):
        document = '<html><p>- ES (Eco Solution)</p><p>공조 제품을 제조합니다.</p><p>- 이노텍</p><p>카메라모듈을 공급합니다.</p></html>'.encode()
        chunks = rag.parse_report_chunks(document, 'report.xml')
        camera = next(c for c in chunks if '카메라' in c['body'])
        self.assertIn('이노텍', camera['heading'])
        self.assertNotIn('ES', camera['heading'])

    def test_full_long_table_header_and_parent_column_are_kept(self):
        header = ''.join(f'<th>상위기간{n}년' + '긴헤더설명' * 15 + '</th>' for n in range(2020, 2030))
        values = ''.join('<td>100</td>' for _ in range(10))
        document = f'<html><table><thead><tr><th>구분</th>{header}</tr></thead><tr><td>항목</td>{values}</tr></table></html>'.encode()
        chunks = rag.parse_report_chunks(document, 'report.xml')
        self.assertTrue(any('상위기간2029년' in c['body'] for c in chunks))
        self.assertTrue(any(c['kind'] == 'table_header' for c in chunks))

    def test_prompt_keeps_evidence_with_long_question(self):
        data = result()
        question = '질문' * 950
        prompt, sources = rag.evidence_prompt(data, question)
        messages, clipped = local_ai.prepare_messages(question, prompt, None)
        self.assertFalse(clipped)
        self.assertIn(sources[0]['excerpt'], messages[0]['content'])

    def test_unseen_numbers_and_fabricated_citations_rejected(self):
        data = result()
        _, sources = rag.evidence_prompt(data, '질문')
        self.assertTrue(rag._supported_answer('냉장고를 제조합니다. [R1]', sources, data['report']))
        for answer in ['매출은 999입니다. [R1]', '냉장고를 제조합니다. [R9]', '확인되지 않은 답변']:
            self.assertFalse(rag._supported_answer(answer, sources, data['report']))
        for answer in ['매출은 -120입니다. [R1]', '매출은 120%입니다. [R1]', '매출은 120억원입니다. [R1]',
                       'HS(홈스페이스) 사업부입니다. [R1]']:
            self.assertFalse(rag._supported_answer(answer, sources, data['report']))

    def test_quantities_are_verified_per_citation(self):
        data = result()
        _, sources = rag.evidence_prompt(data, '질문')
        sources.append({**sources[0], 'id': 'R2', 'excerpt': '영업손익은 -30백만원입니다.'})
        self.assertFalse(rag._supported_answer('영업손익은 -30백만원입니다. [R1]', sources, data['report']))
        self.assertFalse(rag._supported_answer('영업손익은 30억원입니다. [R2]', sources, data['report']))
        self.assertTrue(rag._supported_answer('영업손익은 -30백만원입니다. [R2]', sources, data['report']))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'index.sqlite3'
        self.patch = patch.object(rag, 'RAG_DB_PATH', str(self.path))
        self.patch.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.patch.stop)

    def index(self, corp: str = '123', report: dict | None = None, raw: bytes = DOCUMENT):
        with patch.object(rag, '_dart_get_raw', return_value=archive(raw)):
            return rag._index_report(corp, report or REPORT)

    def test_reuses_persistent_index_without_download(self):
        metadata, cached = self.index()
        self.assertFalse(cached)
        with patch.object(rag, '_dart_get_raw', side_effect=AssertionError('unexpected download')):
            same, cached = rag._index_report('123', REPORT)
        self.assertTrue(cached)
        self.assertEqual(metadata['indexed_chunks'], same['indexed_chunks'])

    def test_company_and_filing_are_isolated(self):
        self.index()
        self.index('456', raw=DOCUMENT.replace('냉장고'.encode(), '타사독점상품'.encode()))
        other = {**REPORT, 'rcept_no': '20240301000001', 'fiscal_year': 2023}
        self.index('123', other, DOCUMENT.replace('냉장고'.encode(), '옛날독점상품'.encode()))
        hits = rag._search('123', REPORT['rcept_no'], '냉장고 주요 제품')
        self.assertTrue(hits)
        self.assertTrue(all('타사독점상품' not in h['body'] and '옛날독점상품' not in h['body'] for h in hits))

    def test_sector_query_prefers_correct_sector(self):
        self.index()
        hits = rag._search('123', REPORT['rcept_no'], 'MS 사업부 경쟁력')
        self.assertTrue(hits)
        self.assertIn('MS', hits[0]['heading'])

    def test_h_and_a_identifier_is_searchable(self):
        self.index(raw=DOCUMENT.replace(b'HS', b'H&A'))
        hits = rag._search('123', REPORT['rcept_no'], 'H&A 사업부 경쟁력')
        self.assertTrue(hits)
        self.assertIn('H&A', hits[0]['heading'])

    def test_fts_syntax_is_not_executable_input(self):
        self.index()
        rag._search('123', REPORT['rcept_no'], '\" OR * NEAR(a b); DROP TABLE reports; --')
        with rag._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM reports').fetchone()[0], 1)

    def test_new_parser_rebuilds_index(self):
        self.index()
        with patch.object(rag, 'RAG_INDEX_VERSION', rag.RAG_INDEX_VERSION + 1):
            metadata, cached = self.index()
        self.assertFalse(cached)
        self.assertEqual(metadata['index_version'], rag.RAG_INDEX_VERSION + 1)

    def test_failed_refresh_does_not_replace_previous_index(self):
        self.index()
        with patch.object(rag, 'RAG_INDEX_VERSION', rag.RAG_INDEX_VERSION + 1), patch.object(rag, 'RAG_MAX_DOCUMENT_BYTES', 1):
            with self.assertRaises(HTTPException) as caught:
                self.index()
        self.assertEqual(caught.exception.status_code, 413)
        self.assertTrue(rag._search('123', REPORT['rcept_no'], '냉장고'))


class MemoryAnswerCache:
    def __init__(self):
        self.values = {}
        self.locks = {}

    def lock(self, key):
        return self.locks.setdefault(key, asyncio.Lock())

    async def get(self, key):
        return copy.deepcopy(self.values.get(key))

    async def set(self, key, value):
        self.values[key] = copy.deepcopy(value)


class AnswerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(rag, 'rag_answer_cache', MemoryAnswerCache()).start()
        rag._cached_search.cache_clear()
    async def test_cited_answer_and_source_location(self):
        with patch.object(rag, 'retrieve_report_evidence', AsyncMock(return_value=result())), \
             patch.object(rag, 'call_gemini', AsyncMock(return_value='냉장고를 제조하며 원재료 위험이 있습니다. [R1]')):
            answer = await rag.answer_from_report('회사', '123', '사업과 위험', [])
        self.assertTrue(answer['ai_used'])
        self.assertIn('원문URL', answer['answer'])
        self.assertIn('report.xml', answer['answer'])

    async def test_unsupported_generation_becomes_source_quote(self):
        with patch.object(rag, 'retrieve_report_evidence', AsyncMock(return_value=result())), \
             patch.object(rag, 'call_gemini', AsyncMock(return_value='매출은 999입니다. [R1]')):
            answer = await rag.answer_from_report('회사', '123', '사업과 위험', [])
        self.assertFalse(answer['ai_used'])
        self.assertNotIn('999', answer['answer'])
        self.assertIn('냉장고', answer['answer'])

    async def test_invalid_first_generation_can_be_repaired(self):
        with patch.object(rag, 'retrieve_report_evidence', AsyncMock(return_value=result())), \
             patch.object(rag, 'call_gemini', AsyncMock(side_effect=['매출은 999입니다. [R1]', '원재료 가격 변동 위험이 있습니다. [R1]'])) as model:
            answer = await rag.answer_from_report('회사', '123', '사업과 위험', [])
        self.assertTrue(answer['ai_used'])
        self.assertEqual(model.await_count, 2)
        self.assertNotIn('999', answer['answer'])

    async def test_no_evidence_does_not_call_model(self):
        data = {**result(), 'evidence': []}
        with patch.object(rag, 'retrieve_report_evidence', AsyncMock(return_value=data)), \
             patch.object(rag, 'call_gemini', AsyncMock()) as model:
            answer = await rag.answer_from_report('회사', '123', '알 수 없는 주제', [])
        model.assert_not_awaited()
        self.assertFalse(answer['ai_used'])

    async def test_unavailable_year_is_not_replaced_with_latest(self):
        cache = AsyncMock()
        cache.get_or_create.return_value = ({'reports': [REPORT]}, True)
        with patch.object(rag, 'rag_manifest_cache', cache), patch.object(rag, '_index_report') as index:
            with self.assertRaises(HTTPException) as caught:
                await rag.retrieve_report_evidence('회사', '123', '2022년 사업구조')
        self.assertEqual(caught.exception.status_code, 404)
        index.assert_not_called()

    async def test_explicit_followup_year_wins_over_previous_year(self):
        report = {**REPORT, 'fiscal_year': 2023}
        cache = AsyncMock()
        cache.get_or_create.return_value = ({'reports': [REPORT, report]}, True)
        metadata = {**result()['report'], 'receipt_no': report['rcept_no'], 'fiscal_year': 2023}
        with patch.object(rag, 'rag_manifest_cache', cache), \
             patch.object(rag, '_index_report', return_value=(metadata, True)) as index, \
             patch.object(rag, '_search', return_value=[]):
            await rag.retrieve_report_evidence('회사', '123', '그럼 2023년 사업구조는?', [{'role': 'user', 'text': '2022년 사업구조'}])
        self.assertEqual(index.call_args.args[1]['fiscal_year'], 2023)

    async def test_large_recent_year_range_is_rejected_before_indexing(self):
        cache = AsyncMock()
        cache.get_or_create.return_value = ({'reports': [REPORT]}, True)
        with patch.object(rag, 'rag_manifest_cache', cache), patch.object(rag, '_index_report') as index:
            with self.assertRaises(HTTPException) as caught:
                await rag.retrieve_report_evidence('회사', '123', '최근 999999999999년 사업구조')
        self.assertEqual(caught.exception.status_code, 422)
        index.assert_not_called()

    async def test_comparison_indexes_both_requested_years(self):
        second = {**REPORT, 'rcept_no': '20240301000001', 'fiscal_year': 2023}
        cache = AsyncMock()
        cache.get_or_create.return_value = ({'reports': [REPORT, second]}, True)
        def index(corp, report):
            return {**result()['report'], 'receipt_no': report['rcept_no'], 'fiscal_year': report['fiscal_year']}, True
        with patch.object(rag, 'rag_manifest_cache', cache), patch.object(rag, '_index_report', side_effect=index) as build, \
             patch.object(rag, '_search', return_value=result()['evidence']):
            found = await rag.retrieve_report_evidence('회사', '123', '2023년과 2025년 사업구조 비교')
        self.assertEqual({r['fiscal_year'] for r in found['reports']}, {2023, 2025})
        self.assertEqual(build.call_count, 2)

    async def test_narrative_chat_uses_report_search(self):
        with patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai, 'answer_factual', AsyncMock(return_value=None)), \
             patch.object(ai, 'answer_from_report', AsyncMock(return_value={'answer': '공시 근거 답변', 'ai_used': True})) as search:
            response = await ai.chat('회사', ai.ChatRequest(message='사업 내용과 경쟁력을 설명해줘'))
        search.assert_awaited_once()
        self.assertIn('공시 근거 답변', response.body.decode())


if __name__ == '__main__':
    unittest.main()
