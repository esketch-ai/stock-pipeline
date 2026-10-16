"""30년 차 방송국 오디오 감독 & 보이스 디렉팅 엔진 (Voice Director System).

역할:
    1. 유튜브 주식 채널 특성에 맞춘 '전문가 엔터테이너' 보이스 페르소나 설정.
    2. 평이한 대본을 분석하여 '주식 챠트를 뿌셔 보까!', 도파민 오프닝 훅,
       수급 반전, 리스크 경고, 3대 실전 수칙 등 핵심 구간에 다이내믹 SSML 연출 적용.
    3. Google Cloud TTS (Neural2/Chirp3-HD) 및 타 프로바이더와의 완벽한 호환성.
    4. Whisper 단어 타임스탬프 및 forced alignment 자막 싱크 무결성 보장.
"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from typing import Final

# ── 보이스 페르소나 프리셋 ─────────────────────────────────
VOICE_PERSONAS: Final[dict[str, dict[str, str | float]]] = {
    # 1. 메인 추천: 에너지와 신뢰감을 겸비한 전문 유튜브 애널리스트
    "ANALYST_ENERGETIC": {
        "voice": "ko-KR-Neural2-C",
        "desc": "남성 · 30-40대 활력 넘치는 수석 애널리스트 (SSML 다이내믹스 최적화)",
        "rate": 1.03,
        "pitch": 0.0,
    },
    # 2. 최신 구글 생성형 초고음질 모델
    "CHIRP_PREMIUM": {
        "voice": "ko-KR-Chirp3-HD-Fenrir",
        "desc": "남성 · 최신 고음질 생성형 모델 (세련되고 스마트한 톤)",
        "rate": 1.02,
        "pitch": 0.0,
    },
    # 3. 밝고 경쾌한 엔터테인먼트 톤
    "CHIRP_PUCK": {
        "voice": "ko-KR-Chirp3-HD-Puck",
        "desc": "남성 · 빠르고 경쾌한 도파민 부스터 톤",
        "rate": 1.04,
        "pitch": 0.0,
    },
    # 4. 당당하고 예리한 여성 수석 전문가
    "LEADER_FEMALE": {
        "voice": "ko-KR-Neural2-A",
        "desc": "여성 · 확신에 찬 당당한 수석 전략가",
        "rate": 1.02,
        "pitch": 0.0,
    },
    # 5. 정통 지상파 경제 앵커
    "CALM_ANCHOR": {
        "voice": "ko-KR-Neural2-B",
        "desc": "여성 · 지적이고 차분한 정통 경제 앵커",
        "rate": 0.98,
        "pitch": 0.0,
    },
}

DEFAULT_PERSONA = "ANALYST_ENERGETIC"


def strip_ssml(text: str) -> str:
    """SSML 태그를 제거하고 순수 텍스트만 추출한다."""
    if not text:
        return ""
    # XML 태그 제거
    clean = re.sub(r"<[^>]+>", " ", text)
    # XML 엔티티 언이스케이프
    clean = saxutils.unescape(clean)
    # 중복 공백 정리
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n\s*\n", "\n", clean)
    return clean.strip()


def direct_script_for_tts(text: str, provider: str = "gcloud") -> str:
    """대본 텍스트를 분석하여 오디오 감독의 다이내믹 연출을 입힌다.

    gcloud 프로바이더의 경우 완벽한 SSML 마크업을 생성하여,
    '뿌셔 보까!', 도파민 오프닝 훅, 리스크 경고, 3대 수칙 등에
    피치, 볼륨, 속도, 호흡(Pause)의 역동적 다이내믹 레인지를 부여한다.
    """
    if not text:
        return ""

    # 이미 SSML인 경우 그대로 반환
    stripped = text.strip()
    if stripped.startswith("<speak>") and stripped.endswith("</speak>"):
        return text

    # SSML 미지원 프로바이더 (openai, local 등)는 텍스트만 다듬어 반환
    if provider.lower() not in ("gcloud", "google"):
        return _polish_plain_text(text)

    return _apply_ssml_direction(text)


def _polish_plain_text(text: str) -> str:
    """일반 LLM TTS(OpenAI 등)를 위한 텍스트 호흡 정리."""
    t = text
    # 시그니처 구호 뒤 쉼표나 느낌표 강화
    t = re.sub(r"(뿌셔\s*보까)(?![!?,])", r"\1!", t)
    # 첫째, 둘째 뒤 호흡
    t = re.sub(r"(\b(?:첫째|둘째|셋째|넷째|다섯째),)", r"\1 ", t)
    return t


def _apply_ssml_direction(text: str) -> str:
    """Google Cloud TTS용 7대 방송 오디오 연출 SSML 생성 (토큰 기반 안전 치환)."""
    tokens: list[str] = []

    def put_token(markup: str) -> str:
        idx = len(tokens)
        tokens.append(markup)
        return f"@@SSML_TOK_{idx}@@"

    # 1. 특수문자 이스케이프 선행 (& -> &amp;, < -> &lt;, > -> &gt;)
    escaped = saxutils.escape(text)

    # 2. [연출 1] 시그니처 타이틀 ('주식 챠트를 뿌셔 보까')
    escaped = re.sub(
        r"([\'\"]?주식\s*챠트를\s*뿌셔\s*보까[\'\"]?)",
        lambda m: put_token(
            f'<prosody pitch="+2.0st" rate="105%"><emphasis level="moderate">{m.group(1)}</emphasis></prosody>'
        ),
        escaped,
    )

    # 3. [연출 2] 킬러 캐치프레이즈 구호 ("뿌셔 보까!", "시원하게 뿌셔 보까!")
    escaped = re.sub(
        r"((?:시원하게\s+|통쾌하게\s+|함께\s+)?뿌셔\s*보까[!？?]?)",
        lambda m: put_token(
            f'<break time="200ms"/><emphasis level="strong"><prosody pitch="+3.5st" rate="112%" volume="+2.5dB">{m.group(1)}</prosody></emphasis><break time="350ms"/>'
        ),
        escaped,
    )

    # 4. [연출 3] 기타 뿌셔 변형 ("뿌셔 보겠습니다", "뿌셔 볼 종목", "뿌셔 보았습니다")
    escaped = re.sub(
        r"((?:시원하게\s+|통쾌하게\s+|알기\s*쉽게\s+)?뿌셔\s*(?:보겠습니다|볼\s*종목|보았습니다)[!？.]?)",
        lambda m: put_token(
            f'<emphasis level="moderate"><prosody pitch="+1.8st" rate="106%" volume="+1.5dB">{m.group(1)}</prosody></emphasis>'
        ),
        escaped,
    )

    # 5. [연출 4] 핵심 넘버링 앵커 ("첫째,", "둘째,", "셋째,")
    escaped = re.sub(
        r"(\b(?:첫째|둘째|셋째|넷째|다섯째),)",
        lambda m: put_token(
            f'<break time="200ms"/><emphasis level="moderate"><prosody pitch="+1.5st">{m.group(1)}</prosody></emphasis><break time="120ms"/>'
        ),
        escaped,
    )

    # 6. [연출 5] 도파민 오프닝 질문 & 훅 문장
    escaped = re.sub(
        r"([^.!?\n]{5,80}?(?:어떻게 하시겠습니까|주목해야 할까요|말이 안 되죠|미친 가게가 있다면|기적이 벌어지고 있습니다|특가 바겐세일하고 있다는 뜻입니다)[!?]?)",
        lambda m: put_token(
            f'<prosody pitch="+1.8st" rate="104%">{m.group(1)}</prosody><break time="250ms"/>'
        ),
        escaped,
    )

    # 7. [연출 6] 리스크 경고 & 마지노선 (진지하고 단호한 베이스 톤)
    escaped = re.sub(
        r"((?:절대\s*사수|손절선|생명선|칼같은\s*분할\s*매수|안전벨트\s*스탑로스|방심하면\s*지옥)[^.!?\n]*[.!?]?)",
        lambda m: put_token(
            f'<prosody pitch="-1.5st" rate="96%" volume="+1.0dB">{m.group(1)}</prosody>'
        ),
        escaped,
    )

    # 8. [연출 7] 아웃트로 & 구독 훅
    escaped = re.sub(
        r"(구독과 좋아요[^.!?\n]*알림 설정[^.!?\n]*[.!?]?)",
        lambda m: put_token(
            f'<break time="250ms"/><prosody pitch="+1.8st" rate="105%" volume="+1.5dB">{m.group(1)}</prosody>'
        ),
        escaped,
    )
    escaped = re.sub(
        r"(내일도 가장 확실한 차트 급소 분석으로 찾아오겠습니다[.!]?)",
        lambda m: put_token(
            f'<prosody pitch="+1.5st" rate="103%">{m.group(1)}</prosody><break time="200ms"/>'
        ),
        escaped,
    )

    # 토큰 복원 (완벽한 단일 패스)
    for idx, val in enumerate(tokens):
        escaped = escaped.replace(f"@@SSML_TOK_{idx}@@", val)

    # 연속된 break 정리
    escaped = re.sub(r'(<break time="\d+ms"/>\s*)+<break time="(\d+)ms"/>', r'<break time="\2ms"/>', escaped)

    return f"<speak>\n{escaped}\n</speak>"


def synthesize_with_persona(text: str, out_path: Path, persona_name: str = DEFAULT_PERSONA) -> Path:
    """지정된 보이스 페르소나 및 SSML 연출로 음성을 합성한다."""
    import gcloud_tts
    import config

    persona = VOICE_PERSONAS.get(persona_name, VOICE_PERSONAS[DEFAULT_PERSONA])
    voice = str(persona["voice"])
    rate = float(persona.get("rate", 1.03))
    pitch = float(persona.get("pitch", 0.0))

    orig_voice = config.GOOGLE_TTS_VOICE
    config.GOOGLE_TTS_VOICE = voice

    ssml = direct_script_for_tts(text, provider="gcloud")
    try:
        res = gcloud_tts.synth(ssml, out_path, rate=rate, pitch=pitch)
        if res is None:
            raise RuntimeError(f"합성 실패 (persona: {persona_name})")
        return res
    finally:
        config.GOOGLE_TTS_VOICE = orig_voice


if __name__ == "__main__":
    from pathlib import Path

    test_text = (
        "어렵고 복잡한 주식 차트를 알기 쉽게 시원하게 뽀개 드리는 '주식 챠트를 뿌셔 보까'에 오신 것을 환영합니다! "
        "만 원짜리 지폐를 길바닥에서 2,600원에 파는 미친 가게가 있다면, 여러분은 어떻게 하시겠습니까? "
        "상식적으로 말이 안 되죠. 하지만 오늘 시장에선 바로 그 기적이 벌어지고 있습니다! "
        "첫째, 목표주가 괴리율이 70%에 달합니다. "
        "둘째, 주당 38,189원이라는 든든한 순자산이 바닥을 지켜주고 있습니다. "
        "자, 먼저 차트의 기본인 일봉 캔들을 시원하게 뿌셔 보까! "
        "8,184원 지지선은 절대 사수해야 할 생명선입니다. "
        "구독과 좋아요, 알림 설정 눌러주시면 내일도 가장 확실한 차트 급소 분석으로 찾아오겠습니다."
    )
    directed = direct_script_for_tts(test_text, provider="gcloud")
    print("=== SSML Directed Output ===")
    print(directed)
    print("\n=== Stripped SSML Back ===")
    print(strip_ssml(directed))

    # 테스트 음성 합성
    test_out = Path("cache/voice_samples/cli_test_persona.mp3")
    synth_res = synthesize_with_persona(test_text, test_out, "ANALYST_ENERGETIC")
    print(f"\n=== Synthesized Persona Sample: {synth_res} ({synth_res.stat().st_size} bytes) ===")
