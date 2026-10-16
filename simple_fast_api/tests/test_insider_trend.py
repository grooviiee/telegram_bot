"""실제 매매 사유 분리, 원문 집계와 텔레그램 그래프 응답을 검증합니다."""
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cache import DiskCache
from services import insider_trend
from services.insider_trend import parse_insider_document, aggregate_insider_trades, fetch_insider_filings
from services.insider_chart import render_insider_chart
from fastapi import HTTPException
from config import TRENDING_TIMEZONE
import bot


def document(reason: str, quantity: str, kind: str = '보통주', when: str = '20250512') -> bytes:
    """표준 공시의 거래 행과 중복하면 안 되는 합계 행을 생성합니다."""
    return f'''<DOCUMENT><TABLE><TBODY><TR>
    <TU AUNIT="RPT_RSN">{reason}</TU><TU AUNIT="MDF_DM" AUNITVALUE="{when}"/>
    <TU AUNIT="STR_KND">{kind}</TU><TE ACODE="MDF_STK_CNT">{quantity}</TE>
    </TR><TR><TE ACODE="MDF_STK_SUM">9999</TE></TR></TBODY></TABLE></DOCUMENT>'''.encode()


def chart_data(complete: bool = True) -> dict:
    """그래프와 봇 응답용 최소 집계 데이터를 반환합니다."""
    docs = [parse_insider_document(document('장내매수(+)', '100')),
            parse_insider_document(document('장외매도(-)', '-50'))]
    monthly, annual = aggregate_insider_trades(docs, date(2024, 1, 1), date(2026, 10, 16), complete)
    return {'company_name': '<삼성전자>', 'start_date': '2024-01-01', 'end_date': '2026-10-16',
            'monthly': monthly, 'annual': annual, 'coverage_complete': complete,
            'filings_total': 2, 'filings_parsed': 2, 'filings_failed': 0, 'invalid_rows': 0,
            'recent_sources': [{'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250512000001'}]}


class InsiderParserTests(unittest.TestCase):
    def test_trade_reasons_not_holding_sign(self):
        for reason, quantity, side in (('장내매수(+)', '1,200', 'buy'), ('장외매도(-)', '-800', 'sell')):
            parsed = parse_insider_document(document(reason, quantity))
            self.assertEqual(len(parsed['trades']), 1)
            self.assertEqual(parsed['trades'][0]['side'], side)
            self.assertEqual(parsed['invalid_rows'], 0)
        for reason in ('증여(+)', '상속(+)', '주식매수선택권행사(+)', '신규보고(+)'):
            parsed = parse_insider_document(document(reason, '100'))
            self.assertEqual(parsed['trades'], [])
            self.assertEqual(parsed['invalid_rows'], 0)

    def test_non_stock_and_malformed_are_not_counted(self):
        parsed = parse_insider_document(document('장내매수(+)', '100', '전환사채권'))
        self.assertEqual(parsed['excluded_rows'], 1)
        for raw in (document('장내매수(+)', '-100'), document('장내매수(+)', '100', when='invalid')):
            self.assertEqual(parse_insider_document(raw)['invalid_rows'], 1)
        with self.assertRaises(ValueError):
            parse_insider_document(b'<DOCUMENT/>')

    def test_monthly_trade_date_and_incomplete_zero(self):
        docs = [parse_insider_document(document('장내매수(+)', '100'))]
        monthly, annual = aggregate_insider_trades(docs, date(2024, 1, 1), date(2026, 10, 16), True)
        self.assertEqual(len(monthly), 34)
        self.assertEqual(monthly[16]['buy'], 100)
        self.assertEqual(annual[1]['buy'], 100)
        self.assertEqual(annual[1]['sell'], 0)
        self.assertTrue(annual[-1]['partial_year'])
        monthly, annual = aggregate_insider_trades(docs, date(2024, 1, 1), date(2026, 10, 16), False)
        self.assertIsNone(annual[1]['sell'])
        self.assertEqual(annual[1]['buy'], 100)

    def test_pagination_final_reports_and_receipt_dedup(self):
        record = {'rcept_no': '20250512000001'}
        with patch.object(insider_trend, '_dart_get', side_effect=[
            {'status': '000', 'total_page': 2, 'list': [record]},
            {'status': '000', 'total_page': 2, 'list': [record, {'rcept_no': '20250513000001'}]},
        ]) as get:
            result = fetch_insider_filings('test', date(2024, 1, 1), date(2026, 10, 16))
        self.assertEqual(len(result), 2)
        self.assertEqual(get.call_args.args[1]['last_reprt_at'], 'Y')
        self.assertEqual(get.call_args.args[1]['page_no'], 2)

    def test_png(self):
        for complete in (True, False):
            with render_insider_chart(chart_data(complete)) as image:
                self.assertEqual(image.read(8), b'\x89PNG\r\n\x1a\n')


class InsiderServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # SQLite의 스레드별 연결을 확실히 닫을 수 있도록 테스트의 I/O 스레드를 고정합니다.
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        self.temp = tempfile.TemporaryDirectory()
        self.aggregate = DiskCache(str(Path(self.temp.name) / 'aggregate'))
        self.documents = DiskCache(str(Path(self.temp.name) / 'documents'))
        self.patches = [patch.object(insider_trend, 'insider_trend_cache', self.aggregate),
                        patch.object(insider_trend, 'insider_document_cache', self.documents),
                        patch.object(insider_trend, '_document_slots', asyncio.Semaphore(8)),
                        patch.object(insider_trend, '_wait_document_slot', AsyncMock())]
        for p in self.patches:
            p.start()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()
        self.aggregate._cache.close()
        self.documents._cache.close()
        # diskcache 스레드별 연결도 종료되어야 Windows에서 삭제할 수 있습니다.
        await asyncio.to_thread(self.aggregate._cache.close)
        await asyncio.to_thread(self.documents._cache.close)
        self.temp.cleanup()

    async def test_success_cached_and_second_call_skips_collection(self):
        record = {'rcept_no': '20250512000001'}
        parsed = parse_insider_document(document('장내매수(+)', '100'))
        with patch.object(insider_trend, 'fetch_insider_filings', return_value=[record]) as filings, \
             patch.object(insider_trend, 'fetch_insider_document', return_value=parsed) as fetch:
            first, cached = await insider_trend.insider_trend_data('삼성전자', 'test')
            second, hit = await insider_trend.insider_trend_data('삼성전자', 'test')
        self.assertFalse(cached)
        self.assertTrue(hit)
        self.assertEqual(first, second)
        self.assertEqual(filings.call_count, 1)
        self.assertEqual(fetch.call_count, 1)

    async def test_partial_preserves_coverage_and_zero_is_unknown(self):
        records = [{'rcept_no': '20250512000001'}, {'rcept_no': '20250513000001'}]
        with patch.object(insider_trend, 'fetch_insider_filings', return_value=records), \
             patch.object(insider_trend, 'fetch_insider_document', side_effect=[parse_insider_document(document('장내매수(+)', '100')), ValueError('unsupported')]):
            result, _ = await insider_trend.insider_trend_data('삼성전자', 'test')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['filings_failed'], 1)
        self.assertIsNone(result['annual'][0]['sell'])
        cached = await self.aggregate.get('삼성전자')
        self.assertFalse(cached['coverage_complete'])

    async def test_empty_and_list_failure(self):
        for value, expected in (([], 404), (RuntimeError('upstream'), 502)):
            with patch.object(insider_trend, 'fetch_insider_filings', side_effect=value if isinstance(value, Exception) else None, return_value=value):
                with self.assertRaises(HTTPException) as error:
                    await insider_trend.insider_trend_data('삼성전자', 'test')
            self.assertEqual(error.exception.status_code, expected)

    async def test_list_failure_uses_dated_snapshot(self):
        record = {'rcept_no': '20250512000001'}
        with patch.object(insider_trend, 'fetch_insider_filings', return_value=[record]), \
             patch.object(insider_trend, 'fetch_insider_document', return_value=parse_insider_document(document('장내매수(+)', '100'))):
            result, _ = await insider_trend.insider_trend_data('삼성전자', 'test')
        result['coverage_complete'] = False
        result['collected_at'] = (datetime.now(ZoneInfo(TRENDING_TIMEZONE)) - timedelta(minutes=10)).isoformat()
        await self.aggregate.set('삼성전자', result)
        with patch.object(insider_trend, 'fetch_insider_filings', side_effect=RuntimeError('offline')):
            stale, cached = await insider_trend.insider_trend_data('삼성전자', 'test')
        self.assertTrue(cached)
        self.assertTrue(stale['refresh_failed'])
        self.assertEqual(stale['end_date'], result['end_date'])


class InsiderBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_returns_before_collection(self):
        tasks = []
        application = Mock()
        application.create_task.side_effect = lambda coroutine, **kwargs: tasks.append(coroutine)
        ctx = SimpleNamespace(args=['삼성전자'], application=application)
        update = AsyncMock()
        with patch.object(bot, '_send_insider_chart', AsyncMock()) as send:
            await bot.cmd_insider(update, ctx)
            send.assert_not_awaited()
            self.assertEqual(len(tasks), 1)
            await tasks[0]
            send.assert_awaited_once()

    async def test_photo_and_escaped_caption(self):
        msg = AsyncMock()
        with patch.object(bot, '_get', AsyncMock(return_value=(chart_data(), 200))):
            await bot._send_insider_chart(msg, '삼성전자')
        msg.reply_photo.assert_awaited_once()
        self.assertIn('&lt;삼성전자&gt;', msg.reply_photo.call_args.kwargs['caption'])
        self.assertLess(len(msg.reply_photo.call_args.kwargs['caption']), 1024)


if __name__ == '__main__':
    unittest.main()
