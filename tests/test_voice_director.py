"""voice_director 단위 테스트: 30년 차 오디오 감독 & 보이스 디렉팅 검증."""

import unittest
import voice_director


class TestVoiceDirector(unittest.TestCase):
    def test_signature_hook_ssml(self):
        text = "차트의 기본인 일봉 캔들을 시원하게 뿌셔 보까! 주식 챠트를 뿌셔 보까에 오신 것을 환영합니다."
        ssml = voice_director.direct_script_for_tts(text, provider="gcloud")
        self.assertTrue(ssml.startswith("<speak>"))
        self.assertTrue(ssml.endswith("</speak>"))
        # 킬러 캐치프레이즈 태그 검증
        self.assertIn('prosody pitch="+3.5st"', ssml)
        self.assertIn('rate="112%"', ssml)
        self.assertIn('emphasis level="strong"', ssml)
        # 타이틀 언급 검증
        self.assertIn('prosody pitch="+2.0st"', ssml)

    def test_dopamine_question_ssml(self):
        text = "만 원짜리 지폐를 길바닥에서 2,600원에 파는 미친 가게가 있다면, 여러분은 어떻게 하시겠습니까? 상식적으로 말이 안 되죠."
        ssml = voice_director.direct_script_for_tts(text, provider="gcloud")
        self.assertIn('prosody pitch="+1.8st"', ssml)
        self.assertIn('<break time="250ms"/>', ssml)

    def test_numbering_anchors(self):
        text = "첫째, 목표주가가 높습니다. 둘째, 자산가치가 큽니다. 셋째, 수급이 좋습니다."
        ssml = voice_director.direct_script_for_tts(text, provider="gcloud")
        self.assertIn('emphasis level="moderate"><prosody pitch="+1.5st">첫째,</prosody></emphasis>', ssml)
        self.assertIn('emphasis level="moderate"><prosody pitch="+1.5st">둘째,</prosody></emphasis>', ssml)
        self.assertIn('emphasis level="moderate"><prosody pitch="+1.5st">셋째,</prosody></emphasis>', ssml)

    def test_risk_warning_ssml(self):
        text = "8,184원 지지선은 절대 사수해야 할 생명선입니다. 칼같은 분할 매수 원칙이 필수적입니다."
        ssml = voice_director.direct_script_for_tts(text, provider="gcloud")
        self.assertIn('prosody pitch="-1.5st"', ssml)
        self.assertIn('rate="96%"', ssml)

    def test_strip_ssml_roundtrip(self):
        original = "일봉 캔들을 시원하게 뿌셔 보까! 첫째, 안전이 우선입니다. 절대 사수해야 할 생명선입니다."
        ssml = voice_director.direct_script_for_tts(original, provider="gcloud")
        recovered = voice_director.strip_ssml(ssml)
        # 공백 정규화 후 핵심 어절 순서 보존 검증
        words_orig = original.split()
        words_rec = recovered.split()
        self.assertEqual(words_orig, words_rec)

    def test_plain_text_provider(self):
        text = "일봉 캔들을 뿌셔 보까 첫째, 안전이 우선입니다."
        polished = voice_director.direct_script_for_tts(text, provider="openai")
        self.assertNotIn("<speak>", polished)
        self.assertIn("뿌셔 보까!", polished)
        self.assertIn("첫째, ", polished)


if __name__ == "__main__":
    unittest.main()
