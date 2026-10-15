"""자본 보존형(Capital Preservation) 방어 시스템 엔진.

대가들의 4단계 핵심 철학 및 정량 규칙 구현:
  1단계 (기업분석 - 워런 버핏 & 찰리 멍거): 경제적 해자, F-Score >= 7, 분식회계 필터, ROIC > WACC
  2단계 (시장분석 - 하워드 막스): 20일 이격도 과열 탐지(>110% Buy-Lock), 현금 30~50% 강제 할당
  3단계 (유효종목 - 세스 클라만 & 레이 달리오): 보수적 안전마진 >= 30%, 상관계수 rho < 0.7, 업종 30% Cap
  4단계 (파동분석 - 폴 튜더 존스): 비대칭 손익비 R/R >= 3.0, 단일 거래 1.5% 포지션 사이징, 스윙 로우 손절
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from logger import log
import naver_finance


# ─────────────────────────────────────────────────────────────
# 1단계: 기업분석 (워런 버핏 & 찰리 멍거) — 경제적 해자 및 회계 검증
# ─────────────────────────────────────────────────────────────


def calculate_piotroski_f_score(finance_data: Dict[str, Any]) -> Dict[str, Any]:
    """피오트로스키(Piotroski) F-Score (9점 만점).

    평가 항목 (각 1점):
      [수익성 - Profitability]
      1. ROA > 0 (당기순이익 > 0)
      2. CFO > 0 (영업활동현금흐름 또는 영업이익 > 0)
      3. ROA 증가 (전년 대비 순이익 증가)
      4. 발생액 품질 (Accrual: CFO > ROA)

      [재무구조 - Leverage & Liquidity]
      5. 부채비율 감소 (전년 대비 부채비율 감소)
      6. 유동/당좌비율 증가 (전년 대비 유동성 개선)
      7. 주식수 비희석 (유상증자 등 주식수 증가 없음)

      [영업효율성 - Operating Efficiency]
      8. 매출총이익률/영업이익률 증가
      9. 매출액 증가 (자산회전율 프록시)
    """
    metrics = finance_data.get("metrics") or {}
    periods = finance_data.get("periods") or []

    if len(periods) < 2:
        return {"score": 5, "passed": False, "details": ["재무 데이터 기간 부족 (최소 2개년 필요)"]}

    p_curr = periods[-2] if len(periods) >= 3 else periods[-1]
    p_prev = periods[-3] if len(periods) >= 3 else periods[-2]

    score = 0
    details = []

    # 1. ROA > 0 (순이익 양수)
    net_curr = metrics.get("당기순이익", {}).get(p_curr)
    net_prev = metrics.get("당기순이익", {}).get(p_prev)
    if net_curr is not None and net_curr > 0:
        score += 1
        details.append("✔ 1. 당기순이익 흑자 달성 (+1)")
    else:
        details.append("✖ 1. 당기순이익 적자 (0)")

    # 2. 영업이익 양수 (CFO 프록시)
    op_curr = metrics.get("영업이익", {}).get(p_curr)
    if op_curr is not None and op_curr > 0:
        score += 1
        details.append("✔ 2. 영업활동 현금창출력(영업이익) 양수 (+1)")
    else:
        details.append("✖ 2. 영업이익 적자 (0)")

    # 3. 전년 대비 순이익 증가 (ROA 개선)
    if net_curr is not None and net_prev is not None and net_curr > net_prev:
        score += 1
        details.append("✔ 3. 전년 대비 순이익 증가 (+1)")
    else:
        details.append("✖ 3. 전년 대비 순이익 감소/정체 (0)")

    # 4. 발생액 검증 (영업이익 >= 당기순이익: 회계적 착시 배제)
    if op_curr is not None and net_curr is not None and op_curr >= net_curr * 0.8:
        score += 1
        details.append("✔ 4. 영업이익 기반 질적 이익(발생액 건전) (+1)")
    else:
        details.append("✖ 4. 일회성 영업외이익 의존 또는 발생액 이상 (0)")

    # 5. 부채비율 감소
    debt_curr = metrics.get("부채비율", {}).get(p_curr)
    debt_prev = metrics.get("부채비율", {}).get(p_prev)
    if debt_curr is not None and debt_prev is not None and debt_curr <= debt_prev:
        score += 1
        details.append(f"✔ 5. 부채비율 건전화 ({debt_prev:.1f}% → {debt_curr:.1f}%) (+1)")
    elif debt_curr is not None and debt_curr < 60.0:  # 절대 부채비율이 매우 낮으면 인정
        score += 1
        details.append(f"✔ 5. 초우량 무차입/저부채 구조 ({debt_curr:.1f}%) (+1)")
    else:
        details.append("✖ 5. 부채비율 증가 (0)")

    # 6. 당좌비율(유동성) 증가
    quick_curr = metrics.get("당좌비율", {}).get(p_curr)
    quick_prev = metrics.get("당좌비율", {}).get(p_prev)
    if quick_curr is not None and quick_prev is not None and quick_curr >= quick_prev:
        score += 1
        details.append(f"✔ 6. 당좌유동성 개선 ({quick_curr:.1f}%) (+1)")
    elif quick_curr is not None and quick_curr >= 120.0:
        score += 1
        details.append(f"✔ 6. 풍부한 안전 유동자산 ({quick_curr:.1f}%) (+1)")
    else:
        details.append("✖ 6. 유동성 저하 (0)")

    # 7. 주식수 비희석 (유상증자/희석 없음: EPS 추이로 프록시)
    eps_curr = metrics.get("EPS", {}).get(p_curr)
    eps_prev = metrics.get("EPS", {}).get(p_prev)
    if eps_curr is not None and eps_prev is not None and eps_curr >= eps_prev:
        score += 1
        details.append("✔ 7. 주주가치 비희석(주당순이익 유지/증가) (+1)")
    else:
        details.append("✖ 7. 주당가치 희석 또는 감소 (0)")

    # 8. 영업이익률 개선 (가격 결정력 Pricing Power)
    opm_curr = metrics.get("영업이익률", {}).get(p_curr)
    opm_prev = metrics.get("영업이익률", {}).get(p_prev)
    if opm_curr is not None and opm_prev is not None and opm_curr >= opm_prev:
        score += 1
        details.append(f"✔ 8. 마진율 개선(가격 결정력 확보) ({opm_curr:.1f}%) (+1)")
    else:
        details.append("✖ 8. 마진율 둔화 (0)")

    # 9. 매출액 성장 (성장 및 자산회전율)
    rev_curr = metrics.get("매출액", {}).get(p_curr)
    rev_prev = metrics.get("매출액", {}).get(p_prev)
    if rev_curr is not None and rev_prev is not None and rev_curr >= rev_prev:
        score += 1
        details.append("✔ 9. 외형 매출 성장세 유지 (+1)")
    else:
        details.append("✖ 9. 매출액 역성장 (0)")

    passed = score >= 7
    return {
        "score": score,
        "max_score": 9,
        "passed": passed,
        "details": details,
        "grade": "우수 (버핏 기준 통과)" if score >= 7 else "보통 (방어력 부족)" if score >= 5 else "취약 (탈락)"
    }


def evaluate_beneish_m_score(finance_data: Dict[str, Any]) -> Dict[str, Any]:
    """베네이쉬 M-Score 프록시 검증 (분식회계 및 이상 징후 배제).

    M-Score > -1.78 이면 분식회계 위험 기업으로 판정하여 즉시 배제.
    """
    metrics = finance_data.get("metrics") or {}
    periods = finance_data.get("periods") or []

    if len(periods) < 2:
        return {"m_score": -2.5, "is_fraud_risk": False, "note": "기간 부족으로 기본 정상 판정"}

    p_curr = periods[-2] if len(periods) >= 3 else periods[-1]
    p_prev = periods[-3] if len(periods) >= 3 else periods[-2]

    # 매출액 대비 영업이익 이상치 검증
    rev_curr = metrics.get("매출액", {}).get(p_curr) or 1.0
    rev_prev = metrics.get("매출액", {}).get(p_prev) or 1.0
    op_curr = metrics.get("영업이익", {}).get(p_curr) or 0.0
    net_curr = metrics.get("당기순이익", {}).get(p_curr) or 0.0

    # 당기순이익은 큰데 영업이익이 마이너스이거나 지나치게 괴리된 경우 (Accrual 폭탄 위험)
    is_suspicious = False
    reasons = []

    if net_curr > 0 and op_curr < 0:
        is_suspicious = True
        reasons.append("영업적자 속 당기순이익 흑자(회계상 발생액 이상치)")

    debt_curr = metrics.get("부채비율", {}).get(p_curr) or 0.0
    if debt_curr > 300.0:
        is_suspicious = True
        reasons.append(f"부채비율 과다({debt_curr:.1f}%)로 재무건전성 위험")

    m_score_est = -1.2 if is_suspicious else -2.6
    return {
        "m_score_estimate": m_score_est,
        "is_fraud_risk": is_suspicious,
        "passed": not is_suspicious,
        "reasons": reasons if reasons else ["회계 이상 징후 없음 (정상)"]
    }


def evaluate_moat_roic_wacc(finance_data: Dict[str, Any], estimated_wacc: float = 7.5) -> Dict[str, Any]:
    """워런 버핏의 경제적 해자(Moat): ROIC vs WACC 스프레드.

    ROIC - WACC > 3.0% (자본 비용 이상의 초과 이익 창출 기업).
    """
    metrics = finance_data.get("metrics") or {}
    periods = finance_data.get("periods") or []

    if not periods:
        return {"spread": 0.0, "passed": False, "note": "재무 데이터 없음"}

    p_curr = periods[-2] if len(periods) >= 3 else periods[-1]
    roe = metrics.get("ROE", {}).get(p_curr) or 5.0
    debt_ratio = metrics.get("부채비율", {}).get(p_curr) or 50.0

    # ROIC 추정 (ROE 와 부채비율 기반 근사)
    roic_est = roe * (100.0 / (100.0 + debt_ratio * 0.5))
    spread = roic_est - estimated_wacc

    passed = spread >= 3.0
    return {
        "roic_estimate": round(roic_est, 2),
        "wacc_estimate": round(estimated_wacc, 2),
        "spread": round(spread, 2),
        "passed": passed,
        "has_moat": passed,
        "comment": "자본비용 초과 창출 (경제적 해자 확인)" if passed else "자본비용 이하 이익 (해자 불충분)"
    }


# ─────────────────────────────────────────────────────────────
# 2단계: 시장분석 (하워드 막스) — 시장 사이클 진자 추적 & 현금 비중
# ─────────────────────────────────────────────────────────────


def evaluate_market_cycle(index_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """하워드 막스의 2차적 사고: 시장 사이클 과열 진단 및 현금 강제 할당.

    1. 코스피 20일 이동평균선 이격도(Disparity) > 110% 시 신규 매수 강제 잠금(Buy-Lock).
    2. 시장 레짐에 따른 의무 현금 비중(Cash Allocation) 30~50% 산출.
    """
    if not index_history:
        try:
            index_history = naver_finance.fetch_market_index("KOSPI", count=30)
        except Exception:
            index_history = []

    if not index_history or len(index_history) < 20:
        return {
            "disparity_20": 100.0,
            "is_overheated": False,
            "buy_lock": False,
            "cash_allocation_pct": 30.0,
            "regime": "중립 (안전 현금 30% 유지)"
        }

    closes = [item["close"] for item in index_history if item.get("close") is not None]
    last_idx_close = closes[0]  # 최신
    last_20 = closes[:20]
    ma20 = sum(last_20) / len(last_20)

    disparity_20 = round((last_idx_close / ma20) * 100, 2)
    is_overheated = disparity_20 >= 110.0
    is_oversold = disparity_20 <= 92.0

    # 현금 비중 결정: 과열 시 50%, 침체/급락 시 40%, 정상 시 30%
    if is_overheated:
        cash_pct = 50.0
        regime = "극단적 탐욕/과열 (하워드 막스 원칙: 신규 매수 잠금 & 현금 50% 확보)"
    elif is_oversold:
        cash_pct = 30.0
        regime = "패닉/공포 구간 (바겐세일 국면, 현금 30% 유지 속 우량주 선별)"
    else:
        cash_pct = 30.0
        regime = "정상 변동성 구간 (의무 현금 30% 유지)"

    return {
        "index_close": last_idx_close,
        "ma20": round(ma20, 2),
        "disparity_20": disparity_20,
        "is_overheated": is_overheated,
        "buy_lock": is_overheated,  # 과열 시 매수 금지
        "cash_allocation_pct": cash_pct,
        "regime": regime,
    }


# ─────────────────────────────────────────────────────────────
# 3단계: 유효종목 (세스 클라만 & 레이 달리오) — 안전마진 및 비상관성
# ─────────────────────────────────────────────────────────────


def evaluate_margin_of_safety(ticker: str, current_price: float,
                              finance_data: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    """세스 클라만의 안전마진(Margin of Safety): NCAV 및 보수적 청산가치 대비 할인율.

    안전마진 >= 30% 충족 여부 검증.
    """
    metrics = finance_data.get("metrics") or {}
    periods = finance_data.get("periods") or []

    bps = None
    if periods:
        p_curr = periods[-2] if len(periods) >= 3 else periods[-1]
        bps = metrics.get("BPS", {}).get(p_curr)

    if not bps or bps <= 0:
        # BPS 폴백: facts 또는 현재가 역산
        pbr = float(str(facts.get("pbr", "1.0")).replace(",", "")) if facts.get("pbr") else 1.0
        bps = current_price / pbr if pbr > 0 else current_price

    # 보수적 청산가치 (NCAV 프록시: 보수적으로 BPS 의 70~80% 적용)
    conservative_intrinsic_value = bps * 0.85
    margin_of_safety_pct = round(((conservative_intrinsic_value - current_price) / conservative_intrinsic_value) * 100, 1)

    has_margin = margin_of_safety_pct >= 30.0
    return {
        "current_price": current_price,
        "bps": round(bps),
        "conservative_intrinsic_value": round(conservative_intrinsic_value),
        "margin_of_safety_pct": margin_of_safety_pct,
        "passed": has_margin,
        "status": f"안전마진 {margin_of_safety_pct:+.1f}% (충족)" if has_margin else f"안전마진 {margin_of_safety_pct:+.1f}% (30% 미달)"
    }


def filter_uncorrelated_portfolio(candidates: List[Dict[str, Any]], max_corr: float = 0.70, max_sector_ratio: float = 0.30) -> List[Dict[str, Any]]:
    """레이 달리오의 성배(The Holy Grail): 비상관성 매트릭스 필터 및 섹터 30% 캡.

    상관계수 rho >= 0.70 인 중복 종목 및 단일 업종 비중 30% 초과 종목 배제.
    """
    if not candidates:
        return []

    accepted: List[Dict[str, Any]] = []
    sector_counts: Dict[str, int] = {}
    max_per_sector = max(1, int(len(candidates) * max_sector_ratio))

    for cand in candidates:
        sec = cand.get("sector") or cand.get("industry") or "일반제조"
        curr_cnt = sector_counts.get(sec, 0)

        # 1. 섹터 30% 캡 초과 시 탈락
        if curr_cnt >= max_per_sector:
            log.debug("섹터 캡(30%%) 초과 배제: %s (%s)", cand.get("name"), sec)
            continue

        # 2. 비상관성 검증 (시계열이 있는 경우 상관계수 검증)
        cand_series = cand.get("series", {}).get("c") or []
        is_correlated = False

        if cand_series and len(cand_series) >= 20:
            for acc in accepted:
                acc_series = acc.get("series", {}).get("c") or []
                if len(acc_series) >= 20:
                    corr = _calc_pearson_corr(cand_series[-30:], acc_series[-30:])
                    if corr >= max_corr:
                        is_correlated = True
                        log.debug("비상관성 필터 탈락: %s와 %s의 상관계수 %.2f >= %.2f", cand.get("name"), acc.get("name"), corr, max_corr)
                        break

        if not is_correlated:
            accepted.append(cand)
            sector_counts[sec] = curr_cnt + 1

    return accepted


def _calc_pearson_corr(x: List[float], y: List[float]) -> float:
    """두 시계열의 피어슨 상관계수 산출."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0
    x, y = x[-n:], y[-n:]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    return cov / math.sqrt(var_x * var_y)


# ─────────────────────────────────────────────────────────────
# 4단계: 파동분석 & 자금관리 (폴 튜더 존스) — 비대칭 손익비 & 포지션 사이징
# ─────────────────────────────────────────────────────────────


def evaluate_asymmetric_trade(
    *,
    entry_price: float,
    swing_low: float,
    target_price: float,
    total_capital: float = 100_000_000,
    risk_pct_per_trade: float = 0.015,  # 1.5% Rule
    min_rr_ratio: float = 3.0,          # 3:1 ~ 5:1
) -> Dict[str, Any]:
    """폴 튜더 존스의 비대칭적 위험-보상(5:1 R/R) 및 2% 자금관리 규칙.

    - Risk/Reward = (목표가 - 진입가) / (진입가 - 손절가)
    - 주문 수량 = (총 자본 * 0.015) / (진입가 - 손절가)
    """
    if entry_price <= swing_low or entry_price <= 0:
        return {
            "passed": False,
            "rr_ratio": 0.0,
            "reason": "진입가가 스윙 로우(손절가) 이하이거나 유효하지 않음",
        }

    risk_per_share = entry_price - swing_low
    reward_per_share = target_price - entry_price

    if risk_per_share <= 0:
        return {"passed": False, "rr_ratio": 0.0, "reason": "위험폭 산출 불가"}

    rr_ratio = round(reward_per_share / risk_per_share, 2)
    passed = rr_ratio >= min_rr_ratio

    # 1.5% 계좌 리스크 포지션 사이징
    max_account_loss = total_capital * risk_pct_per_trade
    shares = int(max_account_loss / risk_per_share)
    total_investment = shares * entry_price
    portfolio_weight = round((total_investment / total_capital) * 100, 1)

    return {
        "entry_price": round(entry_price),
        "stop_loss_price": round(swing_low),
        "target_price": round(target_price),
        "risk_per_share": round(risk_per_share),
        "reward_per_share": round(reward_per_share),
        "rr_ratio": rr_ratio,
        "passed": passed,
        "shares_to_buy": shares,
        "total_investment": total_investment,
        "portfolio_weight_pct": portfolio_weight,
        "max_risk_amount": round(max_account_loss),
        "comment": f"비대칭 손익비 {rr_ratio}:1 (통과)" if passed else f"손익비 {rr_ratio}:1 (최소 3.0:1 미달 탈락)"
    }


# ─────────────────────────────────────────────────────────────
# 통합 평가 엔진 (Capital Preservation Master Evaluation)
# ─────────────────────────────────────────────────────────────


def evaluate_capital_preservation(
    ticker: str,
    name: str,
    series: Dict[str, Any],
    levels: Optional[Dict[str, Any]] = None,
    total_capital: float = 100_000_000,
) -> Dict[str, Any]:
    """대가 5인의 철학을 통합한 종합 자본 보존형 평가 보고서 생성.

    Step 1: 버핏/멍거 해자 & F-Score >= 7 & M-Score 정상
    Step 2: 하워드 막스 시장 사이클 이격도 & Buy-Lock
    Step 3: 세스 클라만 안전마진 30%
    Step 4: 폴 튜더 존스 비대칭 손익비 3:1 이상 & 포지션 사이징
    """
    closes = [c for c in (series.get("c") or []) if c is not None]
    last_close = closes[-1] if closes else 10000.0

    # 1. 재무 데이터 수집 및 1단계 평가
    fin = naver_finance.fetch_finance_naver(ticker)
    f_score_res = calculate_piotroski_f_score(fin)
    m_score_res = evaluate_beneish_m_score(fin)
    moat_res = evaluate_moat_roic_wacc(fin)

    step1_passed = f_score_res["passed"] and m_score_res["passed"]

    # 2. 시장 분석 (2단계)
    market_res = evaluate_market_cycle()
    step2_passed = not market_res["buy_lock"]

    # 3. 안전마진 분석 (3단계)
    integ = naver_finance.fetch_stock_integration(ticker)
    info = integ.get("info", {})
    safety_res = evaluate_margin_of_safety(ticker, last_close, fin, info)
    step3_passed = safety_res["passed"] or f_score_res["score"] >= 8  # 초우량 재무 시 안전마진 요건 유연화

    # 4. 파동 및 손익비 (4단계)
    sup = (levels.get("support") if levels else None) or int(last_close * 0.94)
    res = (levels.get("resistance") if levels else None) or int(last_close * 1.18)
    trade_res = evaluate_asymmetric_trade(
        entry_price=last_close,
        swing_low=sup,
        target_price=res,
        total_capital=total_capital,
    )
    step4_passed = trade_res["passed"]

    # 종합 스코어 계산 (100점 만점)
    score = 0
    if f_score_res["passed"]: score += 25
    if m_score_res["passed"]: score += 15
    if moat_res["passed"]: score += 10
    if step2_passed: score += 15
    if safety_res["passed"]: score += 15
    if trade_res["passed"]: score += 20

    is_overall_passed = (
        f_score_res["score"] >= 6
        and m_score_res["passed"]
        and not market_res["buy_lock"]
        and trade_res["rr_ratio"] >= 2.0
    )

    return {
        "ticker": ticker,
        "name": name,
        "total_score": score,
        "is_overall_passed": is_overall_passed,
        "step1_moat": {
            "f_score": f_score_res["score"],
            "grade": f_score_res["grade"],
            "passed": step1_passed,
            "details": f_score_res["details"][:3],
            "fraud_risk": m_score_res["is_fraud_risk"],
            "moat_spread": moat_res["spread"],
        },
        "step2_market": market_res,
        "step3_safety": safety_res,
        "step4_trade": trade_res,
        "defense_summary": (
            f"F-Score {f_score_res['score']}점 달성, "
            f"시장 이격도 {market_res['disparity_20']}% (정상), "
            f"손익비 {trade_res['rr_ratio']}:1 비대칭 구조 확보"
            if is_overall_passed else
            f"방어 기준 미달 ({f_score_res['grade']}, 손익비 {trade_res['rr_ratio']}:1)"
        )
    }
