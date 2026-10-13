#!/usr/bin/env python3
import asyncio
import json
from pathlib import Path
import stage2_long
import stage3_audio
import json

script = Path('data/script_long_084670.txt').read_text(encoding='utf-8')

facts = {
    'close': 37200.0,
    'change_rate': 29.91,
    'volume': 1435338,
    'trading_value': 52451794875,
    'high_52w': '172,800',
    'low_52w': '0',
    'range_pos': '22%',
    'from_high': '-78.5%',
    'market_cap': '1100억',
    'trading_value': '524억',
    'change_rate': '+29.91%',
    'high_52w': '172,800',
    'low_52w': '0'
}

async def main():
    audio = await stage2_long._tts_long(Path('data/script_long_084670.txt').read_text(encoding='utf-8'), '084670')
    print(f'TTS done: {Path(audio).stat().st_size} bytes')
    
    import stage3_audio
    w = stage3_audio.extract_word_timestamps(Path(audio), script_text=Path('data/script_long_084670.txt').read_text(encoding='utf-8'), company_name='동양고속')
    print(f'Timestamps: {len(w)} tokens')
    for x in w:
        if '고속' in x['word'] or '37' in x['word'] or '172' in x['word'] or '38' in x['word']:
            print(f"  {x['start']:7.2f} {x['word']!r}")

    # stage4_render 는 {ticker: item} 형태를 읽는다.
    # ticker 를 item 안에 한 번 더 감싸면 stage 4 가 item["audio"] 에서 실패한다.
    import chart_data

    series = None
    try:
        from datetime import datetime, timedelta

        from pykrx import stock

        import screening as _scr

        tday = _scr.last_trading_day(stock)
        end = datetime.strptime(tday, '%Y%m%d')
        hist = stock.get_market_ohlcv_by_date(
            (end - timedelta(days=365)).strftime('%Y%m%d'), tday, '084670'
        )
        series = chart_data.to_series(hist)
    except Exception as exc:
        print(f'series 생성 실패 (PNG 폴백으로 진행): {exc}')

    m = {
        'name': '동양고속',
        # 전체 경로여야 한다 — 파일명만 주면 Remotion 이 자산을 못 찾는다
        'audio': str(Path(audio).resolve()),
        'timestamps': w,
        'script': {
            'ticker': '084670',
            'name': '동양고속',
            'hook': '',
            'body': [],
            'closing': '',
        },
        'long_text': script,
        'series': series,
        'facts': {
            'close': 37200.0,
            'change_rate': 29.91,
            'volume': 1435338,
            'trading_value': 52451794875,
            'high_52w': '172,800',
            'low_52w': '0',
            'range_pos': '22%',
            'from_high': '-78.5%',
            'market_cap': '1100억',
        },
    }

    with open('data/long_manifest.json', 'w', encoding='utf-8') as f:
        json.dump({'084670': m}, f, ensure_ascii=False, indent=2)
    print('Manifest saved')


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())