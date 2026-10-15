"""자본 보존형(Capital Preservation) 방어 시스템 종목 스크리너 및 리포트 생성기.

워런 버핏의 제1원칙("절대로 돈을 잃지 마라")과 하워드 막스, 세스 클라만, 레이 달리오, 폴 튜더 존스의
하방 위험 통제 4단계 규칙을 적용하여 전 종목 또는 후보군을 검증하고 최종 유효 종목을 선별합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import capital_preservation
import chart_data
import config
import naver_finance
from logger import log


DEFAULT_CANDIDATES = [
    ("005930", "삼성전자", "전기전자"),
    ("000660", "SK하이닉스", "전기전자"),
    ("089590", "제주항공", "운수창고"),
    ("011330", "유니켐", "피혁제조"),
    ("084010", "대한제강", "철강금속"),
    ("010580", "에스엠벡셀", "자동차부품"),
    ("009190", "대양금속", "철강금속"),
    ("272450", "진에어", "운수창고"),
    ("015260", "에이엔피", "인쇄회로기판"),
    ("028670", "팬오션", "해운운수"),
    ("004700", "조광피혁", "피혁제조"),
    ("006840", "AK홀딩스", "지주회사"),
    ("011200", "HMM", "해운운수"),
    ("071090", "하이스틸", "철강금속"),
    ("000180", "성창기업지주", "지주회사"),
    ("298690", "에어부산", "운수창고"),
]


def run_screening(
    stock_list: List[tuple[str, str, str]] = DEFAULT_CANDIDATES,
    total_capital: float = 100_000_000,
) -> Dict[str, Any]:
    """자본 보존형 4단계 스크리닝 실행."""
    log.info("자본 보존형(Capital Preservation) 스크리닝 시작 (대상 %d개 종목)", len(stock_list))

    # 1. 시장 레짐 진단 (하워드 막스 2단계)
    market_res = capital_preservation.evaluate_market_cycle()
    log.info(
        "시장 사이클 진단: 코스피 20일 이격도 %.1f%% | 상태: %s | 현금 의무 비중 %.0f%%",
        market_res["disparity_20"],
        market_res["regime"],
        market_res["cash_allocation_pct"],
    )

    evaluated_candidates = []

    for ticker, name, sector in stock_list:
        try:
            series = naver_finance.fetch_ohlcv_naver(ticker, count=180)
            if not series or not series.get("c"):
                log.warning("%s OHLCV 데이터 누락으로 건너뜀", name)
                continue

            levels = chart_data.support_resistance(series) or {}
            eval_res = capital_preservation.evaluate_capital_preservation(
                ticker=ticker,
                name=name,
                series=series,
                levels=levels,
                total_capital=total_capital,
            )
            eval_res["sector"] = sector
            eval_res["series"] = series
            evaluated_candidates.append(eval_res)
            log.info(
                "[%s] %s: 총점 %d점 | F-Score %d | 손익비 %.2f:1 | 적격=%s",
                ticker,
                name,
                eval_res["total_score"],
                eval_res["step1_moat"]["f_score"],
                eval_res["step4_trade"]["rr_ratio"],
                eval_res["is_overall_passed"],
            )
        except Exception as exc:
            log.error("%s(%s) 스크리닝 중 오류: %s", name, ticker, exc)

    # 2. 레이 달리오 비상관성 및 섹터 30% 캡 필터링 (3단계)
    passed_raw = [c for c in evaluated_candidates if c["is_overall_passed"]]
    final_portfolio = capital_preservation.filter_uncorrelated_portfolio(
        passed_raw, max_corr=0.70, max_sector_ratio=0.30
    )

    result = {
        "screened_at": datetime.now().isoformat(timespec="seconds"),
        "total_analyzed": len(evaluated_candidates),
        "total_passed": len(passed_raw),
        "final_selected": len(final_portfolio),
        "market_cycle": market_res,
        "selected_stocks": [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "sector": s["sector"],
                "score": s["total_score"],
                "f_score": s["step1_moat"]["f_score"],
                "margin_of_safety": s["step3_safety"]["status"],
                "rr_ratio": s["step4_trade"]["rr_ratio"],
                "entry_price": s["step4_trade"]["entry_price"],
                "stop_loss": s["step4_trade"]["stop_loss_price"],
                "target_price": s["step4_trade"]["target_price"],
                "shares": s["step4_trade"]["shares_to_buy"],
                "investment": s["step4_trade"]["total_investment"],
                "summary": s["defense_summary"],
            }
            for s in final_portfolio
        ],
        "all_evaluations": [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "sector": s["sector"],
                "score": s["total_score"],
                "passed": s["is_overall_passed"],
                "f_score": s["step1_moat"]["f_score"],
                "rr_ratio": s["step4_trade"]["rr_ratio"],
                "summary": s["defense_summary"],
            }
            for s in evaluated_candidates
        ],
    }

    # 리포트 파일 저장
    out_json = config.DATA_DIR / "defense_screening_result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("스크리닝 결과 저장 완료: %s", out_json)

    return result


def generate_markdown_report(res: Dict[str, Any]) -> str:
    """스크리닝 결과를 깔끔한 마크다운 리포트로 포맷팅."""
    m = res["market_cycle"]
    lines = [
        "# 🛡️ 자본 보존형(Capital Preservation) 종목 스크리닝 리포트",
        f"- **분석 시각**: {res['screened_at']}",
        f"- **총 분석 종목**: {res['total_analyzed']}개 | **기준 적격 종목**: {res['total_passed']}개 | **비상관성 최종 엄선**: {res['final_selected']}개",
        "",
        "## 1. 시장 사이클 진단 (하워드 막스)",
        f"- **코스피 20일 이동평균 이격도**: `{m['disparity_20']}%`",
        f"- **신규 매수 잠금(Buy-Lock)**: `{'🔒 매수 금지 (과열)' if m['buy_lock'] else '🔓 매수 가능 (정상)'}`",
        f"- **권고 현금/무위험자산 비중**: **`{m['cash_allocation_pct']}%`** ({m['regime']})",
        "",
        "## 2. 최종 엄선된 자본 보존형 유효 종목 (세스 클라만 & 폴 튜더 존스)",
        "| 종목명 (티커) | 섹터 | 점수 | F-Score | 안전마진 | 손익비(R/R) | 진입가 | 손절가 | 추천 수량 |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for s in res["selected_stocks"]:
        lines.append(
            f"| **{s['name']}** ({s['ticker']}) | {s['sector']} | {s['score']}점 | "
            f"**{s['f_score']}/9점** | {s['margin_of_safety']} | **{s['rr_ratio']}:1** | "
            f"{s['entry_price']:,}원 | {s['stop_loss']:,}원 | **{s['shares']:,}주** |"
        )

    if not res["selected_stocks"]:
        lines.append("| (엄격한 방어 기준을 통과한 종목이 없습니다. 현금 비중 확대를 권고합니다) | - | - | - | - | - | - | - | - |")

    lines.extend([
        "",
        "## 3. 전체 종목 평가 현황",
        "| 종목 | 섹터 | 점수 | 적격 여부 | F-Score | 손익비 | 평가 요약 |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ])

    for s in res["all_evaluations"]:
        p_badge = "✅ 통과" if s["passed"] else "❌ 미달"
        lines.append(
            f"| {s['name']} ({s['ticker']}) | {s['sector']} | {s['score']}점 | {p_badge} | "
            f"{s['f_score']}점 | {s['rr_ratio']}:1 | {s['summary']} |"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    result = run_screening()
    report = generate_markdown_report(result)
    print("\n" + report)
    report_path = config.DATA_DIR / "defense_screening_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✔ 마크다운 리포트 생성 완료: {report_path}")
