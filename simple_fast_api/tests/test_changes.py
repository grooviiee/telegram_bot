"""연속 연도 선택·본문 대응·근거 보존·모델 실패·텔레그램 변화를 검증합니다."""
import asyncio
import copy
import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from services import changes, report_retrieval as rag
from routes import ai
from config import TELEGRAM_COMMANDS, TELEGRAM_MSG_LIMIT
import bot


def report(year: int) -> dict:
    """회계연도와 공시일을 구별하는 보고서 메타데이터를 만듭니다."""
    return {'fiscal_year': year, 'fiscal_month': 12, 'receipt_no': f'{year + 1}0301000001',
            'report_name': f'사업보고서 ({year}.12)', 'filed_at': f'{year + 1}0301',
            'source': f'https://example.test/{year}', 'index_version': 6}


def documents() -> list[dict]:
    """공통 문장을 충분히 보존한 세 주제의 변경 본문을 만듭니다."""
    result = []
    for year in (2024, 2025):
        passages = []
        values = [
            ('1. 주요 제품 및 서비스', '당사는 국내외 고객을 대상으로 제품을 생산하고 판매하는 사업을 운영하고 있으며 주요 공급 제품은 ' +
             ('냉장고와 세탁기를 중심으로 구성되어 있습니다.' if year == 2024 else '냉장고와 공조 시스템을 중심으로 구성되어 있습니다.')),
            ('가. 연구개발활동', '회사는 핵심 기술의 경쟁력을 확보하기 위한 연구개발과 제품 혁신을 꾸준히 추진하고 있으며 앞으로 ' +
             ('가전제품의 에너지 효율을 높이는 기술 개발에 집중할 계획입니다.' if year == 2024 else '공조 시스템의 서비스 플랫폼을 개발하는 투자에 집중할 계획입니다.')),
            ('5. 위험관리', '회사는 해외 시장에서 발생할 수 있는 불확실성에 대응하기 위해 위험 관리 체계를 운영하고 있으며 특히 ' +
             ('환율 변동과 원재료 가격 상승에 따른 위험을 관리하고 있습니다.' if year == 2024 else '환율 변동과 공급망 불안에 따른 위험을 관리하고 있습니다.')),
        ]
        for i, (heading, body) in enumerate(values, 1):
            passages.append({'heading': heading, 'body': body, 'filename': 'report.xml', 'ordinal': i, 'kind': 'text'})
        result.append({'report': report(year), 'filename': 'report.xml', 'passages': passages})
    return result


def service_result() -> dict:
    """봇 표시 검증용 서비스 결과를 만듭니다."""
    docs = documents()
    result = {'company_name': '회사<&>', 'corp_code': '123', 'previous_year': 2024, 'current_year': 2025,
              'reports': [d['report'] for d in docs], 'ai_used': False, 'cached': False, 'warnings': ['서술 변경 후보입니다.']}
    result.update(changes.compare_documents(docs))
    for item in result['changes']:
        item['summary'] = '대응 본문의 표현 차이입니다.'
    return result


class CompareTests(unittest.TestCase):
    def test_matches_three_topics_with_unique_year_citations(self):
        result = changes.compare_documents(documents())
        self.assertEqual({c['topic'] for c in result['changes']}, {'products', 'strategy', 'risk'})
        evidence = [s for c in result['changes'] for s in c['evidence']]
        self.assertEqual([s['id'] for s in evidence], [f'R{i}' for i in range(1, 7)])
        self.assertEqual([s['fiscal_year'] for s in evidence], [2024, 2025] * 3)

    def test_unchanged_and_numeric_only_edits_are_excluded(self):
        docs = documents()
        docs[1]['passages'] = copy.deepcopy(docs[0]['passages'])
        for row in docs[0]['passages']:
            row['body'] += ' 2024년 매출액은 100억원입니다.'
        for row in docs[1]['passages']:
            row['body'] += ' 2025년 매출액은 200억원입니다.'
        self.assertEqual(changes.compare_documents(docs)['changes'], [])

    def test_unmatched_sections_do_not_become_new_or_discontinued_business(self):
        docs = documents()
        for row in docs[1]['passages']:
            row['heading'] = '전혀 다른 절 ' + row['heading']
        result = changes.compare_documents(docs)
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['coverage']['unmatched_sections'], 6)

    def test_section_number_changes_preserve_correspondence(self):
        docs = documents()
        docs[1]['passages'][0]['heading'] = '2. 주요 제품 및 서비스'
        self.assertIn('products', [c['topic'] for c in changes.compare_documents(docs)['changes']])

    def test_disjoint_contents_are_not_forced_into_pair(self):
        docs = documents()
        docs[1]['passages'][0]['body'] = '독립적인 통신장비 개발을 수행하면서 소프트웨어 솔루션 및 네트워크 보안 서비스를 구축하는 새로운 조직의 활동을 기록한 문서입니다.'
        self.assertNotIn('products', [c['topic'] for c in changes.compare_documents(docs)['changes']])

    def test_overlapping_chunks_are_restored_without_partial_word(self):
        text = '당사는 주요 제품을 생산하고 판매하면서 시장의 다양한 요구를 반영하기 위한 연구를 수행합니다. ' * 8
        rows = [{'heading': '주요 제품', 'filename': 'report.xml', 'ordinal': i + 1, 'kind': 'text', 'body': part}
                for i, part in enumerate(rag._split(text, 180))]
        groups, limited = changes._sentences({'passages': rows})
        sentences = next(iter(groups.values()))
        self.assertFalse(limited)
        self.assertTrue(all(r['body'].startswith('당사는') for r in sentences))
        self.assertTrue(any(r['ordinal_end'] >= r['ordinal'] for r in sentences))

    def test_long_sections_are_bounded_and_disclosed(self):
        docs = documents()
        with patch.object(changes, 'CHANGES_MAX_SECTION_SENTENCES', 0):
            result = changes.compare_documents(docs)
        self.assertGreater(result['coverage']['limited_sections'], 0)

    def test_very_long_unpunctuated_sentence_is_skipped_before_matching(self):
        docs = documents()
        docs[0]['passages'][0]['body'] = '주요제품을 개발하고 생산하며 공급하고 있습니다' * 1000
        result = changes.compare_documents(docs)
        self.assertGreater(result['coverage']['limited_sections'], 0)
        self.assertNotIn('products', [c['topic'] for c in result['changes']])

    def test_section_character_budget_discloses_partial_coverage(self):
        with patch.object(changes, 'CHANGES_MAX_SECTION_CHARS', 1):
            result = changes.compare_documents(documents())
        self.assertEqual(result['changes'], [])
        self.assertGreater(result['coverage']['limited_sections'], 0)

    def test_display_has_both_original_links_and_no_change_limit(self):
        result = service_result()
        text = '\n'.join(changes.format_change_blocks(result))
        self.assertIn('2024년 → 2025년', text)
        self.assertIn('https://example.test/2024', text)
        self.assertIn('https://example.test/2025', text)
        result['changes'] = []
        self.assertIn('실제 변화가 없다는 의미는 아닙니다', '\n'.join(changes.format_change_blocks(result)))

    def test_phrase_highlights_first_substantive_edit_instead_of_clipped_tail(self):
        before = '냉장고와 세탁기 및 에어컨 제품을 생산하고 판매하는 회사입니다. ' + '공통적인 설명을 계속하고 있습니다. ' * 4 + '과거의 긴 부가 설명입니다.'
        after = before.replace('에어컨', '청소기').replace('과거의 긴 부가 설명입니다.', '당기의 훨씬 길고 다른 내용의 부가적인 설명을 덧붙였습니다.')
        phrases = changes.changed_phrases([{'excerpt': before}, {'excerpt': after}])
        self.assertIn('에어컨', phrases['previous'])
        self.assertIn('청소기', phrases['current'])


class AnnualSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reports = [{**report(y), 'rcept_no': report(y)['receipt_no']} for y in (2025, 2024, 2023)]

    async def test_latest_corrected_report_and_previous_fiscal_year(self):
        manifest = SimpleNamespace(get_or_create=AsyncMock(return_value=({'reports': self.reports}, True)))
        def index(corp, item):
            return item, True
        @contextmanager
        def connection():
            def execute(sql, args):
                self.assertEqual(args[0], '123')
                return SimpleNamespace(fetchall=lambda: [{'heading': '제품', 'kind': 'text', 'body': '본문',
                    'filename': args[1] + '.xml', 'ordinal': 1}])
            yield SimpleNamespace(execute=execute)
        with patch.object(rag, 'rag_manifest_cache', manifest), patch.object(rag, '_index_report', side_effect=index), \
             patch.object(rag, '_connect', connection):
            docs = await rag.annual_comparison_documents('회사', '123')
        self.assertEqual([d['report']['fiscal_year'] for d in docs], [2024, 2025])

    async def test_missing_previous_year_never_uses_two_year_old_report(self):
        manifest = SimpleNamespace(get_or_create=AsyncMock(return_value=({'reports': self.reports[::2]}, True)))
        with patch.object(rag, 'rag_manifest_cache', manifest), patch.object(rag, '_index_report') as index:
            with self.assertRaises(HTTPException) as caught:
                await rag.annual_comparison_documents('회사', '123')
        self.assertEqual(caught.exception.status_code, 404)
        index.assert_not_called()

    async def test_different_fiscal_month_is_not_comparable(self):
        self.reports[1]['fiscal_month'] = 3
        manifest = SimpleNamespace(get_or_create=AsyncMock(return_value=({'reports': self.reports}, True)))
        with patch.object(rag, 'rag_manifest_cache', manifest):
            with self.assertRaises(HTTPException) as caught:
                await rag.annual_comparison_documents('회사', '123')
        self.assertEqual(caught.exception.status_code, 422)


class MemoryCache:
    def __init__(self):
        self.value = None
        self.mutex = asyncio.Lock()
    def lock(self, key):
        return self.mutex
    async def get(self, key):
        return self.value
    async def set(self, key, value):
        self.value = value


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = MemoryCache()
        self.docs = documents()
        self.addCleanup(patch.stopall)
        patch.object(changes, 'changes_cache', self.cache).start()
        patch.object(changes, 'annual_comparison_documents', AsyncMock(return_value=self.docs)).start()

    async def test_grounded_comparison_is_cached_without_any_model_call(self):
        with patch('utils.call_gemini', AsyncMock()) as model:
            first = await changes.annual_changes_data('회사', '123', '정식명')
            second = await changes.annual_changes_data('회사', '123', '정식명')
        self.assertFalse(first['ai_used'])
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(first['company_name'], '정식명')
        model.assert_not_awaited()
        for change in first['changes']:
            self.assertIn(change['phrases']['previous'], change['evidence'][0]['excerpt'])
            self.assertIn(change['phrases']['current'], change['evidence'][1]['excerpt'])

    async def test_new_correction_invalidates_cached_comparison(self):
        await changes.annual_changes_data('회사', '123', '회사')
        self.docs[1]['report']['receipt_no'] = '20260706000276'
        fresh = await changes.annual_changes_data('회사', '123', '회사')
        self.assertFalse(fresh['cached'])
        self.assertEqual(fresh['reports'][1]['receipt_no'], '20260706000276')

    async def test_different_corporation_does_not_reuse_same_name_cache(self):
        await changes.annual_changes_data('회사', '123', '회사')
        fresh = await changes.annual_changes_data('회사', '456', '회사')
        self.assertFalse(fresh['cached'])
        self.assertEqual(fresh['corp_code'], '456')

    async def test_unavailable_report_is_not_replaced_by_cached_old_comparison(self):
        await changes.annual_changes_data('회사', '123', '회사')
        with patch.object(changes, 'annual_comparison_documents', AsyncMock(side_effect=HTTPException(404, '보고서 없음'))):
            with self.assertRaises(HTTPException) as caught:
                await changes.annual_changes_data('회사', '123', '회사')
        self.assertEqual(caught.exception.status_code, 404)

    async def test_no_changes_does_not_claim_no_actual_changes(self):
        self.docs[1]['passages'] = copy.deepcopy(self.docs[0]['passages'])
        result = await changes.annual_changes_data('회사', '123', '회사')
        self.assertEqual(result['changes'], [])
        self.assertIn('실제 변화가 없다는 의미는 아닙니다', '\n'.join(changes.format_change_blocks(result)))

    async def test_route_uses_selected_identity_and_preserves_raw_cache_key(self):
        with patch.object(ai, 'get_company_info', return_value={'company_name': '신성이엔지', 'corp_code': '00136271'}), \
             patch.object(ai, 'annual_changes_data', AsyncMock(return_value={'cached': False})) as service:
            response = await ai.get_annual_changes('011930')
        self.assertEqual(response.status_code, 200)
        service.assert_awaited_once_with('011930', '00136271', '신성이엔지')


class BotTests(unittest.IsolatedAsyncioTestCase):
    def context(self, args):
        return SimpleNamespace(args=args, user_data={}, application=SimpleNamespace(
            create_task=lambda coroutine, **kwargs: asyncio.create_task(coroutine)))

    async def test_command_help_and_registration(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        await bot.cmd_changes(update, self.context([]))
        self.assertIn('/changes', update.message.reply_text.call_args.args[0])
        self.assertIn('changes', dict(TELEGRAM_COMMANDS))

    async def test_background_delivery_escapes_sources_and_uses_long_sender(self):
        pending = SimpleNamespace(delete=AsyncMock())
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock(return_value=pending)))
        context = self.context(['회사<&>'])
        with patch.object(bot, '_get', AsyncMock(return_value=(service_result(), 200))) as get, \
             patch.object(bot, '_send_long', AsyncMock()) as send:
            await bot.cmd_changes(update, context)
            job = context.user_data['changes_task']
            await job
        self.assertIn('/changes/회사<&>', get.call_args.args[0])
        self.assertIn('회사&lt;&amp;&gt;', send.call_args_list[0].args[1])
        self.assertTrue(all(len(c.args[1]) <= TELEGRAM_MSG_LIMIT for c in send.call_args_list))
        self.assertNotIn('changes_task', context.user_data)

    async def test_missing_data_preserves_search_fallback(self):
        pending = SimpleNamespace(delete=AsyncMock())
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock(return_value=pending)))
        context = self.context(['회사'])
        with patch.object(bot, '_get', AsyncMock(return_value=({'detail': '직전연도 없음'}, 404))), \
             patch.object(bot, '_show_suggestions', AsyncMock()) as suggest:
            await bot.cmd_changes(update, context)
            await context.user_data['changes_task']
        suggest.assert_awaited_once_with(pending, '회사', 'changes', {'detail': '직전연도 없음'}, 404)

    async def test_duplicate_running_job_does_not_launch_another(self):
        context = self.context(['회사'])
        context.user_data['changes_task'] = asyncio.get_running_loop().create_future()
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        with patch.object(bot, '_get', AsyncMock()) as get:
            await bot.cmd_changes(update, context)
        get.assert_not_awaited()
        self.assertIn('앞선', update.message.reply_text.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
