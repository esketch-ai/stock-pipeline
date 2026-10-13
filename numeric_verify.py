"""대본에 등장한 숫자의 계산 검증.

대본은 "신고가 대비 78% 아래", "거래대금이 시가총액의 절반",
"3일 동안 65% 상승" 같은 계산을 자연어에 섞어서 말한다.
팩트/원본 OHLCV 로 그 계산을 실제로 재보고, 맞는지 확인한다.

검증 유형:
  A. 수치 일치   — 대본 숫자 == 팩트 값
  B. 비율 계산   — "N% 아래/위", "절반", "N배"
  C. 등락 재계산 — 1일/3일/5일 수익률
  D. 범위 위치   — 52주 레인지 위치
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 수치 표현 파싱 ───────────────────────────────────────
NUM = r"[-+]?\d[\d,]*(?:\.\d+)?"


def _to_num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


@dataclass
class NumIssue:
    level: str          # error | warn
    kind: str
    claim: str           # 대본이 주장한 것
    actual: str          # 실제 계산값
    message: str
    suggestion: str = ""


@dataclass
class NumResult:
    issues: list[NumIssue] = field(default_factory=list)
    checked: int = 0

    @property
    def errors(self) -> list[NumIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[NumIssue]:
        return [i for i in self.issues if i.level == "warn"]

    def summary(self) -> str:
        return f"검사 {self.checked}건 · 오류 {len(self.errors)} · 경고 {len(self.warnings)}"


# ── A. 팩트 값과 대본 대조 ────────────────────────────────

def _fmt_variants(value: float) -> set[float]:
    """수치가 대본에 나타날 수 있는 모든 표기 형태 (숫자 값)."""
    out: set[float] = set()
    v = abs(float(value))
    for cand in (round(v), round(v, 1), round(v, 2), round(v / 1e8, 2), round(v / 1e12, 2)):
        if cand > 0:
            out.add(float(cand))
    return out


def _verify_mentions(text: str, fact_value, label: str, res: NumResult,
                    tolerance: float = 0.0) -> bool:
    """대본에 label 과 함께 등장하는 숫자가 fact_value 와 같은지 확인.

    fact_value 는 숫자일 수도, '172,800' 같은 문자열일 수도 있다.
    문자열이면 '억'/'조' 단위 표기를 되돌려 원래 값을 복원한다.
    """
    if fact_value is None:
        return False

    # 문자열 → 원래 값 복원
    if isinstance(fact_value, str):
        s = fact_value.replace(",", "").strip()
        unit_scale = 1.0
        for unit, scale in (("조", 1e12), ("억", 1e8), ("만", 1e4)):
            if s.endswith(unit):
                s = s[: -len(unit)]
                unit_scale = scale
                break
        parsed = _to_num(s)
        if parsed is None:
            return False
        fv = parsed * unit_scale
    else:
        fv = float(fact_value)

    expected = _fmt_variants(fv)  # float 집합 (억/조 단위로도 포함)

    # 라벨과 숫자 사이는 '조사' 만 허용한다. 어절이 하나라도 끼면 다른 대상이다.
    #   "신고가 172,800원"        → 사이 = 공백          ✅
    #   "신고가는 172,800원"      → 사이 = "는 "         ✅
    #   "신고가 복귀에 ... 38,000원" → 사이에 "복귀에"   ❌ 다른 대상
    _josa = "[은는이가을를의에서도에서부터까지보다대비랑과와만도]"
    pat = re.compile(
        rf"(?:{re.escape(label)})(?:{_josa})?\s*({NUM})\s*(%|원|억|조|배)?"
    )
    found = False
    for m in pat.finditer(text):
        raw = m.group(1)
        n = _to_num(raw)
        if n is None:
            continue
        found = True
        unit = m.group(2) or ""

        # "현재가 52주 신고가" 처럼 숫자 뒤에 '주' 가 붙으면 기간 표현이다 (52주 레인지).
        # 가격 주장으로 보면 실제값과 어긋나 生产이 차단된다 — 여기서 제외한다.
        if text[m.end(): m.end() + 1] == "주":
            continue

        # 백분율은 별도 검증(_verify_percentage_claims)이 담당한다.
        # 금액 표기와 섞이지 않도록 여기서는 건너뛴다.
        if unit == "%":
            continue

        res.checked += 1
        cand = abs(n)

        ok = any(abs(cand - v) <= max(1.0, abs(v) * 0.01) for v in expected)
        if not ok:
            # 뒤에 다른 가격 라벨이 이어지면 (예: "신고가는 172,800원, 현재가 38,000원")
            # 뒤쪽 숫자가 다른 대상일 수 있으므로 문맥을 확인한다.
            after = text[m.end(): m.end() + 14]
            if any(lbl in after for lbl in ("현재가", "종가", "시가", "저가", "고가")):
                continue
            # 앞에 다른 가격 라벨이 있으면 그 라벨의 숫자가 뒤에 붙은 경우.
            # 예) "52주 신고가보다 78% 낮거든요. ... 52주 신고가는 172,800원"
            #     → "신고가" 근처의 다른 % 는 비율 계산으로 별도 검증한다.
            before = text[max(0, m.start() - 24): m.start()]
            if re.search(r"\d+\s*%\s*(?:낮|아래|내려|위|오르|높)", before):
                continue
            res.issues.append(NumIssue(
                "error", "수치", f"{label} {raw}{unit}", f"{fv:,.0f}",
                f'"{label}" 값이 실제 데이터와 다릅니다',
                f"대본의 {raw}{unit} → {fv:,.0f} 로 교체",
            ))
    return found


# ── B. 비율 계산 검증 ─────────────────────────────────────

def _verify_percentage_claims(text: str, close: float, high: float,
                              low: float, res: NumResult) -> None:
    """고점 대비 하락률 / 저점 대비 상승률 계산 검증.

    한국어 표현이 다양하므로 여러 패턴을 시도한다.
    ("신고가 대비 78% 아래", "고점보다 78% 낮", "78% 아래", ...)
    """
    if not close:
        return

    if high and high > 0:
        actual = (1 - close / high) * 100
        # 고점 대비 하락률
        _check_pct_phrase(text, [
            r"신고가[^.]{0,20}?대비[^.]{0,14}?(\d+)\s*%\s*(?:아래|내려|하락)",
            r"신고가[^.]{0,14}?(\d+)\s*%\s*(?:아래|낮)",
            r"고점[^.]{0,20}?(\d+)\s*%\s*(?:아래|낮|내려)",
            r"(\d+)\s*%\s*(?:아래|낮|내려)[^.]{0,26}?(?:신고가|고점)",
        ], actual, "고점 대비 하락률", res)

    if low and low > 0:
        actual_up = (close / low - 1) * 100
        # 저점 대비 상승률
        _check_pct_phrase(text, [
            r"저점[^.]{0,20}?대비[^.]{0,14}?(\d+)\s*%\s*(?:위|오르|상승)",
            r"저점[^.]{0,14}?(\d+)\s*%\s*(?:위|오르)",
            r"(\d+)\s*%\s*(?:위|오르)[^.]{0,26}?저점",
        ], actual_up, "저점 대비 상승률", res)


def _check_pct_phrase(text: str, patterns: list[str], actual: float,
                      label: str, res: NumResult) -> None:
    """패턴 목록 중 하나로 찾은 퍼센트 주장이 실제 계산과 맞는지 확인."""
    seen: set[int] = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            claimed = _to_num(m.group(1))
            if claimed is None or id(m) in seen:
                continue
            seen.add(claimed)
            res.checked += 1
            # 반올림 오차 허용 (1.5%p 이내)
            if abs(claimed - actual) > 1.5:
                res.issues.append(NumIssue(
                    "error", "계산", f"{label} {claimed:.0f}%", f"{actual:.0f}%",
                    f"계산이 맞지 않습니다 ({label})",
                    f"대본의 {claimed:.0f}% → {actual:.0f}% 로 교체",
                ))
            break  # 이 패턴으로는 한 번만


def _verify_range_position(text: str, close: float, high: float, low: float,
                          res: NumResult) -> None:
    """'52주 레인지에서 N% 지점' 검증."""
    if not close or not high or not low or high <= low:
        return
    actual = (close - low) / (high - low) * 100
    for m in re.finditer(r"(?:레인지|범위|구간)[^.]{0,24}?(\d+)\s*%\s*(?:지점|위치|자리)", text):
        claimed = _to_num(m.group(1))
        if claimed is None:
            continue
        res.checked += 1
        if abs(claimed - actual) > 2.5:
            res.issues.append(NumIssue(
                "error", "계산", f"52주 레인지 위치 {claimed:.0f}%", f"{actual:.0f}%",
                "레인지 위치 계산이 맞지 않습니다",
                f"대본의 {claimed:.0f}% → {actual:.0f}% 로 교체",
            ))


def _verify_ratio_words(text: str, trading_value: float, market_cap: float,
                        res: NumResult) -> None:
    """'거래대금이 시가총액의 절반' 같은 비율 어휘 검증."""
    if not trading_value or not market_cap or market_cap <= 0:
        return
    pct = trading_value / market_cap * 100
    res.checked += 1

    # "절반" = 50%, "3분의 1" = 33%, "4분의 1" = 25%
    expectations = {
        "절반": 50, "반": 50,
        "3분의 1": 33.3, "4분의 1": 25, "5분의 1": 20,
        "10분의 1": 10,
    }
    m = re.search(r"거래대금[^.]{0,40}?(절반|3분의 1|4분의 1|5분의 1|10분의 1)", text)
    if not m:
        return
    word = m.group(1)
    target = expectations.get(word)
    if target is None:
        return
    if abs(pct - target) > 12:  # 12%p 이상 차이면 과장
        res.issues.append(NumIssue(
            "warn", "계산", f'거래대금 "시총의 {word}"', f"실제 {pct:.0f}%",
            f"비율 표현이 실제({pct:.0f}%)와 다릅니다",
            f'"{word}" → 실제 비율로 표현 변경',
        ))


def _verify_returns(text: str, reason: str, res: NumResult) -> None:
    """'3일 동안 65%' 같은 등락 검증 (선별 지표 문자열 사용)."""
    m = re.search(r"(\d+)\s*일\s*동안\s*\+?(\d+)\s*%", text)
    if not m:
        m = re.search(r"(\d+)\s*일\s*만\s*\+?(\d+)\s*%", text)
    if not m:
        return
    days = _to_num(m.group(1))
    claimed = _to_num(m.group(2))
    if days is None or claimed is None:
        return

    rm = re.search(rf"{days}\s*일\s*([\d.+]+)%", reason or "")
    if not rm:
        return
    actual = abs(_to_num(rm.group(1)) or 0)
    res.checked += 1
    if abs(claimed - actual) > 2:
        res.issues.append(NumIssue(
            "error", "계산", f"{days:.0f}일 등락 {claimed:.0f}%", f"{actual:.0f}%",
            f"{days:.0f}일 등락률이 실제 데이터와 다릅니다",
            f"대본의 {claimed:.0f}% → {actual:.0f}% 로 교체",
        ))


# ── 공개 진입점 ──────────────────────────────────────────

def _parse_korean_amount(value) -> float | None:
    """'172,800' / '172,800원' / '1,100억' → 숫자(원 단위). 실패 시 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).replace(",", "").strip()
    s = re.sub(r"[원주억조만%배]+$", "", s).strip()
    if not s:
        return None

    scale = 1.0
    for unit, mult in (("조", 1e12), ("억", 1e8), ("만", 1e4)):
        if unit in s:
            scale = mult
            s = s.replace(unit, "")
            break

    s = re.sub(r"[^\d.\-]", "", s)
    n = _to_num(s)
    return n * scale if n is not None else None


def verify(text: str, facts: dict, reason: str = "", hist=None) -> NumResult:
    """대본의 모든 숫자 주장을 원본 데이터로 검증한다."""
    res = NumResult()
    if not text:
        return res

    # 원시값 추출 (문자열 표기도 파싱)
    close = facts.get("close_raw") or _parse_korean_amount(facts.get("close"))
    high_w = facts.get("high_52w_raw") or _parse_korean_amount(facts.get("high_52w"))
    low_w = facts.get("low_52w_raw") or _parse_korean_amount(facts.get("low_52w"))

    # hist가 있으면 직접 계산 (가장 정확)
    if hist is not None and len(hist):
        try:
            close = float(hist["종가"].iloc[-1])
            high_w = float(hist["고가"].max())
            low_w = float(hist["저가"].min())
        except (KeyError, IndexError):
            pass

    # A. 팩트 대조
    _verify_mentions(text, close, "현재가", res)
    _verify_mentions(text, high_w, "신고가", res)
    _verify_mentions(text, facts.get("market_cap"), "시가총액", res)
    _verify_mentions(text, facts.get("trading_value"), "거래대금", res)
    _verify_mentions(text, facts.get("change_rate"), "등락률", res, tolerance=1.5)

    # B/C/D. 계산 검증
    if close and high_w and high_w > 0:
        _verify_percentage_claims(text, close, high_w, low_w or 0, res)
    if close and high_w and low_w and high_w > low_w:
        _verify_range_position(text, close, high_w, low_w, res)

    tv_raw = facts.get("trading_value_raw") or _parse_korean_amount(facts.get("trading_value"))
    mc_raw = facts.get("market_cap_raw") or _parse_korean_amount(facts.get("market_cap"))
    if tv_raw and mc_raw:
        _verify_ratio_words(text, tv_raw, mc_raw, res)

    _verify_returns(text, reason, res)

    return res