"""단계 2 — LLM 대본 비동기 생성 + mplfinance 4K 투명 차트 렌더."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import httpx

import config
import pandas as pd
from config import CACHE_DIR, DATA_DIR
from logger import log
from screening import Candidate

PROMPT_TEMPLATE = """당신은 한국 주식 유튜브 채널의 대본을 쓰는 프로 라이터입니다.
설명식 브리딩이 아니라, 시청자가 끝까지 들을 만한 이야기를 씁니다.

아래 종목으로 60~90초 분량의 한국어 대본을 쓰세요.

[확인된 팩트 — 반드시 이 안의 수치만 사용]
{facts_block}

[기술적 지표]
- {reason}

═══════════════════════════════════════════
## 금지 (이걸 어기면 폐기됩니다)
═══════════════════════════════════════════
1. 같은 단어를 3번 이상 반복 금지. (예: "급등" "매수세" "관심" 연타)
2. 사실 나열형 금지. "A원은 B원입니다" 식의 보고 멘트 3문장 연속 금지.
3. 매 문장이 독립 완결 금지. 앞 문장과 이어지는 접속이 있어야 한다.
4. 확인되지 않은 정보를 만들지 않는다:
   - "공시가 있습니다" / "특별한 공시는 없습니다" → 공시 조회 권한이 없다
   - "테마입니다" / "테마성" → 확인 불가
   - "기관이 사들였습니다" / "외국인이 유입" → 수급 데이터 없음
   - "실적이 나빠졌습니다" / "호실적" → 재무 미조회
   위와 같은 표현을 쓰려면 팩트 블록에 근거가 있을 때만, 그리고 "추정된다" 는 뉘앙스로 쓴다.
5. 금지 클리셰 오프닝:
   "여러분, ~~ 보셨나요?" / "오늘은 ~~ 을 다루겠습니다" / "여러분 반갑습니다"

═══════════════════════════════════════════
## 반드시 지켜야 할 구조
═══════════════════════════════════════════
- body 는 정확히 4~5개. 각 항목은 한 문장 15~45자.
- 2번째와 4번째 항목은 반드시 **해석/의미** 를 담아라. 숫자 나열로 끝내지 마라.
- 마지막 body 항목은 리스크나 관점을 던지는 반전 한 마디.

═══════════════════════════════════════════
## 톤 — 이 채널의 특성
═══════════════════════════════════════════
- 감각적이고 브랜드 있다. 평범한 뉴스 브리딩이 아니라 "읽히는 이야기".
- 비유·대비·의 analogies 를 적극 사용. (예: "1년 고점보다 78% 아래" → "산 정상에서 구름밑으로")
- 숫자는 놀라운 발견처럼 제시: "38,000원. 이 숫자, 하루 만에 12,000원 가까이 밀렸습니다."
- 존댓말 구어체. "~입니다"보다는 "~했죠", "~거든요" 같은 생동감.
- But 짧고 쿵하게. 군더더기 수식어("아주", "역시", "다시 한번") 쓰지 않는다.
- 투자 권유 금지: 매수/매도/보유 권유 없음.
- closing 에 반드시 포함: "이 영상은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다."
- closing 은 기계적 고지 말고, 시청자를 남기는 질문이나 여운으로 끝낸 뒤 고지를 붙여라.

═══════════════════════════════════════════
## 예시 (이 톤을 느껴라)
═══════════════════════════════════════════
나쁜 예:
"동양고속은 오늘 38,000원에 거래를 마쳤습니다. 하루 만에 29.91%가 올랐습니다.
이는 사실상 상한가에 근접한 수치입니다. 이러한 급등은 일반적이지 않습니다."

좋은 예:
"38,000원입니다. 하루 만에 12,000원 가까이 밀렸어요.
그런데 이 종목, 1년 전엔 17만원이었습니다. 지금은 그 22% 지점에 있어요.
고속도로 위를 달리던 이 종목이 지금은 반대편 차선을 달리고 있는 셈이죠.
숫자만 보면 강한데, 이게 무서운 이유가 있어요."

═══════════════════════════════════════════
[출력 형식 — 이 JSON만, 마크다운 코드블록 없이]
{{"hook": "첫 15초 오프닝 1~2문장",
  "body": ["포인트1", "포인트2", "포인트3", "포인트4"],
  "closing": "여운 + 투자권유 고지"}}"""

# mplfinance 는 한글 라벨을 시스템 폰트로 그리므로 한글 폰트를 강제 등록한다.
_KOREAN_FONTS = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    str(Path.home() / "Library/Fonts/NotoSansCJKkr-Regular.otf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


def _setup_korean_font() -> str:
    """차트에 한글이 깨지지 않도록 폰트를 등록하고 이름을 반환."""
    import matplotlib.font_manager as fm

    available = {f.name for f in fm.fontManager.ttflist}
    for path in _KOREAN_FONTS:
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
            except Exception:
                continue
            name = fm.FontProperties(fname=path).get_name()
            if name in available or True:
                return name
    return "AppleGothic"


@dataclass
class Script:
    ticker: str
    name: str
    hook: str
    body: list[str]
    closing: str
    charts: list[str] = field(default_factory=list)
    chart_paths: list[str] = field(default_factory=list)
    quality_score: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join([self.hook, *self.body, self.closing])

    def to_dict(self) -> dict:
        return asdict(self)


def _anthropic_key() -> str | None:
    return config.env("ANTHROPIC_API_KEY")


async def _call_openai(prompt: str) -> str:
    model = config.env("OPENAI_MODEL", "gpt-4o")

    # 추론 모델(gpt-5 / o시리즈 / gpt-6-* )은 temperature 와 response_format 을
    # 지원하지 않고 max_tokens 대신 max_completion_tokens 을 쓴다.
    is_reasoning = model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6"))

    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if is_reasoning:
        payload["max_completion_tokens"] = 16000
    else:
        payload["temperature"] = 0.7
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.env('OPENAI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _call_anthropic(prompt: str) -> str:
    import os

    async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _anthropic_key(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.env("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
                "system": "한국 주식 리스크 채널 대본 작성专家. 반드시 유효한 JSON만 출력하세요.",
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


async def _call_gemini(prompt: str) -> str:
    key = config.gemini_key()
    model = config.env("GEMINI_MODEL", "gemini-2.5-flash")
    async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _call_ollama(prompt: str, as_json: bool = False) -> str:
    """로컬 Ollama. 데이터·대본이 기기를 떠나지 않는다.

    로컬 모델은 JSON 지시만으로는 형식을 지키지 못하므로 format=json 을 함께 준다.
    """
    host = config.OLLAMA_HOST.rstrip("/")
    model = config.OLLAMA_MODEL
    is_harmony = model.startswith("gpt-oss")
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.85,
            "num_ctx": config.env_int("OLLAMA_NUM_CTX", 16384),
        },
    }
    if is_harmony:
        # gpt-oss 의 사고(thinking) 토큰은 top-level 매개변수다.
        # options 안에 넣으면 무시되어 대본 생성에 수백 초씩 걸린다.
        payload["think"] = config.env_bool("OLLAMA_THINK", False)
    if as_json:
        payload["format"] = "json"
    async with httpx.AsyncClient(timeout=config.env_int("OLLAMA_TIMEOUT", 1200)) as client:
        resp = await client.post(f"{host}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _call_llm(prompt: str, as_json: bool = False) -> str:
    provider = config.LLM_PROVIDER
    log.info("LLM 호출 — provider=%s", provider)

    # 429/503 등 일시적 오류는 자동 재시도 (지수 백오프, 레이트리밋은 더 길게)
    attempts = 5
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            if provider == "ollama":
                return await _call_ollama(prompt, as_json=as_json)
            if provider == "anthropic":
                if not _anthropic_key():
                    raise RuntimeError("ANTHROPIC_API_KEY 미설정 (.env 확인)")
                return await _call_anthropic(prompt)
            if provider == "gemini":
                if not config.gemini_key():
                    raise RuntimeError("GEMINI_API_KEY 미설정 (.env 확인)")
                return await _call_gemini(prompt)
            if not config.openai_key():
                raise RuntimeError("OPENAI_API_KEY 미설정 (.env 확인)")
            return await _call_openai(prompt)
        except RuntimeError:
            raise  # 설정 오류는 재시도 무의미
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            # 429 = 할당량 소진. 재시도해도 회복되지 않으므로 즉시 실패시킨다.
            # (일일 한도면 몇 분 기다려도 소용없다 — 하루가 지나야 풀린다)
            quota_exhausted = (
                "quota" in msg.lower()
                or "RESOURCE_EXHAUSTED" in msg
                or "429" in msg
            )
            if quota_exhausted:
                log.error("LLM 할당량 소진(429) — 재시도하지 않습니다. "
                          "해소: aistudio.google.com/apikey → Billing 연결")
                raise RuntimeError(
                    "LLM API 할당량이 소진되었습니다. Google AI Studio 에서 "
                    "결제(Billing)를 연결하거나, 내일 한도가 초기화된 뒤 재실행하세요."
                )

            rate_limited = "Too Many Requests" in msg
            if i < attempts - 1:
                wait = 30.0 * (i + 1) if rate_limited else 2.0 ** (i + 1)
                log.warning("LLM 호출 실패(%s) — %.0f초 후 재시도 %d/%d",
                            type(exc).__name__, wait, i + 1, attempts)
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _parse_script(raw: str, cand: Candidate) -> Script:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().rstrip("`")

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 응답에서 JSON을 찾을수 없음: {raw[:200]}")
    data = json.loads(text[start : end + 1])

    return Script(
        ticker=cand.ticker,
        name=cand.name,
        hook=data.get("hook", ""),
        body=list(data.get("body", [])),
        closing=data.get("closing", ""),
    )


def render_charts(cand: Candidate, script: Script) -> list[str]:
    """mplfinance로 4K 투명 배경 차트 3종을 생성한다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplfinance as mpf
    from pykrx import stock

    width, height = config.resolution()
    dpi = 100
    out_dir = CACHE_DIR / cand.ticker
    out_dir.mkdir(parents=True, exist_ok=True)

    hist = stock.get_market_ohlcv_by_date(
        fromdate=(datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
        todate=datetime.now().strftime("%Y%m%d"),
        ticker=cand.ticker,
    )
    if hist is None or len(hist) == 0:
        # 야간 배치라 주말/공휴일에는 오늘자 데이터가 없다 → 직전 거래일로 재조회
        from screening import last_trading_day

        tday = last_trading_day(stock)
        log.info("%s 차트 데이터 %s 기준 재조회", cand.ticker, tday)
        hist = stock.get_market_ohlcv_by_date(
            fromdate=(datetime.strptime(tday, "%Y%m%d") - timedelta(days=180)).strftime("%Y%m%d"),
            todate=tday,
            ticker=cand.ticker,
        )
    if hist is None or len(hist) < 20:
        log.warning("%s 차트 데이터 부족 — 차트 생성 생략", cand.ticker)
        return []

    # pykrx 는 OHLCV + '등락률' 을 반환한다. mplfinance 는 정확히 5개 컬럼을
    # 영문명(Open/High/Low/Close/Volume)으로 요구하므로 필요한 컬럼만 골라 개명한다.
    rename_map = {"시가": "Open", "고가": "High", "저가": "Low",
                  "종가": "Close", "거래량": "Volume"}
    missing = [k for k in rename_map if k not in hist.columns]
    if missing:
        log.warning("%s 차트 컬럼 누락 %s — 차트 생성 생략", cand.ticker, missing)
        return []
    hist = hist[list(rename_map.keys())].rename(columns=rename_map).copy()
    if not isinstance(hist.index, pd.DatetimeIndex):
        hist.index = pd.to_datetime(hist.index)

    paths: list[str] = []

    marketcolors = mpf.make_marketcolors(
        up="#FF3B30", down="#0A84FF", edge="inherit", wick="inherit", volume="in"
    )
    font_name = _setup_korean_font()
    # 'style' 은 matplotlib rcParam 이 아니라 mplfinance 전용 인자다.
    # mplfinance 는 내부에서 plt.style.use() 를 호출해 rc 를 덮어쓰므로,
    # 한글 폰트 등 커스텀 rc 는 make_mpf_style(rc=...) 로 전달해야 실제로 적용된다.
    rc = {
        "font.family": font_name,
        "font.sans-serif": [font_name, "Apple SD Gothic Neo", "NanumGothic"],
        "axes.unicode_minus": False,
        "axes.titlecolor": "#F5F7FA",
        "axes.labelcolor": "#8FA3C8",
        "text.color": "#F5F7FA",
        "xtick.color": "#8FA3C8",
        "ytick.color": "#8FA3C8",
        "grid.color": "#2A3550",
        # 4K 캔버스에서 가독성을 위해 축제목/눈금 글자를 크게 잡는다
        "axes.titlesize": 56,
        "axes.labelsize": 34,
        "xtick.labelsize": 28,
        "ytick.labelsize": 28,
        "legend.fontsize": 30,
    }
    mpf_style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=marketcolors,
        gridcolor="#2A3550",
        figcolor="none",
        facecolor="none",
        rc=rc,
    )
    with plt.rc_context(rc):
        charts = [
            ("candlestick", "price_chart"),
            ("line", "trend_line"),
        ]
        for kind, filename in charts:
            fig, axes = mpf.plot(
                hist,
                type=kind,
                volume=True,
                style=mpf_style,
                title=f"{cand.name} ({cand.ticker})",
                figratio=(16, 9),
                figsize=(width / dpi, height / dpi),
                returnfig=True,
            )
            fig.patch.set_alpha(0.0)
            for ax in axes:
                ax.set_facecolor("none")
            path = out_dir / f"{filename}.png"
            # bbox_inches="tight" 를 쓰면 4K 규격에서 잘려나므로 정확한 크기를 유지한다.
            fig.savefig(path, dpi=dpi, transparent=True)
            plt.close(fig)
            paths.append(str(path))
            log.info("차트 생성: %s (%dx%d, 폰트=%s)", path.name, width, height, font_name)

    (DATA_DIR / f"{cand.ticker}_ohlcv.csv").write_text(hist.to_csv(), encoding="utf-8")
    script.chart_paths = paths
    return paths


def _build_prompt(cand: Candidate) -> str:
    """확인된 팩트를 수집해 프롬프트로 조립한다 (LLM 환각 방지)."""
    import facts as facts_mod

    try:
        f = facts_mod.collect(cand.ticker, cand.name, cand.market)
    except Exception as exc:
        log.warning("%s 팩트 수집 실패 — 최소 정보로 진행: %s", cand.ticker, exc)
        f = {"ticker": cand.ticker, "name": cand.name}

    return PROMPT_TEMPLATE.format(
        ticker=cand.ticker,
        name=cand.name,
        facts_block=facts_mod.format_facts(f),
        reason=cand.reason,
    )


async def _generate_one(cand: Candidate, semaphore: asyncio.Semaphore) -> Script:
    async with semaphore:
        import script_quality

        prompt = _build_prompt(cand)
        attempts = config.LLM_MAX_RETRIES if hasattr(config, "LLM_MAX_RETRIES") else 2
        script = None
        best = None

        for i in range(attempts):
            raw = await _call_llm(prompt)
            candidate_script = _parse_script(raw, cand)
            result = script_quality.check(candidate_script)

            if best is None or result["score"] > best[1]["score"]:
                best = (candidate_script, result)

            if result["score"] >= 85:
                break

            if i < attempts - 1:
                log.warning(
                    "%s 대본 품질 미달(점수 %d): %s → 재생성",
                    cand.name, result["score"], ", ".join(result["violations"][:3]),
                )
                prompt = script_quality.build_retry_prompt(prompt, candidate_script, result)

        script, result = best
        script.quality_score = result["score"]
        script.violations = result["violations"]
        log.info(
            "대본 생성 완료: %s (%s) 점수=%d%s",
            cand.name, cand.ticker, result["score"],
            f" 위반={result['violations'][:3]}" if result["violations"] else "",
        )
        return script


async def _generate_all(candidates: list[Candidate]) -> list[Script]:
    sem = asyncio.Semaphore(config.LLM_MAX_CONCURRENCY)
    tasks = [_generate_one(c, sem) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scripts: list[Script] = []
    for cand, res in zip(candidates, results):
        if isinstance(res, Exception):
            log.error("대본 생성 실패 %s: %s", cand.ticker, res)
        else:
            scripts.append(res)
    return scripts


def generate_scripts(candidates: list[Candidate]) -> list[Script]:
    if not candidates:
        log.warning("후보 종목이 없어 대본 생성 단계 종료")
        return []
    scripts = asyncio.run(_generate_all(candidates))

    for script in scripts:
        try:
            render_charts(
                next(c for c in candidates if c.ticker == script.ticker), script
            )
        except Exception as exc:
            log.error("차트 렌더 실패 %s: %s", script.ticker, exc)

    out = DATA_DIR / "scripts.json"
    out.write_text(json.dumps([s.to_dict() for s in scripts], ensure_ascii=False, indent=2), encoding="utf-8")
    return scripts
