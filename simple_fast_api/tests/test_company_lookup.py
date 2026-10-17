"""기업명 검색과 밸류에이션의 종목코드 해석 일관성을 검증합니다."""
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from fastapi import HTTPException
from services import dart, valuation


class CompanyLookupTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring('''<result>
          <list><corp_name>LG전자</corp_name><corp_code>00401731</corp_code><stock_code>066570</stock_code></list>
          <list><corp_name>LG화학</corp_name><corp_code>00356361</corp_code><stock_code>051910</stock_code></list>
          <list><corp_name>비상장회사</corp_name><corp_code>99999999</corp_code><stock_code> </stock_code></list>
        </result>''')
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


if __name__ == '__main__':
    unittest.main()
