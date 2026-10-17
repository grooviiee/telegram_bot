"""기업명 검색과 밸류에이션의 종목코드 해석 일관성을 검증합니다."""
import unittest
import asyncio
import io
import os
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
import requests
import xml.etree.ElementTree as ET
from unittest.mock import patch, AsyncMock

from fastapi import HTTPException
from services import dart, valuation
from routes import data
import bot


class CompanyLookupTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring('''<result>
          <list><corp_name>LG전자</corp_name><corp_code>00401731</corp_code><stock_code>066570</stock_code></list>
          <list><corp_name>LG화학</corp_name><corp_code>00356361</corp_code><stock_code>051910</stock_code></list>
          <list><corp_name>비상장회사</corp_name><corp_code>99999999</corp_code><stock_code> </stock_code></list>
        </result>''')
        dart._company_profile.cache_clear()
        dart._company_records.cache_clear()
        self.addCleanup(dart._company_profile.cache_clear)
        self.addCleanup(dart._company_records.cache_clear)
        self.addCleanup(patch.stopall)
        patch.object(dart, '_load_corp_xml_root', return_value=self.root).start()
        patch.object(valuation, '_load_corp_xml_root', return_value=self.root).start()

    def test_stock_lookup_accepts_company_search_case_variants(self):
        for query in ['LG전자', 'lg전자', 'Lg전자', 'lG전자', '전자']:
            with self.subTest(query=query):
                self.assertEqual(dart.get_corp_code(query), '00401731')
                self.assertEqual(valuation.get_stock_code(query), '066570')

    def test_ambiguous_partial_not_selected(self):
        self.assertIsNone(valuation.get_stock_code('LG'))

    def test_unknown_company_returns_none(self):
        self.assertIsNone(valuation.get_stock_code('없는회사'))

    def test_unlisted_company_has_no_stock_code(self):
        self.assertIsNone(valuation.get_stock_code('비상장회사'))

    def test_source_error_is_not_misreported_as_no_match(self):
        with patch.object(valuation, 'get_corp_code', side_effect=HTTPException(500, '원본 오류')):
            with self.assertRaises(HTTPException) as caught:
                valuation.get_stock_code('LG전자')
        self.assertEqual(caught.exception.status_code, 500)

    def duplicates(self, decorated: bool = False) -> None:
        for name, code, stock in [('(주)신성이엔지' if decorated else '신성이엔지', '00686068', '104110'),
                                  ('신성이엔지', '00136271', '011930')]:
            item = ET.SubElement(self.root, 'list')
            for tag, text in [('corp_name', name), ('corp_code', code), ('stock_code', stock)]:
                ET.SubElement(item, tag).text = text

    def test_duplicate_historical_listed_ticker_does_not_win(self):
        self.duplicates()
        def profile(url, params):
            return {'status': '000', 'corp_cls': 'Y' if params['corp_code'] == '00136271' else 'E',
                    'stock_code': '011930' if params['corp_code'] == '00136271' else '104110'}
        with patch.object(dart, '_dart_get', side_effect=profile) as api:
            for name in ['신성이엔지', '신성 이엔지', '주식회사 신성이엔지', '㈜신성이엔지']:
                self.assertEqual(dart.get_corp_code(name), '00136271')
                self.assertEqual(valuation.get_stock_code(name), '011930')
            self.assertEqual(api.call_count, 2)
            self.root[:] = list(reversed(list(self.root)))
            self.assertEqual(dart.get_corp_code('신성이엔지'), '00136271')

    def test_legal_marker_on_historical_record_still_checks_all_names(self):
        self.duplicates(decorated=True)
        with patch.object(dart, '_dart_get', side_effect=lambda url, p: {
                'status': '000', 'corp_cls': 'Y' if p['corp_code'] == '00136271' else 'E'}):
            self.assertEqual(dart.get_corp_code('(주)신성이엔지'), '00136271')

    def test_two_current_or_no_current_companies_require_selection(self):
        self.duplicates()
        for market in ['Y', 'E']:
            dart._company_profile.cache_clear()
            with patch.object(dart, '_dart_get', return_value={'status': '000', 'corp_cls': market}):
                with self.assertRaises(HTTPException) as caught:
                    dart.get_corp_code('신성이엔지')
                self.assertEqual(caught.exception.status_code, 404)
                self.assertIn('011930', caught.exception.detail)
                self.assertIn('104110', caught.exception.detail)

    def test_profile_outage_is_not_no_match_or_first_match(self):
        self.duplicates()
        for response in [requests.ConnectionError('secret url'), {'status': '020'}]:
            with patch.object(dart, '_dart_get', side_effect=response if isinstance(response, Exception) else None,
                              return_value=response):
                with self.assertRaises(HTTPException) as caught:
                    dart.get_corp_code('신성이엔지')
                self.assertEqual(caught.exception.status_code, 503)
                self.assertNotIn('secret', caught.exception.detail)

    def test_normalized_names_and_explicit_stock_codes(self):
        for query in [' LG 전자 ', '주식회사 LG전자', '(주)LG전자', '㈜LG전자', 'LG전자(주)', 'ＬＧ전자', 'LG\u200b전자', '066570']:
            with self.subTest(query=query):
                self.assertEqual(dart.get_company_info(query)['company_name'], 'LG전자')
                self.assertEqual(valuation.get_stock_code(query), '066570')
        for query in ['', ' ', '(주)', '123456']:
            with self.assertRaises(HTTPException) as caught:
                dart.get_corp_code(query)
            self.assertEqual(caught.exception.status_code, 404)

    def test_explicit_old_ticker_remains_explicit_choice(self):
        self.duplicates()
        with patch.object(dart, '_dart_get') as api:
            self.assertEqual(dart.get_corp_code('011930'), '00136271')
            self.assertEqual(dart.get_corp_code('104110'), '00686068')
            api.assert_not_called()

    def test_suggestions_normalize_spaces_and_keep_ambiguity(self):
        self.assertIn('LG전자', dart.search_similar_companies('l g'))
        with self.assertRaises(HTTPException):
            dart.get_corp_code('l g')
        self.assertEqual(dart.search_similar_companies(' '), [])

    def test_punctuation_is_not_erased_from_real_names(self):
        self.assertNotEqual(dart._normalize_company_name('A+B'), dart._normalize_company_name('AB'))


class DirectoryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'corpCode.xml'
        self.old = b'<result><list><corp_name>Old</corp_name><corp_code>1</corp_code></list></result>'
        self.new = self.old.replace(b'Old', b'New')
        self.path.write_bytes(self.old)
        self.addCleanup(patch.stopall)
        patch.object(dart, 'REPORTS_DIR', self.folder.name).start()
        patch.object(dart, '_corp_directory_retry_at', 0.0).start()
        patch.object(dart, '_corp_directory_root', None).start()
        patch.object(dart, '_corp_directory_stamp', None).start()

    def archive(self, content: bytes, filename: str = 'CORPCODE.xml') -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr(filename, content)
        return buffer.getvalue()

    def test_fresh_directory_does_not_download(self):
        with patch.object(dart, '_dart_get_raw') as api:
            self.assertEqual(dart._load_corp_xml_root().findtext('./list/corp_name'), 'Old')
        api.assert_not_called()

    def test_parsed_directory_is_reused_until_file_changes(self):
        with patch.object(dart.ET, 'parse', wraps=ET.parse) as parse:
            old_root = dart._load_corp_xml_root()
            self.assertIs(dart._load_corp_xml_root(), old_root)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(dart._company_records(old_root)[0]['company_name'], 'Old')
            self.path.write_bytes(self.new)
            now = time.time() + 1
            os.utime(self.path, (now, now))
            new_root = dart._load_corp_xml_root()
            self.assertIsNot(new_root, old_root)
            self.assertEqual(dart._company_records(new_root)[0]['company_name'], 'New')
            self.assertEqual(parse.call_count, 2)

    def test_expired_directory_is_refreshed_atomically(self):
        os.utime(self.path, (0, 0))
        with patch.object(dart, '_dart_get_raw', return_value=self.archive(self.new)) as api:
            self.assertEqual(dart._load_corp_xml_root().findtext('./list/corp_name'), 'New')
            dart._load_corp_xml_root()
        self.assertEqual(api.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.new)

    def test_failed_refresh_preserves_previous_directory_and_backs_off(self):
        os.utime(self.path, (0, 0))
        with patch.object(dart, '_dart_get_raw', side_effect=requests.ConnectionError('secret')) as api:
            for _ in range(2):
                self.assertEqual(dart._load_corp_xml_root().findtext('./list/corp_name'), 'Old')
        self.assertEqual(api.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.old)

    def test_bad_zip_cannot_overwrite_existing_directory_or_extract_paths(self):
        os.utime(self.path, (0, 0))
        for archive in [b'not zip', self.archive(b'bad xml'), self.archive(self.new, '../CORPCODE.xml')]:
            with patch.object(dart, '_corp_directory_retry_at', 0.0), patch.object(dart, '_dart_get_raw', return_value=archive):
                self.assertEqual(dart._load_corp_xml_root().findtext('./list/corp_name'), 'Old')
            self.assertEqual(self.path.read_bytes(), self.old)
        self.assertEqual([p.name for p in Path(self.folder.name).iterdir()], ['corpCode.xml'])

    def test_missing_directory_and_outage_returns_503_without_secret(self):
        self.path.unlink()
        with patch.object(dart, '_dart_get_raw', side_effect=requests.ConnectionError('secret')):
            with self.assertRaises(HTTPException) as caught:
                dart._load_corp_xml_root()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('secret', caught.exception.detail)


class CompanyBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(bot, 'AI_PROVIDER', 'gemini').start()
    async def test_identity_endpoint_does_not_require_financials(self):
        company = {'company_name': '신성이엔지', 'corp_code': '00136271', 'stock_code': '011930'}
        with patch.object(data, 'get_company_info', return_value=company):
            response = await data.resolve_company('신성 이엔지')
        self.assertIn('011930', response.body.decode())

    async def test_chat_starts_using_identity_only_and_canonical_name(self):
        message = SimpleNamespace(reply_text=AsyncMock(return_value=SimpleNamespace(edit_text=AsyncMock())))
        context = SimpleNamespace(args=['011930'], user_data={})
        with patch.object(bot, '_get', AsyncMock(return_value=({'company_name': '신성이엔지', 'stock_code': '011930'}, 200))) as api:
            result = await bot.cmd_chat_start(SimpleNamespace(message=message), context)
        self.assertEqual(result, bot.CHAT_ACTIVE)
        self.assertEqual(context.user_data['chat_company'], '신성이엔지')
        self.assertEqual(context.user_data['chat_company_query'], '011930')
        api.assert_awaited_once_with('/companies/resolve/011930')

    async def test_chat_preserves_explicit_old_ticker_after_start(self):
        pending = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=pending), text='사업 내용을 설명해줘')
        context = SimpleNamespace(args=['104110'], user_data={})
        context.application = SimpleNamespace(create_task=lambda coro, **kwargs: asyncio.create_task(coro))
        update = SimpleNamespace(message=message)
        with (patch.object(bot, '_get', AsyncMock(return_value=({'company_name': '신성이엔지', 'stock_code': '104110'}, 200))),
              patch.object(bot, '_post', AsyncMock(return_value=({'answer': '해당 법인 근거'}, 200))) as post,
              patch.object(bot, '_send_long', AsyncMock())):
            await bot.cmd_chat_start(update, context)
            await bot.handle_chat_message(update, context)
            await context.user_data['chat_task']
        self.assertEqual(post.call_args.args[0], '/chat/104110')
        await bot.cmd_chat_end(update, context)
        self.assertNotIn('chat_company_query', context.user_data)

    async def test_known_company_missing_data_is_not_name_failure(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        with patch.object(bot, '_get', AsyncMock(return_value=({'company_name': '신성이엔지'}, 200))):
            await bot._show_suggestions(message, '신성이엔지', 'analysis', {'detail': '재무 자료 없음'}, 404)
        text = message.edit_text.call_args.args[0]
        self.assertIn('기업은 확인', text)
        self.assertNotIn('기업을 찾을 수 없습니다', text)

    async def test_upstream_failure_is_not_name_failure(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        with patch.object(bot, '_get', AsyncMock()) as api:
            await bot._show_suggestions(message, '신성이엔지', 'analysis', {'detail': 'DART 일시 장애'}, 503)
        api.assert_not_awaited()
        self.assertIn('DART 일시 장애', message.edit_text.call_args.args[0])

    async def test_ambiguous_company_keeps_stock_code_guidance(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        detail = '동명 기업입니다. 011930, 104110 종목코드로 선택해주세요.'
        with patch.object(bot, '_get', AsyncMock(return_value=({'detail': detail}, 404))), \
             patch.object(dart, 'search_similar_companies', return_value=[]):
            await bot._show_suggestions(message, '신성이엔지', 'analysis')
        self.assertIn('011930', message.edit_text.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
