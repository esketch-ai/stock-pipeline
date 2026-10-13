"""script_gate 회귀 검증 — 02:04 야간 실패 재현/수정 확인.

재현한 버그 3건:
    1. 비동기 컨텍스트에서 asyncio.run() 불가 → LLM 교정이 매 라운드 실패
    2. render_report 의 josa_client 미정의 → NameError 로 단계2 전체 중단
    3. 조사 오류가 통과 판정에 반영되지 않음 (리포트만 차단 사유로 표기)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import josa_rules
import llm_proofread
import script_gate
from logger import log

FAILS = []
CALLS = {"n": 0}

# 100자 이상이어야 proofread 이 실제로 LLM 을 호출한다
SAMPLE = (
    "오늘 장 마감 기준 동양고속은 3일 사이 65% 가까이 급등했습니다. "
    "거래대금이 크게 늘었는데, 외국인 투자자의 순매수가 주된 배경입니다. "
    "다만 회사의 영업실적은 아직 Special 한 단계라는 점은 유의해야 합니다. "
    "다음 분기 실적 발표를 앞두고 변동성이 커질 수 있습니다."
)

# 1라운드에서 조사 오류가 검출 → 자동 교정 후 2라운드로 넘어가야 LLM 이 돈다.
# (깨끗한 대본은 1라운드에 통과하고 LLM 을 아끼는 게 정상 동작이다)
SAMPLE_NEEDS_FIX = SAMPLE + " 이 종목의 수익률를 다시 봅니다."


def check(name, cond, detail=""):
    print(f"  {'✓' if cond else '✖'} {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


async def fake_call_llm(prompt: str) -> str:
    CALLS["n"] += 1
    await asyncio.sleep(0)          # 진짜 I/O 가 있는 것처럼
    return SAMPLE.replace("Special 한 단계", "아직 Special 한 단계")


def sync_call_llm_stub():
    """동기 컨텍스트용 — 이미 실행 중인 루프에서 호출되면 안 된다."""
    return asyncio.run(fake_call_llm("x"))


def main() -> int:
    print("\n[1] josa_rules.summary 존재")
    check("summary 정의", hasattr(josa_rules, "summary"))
    check("빈 결과", josa_rules.summary([]) == "이상 없음")
    check("오류 1건", "오류 1건" in josa_rules.summary([{"level": "error"}]))
    check("경고 1건", "경고 1건" in josa_rules.summary([{"level": "warn"}]))

    print("\n[2] 조사 오류 검출 + 자동 교정")
    bad = "이 종목의 수익률를 다시 봅니다."
    issues = josa_rules.check_josa(bad)
    check("조사 오류 검출", len(issues) > 0, f"{len(issues)}건")
    fixed, fx = josa_rules.auto_fix_josa(bad)
    check("자동 교정", fixed == "이 종목의 수익률을 다시 봅니다.", fixed)
    check("교정 후 잔여 0", len(josa_rules.check_josa(fixed)) == 0)

    print("\n[2b] 오탐 가드 — 게이트를 막으면 안 되는 형태들")
    fp = [
        "벤저민 그레이엄의 안전마진 원칙을 봅니다.",      # 외래어
        "판단이 틀렸을 때 멈출 기준도 분명한가요?",      # 의문문 종결어미
        "계속 보유할 이유를 지금 갖고 계신가요?",
        "3일 사이 65% 가까이 급등했습니다.",            # '이'가 명사 끝음절
        "누군가 왔다.",
    ]
    for t in fp:
        check(f"오탐 없음: {t[:22]}", not josa_rules.check_josa(t),
              ",".join(i["excerpt"] for i in josa_rules.check_josa(t)))

    print("\n[3] 깨끗한 대본 — 1라운드 통과, LLM 아끼기")
    CALLS["n"] = 0
    r0 = script_gate.validate(SAMPLE, call_llm=fake_call_llm, name="테스트",
                              use_llm=True, max_rounds=2)
    check("통과", r0.passed, r0.summary()[:60])
    check("LLM 불필요하게 호출 안 함", CALLS["n"] == 0, f"{CALLS['n']}회")

    print("\n[4] 교정 필요한 대본 — 동기 컨텍스트")
    CALLS["n"] = 0
    r1 = script_gate.validate(SAMPLE_NEEDS_FIX, call_llm=fake_call_llm, name="테스트",
                              use_llm=True, max_rounds=2)
    check("반환됨", r1 is not None)
    check("조사 오류 자동 교정", r1.josa_errors == 0, f"잔여 {r1.josa_errors}건")
    check("동기에서 LLM 호출됨", CALLS["n"] > 0, f"{CALLS['n']}회")
    check("render_report 동작", len(script_gate.render_report(r1, "테스트")) > 100)

    print("\n[5] 비동기 컨텍스트 — ★핵심 회귀★")
    CALLS["n"] = 0

    async def from_async():
        # stage2_long._generate_and_tts 와 같은 상황:
        # 이미 asyncio.run() 안에서 실행 중
        return script_gate.validate(SAMPLE_NEEDS_FIX, call_llm=fake_call_llm,
                                    name="테스트", use_llm=True, max_rounds=2)

    r2 = asyncio.run(from_async())
    check("예외 없이 반환", r2 is not None)
    check("★이벤트 루프 안에서 LLM 호출 성공★", CALLS["n"] > 0, f"{CALLS['n']}회 (이전엔 0회)")
    check("proofread_done 표시", r2.proofread_done is True, "이전엔 무조건 False였음")
    check("render_report 동작", len(script_gate.render_report(r2, "테스트")) > 100)

    print("\n[6] 라운드당 LLM 1회만 (중복 호출 제거)")
    CALLS["n"] = 0
    script_gate.validate(SAMPLE_NEEDS_FIX, call_llm=fake_call_llm, name="테스트",
                         use_llm=True, max_rounds=2)
    check("최대 2회 (라운드 2개 × 1회)", CALLS["n"] <= 2, f"{CALLS['n']}회")
    check("이전엔 최대 9회였음", CALLS["n"] < 9)

    print("\n[7] 조사 오류가 통과 판정에 반영")
    check("테스트 문자열에 오류 존재", len(josa_rules.check_josa(SAMPLE_NEEDS_FIX)) > 0)
    check("자동 교정 후 잔여 0", r1.josa_errors == 0)
    check("리포트와 판정 일치",
          (r1.passed == (r1.total_errors <= script_gate.MAX_ERRORS)),
          f"passed={r1.passed} errors={r1.total_errors}")

    print("\n[8] use_llm=False 경로 (LLM 미사용)")
    r4 = script_gate.validate(SAMPLE, call_llm=None, use_llm=False, max_rounds=1)
    check("동작", r4 is not None)
    check("proofread_done False", r4.proofread_done is False)

    print("\n[9] llm_proofread 반환 계약")
    out = asyncio.run(llm_proofread.proofread("", fake_call_llm, "x"))
    check("짧은 텍스트 → (원문, False)", out == ("", False))

    async def boom(prompt):
        raise RuntimeError("API 500")

    out2 = asyncio.run(llm_proofread.proofread(SAMPLE, boom, "테스트"))
    check("실패 → (원문, False)", out2 == (SAMPLE, False))

    out3 = asyncio.run(llm_proofread.proofread(SAMPLE, fake_call_llm, "테스트"))
    check("성공 → (텍스트, True)", out3[1] is True)

    print("\n" + "=" * 52)
    print(f"통과 {29 - len(FAILS)}  실패 {len(FAILS)}")
    for f in FAILS:
        print(f"  · {f}")
    print("=" * 52)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
