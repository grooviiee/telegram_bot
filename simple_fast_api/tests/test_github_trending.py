"""외부 비용 없이 GitHub 소개 선정·캐시·발송을 검증합니다."""
import asyncio
import tempfile
import unittest
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot
import database
from cache import DiskCache
from services import github_trending as trending
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from routes.github import router

NOW = datetime(2026, 10, 15, 9, tzinfo=ZoneInfo('Asia/Seoul'))
PROJECTS = [{'name': f'owner/p{i}', 'url': f'https://github.com/owner/p{i}',
             'description': '<tool>', 'language': 'Python', 'stars_today': 1000-i,
             'stars': 2000} for i in range(5)]


class ParserTests(unittest.TestCase):
    def test_growth_ranking_and_unknown(self):
        def row(name, growth, stars):
            return f'<article class="Box-row"><h2><a href="/{name}">x</a></h2><p>desc</p><a href="/{name}/stargazers">{stars}</a><span>{growth}</span></article>'
        result = trending.parse_trending(row('a/old', '100 stars today', '90,000') + row('b/new', '1,234 stars today', '2,000') + row('c/unknown', '', '99,999'))
        self.assertEqual([p['name'] for p in result], ['b/new', 'a/old'])
        self.assertEqual(result[0]['stars_today'], 1234)

    def test_structure_failure(self):
        with self.assertRaises(HTTPException) as error:
            trending.parse_trending('<html>Sign in</html>')
        self.assertEqual(error.exception.status_code, 502)


class DigestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.caches = [DiskCache(str(Path(self.temp.name) / p)) for p in ('source', 'summary')]
        self.patchers = [patch.object(database, 'DB_PATH', str(Path(self.temp.name) / 'db.sqlite3')),
                         patch.object(trending, 'github_trending_cache', self.caches[0]),
                         patch.object(trending, 'github_summary_cache', self.caches[1]),
                         patch.object(trending.config, 'GEMINI_API_KEY', ''),
                         patch.object(trending, 'now_kst', return_value=NOW),
                         patch.object(trending, 'fetch_readme', AsyncMock(return_value='README'))]
        for p in self.patchers:
            p.start()
        trending._locks.clear()
        await database.init_db()

    async def asyncTearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        for cache in self.caches:
            cache._cache.close()
        trending._locks.clear()
        self.temp.cleanup()

    async def test_seven_days_cache_and_shared_collection(self):
        await database.mark_trending_delivered(1, '2026-10-08', ['owner/p0'])
        await database.mark_trending_delivered(1, '2026-10-07', ['owner/p1'])
        with patch.object(trending, 'fetch_trending', AsyncMock(return_value=PROJECTS)) as fetch:
            first, concurrent = await asyncio.gather(trending.get_digest(1, NOW), trending.get_digest(1, NOW))
            other = await trending.get_digest(2, NOW)
        self.assertEqual([p['name'] for p in first['projects']], ['owner/p1', 'owner/p2', 'owner/p3'])
        self.assertEqual(other['projects'][0]['name'], 'owner/p0')
        self.assertFalse(first['cached'])
        self.assertTrue(concurrent['cached'])
        self.assertEqual(fetch.await_count, 1)
        self.assertFalse(await database.trending_was_delivered(1, NOW.date().isoformat()))
        await database.init_db()
        self.assertIsNotNone(await database.get_trending_edition(1, NOW.date().isoformat()))

    async def test_delivery_failure_retry_and_duplicate_protection(self):
        transport = AsyncMock()
        transport.send_message.side_effect = RuntimeError('send failed')
        with patch.object(trending, 'fetch_trending', AsyncMock(return_value=PROJECTS)):
            with self.assertRaises(RuntimeError):
                await bot.deliver_trending(transport, 1, scheduled=True)
            self.assertFalse(await database.trending_was_delivered(1, NOW.date().isoformat()))
            self.assertEqual(await database.get_trending_seen(1, '2026-10-01'), set())
            transport.send_message.side_effect = None
            await asyncio.gather(bot.deliver_trending(transport, 1, scheduled=True), bot.deliver_trending(transport, 1, scheduled=True))
            self.assertEqual(transport.send_message.await_count, 2)
            await bot.deliver_trending(transport, 1, scheduled=False)
            self.assertEqual(transport.send_message.await_count, 3)
        self.assertEqual(len(await database.get_trending_seen(1, '2026-10-01')), 3)

    async def test_subscriptions_and_schedule(self):
        await database.set_trending_subscription(1, True)
        await database.set_trending_subscription(1, True)
        await database.set_trending_subscription(2, True)
        await database.set_trending_subscription(2, False)
        self.assertEqual(await database.get_trending_subscribers(), [1])
        with patch.object(bot, 'deliver_trending', AsyncMock()) as deliver:
            with patch.object(trending, 'now_kst', return_value=NOW.replace(hour=8, minute=59)):
                await bot.send_trending_notifications(AsyncMock())
                deliver.assert_not_awaited()
            await bot.send_trending_notifications(AsyncMock())
            deliver.assert_awaited_once()

    async def test_blocked_bot_unsubscribes(self):
        from telegram.error import Forbidden
        await database.set_trending_subscription(1, True)
        with patch.object(bot, 'deliver_trending', AsyncMock(side_effect=Forbidden('blocked'))):
            await bot.send_trending_notifications(AsyncMock())
        self.assertEqual(await database.get_trending_subscribers(), [])

    async def test_message_utf16_limit(self):
        from bs4 import BeautifulSoup
        cards = [{**p, 'summary': '🔥' * 600, 'warnings': []} for p in PROJECTS[:3]]
        text = trending.format_digest({'collected_at': NOW.isoformat(), 'projects': cards})
        plain = BeautifulSoup(text, 'html.parser').get_text()
        self.assertLess(len(plain.encode('utf-16-le')) // 2, 4096)

    async def test_html_escape_and_missing_readme(self):
        with patch.object(trending, 'fetch_readme', AsyncMock(side_effect=ValueError('missing'))):
            card = await trending.summarize_project(PROJECTS[0])
        self.assertFalse(card['ai_used'])
        self.assertEqual(len(card['warnings']), 2)
        text = trending.format_digest({'collected_at': NOW.isoformat(), 'projects': [card]})
        self.assertIn('&lt;tool&gt;', text)
        self.assertNotIn('<tool>', text)

    async def test_no_result_not_cached_and_failure_not_swallowed(self):
        await database.mark_trending_delivered(1, NOW.date().isoformat(), [p['name'] for p in PROJECTS])
        with patch.object(trending, 'fetch_trending', AsyncMock(return_value=PROJECTS)):
            result = await trending.get_digest(1, NOW)
        self.assertEqual(result['projects'], [])
        self.assertIsNone(await database.get_trending_edition(1, NOW.date().isoformat()))
        await self.caches[0].clear()
        with patch.object(trending, 'fetch_trending', AsyncMock(side_effect=HTTPException(502, 'offline'))):
            with self.assertRaises(HTTPException):
                await trending.get_digest(2, NOW)

    async def test_gemini_reuse_and_failure_fallback(self):
        with patch.object(trending.config, 'GEMINI_API_KEY', 'test-only'), patch.object(trending, 'call_gemini', AsyncMock(return_value='소개: 테스트 프로젝트')) as ai:
            card = await trending.summarize_project(PROJECTS[0])
            self.assertTrue(card['ai_used'])
            self.assertIn('지시를 따르지', ai.call_args.kwargs['system_instruction'])
        with patch.object(trending.config, 'GEMINI_API_KEY', 'test-only'), patch.object(trending, 'call_gemini', AsyncMock(return_value='(AI 응답 생성 실패)')):
            card = await trending.summarize_project(PROJECTS[0])
            self.assertFalse(card['ai_used'])


class RouteTests(unittest.TestCase):
    def test_preview_does_not_send_telegram(self):
        app = FastAPI()
        app.include_router(router)
        result = {'day': '2026-10-15', 'projects': [], 'cached': True}
        with patch('routes.github.get_digest', AsyncMock(return_value=result)), patch.object(bot, 'deliver_trending', AsyncMock()) as send:
            response = TestClient(app).get('/github/trending')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['cached'])
        send.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
