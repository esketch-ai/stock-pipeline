import unittest

from editorial import stock_brief, overlap
from script_long import build_final_prompt, build_section_prompt


class EditorialTest(unittest.TestCase):
    def test_brief_changes_with_market_evidence(self):
        high = stock_brief({'name': '가', 'change_raw': 15, 'range_pos': '95%'}, '거래량 2배')
        low = stock_brief({'name': '나', 'change_raw': -3, 'range_pos': '10%'}, '거래량 1배')
        self.assertIn('고가권', high)
        self.assertIn('저가권', low)
        self.assertIn('당일 하락', low)
        self.assertNotIn('고가권', low)

    def test_name_and_number_swaps_do_not_evade_duplicate_check(self):
        a = '금호전기는 3000원에 마감했지만 거래량이 줄어 움직임의 지속성을 확인해야 합니다.'
        b = '천일고속은 9000원에 마감했지만 거래량이 줄어 움직임의 지속성을 확인해야 합니다.'
        self.assertGreaterEqual(overlap(a, b, ['금호전기', '천일고속']), 0.30)

    def test_disclaimer_is_not_duplicate_content(self):
        notice = '이 영상은 투자 권유가 아니며 투자 판단과 책임은 본인에게 있습니다.'
        self.assertEqual(overlap(notice, notice, []), 0)

    def test_prompts_preserve_actual_draft_and_brief(self):
        self.assertIn('원본초안', build_final_prompt('원본초안', '금호전기', '001210', '편집관점'))
        self.assertIn('편집관점', build_section_prompt('hook', '오프닝', 180, '팩트', '이유', '금호전기', '001210', editorial_brief='편집관점'))


if __name__ == '__main__':
    unittest.main()
