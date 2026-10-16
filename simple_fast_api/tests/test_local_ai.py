"""로컬 AI의 추론 노출 방지와 제공자 전환을 검증합니다."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from services import local_ai
import utils
from services import chat


class LocalAnswerTests(unittest.TestCase):
    def test_local_context_preserves_financial_years(self):
        financials = [{'year': year, 'revenue': 100_000_000, 'operating_income': 10_000_000,
                       'net_income': 5_000_000} for year in range(2021, 2026)]
        with patch.object(chat, 'AI_PROVIDER', 'ollama'):
            context = chat.build_system_context('테스트', [], financials, [], None, [], buffett_mode=True)
        for row in financials:
            self.assertIn(str(row['year']), context)
        self.assertIn('DART', context)
        self.assertLess(len(context), 1000)

    def test_reasoning_removed(self):
        self.assertEqual(local_ai.extract_answer({'content': 'private reasoning</think>최종 답변'}, 'stop'), '최종 답변')

    def test_incomplete_rejected(self):
        for content, reason in [('미완성', 'length'), ('<think>계산 중', 'stop'), ('', 'stop')]:
            self.assertEqual(local_ai.extract_answer({'content': content}, reason), local_ai.FAILURE)

    def test_context_bounded_and_disclosed(self):
        messages, clipped = local_ai.prepare_messages('질문' * 5000, '자료' * 10000, None)
        self.assertTrue(clipped)
        self.assertLessEqual(sum(len(m['content']) for m in messages), local_ai.OLLAMA_MAX_INPUT_CHARS + 1)

    def test_small_clip_is_bounded(self):
        self.assertLessEqual(len(local_ai._clip('a' * 100, 10)), 10)

    def test_remote_endpoint_rejected(self):
        with patch.object(local_ai, 'OLLAMA_BASE_URL', 'https://example.com'):
            with self.assertRaises(ValueError):
                local_ai._validate_local_endpoint()

    def test_cloud_model_rejected(self):
        with patch.object(local_ai, 'OLLAMA_MODEL', 'model:cloud'):
            with self.assertRaises(ValueError):
                local_ai._validate_local_endpoint()


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_round_trip_with_long_context(self):
        responses = [
            {'done': True, 'done_reason': 'stop', 'message': {'role': 'assistant', 'content': '',
                'tool_calls': [{'function': {'name': 'lookup', 'arguments': {}}}]}},
            {'done': True, 'done_reason': 'stop', 'message': {'content': '확인한 답변'}},
        ]
        contexts = []
        for data in responses:
            response = MagicMock(status=200)
            response.json = AsyncMock(return_value=data)
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=response)
            context.__aexit__ = AsyncMock(return_value=False)
            contexts.append(context)
        session = MagicMock()
        session.post.side_effect = contexts
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=session)
        client.__aexit__ = AsyncMock(return_value=False)
        executor = AsyncMock(return_value={'revenue': 100})
        with patch.object(local_ai.aiohttp, 'ClientSession', return_value=client), patch.object(local_ai, '_inference_slot', asyncio.Semaphore(1)):
            answer = await local_ai.call_ollama('질문', system_instruction='자료' * 4000,
                tools=[{'name': 'lookup', 'description': '자료 조회', 'parameters': {'type': 'object'}}],
                tool_executor=executor)
        self.assertTrue(answer.endswith('확인한 답변'))
        executor.assert_awaited_once_with('lookup', {})
        self.assertEqual(session.post.call_count, 2)

    async def test_groq_dispatches_locally(self):
        with patch.object(utils, 'AI_PROVIDER', 'ollama'), patch.object(local_ai, 'call_ollama', new_callable=AsyncMock, return_value='{}') as call:
            self.assertEqual(await utils.call_groq('질문'), '{}')
            self.assertIn('JSON', call.call_args.kwargs['system_instruction'])

    async def test_wrapper_dispatches_locally(self):
        with patch.object(utils, 'AI_PROVIDER', 'ollama'), patch.object(local_ai, 'call_ollama', new_callable=AsyncMock, return_value='로컬 답변') as call:
            self.assertEqual(await utils.call_gemini('질문'), '로컬 답변')
            call.assert_awaited_once()

    async def test_invalid_endpoint_fails_without_network(self):
        with patch.object(local_ai, 'OLLAMA_BASE_URL', 'http://remote.invalid'), patch.object(local_ai.aiohttp, 'ClientSession') as session:
            self.assertEqual(await local_ai.call_ollama('질문'), local_ai.FAILURE)
            session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
