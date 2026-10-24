"""실제 메시지를 보내지 않고 가격 조건·저장·예약 발송의 실패 경계를 검증합니다."""
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import HTTPException
from telegram.error import Forbidden

import bot
import database
from cache import DiskCache
from services import timing

NOW = datetime(2026, 10, 23, 10, 5, tzinfo=ZoneInfo('Asia/Seoul'))


def quote(**changes: object) -> dict:
    """기준시각에 유효한 시세 표본을 만듭니다."""
    return {'stock_code': '005930', 'symbol': '005930.KS', 'price': 70000.0,
            'volume': 100, 'quote_at': (NOW - timedelta(minutes=5)).isoformat(),
            'rsi': 25.0, 'ma': 75000.0, 'history_through': '2026-10-22', **changes}


class IndicatorTests(unittest.TestCase):
    def test_wilder_rsi_known_initial_and_smoothed_values(self):
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                  45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        self.assertAlmostEqual(timing.calculate_rsi(closes), 70.464135, places=5)
        self.assertAlmostEqual(timing.calculate_rsi(closes + [46.0]), 66.249619, places=5)

    def test_rsi_flat_up_down_and_invalid(self):
        self.assertEqual(timing.calculate_rsi([100.] * 30), 50)
        self.assertEqual(timing.calculate_rsi(list(range(1, 31))), 100)
        self.assertEqual(timing.calculate_rsi(list(range(30, 0, -1))), 0)
        for closes in ([1.] * 14, [1.] * 20 + [float('nan')], [1.] * 20 + [0.]):
            self.assertIsNone(timing.calculate_rsi(closes))

    def test_registration_code_target_spaces_and_auto(self):
        self.assertEqual(timing.parse_registration(['005930']), ('005930', None))
        self.assertEqual(timing.parse_registration(['삼성전자', '70,000원']), ('삼성전자', 70000))
        self.assertEqual(timing.parse_registration(['회사', '이름']), ('회사 이름', None))
        self.assertEqual(timing.parse_registration(['회사', 'auto']), ('회사', None))
        for args in ([], ['회사', '0'], ['회사', '-1'], ['회사', 'NaN'], ['회사', 'inf']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                timing.parse_registration(args)

    def test_korean_session_weekend_and_utc(self):
        self.assertTrue(timing.is_market_hours(NOW.astimezone(timezone.utc)))
        self.assertFalse(timing.is_market_hours(NOW.replace(hour=8)))
        self.assertFalse(timing.is_market_hours(NOW.replace(hour=15, minute=31)))
        self.assertFalse(timing.is_market_hours(NOW + timedelta(days=1)))

    def test_freshness_rejects_old_future_naive_and_invalid_quotes(self):
        self.assertTrue(timing.is_fresh_quote(quote(), NOW))
        for changes in ({'quote_at': (NOW - timedelta(days=1)).isoformat()},
                        {'quote_at': (NOW - timedelta(minutes=21)).isoformat()},
                        {'quote_at': (NOW + timedelta(seconds=1)).isoformat()},
                        {'quote_at': NOW.replace(tzinfo=None).isoformat()},
                        {'quote_at': 'bad'}, {'price': float('nan')}, {'price': float('inf')},
                        {'price': 0}, {'volume': 0}, {'volume': float('nan')}):
            with self.subTest(changes=changes):
                self.assertFalse(timing.is_fresh_quote(quote(**changes), NOW))

    def test_conditions_boundaries_and_no_data(self):
        auto = {'target_price': None}
        self.assertEqual(timing.evaluate_watch(auto, quote(rsi=30, price=75000), NOW), 'matched')
        self.assertEqual(timing.evaluate_watch(auto, quote(rsi=30.00001), NOW), 'not_matched')
        self.assertEqual(timing.evaluate_watch(auto, quote(price=75001), NOW), 'not_matched')
        self.assertEqual(timing.evaluate_watch(auto, quote(rsi=None), NOW), 'insufficient_data')
        self.assertEqual(timing.evaluate_watch(auto, None, NOW), 'unavailable')
        self.assertEqual(timing.evaluate_watch(auto, quote(quote_at='invalid'), NOW), 'stale')
        self.assertEqual(timing.evaluate_watch({'target_price': 70000}, quote(rsi=None, ma=None), NOW), 'matched')
        self.assertEqual(timing.evaluate_watch({'target_price': 69999}, quote(), NOW), 'not_matched')

    def test_message_escapes_company_and_reports_candle_basis(self):
        watch = {'company': '<삼성&전자>', 'stock_code': '005930', 'target_price': None}
        text = timing.build_alert_message(watch, quote())
        self.assertIn('&lt;삼성&amp;전자&gt;', text)
        for value in ('70,000원', '25.0', '2026-10-23 10:00', '5분봉 시작시각', '지연 가능', '보장하지'):
            self.assertIn(value, text)


class _ClosingCache(DiskCache):
    """Windows에서 테스트 작업 스레드의 캐시 연결을 즉시 정리합니다."""

    def _get_sync(self, key: str) -> dict | None:
        try:
            return super()._get_sync(key)
        finally:
            self._cache.close()

    def _set_sync(self, key: str, value: dict) -> None:
        try:
            super()._set_sync(key, value)
        finally:
            self._cache.close()


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = _ClosingCache(str(Path(self.temp.name) / 'cache'))
        self.patcher = patch.object(timing, 'timing_cache', self.cache)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()
        self.cache._cache.close()
        self.temp.cleanup()

    async def test_shared_cache_and_same_name_different_code(self):
        with patch.object(timing, '_fetch_snapshot', return_value=quote()) as fetch:
            first, second = await asyncio.gather(timing.get_price_snapshot('회사', '005930'),
                                                 timing.get_price_snapshot('회사', '005930'))
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertEqual(fetch.call_count, 1)
            fetch.return_value = quote(stock_code='000660')
            third = await timing.get_price_snapshot('회사', '000660')
            self.assertFalse(third['cached'])
            self.assertEqual(fetch.call_count, 2)

    async def test_failure_not_cached_and_shared_across_subscribers(self):
        with patch.object(timing, '_fetch_snapshot', side_effect=ValueError('no quote')):
            results = await timing.collect_snapshots([
                {'company': '회사', 'stock_code': '005930'}, {'company': '회사', 'stock_code': '005930'}])
            self.assertIsNone(results['005930'])
            self.assertIsNone(await self.cache.get('회사'))
        with patch.object(timing, 'get_price_snapshot', AsyncMock(return_value=quote())) as fetch:
            await timing.collect_snapshots([
                {'company': '회사', 'stock_code': '005930'}, {'company': '다른 표기', 'stock_code': '005930'}])
            self.assertEqual(fetch.await_count, 1)

    def test_kosdaq_fallback_completed_daily_and_partial_day_not_duplicated(self):
        quotes = pd.DataFrame({'Close': [70000.], 'Volume': [100]},
                              index=pd.DatetimeIndex([NOW - timedelta(minutes=5)]))
        dates = pd.date_range(end=NOW.date(), periods=45, freq='B', tz='Asia/Seoul')
        history = pd.DataFrame({'Close': [80000. - i * 100 for i in range(44)] + [1.]}, index=dates)
        kospi, kosdaq = MagicMock(), MagicMock()
        kospi.history.return_value = pd.DataFrame()
        kosdaq.history.side_effect = [quotes, history]
        with patch.object(timing.yf, 'Ticker', side_effect=[kospi, kosdaq]):
            result = timing._fetch_snapshot('005930')
        self.assertEqual(result['symbol'], '005930.KQ')
        self.assertEqual(result['history_through'], '2026-10-22')
        self.assertLess(result['rsi'], 30)
        self.assertAlmostEqual(result['ma'], (sum(history['Close'].tolist()[-20:-1]) + 70000) / 20)

    def test_missing_daily_still_allows_target_but_not_automatic(self):
        candles = pd.DataFrame({'Close': [70000.], 'Volume': [100]},
                               index=pd.DatetimeIndex([NOW - timedelta(minutes=5)]))
        ticker = MagicMock()
        ticker.history.side_effect = [candles, RuntimeError('daily error')]
        with patch.object(timing.yf, 'Ticker', return_value=ticker):
            result = timing._fetch_snapshot('005930')
        self.assertEqual(timing.evaluate_watch({'target_price': 70000}, result, NOW), 'matched')
        self.assertEqual(timing.evaluate_watch({'target_price': None}, result, NOW), 'insufficient_data')


class TimingDatabaseCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patchers = [patch.object(database, 'DB_PATH', str(Path(self.temp.name) / 'db.sqlite3')),
                         patch.object(timing, 'now_kst', return_value=NOW),
                         patch.object(timing, 'notification_lock', asyncio.Lock()),
                         patch.object(timing, 'collect_snapshots', AsyncMock(return_value={'005930': quote()}))]
        for p in self.patchers:
            p.start()
        await database.init_db()
        self.transport = SimpleNamespace(send_message=AsyncMock())
        await database.save_timing_watch(1, '삼성전자', '005930', None)

    async def asyncTearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.temp.cleanup()


class DeliveryTests(TimingDatabaseCase):
    async def test_repeated_concurrent_checks_restart_and_next_day(self):
        await asyncio.gather(bot.send_timing_alerts(self.transport), bot.send_timing_alerts(self.transport))
        self.assertEqual(self.transport.send_message.await_count, 1)
        await database.init_db()
        await bot.send_timing_alerts(self.transport)
        self.assertEqual(self.transport.send_message.await_count, 1)
        next_day = NOW + timedelta(days=3)
        with patch.object(timing, 'now_kst', return_value=next_day), patch.object(
                timing, 'collect_snapshots', AsyncMock(return_value={
                    '005930': quote(quote_at=next_day.isoformat())})):
            await bot.send_timing_alerts(self.transport)
        self.assertEqual(self.transport.send_message.await_count, 2)

    async def test_failed_send_is_retryable_and_does_not_block_other_chat(self):
        await database.save_timing_watch(2, '삼성전자', '005930', None)
        self.transport.send_message.side_effect = [RuntimeError('transport'), None]
        await bot.send_timing_alerts(self.transport)
        first, second = await database.get_timing_watches()
        self.assertIsNone(first['last_alert_day'])
        self.assertEqual(first['last_status'], 'delivery_failed')
        self.assertEqual(second['last_alert_day'], '2026-10-23')
        self.transport.send_message.side_effect = None
        await bot.send_timing_alerts(self.transport)
        self.assertEqual(self.transport.send_message.await_count, 3)

    async def test_forbidden_unsubscribes_only_affected_chat(self):
        await database.save_timing_watch(2, '삼성전자', '005930', None)
        self.transport.send_message.side_effect = [Forbidden('blocked'), None]
        await bot.send_timing_alerts(self.transport)
        watches = await database.get_timing_watches()
        self.assertEqual([w['chat_id'] for w in watches], [2])
        self.assertEqual(watches[0]['last_status'], 'sent')

    async def test_closed_market_holiday_stale_and_unavailable_skip(self):
        for now in (NOW.replace(hour=8), NOW + timedelta(days=1)):
            with patch.object(timing, 'now_kst', return_value=now):
                await bot.send_timing_alerts(self.transport)
        timing.collect_snapshots.assert_not_awaited()
        for snapshot, status in ((quote(quote_at=(NOW-timedelta(days=1)).isoformat()), 'stale'),
                                 (None, 'unavailable'), (quote(rsi=None), 'insufficient_data')):
            with patch.object(timing, 'collect_snapshots', AsyncMock(return_value={'005930': snapshot})):
                await bot.send_timing_alerts(self.transport)
            self.assertEqual((await database.get_timing_watches())[0]['last_status'], status)
        self.transport.send_message.assert_not_awaited()

    async def test_quote_expires_during_fetch(self):
        with patch.object(timing, 'now_kst', side_effect=[NOW, NOW+timedelta(hours=1)]):
            await bot.send_timing_alerts(self.transport)
        self.transport.send_message.assert_not_awaited()

    async def test_edit_or_delete_during_collection_prevents_old_alert(self):
        async def edited(watches: list[dict]) -> dict:
            await database.save_timing_watch(1, '삼성전자', '005930', 1.)
            return {'005930': quote()}
        with patch.object(timing, 'collect_snapshots', side_effect=edited):
            await bot.send_timing_alerts(self.transport)
        self.transport.send_message.assert_not_awaited()
        async def deleted(watches: list[dict]) -> dict:
            await database.remove_timing_watch(1, '005930')
            return {'005930': quote()}
        with patch.object(timing, 'collect_snapshots', side_effect=deleted):
            await bot.send_timing_alerts(self.transport)
        self.transport.send_message.assert_not_awaited()

    async def test_update_preserves_daily_limit_and_noop_preserves_revision(self):
        before = (await database.get_timing_watches())[0]
        await database.save_timing_watch(1, '삼성전자', '005930', None)
        self.assertEqual((await database.get_timing_watches())[0]['revision'], before['revision'])
        await bot.send_timing_alerts(self.transport)
        await database.save_timing_watch(1, '삼성전자', '005930', 80000.)
        await bot.send_timing_alerts(self.transport)
        self.assertEqual(self.transport.send_message.await_count, 1)

    async def test_edit_during_send_preserves_success_and_new_condition(self):
        async def send(**kwargs: object) -> None:
            await database.save_timing_watch(1, '삼성전자', '005930', 80000.)
        self.transport.send_message.side_effect = send
        await bot.send_timing_alerts(self.transport)
        saved = (await database.get_timing_watches(1))[0]
        self.assertEqual(saved['target_price'], 80000)
        self.assertEqual(saved['last_alert_day'], '2026-10-23')
        self.assertEqual(saved['last_status'], 'waiting')
        await bot.send_timing_alerts(self.transport)
        self.assertEqual(self.transport.send_message.await_count, 1)

    async def test_delete_and_reregister_during_send_does_not_mark_new_subscription(self):
        async def send(**kwargs: object) -> None:
            await database.remove_timing_watch(1, '005930')
            await database.save_timing_watch(1, '삼성전자', '005930', 80000.)
        self.transport.send_message.side_effect = send
        await bot.send_timing_alerts(self.transport)
        self.assertIsNone((await database.get_timing_watches(1))[0]['last_alert_day'])

    async def test_watch_limit_and_chat_isolation(self):
        with patch.object(database, 'TIMING_MAX_WATCHES', 1):
            with self.assertRaises(ValueError):
                await database.save_timing_watch(1, '다른회사', '000660', None)
            await database.save_timing_watch(1, '삼성전자', '005930', 70000.)
        await database.save_timing_watch(2, '다른회사', '000660', None)
        self.assertFalse(await database.remove_timing_watch(2, '005930'))
        self.assertEqual(len(await database.get_timing_watches(2)), 1)
        self.assertTrue(await database.remove_timing_watch(1, '삼성전자'))


class CommandTests(TimingDatabaseCase):
    def update(self, chat_type: str = 'private') -> SimpleNamespace:
        """텍스트 명령 검증용 개인 채팅 업데이트를 만듭니다."""
        message = SimpleNamespace(reply_text=AsyncMock())
        return SimpleNamespace(effective_chat=SimpleNamespace(id=1, type=chat_type),
                               effective_message=message, message=message)

    async def test_registration_lookup_code_and_html(self):
        update = self.update()
        ctx = SimpleNamespace(args=['005930', '70,000'])
        with patch.object(bot, 'get_company_info', return_value={
                'company_name': '<삼성전자>', 'stock_code': '005930'}) as lookup:
            await bot.cmd_timing(update, ctx)
        lookup.assert_called_once_with('005930')
        saved = (await database.get_timing_watches(1))[0]
        self.assertEqual(saved['target_price'], 70000)
        self.assertIn('&lt;삼성전자&gt;', update.message.reply_text.call_args.args[0])

    async def test_invalid_or_unlisted_company_not_saved(self):
        await database.remove_timing_watch(1, '005930')
        for info in ({'company_name': '비상장', 'stock_code': None}, HTTPException(404, '<없음>')):
            update = self.update()
            kwargs = {'side_effect': info} if isinstance(info, Exception) else {'return_value': info}
            with patch.object(bot, 'get_company_info', **kwargs):
                await bot.cmd_timing(update, SimpleNamespace(args=['회사']))
            self.assertEqual(await database.get_timing_watches(1), [])
        self.assertIn('&lt;없음&gt;', update.message.reply_text.call_args.args[0])

    async def test_groups_cannot_register_list_or_delete(self):
        with patch.object(bot, 'get_company_info') as lookup:
            for handler in (bot.cmd_timing, bot.cmd_timing_list, bot.cmd_timing_del):
                update = self.update('group')
                await handler(update, SimpleNamespace(args=['005930']))
                self.assertIn('개인 채팅', update.message.reply_text.call_args.args[0])
            lookup.assert_not_called()
        self.assertEqual(len(await database.get_timing_watches(1)), 1)

    async def test_list_and_delete_without_external_lookup(self):
        await bot.send_timing_alerts(self.transport)
        update = self.update()
        with patch.object(bot, 'get_company_info') as lookup:
            await bot.cmd_timing_list(update, SimpleNamespace(args=[]))
            self.assertIn('70,000원', update.message.reply_text.call_args.args[0])
            await bot.cmd_timing_del(update, SimpleNamespace(args=['005930']))
            lookup.assert_not_called()
        self.assertEqual(await database.get_timing_watches(1), [])


if __name__ == '__main__':
    unittest.main()
