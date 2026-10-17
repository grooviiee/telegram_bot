"""응답 재사용의 근거·대화 격리와 중복 추론·준비·상담 취소를 검증합니다."""
import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from services import report_retrieval as rag, local_ai
from tests.test_report_retrieval import result, MemoryAnswerCache


class AnswerReuseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = MemoryAnswerCache()
        self.data = result()
        self.addCleanup(patch.stopall)
        patch.object(rag, 'rag_answer_cache', self.cache).start()
        async def retrieve(company, corp, message, history):
            data = copy.deepcopy(self.data)
            data['search_query'] = rag.expand_followup_query(message, history)
            return data
        patch.object(rag, 'retrieve_report_evidence', side_effect=retrieve).start()
        self.model = patch.object(rag, 'call_gemini', AsyncMock(return_value='냉장고를 제조하며 원재료 위험이 있습니다. [R1]')).start()

    async def answer(self, message='사업과 위험', history=None, corp='123'):
        return await rag.answer_from_report('회사', corp, message, history or [])

    async def test_repeated_answer_and_evidence_are_identical_without_new_inference(self):
        first = await self.answer()
        second = await self.answer()
        self.assertFalse(first['answer_cached'])
        self.assertTrue(second['answer_cached'])
        self.assertEqual(first['answer'], second['answer'])
        self.assertEqual(first['evidence'], second['evidence'])
        self.assertEqual(self.model.await_count, 1)

    async def test_different_question_or_history_or_corporation_is_not_reused(self):
        await self.answer()
        for kwargs in [{'message': '제품을 자세히 설명해줘'}, {'history': [{'role': 'user', 'text': 'MS 사업부는?'}]}, {'corp': '456'}]:
            self.assertFalse((await self.answer(**kwargs))['answer_cached'])
        self.assertEqual(self.model.await_count, 4)

    async def test_revised_receipt_or_evidence_requires_fresh_answer(self):
        await self.answer()
        self.data['report']['receipt_no'] = '20260706000276'
        self.assertFalse((await self.answer())['answer_cached'])
        self.data['evidence'][0]['body'] += ' 새로운 사업 설명입니다.'
        self.assertFalse((await self.answer())['answer_cached'])
        self.assertEqual(self.model.await_count, 3)

    async def test_model_prompt_or_generation_change_invalidates_answer(self):
        await self.answer()
        with patch.object(rag, 'OLLAMA_MODEL', 'different-local-model'), patch.object(rag, 'AI_PROVIDER', 'ollama'):
            self.assertFalse((await self.answer())['answer_cached'])
        with patch.object(rag, 'RAG_OUTPUT_TOKENS', rag.RAG_OUTPUT_TOKENS + 1):
            self.assertFalse((await self.answer())['answer_cached'])
        self.assertEqual(self.model.await_count, 3)

    async def test_cached_text_is_validated_again_before_reuse(self):
        await self.answer()
        key = next(iter(self.cache.values['회사']['entries']))
        self.cache.values['회사']['entries'][key] = '매출은 999억원입니다. [R1]'
        answer = await self.answer()
        self.assertFalse(answer['answer_cached'])
        self.assertNotIn('999', answer['answer'])
        self.assertEqual(self.model.await_count, 2)

    async def test_failed_or_unsupported_answer_is_not_saved(self):
        self.model.return_value = '매출은 999억원입니다. [R1]'
        for _ in range(2):
            answer = await self.answer()
            self.assertFalse(answer['ai_used'])
            self.assertFalse(answer['answer_cached'])
        self.assertEqual(self.model.await_count, 4)
        self.assertEqual(self.cache.values, {})

    async def test_concurrent_identical_requests_share_one_generation(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def generate(*args, **kwargs):
            started.set()
            await release.wait()
            return '냉장고를 제조합니다. [R1]'
        self.model.side_effect = generate
        first = asyncio.create_task(self.answer())
        await started.wait()
        second = asyncio.create_task(self.answer())
        await asyncio.sleep(0)
        release.set()
        answers = await asyncio.gather(first, second)
        self.assertEqual(self.model.await_count, 1)
        self.assertEqual(answers[0]['answer'], answers[1]['answer'])
        self.assertTrue(any(a['response_shared'] for a in answers))

    async def test_cancelled_waiter_does_not_cancel_shared_generation(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def generate(*args, **kwargs):
            started.set()
            await release.wait()
            return '냉장고를 제조합니다. [R1]'
        self.model.side_effect = generate
        first = asyncio.create_task(self.answer())
        await started.wait()
        second = asyncio.create_task(self.answer())
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertTrue((await second)['ai_used'])
        self.assertEqual(self.model.await_count, 1)
        self.assertTrue((await self.answer())['answer_cached'])

    async def test_company_variant_count_is_bounded(self):
        with patch.object(rag, 'RAG_ANSWER_VARIANTS_PER_COMPANY', 2):
            for query in ('첫 질문', '다른 질문', '새 질문'):
                await self.answer(query)
        self.assertEqual(len(self.cache.values['회사']['entries']), 2)

    async def test_concurrent_different_questions_do_not_overwrite_variants(self):
        await asyncio.gather(self.answer('제품 설명'), self.answer('위험 설명'))
        self.assertEqual(self.model.await_count, 2)
        self.assertEqual(len(self.cache.values['회사']['entries']), 2)


class SearchReuseTests(unittest.TestCase):
    def test_revision_and_receipt_are_part_of_search_identity(self):
        rag._cached_search.cache_clear()
        self.addCleanup(rag._cached_search.cache_clear)
        with patch.object(rag, '_search', return_value=[{'body': '원문'}]) as search:
            first = rag._cached_search('123', 'receipt', '제품', 'revision1')
            self.assertEqual(first, rag._cached_search('123', 'receipt', '제품', 'revision1'))
            self.assertEqual(search.call_count, 1)
            rag._cached_search('123', 'receipt', '제품', 'revision2')
            rag._cached_search('123', 'new-receipt', '제품', 'revision2')
            self.assertEqual(search.call_count, 3)


class PreloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await local_ai.close_preload()

    async def test_concurrent_preload_requests_are_merged(self):
        release = asyncio.Event()
        async def prepare():
            await release.wait()
            return True
        with patch.object(local_ai, '_preload_model', AsyncMock(side_effect=prepare)) as model:
            tasks = [asyncio.create_task(local_ai.preload_ollama()) for _ in range(3)]
            await asyncio.sleep(0)
            release.set()
            self.assertEqual(await asyncio.gather(*tasks), [True] * 3)
        self.assertEqual(model.await_count, 1)

    def client(self, loaded=False):
        state = MagicMock()
        state.json = AsyncMock(return_value={'models': [{'name': local_ai.OLLAMA_MODEL}] if loaded else []})
        ready = MagicMock()
        ready.json = AsyncMock(return_value={'done': True})
        def context(response):
            manager = MagicMock()
            manager.__aenter__ = AsyncMock(return_value=response)
            manager.__aexit__ = AsyncMock(return_value=False)
            return manager
        session = MagicMock()
        session.get.return_value = context(state)
        session.post.return_value = context(ready)
        client = context(session)
        return client, session

    async def test_preload_only_loads_model_without_generating_answer(self):
        client, session = self.client()
        with patch.object(local_ai.aiohttp, 'ClientSession', return_value=client), patch.object(local_ai, '_inference_slot', asyncio.Semaphore(1)):
            self.assertTrue(await local_ai.preload_ollama())
        payload = session.post.call_args.kwargs['json']
        self.assertNotIn('prompt', payload)
        self.assertEqual(payload['options']['num_ctx'], local_ai.OLLAMA_NUM_CTX)
        self.assertEqual(payload['model'], local_ai.OLLAMA_MODEL)

    async def test_loaded_model_is_not_reloaded(self):
        client, session = self.client(loaded=True)
        with patch.object(local_ai.aiohttp, 'ClientSession', return_value=client), patch.object(local_ai, '_inference_slot', asyncio.Semaphore(1)):
            self.assertTrue(await local_ai.preload_ollama())
        session.post.assert_not_called()


class ChatResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    def context(self):
        return SimpleNamespace(user_data={'chat_company': '회사', 'chat_company_query': '011930', 'chat_history': []},
            application=SimpleNamespace(create_task=lambda coroutine, **kwargs: asyncio.create_task(coroutine)))

    def update(self, text='질문'):
        pending = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        return SimpleNamespace(message=SimpleNamespace(text=text, reply_text=AsyncMock(return_value=pending)))

    async def test_handler_returns_before_slow_answer_and_preserves_history(self):
        context, update = self.context(), self.update()
        release = asyncio.Event()
        async def post(*args, **kwargs):
            await release.wait()
            return {'answer': '근거 답변'}, 200
        with patch.object(bot, '_post', AsyncMock(side_effect=post)), patch.object(bot, '_send_long', AsyncMock()):
            self.assertEqual(await bot.handle_chat_message(update, context), bot.CHAT_ACTIVE)
            task = context.user_data['chat_task']
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            self.assertEqual(context.user_data['chat_history'], [])
            release.set()
            await task
        self.assertEqual([m['role'] for m in context.user_data['chat_history']], ['user', 'model'])
        self.assertNotIn('chat_task', context.user_data)

    async def test_duplicate_messages_do_not_race_conversation_history(self):
        context, update = self.context(), self.update()
        release = asyncio.Event()
        async def post(*args, **kwargs):
            await release.wait()
            return {'answer': '답변'}, 200
        with patch.object(bot, '_post', AsyncMock(side_effect=post)) as api, patch.object(bot, '_send_long', AsyncMock()):
            await bot.handle_chat_message(update, context)
            task = context.user_data['chat_task']
            await asyncio.sleep(0)
            await bot.handle_chat_message(update, context)
            self.assertEqual(api.await_count, 1)
            release.set()
            await task
        self.assertEqual(len(context.user_data['chat_history']), 2)

    async def test_end_cancels_wait_without_late_answer_or_history(self):
        context, update = self.context(), self.update()
        release = asyncio.Event()
        async def post(*args, **kwargs):
            await release.wait()
            return {'answer': '늦은 답변'}, 200
        with patch.object(bot, '_post', AsyncMock(side_effect=post)), patch.object(bot, '_send_long', AsyncMock()) as send:
            await bot.handle_chat_message(update, context)
            await asyncio.sleep(0)
            await bot.cmd_chat_end(update, context)
        send.assert_not_awaited()
        self.assertNotIn('chat_history', context.user_data)
        self.assertNotIn('chat_task', context.user_data)

    async def test_other_user_can_receive_answer_while_first_is_waiting(self):
        first, second = self.context(), self.context()
        release = asyncio.Event()
        async def post(path, payload):
            if payload['message'] == '느린 질문':
                await release.wait()
            return {'answer': '답변'}, 200
        with patch.object(bot, '_post', AsyncMock(side_effect=post)), patch.object(bot, '_send_long', AsyncMock()):
            await bot.handle_chat_message(self.update('느린 질문'), first)
            first_task = first.user_data['chat_task']
            await bot.handle_chat_message(self.update('빠른 질문'), second)
            await second.user_data['chat_task']
            self.assertFalse(first_task.done())
            release.set()
            await first_task


if __name__ == '__main__':
    unittest.main()
