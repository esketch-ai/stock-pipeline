"""반복 멘트 방지 — 섹션 안에서 같은 문장이 되풀이되지 않는지."""
import re
import unittest

import script_long


def sections(*texts):
    return [{"id": f"s{i}", "title": f"구간{i}", "text": t} for i, t in enumerate(texts)]


class RepetitionTest(unittest.TestCase):
    def test_same_sentence_twice_is_detected(self):
        s = sections("이건 확인이 필요합니다. 시장이 다른 방향을 보입니다.",
                     "어제 같은 문장을 다시 쓰면 안 됩니다. 다음 구간은 넘어갑니다.")
        s[1]["text"] += " 이건 확인이 필요합니다."
        hits = script_long.repeated_sentences(s)
        self.assertTrue(any("확인이 필요" in h["text"] for h in hits), hits)

    def test_numbers_do_not_hide_duplicates(self):
        s = sections("현재가 240원입니다. 신고가 대비 76% 아래예요.")
        s[0]["text"] += " 현재가 240원입니다. 신고가 대비 76% 아래예요."
        self.assertTrue(script_long.repeated_sentences(s))

    def test_same_sentence_with_different_numbers_counts_as_repeat(self):
        # 문장마다 숫자가 달라 문장 중복으로는 안 잡힌다.
        # 실제로는 같은 문장을 숫자만 바꿔 반복한 것이다 → 횟수까지 올려 잡아야 한다.
        text = (
            "에이엔피는 52주 신고가 대비 77% 하락한 후 단기적으로 급등하며 주목받고 있습니다. "
            "에이엔피는 52주 신고가 대비 77% 하락한 후 3일 만에 27% 올라섰습니다. "
            "에이엔피는 52주 신고가 대비 77% 하락한 후 3일 연속 급등세를 보였습니다. "
            "에이엔피는 52주 신고가 대비 77% 하락 후 단기간에 급등하며 주목받고 있습니다."
        )
        hits = script_long.repeated_sentences(sections(text))
        self.assertTrue(hits)
        self.assertGreaterEqual(max(h["count"] for h in hits), 3)

    def test_distinct_scripts_pass(self):
        s = sections("에이엔피는 하루 만에 29% 올랐습니다. 신고가까지는 멀었습니다.",
                     "거래량이 0.6배에 그쳤다는 점이 오히려奇怪합니다.".replace("奇怪", "이러함"))
        self.assertEqual(script_long.repeated_sentences(s), [])

    def test_repeated_question_openers_are_detected(self):
        s = sections("이 전환이 지속될까요. 확인하려면 거래량을 봐야 합니다.",
                     "이 전환이 지속될까요. 이번엔 가격보다 물량을 보겠습니다.")
        self.assertTrue(script_long.repeated_sentences(s))


class RepairTest(unittest.IsolatedAsyncioTestCase):
    async def test_repair_rewrites_only_the_repeated_later_section(self):
        calls = []

        async def llm(prompt):
            calls.append(prompt)
            if "다시 작성한다" in prompt:
                return "새로운 접근으로 다시 쓰겠습니다. 이번 구간은 다른 각도에서 봅니다."
            return "구간 본문입니다. " * 5

        result = {"sections": sections(
            "기준 문장입니다. 여기서 출발합니다.",
            "기준 문장입니다. 저도 같은 말입니다."),
            "text": ""}
        result["text"] = "\n\n".join(x["text"] for x in result["sections"])
        out = await script_long.repair_repetitions(
            llm, result=result, facts_block="팩트", reason="이유", stock_name="종목",
            ticker="000000", editorial_brief="브리프", weights={"s0": 100, "s1": 100})
        self.assertEqual(out["regenerated_sections"], 1)
        self.assertEqual(out["repetitions"], [])
        self.assertEqual(len(calls), 1)
        # 첫 등장 문장은 보존하고, 뒤에 반복된 구간만 다시 쓴다.
        self.assertIn("기준 문장입니다", out["sections"][0]["text"])
        self.assertIn("새로운 접근", out["sections"][1]["text"])

    async def test_repair_passes_avoid_list_from_other_sections(self):
        seen = []

        async def llm(prompt):
            seen.append(prompt)
            if "다시 작성한다" in prompt:
                return "이 구간은 완전히 다른 각도에서 출발합니다. 이야기가 달라집니다."
            return "구간 본문입니다. " * 4

        secs = sections("첫 구간이라 여기서 시작합니다. 흐름이 잡힙니다.",
                        "첫 구간이라 여기서 시작합니다. 흐름이 잡힙니다.")
        out = await script_long.repair_repetitions(
            llm, result={"sections": secs, "text": "x"}, facts_block="f", reason="r",
            stock_name="종목", ticker="000000", editorial_brief="b", weights={"s0": 50, "s1": 50})
        self.assertTrue(any("이미 다른 구간에서 쓴 시작 표현" in p for p in seen))
        self.assertIn("첫 구간이라", out["sections"][0]["text"])

    async def test_repair_keeps_first_occurrence_section_intact(self):
        async def llm(prompt):
            return "전혀 다른 문장으로 다시 썼습니다. 각도도 바꿉니다."

        secs = sections("공통 도입 문장입니다. 세기가 있습니다.",
                        "공통 도입 문장입니다. 세기가 있습니다.")
        out = await script_long.repair_repetitions(
            llm, result={"sections": secs, "text": "x"}, facts_block="f", reason="r",
            stock_name="종목", ticker="000000", editorial_brief="b", weights={"s0": 50, "s1": 50})
        self.assertIn("공통 도입", out["sections"][0]["text"])
        self.assertIn("전혀 다른", out["sections"][1]["text"])


if __name__ == "__main__":
    unittest.main()