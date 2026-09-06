"""실제 AI/외부 API 비용 없이 분석 신뢰성과 호출 수를 검증합니다."""
import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cache import DiskCache
from services import company_data, ai_policy, factual, events
from services.dart import _accounts_to_metrics, _fetch_dividend_common, fetch_filing_list
from services.scoring import compute_investment_score, compute_owner_earnings, _cagr, compute_yoy_highlights
from services.report import _build_data_section
from services.filing_alert import build_filing_alert_message
from routes import ai
from fastapi import HTTPException


FIN = [{'year': y, 'fs_div': 'CFS', 'revenue': 1000, 'operating_income': 100,
        'net_income': 80, 'roe': 10, 'operating_margin': 10, 'debt_ratio': 50,
        'equity': 800, 'total_assets': 1200, 'liabilities': 400, 'fcf': 90,
        'eps': 10} for y in (2022, 2023, 2024, 2025)]


class ArithmeticTests(unittest.TestCase):
    def test_zero_and_missing_capex(self):
        accounts = {key: {'thstrm_amount': str(v)} for key, v in {
            '매출액': 100, '영업이익': 0, '당기순이익': 0, '자본총계': 100,
            '부채총계': 0, '영업활동현금흐름': 30}.items()}
        result = _accounts_to_metrics(accounts, 2025, 'CFS')
        self.assertEqual([result[k] for k in ('roe', 'operating_margin', 'debt_ratio')], [0, 0, 0])
        self.assertIsNone(result['fcf'])
        self.assertIsNone(result['net_debt'])

    def test_missing_is_not_zero_dividend(self):
        missing = compute_investment_score(FIN, [], None)
        zero = compute_investment_score(FIN, [{'year': 2025, 'dividend': 0}], {'per': 12})
        self.assertIsNone(missing['categories']['dividend']['score'])
        self.assertIsNone(missing['total_score'])
        self.assertIsNotNone(zero['categories']['dividend']['score'])
        self.assertIsNotNone(zero['total_score'])

    def test_negative_cagr_and_gaps(self):
        self.assertIsNone(_cagr(100, -10, 3))
        self.assertEqual(_cagr(100, 0, 3), -1)
        rows = [dict(FIN[0], year=2020, revenue=100), dict(FIN[-1], year=2025, revenue=200)]
        self.assertEqual(compute_yoy_highlights(rows), [])
        score = compute_investment_score(rows, [], None)
        self.assertEqual(score['categories']['growth']['details']['revenue_cagr'], '14.9%')

    def test_owner_earnings_not_invented(self):
        self.assertIsNone(compute_owner_earnings([dict(FIN[-1], fcf=None)])[0]['owner_earnings'])

    def test_report_handles_zero_and_negative_profit(self):
        rows = [dict(FIN[0], net_income=100), dict(FIN[-1], net_income=-10, roe=0)]
        text = _build_data_section('회사', [], rows, [], {'price': None, 'per': 0})
        self.assertIn('ROE 0%', text)
        self.assertIn('평가 불가', text)

    def test_explicit_zero_dividend_preserved(self):
        with patch('services.dart._fetch_with_fs_fallback', return_value=({'주당 현금배당금': {'thstrm_amount': '0'}}, 'OFS')):
            self.assertEqual(_fetch_dividend_common('123', '2025', '11011'), 0)

    def test_filing_failure_different_from_no_filings(self):
        with patch('services.dart._dart_get', return_value={'status': '013'}):
            self.assertEqual(fetch_filing_list('123', '20250101', strict=True), [])
        with patch('services.dart._dart_get', return_value={'status': '020'}):
            with self.assertRaises(HTTPException):
                fetch_filing_list('123', '20250101', strict=True)

    def test_missing_assets_does_not_crash_report(self):
        text = _build_data_section('회사', [], [dict(FIN[-1], total_assets=None)], [], None)
        self.assertIn('데이터 부족', text)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.caches = []
        self.patchers = []
        for name in ('financials_cache', 'dividend_cache', 'valuation_cache', 'business_cache', 'filings_cache'):
            cache = self.cache(name)
            p = patch.object(company_data, name, cache)
            p.start(); self.patchers.append(p)

    def cache(self, name='test', ttl=60):
        cache = DiskCache(str(Path(self.temp.name) / name), ttl=ttl)
        self.caches.append(cache)
        return cache

    async def asyncTearDown(self):
        for p in self.patchers:
            p.stop()
        for cache in self.caches:
            cache._cache.close()
        self.temp.cleanup()

    async def test_cold_warm_and_concurrent_inputs_match(self):
        year = company_data.datetime.now().year
        def fetch_fin(corp, requested):
            return dict(FIN[-1], year=int(requested)) if int(requested) != year - 1 else None
        with patch.object(company_data, 'fetch_dart_financials', side_effect=fetch_fin) as fin, \
             patch.object(company_data, 'fetch_dividend_per_share', return_value=0) as div, \
             patch.object(company_data, 'fetch_valuation', return_value={'per': 12, 'latest_year': year - 2}) as val:
            cold, duplicate = await asyncio.gather(*[company_data.gather_company_data('123', '회사', narrative=False) for _ in range(2)])
            warm = await company_data.gather_company_data('123', '회사', narrative=False)
        self.assertEqual(cold, warm)
        self.assertEqual(cold, duplicate)
        self.assertEqual(fin.call_count, 6)
        self.assertEqual(div.call_count, 6)
        self.assertEqual(val.call_count, 1)
        self.assertEqual(len(cold['financials']), 5)
        self.assertEqual(cold['financials'][0]['year'], year - 6)
        self.assertTrue(cold['data_quality']['warnings'])

    async def test_valuation_receives_same_snapshot_and_rebuilds_on_change(self):
        with patch.object(company_data, 'fetch_valuation', return_value={'latest_year': 2025, 'per': 12}) as fetch:
            await company_data.valuation_data('회사', '123', FIN)
            self.assertEqual(fetch.call_args.args[1], FIN)
            await company_data.valuation_data('회사', '123', FIN)
            changed = copy.deepcopy(FIN)
            changed[-1]['net_income'] = 10
            await company_data.valuation_data('회사', '123', changed)
            self.assertEqual(fetch.call_count, 2)

    async def test_filing_failure_not_cached(self):
        with patch.object(company_data, 'fetch_filing_list', side_effect=HTTPException(502, 'offline')):
            with self.assertRaises(HTTPException):
                await company_data.recent_filings('회사', '123')
        self.assertIsNone(await company_data.filings_cache.get('회사'))

    async def test_optional_failure_is_disclosed(self):
        with patch.object(company_data, 'fetch_dart_financials', return_value=FIN[-1]), \
             patch.object(company_data, 'fetch_dividend_per_share', side_effect=RuntimeError('offline')), \
             patch.object(company_data, 'fetch_valuation', side_effect=RuntimeError('offline')):
            data = await company_data.gather_company_data('123', '회사', narrative=False)
        self.assertEqual(data['dividends'], [])
        self.assertIsNone(data['valuation'])
        self.assertGreaterEqual(len(data['data_quality']['warnings']), 2)

    async def test_ai_deduplicates_and_invalidates_changed_input(self):
        cache = self.cache()
        generate = AsyncMock(return_value='근거 기반 해석')
        with patch.object(ai_policy, 'GEMINI_API_KEY', 'test-only'):
            results = await asyncio.gather(*[ai_policy.cached_inference(cache, '회사', {'value': 1}, generate) for _ in range(4)])
            self.assertEqual(generate.await_count, 1)
            self.assertEqual(sum(not hit for _, hit in results), 1)
            await ai_policy.cached_inference(cache, '회사', {'value': 2}, generate)
            self.assertEqual(generate.await_count, 2)
        self.assertEqual(company_data.input_fingerprint({'retrieved_at': 'a', 'value': 1}),
                         company_data.input_fingerprint({'retrieved_at': 'b', 'value': 1}))

    async def test_malformed_event_not_treated_as_success(self):
        from datetime import datetime, timezone
        articles = [{'title': '기사', 'summary': '기사 설명', 'url': 'https://example.com',
                     '_parsed_date': datetime.now(timezone.utc)}]
        for response in ('(AI 응답 생성 실패)', '{"events":[{"headline":"사건","summary":"설명","article_indices":[true,"1"]}]}'):
            with patch.object(events, 'call_groq', AsyncMock(return_value=response)):
                with self.assertRaises(HTTPException):
                    await events._select_events('회사', articles)

    async def test_ai_failure_not_cached(self):
        cache = self.cache()
        with patch.object(ai_policy, 'GEMINI_API_KEY', 'test-only'):
            with self.assertRaises(HTTPException) as exc:
                await ai_policy.cached_inference(cache, '회사', {}, AsyncMock(return_value='(AI 응답 생성 실패)'))
        self.assertEqual(exc.exception.status_code, 502)
        self.assertIsNone(await cache.get('회사'))

    async def test_old_and_expired_cache_not_reused(self):
        cache = self.cache(ttl=-1)
        cache._cache.set('old', {'financials': FIN})
        self.assertIsNone(await cache.get('old'))
        await cache.set('expired', {'value': 1})
        self.assertIsNone(await cache.get('expired'))

    async def test_factual_chat_uses_no_ai(self):
        with patch.object(factual, 'annual_data', AsyncMock(return_value=({'financials': FIN, 'provenance': {'retrieved_at': 'now'}}, True))), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'chat_with_gemini', AsyncMock(side_effect=AssertionError('Unexpected AI'))):
            result = await ai.chat('회사', ai.ChatRequest(message='2025년 매출 알려줘'))
            self.assertFalse(json.loads(result.body)['ai_used'])
            self.assertIsNone(await factual.answer_factual('회사', '123', '매출이 감소한 이유는?'))

    async def test_alert_no_ai_and_html_safe(self):
        with patch('utils.call_gemini', AsyncMock(side_effect=AssertionError('Unexpected AI'))):
            text = await build_filing_alert_message('<회사>', {'report_nm': '<유상증자>', 'rcept_dt': '20260905', 'rcept_no': '123'})
        self.assertIn('&lt;회사&gt;', text)
        self.assertIn('&lt;유상증자&gt;', text)
        self.assertIn('원문', text)

    async def test_insider_default_no_ai_and_cached(self):
        with patch.object(ai, 'insider_cache', self.cache('insider')), \
             patch.object(ai, 'resolve_corp_code', AsyncMock(return_value='123')), \
             patch.object(ai.database, 'record_search', AsyncMock()), \
             patch.object(ai, 'fetch_insider_trading', return_value={'holdings': [], 'recent_filings': [{'filer': '<x>'}]}), \
             patch.object(ai, 'analyze_insider_with_gemini', AsyncMock(side_effect=AssertionError('Unexpected AI'))):
            first = await ai.get_insider_trading('회사')
            second = await ai.get_insider_trading('회사')
        self.assertFalse(first['ai_used'])
        self.assertEqual(first['ai_analysis'], '')
        self.assertTrue(second['cached'])


if __name__ == '__main__':
    unittest.main()
