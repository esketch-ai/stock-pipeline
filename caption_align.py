"""자막 텍스트 = 대본, 타이밍 = Whisper 경계 (강제 정렬).

왜 이 구조인가:
    기존 흐름은  대본 -> TTS 음성 -> Whisper 재인식 -> 자막  이었다.
    즉 이미 정확한 대본을 두고 음성을 다시 인식해 자막을 만들었다.
    그래서 고유명사('동양보석'), 숫자('112만 8백원') 같은 오류가 계속 발생했다.

    올바른 구조는  자막 텍스트는 **대본을 그대로** 쓰고,
    타이밍만 음성에서 얻는 것(강제 정렬, forced alignment) 이다.

방법:
    1. 대본을 어절로 자른다 (정답 텍스트)
    2. Whisper 타임스탬프에서 어절 경계 시각을 얻는다 (정답이 아닌 '언제')
    3. 두 열을 순서 정렬(sequence alignment)한다.
       - 큰 덩어리(eqaul)는 그대로
       - 잘린 구간(replace/insert/delete)은 **대본 어절**로 채운다
    4. 결과: 텍스트는 100% 대본, 시간은 음성 실측

이렇게 하면 인식 오류가 원천적으로 사라진다.
"""

from __future__ import annotations

import difflib
import math
import re

from logger import log

# 대본 어절 분리 (부호는 어절에 붙인다)
_WORD_RE = re.compile(r"[^\s]+")

# 한 어절이 화면에서 너무 길면 어깨로 나눌 기준
_MAX_CHARS = 14

# 조사·어미 목록 (긴 것부터 정렬).
# 이 경계 "앞"에서 자르면 한국어 어절로 읽힌다.
#   "한국거래소상장주식의실적이큰우리" → ["한국거래소상장주식", "의실적이", "큰우리"]
# 조사 경계가 없는 라틴어/숫자 덩어리는 균등 분할로 처리한다.
_JOSA = sorted(
    {
        "에서는", "에서도", "이라고", "이라는", "에도", "에는",
        "까지", "부터", "에게", "한테", "처럼", "만큼", "보다", "라는",
        "에서", "으로", "는데", "지만", "면서", "이며", "이고", "이라",
        "이나", "라도", "엔",
        "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
    },
    key=len,
    reverse=True,
)


def _norm(s: str) -> str:
    """비교용 정규화 — 부호 제거, 소문자."""
    return re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())


def _split_at_josa(core: str) -> list[str]:
    """조사/어미 앞에서 끊는다. 경계를 찾지 못하면 원본 그대로 반환한다."""
    pieces: list[str] = []
    start = 0

    for i in range(1, len(core)):
        if len(core) - start <= _MAX_CHARS:
            break
        for josa in _JOSA:
            if core.startswith(josa, i):
                if i - start >= 2:  # 한 글자 조각은 만들지 않는다
                    pieces.append(core[start:i])
                    start = i
                break

    pieces.append(core[start:])
    return pieces


def _balanced_split(chunk: str) -> list[str]:
    """조사 경계가 남은 조각을 고르게 나눈다 (마지막 1글자 조각 방지)."""
    n = max(1, math.ceil(len(chunk) / _MAX_CHARS))
    if n == 1:
        return [chunk]
    size = math.ceil(len(chunk) / n)
    return [chunk[i : i + size] for i in range(0, len(chunk), size)]


def _split_long(word: str) -> list[str]:
    """긴 어절을 화면 가독에 맞게 쪼갠다 (부호는 끝에 붙인다).

    한국어는 조사/어미 앞에서 끊어야 어절로 읽힌다
    ("한국거래소상장주식의실적이" → "한국거래소상장주식" / "의실적이").
    조사 경계가 없을 때만 균등 분할로 대체한다.
    """
    if len(word) <= _MAX_CHARS:
        return [word]

    m = re.match(r"^(.*?)([^\w가-힣]*)$", word, re.S)
    core, tail = (m.group(1), m.group(2)) if m else (word, "")

    if len(core) <= _MAX_CHARS:
        return [word]

    parts: list[str] = []
    for piece in _split_at_josa(core):
        parts.extend(_balanced_split(piece))

    if tail:
        parts[-1] += tail
    return parts


def build_from_script(
    script_text: str,
    whisper_timestamps: list[dict],
) -> list[dict]:
    """대본 텍스트 + Whisper 타이밍 → 자막용 타임스탬프.

    반환: [{'word': 대본 어절, 'start': float, 'end': float}, ...]

    원리:
        대본 어절열(정답)과 Whisper 인식열을 순서 정렬한다.
        정렬 결과에서 '같은 구간'은 그대로 두고,
        어긋난 구간은 대본 어절로 교체한다. (텍스트는 항상 대본 기준)
    """
    if not script_text or not whisper_timestamps:
        return []

    # ── 1. 대본 어절 (오디오 구간과 1:1 대응이 되도록 쪼갠다) ──
    raw_words = _WORD_RE.findall(script_text)
    if not raw_words:
        return []

    # ── 2. Whisper 경계 ──
    whisper_spans: list[tuple[str, float, float]] = []
    for t in whisper_timestamps:
        w = t.get("word", "")
        st = t.get("start", 0.0)
        en = t.get("end", st)
        if not w or en <= st:
            continue
        whisper_spans.append((w, float(st), float(en)))

    if not whisper_spans:
        # 경계가 없으면 전체를 균등 분할
        n = len(raw_words)
        span = (whisper_timestamps[-1].get("end", 60) if whisper_timestamps else 60)
        out = []
        for i, w in enumerate(raw_words):
            s = span * i / max(1, n)
            e = span * (i + 1) / max(1, n)
            out.append({"word": w, "start": s, "end": e})
        return out

    # ── 3. 순서 정렬 ──
    # 비교 키는 정규화 문자열. 수치 표기 차이(172800 vs 172,800)는 같게 본다.
    wkeys = [_norm(w) for w, _, _ in whisper_spans]
    skeys = [_norm(w) for w in raw_words]

    matcher = difflib.SequenceMatcher(None, wkeys, skeys, autojunk=False)

    # 각 대본 어절에 대응할 시간 구간을 배정한다
    script_spans: list[tuple[str, float, float]] = [None] * len(raw_words)  # type: ignore

    def _interp(span: tuple[str, float, float], ratio: float) -> tuple[float, float]:
        _, s, e = span
        return s + (e - s) * ratio, s + (e - s) * min(1.0, ratio + 0.001)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # Whisper 구간 [i1,i2) ↔ 대본 어절 [j1,j2)
        if tag == "equal":
            for k in range(i2 - i1):
                wi = i1 + k
                sjj = j1 + k
                if sjj < len(raw_words):
                    script_spans[sjj] = (raw_words[sjj], whisper_spans[wi][1], whisper_spans[wi][2])
        else:
            # 어긋난 구간: 전체 시간 범위를 대본 어절 수에 균등 배분
            t_start = whisper_spans[i1][1] if i1 < len(whisper_spans) else (
                whisper_spans[i1 - 1][2] if i1 > 0 else 0.0
            )
            t_end = whisper_spans[i2 - 1][2] if i2 > i1 else (
                whisper_spans[min(i2, len(whisper_spans) - 1)][2]
                if whisper_spans else t_start + 0.5
            )
            cnt = max(1, j2 - j1)
            step = (t_end - t_start) / cnt if cnt else 0.5
            for k in range(cnt):
                sj = j1 + k
                if sj < len(raw_words):
                    script_spans[sj] = (
                        raw_words[sj],
                        t_start + step * k,
                        t_start + step * (k + 1),
                    )

    # ── 4. 빈 구간 보간 ──
    last_end = 0.0
    for i, sp in enumerate(script_spans):
        if sp is None:
            prev = script_spans[i - 1][2] if i > 0 and script_spans[i - 1] else last_end
            script_spans[i] = (raw_words[i], prev, prev + 0.3)
        last_end = sp[2]

    # ── 5. 길이 제한 분할 (선택적) ──
    out: list[dict] = []
    for word, s, e in script_spans:
        pieces = _split_long(word)
        if len(pieces) == 1:
            out.append({"word": word, "start": s, "end": e})
        else:
            step = (e - s) / len(pieces)
            for k, p in enumerate(pieces):
                out.append({
                    "word": p,
                    "start": s + step * k,
                    "end": s + step * (k + 1),
                })

    log.info("자막 생성 — 대본 %d어절 (Whisper 경계 %d개)",
             len(raw_words), len(whisper_spans))
    return out


def verify(script_text: str, captions: list[dict]) -> dict:
    """자막 텍스트가 대본과 정확히 일치하는지 검증한다.

    자막은 대본에서 직접 만들어야 하므로, 이 검증이 실패하면
    무언가 잘못 끼어든 것이다 (예: 이전 파이프라인의 잔재).
    """
    script_norm = _norm(script_text)
    cap_norm = "".join(_norm(c.get("word", "")) for c in captions)

    if script_norm == cap_norm:
        return {"ok": True, "reason": "자막이 대본과 100% 일치"}

    # 어느 지점부터 어긋났는지
    sm = difflib.SequenceMatcher(None, script_norm, cap_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            return {
                "ok": False,
                "reason": f"위치 {i1}~{i2} 불일치: "
                          f"대본={script_norm[i1:i2][:30]!r} 자막={cap_norm[j1:j2][:30]!r}",
            }
    return {"ok": True, "reason": "자막이 대본과 일치"}