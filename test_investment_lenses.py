import unittest
from unittest.mock import AsyncMock

import investment_lenses as lenses
import script_long


class AllocationTest(unittest.TestCase):
    def test_missing_business_and_disclosures_are_not_fabricated(self):
        reserved = []
        for i in range(15):
            lenses.allocate({'ticker': str(i), 'name': str(i)}, reserved)
        self.assertEqual({p['lens_id'] for p in reserved}, {'business_value', 'expectations', 'risk_budget', 'quant_validation', 'downside'})
        self.assertEqual(len({(p['lens_id'], p['structure_id']) for p in reserved}), 15)

    def test_business_and_verified_events_enable_other_lenses(self):
        reserved = []
        facts = {'business': '출처 있는 사업 자료', 'verified_corporate_events': ['검증 공시']}
        for _ in range(5):
            lenses.allocate(facts, reserved)
        self.assertEqual(len({p['lens_id'] for p in reserved}), 5)

    def test_character_uses_selected_plan_not_arbitrary_person(self):
        plan = {'investor': '짐 사이먼스', 'principle': '검증', 'outline': {'question': '기간이 달라도 같은가?'}}
        self.assertEqual(lenses.character_insight(plan), {'id': 'simons', 'principle': '검증', 'question': '기간이 달라도 같은가?'})
        self.assertIsNone(lenses.character_insight(None))


class PromptTest(unittest.IsolatedAsyncioTestCase):
    async def test_outline_replaces_fixed_investor_catalog_and_sections(self):
        ids = [s[0] for s in script_long.SECTIONS]
        plan = {'sections': {s: f'{s} 고유관점지시' for s in ids}}
        calls = []
        async def llm(prompt):
            calls.append(prompt)
            return '실제 자료로 비교한 종목별 근거입니다. ' * 15
        await script_long.generate_long_script('팩트', '관찰', '종목', '001210', llm,
                                              section_gap=0, editorial_brief='배정관점', editorial_plan=plan)
        for sid, prompt in zip(ids, calls):
            self.assertIn(f'{sid} 고유관점지시', prompt)
            self.assertNotIn('벤저민 그레이엄', prompt)
        self.assertIn('[다듬을 초안]', calls[-1])

    async def test_invalid_outline_stops_before_script(self):
        with self.assertRaises(ValueError):
            await lenses.make_outline('팩트', '관찰', '브리프', {}, [], AsyncMock(return_value='{}'))


if __name__ == '__main__':
    unittest.main()
