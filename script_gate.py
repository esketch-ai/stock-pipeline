"""대본 검증 게이트.

파이프라인이 오디오/비디오를 만들기 **전에** 반드시 통과해야 한다.
순서:
    1. korean_lint    — 규칙 기반 한국어 검출
    2. numeric_verify — 숫자 계산 검증 (원본 데이터 대조)
    3. josa_rules     — 조사/어법 검사 (신조법)
    4. 자동 교정       — 규칙 교정 + 조사 교정 (안전한 것만)
    5. llm_proofread  — 의미층 교정 (LLM)
    6. 판정           — error 가 남으면 생산 중단

게이트를 통과한 대본만 TTS·렌더로 넘어간다.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import josa_rules
import korean_lint
import llm_proofread
import numeric_verify
from logger import log

# 생산 차단 기준
MAX_ERRORS = 0        # 오류는 0개여야 통과
MAX_WARNINGS = 12     # 경고는 어느 정도 허용


@dataclass
class GateResult:
    passed: bool
    text: str
    lint_score: int = 0
    lint_errors: int = 0
    lint_warnings: int = 0
    josa_errors: int = 0
    num_checked: int = 0
    num_errors: int = 0
    num_warnings: int = 0
    auto_fixed: list[str] = field(default_factory=list)
    proofread_done: bool = False
    issues: list[dict] = field(default_factory=list)
    inspections: list[str] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return self.lint_errors + self.num_errors + self.josa_errors

    @property
    def total_warnings(self) -> int:
        return self.lint_warnings + self.num_warnings

    def summary(self) -> str:
        status = "✅ 통과" if self.passed else "⛔ 차단"
        return (
            f"{status} | 한국어 {self.lint_score}점 "
            f"(오류 {self.lint_errors}, 경고 {self.lint_warnings})"
            f" | 조사 오류 {self.josa_errors}"
            f" | 숫자 검사 {self.num_checked}건 (오류 {self.num_errors}, 경고 {self.num_warnings})"
        )

    def to_dict(self) -> dict:
        """JSON 직렬화용 dict (대시보드·아카이브가 읽는다).

        stage2_long 이 통과/차단 두 경로 모두에서 이 메서드를 호출하므로
        없으면 단계 2 가 무조건 죽는다.
        """
        from dataclasses import asdict

        d = asdict(self)
        d["total_errors"] = self.total_errors
        d["total_warnings"] = self.total_warnings
        d["summary"] = self.summary()
        return d


def _run_coro(coro):
    """코루틴을 실행한다 — 이미 이벤트 루프가 있든 없든.

    validate() 는 동기 컨텍스트(_test_gate.py) 와 비동기 컨텍스트
    (stage2_long 의 asyncio.run 안, dashboard 의 FastAPI 안) 양쪽에서
    호출된다. asyncio.run() 을 그대로 쓰면 비동기 쪽에서
    "asyncio.run() cannot be called from a running event loop" 로 죽는다.
    (이 예전부터 LLM 교정이 매 라운드 실패했다)

    루프가 이미 돌고 있으면 별도 스레드에 새 루프를 만들어 거기서 돌린다.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _lint_to_issues(lint: korean_lint.LintResult) -> list[dict]:
    return [
        {
            "level": i.level,
            "kind": i.kind,
            "message": i.message,
            "excerpt": i.excerpt[:80],
            "position": i.position,
            "suggestion": i.suggestion,
        }
        for i in lint.issues
    ]


def _num_to_issues(num: numeric_verify.NumResult) -> list[dict]:
    return [
        {
            "level": i.level,
            "kind": i.kind,
            "message": i.message,
            "claim": i.claim,
            "actual": i.actual,
            "suggestion": i.suggestion,
        }
        for i in num.issues
    ]


def _apply_auto_fixes(text: str, result: GateResult) -> str:
    """안전한 자동 교정을 적용한다 (규칙 + 조사)."""
    fixed, fixes = korean_lint.auto_fix(text)
    if fixed != text:
        result.auto_fixed.extend(f.message for f in fixes)
        log.info("자동 교정 %d건 적용", len(fixes))
    text = fixed

    fixed, jfixes = josa_rules.auto_fix_josa(text)
    if fixed != text:
        # josa_rules 는 issue dict 를, korean_lint 는 message 속성 객체를 돌려준다
        result.auto_fixed.extend(i["message"] for i in jfixes)
        log.info("조사 자동 교정 %d건 적용", len(jfixes))
    text = fixed

    return text


def validate(
    text: str,
    facts: dict | None = None,
    reason: str = "",
    hist=None,
    call_llm=None,
    name: str = "",
    use_llm: bool = True,
    max_rounds: int = 2,
) -> GateResult:
    """대본을 검증하고 통과 여부를 판정한다.

    call_llm 이 주어지면 의미층 교정을 수행한다 (비동기 callable).
    라운드마다 '검사 → 교정' 을 반복하고, 통과하면 즉시 반환한다.
    """
    result = GateResult(passed=False, text=text)
    use_llm = use_llm and call_llm is not None

    for rnd in range(max_rounds + 1):
        # ── 1. 한국어 규칙 검사 ──
        lint = korean_lint.check(text)
        result.lint_score = lint.score
        result.lint_errors = len(lint.errors)
        result.lint_warnings = len(lint.warnings)
        result.issues = _lint_to_issues(lint)

        # ── 2. 숫자 검증 ──
        num = numeric_verify.verify(text, facts or {}, reason, hist)
        result.num_checked = num.checked
        result.num_errors = len(num.errors)
        result.num_warnings = len(num.warnings)
        result.issues += _num_to_issues(num)

        # ── 3. 조사/어법 검사 (신조법) ──
        josa_issues = josa_rules.check_josa(text)
        result.josa_errors = sum(1 for i in josa_issues if i["level"] == "error")
        result.issues += josa_issues

        # ── 4. 판정 ──
        # LLM 교정은 숫자를 바꿀 수 있다 → 숫자 오류가 있으면 손대지 않는다
        if result.num_errors:
            log.warning(
                "숫자 오류 %d건 — LLM 교정 건너뜀 (LLM 은 수치를 바꿀 수 있음)",
                result.num_errors,
            )
            break

        if result.total_errors <= MAX_ERRORS and result.total_warnings <= MAX_WARNINGS:
            result.passed = True
            result.text = text
            log.info("대본 검증 %s (라운드 %d)", result.summary(), rnd + 1)
            return result

        if rnd >= max_rounds:
            break

        # ── 5. 안전한 자동 교정 ──
        text = _apply_auto_fixes(text, result)

        # ── 6. LLM 의미층 교정 ──
        if use_llm:
            try:
                text, done = _run_coro(llm_proofread.proofread(text, call_llm, name))
                result.proofread_done = result.proofread_done or done
            except Exception as exc:
                log.warning("LLM 교정 실패: %s", exc)

    # 마지막 라운드 결과를 텍스트에 반영하고 판정
    lint = korean_lint.check(text)
    result.lint_score = lint.score
    result.lint_errors = len(lint.errors)
    result.lint_warnings = len(lint.warnings)
    result.issues = _lint_to_issues(lint)

    num = numeric_verify.verify(text, facts or {}, reason, hist)
    result.num_checked = num.checked
    result.num_errors = len(num.errors)
    result.num_warnings = len(num.warnings)
    result.issues += _num_to_issues(num)

    josa_issues = josa_rules.check_josa(text)
    result.josa_errors = sum(1 for i in josa_issues if i["level"] == "error")
    result.issues += josa_issues

    result.text = text
    result.passed = (
        result.total_errors <= MAX_ERRORS and result.total_warnings <= MAX_WARNINGS
    )

    if result.passed:
        log.info("대본 검증 %s (자동 교정 후)", result.summary())
        return result

    log.error("대본 검증 실패 — 생산 차단: %s", result.summary())
    for i in [x for x in result.issues if x["level"] == "error"][:5]:
        log.error("  · [%s] %s", i["kind"], i["message"])
    return result


def render_report(result: GateResult, name: str = "") -> str:
    """검증 리포트를 사람이 읽을 수 있는 텍스트로."""
    josa_state = josa_rules.summary(josa_rules.check_josa(result.text))
    lines = [
        "=" * 60,
        f"대본 검증 리포트 {name}",
        "=" * 60,
        result.summary(),
        f"자동 교정: {len(result.auto_fixed)}건  |  LLM 교정: "
        f"{'완료' if result.proofread_done else '미실시'}  |  "
        f"조사 검사: {josa_state}",
        "",
    ]
    errors = [i for i in result.issues if i["level"] == "error"]
    warns = [i for i in result.issues if i["level"] == "warn"]

    if errors:
        lines.append(f"[오류 {len(errors)}건] — 생산 차단 사유")
        for i in errors[:20]:
            lines.append(f"  ✗ {i['kind']:10} {i['message']}")
            if i.get("suggestion"):
                lines.append(f"      → {i['suggestion']}")
        lines.append("")

    if warns:
        lines.append(f"[경고 {len(warns)}건]")
        for i in warns[:15]:
            lines.append(f"  ! {i['kind']:10} {i['message']}")
            if i.get("suggestion"):
                lines.append(f"      → {i['suggestion']}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
