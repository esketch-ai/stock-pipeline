"""로컬 모델 비교 — 같은 구간 프롬프트로 속도와 반복 경향을 본다.

사용 방법:
    OLLAMA_MODEL=qwen3:8b venv/bin/python tools/compare_llm.py
"""
from __future__ import annotations

import asyncio
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import script_long  # noqa: E402
import stage2_script  # noqa: E402


async def main() -> int:
    print(f"모델: {config.OLLAMA_MODEL}\n", flush=True)
    plans = sorted(glob.glob(str(config.DATA_DIR / "editorial_review" / "*" / "PLAN_*.json")))[-3:]
    if not plans:
        print("비교할 계획 파일이 없습니다 (tools/plan_batch3.py 먼저 실행).")
        return 1

    for plan_file in plans:
        record = json.loads(Path(plan_file).read_text(encoding="utf-8"))
        plan = record["editorial_plan"]
        facts = record["facts"]
        prompt = script_long.build_section_prompt(
            "hook", "오프닝", 140,
            "\n".join([
                f"- 종목코드: {record['ticker']} ({record['name']})",
                f"- 현재가: {facts.get('close')}",
                f"- 등락률: {facts.get('change_rate')}",
                f"- 시가총액: {facts.get('market_cap')}",
                f"- 52주 신고가: {facts.get('high_52w')}",
                f"- 신고가 대비: {facts.get('from_high')}",
                f"- 52주 레인지 내 현재 위치: {facts.get('range_pos')}",
            ]),
            record["reason"], record["name"], record["ticker"],
            editorial_brief=plan["principle"] + "\n" + plan["question"],
        )
        started = time.time()
        text = script_long._clean(await stage2_script._call_llm(prompt))
        elapsed = time.time() - started
        sentences = script_long._split_sentences(text)
        # 같은 모델 안에서 반복되는지는 구간 1개로는 보이지 않는다 → 생성되는 한 편 전체를 보고 판단한다.
        print(f"{record['ticker']} {record['name']} · {elapsed:.1f}s · {len(text)}자 · 문장 {len(sentences)}")
        print(f"  {text[:160]}\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))