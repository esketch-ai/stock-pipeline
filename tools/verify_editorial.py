"""실제 장편 대본 3편을 생성하여 종목 간 중복률과 검토용 원문 저장."""
import asyncio
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import editorial
import investment_lenses
import facts
import script_long
import stage2_script


async def main():
    output = config.DATA_DIR / 'editorial_review' / datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True)
    print(f'검토 결과: {output}', flush=True)
    candidates = json.loads((config.STATE_DIR / 'candidates.json').read_text())[:3]
    results = []
    reserved = []
    for candidate in candidates:
        ticker, name = candidate['ticker'], candidate['name']
        source = facts.collect(ticker, name, candidate['market'])
        brief = editorial.stock_brief(source, candidate['reason'])
        lens = investment_lenses.allocate(source, reserved)
        outline = await investment_lenses.make_outline(
            facts.format_facts(source), candidate['reason'], brief, lens,
            [r['editorial_plan']['outline'] for r in results], stage2_script._call_llm,
        )
        lens['outline'] = outline
        brief += '\n' + investment_lenses.instruction(lens)
        prior = '\n'.join(f"{r['name']}: {r['text'][:300]}" for r in results)
        for attempt in range(2):
            result = await script_long.generate_long_script(
                facts.format_facts(source), candidate['reason'], name, ticker,
                stage2_script._call_llm, target_chars=config.LONG_TARGET_CHARS,
                section_gap=config.LONG_SECTION_GAP,
                editorial_brief=brief + '\n[앞선 도입 재사용 금지]\n' + prior,
                editorial_plan=outline,
            )
            duplicate = any(editorial.overlap(result['text'], p['text'], [name, p['name']]) >= .30 for p in results)
            if not duplicate:
                break
            brief += '\n다른 종목과 겹쳤으므로 핵심 질문과 근거 제시 순서를 다시 설계한다.'
        result.update(ticker=ticker, name=name, facts=source, editorial_brief=brief, editorial_plan=lens, duplicate=duplicate)
        results.append(result)
        (output / f'{ticker}_{name}.txt').write_text(result['text'], encoding='utf-8')
        (output / f'{ticker}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"{ticker} {name}: {len(result['text'])}자, 중복={duplicate}", flush=True)
    pairs = [dict(a=a['name'], b=b['name'], overlap=round(editorial.overlap(a['text'], b['text'], [a['name'], b['name']]), 4))
             for a, b in itertools.combinations(results, 2)]
    (output / 'comparison.json').write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(pairs, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
