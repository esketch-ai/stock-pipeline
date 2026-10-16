"""대본 검증 게이트의 오탐 회귀 — 실제 대본에서 차단됐던 사례."""
import unittest

import josa_rules
import korean_lint
import numeric_verify


class JosaTest(unittest.TestCase):
    def test_question_ending_is_not_a_particle(self):
        for text in ("이건 반등인가?", "자리는 어디인가", "저평가인가요", "급등일까?", "무슨 일인가"):
            self.assertEqual(josa_rules.check_josa(text), [], text)

    def test_real_particle_error_is_still_caught(self):
        # 받침 없는 명사 뒤 이/가 는 어절 끝에서 잘못된 조사다.
        issues = josa_rules.check_josa("전망가 잘 봤다")
        self.assertTrue(any(i["kind"] == "조사(신조법)" for i in issues), issues)


class LintTest(unittest.TestCase):
    def test_noun_ending_in_ga_is_not_a_particle(self):
        for text in ("최근 평가가 나왔습니다.", "평가. 한계가 있다.", "시가 3,860원", "추가가 붙었다"):
            self.assertEqual(josa_rules.check_josa(text), [], text)

    def test_correct_spelling_is_not_flagged(self):
        self.assertEqual(korean_lint.check("아무 정보도 없다").issues, [])
        self.assertTrue(korean_lint.check("이건 없 다").issues)

    def test_isen_gua_question_is_not_a_particle(self):
        self.assertEqual(josa_rules.check_josa("무슨 일인가"), [])
        self.assertEqual(josa_rules.check_josa("어느 쪽인가"), [])


class NumericTest(unittest.TestCase):
    def test_52week_phrase_is_not_a_price_claim(self):
        result = numeric_verify.NumResult()
        numeric_verify._verify_mentions(
            "현재가 52주 신고가보다 낮습니다", 1_220, "현재가", result, [1_220]
        )
        self.assertEqual(result.checked, 0, result.summary())
        self.assertFalse(result.errors)

    def test_wrong_price_is_still_caught(self):
        result = numeric_verify.NumResult()
        numeric_verify._verify_mentions(
            "현재가는 52원입니다", 1_220, "현재가", result, [1_220]
        )
        self.assertTrue(result.errors)


if __name__ == "__main__":
    unittest.main()