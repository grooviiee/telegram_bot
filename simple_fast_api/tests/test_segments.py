"""부문 손익의 기간·연결 기준·단위·음수 비중과 상담 연결을 검증합니다."""
import unittest
import io
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from services import segments, company_data
from routes import ai


def document(profit_a: str = '120', profit_b: str = '(20)', total: str = '100',
             period: str = '당기', basis: str = '연결', unit: str = '백만원') -> bytes:
    """병합 헤더가 있는 가상 연결 부문 표를 생성합니다."""
    return f'''<html><p>4. 영업부문 정보 ({basis})</p><p>{period} (단위 : {unit})</p>
    <table><thead><tr><th rowspan="2">구분</th><th colspan="2">보고부문</th><th rowspan="2">부문 합계</th></tr>
    <tr><th>가전</th><th>영상</th></tr></thead><tbody>
    <tr><td>매출액</td><td>700</td><td>300</td><td>1000</td></tr>
    <tr><td>영업이익(손실)</td><td>{profit_a}</td><td>{profit_b}</td><td>{total}</td></tr>
    </tbody></table></html>'''.encode()


class SegmentParserTests(unittest.TestCase):
    def test_negative_profit_and_more_than_100_percent(self):
        result = segments.parse_segment_document(document(), 2025)[0]
        self.assertEqual(result['year'], 2025)
        self.assertEqual(result['total_operating_income'], 100_000_000)
        self.assertEqual(result['segments'][0]['operating_income_share'], 120)
        self.assertEqual(result['segments'][1]['operating_income_share'], -20)
        self.assertEqual(result['segments'][0]['revenue_share'], 70)

    def test_previous_year_is_not_filing_year(self):
        result = segments.parse_segment_document(document(period='전기'), 2025)[0]
        self.assertEqual(result['year'], 2024)

    def test_unit_changes_amount_not_ratio(self):
        result = segments.parse_segment_document(document(unit='억원'), 2025)[0]
        self.assertEqual(result['total_operating_income'], 10_000_000_000)
        self.assertEqual(result['segments'][0]['operating_income_share'], 120)

    def test_unverified_tables_are_rejected(self):
        for raw in [document(total='999'), document(profit_b='-'), document(basis='별도'),
                    document(period='기간 미상'), document(unit='USD')]:
            with self.subTest(raw=raw[:80]):
                self.assertEqual(segments.parse_segment_document(raw, 2025), [])

    def test_loss_total_has_no_contribution_ratio(self):
        result = segments.parse_segment_document(document('10', '(30)', '(20)'), 2025)[0]
        self.assertTrue(all(r['operating_income_share'] is None for r in result['segments']))

    def test_zero_total_has_no_ratio(self):
        result = segments.parse_segment_document(document('20', '(20)', '0'), 2025)[0]
        self.assertIsNone(result['segments'][0]['operating_income_share'])

    def test_conflicting_tables_do_not_silently_pick_first(self):
        raw = document().replace(b'</html>', b'') + document('130', '(30)', '100').replace(b'<html>', b'')
        self.assertEqual(segments.parse_segment_document(raw, 2025), [])

    def test_followup_keeps_segment_topic(self):
        history = [{'role': 'user', 'text': '사업영역 중 영업이익 비중 알려줘'}]
        self.assertTrue(segments.is_segment_question('2024년은?', history))
        self.assertTrue(segments.is_segment_question('이 비중의 의미를 분석해줘', history))
        self.assertTrue(segments.is_segment_question('왜 100%가 넘어?', history))
        self.assertFalse(segments.is_segment_question('2024년은?', []))
        self.assertFalse(segments.is_segment_question('주가 전망은?', history))
        self.assertTrue(segments.is_segment_question('사업 영역 중 영업이익 비중도 알려줘'))
        for question in ['사업 영역 중 영업이익 비중 알려줘', '영업부문 매출 비중 알려줘']:
            self.assertTrue(segments.is_segment_question('2024년은?', [{'text': question}]))

    def test_relative_year_and_followup_metric(self):
        history = [{'role': 'model', 'text': '회사 2024년 사업부별 매출 (연간·연결 기준)'}]
        self.assertEqual(segments.resolve_segment_request('2023년은?', history, 2025), (2023, True))
        self.assertEqual(segments.resolve_segment_request('전년은?', history, 2025), (2023, True))
        self.assertEqual(segments.resolve_segment_request('작년은?', history, 2025), (datetime.now().year - 1, True))
        self.assertEqual(segments.resolve_segment_request('영업이익은?', history, 2025), (2024, False))

    def test_conflicting_tables_across_zip_files_are_rejected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('main.xml', document())
            bundle.writestr('attachment.xml', document('130', '(30)', '100'))
        with patch.object(segments, '_dart_get', return_value={'status': '000', 'list': [
                {'report_nm': '사업보고서 (2025.12)', 'rcept_no': '20260301000001', 'rcept_dt': '20260301'}]}), \
             patch.object(segments, '_dart_get_raw', return_value=archive.getvalue()):
            with self.assertRaises(HTTPException):
                segments.fetch_segment_report('123')

    def test_conflicting_main_is_not_overridden_by_matching_attachment(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('main.xml', document().replace(b'</html>', b'') + document('130', '(30)', '100').replace(b'<html>', b''))
            bundle.writestr('attachment.xml', document())
        with patch.object(segments, '_dart_get', return_value={'status': '000', 'list': [
                {'report_nm': '사업보고서 (2025.12)', 'rcept_no': '20260301000001', 'rcept_dt': '20260301'}]}), \
             patch.object(segments, '_dart_get_raw', return_value=archive.getvalue()):
            with self.assertRaises(HTTPException):
                segments.fetch_segment_report('123')


class SegmentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconciliation_and_cache(self):
        parsed = segments.parse_segment_document(document(), 2025)
        report = {'periods': parsed, 'fiscal_year': 2025, 'fiscal_month': 12,
                  'parser_version': segments.SEGMENT_PARSER_VERSION, 'report_name': '사업보고서 (2025.12)',
                  'provenance': {'source': '원문', 'filed_at': '20260301', 'retrieved_at': '조회시각'}}
        class MemoryCache:
            value = None
            async def get(self, key):
                return self.value
            async def get_or_create(self, key, loader):
                cached = self.value is not None
                if not cached:
                    self.value = await loader()
                return self.value, cached
        cache = MemoryCache()
        with patch.object(segments, 'segment_cache', cache), patch.object(segments, 'fetch_segment_report', return_value=report) as fetch, \
             patch.object(company_data, 'annual_data', AsyncMock(return_value=({'financials': [
                 {'year': 2025, 'fs_div': 'CFS', 'operating_income': 100_000_000, 'revenue': 1_000_000_000}]}, False))):
            result, cached = await segments.segment_data('회사', '123')
            self.assertFalse(cached)
            _, cached = await segments.segment_data('회사', '123')
            self.assertTrue(cached)
            fetch.assert_called_once()
        text = segments.format_segment_answer(result)
        self.assertIn('-20.00%', text)
        self.assertIn('원문', text)
        self.assertIn('2025', text)
        self.assertEqual(result['total_revenue'], 1_000_000_000)

    async def test_internal_revenue_is_not_labeled_consolidated(self):
        report = {'periods': segments.parse_segment_document(document(), 2025), 'fiscal_year': 2025}
        cache = AsyncMock()
        cache.get.return_value = None
        async def load(key, loader):
            return await loader(), False
        cache.get_or_create.side_effect = load
        with patch.object(segments, 'segment_cache', cache), patch.object(segments, 'fetch_segment_report', return_value=report), \
             patch.object(company_data, 'annual_data', AsyncMock(return_value=({'financials': [
                 {'year': 2025, 'fs_div': 'CFS', 'operating_income': 100_000_000, 'revenue': 900_000_000}]}, False))):
            result, _ = await segments.segment_data('회사', '123')
        self.assertIsNone(result['total_revenue'])
        self.assertTrue(all(s['revenue_share'] is None for s in result['segments']))

    async def test_analysis_explains_calculation_without_model_reinterpretation(self):
        request = ai.ChatRequest(message='사업부별 영업이익 비중의 의미를 분석해줘')
        with patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai, 'segment_data', AsyncMock(return_value=(segments.parse_segment_document(document(), 2025)[0], True))), \
             patch.object(ai, 'format_segment_answer', return_value='검증된 수치'), \
             patch.object(ai, 'call_gemini', AsyncMock(return_value='적자 부문의 음수 비중입니다.')) as model:
            response = await ai.chat('회사', request)
        self.assertIn('검증된 수치', response.body.decode())
        self.assertIn('계산 해설', response.body.decode())
        self.assertIn('120.00%', response.body.decode())
        model.assert_not_awaited()

    async def test_wrong_cfs_total_rejected(self):
        report = {'periods': segments.parse_segment_document(document(), 2025)}
        cache = AsyncMock()
        cache.get.return_value = None
        async def load(key, loader):
            return await loader(), False
        cache.get_or_create.side_effect = load
        with patch.object(segments, 'segment_cache', cache), patch.object(segments, 'fetch_segment_report', return_value=report), \
             patch.object(company_data, 'annual_data', AsyncMock(return_value=({'financials': [
                 {'year': 2025, 'fs_div': 'CFS', 'operating_income': 999_000_000}]}, False))):
            with self.assertRaises(HTTPException) as caught:
                await segments.segment_data('회사', '123')
        self.assertEqual(caught.exception.status_code, 404)

    async def test_chat_uses_calculated_facts_without_ai(self):
        request = ai.ChatRequest(message='사업영역 중 영업이익 비중 알려줘')
        with patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai, 'segment_data', AsyncMock(return_value=({'verified': True, 'year': 2025}, True))), \
             patch.object(ai, 'format_segment_answer', return_value='검증된 수치'), \
             patch.object(ai, 'call_gemini', AsyncMock()) as model:
            response = await ai.chat('회사', request)
        self.assertIn('"ai_used":false', response.body.decode())
        model.assert_not_awaited()

    async def test_quarter_is_not_answered_with_annual_data(self):
        request = ai.ChatRequest(message='2025년 3분기 사업부별 영업이익 비중')
        with patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai, 'segment_data', AsyncMock()) as fetch:
            response = await ai.chat('회사', request)
        self.assertIn('분기', response.body.decode())
        fetch.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
