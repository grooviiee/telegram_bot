"""분기 계산, 누락 표시, 텔레그램 이미지 응답을 검증합니다."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.quarterly_profit import build_profit_series, fetch_profit_period
from services.profit_chart import render_profit_chart
import bot


def period(year: int, quarter: int, revenue: int | None, income: int | None = 0,
           fs_div: str = 'CFS', cumulative: int | None = None) -> dict:
    """테스트용 단일 기간 데이터를 생성합니다."""
    return {'year': year, 'quarter': quarter, 'fs_div': fs_div,
            'revenue': revenue, 'operating_income': income,
            'revenue_cumulative': cumulative, 'operating_income_cumulative': 0}


class QuarterlyProfitTests(unittest.TestCase):
    def test_q4_subtracts_cumulative_and_preserves_zero(self):
        rows = build_profit_series([period(2024, 3, 40, cumulative=100), period(2024, 4, 160, 0)])
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[-1]['revenue'], 60)
        self.assertEqual(rows[-1]['operating_margin'], 0)

    def test_q4_missing_or_mixed_basis_is_not_annual(self):
        for preceding in ([], [period(2024, 3, 40, fs_div='OFS', cumulative=100)]):
            rows = build_profit_series(preceding + [period(2024, 4, 160)])
            self.assertIsNone(rows[-1]['revenue'])

    def test_yoy_and_missing_quarters(self):
        rows = build_profit_series([period(2023, 2, 100), period(2024, 2, 0)])
        self.assertEqual(rows[-1]['revenue_yoy'], -100)
        self.assertNotIn('revenue', rows[-2])
        rows = build_profit_series([period(2023, 2, 100, fs_div='OFS'), period(2024, 2, 150)])
        self.assertIsNone(rows[-1]['revenue_yoy'])

    def test_income_statement_not_equity_statement(self):
        accounts = [
            {'sj_div': 'IS', 'account_nm': '매출액', 'thstrm_amount': '50', 'thstrm_add_amount': '130'},
            {'sj_div': 'IS', 'account_nm': '영업이익', 'thstrm_amount': '-5', 'thstrm_add_amount': '10'},
            {'sj_div': 'SCE', 'account_nm': '영업이익', 'thstrm_amount': '999'},
        ]
        with patch('services.quarterly_profit._dart_get', return_value={'status': '000', 'list': accounts}):
            result = fetch_profit_period('test', 2025, 3)
        self.assertEqual(result['operating_income'], -5)
        self.assertEqual(result['revenue_cumulative'], 130)

    def test_png_with_negative_zero_and_missing(self):
        rows = build_profit_series([period(2024, 1, 100, -5), period(2024, 3, 120, 0)])
        with render_profit_chart('삼성전자', rows) as image:
            self.assertEqual(image.read(8), b'\x89PNG\r\n\x1a\n')


class ProfitBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_photo_instead_of_annual_table(self):
        rows = build_profit_series([period(2025, 1, 100, 0)])
        msg = AsyncMock()
        with patch.object(bot, '_get', AsyncMock(return_value=({'company_name': '삼성전자', 'financials': rows}, 200))) as get:
            await bot._send_profit_chart(msg, '삼성전자')
        get.assert_awaited_once_with('/profit-quarterly/삼성전자')
        msg.reply_photo.assert_awaited_once()
        msg.delete.assert_awaited_once()

    async def test_upstream_error_is_not_company_suggestion(self):
        msg = AsyncMock()
        with patch.object(bot, '_get', AsyncMock(return_value=({'detail': 'DART 조회 실패'}, 502))), patch.object(bot, '_show_suggestions', AsyncMock()) as suggest:
            await bot._send_profit_chart(msg, '삼성전자')
        suggest.assert_not_awaited()
        msg.reply_photo.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
